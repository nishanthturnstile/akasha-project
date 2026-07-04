"""Route tests for the feature-gated Sentinel-2 NDVI pipeline overlay branch.

The field overlay endpoint (``GET /api/fields/{id}/overlay/{index}.png``) must,
for the pipeline source, return a field-clipped image sourced from ingestion via
an app-domain response (no full-scene tiles, no leaked ingestion host/URL/query).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.ingestion_client import (
    FieldIndexAvailableResponse,
    FieldIndexUnavailableResponse,
    ReadinessResponse,
)
from app.main import app
from app.routers import analytics_router as field_analytics
from fastapi.testclient import TestClient

client = TestClient(app)

SENTINEL = "sentinel-2-l2a"
_PNG = b"\x89PNG\r\n\x1a\n" + b"clipped-overlay-bytes" * 8
_CORNERS = "[[77.6,12.98],[77.61,12.98],[77.61,12.97],[77.6,12.97]]"


@pytest.fixture(autouse=True)
def _pipeline_settings(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setattr(settings, "max_polygon_area_ha", 100000)
    monkeypatch.setattr(settings, "max_polygon_vertices", 10000)


def _plot() -> dict[str, Any]:
    return {
        "id": "field-1",
        "name": "Field 1",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]],
        },
        "areaHa": 3.0,
    }


def _readiness(status: str = "AVAILABLE", **overrides: Any) -> ReadinessResponse:
    data: dict[str, Any] = {
        "status": status,
        "sourceId": SENTINEL,
        "aoiId": "bangalore_60km_geodesic_aoi",
        "latestProcessedSceneDate": "2026-01-13",
        "staleAfter": "2026-01-21T02:30:00Z",
        "availableDates": ["2026-01-13", "2026-01-06"],
        "indexCoverage": {"NDVI": {"available": True, "dateCount": 2, "coveragePercent": 100.0}},
    }
    data.update(overrides)
    return ReadinessResponse.model_validate(data)


def _available_response(overlay_url: str | None = None) -> FieldIndexAvailableResponse:
    return FieldIndexAvailableResponse.model_validate(
        {
            "status": "AVAILABLE",
            "queryId": "q_secret",
            "fieldId": "ingestion_field",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "selectedSceneDate": "2026-01-13",
            "source": SENTINEL,
            "providerRoute": "earthsearch:sentinel-2-l2a",
            "resolution": {"processingMeters": 10},
            "layerId": "layer_secret",
            "tileUrl": "https://ingestion.internal/tiles/x?sig=SIGNED",
            "statsUrl": "https://ingestion.internal/stats?sig=SIGNED",
            "overlayUrl": overlay_url,
            "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
            "statistics": {
                "min": 0.12,
                "max": 0.86,
                "mean": 0.54,
                "stdDev": 0.08,
                "usablePixelPercentage": 92.5,
                "cloudPercentage": 4.2,
            },
            "quality": {"status": "GOOD", "reason": "OK", "warnings": []},
            "versions": {"analytics": "phase2-sentinel2-v1"},
        }
    )


class FakeClient:
    def __init__(
        self,
        *,
        readiness_result: Any = None,
        field_index_result: Any = None,
        overlay_result: Any = None,
    ) -> None:
        self._readiness_result = readiness_result
        self._field_index_result = field_index_result
        self._overlay_result = overlay_result
        self.fetch_overlay_calls: list[str] = []

    def readiness(self, *, source_id=None, aoi_id=None, request_id=None):
        if isinstance(self._readiness_result, Exception):
            raise self._readiness_result
        return self._readiness_result

    def field_index(self, request, *, request_id=None):
        if isinstance(self._field_index_result, Exception):
            raise self._field_index_result
        return self._field_index_result

    def fetch_overlay(self, url, *, request_id=None):
        self.fetch_overlay_calls.append(url)
        if isinstance(self._overlay_result, Exception):
            raise self._overlay_result
        return self._overlay_result


def _install_client(monkeypatch, fake: FakeClient) -> FakeClient:
    monkeypatch.setattr(field_analytics, "IngestionClient", lambda *a, **k: fake)
    return fake


def _get(source_id: str = SENTINEL, index_type: str = "NDVI", date: str = "2026-01-15"):
    return client.get(
        f"/api/fields/field-1/overlay/{index_type}.png",
        params={"sourceId": source_id, "acquisitionDate": date},
    )


def test_pipeline_overlay_returns_clipped_png_from_ingestion(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    overlay_url = (
        "https://ingestion.internal/api/v1/analytics/field-index/q_secret/overlay.png?sig=SIGNED"
    )
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(),
            field_index_result=_available_response(overlay_url),
            overlay_result=(_PNG, "image/png", _CORNERS),
        ),
    )

    r = _get()

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _PNG
    assert r.headers["X-Akasha-Overlay-Corners"] == _CORNERS
    # The ingestion overlay URL is fetched server-side; nothing leaks to the browser.
    assert len(fake.fetch_overlay_calls) == 1
    assert fake.fetch_overlay_calls[0] == overlay_url
    assert "ingestion.internal" not in r.text
    assert "q_secret" not in r.text
    assert "SIGNED" not in r.text


def test_pipeline_overlay_missing_url_returns_error(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(),
            field_index_result=_available_response(None),
        ),
    )

    r = _get()

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PIPELINE_OVERLAY_UNAVAILABLE"


def test_pipeline_overlay_unavailable_readiness_does_not_call_field_index(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(
                status="UNAVAILABLE",
                indexCoverage={
                    "NDVI": {"available": False, "dateCount": 0, "coveragePercent": 0.0}
                },
                availableDates=[],
            ),
            field_index_result=_available_response("https://ingestion.internal/x?sig=S"),
        ),
    )

    r = _get()

    assert r.status_code >= 400
    assert fake.fetch_overlay_calls == []
