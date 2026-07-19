from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.main import app
from app.routers import analytics_router, product_router
from fastapi.testclient import TestClient

EOS04_SOURCE_ID = "eos-04-sar-mrs-l2b"
NISAR_SOURCE_ID = "nisar-ssar-beta-gcov"
client = TestClient(app)


def _field() -> dict[str, Any]:
    return {
        "id": "field-1",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[[77.0, 12.0], [77.01, 12.0], [77.01, 12.01], [77.0, 12.0]]]
            ],
        },
    }


@pytest.fixture(autouse=True)
def nisar_settings(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_api_url", "http://ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore")
    monkeypatch.setattr(settings, "ingestion_nisar_cutover_enabled", True)
    monkeypatch.setattr(settings, "nisar_product_enabled", True)
    monkeypatch.setattr(settings, "nisar_field_support_enabled", True)
    monkeypatch.setattr(settings, "eos04_field_support_enabled", True)
    monkeypatch.setattr(settings, "eos04_temporal_change_enabled", False)
    monkeypatch.setattr(settings, "eos04_temporal_shadow_enabled", False)


def test_nisar_source_uses_backscatter_and_natural_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "get_natural_source_dates",
        lambda *_a, **_kw: {
            "sourceId": NISAR_SOURCE_ID,
            "aoiId": "bangalore",
            "dates": [
                {
                    "acquisitionDate": "2026-07-12",
                    "datetime": "2026-07-12T05:30:00Z",
                    "tileAvailable": True,
                    "sceneCount": 1,
                    "bounds": [77.0, 12.0, 78.0, 13.0],
                    "polarizations": ["HH", "HV"],
                }
            ],
        },
    )

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    nisar = next(item for item in sources.json() if item["id"] == NISAR_SOURCE_ID)
    assert nisar["displayModes"] == ["BACKSCATTER"]
    assert nisar["defaultDisplayMode"] == "BACKSCATTER"
    assert nisar["supportedIndices"] == []
    assert nisar["tileRouteMode"] == "natural-pipeline"

    dates = client.get(f"/api/sources/{NISAR_SOURCE_ID}/dates")
    assert dates.status_code == 200
    assert dates.json()[0]["polarizations"] == ["HH", "HV"]
    assert dates.json()[0]["sensor"] == "NISAR S-SAR"
    assert dates.json()[0]["usablePixelPercent"] is None

    layer = client.get("/api/layers/default", params={"sourceId": NISAR_SOURCE_ID})
    assert layer.status_code == 200
    assert "/BACKSCATTER/" in layer.json()["tileUrlTemplate"]


def test_nisar_remains_hidden_when_either_release_gate_is_false(monkeypatch) -> None:
    monkeypatch.setattr(settings, "nisar_product_enabled", False)
    assert NISAR_SOURCE_ID not in {item["id"] for item in client.get("/api/sources").json()}

    monkeypatch.setattr(settings, "nisar_product_enabled", True)
    monkeypatch.setattr(settings, "ingestion_nisar_cutover_enabled", False)
    assert NISAR_SOURCE_ID not in {item["id"] for item in client.get("/api/sources").json()}


@pytest.mark.parametrize(
    ("eos_offset", "eos_coverage", "nisar_offset", "nisar_coverage", "expected"),
    [
        (2, 100.0, 1, 96.0, NISAR_SOURCE_ID),
        (1, 96.0, 1, 99.0, NISAR_SOURCE_ID),
        (1, 99.0, 1, 99.0, EOS04_SOURCE_ID),
        (1, 99.0, 0, 94.9, EOS04_SOURCE_ID),
    ],
)
def test_radar_selection_policy_and_overlay_source_pinning(
    monkeypatch,
    eos_offset: int,
    eos_coverage: float,
    nisar_offset: int,
    nisar_coverage: float,
    expected: str,
) -> None:
    monkeypatch.setattr(analytics_router.fields_repo, "get_field", lambda *_a: _field())
    monkeypatch.setattr(analytics_router, "_field_dates_response", lambda **_kw: [])
    monkeypatch.setattr(analytics_router, "_uses_pipeline", lambda *_a: True)
    monkeypatch.setattr(analytics_router, "_pipeline_dates", lambda *_a, **_kw: [])

    def field_sar(*_args, **kwargs):
        source_id = kwargs["source_id"]
        offset, coverage = (
            (eos_offset, eos_coverage)
            if source_id == EOS04_SOURCE_ID
            else (nisar_offset, nisar_coverage)
        )
        return {
            "status": "AVAILABLE",
            "sourceId": source_id,
            "requestedDate": "2026-07-19",
            "acquisitionDate": "2026-07-18",
            "daysFromTarget": offset,
            "coveragePercent": coverage,
            "quality": {"qualified": True, "confidence": "high", "warnings": []},
            "displayedPolarization": "HH",
            "overlayUrl": "http://ingestion.internal/private?sig=secret",
            "queryId": "private-query",
        }

    monkeypatch.setattr(analytics_router, "request_field_sar", field_sar)
    response = client.get(
        "/api/fields/field-1/monitoring/evidence",
        params={
            "sourceId": "sentinel-2-l2a",
            "indexType": "NDVI",
            "targetDate": "2026-07-19",
            "includeRadar": True,
        },
    )

    assert response.status_code == 200
    radar = response.json()["radar"]
    assert radar["sourceId"] == expected
    assert radar["selection"]["policyVersion"] == "radar-support-selection-v1"
    assert f"sourceId={expected}" in radar["overlayUrl"]
    assert "private-query" not in response.text
    assert "ingestion.internal" not in response.text


def test_nisar_overlay_proxy_forwards_explicit_source(monkeypatch) -> None:
    monkeypatch.setattr(analytics_router.fields_repo, "get_field", lambda *_a: _field())
    seen: dict[str, Any] = {}

    def field_sar(*_args, **kwargs):
        seen.update(kwargs)
        return {
            "status": "AVAILABLE",
            "sourceId": NISAR_SOURCE_ID,
            "overlayUrl": "http://ingestion.internal/private?sig=secret",
        }

    monkeypatch.setattr(analytics_router, "request_field_sar", field_sar)
    monkeypatch.setattr(
        analytics_router,
        "fetch_signed_ingestion_binary",
        lambda *_a: (b"png", "image/png", {}),
    )

    response = client.get(
        "/api/fields/field-1/sar/overlay.png",
        params={"targetDate": "2026-07-19", "sourceId": NISAR_SOURCE_ID},
    )

    assert response.status_code == 200
    assert seen["source_id"] == NISAR_SOURCE_ID
    assert response.headers["X-Akasha-Resolved-Source"] == NISAR_SOURCE_ID
