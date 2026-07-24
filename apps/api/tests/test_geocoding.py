from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.routers import geocoding_router


def test_geocoding_normalizes_provider_results(monkeypatch):
    geocoding_router._CACHE.clear()

    async def fake_search(query: str):
        assert query == "Bengaluru India"
        return [
            {
                "display_name": "Bengaluru, Karnataka, India",
                "lon": "77.5946",
                "lat": "12.9716",
                "boundingbox": ["12.83", "13.14", "77.46", "77.78"],
            }
        ]

    monkeypatch.setattr(geocoding_router, "_search_provider", fake_search)
    response = TestClient(app).get("/api/geocoding/search", params={"q": " Bengaluru   India "})

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "label": "Bengaluru, Karnataka, India",
                "center": [77.5946, 12.9716],
                "bbox": [77.46, 12.83, 77.78, 13.14],
                "type": "place",
            }
        ]
    }


def test_geocoding_rejects_unbounded_queries():
    response = TestClient(app).get("/api/geocoding/search", params={"q": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
