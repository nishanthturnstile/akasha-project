"""Selected-field native export routes."""
from __future__ import annotations

import csv
import functools
import logging
import re
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from ..api_models import CloudMaskOptions
from ..auth import CurrentUser, get_current_team, get_current_user
from ..cloud_mask import source_cloud_mask_mapping
from ..config import settings
from ..optical_cloud import DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT, optical_cloud_threshold
from ..raster import catalog_resolver as catalog
from ..raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
from ..raster.indices import DEFAULT_INDEX
from ..repositories import fields_repo
from ..routers.analytics_router import (
    _field_statistics,
    _native_trend_response,
    _normalize_index,
    _pipeline_statistics_response,
    _pipeline_trend_response,
    _uses_pipeline,
    _validate_range,
)

logger = logging.getLogger("akasha.api.field_exports")

router = APIRouter(
    prefix="/api",
    tags=["field-exports"],
    dependencies=[Depends(get_current_team)],
)

ExportFormat = Literal["geojson", "csv", "shp", "geotiff"]


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field export backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Field export storage is not available in this environment."
        ) from exc


async def _get_field_or_404(field_id: str, user_id: str) -> dict[str, Any]:
    field = await _run_blocking(fields_repo.get_field, field_id, user_id)
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or "field"


def _filename(plot: dict[str, Any], acquisition_date: date, index_type: str, suffix: str) -> str:
    name = _safe_filename(str(plot.get("name") or plot.get("id") or "field"))
    return f"{name}_{acquisition_date.isoformat()}_{index_type}.{suffix}"


def _disposition(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _required_acquisition_date(value: date | None) -> date:
    if value is None:
        raise bad_request(
            "acquisitionDate is required for selected-field exports.",
            code="MISSING_DATE",
        )
    return value


def _statistics_for_export(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: date,
    index_type: str,
    cloud_mask: CloudMaskOptions,
    optical_cloud_threshold_percent: int = DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT,
):
    if _uses_pipeline(source_id):
        return _pipeline_statistics_response(
            plot_id=plot_id,
            plot=plot,
            source_id=source_id,
            acquisition_date=acquisition_date.isoformat(),
            index_type=index_type,
            cloud_mask=cloud_mask,
            optical_cloud_threshold_percent=optical_cloud_threshold_percent,
        )
    return _field_statistics(
        plot_id=plot_id,
        plot=plot,
        source_id=source_id,
        acquisition_date=acquisition_date.isoformat(),
        index_type=index_type,
        cloud_mask=cloud_mask,
        optical_cloud_threshold_percent=optical_cloud_threshold_percent,
    )


def _index_csv_content(stats) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "plot_id",
            "source_id",
            "acquisition_date",
            "index_type",
            "min",
            "max",
            "mean",
            "stddev",
            "valid_pixel_percent",
            "cloud_masked_percent",
            "coverage_percent",
            "total_pixels",
            "valid_pixels",
            "masked_pixels",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "plot_id": stats.plot_id,
            "source_id": stats.source_id,
            "acquisition_date": stats.acquisition_date,
            "index_type": stats.index_type,
            "min": stats.statistics.min,
            "max": stats.statistics.max,
            "mean": stats.statistics.mean,
            "stddev": stats.statistics.stddev,
            "valid_pixel_percent": stats.statistics.validPixelPercent,
            "cloud_masked_percent": stats.statistics.cloudMaskedPercent,
            "coverage_percent": stats.statistics.coveragePercent,
            "total_pixels": stats.pixel_counts.totalPixels,
            "valid_pixels": stats.pixel_counts.validPixels,
            "masked_pixels": stats.pixel_counts.maskedPixels,
        }
    )
    return output.getvalue()


def _geojson_payload(plot: dict[str, Any], stats, cloud_mask: CloudMaskOptions) -> dict[str, Any]:
    source = catalog.get_source(stats.source_id)
    return {
        "type": "Feature",
        "geometry": plot["geometry"],
        "properties": {
            "id": plot.get("id"),
            "name": plot.get("name"),
            "areaHa": plot.get("areaHa"),
            "sourceId": stats.source_id,
            "acquisitionDate": stats.acquisition_date,
            "indexType": stats.index_type,
            "min": stats.statistics.min,
            "max": stats.statistics.max,
            "mean": stats.statistics.mean,
            "stddev": stats.statistics.stddev,
            "validPixelPercent": stats.statistics.validPixelPercent,
            "cloudMaskedPercent": stats.statistics.cloudMaskedPercent,
            "coveragePercent": stats.statistics.coveragePercent,
            "maskOptions": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": source_cloud_mask_mapping(source, cloud_mask).model_dump(
                by_alias=True
            ),
        },
    }


def _unsupported_format(message: str, **details: Any) -> AkashaError:
    return AkashaError("EXPORT_FORMAT_UNAVAILABLE", message, 501, details or None)


def _default_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=180), today


def _trend_csv_content(response) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "plot_id",
            "provider",
            "source_id",
            "index_type",
            "acquisition_date",
            "mean",
            "min",
            "max",
            "stddev",
            "valid_pixel_percent",
            "cloud_masked_percent",
            "coverage_percent",
            "cloud_percent",
            "unavailable_reason",
        ],
    )
    writer.writeheader()
    for point in response.points:
        writer.writerow(
            {
                "plot_id": response.plot_id,
                "provider": response.provider,
                "source_id": response.source_id,
                "index_type": response.index_type,
                "acquisition_date": point.acquisition_date.isoformat(),
                "mean": point.mean,
                "min": point.min,
                "max": point.max,
                "stddev": point.stddev,
                "valid_pixel_percent": point.valid_pixel_percent,
                "cloud_masked_percent": point.cloud_masked_percent,
                "coverage_percent": point.coverage_percent,
                "cloud_percent": point.cloud_percent,
                "unavailable_reason": point.unavailable_reason,
            }
        )
    return output.getvalue()


@router.get("/fields/{plot_id}/exports/index")
async def export_field_index(
    plot_id: str,
    format: ExportFormat = Query(default="csv"),
    sourceId: str = Query(default=settings.default_source_id),
    acquisitionDate: date | None = Query(default=None),
    indexType: str = Query(default=DEFAULT_INDEX),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
    user: CurrentUser = Depends(get_current_user),
):
    plot = await _get_field_or_404(plot_id, user.id)
    acquisition_date = _required_acquisition_date(acquisitionDate)
    index_type = _normalize_index(indexType)
    cloud_mask = CloudMaskOptions(clouds=clouds, cloud_shadows=cloudShadows, cirrus=cirrus)

    if format == "shp":
        raise _unsupported_format(
            "SHP export is available after native vector exports are implemented.",
            format="shp",
        )
    if format == "geotiff":
        raise _unsupported_format(
            "Native index GeoTIFF export is not available yet.",
            format="geotiff",
        )

    stats = await _run_blocking(
        _statistics_for_export,
        plot_id=plot_id,
        plot=plot,
        source_id=sourceId,
        acquisition_date=acquisition_date,
        index_type=index_type,
        cloud_mask=cloud_mask,
        optical_cloud_threshold_percent=optical_cloud_threshold(user),
    )

    if format == "csv":
        filename = _filename(plot, acquisition_date, index_type, "csv")
        return Response(
            content=_index_csv_content(stats),
            media_type="text/csv",
            headers=_disposition(filename),
        )

    filename = _filename(plot, acquisition_date, index_type, "geojson")
    return JSONResponse(
        content=_geojson_payload(plot, stats, cloud_mask),
        media_type="application/geo+json",
        headers=_disposition(filename),
    )


@router.get("/fields/{plot_id}/exports/report.csv")
async def export_field_report_csv(
    plot_id: str,
    indexType: str = Query(default=DEFAULT_INDEX),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    sourceId: str = Query(default=settings.default_source_id),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
    user: CurrentUser = Depends(get_current_user),
):
    default_start, default_end = _default_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_range(date_start, date_end)

    plot = await _get_field_or_404(plot_id, user.id)
    index_type = _normalize_index(indexType)
    cloud_mask = CloudMaskOptions(clouds=clouds, cloud_shadows=cloudShadows, cirrus=cirrus)
    if _uses_pipeline(sourceId):
        response = await _run_blocking(
            _pipeline_trend_response,
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            index_type=index_type,
            date_start=date_start,
            date_end=date_end,
            cloud_mask=cloud_mask,
            optical_cloud_threshold_percent=optical_cloud_threshold(user),
        )
    else:
        response = await _run_blocking(
            _native_trend_response,
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            index_type=index_type,
            date_start=date_start,
            date_end=date_end,
            cloud_mask=cloud_mask,
            reason="Native Akasha masked-raster report export is in use.",
        )

    filename = f"{_safe_filename(str(plot.get('name') or plot_id))}_{index_type}_analytics.csv"
    return Response(
        content=_trend_csv_content(response),
        media_type="text/csv",
        headers=_disposition(filename),
    )
