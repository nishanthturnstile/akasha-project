"""Phase 2 EOS provider-adapter foundation tests.

No live EOS key, network, or PostGIS is required. HTTP behavior is exercised
through httpx.MockTransport and persistence side effects are monkeypatched.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from app import plots_repo
from app.config import settings
from app.main import app
from app.providers.eos.client import EosClient
from app.providers.eos.field_provider import EosFieldProvider
from app.providers.eos.scene_provider import EosSceneProvider
from app.providers.eos.tile_provider import EosTileProvider
from app.providers.models import SceneMetadata
from app.raster.errors import AkashaError
from fastapi.testclient import TestClient

client = TestClient(app)

FAKE_KEY = "fake-eos-key-super-secret"
FAKE_BASE_URL = "https://api-connect.eos.com"


@pytest.fixture(autouse=True)
def eos_settings(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", "")
    monkeypatch.setattr(settings, "eos_base_url", FAKE_BASE_URL)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    monkeypatch.setattr(settings, "eos_cache_ttl_seconds", 300)
    monkeypatch.setattr(settings, "eos_rate_limit_per_minute", 10)


def test_eos_status_unconfigured_has_no_secret_or_provider_url():
    r = client.get("/api/providers/eos/status")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "eos"
    assert body["configured"] is False
    assert body["enabled"] is False
    assert body["status"] == "unconfigured"
    assert "EOS_API_KEY" not in r.text
    assert FAKE_BASE_URL not in r.text


def test_eos_status_configured_disabled_does_not_return_key(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    r = client.get("/api/providers/eos/status")
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    assert r.json()["configured"] is True
    assert FAKE_KEY not in r.text
    assert "x-api-key" not in r.text
    assert "api_key" not in r.text


def test_eos_status_ready_does_not_contact_provider_or_return_key(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)
    r = client.get("/api/providers/eos/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["enabled"] is True
    assert all(feature["available"] for feature in body["features"])
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_app_imports_without_provider_secret():
    from app.main import app as imported_app

    assert imported_app.title == "Akasha BFF"


def test_eos_client_sends_x_api_key_header_without_exposing_it():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"ok": True})

    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    eos = EosClient(api_key=FAKE_KEY, base_url="https://example.test", client=http_client)
    assert eos.request("GET", "/field-management/1") == {"ok": True}
    assert seen["header"] == FAKE_KEY


def test_eos_client_missing_key_is_sanitized():
    eos = EosClient(api_key="", base_url="https://example.test")
    with pytest.raises(AkashaError) as ei:
        eos.request("GET", "/field-management/1")
    payload = ei.value.to_payload()
    assert payload["error"]["code"] == "PROVIDER_UNCONFIGURED"
    assert FAKE_KEY not in str(payload)
    assert FAKE_BASE_URL not in str(payload)


def test_eos_client_timeout_maps_to_sanitized_504():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout with token fake-eos-key-super-secret")

    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    eos = EosClient(api_key=FAKE_KEY, base_url="https://example.test", client=http_client)
    with pytest.raises(AkashaError) as ei:
        eos.request("GET", "/field-management/1")
    payload = ei.value.to_payload()
    assert ei.value.status_code == 504
    assert payload["error"]["code"] == "PROVIDER_TIMEOUT"
    assert FAKE_KEY not in str(payload)
    assert "Traceback" not in str(payload)


def test_eos_client_rate_limit_error_does_not_echo_raw_body():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "12"},
            text=(
                "api_key=fake-eos-key-super-secret "
                "https://api-connect.eos.com SELECT * FROM secrets"
            ),
        )

    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    eos = EosClient(api_key=FAKE_KEY, base_url="https://example.test", client=http_client)
    with pytest.raises(AkashaError) as ei:
        eos.request("GET", "/field-management/1")
    payload = ei.value.to_payload()
    assert ei.value.status_code == 429
    assert payload["error"]["code"] == "PROVIDER_RATE_LIMITED"
    assert payload["error"]["details"]["retryAfterSeconds"] == 12
    assert FAKE_KEY not in str(payload)
    assert "SELECT * FROM secrets" not in str(payload)
    assert FAKE_BASE_URL not in str(payload)


def test_field_mirror_normalizes_response_and_updates_provider_link(monkeypatch):
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            return {"id": 9793351, "area": "77.0"}

    link_updates: list[dict[str, Any]] = []

    def fake_update_provider_link(plot_id: str, **kwargs):
        link_updates.append({"plot_id": plot_id, **kwargs})
        return None

    monkeypatch.setattr(plots_repo, "update_provider_link", fake_update_provider_link)
    provider = EosFieldProvider(client=FakeClient())
    result = provider.mirror_field(
        {
            "id": "akasha-plot-1",
            "name": "North field",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.2, 12.1], [78.3, 12.1], [78.3, 12.2], [78.2, 12.1]]],
            },
            "groupName": "North Farm",
            "cropType": "Paddy",
            "sowingDate": "2026-06-01",
        }
    )
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/field-management"
    assert result.plot_id == "akasha-plot-1"
    assert result.external_field_id == "9793351"
    assert result.provider_area_ha == pytest.approx(77.0)
    assert link_updates == [
        {
            "plot_id": "akasha-plot-1",
            "external_provider": "eos",
            "external_field_id": "9793351",
            "provider_sync_status": "synced",
            "provider_metadata": {"fieldAreaHa": 77.0},
        }
    ]


def test_scene_provider_normalizes_async_search_and_results():
    class FakeClient:
        def request(self, method, path, **kwargs):
            if method == "POST":
                assert path == "/scene-search/for-field/9793351"
                assert kwargs["json"]["params"]["data_source"] == ["sentinel2"]
                return {"status": "pending", "request_id": "request-1"}
            assert path == "/scene-search/for-field/9793351/request-1"
            return {
                "status": "success",
                "result": [
                    {
                        "date": "2026-06-01",
                        "view_id": "S2/43/P/FM/2026/6/1/0",
                        "cloud": 8.5,
                    }
                ],
            }

    provider = EosSceneProvider(client=FakeClient())
    request = provider.search_scenes(
        "9793351",
        date(2026, 6, 1),
        date(2026, 6, 30),
        sensors=["sentinel2"],
    )
    scenes = provider.get_scene_search_result("9793351", request.request_id)
    assert request.request_id == "request-1"
    assert scenes[0].scene_id == "S2/43/P/FM/2026/6/1/0"
    assert scenes[0].sensor == "S2"
    assert scenes[0].cloud_percent == pytest.approx(8.5)


def test_tile_provider_returns_same_origin_template_only():
    scene = SceneMetadata(
        scene_id="S2/43/P/FM/2026/6/1/0",
        view_id="S2/43/P/FM/2026/6/1/0",
        acquisition_date=date(2026, 6, 1),
    )
    tile = EosTileProvider().get_tile_template(scene, layer_type="index", index="NDVI")
    assert tile.tile_url_template.startswith("/api/tiles/")
    assert "{z}/{x}/{y}.png" in tile.tile_url_template
    assert "api-connect.eos.com" not in tile.tile_url_template
    assert "api_key" not in tile.tile_url_template
    assert "x-api-key" not in tile.tile_url_template
