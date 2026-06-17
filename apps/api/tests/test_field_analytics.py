"""Selected-field native analytics route tests."""
from __future__ import annotations

import struct
import zlib
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from app.config import settings
from app.main import app
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
