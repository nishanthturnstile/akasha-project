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

import numpy as np
import pytest
from app.main import app
from app.raster import indices
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
    assert body["maxPolygonAreaHa"] == 50
    assert body["aoi"]["id"] == "bangalore-60km"
    assert body["aoi"]["name"] == "Bangalore 60 km"
    assert body["aoi"]["center"] == [77.5776037099731, 13.076858177177233]
    assert body["aoi"]["bounds"] == [77.023647, 12.537266, 78.131561, 13.61645]
    assert body["aoi"]["geometry"]["type"] == "Polygon"
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


def test_sources_endpoint_contract():
    r = client.get("/api/sources")
    assert r.status_code == 200
    sources = {src["id"]: src for src in r.json()}
    src = sources["sentinel-2-l2a"]
    assert "NDVI" in src["supportedIndices"]
    assert src["kind"] == "optical"
    assert src["bandRoleMapping"]["NIR"] == "B08"
    assert src["maskAsset"] == "scl"
    assert src["displayModes"] == ["RGB"]
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
    assert rs["displayModes"] == ["FCC"]
    assert rs["availableMaskOptions"] == ["clouds", "cloudShadows"]
    assert rs["metricsProvisional"] is True
    assert sources["resourcesat-2a-awifs-boa"]["availabilityStatus"] == "gated"
    assert sources["resourcesat-2a-liss4-mx70-l2"]["availabilityStatus"] == "gated"
    assert sources["eos-06-ocm-lac-ndvi-8day-360m"]["availabilityStatus"] == "gated"
    assert sources["eos-04-sar-mrs-l2b"]["kind"] == "sar"
    assert sources["nisar-ssar-beta-gcov"]["availabilityStatus"] == "gated"
    assert sources["cartosat-3-gated"]["gatedReason"]
    assert sources["irs-1c-liss3-archive"]["analysisLevel"] == "archive"
    s1 = sources["sentinel-1-grd"]
    assert s1["label"] == "Sentinel-1 GRD"
    assert s1["provider"] == "Copernicus"
    assert s1["kind"] == "sar"
    assert s1["displayModes"] == ["VV_GRAYSCALE"]
    assert s1["defaultDisplayMode"] == "VV_GRAYSCALE"
    assert s1["dateMetricsKind"] == "radar"
    assert s1["supportedIndices"] == []


def test_dates_endpoint_returns_real_scene():
    r = client.get("/api/sources/sentinel-2-l2a/dates")
    assert r.status_code == 200
    dates = r.json()
    assert any(d["acquisitionDate"] == "2025-09-14" for d in dates)


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
    assert body["sourceId"] == "sentinel-2-l2a"
    assert body["acquisitionDate"] == "2025-09-14"
    assert body["displayMode"] == "RGB"
    assert body["tileUrlTemplate"] == ("/api/tiles/sentinel-2-l2a/2025-09-14/rgb/{z}/{x}/{y}.png")


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
) -> dict:
    props = {
        "datetime": f"{acquisition_date}T00:00:00Z",
        "akasha:acquisition_date": acquisition_date,
        "akasha:usable_pixel_percent": usable,
        "akasha:cloud_masked_percent": 100.0 - usable,
        "akasha:coverage_percent": coverage,
        "akasha:is_latest_usable": True,
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

    r = client.get("/api/layers/default")
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


def test_layers_default_supports_resourcesat_fcc():
    r = client.get("/api/layers/default?sourceId=resourcesat-2a-liss3-boa")
    assert r.status_code == 200
    body = r.json()
    assert body["sourceId"] == "resourcesat-2a-liss3-boa"
    assert body["displayMode"] == "FCC"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png"
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

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/sentinel-2-l2a/2026-01-15/rgb/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fa%2Fanalytic.tif&bidx=1&bidx=8&bidx=9&"
        "rescale=0%2C3000&rescale=0%2C3000&rescale=0%2C3000"
    )


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

    def fake_fetch_tile(url):
        captured["url"] = url
        return b"png-bytes", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch_tile)

    r = client.get("/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/3/4/5.png")
    assert r.status_code == 200
    assert r.content == b"png-bytes"
    assert captured["url"] == (
        "http://titiler.internal:8000/cog/tiles/WebMercatorQuad/3/4/5.png?"
        "url=s3%3A%2F%2Fakasha-cogs%2Fresourcesat%2Fanalytic.tif&bidx=3&bidx=2&bidx=1&"
        "rescale=0%2C3000&rescale=0%2C3000&rescale=0%2C3000"
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
    assert body["metadata"]["metricsProvisional"] is True


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
    from pyproj import Transformer  # noqa: I001
    from rasterio.transform import from_origin

    from app.raster import catalog_resolver as catalog
    from app.raster.service import compute_statistics

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
