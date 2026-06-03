"""Phase 8 VRA vegetation zoning route tests."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import pytest
from app import field_zoning
from app.config import settings
from app.main import app
from app.providers.models import (
    ProviderAsyncRequest,
    SceneMetadata,
    ZoningMapStatus,
    ZoningZone,
)
from app.raster.errors import AkashaError
from fastapi.testclient import TestClient

client = TestClient(app)

FAKE_KEY = "fake-eos-key-super-secret"
FAKE_BASE_URL = "https://api-connect.eos.com"
PUBLIC_MAP_ID = "11111111-1111-4111-8111-111111111111"
RAW_ZMAP_ID = "raw-provider-zmap-secret"
RAW_FIELD_ID = "raw-provider-field-secret"
RAW_REQUEST_ID = "raw-provider-request-secret"


@pytest.fixture(autouse=True)
def provider_settings(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", "")
    monkeypatch.setattr(settings, "eos_base_url", FAKE_BASE_URL)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {"type": "Polygon", "coordinates": []},
        "areaHa": 5.0,
        "externalProvider": "eos",
        "externalFieldId": RAW_FIELD_ID,
        "providerSyncStatus": "synced",
    }
    plot.update(overrides)
    return plot


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": PUBLIC_MAP_ID,
        "plotId": "plot-1",
        "provider": "eos",
        "externalZmapId": RAW_ZMAP_ID,
        "providerRequestId": RAW_REQUEST_ID,
        "status": "processing",
        "mapType": "vegetation",
        "indexType": "NDVI",
        "imageDate": "2026-06-01",
        "zoneCount": 3,
        "minZoneAreaHa": 0.25,
        "metadata": {"unsafe": RAW_ZMAP_ID},
        "createdAt": "2026-06-03T00:00:00Z",
        "updatedAt": "2026-06-03T00:00:00Z",
    }
    row.update(overrides)
    return row


def _zone_geometry() -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]],
    }


def _enable_eos(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)


def _assert_no_provider_leaks(text: str) -> None:
    for leaked in [FAKE_KEY, FAKE_BASE_URL, RAW_FIELD_ID, RAW_ZMAP_ID, RAW_REQUEST_ID]:
        assert leaked not in text


def test_create_vegetation_zoning_map_returns_public_id(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())
    calls: dict[str, Any] = {}

    class FakeSceneProvider:
        def search_scenes(self, external_field_id, date_start, date_end, **kwargs):
            assert external_field_id == RAW_FIELD_ID
            assert date_start == date(2026, 6, 1)
            assert date_end == date(2026, 6, 1)
            return ProviderAsyncRequest(request_id="scene-request", status="done")

        def get_scene_search_result(self, *_args):
            return [
                SceneMetadata(
                    scene_id="scene-1",
                    view_id="provider-dataset-secret",
                    acquisition_date=date(2026, 6, 1),
                    cloud_percent=5,
                )
            ]

    class FakeZoningProvider:
        def create_vegetation_map(self, external_field_id, **kwargs):
            calls.update({"external_field_id": external_field_id, **kwargs})
            return ProviderAsyncRequest(
                request_id=RAW_REQUEST_ID,
                status="pending",
                external_field_id=external_field_id,
                external_zmap_id=RAW_ZMAP_ID,
            )

    def fake_create_zoning_map(**kwargs):
        assert kwargs["external_zmap_id"] == RAW_ZMAP_ID
        assert kwargs["provider_request_id"] == RAW_REQUEST_ID
        assert kwargs["min_zone_area_ha"] == 0.25
        return _row()

    monkeypatch.setattr(field_zoning, "EosSceneProvider", lambda: FakeSceneProvider())
    monkeypatch.setattr(field_zoning, "EosZoningProvider", lambda: FakeZoningProvider())
    monkeypatch.setattr(field_zoning.zoning_repo, "create_zoning_map", fake_create_zoning_map)

    r = client.post(
        "/api/fields/plot-1/zoning/vegetation",
        json={
            "indexType": "NDVI",
            "imageDate": "2026-06-01",
            "zoneCount": 3,
            "minZoneArea": 0.25,
            "asyncProcessing": True,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["plotId"] == "plot-1"
    assert body["mapId"] == PUBLIC_MAP_ID
    assert body["status"] == "processing"
    assert body["metadata"]["minZoneAreaHa"] == 0.25
    assert calls["dataset_id"] == "provider-dataset-secret"
    assert calls["min_zone_area"] == 0.25
    assert calls["image_date"] == date(2026, 6, 1)
    _assert_no_provider_leaks(r.text)


def test_create_zoning_rejects_browser_callback(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())

    r = client.post(
        "/api/fields/plot-1/zoning/vegetation",
        json={
            "indexType": "NDVI",
            "imageDate": "2026-06-01",
            "zoneCount": 3,
            "minZoneArea": 0.25,
            "callbackUrl": "https://attacker.example/callback",
        },
    )

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CALLBACK_UNSUPPORTED"
    _assert_no_provider_leaks(r.text)


def test_zoning_requires_synced_field(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot(externalFieldId=None))

    r = client.get("/api/fields/plot-1/zoning/maps")

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FIELD_PROVIDER_NOT_SYNCED"
    _assert_no_provider_leaks(r.text)


def test_zoning_respects_provider_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())

    r = client.get("/api/fields/plot-1/zoning/maps")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    _assert_no_provider_leaks(r.text)


def test_get_zoning_map_normalizes_zones_and_hides_provider_ids(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())
    monkeypatch.setattr(field_zoning.zoning_repo, "get_zoning_map", lambda *_: _row())
    updates: list[dict[str, Any]] = []

    class FakeZoningProvider:
        def get_zoning_map(self, external_field_id, external_zmap_id):
            assert external_field_id == RAW_FIELD_ID
            assert external_zmap_id == RAW_ZMAP_ID
            return ZoningMapStatus(
                external_field_id=external_field_id,
                external_zmap_id=external_zmap_id,
                status="ready",
                map_type="vegetation",
                index="NDVI",
                zone_count=1,
                zones=[
                    ZoningZone(
                        zone_id="zone-1",
                        area_ha=1.2,
                        area_percent=24.0,
                        fertilizer=0.72,
                        geometry=_zone_geometry(),
                    )
                ],
            )

    def fake_update(*_args, **kwargs):
        updates.append(kwargs)
        return _row(status="ready", zoneCount=1)

    monkeypatch.setattr(field_zoning, "EosZoningProvider", lambda: FakeZoningProvider())
    monkeypatch.setattr(field_zoning.zoning_repo, "update_zoning_map", fake_update)

    r = client.get(f"/api/fields/plot-1/zoning/maps/{PUBLIC_MAP_ID}")

    assert r.status_code == 200
    body = r.json()
    assert body["mapId"] == PUBLIC_MAP_ID
    assert body["status"] == "ready"
    assert body["zones"][0]["zoneId"] == "zone-1"
    assert body["zones"][0]["clusterValue"] == 0.72
    assert updates[0]["status"] == "ready"
    _assert_no_provider_leaks(r.text)


def test_zoning_exports_geojson_and_shp_without_provider_ids(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())
    monkeypatch.setattr(field_zoning.zoning_repo, "get_zoning_map", lambda *_: _row(status="ready"))
    monkeypatch.setattr(
        field_zoning.zoning_repo,
        "update_zoning_map",
        lambda *_args, **_kwargs: _row(status="ready"),
    )

    class FakeZoningProvider:
        def get_zoning_map(self, *_args):
            return ZoningMapStatus(
                external_field_id=RAW_FIELD_ID,
                external_zmap_id=RAW_ZMAP_ID,
                status="ready",
                map_type="vegetation",
                index="NDVI",
                zone_count=1,
                zones=[
                    ZoningZone(
                        zone_id="zone-1",
                        area_ha=1.2,
                        area_percent=24.0,
                        fertilizer=0.72,
                        geometry=_zone_geometry(),
                    )
                ],
            )

    monkeypatch.setattr(field_zoning, "EosZoningProvider", lambda: FakeZoningProvider())

    geojson = client.get(f"/api/fields/plot-1/zoning/maps/{PUBLIC_MAP_ID}/export.geojson")
    assert geojson.status_code == 200
    assert geojson.headers["content-type"].startswith("application/geo+json")
    assert geojson.json()["features"][0]["properties"]["mapId"] == PUBLIC_MAP_ID
    _assert_no_provider_leaks(geojson.text)

    shp = client.get(f"/api/fields/plot-1/zoning/maps/{PUBLIC_MAP_ID}/export.shp")
    assert shp.status_code == 200
    assert shp.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(shp.content)) as zf:
        assert {"zones.shp", "zones.shx", "zones.dbf", "zones.prj"}.issubset(zf.namelist())
    _assert_no_provider_leaks(shp.text)


def test_zoning_rate_limit_error_is_sanitized(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda _: _plot())

    class FakeZoningProvider:
        def list_zoning_maps(self, *_args):
            raise AkashaError(
                "PROVIDER_RATE_LIMITED",
                "EOS provider rate limit was reached.",
                429,
                {"provider": "eos", "retryAfterSeconds": 12, "url": FAKE_BASE_URL},
            )

    monkeypatch.setattr(field_zoning, "EosZoningProvider", lambda: FakeZoningProvider())

    r = client.get("/api/fields/plot-1/zoning/maps")

    assert r.status_code == 429
    assert r.json()["error"]["code"] == "PROVIDER_RATE_LIMITED"
    assert r.json()["error"]["details"]["retryAfterSeconds"] == 12
    _assert_no_provider_leaks(r.text)
