"""Selected-field native analytics route tests."""
from __future__ import annotations

from typing import Any

import pytest
from app import field_analytics
from app.config import settings
from app.main import app
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


def test_field_statistics_loads_geometry_server_side(monkeypatch):
    plot = _plot()
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: plot)
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
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: None)
    r = client.post("/api/fields/missing/indices/statistics", json={"indexType": "NDVI"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FIELD_NOT_FOUND"
    assert "Traceback" not in r.text


def test_trend_rejects_invalid_date_range(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend?startDate=2026-06-30&endDate=2026-01-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_native_trend_normalizes_points(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: _plot())
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
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?indexType=BAD&startDate=2026-01-01&endDate=2026-03-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_INDEX"


def test_trend_without_dates_uses_catalog_defaults_without_internal_leaks(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: _plot())
    monkeypatch.setattr(field_analytics.catalog, "list_dates", lambda _: [])
    r = client.get("/api/fields/plot-1/analytics/trend?indexType=NDVI")
    assert r.status_code == 200
    assert r.json()["provider"] == "native"
    for leak in ["s3://", "minio", "postgres", "Traceback"]:
        assert leak not in r.text
