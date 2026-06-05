"""Selected-field weather routes for EOS-parity Phase 7."""
from __future__ import annotations

import functools
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

from . import plots_repo
from .auth import get_current_team
from .config import settings
from .providers.eos.weather_provider import EosWeatherProvider
from .providers.models import ProviderModel, WeatherRecord, WeatherResponse
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.weather")

router = APIRouter(prefix="/api", tags=["weather"], dependencies=[Depends(get_current_team)])

ProviderChoice = Literal["auto", "eos", "native"]
MAX_HISTORY_DAYS = 365
MAX_FORECAST_DAYS = 14
DEFAULT_FORECAST_DAYS = 7
DEFAULT_HISTORY_DAYS = 30

WEATHER_SERIES_DEFS: dict[str, tuple[str, str]] = {
    "accumulatedPrecipitation": ("Accumulated precipitation", "mm"),
    "dailyPrecipitation": ("Daily precipitation", "mm"),
    "dailyTemperature": ("Daily temperature", "C"),
    "sumActiveTemperatures": ("Sum active temperatures", "C"),
    "evapotranspiration": ("Evapotranspiration", "mm"),
    "relativeHumidity": ("Relative humidity", "%"),
    "globalRadiation": ("Global radiation", "MJ/m2"),
}


class WeatherForecastCard(ProviderModel):
    id: str
    label: str
    value: float | None = None
    unit: str
    secondary_value: float | None = None
    secondary_unit: str | None = None
    summary: str


class WeatherForecastPoint(ProviderModel):
    date: date
    start_time: datetime | None = None
    end_time: datetime | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    temperature_avg_c: float | None = None
    precipitation_mm: float | None = None
    humidity_percent: float | None = None
    cloudiness_percent: float | None = None
    wind_mps: float | None = None
    wind_direction: str | None = None
    conditions: str | None = None


class WeatherForecastResponse(ProviderModel):
    plot_id: str
    provider: str
    scope: Literal["field"] = "field"
    start_date: date
    end_date: date
    cards: list[WeatherForecastCard]
    timeline: list[WeatherForecastPoint]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WeatherSeriesPoint(ProviderModel):
    date: date
    value: float | None = None


class WeatherSeries(ProviderModel):
    id: str
    label: str
    unit: str
    available: bool = True
    unavailable_reason: str | None = None
    points: list[WeatherSeriesPoint] = Field(default_factory=list)


class WeatherHistoryResponse(ProviderModel):
    plot_id: str
    provider: str
    scope: Literal["field"] = "field"
    start_date: date
    end_date: date
    series: list[WeatherSeries]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WeatherSoilMoistureResponse(ProviderModel):
    plot_id: str
    provider: str
    scope: Literal["field"] = "field"
    start_date: date
    end_date: date
    available: bool
    series: WeatherSeries | None = None
    unavailable_reason: str | None = None
    unavailable_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


async def _run_blocking(
    func,
    *args,
    error_scope: Literal["storage", "provider"] = "storage",
    **kwargs,
):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("weather backend unavailable: %s", type(exc).__name__)
        if error_scope == "provider":
            raise AkashaError(
                "PROVIDER_UPSTREAM_ERROR",
                "Weather provider is unavailable.",
                502,
                {"provider": "eos"},
            ) from exc
        raise plots_backend_unavailable(
            "Weather field storage is not available in this environment."
        ) from exc


async def _get_plot_or_404(plot_id: str) -> dict[str, Any]:
    plot = await _run_blocking(plots_repo.get_plot, plot_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


def _is_eos_ready() -> bool:
    mode = (settings.provider_mode or "disabled").strip().lower()
    return bool(settings.eos_api_key.strip()) and settings.eos_enabled and mode in {"eos", "hybrid"}


def _default_history_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=DEFAULT_HISTORY_DAYS), today


def _forecast_range(days: int) -> tuple[date, date]:
    if days < 1 or days > MAX_FORECAST_DAYS:
        raise bad_request(
            f"Forecast range must be between 1 and {MAX_FORECAST_DAYS} days.",
            code="INVALID_FORECAST_RANGE",
            maxDays=MAX_FORECAST_DAYS,
        )
    today = datetime.now(UTC).date()
    return today, today + timedelta(days=days - 1)


def _validate_history_range(date_start: date, date_end: date) -> None:
    if date_start > date_end:
        raise bad_request("startDate must be on or before endDate.", code="INVALID_DATE_RANGE")
    if (date_end - date_start).days > MAX_HISTORY_DAYS:
        raise bad_request(
            "Weather history ranges are limited to 365 days.",
            code="DATE_RANGE_TOO_LARGE",
            maxDays=MAX_HISTORY_DAYS,
        )


def _split_parameters(parameters: list[str] | None) -> list[str]:
    if not parameters:
        return list(WEATHER_SERIES_DEFS)
    values: list[str] = []
    for item in parameters:
        values.extend(part.strip() for part in item.split(",") if part.strip())
    unsupported = [item for item in values if item not in WEATHER_SERIES_DEFS]
    if unsupported:
        raise bad_request(
            "Unsupported weather history parameter.",
            code="UNSUPPORTED_WEATHER_PARAMETER",
            unsupported=unsupported,
            supported=list(WEATHER_SERIES_DEFS),
        )
    return values


def _resolve_external_field_id(plot_id: str, plot: dict[str, Any], provider: ProviderChoice) -> str:
    if provider == "native":
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "Native weather provider is not available yet.",
            503,
            {"provider": "native"},
        )
    external_field_id = plot.get("externalFieldId")
    external_provider = str(plot.get("externalProvider") or "").strip().lower()
    if not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before loading provider weather.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )
    if external_provider and external_provider != "eos":
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "Configured weather provider cannot serve the selected field.",
            503,
            {"provider": provider, "plotId": plot_id},
        )
    if not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "Weather provider is not available.",
            503,
            {"provider": "eos"},
        )
    return str(external_field_id)


def _record_date(record: WeatherRecord) -> date | None:
    if record.record_date:
        return record.record_date
    if record.start_time:
        return record.start_time.date()
    return None


def _temperature_avg(record: WeatherRecord) -> float | None:
    if record.temperature_avg_c is not None:
        return record.temperature_avg_c
    if record.temperature_min_c is not None and record.temperature_max_c is not None:
        return (record.temperature_min_c + record.temperature_max_c) / 2
    return _first_not_none(record.temperature_max_c, record.temperature_min_c)


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} {unit}"


def _forecast_point(record: WeatherRecord) -> WeatherForecastPoint | None:
    item_date = _record_date(record)
    if item_date is None:
        return None
    return WeatherForecastPoint(
        date=item_date,
        start_time=record.start_time,
        end_time=record.end_time,
        temperature_min_c=record.temperature_min_c,
        temperature_max_c=record.temperature_max_c,
        temperature_avg_c=_temperature_avg(record),
        precipitation_mm=record.precipitation_mm,
        humidity_percent=record.humidity_percent,
        cloudiness_percent=record.cloudiness_percent,
        wind_mps=record.wind_mps,
        wind_direction=record.wind_direction,
        conditions=record.conditions,
    )


def _forecast_cards(record: WeatherRecord | None) -> list[WeatherForecastCard]:
    temperature = _temperature_avg(record) if record else None
    precipitation = record.precipitation_mm if record else None
    humidity = record.humidity_percent if record else None
    clouds = record.cloudiness_percent if record else None
    wind = record.wind_mps if record else None
    wind_summary = _fmt(wind, "m/s")
    if record and record.wind_direction:
        wind_summary = f"{wind_summary} {record.wind_direction}"
    return [
        WeatherForecastCard(
            id="temperature",
            label="Temperature",
            value=temperature,
            unit="C",
            summary=_fmt(temperature, "C"),
        ),
        WeatherForecastCard(
            id="precipitation",
            label="Precipitation",
            value=precipitation,
            unit="mm",
            summary=_fmt(precipitation, "mm"),
        ),
        WeatherForecastCard(
            id="relativeHumidity",
            label="Relative humidity",
            value=humidity,
            unit="%",
            summary=_fmt(humidity, "%"),
        ),
        WeatherForecastCard(
            id="clouds",
            label="Clouds",
            value=clouds,
            unit="%",
            summary=_fmt(clouds, "%"),
        ),
        WeatherForecastCard(
            id="wind",
            label="Wind",
            value=wind,
            unit="m/s",
            summary=wind_summary,
        ),
    ]


def _series_value(series_id: str, record: WeatherRecord) -> float | None:
    match series_id:
        case "accumulatedPrecipitation":
            return _first_not_none(
                record.accumulated_precipitation_mm,
                record.precipitation_mm,
            )
        case "dailyPrecipitation":
            return record.precipitation_mm
        case "dailyTemperature":
            return _temperature_avg(record)
        case "sumActiveTemperatures":
            return record.sum_active_temperatures_c
        case "evapotranspiration":
            return record.evapotranspiration_mm
        case "relativeHumidity":
            return record.humidity_percent
        case "globalRadiation":
            return record.global_radiation_mj_m2
        case _:
            return None


def _first_not_none(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _series_from_records(
    series_id: str,
    records: list[WeatherRecord],
) -> WeatherSeries:
    label, unit = WEATHER_SERIES_DEFS[series_id]
    points: list[WeatherSeriesPoint] = []
    for record in records:
        item_date = _record_date(record)
        if item_date is None:
            continue
        points.append(WeatherSeriesPoint(date=item_date, value=_series_value(series_id, record)))
    points.sort(key=lambda point: point.date)
    return WeatherSeries(
        id=series_id,
        label=label,
        unit=unit,
        available=any(point.value is not None for point in points),
        unavailable_reason=None if any(point.value is not None for point in points) else "No data.",
        points=points,
    )


def _eos_forecast_response(
    plot_id: str,
    external_field_id: str,
    date_start: date,
    date_end: date,
) -> WeatherForecastResponse:
    provider = EosWeatherProvider()
    forecast = provider.get_forecast(external_field_id, date_start, date_end)
    timeline = [
        point
        for point in (_forecast_point(record) for record in forecast.records)
        if point is not None
    ]
    timeline.sort(
        key=lambda point: (
            point.date,
            point.start_time.isoformat() if point.start_time else "",
        )
    )
    first_record = forecast.records[0] if forecast.records else None
    return WeatherForecastResponse(
        plot_id=plot_id,
        provider=forecast.provider,
        start_date=date_start,
        end_date=date_end,
        cards=_forecast_cards(first_record),
        timeline=timeline,
        metadata={
            "cacheTtlSeconds": settings.eos_cache_ttl_seconds,
            "forecastDays": (date_end - date_start).days + 1,
        },
    )


def _eos_history_response(
    plot_id: str,
    external_field_id: str,
    date_start: date,
    date_end: date,
    parameters: list[str],
) -> WeatherHistoryResponse:
    provider = EosWeatherProvider()
    history = provider.get_history(external_field_id, date_start, date_end)
    accumulated = provider.get_accumulated(external_field_id, date_start, date_end)
    records_by_series = {
        "accumulatedPrecipitation": accumulated.records,
        "sumActiveTemperatures": accumulated.records,
    }
    series = [
        _series_from_records(series_id, records_by_series.get(series_id, history.records))
        for series_id in parameters
    ]
    return WeatherHistoryResponse(
        plot_id=plot_id,
        provider=history.provider,
        start_date=date_start,
        end_date=date_end,
        series=series,
        metadata={
            "cacheTtlSeconds": settings.eos_cache_ttl_seconds,
            "rangeLimitDays": MAX_HISTORY_DAYS,
        },
    )


def _soil_response_from_provider(
    plot_id: str,
    provider_response: WeatherResponse,
    date_start: date,
    date_end: date,
) -> WeatherSoilMoistureResponse:
    series = WeatherSeries(
        id="soilMoisture",
        label="Soil moisture",
        unit="%",
        available=True,
        points=[
            WeatherSeriesPoint(date=item_date, value=record.soil_moisture_percent)
            for record in provider_response.records
            if (item_date := _record_date(record)) is not None
        ],
    )
    series.available = any(point.value is not None for point in series.points)
    if not series.available:
        series.unavailable_reason = "No soil-moisture values were returned."
    return WeatherSoilMoistureResponse(
        plot_id=plot_id,
        provider=provider_response.provider,
        start_date=date_start,
        end_date=date_end,
        available=series.available,
        series=series,
        unavailable_reason=series.unavailable_reason,
        unavailable_code=None if series.available else "NO_SOIL_MOISTURE_VALUES",
        metadata={"cacheTtlSeconds": settings.eos_cache_ttl_seconds},
    )


@router.get(
    "/fields/{plot_id}/weather/forecast",
    response_model=WeatherForecastResponse,
    response_model_by_alias=True,
)
async def get_field_weather_forecast(
    plot_id: str,
    response: Response,
    provider: ProviderChoice = "auto",
    days: int = Query(default=DEFAULT_FORECAST_DAYS, ge=1, le=MAX_FORECAST_DAYS),
) -> WeatherForecastResponse:
    date_start, date_end = _forecast_range(days)
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, provider)
    response.headers["Cache-Control"] = f"private, max-age={settings.eos_cache_ttl_seconds}"
    return await _run_blocking(
        _eos_forecast_response,
        plot_id,
        external_field_id,
        date_start,
        date_end,
        error_scope="provider",
    )


@router.get(
    "/fields/{plot_id}/weather/history",
    response_model=WeatherHistoryResponse,
    response_model_by_alias=True,
)
async def get_field_weather_history(
    plot_id: str,
    response: Response,
    provider: ProviderChoice = "auto",
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    parameters: list[str] | None = Query(default=None),
) -> WeatherHistoryResponse:
    default_start, default_end = _default_history_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_history_range(date_start, date_end)
    selected_parameters = _split_parameters(parameters)
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, provider)
    response.headers["Cache-Control"] = f"private, max-age={settings.eos_cache_ttl_seconds}"
    return await _run_blocking(
        _eos_history_response,
        plot_id,
        external_field_id,
        date_start,
        date_end,
        selected_parameters,
        error_scope="provider",
    )


@router.get(
    "/fields/{plot_id}/weather/soil-moisture",
    response_model=WeatherSoilMoistureResponse,
    response_model_by_alias=True,
)
async def get_field_weather_soil_moisture(
    plot_id: str,
    response: Response,
    provider: ProviderChoice = "auto",
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
) -> WeatherSoilMoistureResponse:
    default_start, default_end = _default_history_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_history_range(date_start, date_end)
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, provider)
    response.headers["Cache-Control"] = f"private, max-age={settings.eos_cache_ttl_seconds}"

    def _load() -> WeatherSoilMoistureResponse:
        try:
            provider_response = EosWeatherProvider().get_soil_moisture(
                external_field_id,
                date_start,
                date_end,
            )
        except AkashaError as exc:
            if exc.code != "PROVIDER_FEATURE_UNAVAILABLE":
                raise
            return WeatherSoilMoistureResponse(
                plot_id=plot_id,
                provider="eos",
                start_date=date_start,
                end_date=date_end,
                available=False,
                unavailable_reason=exc.message,
                unavailable_code=exc.code,
                metadata={"cacheTtlSeconds": settings.eos_cache_ttl_seconds},
            )
        return _soil_response_from_provider(plot_id, provider_response, date_start, date_end)

    return await _run_blocking(_load, error_scope="provider")
