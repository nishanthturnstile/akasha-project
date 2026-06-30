"""Slice 2 (Phase 2 raster de-risk) unit tests for the Akasha BFF.

Covers (no Docker / no MinIO required):
  * index registry + STAC band-name -> position mapping (incl. RGB [1,8,9])
  * pure-numpy masked statistics engine: offset/scale correction, SCL masking,
    pixel accounting, and a deterministic NDVI numeric reference
  * geometry validation + area guardrails (error shapes)
  * product endpoints via FastAPI TestClient (config/sources/dates/layers + the
    standard error shape for invalid/oversized/unsupported requests)
  * (when rasterio is installed) a full synthetic dual-COG read -> mask -> stat
    pipeline that proves NDVI end-to-end without the real 2.24 GiB scene
"""

import json

import numpy as np
import pytest
from app.main import app
from app.raster import catalog_resolver as catalog
from app.raster import indices
from app.raster.errors import AkashaError
from app.raster.statistics_core import compute_index_statistics, correct_reflectance
from fastapi.testclient import TestClient

client = TestClient(app)

IN_FOOTPRINT_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]],
}

SENTINEL2_BAND_ROLE_MAPPING = {
    "BLUE": "B02",
    "GREEN": "B03",
    "RED": "B04",
    "NIR": "B08",
    "RED_EDGE": "B05",
    "SWIR1": "B11",
    "SWIR2": "B12",
}


# --------------------------------------------------------------------------
# index registry + band mapping
# --------------------------------------------------------------------------
def test_index_registry_has_supported_core_indices():
    assert set(indices.INDEX_REGISTRY) == {
        "NDVI",
        "MSAVI",
        "NDRE",
        "NDMI",
        "NDWI_GREEN_NIR",
    }
    assert indices.DEFAULT_INDEX == "NDVI"


def test_statistics_openapi_documents_source_neutral_metadata_fields():
    schema = client.get("/api/openapi.json").json()
    metadata = schema["components"]["schemas"]["StatisticsMetadata"]
    properties = metadata["properties"]

    assert properties["maskMethod"]["type"] == "string"
    assert properties["nativeExcludedMaskClasses"]["items"]["type"] == "integer"
    assert properties["metricsProvisional"]["type"] == "boolean"
    assert properties["warnings"]["items"]["type"] == "string"

    response = schema["components"]["schemas"]["StatisticsResponse"]
    metadata_ref = response["properties"]["metadata"]["$ref"]
    assert metadata_ref.endswith("/StatisticsMetadata")


def test_ndvi_band_assignment_is_nir_minus_red():
    ndvi = indices.get_index("NDVI")
    assert ndvi.required_roles == ("NIR", "RED")
    assert ndvi.formula == "(NIR - RED) / (NIR + RED)"


def test_msavi_formula_uses_nir_and_red_roles():
    msavi = indices.get_index("MSAVI")
    assert msavi.formula_kind == "msavi"
    assert msavi.required_roles == ("NIR", "RED")
    assert "sqrt" in msavi.formula


def test_band_name_to_position_uses_frozen_order():
    pos = indices.band_name_to_position(indices.FROZEN_ANALYTIC_BANDS)
    assert pos["B04"] == 1  # red
    assert pos["B08"] == 2  # nir
    assert pos["B03"] == 8  # green
    assert pos["B02"] == 9  # blue


def test_role_to_position_resolves_sentinel2_mapping():
    pos = indices.role_to_position(indices.FROZEN_ANALYTIC_BANDS, SENTINEL2_BAND_ROLE_MAPPING)
    assert pos["RED"] == 1
    assert pos["NIR"] == 2
    assert pos["GREEN"] == 8


def test_rgb_positions_are_1_8_9_not_1_2_3():
    assert indices.rgb_band_positions(indices.FROZEN_ANALYTIC_BANDS) == [1, 8, 9]


def test_fcc_positions_use_nir_red_green_roles():
    assert indices.fcc_band_positions(
        ["BAND2", "BAND3", "BAND4", "BAND5"],
        {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5"},
    ) == [3, 2, 1]


# --------------------------------------------------------------------------
# pure-numpy statistics engine
# --------------------------------------------------------------------------
def test_reflectance_correction_formula():
    dn = np.array([2000, 4000, 0], dtype="uint16")
    out = correct_reflectance(dn, 0.0001, -0.1)
    assert np.allclose(out, [0.1, 0.3, -0.1])


def test_ndvi_reference_with_offset_and_masking():
    # 3x3 window: NDVI=0.5 everywhere valid (red=2000->0.1, nir=4000->0.3).
    nir = np.full((3, 3), 4000, dtype="uint16")
    red = np.full((3, 3), 2000, dtype="uint16")
    scl = np.full((3, 3), 4, dtype="uint8")  # vegetation -> kept
    geom = np.ones((3, 3), dtype=bool)
    scl[0, 0] = 9  # cloud high -> excluded
    red[0, 1] = 0  # analytic nodata
    geom[0, 2] = False  # outside polygon

    s = compute_index_statistics(
        index_type="NDVI",
        band_a_dn=nir,
        band_b_dn=red,
        mask=scl,
        geometry_mask=geom,
        scale=0.0001,
        offset=-0.1,
        nodata=0,
    ).as_dict()

    assert s["totalPixels"] == 8
    assert s["nodataPixels"] == 1
    assert s["coveragePixels"] == 7
    assert s["maskedPixels"] == 1
    assert s["validPixels"] == 6
    assert s["mean"] == pytest.approx(0.5)
    assert s["min"] == pytest.approx(0.5) and s["max"] == pytest.approx(0.5)
    assert s["stddev"] == pytest.approx(0.0)
    assert s["validPixelPercent"] == pytest.approx(75.0)
    assert s["cloudMaskedPercent"] == pytest.approx(12.5)
    assert s["coveragePercent"] == pytest.approx(87.5)


def test_mask_only_nodata_policy_keeps_single_zero_band_pixels():
    stats = compute_index_statistics(
        index_type="NDVI",
        band_a_dn=np.array([[0, 5000]], dtype="uint16"),
        band_b_dn=np.array([[1000, 2000]], dtype="uint16"),
        mask=np.array([[1, 1]], dtype="uint8"),
        geometry_mask=np.array([[True, True]]),
        scale=0.0001,
        offset=0.0,
        nodata=0,
        excluded_mask_classes=(0, 2, 3),
        analytic_nodata_policy="mask_only",
    ).as_dict()

    assert stats["nodataPixels"] == 0
    assert stats["coveragePixels"] == 2
    assert stats["validPixels"] == 2
    assert stats["coveragePercent"] == 100.0


def test_offset_does_not_cancel_in_ndvi():
    # With offset: 0.5 ; without offset: 0.2/0.6 = 0.3333 -> must differ.
    nir = np.full((2, 2), 4000, dtype="uint16")
    red = np.full((2, 2), 2000, dtype="uint16")
    scl = np.full((2, 2), 4, dtype="uint8")
    geom = np.ones((2, 2), dtype=bool)
    with_off = compute_index_statistics(
        index_type="NDVI",
        band_a_dn=nir,
        band_b_dn=red,
        mask=scl,
        geometry_mask=geom,
        scale=0.0001,
        offset=-0.1,
        nodata=0,
    ).mean
    no_off = compute_index_statistics(
        index_type="NDVI",
        band_a_dn=nir,
        band_b_dn=red,
        mask=scl,
        geometry_mask=geom,
        scale=0.0001,
        offset=0.0,
        nodata=0,
    ).mean
    assert with_off == pytest.approx(0.5)
    assert no_off == pytest.approx(1 / 3, abs=1e-4)
    assert abs(with_off - no_off) > 0.1


def test_water_class_6_is_kept_clouds_excluded():
    nir = np.full((1, 4), 4000, dtype="uint16")
    red = np.full((1, 4), 2000, dtype="uint16")
    geom = np.ones((1, 4), dtype=bool)
    scl = np.array([[4, 6, 8, 3]], dtype="uint8")  # veg, water, cloud-med, cloud-shadow
    s = compute_index_statistics(
        index_type="NDVI",
        band_a_dn=nir,
        band_b_dn=red,
        mask=scl,
        geometry_mask=geom,
        scale=0.0001,
        offset=-0.1,
        nodata=0,
    ).as_dict()
    # veg (4) + water (6) kept = 2 valid ; classes 8 and 3 excluded = 2.
    assert s["validPixels"] == 2
    assert s["maskedPixels"] == 2


# --------------------------------------------------------------------------
# geometry validation
# --------------------------------------------------------------------------
def test_validate_polygon_accepts_in_footprint_and_reports_area():
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    from app.raster.geo_validate import validate_polygon

    facts = validate_polygon(IN_FOOTPRINT_POLY, max_area_ha=50, max_vertices=5000)
    assert facts["vertices"] == 5
    assert 10 < facts["areaHa"] < 50  # ~30 ha at this latitude


def test_validate_polygon_rejects_non_polygon():
    from app.raster.errors import AkashaError
    from app.raster.geo_validate import validate_polygon

    with pytest.raises(AkashaError) as ei:
        validate_polygon({"type": "Point", "coordinates": [78.2, 12.1]})
    assert ei.value.code == "INVALID_GEOMETRY"
    assert ei.value.status_code == 422


def test_validate_polygon_enforces_max_area():
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    from app.raster.errors import AkashaError
    from app.raster.geo_validate import validate_polygon

    big = {"type": "Polygon", "coordinates": [[[78, 12], [79, 12], [79, 13], [78, 13], [78, 12]]]}
    with pytest.raises(AkashaError) as ei:
        validate_polygon(big, max_area_ha=50)
    assert ei.value.code == "POLYGON_TOO_LARGE"
    assert ei.value.status_code == 413


# --------------------------------------------------------------------------
# product endpoints (TestClient)
# --------------------------------------------------------------------------
def test_config_endpoint_contract():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["supportedIndices"] == [
        "NDVI",
        "MSAVI",
        "NDRE",
        "NDMI",
        "NDWI_GREEN_NIR",
    ]
    assert body["defaultIndex"] == "NDVI"
    assert body["indexFieldsKind"] == "global-optical-defaults"
    assert body["adminIngestionLiveTriggerEnabled"] is False
    assert body["maxPolygonAreaHa"] == 50
    assert body["aoi"]["id"] == "bangalore-60km"
    assert body["aoi"]["name"] == "Bangalore 60 km"
    assert body["aoi"]["center"] == [77.5776037099731, 13.076858177177233]
    assert body["aoi"]["bounds"] == [77.023647, 12.537266, 78.131561, 13.61645]
    assert body["aoi"]["geometry"]["type"] == "Polygon"
    assert body["aois"][0]["id"] == "bangalore-60km"
    assert body["aois"][0]["geometry"]["type"] == "Polygon"
    assert body["basemapStyleUrl"] == ""
    assert body["basemap"] == {
        "provider": "esri",
        "style": "arcgis/imagery",
        "styleFamily": "arcgis",
        "usageModel": "session",
        "places": "none",
        "sessionDurationSeconds": 43200,
    }
    assert "arcgis/imagery" in r.text


def _aoi_feature(aoi_id: str, west: float, south: float, east: float, north: float):
    return {
        "type": "Feature",
        "properties": {
            "id": aoi_id,
            "name": aoi_id.replace("-", " ").title(),
            "center": [(west + east) / 2, (south + north) / 2],
            "zoom": 10,
            "radiusMeters": 60000,
            "compositeGridCrs": "EPSG:32643",
        },
        "bbox": [west, south, east, north],
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[west, south], [east, south], [east, north], [west, north], [west, south]]
            ],
        },
    }


def test_config_endpoint_lists_configured_aois_and_keeps_path_aoi_default(tmp_path, monkeypatch):
    from app.config import settings

    primary = tmp_path / "bangalore-60km.geojson"
    aoi_dir = tmp_path / "aois"
    aoi_dir.mkdir()
    mysore = aoi_dir / "mysore-60km.geojson"
    primary.write_text(
        json.dumps(_aoi_feature("bangalore-60km", 77.0, 12.0, 78.0, 13.0)),
        encoding="utf-8",
    )
    mysore.write_text(
        json.dumps(_aoi_feature("mysore-60km", 76.0, 11.5, 77.0, 12.5)),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "aoi_config_path", str(primary), raising=False)
    monkeypatch.setattr(settings, "aoi_config_dir", str(aoi_dir), raising=False)
    monkeypatch.setattr(settings, "default_aoi_id", "mysore-60km", raising=False)

    r = client.get("/api/config")

    assert r.status_code == 200
    body = r.json()
    assert body["aoi"]["id"] == "bangalore-60km"
    assert [aoi["id"] for aoi in body["aois"]] == ["bangalore-60km", "mysore-60km"]
    assert body["aois"][1]["compositeGridCrs"] == "EPSG:32643"


def test_config_endpoint_ignores_missing_optional_aoi_dir(tmp_path, monkeypatch):
    from app.config import settings

    primary = tmp_path / "bangalore-60km.geojson"
    primary.write_text(
        json.dumps(_aoi_feature("bangalore-60km", 77.0, 12.0, 78.0, 13.0)),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "aoi_config_path", str(primary), raising=False)
    monkeypatch.setattr(settings, "aoi_config_dir", str(tmp_path / "missing-aois"), raising=False)
    monkeypatch.setattr(settings, "default_aoi_id", "", raising=False)

    r = client.get("/api/config")

    assert r.status_code == 200
    body = r.json()
    assert body["aoi"]["id"] == "bangalore-60km"
    assert [aoi["id"] for aoi in body["aois"]] == ["bangalore-60km"]


def test_sources_endpoint_contract():
    r = client.get("/api/sources")
    assert r.status_code == 200
    sources = {src["id"]: src for src in r.json()}
    assert "sentinel-2-l2a" not in sources
    assert "sentinel-1-grd" not in sources
    rs = sources["resourcesat-2a-liss3-boa"]
    assert rs["provider"] == "ISRO/NRSC Bhoonidhi"
    assert rs["supportedIndices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert rs["bandRoleMapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert rs["maskAsset"] == "mask"
    # FCC base imagery + optical index display modes (EOS-style LAYER picker).
    assert rs["displayModes"] == ["FCC", "NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert rs["defaultDisplayMode"] == "FCC"
    assert rs["mapDisplayModes"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert rs["defaultMapDisplayMode"] == "NDVI"
    assert [g["label"] for g in rs["layerGroups"]] == [
        "Imagery",
        "Vegetation Indices",
        "Moisture Indices",
        "Water Index",
    ]
    assert rs["layerGroups"][3]["modes"] == ["NDWI_GREEN_NIR"]
    assert rs["availableMaskOptions"] == ["clouds", "cloudShadows"]
    assert rs["metricsProvisional"] is True
    awifs = sources["resourcesat-2a-awifs-boa"]
    assert awifs["availabilityStatus"] == "active"
    assert awifs["gatedReason"] is None
    assert awifs["analysisLevel"] == "regional"
    assert awifs["resolutionMeters"] == 56
    assert awifs["supportedIndices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["displayModes"] == ["FCC", "NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["mapDisplayModes"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["defaultDisplayMode"] == "FCC"
    assert sources["resourcesat-2a-liss4-mx70-l2"]["availabilityStatus"] == "active"
    liss4 = catalog.source_payload("resourcesat-2a-liss4-mx70-l2")
    assert liss4["availabilityStatus"] == "active"
    assert liss4["gatedReason"] is None
    assert liss4["analysisLevel"] == "field"
    assert liss4["supportedIndices"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert "NDMI" not in liss4["supportedIndices"]
    assert "NDRE" not in liss4["supportedIndices"]
    assert "NDMI" not in liss4["displayModes"]
    assert "NDRE" not in liss4["displayModes"]
    assert "RECI" not in liss4["displayModes"]
    assert "NDMI" not in liss4["mapDisplayModes"]
    assert "NDRE" not in liss4["mapDisplayModes"]
    assert "RECI" not in liss4["mapDisplayModes"]
    assert liss4["bandRoleMapping"] == {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4"}
    assert liss4["displayModes"] == ["FCC", "NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert liss4["mapDisplayModes"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert liss4["defaultMapDisplayMode"] == "NDVI"
    assert [g["label"] for g in liss4["layerGroups"]] == [
        "Imagery",
        "Vegetation Indices",
        "Water Index",
    ]
    assert liss4["maskMethod"] == "Akasha threshold mask v1 (LISS-4, no SWIR; provisional)"
    assert liss4["resolutionMeters"] == 5.8
    assert liss4["metricsProvisional"] is True
    assert "ISRO" in liss4["attribution"]
    assert "NRSC" in liss4["attribution"]
    assert "Bhoonidhi" in liss4["attribution"]
    assert sources["eos-06-ocm-lac-ndvi-8day-360m"]["availabilityStatus"] == "gated"
    assert sources["eos-06-ocm-lac-ndvi-8day-360m"]["kind"] == "context"
    assert sources["eos-06-ocm-lac-ndvi-8day-360m"]["supportedIndices"] == []
    assert sources["eos-06-ocm-lac-ndvi-8day-360m"]["displayModes"] == ["NDVI_CONTEXT"]
    # EOS-04 is validated for backend SAR-assist, but not directly product-active.
    assert sources["eos-04-sar-mrs-l2b"]["kind"] == "sar"
    assert sources["eos-04-sar-mrs-l2b"]["availabilityStatus"] == "gated"
    assert "backend SAR-assisted" in sources["eos-04-sar-mrs-l2b"]["gatedReason"]
    assert sources["eos-04-sar-mrs-l2b"]["supportedIndices"] == []
    assert sources["eos-04-sar-mrs-l2b"]["displayModes"] == ["VV_GRAYSCALE"]
    assert sources["nisar-ssar-beta-gcov"]["kind"] == "sar"
    assert sources["nisar-ssar-beta-gcov"]["availabilityStatus"] == "gated"
    assert sources["nisar-ssar-beta-gcov"]["supportedIndices"] == []
    assert sources["nisar-ssar-beta-gcov"]["displayModes"] == ["VV_GRAYSCALE"]
    cartosat = sources["cartosat-3-gated"]
    assert cartosat["availabilityStatus"] == "gated"
    assert cartosat["kind"] == "context"
    assert cartosat["analysisLevel"] == "context"
    assert cartosat["expectedAssets"] == ["visual"]
    assert cartosat["supportedIndices"] == []
    assert cartosat["displayModes"] == ["CONTEXT"]
    assert cartosat["gatedReason"]
    assert sources["irs-1c-liss3-archive"]["kind"] == "archive"
    assert sources["irs-1c-liss3-archive"]["analysisLevel"] == "archive"


def test_legacy_sentinel_sources_are_opt_in(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setenv("AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES", "true")
    sources = {src["id"]: src for src in catalog.list_sources()}
    src = sources["sentinel-2-l2a"]
    assert "NDVI" in src["supportedIndices"]
    assert src["kind"] == "optical"
    assert src["bandRoleMapping"]["NIR"] == "B08"
    assert src["maskAsset"] == "scl"
    # RGB stays the default layer; index display modes are additive (EOS-style picker).
    assert src["displayModes"] == ["RGB", "NDVI", "NDRE", "MSAVI", "NDMI"]
    assert src["defaultDisplayMode"] == "RGB"
    s1 = sources["sentinel-1-grd"]
    assert s1["label"] == "Sentinel-1 GRD"
    assert s1["provider"] == "Copernicus"
    assert s1["kind"] == "sar"
    assert s1["displayModes"] == ["VV_GRAYSCALE"]
    assert s1["defaultDisplayMode"] == "VV_GRAYSCALE"
    assert s1["dateMetricsKind"] == "radar"
    assert s1["supportedIndices"] == []


def test_phase5_collection_contracts_are_loadable():
    from app.raster import catalog_resolver as catalog

    for source_id in (
        "eos-06-ocm-lac-ndvi-8day-360m",
        "irs-1c-liss3-archive",
        "cartosat-3-gated",
    ):
        collection = catalog.get_collection(source_id)
        assert collection["id"] == source_id
        assert collection.get("akasha:availability_status") == "gated"

    awifs = catalog.get_collection("resourcesat-2a-awifs-boa")
    assert awifs["id"] == "resourcesat-2a-awifs-boa"
    assert awifs.get("akasha:availability_status") == "active"
    assert awifs.get("akasha:gated_reason") is None

    # EOS-04 / NISAR SAR collections are loadable and now active (display-only).
    for source_id in ("eos-04-sar-mrs-l2b", "nisar-ssar-beta-gcov"):
        collection = catalog.get_collection(source_id)
        assert collection["id"] == source_id
        assert collection.get("akasha:availability_status") == "active"
        assert collection.get("akasha:kind") == "sar"


def test_liss4_seed_collection_and_sample_item_contracts_are_loadable():
    from app.raster import catalog_resolver as catalog

    source_id = "resourcesat-2a-liss4-mx70-l2"
    collection = catalog.get_collection(source_id)
    item = catalog.list_items(source_id)[0]

    assert collection["id"] == source_id
    assert collection["summaries"]["instruments"] == ["liss-4"]
    assert collection["summaries"]["gsd"] == [5.8]
    assert collection["akasha:analysis_level"] == "field"
    assert collection["akasha:supported_indices"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert collection["akasha:display_modes"] == ["FCC", "NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert collection["akasha:fcc_role_order"] == ["NIR", "RED", "GREEN"]
    assert collection["akasha:band_role_mapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
    }
    assert collection["akasha:reflectance"] == {
        "scale": 0.0001,
        "offset": 0,
        "background_value": 0,
        "nodata_policy": "all-band-background-or-warp-gap",
        "note": (
            "LISS-4 L2 reflectance metadata is provisional until staging radiometry " "validation."
        ),
    }
    analytic = collection["item_assets"]["analytic"]
    assert [band["name"] for band in analytic["eo:bands"]] == ["BAND2", "BAND3", "BAND4"]
    assert len(analytic["raster:bands"]) == 3
    assert [c["value"] for c in collection["item_assets"]["mask"]["classification:classes"]] == [
        0,
        1,
        2,
        3,
        4,
    ]

    assert item["collection"] == source_id
    assert item["properties"]["akasha:composite"] is True
    assert item["properties"]["akasha:aoi_id"] == "bangalore-60km"
    assert item["properties"]["proj:epsg"] == 32643
    assert item["properties"]["akasha:composite_resolution_meters"] == 5.8
    assert item["assets"]["analytic"]["href"].startswith(
        "s3://akasha-cogs/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/"
    )
    assert item["assets"]["mask"]["href"].endswith("/mask.tif")


def test_awifs_seed_collection_contract_is_regional_and_active():
    from app.raster import catalog_resolver as catalog

    source_id = "resourcesat-2a-awifs-boa"
    collection = catalog.get_collection(source_id)

    assert collection["id"] == source_id
    assert collection["summaries"]["instruments"] == ["awifs"]
    assert collection["summaries"]["gsd"] == [56]
    assert collection["akasha:bhoonidhi_collection_id"] == "ResourceSat-2A_AWIFS_BOA"
    assert collection["akasha:analysis_level"] == "regional"
    assert collection["akasha:availability_status"] == "active"
    assert collection["akasha:gated_reason"] is None
    assert collection["akasha:supported_indices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert collection["akasha:display_modes"] == ["FCC", "NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert collection["akasha:default_display_mode"] == "FCC"
    assert collection["akasha:fcc_role_order"] == ["NIR", "RED", "GREEN"]
    assert collection["akasha:band_role_mapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert collection["akasha:reflectance"] == {
        "scale": 0.0001,
        "offset": 0,
        "background_value": 0,
        "nodata_policy": "all-band-background-or-warp-gap",
    }
    mask_classes = collection["item_assets"]["mask"]["classification:classes"]
    assert {klass["value"] for klass in mask_classes} == {
        0,
        1,
        2,
        3,
        4,
    }


def test_latest_items_for_empty_registered_source_returns_typed_error(monkeypatch):
    monkeypatch.setattr(catalog, "list_dates", lambda source_id: [])

    with pytest.raises(AkashaError) as exc:
        catalog.latest_items("resourcesat-2a-awifs-boa")

    assert exc.value.code == "SOURCE_HAS_NO_DATES"
    assert exc.value.status_code == 404
    assert exc.value.details["sourceId"] == "resourcesat-2a-awifs-boa"

    eos = catalog.get_collection("eos-06-ocm-lac-ndvi-8day-360m")
    assert eos["akasha:source_kind"] == "context"
    assert eos["akasha:supported_indices"] == []
    irs = catalog.get_collection("irs-1c-liss3-archive")
    assert irs["akasha:source_kind"] == "archive"
    assert irs["akasha:refresh_policy"] == "Archive only; no scheduled refresh."
    eos04 = catalog.get_collection("eos-04-sar-mrs-l2b")
    assert eos04["akasha:kind"] == "sar"
    assert eos04["akasha:supported_indices"] == []
    nisar = catalog.get_collection("nisar-ssar-beta-gcov")
    assert nisar["akasha:default_display_mode"] == "VV_GRAYSCALE"
    cartosat = catalog.get_collection("cartosat-3-gated")
    assert cartosat["akasha:source_kind"] == "context"
    assert cartosat["akasha:expected_assets"] == ["visual"]
    assert cartosat["akasha:supported_indices"] == []
    assert cartosat["akasha:crop_indices_enabled"] is False


def test_legacy_sentinel_seed_dates_are_removed_from_production_seed():
    r = client.get("/api/sources/sentinel-2-l2a/dates")
    assert r.status_code == 200
    assert r.json() == []


def test_registered_empty_source_returns_empty_dates_and_clear_default_layer():
    dates = client.get("/api/sources/resourcesat-2a-awifs-boa/dates")
    assert dates.status_code == 200
    assert dates.json() == []

    layer = client.get("/api/layers/default?sourceId=resourcesat-2a-awifs-boa")
    assert layer.status_code == 200
    body = layer.json()
    assert body["sourceId"] == "resourcesat-2a-awifs-boa"
    assert body["acquisitionDate"] is None
    assert body["displayMode"] == "FCC"
    assert body["tileUrlTemplate"] is None
    assert body["tileAvailable"] is False
    assert body["unavailableReason"]


def test_layers_default_tile_template_is_same_origin_api_route():
    r = client.get("/api/layers/default")
    assert r.status_code == 200
    body = r.json()
    assert body["sourceId"] == "resourcesat-2a-liss3-boa"
    assert body["acquisitionDate"] == "2026-03-19"
    assert body["displayMode"] == "FCC"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png"
    )


def _stac_item(item_id, acquisition_date, bbox, analytic_href, scl_href, usable=80.0):
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "bbox": bbox,
        "properties": {
            "datetime": f"{acquisition_date}T05:00:00Z",
            "akasha:acquisition_date": acquisition_date,
            "akasha:usable_pixel_percent": usable,
            "akasha:cloud_masked_percent": 100.0 - usable,
            "akasha:coverage_percent": 100.0,
            "akasha:is_latest_usable": True,
            "akasha:metrics_provisional": True,
            "proj:epsg": 32643,
        },
        "assets": {
            "analytic": {
                "href": analytic_href,
                "eo:bands": [{"name": name} for name in indices.FROZEN_ANALYTIC_BANDS],
                "raster:bands": [{"scale": 0.0001, "offset": -0.1, "nodata": 0}],
                "proj:epsg": 32643,
            },
            "scl": {"href": scl_href},
        },
    }


def _s1_stac_item(
    item_id,
    acquisition_date,
    bbox,
    backscatter_href,
    coverage=64.0,
    latest=None,
):
    props = {
        "datetime": f"{acquisition_date}T01:30:00Z",
        "akasha:acquisition_date": acquisition_date,
        "akasha:coverage_percent": coverage,
        "sar:polarizations": ["VV", "VH"],
        "proj:epsg": 32643,
    }
    if latest is not None:
        props["akasha:is_latest_usable"] = latest
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-1-grd",
        "bbox": bbox,
        "properties": props,
        "assets": {
            "backscatter": {
                "href": backscatter_href,
                "raster:bands": [{"name": "VV", "nodata": -9999.0}],
                "proj:epsg": 32643,
            }
        },
    }


def _resourcesat_stac_item(
    item_id,
    acquisition_date,
    bbox,
    analytic_href,
    mask_href,
    *,
    composite=False,
    usable=80.0,
    coverage=100.0,
    latest=True,
) -> dict:
    props = {
        "datetime": f"{acquisition_date}T00:00:00Z",
        "akasha:acquisition_date": acquisition_date,
        "akasha:usable_pixel_percent": usable,
        "akasha:cloud_masked_percent": 100.0 - usable,
        "akasha:coverage_percent": coverage,
        "akasha:metrics_provisional": True,
        "akasha:band_role_mapping": {
            "GREEN": "BAND2",
            "RED": "BAND3",
            "NIR": "BAND4",
            "SWIR1": "BAND5",
        },
        "akasha:mask_asset": "mask",
        "proj:epsg": 32643,
    }
    if latest is not None:
        props["akasha:is_latest_usable"] = latest
    if composite:
        props.update(
            {
                "akasha:composite": True,
                "akasha:aoi_id": "bangalore-60km",
                "akasha:period_start": "2026-03-05",
                "akasha:period_end": acquisition_date,
                "akasha:contributing_scenes": [{"id": "scene-a"}, {"id": "scene-b"}],
            }
        )
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "resourcesat-2a-liss3-boa",
        "bbox": bbox,
        "properties": props,
        "assets": {
            "analytic": {
                "href": analytic_href,
                "eo:bands": [{"name": name} for name in ["BAND2", "BAND3", "BAND4", "BAND5"]],
                "raster:bands": [{"scale": 0.0001, "offset": 0, "nodata": 0}],
                "proj:epsg": 32643,
            },
            "mask": {"href": mask_href},
        },
    }


def _context_stac_item(
    source_id: str,
    item_id: str,
    acquisition_date: str,
    bbox: list[float],
    asset_key: str,
    href: str,
    *,
    raster_bands: list[dict] | None = None,
) -> dict:
    return {
        "type": "Feature",
        "id": item_id,
        "collection": source_id,
        "bbox": bbox,
        "properties": {
            "datetime": f"{acquisition_date}T00:00:00Z",
            "akasha:acquisition_date": acquisition_date,
            "akasha:coverage_percent": 100.0,
            "akasha:is_latest_usable": True,
            "akasha:metrics_provisional": True,
            "proj:epsg": 32643,
        },
        "assets": {
            asset_key: {
                "href": href,
                "raster:bands": raster_bands or [{"name": asset_key, "nodata": None}],
                "proj:epsg": 32643,
            }
        },
    }


def test_supported_indices_preserves_explicit_empty_collection(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "get_collection",
        lambda source_id="sentinel-1-grd": {
            "id": source_id,
            "akasha:supported_indices": [],
        },
    )

    assert catalog.supported_indices("sentinel-1-grd") == []


def test_sentinel1_asset_resolution_uses_backscatter_not_optical_assets(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-1-grd": [
            _s1_stac_item(
                "s1-a",
                "2026-04-26",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/a/backscatter.tif",
            )
        ],
    )

    assets = catalog.resolve_assets("sentinel-1-grd", "2026-04-26")
    assert assets["backscatterHref"] == "s3://akasha-cogs/s1/a/backscatter.tif"
    assert assets["bandNames"] == ["VV"]
    assert "analyticHref" not in assets
    assert "sclHref" not in assets


def test_sentinel1_dates_are_radar_safe(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-1-grd": [
            _s1_stac_item(
                "s1-old",
                "2026-04-24",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/old/backscatter.tif",
                coverage=50.0,
            ),
            _s1_stac_item(
                "s1-new",
                "2026-04-26",
                [77.5, 11.5, 79.0, 13.5],
                "s3://akasha-cogs/s1/new/backscatter.tif",
                coverage=70.0,
            ),
        ],
    )

    r = client.get("/api/sources/sentinel-1-grd/dates")
    assert r.status_code == 200
    dates = r.json()
    assert dates[0]["acquisitionDate"] == "2026-04-26"
    assert dates[0]["sceneCount"] == 1
    assert dates[0]["bounds"] == [77.5, 11.5, 79.0, 13.5]
    assert dates[0]["tileAvailable"] is True
    assert dates[0]["usablePixelPercent"] is None
    assert dates[0]["cloudMaskedPercent"] is None
    assert dates[0]["coveragePercent"] == pytest.approx(70.0)
    assert dates[0]["isLatestUsable"] is True
    assert dates[0]["metricsProvisional"] is False


def test_sentinel1_multi_scene_dates_are_not_tile_available(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-1-grd": [
            _s1_stac_item(
                "s1-a",
                "2026-04-26",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/a/backscatter.tif",
            ),
            _s1_stac_item(
                "s1-b",
                "2026-04-26",
                [78.0, 12.0, 79.0, 13.0],
                "s3://akasha-cogs/s1/b/backscatter.tif",
            ),
        ],
    )

    r = client.get("/api/sources/sentinel-1-grd/dates")

    assert r.status_code == 200
    dates = r.json()
    assert dates[0]["sceneCount"] == 2
    assert dates[0]["tileAvailable"] is False
    assert "mosaic backend" in dates[0]["unavailableReason"]
    assert dates[0]["metricsProvisional"] is True


def test_dates_endpoint_deduplicates_same_date_scenes_with_merged_bounds(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-2-l2a": [
            _stac_item(
                "scene-a",
                "2026-01-15",
                [77.0, 12.0, 78.0, 13.0],
                "s3://a",
                "s3://scl-a",
                80.0,
            ),
            _stac_item(
                "scene-b",
                "2026-01-15",
                [78.0, 11.5, 79.0, 13.5],
                "s3://b",
                "s3://scl-b",
                90.0,
            ),
        ],
    )

    r = client.get("/api/sources/sentinel-2-l2a/dates")
    assert r.status_code == 200
    dates = r.json()
    assert len(dates) == 1
    assert dates[0]["acquisitionDate"] == "2026-01-15"
    assert dates[0]["sceneCount"] == 2
    assert dates[0]["bounds"] == [77.0, 11.5, 79.0, 13.5]
    assert dates[0]["usablePixelPercent"] == pytest.approx(85.0)


def test_source_dates_can_be_windowed_by_lookback_days(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-2-l2a": [
            _stac_item(
                "older",
                "2026-01-01",
                [77.0, 12.0, 78.0, 13.0],
                "s3://older",
                "s3://older-scl",
                90.0,
            ),
            _stac_item(
                "latest",
                "2026-03-15",
                [77.0, 12.0, 78.0, 13.0],
                "s3://latest",
                "s3://latest-scl",
                90.0,
            ),
        ],
    )

    r = client.get("/api/sources/sentinel-2-l2a/dates?lookbackDays=30")

    assert r.status_code == 200
    assert [entry["acquisitionDate"] for entry in r.json()] == ["2026-03-15"]


def test_source_dates_reject_invalid_window(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-2-l2a": [
            _stac_item(
                "scene",
                "2026-03-15",
                [77.0, 12.0, 78.0, 13.0],
                "s3://scene",
                "s3://scene-scl",
                90.0,
            )
        ],
    )

    r = client.get("/api/sources/sentinel-2-l2a/dates?startDate=2026-04-01&endDate=2026-03-01")

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_resourcesat_dates_prefer_composite_when_scene_items_coexist(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "scene-a",
                "2026-03-19",
                [77.0, 12.0, 78.0, 13.0],
                "s3://scene-a/analytic.tif",
                "s3://scene-a/mask.tif",
                usable=70.0,
            ),
            _resourcesat_stac_item(
                "composite",
                "2026-03-19",
                [76.5, 11.5, 79.0, 13.5],
                "s3://composite/analytic.tif",
                "s3://composite/mask.tif",
                composite=True,
                usable=92.0,
                coverage=99.0,
            ),
        ],
    )

    r = client.get("/api/sources/resourcesat-2a-liss3-boa/dates")

    assert r.status_code == 200
    dates = r.json()
    assert len(dates) == 1
    assert dates[0]["sceneCount"] == 1
    assert dates[0]["bounds"] == [76.5, 11.5, 79.0, 13.5]
    assert dates[0]["usablePixelPercent"] == pytest.approx(92.0)
    assert dates[0]["coveragePercent"] == pytest.approx(99.0)
    assert dates[0]["tileAvailable"] is True


def test_resourcesat_dates_mark_newest_qualified_composite_latest_when_stac_flag_missing(
    monkeypatch,
):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setenv("USABLE_PIXEL_THRESHOLD_PERCENT", "70")
    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "older-composite",
                "2026-03-19",
                [76.5, 11.5, 79.0, 13.5],
                "s3://older/analytic.tif",
                "s3://older/mask.tif",
                composite=True,
                usable=92.0,
                latest=None,
            ),
            _resourcesat_stac_item(
                "newer-composite",
                "2026-04-18",
                [76.5, 11.5, 79.0, 13.5],
                "s3://newer/analytic.tif",
                "s3://newer/mask.tif",
                composite=True,
                usable=88.0,
                latest=None,
            ),
        ],
    )

    dates = client.get("/api/sources/resourcesat-2a-liss3-boa/dates").json()

    assert dates[0]["acquisitionDate"] == "2026-04-18"
    assert dates[0]["isLatestUsable"] is True
    assert dates[1]["isLatestUsable"] is False


def test_default_layer_uses_resolver_marked_latest_usable_resource_sat_composite(
    monkeypatch,
):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setenv("USABLE_PIXEL_THRESHOLD_PERCENT", "70")
    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "older-composite",
                "2026-03-19",
                [76.5, 11.5, 79.0, 13.5],
                "s3://older/analytic.tif",
                "s3://older/mask.tif",
                composite=True,
                usable=92.0,
                latest=None,
            ),
            _resourcesat_stac_item(
                "newer-composite",
                "2026-04-18",
                [76.5, 11.5, 79.0, 13.5],
                "s3://newer/analytic.tif",
                "s3://newer/mask.tif",
                composite=True,
                usable=88.0,
                latest=None,
            ),
        ],
    )

    body = client.get("/api/layers/default?sourceId=resourcesat-2a-liss3-boa").json()

    assert body["acquisitionDate"] == "2026-04-18"
    assert body["displayMode"] == "FCC"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/resourcesat-2a-liss3-boa/2026-04-18/FCC/{z}/{x}/{y}.png"
    )


def test_resourcesat_dates_do_not_mark_low_quality_composite_latest_when_flag_missing(
    monkeypatch,
):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setenv("USABLE_PIXEL_THRESHOLD_PERCENT", "70")
    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "low-composite",
                "2026-04-18",
                [76.5, 11.5, 79.0, 13.5],
                "s3://low/analytic.tif",
                "s3://low/mask.tif",
                composite=True,
                usable=44.0,
                latest=None,
            ),
        ],
    )

    dates = client.get("/api/sources/resourcesat-2a-liss3-boa/dates").json()

    assert dates[0]["tileAvailable"] is True
    assert dates[0]["usablePixelPercent"] == pytest.approx(44.0)
    assert dates[0]["isLatestUsable"] is False


def test_resourcesat_dates_explain_missing_tile_assets(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "missing-mask",
                "2026-04-18",
                [76.5, 11.5, 79.0, 13.5],
                "s3://missing-mask/analytic.tif",
                None,
                composite=True,
                usable=84.0,
                latest=None,
            ),
        ],
    )

    dates = client.get("/api/sources/resourcesat-2a-liss3-boa/dates").json()

    assert dates[0]["tileAvailable"] is False
    assert "mask" in dates[0]["unavailableReason"]


def test_resourcesat_resolve_assets_prefers_composite_when_scene_items_coexist(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="resourcesat-2a-liss3-boa": [
            _resourcesat_stac_item(
                "scene-a",
                "2026-03-19",
                [77.0, 12.0, 78.0, 13.0],
                "s3://scene-a/analytic.tif",
                "s3://scene-a/mask.tif",
            ),
            _resourcesat_stac_item(
                "composite",
                "2026-03-19",
                [76.5, 11.5, 79.0, 13.5],
                "s3://composite/analytic.tif",
                "s3://composite/mask.tif",
                composite=True,
            ),
        ],
    )

    assets = catalog.resolve_assets_for_date("resourcesat-2a-liss3-boa", "2026-03-19")

    assert len(assets) == 1
    assert assets[0]["itemId"] == "composite"
    assert assets[0]["analyticHref"] == "s3://composite/analytic.tif"
    assert assets[0]["maskHref"] == "s3://composite/mask.tif"


def test_layers_default_uses_merged_bounds_for_latest_date(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-2-l2a": [
            _stac_item("scene-a", "2026-01-15", [77.0, 12.0, 78.0, 13.0], "s3://a", "s3://scl-a"),
            _stac_item("scene-b", "2026-01-15", [78.0, 11.5, 79.0, 13.5], "s3://b", "s3://scl-b"),
        ],
    )

    r = client.get("/api/layers/default?sourceId=sentinel-2-l2a")
    assert r.status_code == 200
    body = r.json()
    assert body["acquisitionDate"] == "2026-01-15"
    assert body["sceneCount"] == 2
    assert body["bounds"] == [77.0, 11.5, 79.0, 13.5]
    assert body["tileUrlTemplate"] == ("/api/tiles/sentinel-2-l2a/2026-01-15/rgb/{z}/{x}/{y}.png")


def test_layers_default_supports_sentinel1_display_mode(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-1-grd": [
            _s1_stac_item(
                "s1-a",
                "2026-04-26",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/a/backscatter.tif",
            )
        ],
    )

    r = client.get("/api/layers/default?sourceId=sentinel-1-grd")
    assert r.status_code == 200
    body = r.json()
    assert body["sourceId"] == "sentinel-1-grd"
    assert body["displayMode"] == "VV_GRAYSCALE"
    assert body["kind"] == "sar"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png"
    )
    assert body["usablePixelPercent"] is None
    assert body["cloudMaskedPercent"] is None


def test_layers_default_uses_resourcesat_natural_fcc_mode():
    r = client.get("/api/layers/default?sourceId=resourcesat-2a-liss3-boa")
    assert r.status_code == 200
    body = r.json()
    assert body["sourceId"] == "resourcesat-2a-liss3-boa"
    assert body["displayMode"] == "FCC"
    assert body["defaultDisplayMode"] == "FCC"
    assert body["mapDisplayModes"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert body["defaultMapDisplayMode"] == "NDVI"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png"
    )


def test_context_source_default_layer_uses_declared_display_asset(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="eos-06-ocm-lac-ndvi-8day-360m": [
            _context_stac_item(
                source_id,
                "eos06-a",
                "2026-04-16",
                [76.5, 11.5, 79.0, 13.5],
                "ndvi",
                "s3://akasha-cogs/eos06/ndvi.tif",
            )
        ],
    )

    dates = client.get("/api/sources/eos-06-ocm-lac-ndvi-8day-360m/dates")
    assert dates.status_code == 200
    assert dates.json()[0]["tileAvailable"] is True
    assert dates.json()[0]["usablePixelPercent"] is None
    assert dates.json()[0]["cloudMaskedPercent"] is None

    layer = client.get("/api/layers/default?sourceId=eos-06-ocm-lac-ndvi-8day-360m")
    assert layer.status_code == 200
    body = layer.json()
    assert body["sourceId"] == "eos-06-ocm-lac-ndvi-8day-360m"
    assert body["displayMode"] == "NDVI_CONTEXT"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/eos-06-ocm-lac-ndvi-8day-360m/2026-04-16/NDVI_CONTEXT/{z}/{x}/{y}.png"
    )


def test_layers_default_skips_unsupported_sentinel1_multi_scene_date(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="sentinel-1-grd": [
            _s1_stac_item(
                "s1-new-a",
                "2026-04-26",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/new-a/backscatter.tif",
            ),
            _s1_stac_item(
                "s1-new-b",
                "2026-04-26",
                [78.0, 12.0, 79.0, 13.0],
                "s3://akasha-cogs/s1/new-b/backscatter.tif",
            ),
            _s1_stac_item(
                "s1-old",
                "2026-04-24",
                [77.0, 12.0, 78.0, 13.0],
                "s3://akasha-cogs/s1/old/backscatter.tif",
            ),
        ],
    )

    r = client.get("/api/layers/default?sourceId=sentinel-1-grd")

    assert r.status_code == 200
    body = r.json()
    assert body["acquisitionDate"] == "2026-04-24"
    assert body["tileAvailable"] is True
    assert body["tileUrlTemplate"] == (
        "/api/tiles/sentinel-1-grd/2026-04-24/VV_GRAYSCALE/{z}/{x}/{y}.png"
    )


def test_tile_route_preserves_single_cog_url_behavior(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "scene-a",
                "analyticHref": "s3://akasha-cogs/a/analytic.tif",
                "sclHref": "s3://akasha-cogs/a/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "epsg": 32643,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            }
        ],
    )

    def fake_render_rgb_tile(**kwargs):
        captured.update(kwargs)
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "render_rgb_tile", fake_render_rgb_tile)

    r = client.get("/api/tiles/sentinel-2-l2a/2026-01-15/rgb/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured == {
        "analytic_href": "s3://akasha-cogs/a/analytic.tif",
        "rgb_positions": [1, 8, 9],
        "z": 3,
        "x": 4,
        "y": 5,
    }


def test_resourcesat_fcc_tile_route_uses_nir_red_green_order(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "resourcesat-scene",
                "analyticHref": "s3://akasha-cogs/resourcesat/analytic.tif",
                "maskHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "sclHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "maskAsset": "mask",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2",
                    "RED": "BAND3",
                    "NIR": "BAND4",
                    "SWIR1": "BAND5",
                },
            }
        ],
    )

    def fake_render_rgb_tile(**kwargs):
        captured.update(kwargs)
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "render_rgb_tile", fake_render_rgb_tile)

    r = client.get("/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured == {
        "analytic_href": "s3://akasha-cogs/resourcesat/analytic.tif",
        "rgb_positions": [3, 2, 1],
        "z": 3,
        "x": 4,
        "y": 5,
    }


def test_ndvi_context_tile_route_uses_declared_context_asset(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "eos06-a",
                "contextHref": "s3://akasha-cogs/eos06/ndvi.tif",
                "contextAsset": "ndvi",
                "bandNames": ["ndvi"],
                "rasterBandCount": 1,
                "bbox": [76.5, 11.5, 79.0, 13.5],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/eos-06-ocm-lac-ndvi-8day-360m/2026-04-16/NDVI_CONTEXT/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Feos06%2Fndvi.tif&bidx=1&"
        "rescale=0%2C1&colormap_name=rdylgn"
    )


def test_visual_context_tile_route_uses_declared_visual_asset(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "cartosat-a",
                "contextHref": "s3://akasha-cogs/cartosat/visual.tif",
                "contextAsset": "visual",
                "bandNames": ["red", "green", "blue"],
                "rasterBandCount": 3,
                "bbox": [76.5, 11.5, 79.0, 13.5],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/cartosat-3-gated/2026-04-16/CONTEXT/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fcartosat%2Fvisual.tif&rescale=0%2C3000"
    )


def test_sentinel1_tile_builder_uses_vv_bidx_and_default_rescale(monkeypatch):
    from app.raster import tiles

    monkeypatch.setenv("AKASHA_S1_VV_RESCALE", "-25,5")
    url = tiles.build_sentinel1_vv_tile_url(
        backscatter_href="s3://akasha-cogs/s1/backscatter.tif",
        z=3,
        x=4,
        y=5,
        titiler_url="http://titiler.internal:8000",
    )

    assert url == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fs1%2Fbackscatter.tif&bidx=1&"
        "rescale=-25%2C5&colormap_name=gray"
    )


def test_sar_tile_builder_can_select_non_first_vv_band(monkeypatch):
    from app.raster import tiles

    monkeypatch.setenv("AKASHA_SAR_VV_RESCALE", "-24,4")
    url = tiles.build_sar_vv_grayscale_tile_url(
        backscatter_href="s3://akasha-cogs/sar/backscatter.tif",
        vv_position=2,
        z=3,
        x=4,
        y=5,
        titiler_url="http://titiler.internal:8000",
    )

    assert url == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fsar%2Fbackscatter.tif&bidx=2&"
        "rescale=-24%2C4&colormap_name=gray"
    )


def test_sentinel1_display_tile_route_uses_backscatter_asset(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "s1-a",
                "backscatterHref": "s3://akasha-cogs/s1/a/backscatter.tif",
                "bandNames": ["VV"],
                "nodata": -9999.0,
                "epsg": 32643,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fs1%2Fa%2Fbackscatter.tif&bidx=1&"
        "rescale=-25%2C5&colormap_name=gray"
    )


def test_eos04_sar_display_tile_route_uses_backscatter_asset(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "eos04-a",
                "backscatterHref": "s3://akasha-cogs/eos-04/a/backscatter.tif",
                "bandNames": ["VV"],
                "nodata": -9999.0,
                "epsg": 32643,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/eos-04-sar-mrs-l2b/2026-04-26/VV_GRAYSCALE/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Feos-04%2Fa%2Fbackscatter.tif&bidx=1&"
        "rescale=-25%2C5&colormap_name=gray"
    )


def test_eos04_sar_asset_resolution_requires_explicit_polarization_metadata(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="eos-04-sar-mrs-l2b": [
            {
                "type": "Feature",
                "id": "eos04-missing-pol",
                "collection": "eos-04-sar-mrs-l2b",
                "bbox": [77.0, 12.0, 78.0, 13.0],
                "properties": {
                    "datetime": "2026-04-26T01:30:00Z",
                    "akasha:acquisition_date": "2026-04-26",
                },
                "assets": {
                    "backscatter": {
                        "href": "s3://akasha-cogs/eos-04/a/backscatter.tif",
                        "raster:bands": [{"nodata": -9999.0}],
                    }
                },
            }
        ],
    )

    with pytest.raises(AkashaError) as exc:
        catalog.resolve_assets_for_date("eos-04-sar-mrs-l2b", "2026-04-26")

    assert exc.value.code == "MISSING_SAR_POLARIZATIONS"
    assert exc.value.details["sourceId"] == "eos-04-sar-mrs-l2b"


def test_eos04_sar_asset_resolution_rejects_generic_band_names(monkeypatch):
    from app.raster import catalog_resolver as catalog

    monkeypatch.setattr(
        catalog,
        "list_items",
        lambda source_id="eos-04-sar-mrs-l2b": [
            {
                "type": "Feature",
                "id": "eos04-b1",
                "collection": "eos-04-sar-mrs-l2b",
                "bbox": [77.0, 12.0, 78.0, 13.0],
                "properties": {
                    "datetime": "2026-04-26T01:30:00Z",
                    "akasha:acquisition_date": "2026-04-26",
                },
                "assets": {
                    "backscatter": {
                        "href": "s3://akasha-cogs/eos-04/a/backscatter.tif",
                        "raster:bands": [{"name": "B1", "nodata": -9999.0}],
                    }
                },
            }
        ],
    )

    with pytest.raises(AkashaError) as exc:
        catalog.resolve_assets_for_date("eos-04-sar-mrs-l2b", "2026-04-26")

    assert exc.value.code == "MISSING_SAR_POLARIZATIONS"
    assert exc.value.details["availableBands"] == ["B1"]


def test_sar_vv_tile_route_uses_actual_vv_band_position(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "nisar-a",
                "backscatterHref": "s3://akasha-cogs/nisar/a/backscatter.tif",
                "bandNames": ["VH_dB", "VV_dB"],
                "nodata": -9999.0,
                "epsg": 32643,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/nisar-ssar-beta-gcov/2026-04-26/VV_GRAYSCALE/3/4/5.png")

    assert r.status_code == 200
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fnisar%2Fa%2Fbackscatter.tif&bidx=2&"
        "rescale=-25%2C5&colormap_name=gray"
    )


def test_sar_tile_route_renders_first_band_when_vv_absent(monkeypatch):
    # EOS-04 SAR-MRS is typically HH/HV (no VV); display-only SAR must still
    # render the primary backscatter band (bidx=1) rather than erroring.
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    captured = {}
    monkeypatch.setenv("TITILER_URL", "http://titiler.internal:8000")
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "eos04-hh-hv",
                "backscatterHref": "s3://akasha-cogs/eos-04/backscatter.tif",
                "bandNames": ["HH_dB", "HV_dB"],
                "nodata": -9999.0,
                "epsg": 32643,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            }
        ],
    )

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/eos-04-sar-mrs-l2b/2026-04-26/VV_GRAYSCALE/3/4/5.png")

    assert r.status_code == 200
    assert r.content == b"png-bytes"
    # First (HH) band is rendered in grayscale with the SAR dB rescale.
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Feos-04%2Fbackscatter.tif&bidx=1&"
        "rescale=-25%2C5&colormap_name=gray"
    )
    # The internal href is never leaked to the browser (only tile bytes).
    assert "s3://" not in r.text
    assert "akasha-cogs" not in r.text


def test_sentinel1_tile_route_rejects_unsupported_display_mode():
    r = client.get("/api/tiles/sentinel-1-grd/2026-04-26/RGB/3/4/5.png")

    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_DISPLAY_MODE"
    assert body["error"]["details"] == {
        "sourceId": "sentinel-1-grd",
        "displayMode": "RGB",
        "supportedDisplayModes": ["VV_GRAYSCALE"],
    }
    assert "s3://" not in r.text


def test_tile_route_multi_scene_fails_without_leaking_cog_hrefs(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import tiles

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "scene-a",
                "analyticHref": "s3://secret-bucket/a/analytic.tif",
                "sclHref": "s3://secret-bucket/a/scl.tif",
                "maskHref": "s3://secret-bucket/a/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
            },
            {
                "itemId": "scene-b",
                "analyticHref": "s3://secret-bucket/b/analytic.tif",
                "sclHref": "s3://secret-bucket/b/scl.tif",
                "maskHref": "s3://secret-bucket/b/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
            },
        ],
    )

    def fail_fetch_tile(url):
        raise AssertionError(f"multi-scene route must not call TiTiler URL: {url}")

    monkeypatch.setattr(tiles, "fetch_tile", fail_fetch_tile)

    r = client.get("/api/tiles/sentinel-2-l2a/2026-01-15/rgb/3/4/5.png")

    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "MOSAIC_TILES_UNAVAILABLE"
    assert body["error"]["details"] == {"sceneCount": 2, "supportedSceneCount": 1}
    assert "s3://" not in r.text
    assert "secret-bucket" not in r.text
    assert "/mosaicjson/tiles" not in r.text


def test_statistics_invalid_geometry_returns_422_error_shape():
    r = client.post(
        "/api/indices/statistics",
        json={"geometry": {"type": "Point", "coordinates": [78.2, 12.1]}, "indexType": "NDVI"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_GEOMETRY"


def test_statistics_unsupported_index_returns_400_error_shape():
    r = client.post(
        "/api/indices/statistics",
        json={"geometry": IN_FOOTPRINT_POLY, "indexType": "NOPE"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_INDEX"


def test_statistics_rejects_sentinel1_optical_index_without_raster_io(monkeypatch):
    from app.raster import catalog_resolver as catalog

    def fail_resolve_assets(*_args, **_kwargs):
        raise AssertionError("Sentinel-1 optical indices must fail before asset resolution")

    monkeypatch.setattr(catalog, "resolve_assets_for_date", fail_resolve_assets)

    r = client.post(
        "/api/indices/statistics",
        json={
            "geometry": IN_FOOTPRINT_POLY,
            "sourceId": "sentinel-1-grd",
            "acquisitionDate": "2026-04-26",
            "indexType": "NDVI",
        },
    )

    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_INDEX"
    assert body["error"]["details"] == {
        "sourceId": "sentinel-1-grd",
        "indexType": "NDVI",
        "supported": [],
    }
    assert "s3://" not in r.text


def test_statistics_rejects_eos04_optical_index_without_raster_io(monkeypatch):
    from app.raster import catalog_resolver as catalog

    def fail_resolve_assets(*_args, **_kwargs):
        raise AssertionError("EOS-04 optical indices must fail before asset resolution")

    monkeypatch.setattr(catalog, "resolve_assets_for_date", fail_resolve_assets)

    r = client.post(
        "/api/indices/statistics",
        json={
            "geometry": IN_FOOTPRINT_POLY,
            "sourceId": "eos-04-sar-mrs-l2b",
            "acquisitionDate": "2026-04-26",
            "indexType": "NDVI",
        },
    )

    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_INDEX"
    assert body["error"]["details"] == {
        "sourceId": "eos-04-sar-mrs-l2b",
        "indexType": "NDVI",
        "supported": [],
    }
    assert "s3://" not in r.text


def test_resourcesat_rejects_unsupported_ndre_without_raster_access(monkeypatch):
    from app.raster import service

    monkeypatch.setattr(
        service,
        "read_index_windows",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not read rasters")),
    )
    r = client.post(
        "/api/indices/statistics",
        json={
            "geometry": IN_FOOTPRINT_POLY,
            "sourceId": "resourcesat-2a-liss3-boa",
            "acquisitionDate": "2026-03-19",
            "indexType": "NDRE",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_INDEX"
    assert body["error"]["details"]["supported"] == [
        "NDVI",
        "MSAVI",
        "NDMI",
        "NDWI_GREEN_NIR",
    ]


def test_resourcesat_statistics_keeps_valid_and_water_mask_classes(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import service
    from app.raster.raster_reader import WindowRead

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "resourcesat-composite",
                "analyticHref": "s3://akasha-cogs/resourcesat/analytic.tif",
                "sclHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "maskHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2",
                    "RED": "BAND3",
                    "NIR": "BAND4",
                    "SWIR1": "BAND5",
                },
                "maskMethod": "Akasha threshold mask v1",
                "excludedMaskClasses": [0, 2, 3],
                "metricsProvisional": True,
                "scale": 0.0001,
                "offset": 0.0,
                "nodata": 0,
                "bbox": [78.19, 12.09, 78.22, 12.12],
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "read_index_windows",
        lambda **_kwargs: WindowRead(
            band_arrays={
                2: np.array([[1000, 1000], [1000, 1000]], dtype="uint16"),
                3: np.array([[3000, 3000], [3000, 3000]], dtype="uint16"),
            },
            # ResourceSat mask: 1=valid, 2=cloud, 3=shadow, 4=water. Keep 1 and 4.
            mask=np.array([[1, 2], [4, 3]], dtype="uint8"),
            geometry_mask=np.array([[True, True], [True, True]]),
            nodata=0,
            height=2,
            width=2,
            intersects=True,
        ),
    )

    body = service.compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="resourcesat-2a-liss3-boa",
        acquisition_date="2026-03-19",
        index_type="NDVI",
    )

    assert body["pixelCounts"]["coveragePixels"] == 4
    assert body["pixelCounts"]["maskedPixels"] == 2
    assert body["pixelCounts"]["validPixels"] == 2
    assert body["statistics"]["validPixelPercent"] == 50.0
    assert body["statistics"]["mean"] == pytest.approx(0.5)
    assert body["metadata"]["nativeExcludedMaskClasses"] == [0, 2, 3]
    assert body["metadata"]["metricsProvisional"] is True


def test_statistics_attaches_sar_support_without_changing_optical_stats(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import service
    from app.raster.raster_reader import WindowRead

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "resourcesat-composite",
                "analyticHref": "s3://akasha-cogs/resourcesat/analytic.tif",
                "maskHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {"RED": "BAND3", "NIR": "BAND4"},
                "maskMethod": "Akasha threshold mask v1",
                "excludedMaskClasses": [0, 2, 3],
                "scale": 0.0001,
                "offset": 0.0,
                "nodata": 0,
                "bbox": [78.19, 12.09, 78.22, 12.12],
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "read_index_windows",
        lambda **_kwargs: WindowRead(
            band_arrays={
                2: np.array([[1000, 1000]], dtype="uint16"),
                3: np.array([[3000, 3000]], dtype="uint16"),
            },
            mask=np.array([[1, 2]], dtype="uint8"),
            geometry_mask=np.array([[True, True]]),
            nodata=0,
            height=1,
            width=2,
            intersects=True,
        ),
    )

    captured = {}

    def fake_sar_support(**kwargs):
        captured.update(kwargs)
        return {
            "available": True,
            "status": "available",
            "sourceId": "eos-04-sar-mrs-l2b",
            "acquisitionDate": "2026-03-20",
            "daysFromOpticalDate": 1,
            "windowDays": 7,
            "cloudGap": True,
            "opticalCloudMaskedPercent": kwargs["optical_cloud_masked_percent"],
            "opticalMaskedPixels": kwargs["optical_masked_pixels"],
            "polarizations": ["HH", "HV"],
            "coveragePercent": 100.0,
            "confidence": "high",
            "reason": "EOS-04 SAR support is available for cloudy/masked optical pixels.",
            "bands": [
                {
                    "name": "HH_dB",
                    "min": -15.0,
                    "max": -10.0,
                    "mean": -12.5,
                    "stddev": 2.5,
                    "validPixelPercent": 100.0,
                }
            ],
            "wetnessSignal": "not_assessed",
            "changeSignal": "not_assessed",
        }

    monkeypatch.setattr(service, "compute_sar_support", fake_sar_support)

    body = service.compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="resourcesat-2a-liss3-boa",
        acquisition_date="2026-03-19",
        index_type="NDVI",
    )

    assert body["statistics"]["mean"] == pytest.approx(0.5)
    assert body["pixelCounts"]["maskedPixels"] == 1
    assert captured["optical_cloud_masked_percent"] == pytest.approx(50.0)
    assert captured["optical_masked_pixels"] == 1
    assert body["sarSupport"]["available"] is True
    assert body["sarSupport"]["sourceId"] == "eos-04-sar-mrs-l2b"
    assert body["sarSupport"]["bands"][0]["name"] == "HH_dB"


def test_sar_support_resolver_reports_nearby_eos04_scene(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import sar_support

    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-03-20",
                "bounds": [78.19, 12.09, 78.22, 12.12],
                "tileAvailable": True,
            }
        ],
    )
    monkeypatch.setattr(
        catalog,
        "resolve_assets",
        lambda source_id, acquisition_date: {
            "backscatterHref": "s3://akasha-cogs/eos/backscatter.tif",
            "bandNames": ["HH_dB", "HV_dB"],
            "nodata": -9999.0,
        },
    )
    monkeypatch.setattr(
        sar_support,
        "_read_sar_statistics",
        lambda **_kwargs: {
            "intersects": True,
            "coveragePercent": 88.0,
            "bands": [
                {
                    "name": "HH_dB",
                    "min": -18.0,
                    "max": -9.0,
                    "mean": -12.0,
                    "stddev": 1.5,
                    "validPixelPercent": 88.0,
                }
            ],
        },
    )

    support = sar_support.compute_sar_support(
        geometry=IN_FOOTPRINT_POLY,
        optical_source_id="resourcesat-2a-liss3-boa",
        optical_acquisition_date="2026-03-19",
        optical_cloud_masked_percent=50.0,
        optical_masked_pixels=10,
        geometry_bounds=[78.19, 12.09, 78.22, 12.12],
        window_days=7,
        cloud_threshold_percent=20,
    )

    assert support["available"] is True
    assert support["acquisitionDate"] == "2026-03-20"
    assert support["daysFromOpticalDate"] == 1
    assert support["polarizations"] == ["HH", "HV"]
    assert support["confidence"] == "high"


def test_sar_support_resolver_rejects_zero_valid_sar_coverage(monkeypatch):
    from app.raster import catalog_resolver as catalog
    from app.raster import sar_support

    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-03-20",
                "bounds": [78.19, 12.09, 78.22, 12.12],
                "tileAvailable": True,
            }
        ],
    )
    monkeypatch.setattr(
        catalog,
        "resolve_assets",
        lambda source_id, acquisition_date: {
            "backscatterHref": "s3://akasha-cogs/eos/backscatter.tif",
            "bandNames": ["HH_dB", "HV_dB"],
            "nodata": -9999.0,
        },
    )
    monkeypatch.setattr(
        sar_support,
        "_read_sar_statistics",
        lambda **_kwargs: {
            "intersects": True,
            "coveragePercent": 0.0,
            "bands": [
                {
                    "name": "HH_dB",
                    "min": None,
                    "max": None,
                    "mean": None,
                    "stddev": None,
                    "validPixelPercent": 0.0,
                }
            ],
        },
    )

    support = sar_support.compute_sar_support(
        geometry=IN_FOOTPRINT_POLY,
        optical_source_id="resourcesat-2a-liss3-boa",
        optical_acquisition_date="2026-03-19",
        optical_cloud_masked_percent=50.0,
        optical_masked_pixels=10,
        geometry_bounds=[78.19, 12.09, 78.22, 12.12],
        window_days=7,
        cloud_threshold_percent=20,
    )

    assert support["available"] is False
    assert support["status"] == "no_valid_pixels"
    assert support["reason"] == (
        "EOS-04 scene overlaps this field but has no valid backscatter pixels."
    )


def test_resourcesat_statistics_uses_mask_only_nodata_policy(monkeypatch):
    from app.raster import service
    from app.raster.raster_reader import WindowRead

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "resourcesat-composite",
                "analyticHref": "s3://akasha-cogs/resourcesat/analytic.tif",
                "maskHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2",
                    "RED": "BAND3",
                    "NIR": "BAND4",
                    "SWIR1": "BAND5",
                },
                "maskMethod": "Akasha threshold mask v1",
                "excludedMaskClasses": [0, 2, 3],
                "nodataPolicy": "mask_only",
                "metricsProvisional": True,
                "scale": 0.0001,
                "offset": 0.0,
                "nodata": 0,
                "bbox": [78.19, 12.09, 78.22, 12.12],
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "read_index_windows",
        lambda **_kwargs: WindowRead(
            band_arrays={
                2: np.array([[0, 5000]], dtype="uint16"),
                3: np.array([[1000, 2000]], dtype="uint16"),
            },
            mask=np.array([[1, 1]], dtype="uint8"),
            geometry_mask=np.array([[True, True]]),
            nodata=0,
            height=1,
            width=2,
            intersects=True,
        ),
    )

    body = service.compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="resourcesat-2a-liss3-boa",
        acquisition_date="2026-03-19",
        index_type="NDVI",
    )

    assert body["pixelCounts"]["nodataPixels"] == 0
    assert body["pixelCounts"]["coveragePixels"] == 2
    assert body["pixelCounts"]["validPixels"] == 2


def test_statistics_multi_scene_date_uses_intersecting_scene_not_first(monkeypatch):
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    from app.raster import catalog_resolver as catalog
    from app.raster import service
    from app.raster.raster_reader import WindowRead

    monkeypatch.setattr(
        catalog,
        "resolve_assets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("statistics must resolve all same-date assets")
        ),
    )
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "scene-a",
                "analyticHref": "s3://secret-bucket/a/analytic.tif",
                "sclHref": "s3://secret-bucket/a/scl.tif",
                "maskHref": "s3://secret-bucket/a/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "bandRoleMapping": SENTINEL2_BAND_ROLE_MAPPING,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "bbox": [77.0, 12.0, 78.0, 13.0],
            },
            {
                "itemId": "scene-b",
                "analyticHref": "s3://secret-bucket/b/analytic.tif",
                "sclHref": "s3://secret-bucket/b/scl.tif",
                "maskHref": "s3://secret-bucket/b/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "bandRoleMapping": SENTINEL2_BAND_ROLE_MAPPING,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "metricsProvisional": True,
                "bbox": [78.0, 12.0, 79.0, 13.0],
            },
        ],
    )
    monkeypatch.setattr(
        catalog,
        "supported_indices",
        lambda source_id="sentinel-2-l2a": ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"],
    )

    read_hrefs = []

    def fake_read_index_windows(*, analytic_href, mask_href, geometry, positions):
        read_hrefs.append(analytic_href)
        return WindowRead(
            band_arrays={
                1: np.full((1, 1), 2000, dtype="uint16"),
                2: np.full((1, 1), 4000, dtype="uint16"),
            },
            mask=np.full((1, 1), 4, dtype="uint8"),
            geometry_mask=np.ones((1, 1), dtype=bool),
            nodata=0,
            height=1,
            width=1,
            intersects=True,
        )

    monkeypatch.setattr(service, "read_index_windows", fake_read_index_windows)

    resp = service.compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="sentinel-2-l2a",
        acquisition_date="2026-01-15",
        index_type="NDVI",
        max_area_ha=50,
        max_vertices=5000,
    )

    assert read_hrefs == ["s3://secret-bucket/b/analytic.tif"]
    assert resp["metadata"]["itemId"] == "scene-b"
    assert resp["metadata"]["metricsProvisional"] is True
    assert resp["statistics"]["mean"] == pytest.approx(0.5)


def test_statistics_multi_scene_overlap_fails_without_leaking_hrefs(monkeypatch):
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    from app.raster import catalog_resolver as catalog
    from app.raster import service
    from app.raster.raster_reader import WindowRead

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "scene-a",
                "analyticHref": "s3://secret-bucket/a/analytic.tif",
                "sclHref": "s3://secret-bucket/a/scl.tif",
                "maskHref": "s3://secret-bucket/a/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "bandRoleMapping": SENTINEL2_BAND_ROLE_MAPPING,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "bbox": [78.0, 12.0, 79.0, 13.0],
            },
            {
                "itemId": "scene-b",
                "analyticHref": "s3://secret-bucket/b/analytic.tif",
                "sclHref": "s3://secret-bucket/b/scl.tif",
                "maskHref": "s3://secret-bucket/b/scl.tif",
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "bandRoleMapping": SENTINEL2_BAND_ROLE_MAPPING,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "bbox": [78.0, 12.0, 79.0, 13.0],
            },
        ],
    )

    def fake_read_index_windows(*, analytic_href, mask_href, geometry, positions):
        return WindowRead(
            band_arrays={
                1: np.full((1, 1), 2000, dtype="uint16"),
                2: np.full((1, 1), 4000, dtype="uint16"),
            },
            mask=np.full((1, 1), 4, dtype="uint8"),
            geometry_mask=np.ones((1, 1), dtype=bool),
            nodata=0,
            height=1,
            width=1,
            intersects=True,
        )

    monkeypatch.setattr(service, "read_index_windows", fake_read_index_windows)

    r = client.post(
        "/api/indices/statistics",
        json={
            "geometry": IN_FOOTPRINT_POLY,
            "sourceId": "sentinel-2-l2a",
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
        },
    )

    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "MULTI_SCENE_STATISTICS_UNAVAILABLE"
    assert body["error"]["details"] == {
        "sceneCount": 2,
        "intersectingSceneCount": 2,
        "supportedSceneCount": 1,
    }
    assert "s3://" not in r.text
    assert "secret-bucket" not in r.text
    assert "analytic.tif" not in r.text


# --------------------------------------------------------------------------
# full rasterio synthetic dual-COG pipeline (skipped if rasterio missing)
# --------------------------------------------------------------------------
def test_synthetic_dual_cog_statistics_end_to_end(tmp_path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")
    from app.raster import catalog_resolver as catalog
    from app.raster.service import compute_statistics
    from pyproj import Transformer  # noqa: I001
    from rasterio.transform import from_origin

    crs = "EPSG:32643"
    res = 10.0
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    proj = [tf.transform(x, y) for x, y in IN_FOOTPRINT_POLY["coordinates"][0]]
    minx = min(p[0] for p in proj) - 100
    maxx = max(p[0] for p in proj) + 100
    miny = min(p[1] for p in proj) - 100
    maxy = max(p[1] for p in proj) + 100
    w = int((maxx - minx) / res)
    h = int((maxy - miny) / res)
    transform = from_origin(minx, maxy, res, res)

    analytic = np.zeros((9, h, w), dtype="uint16")
    analytic[0, :, :] = 2000  # B04 red -> 0.1
    analytic[1, :, :] = 4000  # B08 nir -> 0.3  => NDVI 0.5
    scl = np.full((h, w), 4, dtype="uint8")

    a_path = tmp_path / "analytic.tif"
    s_path = tmp_path / "scl.tif"
    prof = dict(
        driver="GTiff",
        width=w,
        height=h,
        count=9,
        dtype="uint16",
        crs=crs,
        transform=transform,
        nodata=0,
    )
    with rasterio.open(a_path, "w", **prof) as dst:
        dst.write(analytic)
    prof_s = dict(prof, count=1, dtype="uint8")
    with rasterio.open(s_path, "w", **prof_s) as dst:
        dst.write(scl, 1)

    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "synthetic",
                "analyticHref": str(a_path),
                "sclHref": str(s_path),
                "maskHref": str(s_path),
                "bandNames": indices.FROZEN_ANALYTIC_BANDS,
                "bandRoleMapping": SENTINEL2_BAND_ROLE_MAPPING,
                "scale": 0.0001,
                "offset": -0.1,
                "nodata": 0,
                "epsg": 32643,
                "bbox": None,
            }
        ],
    )
    monkeypatch.setattr(
        catalog,
        "supported_indices",
        lambda source_id="sentinel-2-l2a": ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"],
    )

    resp = compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="sentinel-2-l2a",
        acquisition_date="2025-09-14",
        index_type="NDVI",
        max_area_ha=50,
        max_vertices=5000,
    )
    assert resp["statistics"]["mean"] == pytest.approx(0.5, abs=1e-6)
    assert resp["pixelCounts"]["validPixels"] > 0
    assert resp["statistics"]["validPixelPercent"] == pytest.approx(100.0)
    assert resp["metadata"]["bands"] == ["B08", "B04"]
