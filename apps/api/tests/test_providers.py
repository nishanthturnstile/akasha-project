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
from app.providers.cloud_mask import cloud_mask_mapping, native_scl_excluded_classes
from app.providers.eos.analytics_provider import EosAnalyticsProvider
from app.providers.eos.client import EosClient
from app.providers.eos.field_provider import EosFieldProvider
from app.providers.eos.imagery_provider import EosImageryProvider
from app.providers.eos.scene_provider import EosSceneProvider
from app.providers.eos.tile_provider import EosTileProvider
from app.providers.eos.weather_provider import EosWeatherProvider
from app.providers.models import CloudMaskOptions, SceneMetadata
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


def test_eos_client_does_not_send_api_key_to_cross_origin_download_url():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["header"] = request.headers.get("x-api-key")
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(
            200,
            content=b"downloaded-tiff",
            headers={"Content-Type": "image/tiff"},
        )

    http_client = httpx.Client(
        base_url=FAKE_BASE_URL,
        transport=httpx.MockTransport(handler),
    )
    eos = EosClient(api_key=FAKE_KEY, base_url=FAKE_BASE_URL, client=http_client)
    body, content_type = eos.request_bytes("GET", "https://downloads.example.test/export.tif")

    assert body == b"downloaded-tiff"
    assert content_type == "image/tiff"
    assert seen["url"] == "https://downloads.example.test/export.tif"
    assert seen["header"] is None
    assert "image/png" in str(seen["accept"])


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


def test_weather_provider_normalizes_history_and_accumulated_records():
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            return [
                {
                    "date": "2026-06-01",
                    "temperature": "24.5",
                    "precipitation": "3.2",
                    "relative_humidity": "81",
                    "evapotranspiration": "2.8",
                    "global_radiation": "17.5",
                    "sum_active_temperatures": "126",
                }
            ]

    provider = EosWeatherProvider(client=FakeClient())
    response = provider.get_history("field id/with spaces", date(2026, 6, 1), date(2026, 6, 2))

    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/weather/historical-high-accuracy/field%20id%2Fwith%20spaces"
    record = response.records[0]
    assert record.temperature_avg_c == 24.5
    assert record.precipitation_mm == 3.2
    assert record.humidity_percent == 81
    assert record.evapotranspiration_mm == 2.8
    assert record.global_radiation_mj_m2 == 17.5
    assert record.sum_active_temperatures_c == 126


def test_weather_provider_preserves_zero_values():
    class FakeClient:
        def request(self, *_args, **_kwargs):
            return [
                {
                    "date": "2026-06-01",
                    "temperature": 0,
                    "precipitation": 0,
                    "relative_humidity": 0,
                    "cloudiness": 0,
                    "wind": 0,
                    "evapotranspiration": 0,
                    "global_radiation": 0,
                    "sum_active_temperatures": 0,
                }
            ]

    provider = EosWeatherProvider(client=FakeClient())
    response = provider.get_history("field-1", date(2026, 6, 1), date(2026, 6, 2))
    record = response.records[0]

    assert record.temperature_avg_c == 0
    assert record.precipitation_mm == 0
    assert record.humidity_percent == 0
    assert record.cloudiness_percent == 0
    assert record.wind_mps == 0
    assert record.evapotranspiration_mm == 0
    assert record.global_radiation_mj_m2 == 0
    assert record.sum_active_temperatures_c == 0


def test_weather_provider_soil_moisture_is_explicitly_feature_unavailable():
    provider = EosWeatherProvider(client=object())

    with pytest.raises(AkashaError) as ei:
        provider.get_soil_moisture("field-1", date(2026, 6, 1), date(2026, 6, 2))

    assert ei.value.code == "PROVIDER_FEATURE_UNAVAILABLE"
    assert FAKE_KEY not in str(ei.value.to_payload())


def test_scene_provider_polls_pending_result_before_returning_scenes():
    get_count = 0

    class FakeClient:
        def request(self, method, path, **kwargs):
            nonlocal get_count
            if method == "POST":
                return {"status": "pending", "request_id": "request-1"}
            get_count += 1
            if get_count == 1:
                return {"status": "pending", "result": []}
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
    request = provider.search_scenes("9793351", date(2026, 6, 1), date(2026, 6, 30))
    scenes = provider.get_scene_search_result(
        "9793351",
        request.request_id,
        poll_interval_seconds=0,
        timeout_seconds=1,
    )

    assert get_count == 2
    assert scenes[0].scene_id == "S2/43/P/FM/2026/6/1/0"


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


def test_cloud_mask_mapping_exact_and_conservative_cases():
    all_off = CloudMaskOptions(clouds=False, cloud_shadows=False, cirrus=False)
    assert native_scl_excluded_classes(all_off) == (0, 1, 2, 11)
    assert cloud_mask_mapping(all_off).eos_cloud_masking_level is None

    clouds_only = CloudMaskOptions(clouds=True, cloud_shadows=False, cirrus=False)
    assert native_scl_excluded_classes(clouds_only) == (0, 1, 2, 7, 8, 9, 11)
    assert cloud_mask_mapping(clouds_only).eos_cloud_masking_level == 2
    assert cloud_mask_mapping(clouds_only).eos_exact is True

    shadows_only = CloudMaskOptions(clouds=False, cloud_shadows=True, cirrus=False)
    mapping = cloud_mask_mapping(shadows_only)
    assert mapping.eos_cloud_masking_level == 3
    assert mapping.eos_exact is False
    assert "EOS_CLOUD_MASK_APPROXIMATION" in mapping.warnings


def test_analytics_provider_normalizes_trend_points():
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            if method == "POST":
                return {"status": "created", "request_id": "trend-1"}
            return {
                "status": "success",
                "result": [
                    {
                        "scene_id": "S2B_tile_20230420_13REL_0",
                        "view_id": "S2/13/R/EL/2023/4/20/0",
                        "date": "2023-04-20",
                        "cloud": 7,
                        "min": 0.1,
                        "max": 0.8,
                        "average": 0.6,
                        "std": 0.12,
                    }
                ],
            }

    provider = EosAnalyticsProvider(client=FakeClient())
    request = provider.create_trend_request(
        "9793351",
        date(2023, 4, 1),
        date(2023, 4, 30),
        index="NDVI",
        data_source="S2",
        cloud_mask=CloudMaskOptions(clouds=True, cloud_shadows=True, cirrus=True),
    )
    points = provider.get_trend_result("9793351", request.request_id, index="NDVI")

    assert calls[0]["path"] == "/field-analytics/trend/9793351"
    assert calls[0]["json"]["params"]["distinct_by_date"] is True
    assert calls[0]["json"]["params"]["exclude_cover_pixels"] is True
    assert calls[0]["json"]["params"]["cloud_masking_level"] == 3
    assert calls[1]["path"] == "/field-analytics/trend/9793351/trend-1"
    assert points[0].mean == pytest.approx(0.6)
    assert points[0].minimum == pytest.approx(0.1)
    assert points[0].maximum == pytest.approx(0.8)
    assert points[0].cloud_percent == pytest.approx(7)


def test_analytics_provider_polls_pending_result_before_returning_points():
    get_count = 0

    class FakeClient:
        def request(self, method, path, **kwargs):
            nonlocal get_count
            if method == "POST":
                return {"status": "created", "request_id": "trend-1"}
            get_count += 1
            if get_count == 1:
                return {"status": "running", "result": []}
            return {
                "status": "success",
                "result": [
                    {
                        "date": "2023-04-20",
                        "average": 0.6,
                    }
                ],
            }

    provider = EosAnalyticsProvider(client=FakeClient())
    request = provider.create_trend_request(
        "9793351",
        date(2023, 4, 1),
        date(2023, 4, 30),
        index="NDVI",
        data_source="S2",
    )
    points = provider.get_trend_result(
        "9793351",
        request.request_id,
        index="NDVI",
        poll_interval_seconds=0,
        timeout_seconds=1,
    )

    assert get_count == 2
    assert points[0].mean == pytest.approx(0.6)


def test_imagery_provider_exports_geotiff_bytes_without_exposing_download_url():
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            if method == "POST":
                return {"task_id": "export-1"}
            return {"status": "done", "result": {"download_url": "/safe-provider-download"}}

        def request_bytes(self, method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            assert path == "/safe-provider-download"
            return b"tiff-bytes", "image/tiff"

    provider = EosImageryProvider(client=FakeClient())
    exported = provider.export_index_geotiff(
        "9793351",
        scene_token="opaque-scene",
        acquisition_date=date(2026, 6, 1),
        index="NDVI",
        cloud_mask=CloudMaskOptions(clouds=True, cloud_shadows=True, cirrus=True),
        filename="north_2026-06-01_NDVI.tiff",
    )

    assert calls[0]["path"] == "/api/gdw/api"
    assert calls[0]["json"]["type"] == "bandmath"
    assert calls[0]["json"]["params"]["cloud_masking_level"] == 3
    assert exported.content == b"tiff-bytes"
    assert exported.content_type == "image/tiff"
    assert "api-connect" not in str(exported.model_dump())
