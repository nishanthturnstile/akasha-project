from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_config_uses_aoi_config_path(monkeypatch, tmp_path):
    aoi_path = tmp_path / "custom-aoi.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {
                    "id": "custom-aoi",
                    "name": "Custom AOI",
                    "center": [77.1, 12.9],
                    "zoom": 8,
                    "radiusMeters": 1234,
                    "compositeGridCrs": "EPSG:32643",
                },
                "bbox": [77.0, 12.8, 77.2, 13.0],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[77.0, 12.8], [77.2, 12.8], [77.2, 13.0], [77.0, 13.0], [77.0, 12.8]]
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "aoi_config_path", str(aoi_path), raising=False)

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body["aoi"]["id"] == "custom-aoi"
    assert body["aoi"]["bounds"] == [77.0, 12.8, 77.2, 13.0]
    assert body["aoi"]["bbox"] == [77.0, 12.8, 77.2, 13.0]
    assert body["aoi"]["geometry"]["type"] == "Polygon"
    assert body["aoi"]["radiusMeters"] == 1234
    assert body["aoi"]["compositeGridCrs"] == "EPSG:32643"


def test_config_reports_missing_aoi_file(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.geojson"
    monkeypatch.setattr(settings, "aoi_config_path", str(missing_path), raising=False)

    response = client.get("/api/config")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "AOI_CONFIG_NOT_FOUND"


def test_config_uses_packaged_aoi_fallback_for_container_default(monkeypatch):
    monkeypatch.setattr(
        settings,
        "aoi_config_path",
        "/app/data/seed/bangalore-60km-aoi.geojson",
        raising=False,
    )

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["aoi"]["id"] == "bangalore-60km"


def test_config_reports_malformed_aoi_file(monkeypatch, tmp_path):
    aoi_path = tmp_path / "bad-aoi.geojson"
    aoi_path.write_text(
        json.dumps({"type": "Feature", "properties": {"id": "bad"}, "bbox": [0, 1]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "aoi_config_path", str(aoi_path), raising=False)

    response = client.get("/api/config")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "AOI_CONFIG_INVALID"
    assert "reason" in body["error"]["details"]


def test_resourcesat_seed_contract_files_are_discoverable():
    repo_root = Path(__file__).resolve().parents[3]
    stac_dir = repo_root / "data" / "seed" / "stac"

    collection = stac_dir / "resourcesat-2a-liss3-boa-collection.json"
    item = stac_dir / "resourcesat-2a-liss3-boa-sample-item.json"

    assert collection.is_file()
    assert item.is_file()
    assert json.loads(collection.read_text(encoding="utf-8"))["id"] == "resourcesat-2a-liss3-boa"
    assert json.loads(item.read_text(encoding="utf-8"))["collection"] == "resourcesat-2a-liss3-boa"
