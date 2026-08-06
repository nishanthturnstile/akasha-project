"""Adapters from standalone ingestion field-index payloads to app contracts."""

from __future__ import annotations

from datetime import date
from typing import Any

from .api_models import CloudMaskOptions, FieldTrendPoint
from .raster.errors import bad_request, upstream_error
from .raster.models import IndexStatisticsModel, PixelCounts
from .raster.value_split import normalize_pipeline_ndvi_value_split
from .schemas.analytics import FieldStatisticsResponse

_METADATA_ALLOWLIST = ("queryId", "providerRoute", "versions")


def _ensure_available(result: dict[str, Any]) -> None:
    if result.get("status") == "AVAILABLE":
        return
    raise bad_request(
        "Standalone ingestion field-index is unavailable for this field/date.",
        code="INGESTION_OVERLAY_UNAVAILABLE",
        reason=result.get("reason") or result.get("message"),
    )


def _statistics(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("statistics")
    if not isinstance(stats, dict):
        raise upstream_error(
            "Standalone ingestion field-index response is missing statistics.",
            code="INGESTION_FIELD_INDEX_ERROR",
        )
    return stats


def _selected_scene_date(result: dict[str, Any]) -> str:
    selected = result.get("selectedSceneDate")
    if not selected:
        raise upstream_error(
            "Standalone ingestion field-index response is missing selected scene date.",
            code="INGESTION_FIELD_INDEX_ERROR",
        )
    return str(selected)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_default(value: Any, default: float = 0.0) -> float:
    converted = _float_or_none(value)
    return default if converted is None else converted


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _index_statistics_model(stats: dict[str, Any]) -> IndexStatisticsModel:
    return IndexStatisticsModel(
        min=_float_or_none(stats.get("min")),
        max=_float_or_none(stats.get("max")),
        mean=_float_or_none(stats.get("mean")),
        stddev=_float_or_none(stats.get("stdDev")),
        validPixelPercent=_float_or_default(stats.get("usablePixelPercentage")),
        cloudMaskedPercent=_float_or_default(stats.get("cloudPercentage")),
        coveragePercent=_float_or_default(stats.get("fieldCoveragePercentage")),
    )


def _pixel_counts(result: dict[str, Any]) -> PixelCounts:
    selection = result.get("selection")
    if not isinstance(selection, dict):
        return PixelCounts()
    valid_pixels = _int_or_default(selection.get("validPixelCount"))
    coverage_pixels = _int_or_default(selection.get("coveragePixelCount"), valid_pixels)
    return PixelCounts(
        totalPixels=_int_or_default(selection.get("totalPixelCount")),
        nodataPixels=_int_or_default(selection.get("nodataPixelCount")),
        coveragePixels=coverage_pixels,
        maskedPixels=_int_or_default(selection.get("maskedPixelCount")),
        validPixels=valid_pixels,
    )


def _metadata(result: dict[str, Any], *, scope: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"provider": "pipeline", "scope": scope}
    for key in _METADATA_ALLOWLIST:
        if key in result:
            metadata[key] = result[key]
    return metadata


def _value_split(result: dict[str, Any], *, index_type: str) -> dict[str, Any] | None:
    if index_type != "NDVI":
        return None
    visualization = result.get("visualization")
    threshold_profile = (
        visualization.get("thresholdProfile") if isinstance(visualization, dict) else None
    )
    class_statistics = result.get("classStatistics")
    if not isinstance(class_statistics, list):
        return None
    selection = result.get("selection") if isinstance(result.get("selection"), dict) else {}
    return normalize_pipeline_ndvi_value_split(
        class_statistics=[item for item in class_statistics if isinstance(item, dict)],
        threshold_profile=str(threshold_profile) if threshold_profile else None,
        total_pixel_count=_int_or_default(selection.get("totalPixelCount")) or None,
        coverage_pixel_count=_int_or_default(selection.get("coveragePixelCount")) or None,
        nodata_pixel_count=_int_or_default(selection.get("nodataPixelCount")) or None,
    )


def field_index_to_statistics_response(
    result: dict[str, Any],
    *,
    plot_id: str,
    source_id: str,
    index_type: str,
    cloud_mask: CloudMaskOptions,
) -> FieldStatisticsResponse:
    _ensure_available(result)
    stats = _statistics(result)
    resolution = result.get("resolution") if isinstance(result.get("resolution"), dict) else {}
    return FieldStatisticsResponse(
        plot_id=plot_id,
        provider="pipeline",
        scope="field",
        index_type=index_type,
        source_id=source_id,
        acquisition_date=_selected_scene_date(result),
        cloud_mask=cloud_mask,
        statistics=_index_statistics_model(stats),
        pixel_counts=_pixel_counts(result),
        value_split=_value_split(result, index_type=index_type),
        metadata=_metadata(result, scope="field"),
        resolved_source_id=source_id,
        resolution_meters=_float_or_none(resolution.get("displayMeters")),
        enhanced=False,
    )


def field_index_to_trend_point(result: dict[str, Any]) -> FieldTrendPoint:
    _ensure_available(result)
    stats = _statistics(result)
    acquisition_date = date.fromisoformat(_selected_scene_date(result))
    return FieldTrendPoint(
        acquisition_date=acquisition_date,
        scene_id=str(result.get("sceneId") or result.get("selectedSceneId") or "") or None,
        mean=_float_or_none(stats.get("mean")),
        min=_float_or_none(stats.get("min")),
        max=_float_or_none(stats.get("max")),
        stddev=_float_or_none(stats.get("stdDev")),
        valid_pixel_percent=_float_or_none(stats.get("usablePixelPercentage")),
        cloud_masked_percent=_float_or_none(stats.get("cloudPercentage")),
        coverage_percent=_float_or_none(stats.get("fieldCoveragePercentage")),
        cloud_percent=_float_or_none(stats.get("cloudPercentage")),
        metrics_provisional=False,
    )
