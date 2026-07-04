"""Product source/date bridge tests for the Sentinel-2 ingestion pipeline."""

from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.ingestion_client import ReadinessResponse
from app.main import app
from app.routers import product_router
from fastapi.testclient import TestClient

client = TestClient(app)

SENTINEL = "sentinel-2-l2a"


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


class FakeIngestionClient:
    def __init__(self, readiness: ReadinessResponse) -> None:
        self._readiness = readiness

    def readiness(self, *, source_id=None, aoi_id=None, request_id=None):
        return self._readiness


@pytest.fixture
def enable_pipeline_bridge(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setattr(settings, "ingestion_pipeline_tile_layer_enabled", False)
    monkeypatch.delenv("AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES", raising=False)


def test_sources_include_sentinel_only_when_pipeline_readiness_is_available(
    monkeypatch, enable_pipeline_bridge
):
    monkeypatch.setattr(
        product_router,
        "IngestionClient",
        lambda: FakeIngestionClient(_readiness()),
    )

    response = client.get("/api/sources")

    assert response.status_code == 200
    sources = {source["id"]: source for source in response.json()}
    assert SENTINEL in sources
    assert sources[SENTINEL]["supportedIndices"] == ["NDVI"]
    assert sources[SENTINEL]["displayModes"] == ["NDVI"]
    assert sources[SENTINEL]["mapDisplayModes"] == ["NDVI"]
    assert sources[SENTINEL]["availabilityStatus"] == "active"
    assert sources[SENTINEL]["pipelineBacked"] is True


def test_sources_replace_legacy_sentinel_payload_with_ndvi_only_pipeline_source(
    monkeypatch, enable_pipeline_bridge
):
    monkeypatch.setenv("AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES", "true")
    monkeypatch.setattr(
        product_router,
        "IngestionClient",
        lambda: FakeIngestionClient(_readiness()),
    )

    response = client.get("/api/sources")

    assert response.status_code == 200
    sources = {source["id"]: source for source in response.json()}
    assert sources[SENTINEL]["supportedIndices"] == ["NDVI"]
    assert sources[SENTINEL]["displayModes"] == ["NDVI"]


def test_sources_do_not_include_pipeline_sentinel_when_readiness_is_stale(
    monkeypatch, enable_pipeline_bridge
):
    monkeypatch.setattr(
        product_router,
        "IngestionClient",
        lambda: FakeIngestionClient(_readiness("STALE")),
    )

    response = client.get("/api/sources")

    assert response.status_code == 200
    assert SENTINEL not in {source["id"] for source in response.json()}


def test_sentinel_dates_come_from_readiness_without_upstream_urls(
    monkeypatch, enable_pipeline_bridge
):
    monkeypatch.setattr(
        product_router,
        "IngestionClient",
        lambda: FakeIngestionClient(_readiness()),
    )

    response = client.get(f"/api/sources/{SENTINEL}/dates")

    assert response.status_code == 200
    dates = response.json()
    assert [entry["acquisitionDate"] for entry in dates] == ["2026-01-13", "2026-01-06"]
    assert dates[0]["isLatestUsable"] is True
    assert dates[0]["tileAvailable"] is True
    assert dates[0]["unavailableReason"] is None
    assert dates[0]["sensorBadge"] == "S2"
    serialized = str(dates)
    assert "ingestion.internal" not in serialized
    assert "sig=" not in serialized
