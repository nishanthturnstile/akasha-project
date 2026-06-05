"""Phase 7 selected-field weather route tests."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app import weather
from app.config import settings
from app.main import app
from app.providers.models import WeatherRecord, WeatherResponse
from app.raster.errors import AkashaError
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
    monkeypatch.setattr(settings, "eos_cache_ttl_seconds", 300)


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {"type": "Polygon", "coordinates": []},
        "areaHa": 5.0,
        "externalProvider": "eos",
        "externalFieldId": "provider-field-secret",
        "providerSyncStatus": "synced",
    }
    plot.update(overrides)
    return plot


def _enable_eos(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "eos")
    monkeypatch.setattr(settings, "eos_enabled", True)


def test_weather_forecast_returns_normalized_cards_without_provider_leak(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    class FakeWeatherProvider:
        def get_forecast(self, external_field_id, date_start, date_end):
            assert external_field_id == "provider-field-secret"
            assert date_start <= date_end
            return WeatherResponse(
                external_field_id=external_field_id,
                kind="forecast",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 3),
                        temperature_min_c=20,
                        temperature_max_c=30,
                        precipitation_mm=4,
                        humidity_percent=75,
                        cloudiness_percent=40,
                        wind_mps=3.2,
                        wind_direction="NE",
                        conditions="Partly cloudy",
                    )
                ],
            )

    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    r = client.get("/api/fields/plot-1/weather/forecast?days=3")

    assert r.status_code == 200
    body = r.json()
    assert body["plotId"] == "plot-1"
    assert {card["id"] for card in body["cards"]} == {
        "temperature",
        "precipitation",
        "relativeHumidity",
        "clouds",
        "wind",
    }
    assert body["timeline"][0]["date"] == "2026-06-03"
    assert "provider-field-secret" not in r.text
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_weather_history_returns_required_series(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    class FakeWeatherProvider:
        def get_history(self, *_args):
            return WeatherResponse(
                external_field_id="provider-field-secret",
                kind="history",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        temperature_avg_c=24,
                        precipitation_mm=2,
                        humidity_percent=70,
                        evapotranspiration_mm=3.4,
                        global_radiation_mj_m2=18,
                    )
                ],
            )

        def get_accumulated(self, *_args):
            return WeatherResponse(
                external_field_id="provider-field-secret",
                kind="accumulated",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        accumulated_precipitation_mm=12,
                        sum_active_temperatures_c=124,
                    )
                ],
            )

    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    r = client.get(
        "/api/fields/plot-1/weather/history"
        "?startDate=2026-06-01&endDate=2026-06-02"
    )

    assert r.status_code == 200
    series = {item["id"]: item for item in r.json()["series"]}
    assert set(series) == set(weather.WEATHER_SERIES_DEFS)
    assert series["dailyTemperature"]["points"][0]["value"] == 24
    assert series["accumulatedPrecipitation"]["points"][0]["value"] == 12
    assert series["sumActiveTemperatures"]["points"][0]["value"] == 124
    assert "provider-field-secret" not in r.text


def test_weather_history_preserves_zero_accumulated_precipitation(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    class FakeWeatherProvider:
        def get_history(self, *_args):
            return WeatherResponse(
                external_field_id="provider-field-secret",
                kind="history",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        precipitation_mm=7,
                    )
                ],
            )

        def get_accumulated(self, *_args):
            return WeatherResponse(
                external_field_id="provider-field-secret",
                kind="accumulated",
                records=[
                    WeatherRecord(
                        record_date=date(2026, 6, 1),
                        accumulated_precipitation_mm=0,
                    )
                ],
            )

    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    r = client.get(
        "/api/fields/plot-1/weather/history"
        "?startDate=2026-06-01&endDate=2026-06-02"
        "&parameters=accumulatedPrecipitation"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["series"][0]["points"][0]["value"] == 0


def test_weather_soil_moisture_unsupported_is_optional_response(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    class FakeWeatherProvider:
        def get_soil_moisture(self, *_args):
            raise AkashaError(
                "PROVIDER_FEATURE_UNAVAILABLE",
                "Soil-moisture weather data is not available from the configured provider.",
                503,
                {"provider": "eos"},
            )

    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    r = client.get(
        "/api/fields/plot-1/weather/soil-moisture"
        "?startDate=2026-06-01&endDate=2026-06-02"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["unavailableCode"] == "PROVIDER_FEATURE_UNAVAILABLE"
    assert "provider-field-secret" not in r.text


def test_weather_requires_synced_field(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot(externalFieldId=None))

    r = client.get("/api/fields/plot-1/weather/forecast")

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FIELD_PROVIDER_NOT_SYNCED"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_weather_respects_provider_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "eos_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "provider_mode", "disabled")
    monkeypatch.setattr(settings, "eos_enabled", False)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    r = client.get("/api/fields/plot-1/weather/forecast")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text


def test_weather_field_not_found(monkeypatch):
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: None)

    r = client.get("/api/fields/missing/weather/history")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FIELD_NOT_FOUND"


def test_weather_rate_limit_error_is_sanitized(monkeypatch):
    _enable_eos(monkeypatch)
    monkeypatch.setattr(weather.plots_repo, "get_plot", lambda _: _plot())

    class FakeWeatherProvider:
        def get_forecast(self, *_args):
            raise AkashaError(
                "PROVIDER_RATE_LIMITED",
                "EOS provider rate limit was reached.",
                429,
                {"provider": "eos", "retryAfterSeconds": 12, "url": FAKE_BASE_URL},
            )

    monkeypatch.setattr(weather, "EosWeatherProvider", lambda: FakeWeatherProvider())
    r = client.get("/api/fields/plot-1/weather/forecast")

    assert r.status_code == 429
    assert r.json()["error"]["code"] == "PROVIDER_RATE_LIMITED"
    assert r.json()["error"]["details"]["retryAfterSeconds"] == 12
    assert FAKE_KEY not in r.text
    assert FAKE_BASE_URL not in r.text
