from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.main import app
from app.routers import analytics_router, product_router
from fastapi.testclient import TestClient

EOS04_SOURCE_ID = "eos-04-sar-mrs-l2b"
client = TestClient(app)


def _dates_response() -> dict[str, Any]:
    return {
        "sourceId": EOS04_SOURCE_ID,
        "aoiId": "bangalore",
        "dates": [
            {
                "acquisitionDate": "2026-07-11",
                "datetime": "2026-07-11T05:30:00Z",
                "tileAvailable": True,
                "sceneCount": 1,
                "bounds": [77.0, 12.0, 78.0, 13.0],
                "polarizations": ["VV", "VH"],
                "unavailableReason": None,
            }
        ],
    }


@pytest.fixture(autouse=True)
def eos04_pipeline(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_api_url", "http://ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore")
    monkeypatch.setattr(settings, "eos04_product_enabled", True)
    monkeypatch.setattr(settings, "ingestion_eos04_cutover_enabled", True)
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", False)
    monkeypatch.setattr(settings, "ingestion_resourcesat_cutover_enabled", False)
    monkeypatch.setattr(
        product_router,
        "get_natural_source_dates",
        lambda *_a, **_kw: _dates_response(),
    )


def test_eos04_source_dates_and_default_layer_use_natural_pipeline() -> None:
    sources = client.get("/api/sources")
    assert sources.status_code == 200
    eos04 = next(item for item in sources.json() if item["id"] == EOS04_SOURCE_ID)
    assert eos04["kind"] == "sar"
    assert eos04["availabilityStatus"] == "active"
    assert eos04["supportedIndices"] == []
    assert eos04["displayModes"] == ["VV_GRAYSCALE"]
    assert eos04["tileRouteMode"] == "natural-pipeline"

    dates = client.get(f"/api/sources/{EOS04_SOURCE_ID}/dates")
    assert dates.status_code == 200
    assert dates.json() == [
        {
            "acquisitionDate": "2026-07-11",
            "datetime": "2026-07-11T05:30:00Z",
            "usablePixelPercent": None,
            "cloudMaskedPercent": None,
            "coveragePercent": None,
            "isLatestUsable": True,
            "sceneCount": 1,
            "bounds": [77.0, 12.0, 78.0, 13.0],
            "polarizations": ["VV", "VH"],
            "tileAvailable": True,
            "unavailableReason": None,
            "metricsProvisional": False,
            "sensor": "EOS-04 SAR",
            "provenanceLabel": "EOS-04 · radar backscatter",
        }
    ]

    layer = client.get("/api/layers/default", params={"sourceId": EOS04_SOURCE_ID})
    assert layer.status_code == 200
    assert layer.json()["tileUrlTemplate"] == (
        f"/api/tiles/{EOS04_SOURCE_ID}/2026-07-11/VV_GRAYSCALE/{{z}}/{{x}}/{{y}}.png"
    )
    assert layer.json()["usablePixelPercent"] is None
    assert layer.json()["cloudMaskedPercent"] is None


def test_eos04_tile_is_proxied_without_exposing_ingestion_url(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "fetch_natural_source_tile",
        lambda *_a, **_kw: (b"png-bytes", "image/png"),
    )

    response = client.get(
        f"/api/tiles/{EOS04_SOURCE_ID}/2026-07-11/VV_GRAYSCALE/8/182/105.png"
    )

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"] == "image/png"
    assert b"ingestion.internal" not in response.content


def test_saved_field_timeline_uses_eos04_natural_dates(monkeypatch) -> None:
    monkeypatch.setattr(
        analytics_router.fields_repo,
        "get_field",
        lambda *_a, **_kw: {"id": "field-1", "geometry": {"type": "Polygon", "coordinates": []}},
    )

    response = client.get(
        "/api/fields/field-1/dates",
        params={"sourceId": EOS04_SOURCE_ID, "indexType": "NDVI"},
    )

    assert response.status_code == 200
    assert response.json()[0]["acquisitionDate"] == "2026-07-11"
    assert response.json()[0]["usablePixelPercent"] is None


def test_eos04_remains_hidden_until_both_activation_gates_are_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eos04_product_enabled", False)

    sources = client.get("/api/sources")

    assert sources.status_code == 200
    assert EOS04_SOURCE_ID not in {source["id"] for source in sources.json()}
