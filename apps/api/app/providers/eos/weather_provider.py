"""EOS field weather provider."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal
from urllib.parse import quote

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
        temperature_min_c=_to_float(item.get("temperature_min")),
        temperature_max_c=_to_float(item.get("temperature_max")),
        precipitation_mm=_to_float(item.get("precipitation") or item.get("rainfall")),
        humidity_percent=_to_float(item.get("humidity")),
        cloudiness_percent=_to_float(item.get("cloudiness")),
        wind_mps=_to_float(item.get("wind") or item.get("wind_speed")),
        wind_direction=item.get("wind_direction"),
        conditions=item.get("total_conditions"),
        conditions_code=(
            str(item["conditions_code"]) if item.get("conditions_code") is not None else None
        ),
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
