"""Phase 4 field-aware Monitoring route tests."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from app import field_monitoring
from app.config import settings
from app.main import app
from app.providers.models import FieldMirrorResult, ProviderAsyncRequest, SceneMetadata, TileBytes
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
            "coordinates": [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]],
        },
        "areaHa": 5.0,
        "externalProvider": None,
        "externalFieldId": None,
        "providerSyncStatus": None,
        "providerSyncedAt": None,
    }
    plot.update(overrides)
    return plot


def test_sync_field_provider_mirrors_unsynced_plot(monkeypatch):
    monkeypatch.setattr(field_monitoring.plots_repo, "get_plot", lambda plot_id: _plot(id=plot_id))

    class FakeFieldProvider:
        def mirror_field(self, plot):
            return FieldMirrorResult(
                plot_id=plot["id"],
                external_field_id="eos-field-1",
                sync_status="synced",
                synced_at=datetime(2026, 6, 3, tzinfo=UTC),
                provider_area_ha=5.1,
            )

    monkeypatch.setattr(field_monitoring, "EosFieldProvider", lambda: FakeFieldProvider())
    r = client.post("/api/fields/plot-1/providers/eos/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["plotId"] == "plot-1"
    assert body["syncStatus"] == "synced"
    assert body["field"]["externalFieldId"] == "eos-field-1"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_auto_field_scenes_return_native_fallback_for_unsynced_field(monkeypatch):
    monkeypatch.setattr(field_monitoring.plots_repo, "get_plot", lambda _: _plot())
    r = client.get("/api/fields/plot-1/scenes?provider=auto")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "global_fallback"
    assert body["provider"] == "native"
    assert body["defaultDisplayMode"] == "RGB"
    assert body["scenes"]
    assert body["scenes"][0]["layers"][0]["tileUrlTemplate"].startswith("/api/tiles/")
    assert "api-connect" not in r.text


def test_explicit_eos_scenes_require_synced_field(monkeypatch):
    monkeypatch.setattr(field_monitoring.plots_repo, "get_plot", lambda _: _plot())
    r = client.get("/api/fields/plot-1/scenes?provider=eos")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FIELD_PROVIDER_NOT_SYNCED"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_eos_field_scenes_normalize_and_dedupe(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)
    monkeypatch.setattr(
        field_monitoring.plots_repo,
        "get_plot",
        lambda _: _plot(
            externalProvider="eos",
            externalFieldId="eos-field-1",
            providerSyncStatus="synced",
        ),
    )

    class FakeSceneProvider:
        def search_scenes(self, *args, **kwargs):
            return ProviderAsyncRequest(
                request_id="request-1",
                status="done",
                external_field_id="eos-field-1",
            )

        def get_scene_search_result(self, *args, **kwargs):
            return [
                SceneMetadata(
                    scene_id="scene-low",
                    view_id="S2/scene-low",
                    acquisition_date=date(2026, 6, 1),
                    cloud_percent=50,
                    usable_percent=50,
                ),
                SceneMetadata(
                    scene_id="scene-best",
                    view_id="S2/scene-best",
                    acquisition_date=date(2026, 6, 1),
                    cloud_percent=5,
                    usable_percent=95,
                    coverage_percent=100,
                    bounds=[77.0, 12.0, 77.1, 12.1],
                ),
            ]

    monkeypatch.setattr(field_monitoring, "EosSceneProvider", lambda: FakeSceneProvider())
    r = client.get("/api/fields/plot-1/scenes?provider=eos&startDate=2026-01-01&endDate=2026-06-30")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "field"
    assert body["displayModes"] == ["RGB", "NDVI", "NDRE", "NDMI", "MSAVI", "RECI", "FALSE_COLOR"]
    assert len(body["scenes"]) == 1
    assert body["scenes"][0]["usablePixelPercent"] == 95
    assert body["scenes"][0]["layers"][0]["tileUrlTemplate"].startswith("/api/tiles/fields/")
    assert "/api/providers/eos" not in r.text
    assert FAKE_BASE_URL not in r.text


def test_field_tile_proxy_returns_image_bytes_without_provider_url(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)
    monkeypatch.setattr(
        field_monitoring.plots_repo,
        "get_plot",
        lambda _: _plot(externalProvider="eos"),
    )
    scene = SceneMetadata(
        scene_id="scene-best",
        view_id="S2/scene-best",
        acquisition_date=date(2026, 6, 1),
    )
    token = field_monitoring._scene_token(scene)

    class FakeTileProvider:
        def render_tile(self, scene, **kwargs):
            assert kwargs["display_mode"] == "NDVI"
            assert kwargs["cloud_mask"].cloud_shadows is False
            return TileBytes(content=b"\x89PNG\r\n\x1a\nfake", content_type="image/png")

    monkeypatch.setattr(field_monitoring, "EosTileProvider", lambda: FakeTileProvider())
    r = client.get(
        f"/api/tiles/fields/plot-1/{token}/NDVI/1/2/3.png?clouds=true&cloudShadows=false&cirrus=true"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")
    assert FAKE_BASE_URL.encode() not in r.content


def test_field_tile_proxy_respects_eos_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    monkeypatch.setattr(
        field_monitoring.plots_repo,
        "get_plot",
        lambda _: _plot(externalProvider="eos"),
    )
    scene = SceneMetadata(
        scene_id="scene-best",
        view_id="S2/scene-best",
        acquisition_date=date(2026, 6, 1),
    )
    token = field_monitoring._scene_token(scene)
    r = client.get(f"/api/tiles/fields/plot-1/{token}/RGB/1/2/3.png")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_unknown_field_tile_mode_is_sanitized(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)
    monkeypatch.setattr(
        field_monitoring.plots_repo,
        "get_plot",
        lambda _: _plot(externalProvider="eos"),
    )
    scene = SceneMetadata(
        scene_id="scene-best",
        view_id="S2/scene-best",
        acquisition_date=date(2026, 6, 1),
    )
    token = field_monitoring._scene_token(scene)
    r = client.get(f"/api/tiles/fields/plot-1/{token}/BAD/1/2/3.png")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_DISPLAY_MODE"
    assert "Traceback" not in r.text
    assert FAKE_BASE_URL not in r.text
