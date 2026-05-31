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


# --------------------------------------------------------------------------
# index registry + band mapping
# --------------------------------------------------------------------------
def test_index_registry_has_four_supported_indices():
    assert set(indices.INDEX_REGISTRY) == {"NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"}
    assert indices.DEFAULT_INDEX == "NDVI"


def test_ndvi_band_assignment_is_nir_minus_red():
    ndvi = indices.get_index("NDVI")
    assert ndvi.band_a == "B08" and ndvi.band_b == "B04"
    assert ndvi.formula == "(B08 - B04) / (B08 + B04)"


def test_band_name_to_position_uses_frozen_order():
    pos = indices.band_name_to_position(indices.FROZEN_ANALYTIC_BANDS)
    assert pos["B04"] == 1  # red
    assert pos["B08"] == 2  # nir
    assert pos["B03"] == 8  # green
    assert pos["B02"] == 9  # blue


def test_rgb_positions_are_1_8_9_not_1_2_3():
    assert indices.rgb_band_positions(indices.FROZEN_ANALYTIC_BANDS) == [1, 8, 9]


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
    scl[0, 0] = 9       # cloud high -> excluded
    red[0, 1] = 0       # analytic nodata
    geom[0, 2] = False  # outside polygon

    s = compute_index_statistics(
        index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=scl, geometry_mask=geom,
        scale=0.0001, offset=-0.1, nodata=0,
    ).as_dict()

    assert s["totalPixels"] == 8
    assert s["nodataPixels"] == 1
    assert s["coveragePixels"] == 7
    assert s["sclExcludedPixels"] == 1
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
        index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=scl, geometry_mask=geom,
        scale=0.0001, offset=-0.1, nodata=0,
    ).mean
    no_off = compute_index_statistics(
        index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=scl, geometry_mask=geom,
        scale=0.0001, offset=0.0, nodata=0,
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
        index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=scl, geometry_mask=geom,
        scale=0.0001, offset=-0.1, nodata=0,
    ).as_dict()
    # veg (4) + water (6) kept = 2 valid ; classes 8 and 3 excluded = 2.
    assert s["validPixels"] == 2
    assert s["sclExcludedPixels"] == 2


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
    assert body["supportedIndices"] == ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"]
    assert body["defaultIndex"] == "NDVI"
    assert body["maxPolygonAreaHa"] == 50
    assert body["aoi"]["id"] == "bangalore"


def test_sources_endpoint_contract():
    r = client.get("/api/sources")
    assert r.status_code == 200
    src = r.json()[0]
    assert src["id"] == "sentinel-2-l2a"
    assert "NDVI" in src["supportedIndices"]


def test_dates_endpoint_returns_real_scene():
    r = client.get("/api/sources/sentinel-2-l2a/dates")
    assert r.status_code == 200
    dates = r.json()
    assert any(d["acquisitionDate"] == "2025-09-14" for d in dates)


def test_layers_default_tile_template_is_same_origin_api_route():
    r = client.get("/api/layers/default")
    assert r.status_code == 200
    body = r.json()
    assert body["sourceId"] == "sentinel-2-l2a"
    assert body["acquisitionDate"] == "2025-09-14"
    assert body["tileUrlTemplate"] == (
        "/api/tiles/sentinel-2-l2a/2025-09-14/rgb/{z}/{x}/{y}.png"
    )


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


# --------------------------------------------------------------------------
# full rasterio synthetic dual-COG pipeline (skipped if rasterio missing)
# --------------------------------------------------------------------------
def test_synthetic_dual_cog_statistics_end_to_end(tmp_path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")
    from pyproj import Transformer
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
    prof = dict(driver="GTiff", width=w, height=h, count=9, dtype="uint16",
                crs=crs, transform=transform, nodata=0)
    with rasterio.open(a_path, "w", **prof) as dst:
        dst.write(analytic)
    prof_s = dict(prof, count=1, dtype="uint8")
    with rasterio.open(s_path, "w", **prof_s) as dst:
        dst.write(scl, 1)

    monkeypatch.setattr(
        catalog, "resolve_assets",
        lambda source_id, acquisition_date: {
            "itemId": "synthetic", "analyticHref": str(a_path), "sclHref": str(s_path),
            "bandNames": indices.FROZEN_ANALYTIC_BANDS, "scale": 0.0001, "offset": -0.1,
            "nodata": 0, "epsg": 32643, "bbox": None,
        },
    )
    monkeypatch.setattr(
        catalog, "supported_indices",
        lambda source_id="sentinel-2-l2a": ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"],
    )

    resp = compute_statistics(
        geometry=IN_FOOTPRINT_POLY, source_id="sentinel-2-l2a",
        acquisition_date="2025-09-14", index_type="NDVI",
        max_area_ha=50, max_vertices=5000,
    )
    assert resp["statistics"]["mean"] == pytest.approx(0.5, abs=1e-6)
    assert resp["pixelCounts"]["validPixels"] > 0
    assert resp["statistics"]["validPixelPercent"] == pytest.approx(100.0)
    assert resp["metadata"]["bands"] == ["B08", "B04"]
