"""Selected-field native analytics routes."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import math
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from ..api_models import CloudMaskOptions, FieldTrendPoint, FieldTrendResponse
from ..auth import CurrentUser, get_current_team, get_current_user
from ..cloud_mask import source_cloud_mask_mapping, source_excluded_mask_classes
from ..config import settings
from ..ingestion_adapters import field_index_to_statistics_response, field_index_to_trend_point
from ..ingestion_client import (
    FIELD_DATES_MAX_BATCH_SIZE,
    FIELD_DATES_MAX_CLOUD_PERCENTAGE,
    fetch_signed_ingestion_binary,
    get_readiness,
    request_field_dates,
    request_field_index,
    request_field_index_point,
    request_field_sar,
)
from ..raster import catalog_resolver as catalog
from ..raster import tiles
from ..raster.errors import (
    AkashaError,
    bad_request,
    index_timeout,
    not_found,
    plots_backend_unavailable,
    upstream_error,
)
from ..raster.geo_validate import validate_polygon
from ..raster.indices import DEFAULT_INDEX, get_index
from ..raster.models import IndexStatisticsModel, PixelCounts
from ..raster.raster_reader import read_index_windows
from ..raster.service import (
    _candidate_assets_for_geometry,
    _excluded_mask_classes_for_assets,
    _index_band_positions,
    compute_statistics,
)
from ..raster.statistics_core import MASK_NODATA_CLASS, correct_reflectance, evaluate_index_values
from ..repositories import fields_repo
from ..routers.product_router import (
    _enforce_index_rate_limit,
    _filter_source_dates,
    _is_pipeline_source,
    _natural_dates,
    _pipeline_bridge_enabled,
    _pipeline_dates,
    _requires_ingestion_pipeline,
    _uses_natural_pipeline,
)
from ..schemas.analytics import FieldStatisticsRequest, FieldStatisticsResponse

logger = logging.getLogger("akasha.api.field_analytics")

router = APIRouter(
    prefix="/api",
    tags=["field-analytics"],
    dependencies=[Depends(get_current_team)],
)

MAX_TREND_DAYS = 365
EOS04_SOURCE_ID = "eos-04-sar-mrs-l2b"


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


async def _run_blocking_cancellable(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call, abandon_on_cancel=True)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field analytics backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Field analytics storage is not available in this environment."
        ) from exc


async def _get_field_or_404(field_id: str, user_id: str) -> dict[str, Any]:
    field = await _run_blocking(fields_repo.get_field, field_id, user_id)
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


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


def _validate_cloud_cover(value: float | None) -> None:
    if value is None:
        return
    if value < 0 or value > 100:
        raise bad_request(
            "maxCloudCoverInAoi must be between 0 and 100.",
            code="INVALID_CLOUD_COVER",
            maxCloudCoverInAoi=value,
        )


def _normalize_index(index_type: str | None) -> str:
    return (index_type or DEFAULT_INDEX).strip().upper()


def _uses_pipeline(source_id: str) -> bool:
    return _requires_ingestion_pipeline(source_id) or (
        _is_pipeline_source(source_id) and _pipeline_bridge_enabled()
    )


def _ensure_pipeline_index_supported(source_id: str, index_type: str) -> None:
    supported = catalog.supported_indices(source_id)
    if index_type in supported:
        return
    raise bad_request(
        f"Unsupported index '{index_type}' for source '{source_id}'.",
        code="UNSUPPORTED_INDEX",
        sourceId=source_id,
        indexType=index_type,
        supported=supported,
    )


def _pipeline_trend_max_dates() -> int:
    return max(1, settings.ingestion_trend_max_dates)


def _pipeline_trend_timeout_budget() -> float:
    return max(5.0, min(float(settings.index_request_timeout_seconds), 45.0))


def _pipeline_per_date_timeout(max_dates: int) -> float:
    budget = _pipeline_trend_timeout_budget()
    return max(1.0, min(float(settings.ingestion_request_timeout_seconds), budget / max_dates))


def _readiness_dates(
    *,
    source_id: str,
    timeout_seconds: float | None = None,
) -> list[date]:
    try:
        readiness = get_readiness(
            settings,
            source_id=source_id,
            aoi_id=settings.ingestion_aoi_id,
            timeout_seconds=timeout_seconds,
        )
    except AkashaError as exc:
        if exc.code == "INGESTION_API_UNCONFIGURED":
            raise upstream_error(
                "Standalone ingestion readiness is not configured.",
                code="INGESTION_READINESS_UNAVAILABLE",
                sourceId=source_id,
            ) from exc
        raise
    except Exception as exc:  # noqa: BLE001
        raise upstream_error(
            "Standalone ingestion readiness is unreachable.",
            code="INGESTION_API_UNREACHABLE",
            sourceId=source_id,
        ) from exc
    if not readiness:
        raise upstream_error(
            "Standalone ingestion readiness is unavailable.",
            code="INGESTION_READINESS_UNAVAILABLE",
            sourceId=source_id,
        )

    parsed_dates: list[date] = []
    for value in readiness.get("availableDates") or []:
        try:
            parsed_dates.append(date.fromisoformat(str(value)))
        except ValueError:
            continue
    if not parsed_dates:
        raise upstream_error(
            "Standalone ingestion readiness has no available dates.",
            code="INGESTION_READINESS_UNAVAILABLE",
            sourceId=source_id,
        )
    return sorted(set(parsed_dates))


def _pipeline_acquisition_date(
    *,
    source_id: str,
    requested_date: str | None,
    timeout_seconds: float | None = None,
) -> str:
    if requested_date:
        return requested_date
    return _readiness_dates(source_id=source_id, timeout_seconds=timeout_seconds)[-1].isoformat()


def _pipeline_statistics_response(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
    cloud_mask: CloudMaskOptions,
) -> FieldStatisticsResponse:
    _ensure_pipeline_index_supported(source_id, index_type)
    selected_date = _pipeline_acquisition_date(
        source_id=source_id,
        requested_date=acquisition_date,
        timeout_seconds=min(float(settings.ingestion_request_timeout_seconds), 5.0),
    )
    result = request_field_index(
        settings,
        geometry=plot["geometry"],
        field_id=plot_id,
        source_id=source_id,
        index_type=index_type,
        acquisition_date=selected_date,
        max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent),
    )
    return field_index_to_statistics_response(
        result,
        plot_id=plot_id,
        source_id=source_id,
        index_type=index_type,
        cloud_mask=cloud_mask,
    )


def _field_dates_response(
    *,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    start_date: date | None,
    end_date: date | None,
    lookback_days: int | None,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None

    def remaining_timeout() -> float:
        remaining_seconds = (
            max(0.0, deadline - time.monotonic())
            if deadline is not None
            else float(settings.index_request_timeout_seconds)
        )
        if remaining_seconds <= 0:
            raise index_timeout(
                "Field-date availability exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
                timeoutSeconds=timeout_seconds,
            )
        return remaining_seconds

    pipeline_dates = (
        _pipeline_dates(source_id, timeout_seconds=remaining_timeout())
        if _uses_pipeline(source_id)
        else None
    )
    source_dates = pipeline_dates if pipeline_dates is not None else catalog.list_dates(source_id)
    windowed_dates = _filter_source_dates(
        source_dates,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
    )
    if not windowed_dates or not _uses_pipeline(source_id):
        return windowed_dates

    _ensure_pipeline_index_supported(source_id, index_type)
    acquisition_dates = [
        str(item["acquisitionDate"]) for item in windowed_dates if item.get("acquisitionDate")
    ]
    availability_dates: list[dict[str, Any]] = []
    for offset in range(0, len(acquisition_dates), FIELD_DATES_MAX_BATCH_SIZE):
        availability = request_field_dates(
            settings,
            geometry=plot["geometry"],
            source_id=source_id,
            index_type=index_type,
            acquisition_dates=acquisition_dates[offset : offset + FIELD_DATES_MAX_BATCH_SIZE],
            max_cloud_percentage=FIELD_DATES_MAX_CLOUD_PERCENTAGE,
            timeout_seconds=remaining_timeout(),
        )
        availability_dates.extend(availability.get("dates", []))
    by_date = {
        str(item.get("acquisitionDate")): item
        for item in availability_dates
        if item.get("available") is True
    }
    filtered: list[dict[str, Any]] = []
    for item in windowed_dates:
        field_date = by_date.get(str(item.get("acquisitionDate")))
        if field_date is None:
            continue
        usable = field_date.get("usablePixelPercentage")
        cloud_percentage = field_date.get("cloudPercentage")
        field_coverage = field_date.get("fieldCoveragePercentage")
        shadow_percentage = field_date.get("shadowPercentage")
        obscured_percentage = field_date.get("obscuredPercentage")
        filtered.append(
            {
                **item,
                "usablePixelPercent": usable,
                "cloudMaskedPercent": cloud_percentage,
                "coveragePercent": field_coverage,
                "shadowPercent": shadow_percentage,
                "obscuredPercent": obscured_percentage,
                "isLatestUsable": False,
            }
        )
    if filtered:
        newest = max(str(item["acquisitionDate"]) for item in filtered)
        for item in filtered:
            item["isLatestUsable"] = item["acquisitionDate"] == newest
    return filtered


def _field_monitoring_evidence(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    target_date: date,
    optical_stale_days: int,
    sar_window_days: int,
    include_radar: bool,
) -> dict[str, Any]:
    source = catalog.get_source(source_id)
    if source.get("kind") != "optical":
        raise bad_request(
            "Field monitoring evidence requires a primary optical source.",
            code="OPTICAL_SOURCE_REQUIRED",
            sourceId=source_id,
        )
    if index_type not in catalog.supported_indices(source_id):
        raise bad_request(
            f"Unsupported index '{index_type}' for source '{source_id}'.",
            code="UNSUPPORTED_INDEX",
            sourceId=source_id,
            indexType=index_type,
        )
    start_date = target_date - timedelta(days=max(31, optical_stale_days * 3))
    field_dates = _field_dates_response(
        plot=plot,
        source_id=source_id,
        index_type=index_type,
        start_date=start_date,
        end_date=target_date,
        lookback_days=None,
        timeout_seconds=float(settings.index_request_timeout_seconds),
    )
    global_dates = (
        _pipeline_dates(
            source_id, timeout_seconds=float(settings.ingestion_request_timeout_seconds)
        )
        if _uses_pipeline(source_id)
        else catalog.list_dates(source_id)
    ) or []
    candidate_dates = sorted(
        date.fromisoformat(str(item["acquisitionDate"]))
        for item in global_dates
        if item.get("acquisitionDate")
        and start_date <= date.fromisoformat(str(item["acquisitionDate"])) <= target_date
    )
    qualifying_dates = sorted(
        date.fromisoformat(str(item["acquisitionDate"]))
        for item in field_dates
        if item.get("acquisitionDate")
    )
    latest_candidate = candidate_dates[-1] if candidate_dates else None
    latest_qualifying = qualifying_dates[-1] if qualifying_dates else None
    qualifying_age = (target_date - latest_qualifying).days if latest_qualifying else None

    if (
        latest_qualifying is not None
        and qualifying_age is not None
        and qualifying_age <= optical_stale_days
    ):
        optical_status = "usable"
        trigger_reason = None
    elif latest_candidate is not None and (
        latest_qualifying is None or latest_candidate > latest_qualifying
    ):
        optical_status = "quality_limited"
        trigger_reason = (
            "The newest optical observation did not meet exact-field quality thresholds."
        )
    elif latest_qualifying is not None:
        optical_status = "stale"
        trigger_reason = "The latest qualifying optical observation is stale."
    else:
        optical_status = "unavailable"
        trigger_reason = "No qualifying optical observation is available for this field."

    should_request_radar = include_radar or optical_status != "usable"
    radar: dict[str, Any] = {
        "status": "NOT_REQUESTED",
        "sourceId": EOS04_SOURCE_ID,
        "triggered": should_request_radar,
        "triggerReason": trigger_reason if should_request_radar else None,
    }
    if should_request_radar and not settings.eos04_field_support_enabled:
        radar.update(
            status="DISABLED",
            reason="EOS-04 field support is not enabled in this environment.",
        )
    elif should_request_radar:
        include_temporal = (
            settings.eos04_temporal_change_enabled
            or settings.eos04_temporal_shadow_enabled
        )
        try:
            result = request_field_sar(
                settings,
                geometry=plot["geometry"],
                field_id=plot_id,
                target_date=target_date.isoformat(),
                window_days=sar_window_days,
                include_history=include_temporal,
                history_lookback_days=settings.eos04_temporal_lookback_days,
                maximum_history_observations=settings.eos04_temporal_max_observations,
                minimum_baseline_observations=(
                    settings.eos04_temporal_min_baseline_observations
                ),
                timeout_seconds=float(settings.ingestion_request_timeout_seconds),
            )
        except AkashaError as exc:
            radar.update(status="UNAVAILABLE", reason=exc.message, reasonCode=exc.code)
        else:
            result.pop("overlayUrl", None)
            result.pop("queryId", None)
            if include_temporal and not settings.eos04_temporal_change_enabled:
                for field in ("comparison", "history", "change", "baseline"):
                    result.pop(field, None)
            radar.update(result)
            if result.get("status") == "AVAILABLE":
                radar["overlayUrl"] = (
                    f"/api/fields/{plot_id}/sar/overlay.png"
                    f"?targetDate={target_date.isoformat()}&windowDays={sar_window_days}"
                )
            radar["triggered"] = True
            radar["triggerReason"] = trigger_reason

    return {
        "fieldId": plot_id,
        "targetDate": target_date.isoformat(),
        "optical": {
            "status": optical_status,
            "sourceId": source_id,
            "indexType": index_type,
            "latestCandidateDate": latest_candidate.isoformat() if latest_candidate else None,
            "latestQualifyingDate": latest_qualifying.isoformat() if latest_qualifying else None,
            "ageDays": qualifying_age,
            "staleAfterDays": optical_stale_days,
            "requirements": {
                "minimumCoveragePercent": 95,
                "minimumUsablePixelPercent": 80,
                "maximumCombinedCloudShadowPercent": 20,
            },
        },
        "radar": radar,
    }


def _provisional_trend_point(requested_date: date, reason: str) -> FieldTrendPoint:
    return FieldTrendPoint(
        acquisition_date=requested_date,
        metrics_provisional=True,
        unavailable_reason=reason,
    )


def _pipeline_trend_response(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    date_start: date,
    date_end: date,
    cloud_mask: CloudMaskOptions,
    max_cloud_cover_in_aoi: float | None = None,
) -> FieldTrendResponse:
    _ensure_pipeline_index_supported(source_id, index_type)

    max_dates = _pipeline_trend_max_dates()
    per_date_timeout = _pipeline_per_date_timeout(max_dates)
    readiness_dates = _readiness_dates(source_id=source_id, timeout_seconds=per_date_timeout)
    window_dates = [value for value in readiness_dates if date_start <= value <= date_end]
    selected_dates = window_dates[-max_dates:]
    if not selected_dates:
        raise upstream_error(
            "Standalone ingestion readiness has no dates in the requested range.",
            code="INGESTION_TREND_UNAVAILABLE",
            sourceId=source_id,
            startDate=date_start.isoformat(),
            endDate=date_end.isoformat(),
        )

    points_by_date: dict[date, FieldTrendPoint] = {}
    for requested_date in selected_dates:
        try:
            result = request_field_index(
                settings,
                geometry=plot["geometry"],
                field_id=plot_id,
                source_id=source_id,
                index_type=index_type,
                acquisition_date=requested_date.isoformat(),
                max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent),
                timeout_seconds=per_date_timeout,
            )
            point = field_index_to_trend_point(result)
            points_by_date.setdefault(point.acquisition_date, point)
        except AkashaError as exc:
            reason = str(exc.details.get("reason") or exc.message)
            points_by_date.setdefault(
                requested_date,
                _provisional_trend_point(requested_date, reason),
            )
        except Exception:  # noqa: BLE001
            points_by_date.setdefault(
                requested_date,
                _provisional_trend_point(
                    requested_date,
                    "Standalone ingestion field-index request failed.",
                ),
            )

    points = [points_by_date[key] for key in sorted(points_by_date)]
    if not points:
        raise upstream_error(
            "Standalone ingestion trend is unavailable.",
            code="INGESTION_TREND_UNAVAILABLE",
            sourceId=source_id,
        )

    index_def = get_index(index_type)
    return FieldTrendResponse(
        plot_id=plot_id,
        provider="pipeline",
        scope="pipeline",
        source_id=source_id,
        index_type=index_type,
        start_date=date_start,
        end_date=date_end,
        points=points,
        metadata={
            "provider": "pipeline",
            "scope": "pipeline",
            "formula": index_def.formula,
            "spectralRoles": list(index_def.required_roles),
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "rangeLimitDays": MAX_TREND_DAYS,
            "maxCloudCoverInAoi": max_cloud_cover_in_aoi,
            "maxDates": max_dates,
            "perDateTimeoutSeconds": per_date_timeout,
            "sideEffect": "field-index requests create ingestion query records and tile layers.",
        },
    )


def _pipeline_point_response(
    *,
    plot_id: str,
    source_id: str,
    acquisition_date: str,
    index_type: str,
    lng: float,
    lat: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    return {
        "plotId": plot_id,
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "indexType": index_type,
        "lng": float(result.get("lng", lng)),
        "lat": float(result.get("lat", lat)),
        "value": result.get("value"),
        "masked": bool(result.get("masked", result.get("value") is None)),
        "maskClass": result.get("maskClass"),
        "resolvedSourceId": source_id,
        "resolutionMeters": source.get("resolutionMeters") or source.get("displayMeters") or 10,
        "enhanced": False,
        "basisDate": None,
        "provenanceNote": "Standalone ingestion pipeline point lookup.",
    }


def _field_statistics(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
    cloud_mask: CloudMaskOptions,
    prefer_high_res: bool = True,
) -> FieldStatisticsResponse:
    resolution = catalog.resolve_best_resolution_source(
        primary_source_id=source_id,
        index_type=index_type,
        field_geometry=plot["geometry"],
        acquisition_date=acquisition_date or "",
        prefer_high_res=prefer_high_res,
    )
    effective_source_id = resolution.source_id
    effective_date = resolution.basis_date if resolution.enhanced else acquisition_date

    source = catalog.get_source(effective_source_id)
    mask_mapping = source_cloud_mask_mapping(source, cloud_mask)
    computed = compute_statistics(
        geometry=plot["geometry"],
        source_id=effective_source_id,
        acquisition_date=effective_date,
        index_type=index_type,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
        excluded_mask_classes=source_excluded_mask_classes(source, cloud_mask),
    )
    metadata = dict(computed["metadata"])
    metadata.update(
        {
            "provider": "native",
            "scope": "field",
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": mask_mapping.model_dump(by_alias=True),
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
        sar_support=computed.get("sarSupport"),
        resolved_source_id=resolution.source_id,
        resolution_meters=resolution.resolution_meters,
        enhanced=resolution.enhanced,
        basis_date=resolution.basis_date,
        provenance_note=resolution.provenance_note,
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
        cloud_percent=result.statistics.cloudMaskedPercent,
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
    max_cloud_cover_in_aoi: float | None = None,
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
    cloud_filtered_scene_count = 0
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
                prefer_high_res=False,
            )
            point = _trend_point_from_stats(stats)
            if (
                max_cloud_cover_in_aoi is not None
                and point.cloud_percent is not None
                and point.cloud_percent > max_cloud_cover_in_aoi
            ):
                cloud_filtered_scene_count += 1
                continue
            points.append(point)
        except AkashaError as exc:
            points.append(
                FieldTrendPoint(
                    acquisition_date=date.fromisoformat(acquisition_date),
                    metrics_provisional=True,
                    unavailable_reason=exc.message,
                )
            )

    index_def = get_index(index_type)
    source = catalog.get_source(source_id)
    return FieldTrendResponse(
        plot_id=plot_id,
        source_id=source_id,
        index_type=index_type,
        start_date=date_start,
        end_date=date_end,
        points=points,
        fallback_reason=reason,
        metadata={
            "formula": index_def.formula,
            "spectralRoles": list(index_def.required_roles),
            "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": source_cloud_mask_mapping(source, cloud_mask).model_dump(
                by_alias=True
            ),
            "rangeLimitDays": MAX_TREND_DAYS,
            "maxCloudCoverInAoi": max_cloud_cover_in_aoi,
            "cloudFilteredSceneCount": cloud_filtered_scene_count,
            "highResEnhancementNote": (
                "Trend uses the primary source only for radiometric continuity. "
                "High-resolution LISS-4 enhancement (5.8 m composite grid) is available for "
                "single-date overlay, statistics, and point queries."
            ),
        },
    )


def _compute_index_window(
    *,
    assets: dict[str, Any],
    geometry: dict[str, Any],
    index_type: str,
) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    import numpy as np

    index_def = get_index(index_type)
    pos_a, pos_b, _resolved_bands = _index_band_positions(assets, index_def, index_type)
    read = read_index_windows(
        analytic_href=assets["analyticHref"],
        mask_href=assets["maskHref"],
        geometry=geometry,
        positions=[pos_a, pos_b],
    )
    if not read.intersects:
        return read, None, None, None, None, None, None, None

    band_a = np.asarray(read.band_arrays[pos_a])
    band_b = np.asarray(read.band_arrays[pos_b])
    geom = np.asarray(read.geometry_mask, dtype=bool)
    source_mask = np.asarray(read.mask)

    if str(assets.get("nodataPolicy") or "selected_band_or_mask") == "mask_only":
        analytic_nodata = np.zeros(band_a.shape, dtype=bool)
    else:
        analytic_nodata = (band_a == read.nodata) | (band_b == read.nodata)

    mask_nodata = source_mask == MASK_NODATA_CLASS
    nodata_mask = geom & (analytic_nodata | mask_nodata)
    coverage_mask = geom & ~nodata_mask

    excluded = _excluded_mask_classes_for_assets(assets=assets, override=None)
    excluded_within_coverage = tuple(cls for cls in excluded if cls != MASK_NODATA_CLASS)
    masked_within_coverage = coverage_mask & np.isin(source_mask, excluded_within_coverage)
    valid_mask = coverage_mask & ~masked_within_coverage

    # Per-pixel masks that DO NOT pre-clip to the polygon. The crisp polygon clip
    # is applied at the fine reprojected output grid for the overlay so the edge
    # hugs the boundary instead of stair-stepping at the native pixel size.
    data_nodata = analytic_nodata | mask_nodata
    data_masked = ~data_nodata & np.isin(source_mask, excluded_within_coverage)
    data_valid = ~data_nodata & ~data_masked

    scale = float(assets.get("scale", 0.0001))
    offset = float(assets.get("offset", 0.0))
    band_a_ref = correct_reflectance(band_a, scale, offset)
    band_b_ref = correct_reflectance(band_b, scale, offset)
    values, _good = evaluate_index_values(index_def.formula_kind, band_a_ref, band_b_ref)

    return (
        read,
        values,
        valid_mask,
        nodata_mask | masked_within_coverage,
        source_mask,
        geom,
        data_valid,
        data_masked,
    )


def _resolve_single_field_asset(
    *,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str,
    index_type: str,
) -> dict[str, Any]:
    supported = catalog.supported_indices(source_id)
    if index_type not in supported:
        raise bad_request(
            f"Unsupported index '{index_type}' for source '{source_id}'.",
            code="UNSUPPORTED_INDEX",
            sourceId=source_id,
            indexType=index_type,
            supported=supported,
        )
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    geom_facts = validate_polygon(
        plot["geometry"],
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
    )
    candidate_assets = _candidate_assets_for_geometry(
        assets_for_date=assets_for_date,
        geometry_bounds=geom_facts.get("bounds"),
    )
    if len(candidate_assets) != 1:
        raise bad_request(
            "Field index overlay requires exactly one resolved analytic asset.",
            code="INDEX_OVERLAY_ASSET_UNAVAILABLE",
            sceneCount=len(candidate_assets),
        )
    return candidate_assets[0]


def _index_overlay_response(
    *,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str,
    index_type: str,
    prefer_high_res: bool = True,
) -> tuple[bytes, str, dict[str, str]]:
    resolution = catalog.resolve_best_resolution_source(
        primary_source_id=source_id,
        index_type=index_type,
        field_geometry=plot["geometry"],
        acquisition_date=acquisition_date,
        prefer_high_res=prefer_high_res,
    )
    effective_source_id = resolution.source_id
    effective_date = resolution.basis_date if resolution.enhanced else acquisition_date

    assets = _resolve_single_field_asset(
        plot=plot,
        source_id=effective_source_id,
        acquisition_date=effective_date,
        index_type=index_type,
    )
    (
        read,
        values,
        valid_mask,
        masked_mask,
        _source_mask,
        _geom,
        data_valid,
        data_masked,
    ) = _compute_index_window(
        assets=assets,
        geometry=plot["geometry"],
        index_type=index_type,
    )
    lo, hi = tiles.overlay_display_range(index_type)
    headers: dict[str, str] = {"X-Akasha-Overlay-Stretch": f"{lo},{hi}"}
    # Provenance headers
    headers["X-Akasha-Resolved-Source"] = resolution.source_id
    if resolution.resolution_meters is not None:
        headers["X-Akasha-Resolved-Resolution"] = str(resolution.resolution_meters)
    headers["X-Akasha-Enhanced"] = "true" if resolution.enhanced else "false"
    if resolution.basis_date:
        headers["X-Akasha-Basis-Date"] = resolution.basis_date

    if not read.intersects:
        footprint_corners = getattr(read, "footprint_corners", None)
        if footprint_corners:
            headers["X-Akasha-Overlay-Corners"] = json.dumps(
                footprint_corners, separators=(",", ":")
            )
        return tiles.TRANSPARENT_PNG, "image/png", headers

    window_transform = getattr(read, "window_transform", None)
    window_crs = getattr(read, "crs", None)
    if window_transform is not None and window_crs is not None:
        # EOS-style pixel-perfect path: reproject to north-up Web Mercator,
        # supersample for a smooth heatmap, and clip crisply to the polygon.
        rgba, corners = tiles.reproject_index_overlay_web_mercator(
            index_type=index_type,
            index_values=values,
            data_valid=data_valid,
            data_masked=data_masked,
            src_transform=window_transform,
            src_crs=window_crs,
            geometry=plot["geometry"],
        )
        headers["X-Akasha-Overlay-Corners"] = json.dumps(corners, separators=(",", ":"))
        return tiles.encode_rgba_png(rgba), "image/png", headers

    # Fallback (no georeferencing metadata, e.g. synthetic tests): native render.
    footprint_corners = getattr(read, "footprint_corners", None)
    if footprint_corners:
        headers["X-Akasha-Overlay-Corners"] = json.dumps(footprint_corners, separators=(",", ":"))
    body, content_type = tiles.render_field_index_overlay_png(
        index_type=index_type,
        index_values=values,
        valid_mask=valid_mask,
        masked_mask=masked_mask,
    )
    return body, content_type, headers


def _pipeline_index_overlay_response(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str,
    index_type: str,
) -> tuple[bytes, str, dict[str, str]]:
    _ensure_pipeline_index_supported(source_id, index_type)
    result = request_field_index(
        settings,
        geometry=plot["geometry"],
        field_id=plot_id,
        source_id=source_id,
        index_type=index_type,
        acquisition_date=acquisition_date,
        max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent),
    )
    if result.get("status") != "AVAILABLE" or not result.get("overlayUrl"):
        raise bad_request(
            "Standalone ingestion overlay is unavailable for this field/date.",
            code="INGESTION_OVERLAY_UNAVAILABLE",
            sourceId=source_id,
            acquisitionDate=acquisition_date,
            reason=result.get("reason"),
        )
    body, content_type, upstream_headers = fetch_signed_ingestion_binary(
        settings,
        str(result["overlayUrl"]),
    )
    headers: dict[str, str] = {}
    for name in (
        "X-Akasha-Overlay-Corners",
        "X-Akasha-Overlay-Stretch",
    ):
        if upstream_headers.get(name):
            headers[name] = upstream_headers[name]
    headers["X-Akasha-Resolved-Source"] = source_id
    headers["X-Akasha-Resolved-Resolution"] = str(
        (result.get("resolution") or {}).get("displayMeters") or 10
    )
    headers["X-Akasha-Enhanced"] = "false"
    return body, content_type, headers


def _point_row_col(read: Any, lng: float, lat: float) -> tuple[int, int]:
    transform = getattr(read, "window_transform", None)
    crs = getattr(read, "crs", None)
    if transform is None or crs is None:
        return 0, 0
    from rasterio.warp import transform as transform_coords  # lazy

    xs, ys = transform_coords("EPSG:4326", crs, [lng], [lat])
    inv = ~transform
    col_f, row_f = inv * (xs[0], ys[0])
    return int(math.floor(row_f)), int(math.floor(col_f))


def _field_index_point_response(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str,
    index_type: str,
    lng: float,
    lat: float,
    prefer_high_res: bool = True,
) -> dict[str, Any]:
    import numpy as np

    resolution = catalog.resolve_best_resolution_source(
        primary_source_id=source_id,
        index_type=index_type,
        field_geometry=plot["geometry"],
        acquisition_date=acquisition_date,
        prefer_high_res=prefer_high_res,
    )
    effective_source_id = resolution.source_id
    effective_date = resolution.basis_date if resolution.enhanced else acquisition_date

    assets = _resolve_single_field_asset(
        plot=plot,
        source_id=effective_source_id,
        acquisition_date=effective_date,
        index_type=index_type,
    )
    read, values, valid_mask, masked_mask, source_mask, _geom, _dv, _dm = _compute_index_window(
        assets=assets,
        geometry=plot["geometry"],
        index_type=index_type,
    )

    base: dict[str, Any] = {
        "plotId": plot_id,
        "sourceId": effective_source_id,
        "acquisitionDate": effective_date,
        "indexType": index_type,
        "lng": lng,
        "lat": lat,
        "resolvedSourceId": resolution.source_id,
        "resolutionMeters": resolution.resolution_meters,
        "enhanced": resolution.enhanced,
        "basisDate": resolution.basis_date,
        "provenanceNote": resolution.provenance_note,
    }
    if not read.intersects or values is None:
        return {**base, "value": None, "masked": True, "maskClass": None}

    row, col = _point_row_col(read, lng, lat)
    if row < 0 or col < 0 or row >= values.shape[0] or col >= values.shape[1]:
        return {**base, "value": None, "masked": True, "maskClass": None}

    mask_class = int(np.asarray(source_mask)[row, col])
    is_valid = bool(np.asarray(valid_mask)[row, col])
    is_masked = bool(np.asarray(masked_mask)[row, col]) or not is_valid
    value = None
    if not is_masked and np.isfinite(values[row, col]):
        value = round(float(values[row, col]), 6)
    return {**base, "value": value, "masked": is_masked, "maskClass": mask_class}


@router.get("/fields/{plot_id}/dates")
async def get_field_dates(
    plot_id: str,
    request: Request,
    sourceId: str = Query(default=settings.default_source_id),
    indexType: str = Query(default=DEFAULT_INDEX),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    lookbackDays: int | None = Query(default=None, ge=1, le=366),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _enforce_index_rate_limit(request)
    plot = await _get_field_or_404(plot_id, user.id)
    if _uses_natural_pipeline(sourceId):
        try:
            natural_dates = await asyncio.wait_for(
                _run_blocking_cancellable(_natural_dates, sourceId),
                timeout=settings.index_request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise index_timeout(
                "Natural-source date availability exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
                timeoutSeconds=settings.index_request_timeout_seconds,
            ) from exc
        return _filter_source_dates(
            natural_dates or [],
            start_date=startDate,
            end_date=endDate,
            lookback_days=lookbackDays,
        )
    index_type = _normalize_index(indexType)
    try:
        return await asyncio.wait_for(
            _run_blocking_cancellable(
                _field_dates_response,
                plot=plot,
                source_id=sourceId,
                index_type=index_type,
                start_date=startDate,
                end_date=endDate,
                lookback_days=lookbackDays,
                timeout_seconds=float(settings.index_request_timeout_seconds),
            ),
            timeout=settings.index_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise index_timeout(
            "Field-date availability exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
            timeoutSeconds=settings.index_request_timeout_seconds,
        ) from exc


@router.get("/fields/{plot_id}/monitoring/evidence")
async def get_field_monitoring_evidence(
    plot_id: str,
    sourceId: str = Query(default=settings.default_source_id),
    indexType: str = Query(default=DEFAULT_INDEX),
    targetDate: date | None = Query(default=None),
    opticalStaleDays: int = Query(default=10, ge=1, le=31),
    sarWindowDays: int = Query(default=21, ge=1, le=31),
    includeRadar: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    plot = await _get_field_or_404(plot_id, user.id)
    normalized_index = _normalize_index(indexType)
    requested_date = targetDate or datetime.now(UTC).date()
    try:
        return await asyncio.wait_for(
            _run_blocking_cancellable(
                _field_monitoring_evidence,
                plot_id=plot_id,
                plot=plot,
                source_id=sourceId,
                index_type=normalized_index,
                target_date=requested_date,
                optical_stale_days=opticalStaleDays,
                sar_window_days=sarWindowDays,
                include_radar=includeRadar,
            ),
            timeout=settings.index_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise index_timeout(
            "Field monitoring evidence exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
            timeoutSeconds=settings.index_request_timeout_seconds,
        ) from exc


@router.get("/fields/{plot_id}/sar/overlay.png")
async def get_field_sar_overlay(
    plot_id: str,
    targetDate: date = Query(...),
    windowDays: int = Query(default=21, ge=1, le=31),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    if not settings.eos04_field_support_enabled:
        raise not_found("EOS-04 field support is not enabled.", code="EOS04_FIELD_SUPPORT_DISABLED")
    plot = await _get_field_or_404(plot_id, user.id)
    result = await _run_blocking(
        request_field_sar,
        settings,
        geometry=plot["geometry"],
        field_id=plot_id,
        target_date=targetDate.isoformat(),
        window_days=windowDays,
    )
    if result.get("status") != "AVAILABLE" or not result.get("overlayUrl"):
        raise not_found(
            "EOS-04 evidence is unavailable for this field and date.",
            code="EOS04_FIELD_EVIDENCE_UNAVAILABLE",
            reason=result.get("reason"),
        )
    body, content_type, upstream_headers = await _run_blocking(
        fetch_signed_ingestion_binary,
        settings,
        str(result["overlayUrl"]),
    )
    headers = {
        name: upstream_headers[name]
        for name in ("X-Akasha-Overlay-Corners", "X-Akasha-Overlay-Stretch")
        if upstream_headers.get(name)
    }
    headers["X-Akasha-Resolved-Source"] = EOS04_SOURCE_ID
    return Response(content=body, media_type=content_type, headers=headers)


@router.post(
    "/fields/{plot_id}/indices/statistics",
    response_model=FieldStatisticsResponse,
    response_model_by_alias=True,
)
async def post_field_index_statistics(
    plot_id: str,
    request: Request,
    payload: FieldStatisticsRequest = Body(...),
    user: CurrentUser = Depends(get_current_user),
) -> FieldStatisticsResponse:
    _enforce_index_rate_limit(request)
    plot = await _get_field_or_404(plot_id, user.id)
    index_type = _normalize_index(payload.index_type)

    if _uses_pipeline(payload.source_id):
        try:
            return await asyncio.wait_for(
                _run_blocking(
                    _pipeline_statistics_response,
                    plot_id=plot_id,
                    plot=plot,
                    source_id=payload.source_id,
                    acquisition_date=payload.acquisition_date,
                    index_type=index_type,
                    cloud_mask=payload.cloud_mask,
                ),
                timeout=settings.index_request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise index_timeout(
                "Pipeline index-statistics request exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
                timeoutSeconds=settings.index_request_timeout_seconds,
            ) from exc

    def _compute() -> FieldStatisticsResponse:
        return _field_statistics(
            plot_id=plot_id,
            plot=plot,
            source_id=payload.source_id,
            acquisition_date=payload.acquisition_date,
            index_type=index_type,
            cloud_mask=payload.cloud_mask,
            prefer_high_res=payload.prefer_high_res,
        )

    try:
        return await asyncio.wait_for(
            _run_blocking(_compute),
            timeout=settings.index_request_timeout_seconds,
        )
    except TimeoutError as exc:
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
    sourceId: str = Query(default=settings.default_source_id),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
    maxCloudCoverInAoi: float | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> FieldTrendResponse:
    default_start, default_end = _default_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_range(date_start, date_end)
    _validate_cloud_cover(maxCloudCoverInAoi)

    index_type = _normalize_index(indexType)
    plot = await _get_field_or_404(plot_id, user.id)
    cloud_mask = CloudMaskOptions(
        clouds=clouds,
        cloud_shadows=cloudShadows,
        cirrus=cirrus,
    )
    if _uses_pipeline(sourceId):
        try:
            return await asyncio.wait_for(
                _run_blocking(
                    _pipeline_trend_response,
                    plot_id=plot_id,
                    plot=plot,
                    source_id=sourceId,
                    index_type=index_type,
                    date_start=date_start,
                    date_end=date_end,
                    cloud_mask=cloud_mask,
                    max_cloud_cover_in_aoi=maxCloudCoverInAoi,
                ),
                timeout=_pipeline_trend_timeout_budget(),
            )
        except TimeoutError as exc:
            raise index_timeout(
                "Pipeline trend request exceeded its bounded timeout.",
                timeoutSeconds=_pipeline_trend_timeout_budget(),
            ) from exc

    return await _run_blocking(
        _native_trend_response,
        plot_id=plot_id,
        plot=plot,
        source_id=sourceId,
        index_type=index_type,
        date_start=date_start,
        date_end=date_end,
        cloud_mask=cloud_mask,
        max_cloud_cover_in_aoi=maxCloudCoverInAoi,
        reason="Native Akasha masked-raster trend is in use.",
    )


@router.get("/fields/{plot_id}/overlay/{index_type}.png")
async def get_field_index_overlay(
    plot_id: str,
    index_type: str,
    sourceId: str = Query(default=settings.default_source_id),
    acquisitionDate: str = Query(...),
    preferHighRes: bool = Query(default=True),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    plot = await _get_field_or_404(plot_id, user.id)
    normalized_index = _normalize_index(index_type)
    if _uses_pipeline(sourceId):
        body, content_type, headers = await _run_blocking(
            _pipeline_index_overlay_response,
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            acquisition_date=acquisitionDate,
            index_type=normalized_index,
        )
    else:
        body, content_type, headers = await _run_blocking(
            _index_overlay_response,
            plot=plot,
            source_id=sourceId,
            acquisition_date=acquisitionDate,
            index_type=normalized_index,
            prefer_high_res=preferHighRes,
        )
    return Response(content=body, media_type=content_type, headers=headers)


@router.get("/fields/{plot_id}/indices/point")
async def get_field_index_point(
    plot_id: str,
    sourceId: str = Query(default=settings.default_source_id),
    acquisitionDate: str = Query(...),
    indexType: str = Query(default=DEFAULT_INDEX),
    lng: float = Query(...),
    lat: float = Query(...),
    preferHighRes: bool = Query(default=True),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    plot = await _get_field_or_404(plot_id, user.id)
    normalized_index = _normalize_index(indexType)
    if _uses_pipeline(sourceId):
        _ensure_pipeline_index_supported(sourceId, normalized_index)
        try:
            result = await asyncio.wait_for(
                _run_blocking(
                    request_field_index_point,
                    settings,
                    geometry=plot["geometry"],
                    field_id=plot_id,
                    source_id=sourceId,
                    index_type=normalized_index,
                    acquisition_date=acquisitionDate,
                    lng=lng,
                    lat=lat,
                    max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent),
                ),
                timeout=settings.index_request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise index_timeout(
                "Pipeline point lookup exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
                timeoutSeconds=settings.index_request_timeout_seconds,
            ) from exc
        return _pipeline_point_response(
            plot_id=plot_id,
            source_id=sourceId,
            acquisition_date=acquisitionDate,
            index_type=normalized_index,
            lng=lng,
            lat=lat,
            result=result,
        )
    return await _run_blocking(
        _field_index_point_response,
        plot_id=plot_id,
        plot=plot,
        source_id=sourceId,
        acquisition_date=acquisitionDate,
        index_type=normalized_index,
        lng=lng,
        lat=lat,
        prefer_high_res=preferHighRes,
    )
