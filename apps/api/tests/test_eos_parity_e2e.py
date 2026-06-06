"""Phase 13 mocked EOS-parity end-to-end verification."""
from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from app import field_analytics, field_monitoring, field_zoning, main, plots, reports, weather
from app.config import settings
from app.main import app
from app.providers.models import (
    AnalyticsTrendPoint,
    FieldMirrorResult,
    ProviderAsyncRequest,
    SceneMetadata,
    TileBytes,
    WeatherRecord,
    WeatherResponse,
    ZoningMapStatus,
    ZoningZone,
)
from fastapi.testclient import TestClient

client = TestClient(app)

FAKE_KEY = "fake-eos-key-super-secret"
FAKE_BASE_URL = "https://api-connect.eos.com"
PLOT_ID = "11111111-1111-4111-8111-111111111111"
PUBLIC_MAP_ID = "22222222-2222-4222-8222-222222222222"
EXTERNAL_FIELD_ID = "raw-provider-field-secret"
EXTERNAL_ZMAP_ID = "raw-provider-zmap-secret"


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": PLOT_ID,
        "name": "North Field",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]],
        },
        "areaHa": 5.0,
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
        "externalProvider": "eos",
        "externalFieldId": EXTERNAL_FIELD_ID,
        "providerSyncStatus": "synced",
        "providerSyncedAt": "2026-06-04T00:00:00Z",
        "cropType": "Paddy",
        "groupName": "North",
    }
    plot.update(overrides)
    return plot


def _assert_no_provider_leaks(text: str) -> None:
    for leaked in [FAKE_KEY, FAKE_BASE_URL, EXTERNAL_ZMAP_ID, "x-api-key"]:
        assert leaked not in text


@pytest.fixture(autouse=True)
def safe_env(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "app_env", "development")
    for key in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID"):
        monkeypatch.delenv(key, raising=False)


def test_offline_provider_status_is_sanitized(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", "")
    monkeypatch.setattr(settings, "eos_base_url", FAKE_BASE_URL)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)

    r = client.get("/api/providers/eos/status")

    assert r.status_code == 200
    assert r.json()["status"] == "unconfigured"
    _assert_no_provider_leaks(r.text)


def test_mocked_eos_parity_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "max_request_body_bytes", 1_000_000_000)
    monkeypatch.setattr(main.settings, "max_request_body_bytes", 1_000_000_000)
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "eos_base_url", FAKE_BASE_URL)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)

    created_plot = _plot(externalFieldId=None, providerSyncStatus=None)
    synced_plot = _plot()

    monkeypatch.setattr(plots.plots_repo, "create_plot", lambda *args, **kwargs: created_plot)
    monkeypatch.setattr(field_monitoring.plots_repo, "get_plot", lambda *_: synced_plot)
    monkeypatch.setattr(
        field_monitoring.plots_repo,
        "update_provider_link",
        lambda *args, **kwargs: synced_plot,
    )
    monkeypatch.setattr(field_analytics.plots_repo, "get_plot", lambda *_: synced_plot)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda *_: synced_plot)
    monkeypatch.setattr(field_zoning.plots_repo, "get_plot", lambda *_: synced_plot)
    monkeypatch.setattr(reports.plots_repo, "list_plots", lambda: [synced_plot])

    class FakeFieldProvider:
        def mirror_field(self, plot):
            return FieldMirrorResult(
                plot_id=PLOT_ID,
                external_field_id=EXTERNAL_FIELD_ID,
                sync_status="synced",
                synced_at=datetime(2026, 6, 4, tzinfo=UTC),
            )

        def update_mirror(self, plot, external_field_id):
            return self.mirror_field(plot)

    class FakeSceneProvider:
        def search_scenes(self, *_args, **_kwargs):
            return ProviderAsyncRequest(request_id="scene-request", status="done")

        def get_scene_search_result(self, *_args, **_kwargs):
            return [
                SceneMetadata(
                    scene_id="scene-1",
                    view_id="view-1",
                    acquisition_date=date(2026, 6, 1),
                    cloud_percent=5,
                    usable_percent=95,
                    coverage_percent=100,
                )
            ]

    class FakeTileProvider:
        def render_tile(self, *_args, **_kwargs):
            return TileBytes(content=b"\x89PNG\r\n\x1a\nmock", content_type="image/png")

    class FakeAnalyticsProvider:
        def create_trend_request(self, *_args, **_kwargs):
            return ProviderAsyncRequest(request_id="trend-request", status="done")

        def get_trend_result(self, *_args, **_kwargs):
            return [
                AnalyticsTrendPoint(
                    acquisition_date=date(2026, 6, 1),
                    index="NDVI",
                    mean=0.65,
                    minimum=0.2,
                    maximum=0.9,
                )
            ]

    class FakeWeatherProvider:
        def get_forecast(self, *_args):
            return WeatherResponse(
                external_field_id=EXTERNAL_FIELD_ID,
                kind="forecast",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        temperature_avg_c=28,
                        precipitation_mm=3,
                        humidity_percent=70,
                        cloudiness_percent=30,
                        wind_mps=2,
                    )
                ],
            )

        def get_history(self, *_args):
            return WeatherResponse(
                external_field_id=EXTERNAL_FIELD_ID,
                kind="history",
                records=[WeatherRecord(record_date=date(2026, 6, 1), temperature_avg_c=27)],
            )

        def get_accumulated(self, *_args):
            return WeatherResponse(
                external_field_id=EXTERNAL_FIELD_ID,
                kind="accumulated",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        accumulated_precipitation_mm=12,
                        sum_active_temperatures_c=120,
                    )
                ],
            )

    class FakeZoningProvider:
        def create_vegetation_map(self, *_args, **_kwargs):
            return ProviderAsyncRequest(
                request_id=EXTERNAL_ZMAP_ID,
                status="ready",
                external_zmap_id=EXTERNAL_ZMAP_ID,
            )

        def get_zoning_map(self, *_args, **_kwargs):
            return ZoningMapStatus(
                external_field_id=EXTERNAL_FIELD_ID,
                external_zmap_id=EXTERNAL_ZMAP_ID,
                status="ready",
                map_type="vegetation",
                index="NDVI",
                zone_count=1,
                zones=[
                    ZoningZone(
                        zone_id="zone-1",
                        area_ha=1.2,
                        area_percent=100,
                        fertilizer=0.6,
                        geometry={
                            "type": "Polygon",
                            "coordinates": [
                                [[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]
                            ],
                        },
                    )
                ],
            )

        def list_zoning_maps(self, *_args):
            return []

    zoning_row = {
        "id": PUBLIC_MAP_ID,
        "plotId": PLOT_ID,
        "provider": "eos",
        "externalZmapId": EXTERNAL_ZMAP_ID,
        "providerRequestId": EXTERNAL_ZMAP_ID,
        "status": "ready",
        "mapType": "vegetation",
        "indexType": "NDVI",
        "imageDate": "2026-06-01",
        "zoneCount": 1,
        "minZoneAreaHa": 0.25,
        "metadata": {},
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
    }

    monkeypatch.setattr(
        field_monitoring.provider_factory,
        "field_provider",
        lambda provider="eos": FakeFieldProvider(),
    )
    monkeypatch.setattr(
        field_monitoring.provider_factory,
        "scene_provider",
        lambda provider="eos": FakeSceneProvider(),
    )
    monkeypatch.setattr(
        field_monitoring.provider_factory,
        "tile_provider",
        lambda provider="eos": FakeTileProvider(),
    )
    monkeypatch.setattr(field_analytics, "EosAnalyticsProvider", lambda: FakeAnalyticsProvider())
    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    monkeypatch.setattr(field_zoning, "EosSceneProvider", lambda: FakeSceneProvider())
    monkeypatch.setattr(field_zoning, "EosZoningProvider", lambda: FakeZoningProvider())
    monkeypatch.setattr(field_zoning.zoning_repo, "create_zoning_map", lambda **_kwargs: zoning_row)
    monkeypatch.setattr(field_zoning.zoning_repo, "get_zoning_map", lambda *_args: zoning_row)
    monkeypatch.setattr(
        field_zoning.zoning_repo,
        "update_zoning_map",
        lambda *_args, **_kwargs: zoning_row,
    )
    monkeypatch.setattr(
        reports,
        "_field_statistics",
        lambda **_kwargs: type(
            "Stats",
            (),
            {
                "acquisition_date": "2026-06-01",
                "statistics": type(
                    "S",
                    (),
                    {"mean": 0.6, "validPixelPercent": 90, "cloudMaskedPercent": 5},
                )(),
                "metadata": {"metricsProvisional": False},
            },
        )(),
    )
    monkeypatch.setattr(
        reports.catalog,
        "list_dates",
        lambda _source: [{"acquisitionDate": "2026-06-01"}],
    )

    create = plots.plots_repo.create_plot(
        "North Field",
        synced_plot["geometry"],
        synced_plot["areaHa"],
    )
    assert create["id"] == PLOT_ID

    sync = client.post(f"/api/fields/{PLOT_ID}/providers/eos/sync")
    assert sync.status_code == 200
    _assert_no_provider_leaks(sync.text)

    scenes = client.get(f"/api/fields/{PLOT_ID}/scenes?provider=eos")
    assert scenes.status_code == 200
    scene = scenes.json()["scenes"][0]
    assert scene["layers"][0]["tileUrlTemplate"].startswith("/api/tiles/fields/")
    _assert_no_provider_leaks(scenes.text)

    tile = client.get(scene["layers"][0]["tileUrlTemplate"].replace("{z}/{x}/{y}", "1/2/3"))
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"

    trend = client.get(f"/api/fields/{PLOT_ID}/analytics/trend?provider=eos&indexType=NDVI")
    assert trend.status_code == 200
    assert trend.json()["points"][0]["mean"] == 0.65

    forecast = client.get(f"/api/fields/{PLOT_ID}/weather/forecast")
    history = client.get(
        f"/api/fields/{PLOT_ID}/weather/history?startDate=2026-06-01&endDate=2026-06-02"
    )
    assert forecast.status_code == 200
    assert history.status_code == 200
    _assert_no_provider_leaks(forecast.text + history.text)

    zoning = client.post(
        f"/api/fields/{PLOT_ID}/zoning/vegetation",
        json={"indexType": "NDVI", "imageDate": "2026-06-01", "zoneCount": 3, "minZoneArea": 0.25},
    )
    assert zoning.status_code == 200
    assert zoning.json()["mapId"] == PUBLIC_MAP_ID
    _assert_no_provider_leaks(zoning.text)

    geojson = client.get(f"/api/fields/{PLOT_ID}/zoning/maps/{PUBLIC_MAP_ID}/export.geojson")
    assert geojson.status_code == 200
    assert geojson.json()["features"][0]["properties"]["mapId"] == PUBLIC_MAP_ID
    _assert_no_provider_leaks(geojson.text)

    report = client.get(
        "/api/reports/field-leaderboard/export.csv"
        "?startDate=2026-06-01&endDate=2026-06-01"
    )
    assert report.status_code == 200
    assert "North Field" in report.text
    _assert_no_provider_leaks(report.text)


@pytest.mark.skipif(
    not (
        os.getenv("EOS_API_KEY")
        and os.getenv("AKASHA_REAL_EOS_SMOKE") == "1"
        and os.getenv("EOS_SMOKE_FIELD_GEOJSON")
        and os.getenv("EOS_SMOKE_IMAGE_DATE")
    ),
    reason="Real EOS smoke requires explicit EOS key and smoke inputs.",
)
def test_real_eos_smoke_is_explicitly_guarded():
    pytest.skip(
        "Real EOS configured-demo smoke is an operator-run checklist until a "
        "non-secret live test fixture is approved."
    )
