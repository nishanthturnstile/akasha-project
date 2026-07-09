"""Selected-field native analytics route tests."""
from __future__ import annotations

import json
import struct
import zlib
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from app.config import settings
from app.main import app
from app.raster import tiles
from app.routers import analytics_router as field_analytics
from app.schemas.analytics import FieldStatisticsRequest
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def native_settings(monkeypatch):
    monkeypatch.setattr(settings, "default_source_id", "resourcesat-2a-liss3-boa")


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
        },
        "areaHa": 5.0,
    }
    plot.update(overrides)
    return plot


def _stats_response(
    index_type: str = "NDVI",
    acquisition_date: str = "2026-01-15",
) -> dict[str, Any]:
    return {
        "indexType": index_type,
        "sourceId": "resourcesat-2a-liss3-boa",
        "acquisitionDate": acquisition_date,
        "statistics": {
            "min": 0.1,
            "max": 0.8,
            "mean": 0.55,
            "stddev": 0.12,
            "validPixelPercent": 82.5,
            "cloudMaskedPercent": 10.0,
            "coveragePercent": 92.5,
        },
        "pixelCounts": {
            "totalPixels": 100,
            "nodataPixels": 7,
            "coveragePixels": 93,
            "maskedPixels": 10,
            "validPixels": 83,
        },
        "metadata": {
            "formula": "(NIR - RED) / (NIR + RED)",
            "bands": ["BAND4", "BAND3"],
            "itemId": f"item-{acquisition_date}",
            "warnings": [],
        },
    }


def _decode_rgba_png(png: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    cursor = 8
    width = height = 0
    idat = bytearray()
    while cursor < len(png):
        length = struct.unpack("!I", png[cursor : cursor + 4])[0]
        cursor += 4
        kind = png[cursor : cursor + 4]
        cursor += 4
        data = png[cursor : cursor + length]
        cursor += length + 4
        if kind == b"IHDR":
            width, height = struct.unpack("!II", data[:8])
        elif kind == b"IDAT":
            idat.extend(data)
        elif kind == b"IEND":
            break

    raw = zlib.decompress(bytes(idat))
    pixels: list[tuple[int, int, int, int]] = []
    stride = width * 4
    offset = 0
    for _row in range(height):
        assert raw[offset] == 0
        offset += 1
        row = raw[offset : offset + stride]
        offset += stride
        for col in range(0, len(row), 4):
            pixels.append(tuple(row[col : col + 4]))
    return width, height, pixels


def test_field_statistics_uses_field_repository_for_field_ids(monkeypatch):
    field = _plot(id="field-1", name="Migrated Field")
    calls: list[tuple[str, str]] = []

    def fake_get_field(field_id: str, user_id: str) -> dict[str, Any]:
        calls.append((field_id, user_id))
        return field

    monkeypatch.setattr(field_analytics.fields_repo, "get_field", fake_get_field)
    monkeypatch.setattr(field_analytics, "compute_statistics", lambda **kwargs: _stats_response())

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": "resourcesat-2a-liss3-boa", "indexType": "NDVI"},
    )

    assert r.status_code == 200
    assert calls[0][0] == "field-1"
    assert r.json()["plotId"] == "field-1"


def test_field_statistics_loads_geometry_server_side(monkeypatch):
    plot = _plot()
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: plot)
    calls: list[dict[str, Any]] = []

    def fake_compute_statistics(**kwargs):
        calls.append(kwargs)
        return _stats_response(
            index_type=kwargs["index_type"],
            acquisition_date=kwargs["acquisition_date"],
        )

    monkeypatch.setattr(field_analytics, "compute_statistics", fake_compute_statistics)
    r = client.post(
        "/api/fields/plot-1/indices/statistics",
        json={
            "sourceId": "resourcesat-2a-liss3-boa",
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
            "cloudMask": {"clouds": True, "cloudShadows": False, "cirrus": True},
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert calls[0]["geometry"] == plot["geometry"]
    assert calls[0]["source_id"] == "resourcesat-2a-liss3-boa"
    assert calls[0]["excluded_mask_classes"] == (0, 2)
    assert body["plotId"] == "plot-1"
    assert body["provider"] == "native"
    assert body["scope"] == "field"
    assert body["statistics"]["mean"] == pytest.approx(0.55)
    assert body["metadata"]["cloudMaskMapping"]["nativeExcludedMaskClasses"] == [0, 2]
    assert body["metadata"]["cloudMaskMapping"]["warnings"]


def test_resourcesat_statistics_stays_native_until_bridge_fully_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_api_url", "http://ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", False)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "request_field_index",
        lambda *_args, **_kw: pytest.fail("pipeline should not be used while bridge incomplete"),
    )
    monkeypatch.setattr(field_analytics, "compute_statistics", lambda **kwargs: _stats_response())

    r = client.post(
        "/api/fields/plot-1/indices/statistics",
        json={
            "sourceId": "resourcesat-2a-liss3-boa",
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
        },
    )

    assert r.status_code == 200
    assert r.json()["provider"] == "native"


def test_field_statistics_missing_field(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: None)
    r = client.post("/api/fields/missing/indices/statistics", json={"indexType": "NDVI"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FIELD_NOT_FOUND"
    assert "Traceback" not in r.text


def test_trend_rejects_invalid_date_range(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend?startDate=2026-06-30&endDate=2026-01-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_native_trend_normalizes_points(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "list_dates",
        lambda _: [
            {"acquisitionDate": "2026-01-01"},
            {"acquisitionDate": "2026-02-01"},
        ],
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kwargs: _stats_response(
            index_type=kwargs["index_type"],
            acquisition_date=kwargs["acquisition_date"],
        ),
    )

    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "native"
    assert body["scope"] == "native_fallback"
    assert body["points"][0]["acquisitionDate"] == "2026-01-01"
    assert body["points"][0]["mean"] == pytest.approx(0.55)
    assert body["points"][0]["validPixelPercent"] == pytest.approx(82.5)
    assert body["metadata"]["formula"] == "(NIR - RED) / (NIR + RED)"
    assert body["metadata"]["spectralRoles"] == ["NIR", "RED"]


def test_native_trend_rejects_unsupported_index(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?indexType=BAD&startDate=2026-01-01&endDate=2026-03-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_INDEX"


def test_trend_without_dates_uses_catalog_defaults_without_internal_leaks(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "list_dates", lambda _: [])
    r = client.get("/api/fields/plot-1/analytics/trend?indexType=NDVI")
    assert r.status_code == 200
    assert r.json()["provider"] == "native"
    for leak in ["s3://", "minio", "postgres", "Traceback"]:
        assert leak not in r.text


def test_native_trend_reports_cloud_percent_per_scene(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog, "list_dates", lambda _: [{"acquisitionDate": "2026-01-01"}]
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kwargs: _stats_response(
            index_type=kwargs["index_type"], acquisition_date=kwargs["acquisition_date"]
        ),
    )

    r = client.get(
        "/api/fields/plot-1/analytics/trend?startDate=2026-01-01&endDate=2026-03-01"
    )

    assert r.status_code == 200
    # cloudPercent mirrors the in-field cloud-masked percentage (EOS parity).
    assert r.json()["points"][0]["cloudPercent"] == pytest.approx(10.0)


def test_native_trend_filters_scenes_over_max_cloud_cover(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "list_dates",
        lambda _: [
            {"acquisitionDate": "2026-01-01"},  # clear scene -> kept
            {"acquisitionDate": "2026-02-01"},  # cloudy scene -> dropped
        ],
    )

    def fake_compute(**kwargs):
        resp = _stats_response(
            index_type=kwargs["index_type"], acquisition_date=kwargs["acquisition_date"]
        )
        if kwargs["acquisition_date"] == "2026-02-01":
            resp["statistics"]["cloudMaskedPercent"] = 80.0
        return resp

    monkeypatch.setattr(field_analytics, "compute_statistics", fake_compute)

    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?startDate=2026-01-01&endDate=2026-03-01&maxCloudCoverInAoi=50"
    )

    assert r.status_code == 200
    body = r.json()
    dates = [p["acquisitionDate"] for p in body["points"]]
    assert dates == ["2026-01-01"]
    assert body["metadata"]["maxCloudCoverInAoi"] == pytest.approx(50.0)
    assert body["metadata"]["cloudFilteredSceneCount"] == 1


def test_native_trend_rejects_out_of_range_cloud_cover(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    r = client.get("/api/fields/plot-1/analytics/trend?maxCloudCoverInAoi=150")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_CLOUD_COVER"


def test_field_index_overlay_renders_clipped_png(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "supported_indices", lambda *_: ["NDVI"])
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: [
            {
                "analyticHref": "s3://akasha-cogs/x/analytic.tif",
                "maskHref": "s3://akasha-cogs/x/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5",
                },
                "scale": 0.0001,
                "offset": 0.0,
                "excludedMaskClasses": [0, 2, 3],
                "nodataPolicy": "mask_only",
            }
        ],
    )
    monkeypatch.setattr(
        field_analytics,
        "read_index_windows",
        lambda **_: SimpleNamespace(
            band_arrays={
                2: np.array([[2000, 5000], [1000, 0]], dtype=np.uint16),
                3: np.array([[6000, 5000], [7000, 0]], dtype=np.uint16),
            },
            mask=np.array([[1, 2], [1, 0]], dtype=np.uint8),
            geometry_mask=np.array([[True, True], [True, True]], dtype=bool),
            nodata=0,
            intersects=True,
        ),
    )

    r = client.get(
        "/api/fields/plot-1/overlay/ndvi.png"
        "?sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-03-19"
    )

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    width, height, pixels = _decode_rgba_png(r.content)
    assert (width, height) == (2, 2)
    assert pixels[1] == (208, 213, 221, 255)
    assert pixels[3] == (208, 213, 221, 255)
    assert pixels[0][3] == 255 and pixels[0][:3] != (208, 213, 221)
    assert pixels[2][3] == 255 and pixels[2][1] >= pixels[2][0]


def test_field_index_overlay_returns_true_window_corners_and_reference_stretch(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "supported_indices", lambda *_: ["NDVI"])
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: [
            {
                "analyticHref": "s3://akasha-cogs/x/analytic.tif",
                "maskHref": "s3://akasha-cogs/x/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5",
                },
                "scale": 0.0001,
                "offset": 0.0,
                "excludedMaskClasses": [0, 2, 3],
                "nodataPolicy": "mask_only",
            }
        ],
    )
    true_corners = [[77.001, 13.002], [77.103, 13.001], [77.104, 12.9], [77.0, 12.901]]
    monkeypatch.setattr(
        field_analytics,
        "read_index_windows",
        lambda **_: SimpleNamespace(
            band_arrays={
                2: np.array([[2000, 2000], [2000, 2000]], dtype=np.uint16),
                3: np.array([[6000, 6000], [6000, 6000]], dtype=np.uint16),
            },
            mask=np.array([[1, 1], [1, 1]], dtype=np.uint8),
            geometry_mask=np.array([[True, True], [True, True]], dtype=bool),
            nodata=0,
            intersects=True,
            footprint_corners=true_corners,
        ),
    )

    r = client.get(
        "/api/fields/plot-1/overlay/ndvi.png"
        "?sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-03-19"
    )

    assert r.status_code == 200
    assert r.headers["x-akasha-overlay-corners"] == json.dumps(true_corners, separators=(",", ":"))
    assert r.headers["x-akasha-overlay-stretch"] == "-1.0,1.0"


def test_ndvi_overlay_uses_reference_heatmap_colors():
    png, _content_type = tiles.render_field_index_overlay_png(
        index_type="NDVI",
        index_values=np.array([[-0.5, 0.08, 0.22, 0.37, 0.52, 0.67, 0.82, 0.95]]),
        valid_mask=np.ones((1, 8), dtype=bool),
        masked_mask=np.zeros((1, 8), dtype=bool),
    )

    width, height, pixels = _decode_rgba_png(png)
    assert (width, height) == (8, 1)
    assert [pixel[:3] for pixel in pixels] == [
        (19, 24, 125),   # water / non-vegetation
        (128, 70, 26),   # bare soil
        (213, 0, 35),    # poor vegetation
        (255, 83, 13),   # low-medium growth
        (250, 201, 9),   # moderate growth
        (111, 202, 7),   # healthy crop
        (22, 153, 43),   # very healthy crop
        (0, 88, 37),     # dense / excellent vegetation
    ]


# ---------------------------------------------------------------------------
# Cross-stack NDVI palette contract
# Canonical source of truth: tiles._NDVI_REFERENCE_CLASSES
# Frontend mirror: apps/frontend/src/lib/indexRamp.ts  NDVI_INDEX_RAMP.classes
# If you change colors here you MUST update the frontend hex values and vice-versa.
# ---------------------------------------------------------------------------

def test_ndvi_reference_classes_canonical_rgb_values():
    """Directly verify _NDVI_REFERENCE_CLASSES RGB tuples without rendering.

    This is the authoritative cross-stack contract test.  The frontend mirrors
    these values as CSS hex strings in NDVI_INDEX_RAMP (indexRamp.ts).

    Canonical mapping (RGB → hex):
        (19,  24,  125) → #13187d   water / non-vegetation
        (128, 70,  26)  → #80461a   bare soil
        (213, 0,   35)  → #d50023   stressed / poor vegetation
        (255, 83,  13)  → #ff530d   sparse crop / low-medium growth
        (250, 201, 9)   → #fac909   sub-canopy / moderate growth
        (111, 202, 7)   → #6fca07   moderate / healthy crop
        (22,  153, 43)  → #16992b   healthy / very healthy crop
        (0,   88,  37)  → #005825   peak vigour / dense vegetation
    """
    expected_rgb: list[tuple[int, int, int]] = [
        (19, 24, 125),   # water / non-vegetation — hex #13187d
        (128, 70, 26),   # bare soil              — hex #80461a
        (213, 0, 35),    # stressed               — hex #d50023
        (255, 83, 13),   # sparse crop            — hex #ff530d
        (250, 201, 9),   # sub-canopy             — hex #fac909
        (111, 202, 7),   # moderate               — hex #6fca07
        (22, 153, 43),   # healthy                — hex #16992b
        (0, 88, 37),     # peak vigour            — hex #005825
    ]
    assert len(tiles._NDVI_REFERENCE_CLASSES) == 8, "Expected exactly 8 NDVI classes"
    actual_rgb = [cls[2] for cls in tiles._NDVI_REFERENCE_CLASSES]
    assert actual_rgb == expected_rgb


def test_ndvi_reference_classes_boundaries():
    """Verify NDVI class boundaries match the documented [low, high) intervals."""
    expected_bounds: list[tuple[float, float]] = [
        (-1.0, 0.0),
        (0.0, 0.15),
        (0.15, 0.30),
        (0.30, 0.45),
        (0.45, 0.60),
        (0.60, 0.75),
        (0.75, 0.90),
        (0.90, 1.0),
    ]
    actual_bounds = [(cls[0], cls[1]) for cls in tiles._NDVI_REFERENCE_CLASSES]
    assert actual_bounds == pytest.approx(expected_bounds)



def test_reproject_index_overlay_web_mercator_is_north_up_supersampled_and_clipped():
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    # 10x10 ResourceSat-like window: UTM 43N, 24 m pixels.
    src_transform = from_origin(500000, 1450000, 24, 24)
    src_crs = rasterio.crs.CRS.from_epsg(32643)
    index_values = np.full((10, 10), 0.5, dtype="float64")
    data_valid = np.ones((10, 10), dtype=bool)
    data_masked = np.zeros((10, 10), dtype=bool)

    left, top = 500000.0, 1450000.0
    right, bottom = left + 240.0, top - 240.0
    west, south, east, north = transform_bounds(src_crs, "EPSG:4326", left, bottom, right, top)
    # Inner polygon covering the central half of the window (in lng/lat).
    px0, px1 = west + (east - west) * 0.25, west + (east - west) * 0.75
    py0, py1 = south + (north - south) * 0.25, south + (north - south) * 0.75
    geometry = {
        "type": "Polygon",
        "coordinates": [[[px0, py0], [px1, py0], [px1, py1], [px0, py1], [px0, py0]]],
    }

    rgba, corners = tiles.reproject_index_overlay_web_mercator(
        index_type="NDVI",
        index_values=index_values,
        data_valid=data_valid,
        data_masked=data_masked,
        src_transform=src_transform,
        src_crs=src_crs,
        geometry=geometry,
    )

    out_h, out_w = rgba.shape[:2]
    # Supersampled finer than the native 10x10 window.
    assert out_h > 10 and out_w > 10

    # North-up Web Mercator rectangle (TL, TR, BR, BL) once expressed in lng/lat.
    (tl, tr, br, bl) = corners
    assert tl[1] == pytest.approx(tr[1])
    assert bl[1] == pytest.approx(br[1])
    assert tl[0] == pytest.approx(bl[0])
    assert tr[0] == pytest.approx(br[0])

    # Inside the polygon → opaque colorized; outside → fully transparent.
    assert rgba[out_h // 2, out_w // 2, 3] == 255
    assert rgba[0, 0, 3] == 0
    assert rgba[out_h - 1, out_w - 1, 3] == 0


def test_field_index_point_returns_precise_value_for_hover(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "supported_indices", lambda *_: ["NDVI"])
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **kw: SimpleNamespace(
            source_id=kw["primary_source_id"],
            resolution_meters=24,
            enhanced=False,
            basis_date=None,
            provenance_note=None,
        ),
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: [
            {
                "analyticHref": "s3://akasha-cogs/x/analytic.tif",
                "maskHref": "s3://akasha-cogs/x/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5",
                },
                "scale": 0.0001,
                "offset": 0.0,
                "excludedMaskClasses": [0, 2, 3],
                "nodataPolicy": "mask_only",
            }
        ],
    )
    monkeypatch.setattr(
        field_analytics,
        "read_index_windows",
        lambda **_: SimpleNamespace(
            band_arrays={
                2: np.array([[2000]], dtype=np.uint16),
                3: np.array([[6000]], dtype=np.uint16),
            },
            mask=np.array([[1]], dtype=np.uint8),
            geometry_mask=np.array([[True]], dtype=bool),
            nodata=0,
            intersects=True,
            footprint_corners=[[77, 12], [77.1, 12], [77.1, 11.9], [77, 11.9]],
        ),
    )

    r = client.get(
        "/api/fields/plot-1/indices/point"
        "?sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-03-19"
        "&indexType=NDVI&lng=77.05&lat=12.05"
    )

    assert r.status_code == 200
    assert r.json() == {
        "plotId": "plot-1",
        "sourceId": "resourcesat-2a-liss3-boa",
        "acquisitionDate": "2026-03-19",
        "indexType": "NDVI",
        "lng": 77.05,
        "lat": 12.05,
        "value": 0.5,
        "masked": False,
        "maskClass": 1,
        "resolvedSourceId": "resourcesat-2a-liss3-boa",
        "resolutionMeters": 24,
        "enhanced": False,
        "basisDate": None,
        "provenanceNote": None,
    }


def test_field_index_overlay_rejects_unsupported_index(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "supported_indices", lambda *_: ["NDVI", "NDMI"])
    r = client.get(
        "/api/fields/plot-1/overlay/ndre.png?sourceId=resourcesat-2a-liss3-boa"
        "&acquisitionDate=2026-03-19"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_INDEX"


def test_field_statistics_request_uses_configured_defaults():
    payload = FieldStatisticsRequest()

    assert payload.source_id == settings.default_source_id
    assert payload.index_type == "NDVI"
