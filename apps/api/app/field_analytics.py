"""Selected-field analytics routes for EOS-parity Phase 5."""
from __future__ import annotations

import asyncio
import functools
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Body, Depends, Query, Request

from . import plots_repo
from .auth import get_current_team
from .config import settings
from .product import _enforce_index_rate_limit
from .providers.cloud_mask import cloud_mask_mapping, native_scl_excluded_classes
from .providers.eos.analytics_provider import EosAnalyticsProvider
from .providers.models import (
    CloudMaskOptions,
    FieldTrendPoint,
    FieldTrendResponse,
    ProviderModel,
)
from .raster import catalog_resolver as catalog
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
from .raster.indices import DEFAULT_INDEX, get_index
from .raster.models import IndexStatisticsModel, PixelCounts
from .raster.service import compute_statistics

logger = logging.getLogger("akasha.api.field_analytics")

router = APIRouter(
    prefix="/api",
    tags=["field-analytics"],
    dependencies=[Depends(get_current_team)],
)

ProviderChoice = Literal["auto", "eos", "native"]
MAX_TREND_DAYS = 365
PROVIDER_INDEX_TYPES = {"NDVI", "NDRE", "NDMI", "MSAVI", "RECI"}


class FieldStatisticsRequest(ProviderModel):
    source_id: str = "sentinel-2-l2a"
    acquisition_date: str | None = None
    index_type: str = DEFAULT_INDEX
    cloud_mask: CloudMaskOptions = CloudMaskOptions()


class FieldStatisticsResponse(ProviderModel):
    plot_id: str
    provider: str = "native"
    scope: Literal["field"] = "field"
    index_type: str
    source_id: str
    acquisition_date: str
    cloud_mask: CloudMaskOptions
    statistics: IndexStatisticsModel
    pixel_counts: PixelCounts
    metadata: dict[str, Any]


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field analytics backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Field analytics storage is not available in this environment."
        ) from exc


async def _get_plot_or_404(plot_id: str) -> dict[str, Any]:
    plot = await _run_blocking(plots_repo.get_plot, plot_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


def _is_eos_ready() -> bool:
    mode = (settings.provider_mode or "disabled").strip().lower()
    return bool(settings.eos_api_key.strip()) and settings.eos_enabled and mode in {"eos", "hybrid"}


def _default_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=180), today


def _validate_range(date_start: date, date_end: date) -> None:
    if date_start > date_end:
        raise bad_request("startDate must be on or before endDate.", code="INVALID_DATE_RANGE")
    if (date_end - date_start).days > MAX_TREND_DAYS:
        raise bad_request(
            "Trend ranges are limited to 365 days.",
            code="DATE_RANGE_TOO_LARGE",
            maxDays=MAX_TREND_DAYS,
        )


def _normalize_index(index_type: str | None) -> str:
    return (index_type or DEFAULT_INDEX).strip().upper()


def _field_statistics(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
    cloud_mask: CloudMaskOptions,
) -> FieldStatisticsResponse:
    computed = compute_statistics(
        geometry=plot["geometry"],
        source_id=source_id,
        acquisition_date=acquisition_date,
        index_type=index_type,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
        excluded_scl_classes=native_scl_excluded_classes(cloud_mask),
    )
    metadata = dict(computed["metadata"])
    metadata.update(
        {
            "provider": "native",
            "scope": "field",
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": cloud_mask_mapping(cloud_mask).model_dump(by_alias=True),
        }
    )
    return FieldStatisticsResponse(
        plot_id=plot_id,
        index_type=computed["indexType"],
        source_id=computed["sourceId"],
        acquisition_date=computed["acquisitionDate"],
        cloud_mask=cloud_mask,
        statistics=IndexStatisticsModel(**computed["statistics"]),
        pixel_counts=PixelCounts(**computed["pixelCounts"]),
        metadata=metadata,
    )


def _trend_point_from_stats(result: FieldStatisticsResponse) -> FieldTrendPoint:
    metadata = result.metadata
    return FieldTrendPoint(
        acquisition_date=date.fromisoformat(result.acquisition_date),
        scene_id=str(metadata.get("itemId")) if metadata.get("itemId") else None,
        mean=result.statistics.mean,
        min=result.statistics.min,
        max=result.statistics.max,
        stddev=result.statistics.stddev,
        valid_pixel_percent=result.statistics.validPixelPercent,
        cloud_masked_percent=result.statistics.cloudMaskedPercent,
        coverage_percent=result.statistics.coveragePercent,
        metrics_provisional=False,
    )


def _native_trend_response(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    date_start: date,
    date_end: date,
    cloud_mask: CloudMaskOptions,
    reason: str | None = None,
) -> FieldTrendResponse:
    supported = catalog.supported_indices(source_id)
    if index_type not in supported:
        raise bad_request(
            f"Unsupported index '{index_type}' for source '{source_id}'.",
            code="UNSUPPORTED_INDEX",
            sourceId=source_id,
            indexType=index_type,
            supported=supported,
        )
    dates = [
        item
        for item in catalog.list_dates(source_id)
        if date_start <= date.fromisoformat(item["acquisitionDate"]) <= date_end
    ]
    points: list[FieldTrendPoint] = []
    for item in sorted(dates, key=lambda entry: entry["acquisitionDate"]):
        acquisition_date = item["acquisitionDate"]
        try:
            stats = _field_statistics(
                plot_id=plot_id,
                plot=plot,
                source_id=source_id,
                acquisition_date=acquisition_date,
                index_type=index_type,
                cloud_mask=cloud_mask,
            )
            points.append(_trend_point_from_stats(stats))
        except AkashaError as exc:
            points.append(
                FieldTrendPoint(
                    acquisition_date=date.fromisoformat(acquisition_date),
                    metrics_provisional=True,
                    unavailable_reason=exc.message,
                )
            )

    index_def = get_index(index_type)
    return FieldTrendResponse(
        plot_id=plot_id,
        provider="native",
        scope="native_fallback",
        source_id=source_id,
        index_type=index_type,
        start_date=date_start,
        end_date=date_end,
        points=points,
        fallback_reason=reason,
        metadata={
            "formula": index_def.formula,
            "bands": list(index_def.required_bands),
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": cloud_mask_mapping(cloud_mask).model_dump(by_alias=True),
            "rangeLimitDays": MAX_TREND_DAYS,
        },
    )


def _eos_trend_response(
    *,
    plot_id: str,
    external_field_id: str,
    index_type: str,
    date_start: date,
    date_end: date,
    cloud_mask: CloudMaskOptions,
) -> FieldTrendResponse:
    provider = EosAnalyticsProvider()
    request = provider.create_trend_request(
        external_field_id,
        date_start,
        date_end,
        index=index_type,
        data_source="S2",
        cloud_mask=cloud_mask,
    )
    raw_points = (
        provider.get_trend_result(external_field_id, request.request_id, index=index_type)
        if request.request_id
        else []
    )
    points = [
        FieldTrendPoint(
            acquisition_date=point.acquisition_date,
            scene_id=point.scene_id,
            view_id=point.view_id,
            mean=point.mean,
            min=point.minimum,
            max=point.maximum,
            stddev=point.stddev,
            cloud_percent=point.cloud_percent,
            cloud_masked_percent=point.cloud_percent,
            metrics_provisional=False,
        )
        for point in raw_points
    ]
    index_def = get_index(index_type)
    return FieldTrendResponse(
        plot_id=plot_id,
        provider="eos",
        scope="field",
        source_id="sentinel-2-l2a",
        index_type=index_type,
        start_date=date_start,
        end_date=date_end,
        points=points,
        metadata={
            "formula": index_def.formula,
            "bands": list(index_def.required_bands),
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": cloud_mask_mapping(cloud_mask).model_dump(by_alias=True),
            "requestStatus": request.status,
        },
    )


@router.post(
    "/fields/{plot_id}/indices/statistics",
    response_model=FieldStatisticsResponse,
    response_model_by_alias=True,
)
async def post_field_index_statistics(
    plot_id: str,
    request: Request,
    payload: FieldStatisticsRequest = Body(...),
) -> FieldStatisticsResponse:
    _enforce_index_rate_limit(request)
    plot = await _get_plot_or_404(plot_id)
    index_type = _normalize_index(payload.index_type)

    def _compute() -> FieldStatisticsResponse:
        return _field_statistics(
            plot_id=plot_id,
            plot=plot,
            source_id=payload.source_id,
            acquisition_date=payload.acquisition_date,
            index_type=index_type,
            cloud_mask=payload.cloud_mask,
        )

    try:
        return await asyncio.wait_for(
            _run_blocking(_compute),
            timeout=settings.index_request_timeout_seconds,
        )
    except TimeoutError as exc:
        from .raster.errors import index_timeout

        raise index_timeout(
            "Index-statistics request exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
            timeoutSeconds=settings.index_request_timeout_seconds,
        ) from exc


@router.get(
    "/fields/{plot_id}/analytics/trend",
    response_model=FieldTrendResponse,
    response_model_by_alias=True,
)
async def get_field_analytics_trend(
    plot_id: str,
    indexType: str = Query(default=DEFAULT_INDEX),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    provider: ProviderChoice = "auto",
    sourceId: str = Query(default="sentinel-2-l2a"),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
) -> FieldTrendResponse:
    default_start, default_end = _default_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_range(date_start, date_end)

    index_type = _normalize_index(indexType)
    plot = await _get_plot_or_404(plot_id)
    cloud_mask = CloudMaskOptions(
        clouds=clouds,
        cloud_shadows=cloudShadows,
        cirrus=cirrus,
    )
    external_field_id = plot.get("externalFieldId")

    if provider == "native":
        return await _run_blocking(
            _native_trend_response,
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            index_type=index_type,
            date_start=date_start,
            date_end=date_end,
            cloud_mask=cloud_mask,
            reason="Native Akasha masked-raster trend fallback is in use.",
        )

    if provider == "eos" and not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before loading provider analytics.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )

    if provider == "eos" and not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "EOS provider is not available.",
            503,
            {"provider": "eos"},
        )

    can_use_eos = bool(external_field_id) and _is_eos_ready() and index_type in PROVIDER_INDEX_TYPES
    if provider == "auto" and not can_use_eos:
        return await _run_blocking(
            _native_trend_response,
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            index_type=index_type,
            date_start=date_start,
            date_end=date_end,
            cloud_mask=cloud_mask,
            reason=(
                "Selected field is not synced to the configured provider."
                if not external_field_id
                else "EOS provider is not available for this trend request."
            ),
        )

    return await _run_blocking(
        _eos_trend_response,
        plot_id=plot_id,
        external_field_id=str(external_field_id),
        index_type=index_type,
        date_start=date_start,
        date_end=date_end,
        cloud_mask=cloud_mask,
    )
