"""Phase 5 selected-field analytics route tests."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app import field_analytics
from app.config import settings
from app.main import app
from app.providers.models import AnalyticsTrendPoint, ProviderAsyncRequest
from fastapi.testclient import TestClient

client = TestClient(app)

FAKE_KEY = "fake-eos-key-super-secret"
FAKE_BASE_URL = "https://api-connect.eos.com"


@pytest.fixture(autouse=True)
def provider_settings(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", "")
    monkeypatch.setattr(settings, "eos_base_url", FAKE_BASE_URL)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    monkeypatch.setattr(settings, "default_source_id", "sentinel-2-l2a")


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
        },
        "areaHa": 5.0,
        "externalProvider": None,
        "externalFieldId": None,
        "providerSyncStatus": None,
        "providerSyncedAt": None,
    }
    plot.update(overrides)
    return plot


def _stats_response(index_type: str = "NDVI", acquisition_date: str = "2026-01-15") -> dict[str, Any]:
    return {
        "indexType": index_type,
        "sourceId": "sentinel-2-l2a",
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
            "sclExcludedPixels": 10,
            "validPixels": 83,
        },
        "metadata": {
            "formula": "(B08 - B04) / (B08 + B04)",
            "bands": ["B08", "B04"],
            "itemId": f"item-{acquisition_date}",
            "warnings": [],
        },
    }


def test_field_statistics_loads_geometry_server_side(monkeypatch):
    plot = _plot()
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda plot_id: plot)
    calls: list[dict[str, Any]] = []

    def fake_compute_statistics(**kwargs):
        calls.append(kwargs)
        return _stats_response(index_type=kwargs["index_type"], acquisition_date=kwargs["acquisition_date"])

    monkeypatch.setattr(field_analytics, "compute_statistics", fake_compute_statistics)
    r = client.post(
        "/api/fields/plot-1/indices/statistics",
        json={
            "sourceId": "sentinel-2-l2a",
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
            "cloudMask": {"clouds": True, "cloudShadows": False, "cirrus": True},
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert calls[0]["geometry"] == plot["geometry"]
    assert 3 not in calls[0]["excluded_scl_classes"]
    assert body["plotId"] == "plot-1"
    assert body["provider"] == "native"
    assert body["scope"] == "field"
    assert body["statistics"]["mean"] == pytest.approx(0.55)
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_field_statistics_missing_field(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: None)
    r = client.post("/api/fields/missing/indices/statistics", json={"indexType": "NDVI"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FIELD_NOT_FOUND"
    assert "Traceback" not in r.text


def test_trend_rejects_invalid_date_range(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend?startDate=2026-06-30&endDate=2026-01-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_native_trend_fallback_normalizes_points(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: _plot())
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
        "?provider=native&indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "native"
    assert body["scope"] == "native_fallback"
    assert body["points"][0]["acquisitionDate"] == "2026-01-01"
    assert body["points"][0]["mean"] == pytest.approx(0.55)
    assert body["points"][0]["validPixelPercent"] == pytest.approx(82.5)
    assert body["metadata"]["formula"] == "(B08 - B04) / (B08 + B04)"


def test_native_trend_rejects_unsupported_index(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?provider=native&indexType=BAD&startDate=2026-01-01&endDate=2026-03-01"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_INDEX"


def test_explicit_eos_trend_requires_synced_field(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: _plot())
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?provider=eos&indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FIELD_PROVIDER_NOT_SYNCED"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_eos_trend_normalizes_provider_points(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)
    monkeypatch.setattr(
        field_analytics.plots_repo,
        "get_plot",
        lambda _: _plot(externalProvider="eos", externalFieldId="eos-field-1"),
    )

    class FakeAnalyticsProvider:
        def create_trend_request(self, *args, **kwargs):
            assert kwargs["index"] == "NDVI"
            assert kwargs["cloud_mask"].clouds is True
            return ProviderAsyncRequest(request_id="trend-1", status="created")

        def get_trend_result(self, *args, **kwargs):
            return [
                AnalyticsTrendPoint(
                    scene_id="scene-1",
                    view_id="S2/scene-1",
                    acquisition_date=date(2026, 2, 1),
                    index="NDVI",
                    mean=0.61,
                    minimum=0.2,
                    maximum=0.9,
                    stddev=0.13,
                    cloud_percent=4.0,
                )
            ]

    monkeypatch.setattr(field_analytics, "EosAnalyticsProvider", lambda: FakeAnalyticsProvider())
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?provider=eos&indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "eos"
    assert body["scope"] == "field"
    assert body["points"][0]["mean"] == pytest.approx(0.61)
    assert body["points"][0]["min"] == pytest.approx(0.2)
    assert body["points"][0]["cloudPercent"] == pytest.approx(4.0)
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_auto_trend_falls_back_without_provider_leaks(monkeypatch):
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda _: _plot())
    monkeypatch.setattr(field_analytics.catalog, "list_dates", lambda _: [])
    r = client.get(
        "/api/fields/plot-1/analytics/trend"
        "?provider=auto&indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )
    assert r.status_code == 200
    assert r.json()["provider"] == "native"
    for leak in [FAKE_KEY, FAKE_BASE_URL, "s3://", "minio", "postgres", "Traceback"]:
        assert leak not in r.text
