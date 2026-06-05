"""Selected-field export routes for EOS-parity Phase 6."""
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

from . import plots_repo
from .auth import get_current_team
from .config import settings
from .field_analytics import (
    PROVIDER_INDEX_TYPES,
    _eos_trend_response,
    _field_statistics,
    _native_trend_response,
    _normalize_index,
    _validate_range,
)
from .providers.cloud_mask import cloud_mask_mapping
from .providers.eos.imagery_provider import EosImageryProvider
from .providers.models import CloudMaskOptions, ExportFile
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
from .raster.indices import DEFAULT_INDEX

logger = logging.getLogger("akasha.api.field_exports")

router = APIRouter(
    prefix="/api",
    tags=["field-exports"],
    dependencies=[Depends(get_current_team)],
)

ExportFormat = Literal["geotiff", "geojson", "csv", "shp"]
ProviderChoice = Literal["auto", "eos", "native"]


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


async def _get_plot_or_404(plot_id: str) -> dict[str, Any]:
    plot = await _run_blocking(plots_repo.get_plot, plot_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


def _is_eos_ready() -> bool:
    mode = (settings.provider_mode or "disabled").strip().lower()
    return bool(settings.eos_api_key.strip()) and settings.eos_enabled and mode in {"eos", "hybrid"}


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
):
    return _field_statistics(
        plot_id=plot_id,
        plot=plot,
        source_id=source_id,
        acquisition_date=acquisition_date.isoformat(),
        index_type=index_type,
        cloud_mask=cloud_mask,
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
            "scl_excluded_pixels",
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
            "scl_excluded_pixels": stats.pixel_counts.sclExcludedPixels,
        }
    )
    return output.getvalue()


def _geojson_payload(plot: dict[str, Any], stats, cloud_mask: CloudMaskOptions) -> dict[str, Any]:
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
            "cloudMask": cloud_mask.model_dump(by_alias=True),
            "cloudMaskMapping": cloud_mask_mapping(cloud_mask).model_dump(by_alias=True),
        },
    }


def _unsupported_format(message: str, **details: Any) -> AkashaError:
    return AkashaError("EXPORT_FORMAT_UNAVAILABLE", message, 501, details or None)


def _provider_export_file(
    *,
    plot_id: str,
    plot: dict[str, Any],
    acquisition_date: date,
    index_type: str,
    scene_token: str | None,
    provider: ProviderChoice,
    cloud_mask: CloudMaskOptions,
) -> ExportFile:
    if provider == "native":
        raise _unsupported_format(
            "Native index GeoTIFF export is not available in Phase 6.",
            provider="native",
            format="geotiff",
        )
    external_field_id = plot.get("externalFieldId")
    if not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before exporting provider index imagery.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )
    if not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "EOS provider is not available for index imagery export.",
            503,
            {"provider": "eos"},
        )
    if index_type not in PROVIDER_INDEX_TYPES:
        raise bad_request(
            f"Unsupported provider export index '{index_type}'.",
            code="UNSUPPORTED_INDEX",
            indexType=index_type,
            supported=sorted(PROVIDER_INDEX_TYPES),
        )
    exported = EosImageryProvider().export_index_geotiff(
        str(external_field_id),
        scene_token=scene_token,
        acquisition_date=acquisition_date,
        index=index_type,
        cloud_mask=cloud_mask,
        filename=_filename(plot, acquisition_date, index_type, "tiff"),
    )
    metadata = exported.metadata.model_copy(
        update={
            "plot_id": plot_id,
            "acquisition_date": acquisition_date,
            "index_type": index_type,
            "cloud_mask": cloud_mask,
            "cloud_mask_mapping": cloud_mask_mapping(cloud_mask),
        }
    )
    return exported.model_copy(update={"metadata": metadata})


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
    sourceId: str = Query(default="sentinel-2-l2a"),
    acquisitionDate: date | None = Query(default=None),
    indexType: str = Query(default=DEFAULT_INDEX),
    sceneToken: str | None = Query(default=None),
    provider: ProviderChoice = Query(default="auto"),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
):
    plot = await _get_plot_or_404(plot_id)
    acquisition_date = _required_acquisition_date(acquisitionDate)
    index_type = _normalize_index(indexType)
    cloud_mask = CloudMaskOptions(clouds=clouds, cloud_shadows=cloudShadows, cirrus=cirrus)

    if format == "shp":
        raise _unsupported_format(
            "SHP export is available after zoning/vector exports are implemented.",
            format="shp",
        )

    if format == "geotiff":
        exported = await _run_blocking(
            _provider_export_file,
            plot_id=plot_id,
            plot=plot,
            acquisition_date=acquisition_date,
            index_type=index_type,
            scene_token=sceneToken,
            provider=provider,
            cloud_mask=cloud_mask,
        )
        return Response(
            content=exported.content,
            media_type=exported.content_type,
            headers=_disposition(exported.filename),
        )

    stats = await _run_blocking(
        _statistics_for_export,
        plot_id=plot_id,
        plot=plot,
        source_id=sourceId,
        acquisition_date=acquisition_date,
        index_type=index_type,
        cloud_mask=cloud_mask,
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
    provider: ProviderChoice = Query(default="auto"),
    sourceId: str = Query(default="sentinel-2-l2a"),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
):
    default_start, default_end = _default_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_range(date_start, date_end)

    plot = await _get_plot_or_404(plot_id)
    index_type = _normalize_index(indexType)
    cloud_mask = CloudMaskOptions(clouds=clouds, cloud_shadows=cloudShadows, cirrus=cirrus)
    external_field_id = plot.get("externalFieldId")

    if provider == "eos" and not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before exporting provider analytics.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )
    if provider == "eos" and not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "EOS provider is not available for analytics export.",
            503,
            {"provider": "eos"},
        )
    if provider == "eos" and index_type not in PROVIDER_INDEX_TYPES:
        raise bad_request(
            f"Unsupported provider export index '{index_type}'.",
            code="UNSUPPORTED_INDEX",
            indexType=index_type,
            supported=sorted(PROVIDER_INDEX_TYPES),
        )

    use_native_export = provider == "native" or not (
        external_field_id and _is_eos_ready() and index_type in PROVIDER_INDEX_TYPES
    )
    if use_native_export:
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
    else:
        response = await _run_blocking(
            _eos_trend_response,
            plot_id=plot_id,
            external_field_id=str(external_field_id),
            index_type=index_type,
            date_start=date_start,
            date_end=date_end,
            cloud_mask=cloud_mask,
        )

    filename = f"{_safe_filename(str(plot.get('name') or plot_id))}_{index_type}_analytics.csv"
    return Response(
        content=_trend_csv_content(response),
        media_type="text/csv",
        headers=_disposition(filename),
    )
