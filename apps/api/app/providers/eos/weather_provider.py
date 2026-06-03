"""EOS field weather provider."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal
from urllib.parse import quote

from ...raster.errors import AkashaError
from ..models import WeatherRecord, WeatherResponse
from .client import EosClient


class EosWeatherProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def get_forecast(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse:
        field_id = quote(external_field_id, safe="")
        response = self.client.request(
            "POST",
            f"/weather/forecast/{field_id}",
            json={
                "params": {
                    "date_start": date_start.isoformat(),
                    "date_end": date_end.isoformat(),
                }
            },
        )
        return _weather_response(external_field_id, "forecast", response)

    def get_history(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse:
        field_id = quote(external_field_id, safe="")
        response = self.client.request(
            "POST",
            f"/weather/historical-high-accuracy/{field_id}",
            json={
                "params": {
                    "date_start": date_start.isoformat(),
                    "date_end": date_end.isoformat(),
                }
            },
        )
        return _weather_response(external_field_id, "history", response)

    def get_accumulated(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse:
        field_id = quote(external_field_id, safe="")
        response = self.client.request(
            "POST",
            f"/weather/historical-accumulated/{field_id}",
            json={
                "params": {
                    "date_start": date_start.isoformat(),
                    "date_end": date_end.isoformat(),
                }
            },
        )
        return _weather_response(external_field_id, "accumulated", response)

    def get_soil_moisture(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse:
        raise AkashaError(
            "PROVIDER_FEATURE_UNAVAILABLE",
            "Soil-moisture weather data is not available from the configured provider.",
            503,
            {
                "provider": "eos",
                "feature": "soil_moisture",
                "externalFieldId": external_field_id,
                "startDate": date_start.isoformat(),
                "endDate": date_end.isoformat(),
            },
        )


def _weather_response(
    external_field_id: str,
    kind: Literal["forecast", "history", "accumulated"],
    items: list[dict[str, Any]],
) -> WeatherResponse:
    records: list[WeatherRecord] = []
    for item in items:
        item_date = date.fromisoformat(str(item["date"])[:10]) if item.get("date") else None
        nested = item.get("forecast")
        if isinstance(nested, list):
            for record in nested:
                records.append(_record(record, item_date))
        else:
            records.append(_record(item, item_date))
    return WeatherResponse(external_field_id=external_field_id, kind=kind, records=records)


def _record(item: dict[str, Any], item_date: date | None) -> WeatherRecord:
    return WeatherRecord(
        record_date=item_date,
        start_time=item.get("start_time"),
        end_time=item.get("end_time"),
        temperature_avg_c=_to_float(
            _first_present(
                item,
                "temperature",
                "temperature_avg",
                "temperature_mean",
                "air_temperature",
            )
        ),
        temperature_min_c=_to_float(item.get("temperature_min")),
        temperature_max_c=_to_float(item.get("temperature_max")),
        precipitation_mm=_to_float(
            _first_present(item, "precipitation", "rainfall", "rain")
        ),
        accumulated_precipitation_mm=_to_float(
            _first_present(
                item,
                "accumulated_precipitation",
                "accumulated_precipitation_mm",
                "precipitation_accumulated",
            )
        ),
        humidity_percent=_to_float(_first_present(item, "humidity", "relative_humidity")),
        cloudiness_percent=_to_float(_first_present(item, "cloudiness", "clouds")),
        wind_mps=_to_float(_first_present(item, "wind", "wind_speed")),
        wind_direction=item.get("wind_direction"),
        sum_active_temperatures_c=_to_float(
            _first_present(
                item,
                "sum_active_temperatures",
                "sum_active_temperature",
                "active_temperature_sum",
                "accumulated_temperature",
            )
        ),
        evapotranspiration_mm=_to_float(
            _first_present(item, "evapotranspiration", "et", "eto")
        ),
        global_radiation_mj_m2=_to_float(
            _first_present(item, "global_radiation", "solar_radiation", "radiation")
        ),
        soil_moisture_percent=_to_float(
            _first_present(item, "soil_moisture", "soil_moisture_percent")
        ),
        conditions=item.get("total_conditions"),
        conditions_code=(
            str(item["conditions_code"]) if item.get("conditions_code") is not None else None
        ),
    )


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if item.get(key) is not None:
            return item[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
