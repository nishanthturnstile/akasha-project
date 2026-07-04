"""Pure adapter: ingestion field-index -> app ``FieldStatisticsResponse``.

Implements the Appendix B "Statistics and Metadata Mapping" contract from
``docs/impl-plan/feature-ui-pipeline-integration-1.md``. This module performs no
I/O; it only translates an ingestion ``AVAILABLE`` response into the app-domain
statistics contract while preserving ``provider:"native"`` / ``scope:"field"``
compatibility and adding optional ``metadata.pipeline`` details.

Browser-visible JSON must never contain ingestion signed URLs, hostnames,
``queryId``/``layerId`` values, or API keys. Tile/stats URLs are only included
when an app-domain proxy URL is supplied by the caller; the raw ingestion
``tileUrl``/``statsUrl`` are never copied through.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .api_models import CloudMaskOptions
from .ingestion_client import FieldIndexAvailableResponse
from .raster.errors import AkashaError
from .raster.models import IndexStatisticsModel, PixelCounts
from .schemas.analytics import FieldStatisticsResponse

# Sentinel-2 NDVI is the only pipeline-backed combination in this MVP.
PIPELINE_INDEX_FORMULA = "(NIR-RED)/(NIR+RED)"
PIPELINE_INDEX_BANDS = ["NIR", "RED"]
PIPELINE_MASK_METHOD = "sentinel2-pipeline-scl"
PIPELINE_CLOUD_MASK_OPTIONS_NOTE = (
    "Request cloudMask flags are echoed for compatibility; Sentinel-2 pipeline "
    "MVP applies its precomputed mask and maxCloudPercentage policy."
)
PIXEL_COUNTS_BASIS = "derivedFromValidPixelCountAndUsablePixelPercentage"
COVERAGE_PERCENT_BASIS = "availableOutputAssumedFullCoverage"
_CLOUD_CLASS_TOKENS = ("cloud", "shadow", "cirrus")


def _pipeline_contract_mismatch(message: str, **details: Any) -> AkashaError:
    return AkashaError("PIPELINE_CONTRACT_MISMATCH", message, 502, details or None)


def _as_iso_date(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _clamp_percentage(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def _cloud_masked_percent(
    response: FieldIndexAvailableResponse,
) -> tuple[float | None, str]:
    """Prefer summed cloud/shadow/cirrus class percentages, else cloud percentage."""

    class_percent = 0.0
    matched = False
    for entry in response.class_statistics:
        name = (entry.class_name or "").lower()
        if any(token in name for token in _CLOUD_CLASS_TOKENS):
            matched = True
            if entry.area_percentage is not None:
                class_percent += float(entry.area_percentage)
    if matched:
        return _clamp_percentage(class_percent), "sumOfCloudClassPercentages"
    scene_cloud = response.statistics.cloud_percentage if response.statistics else None
    return _clamp_percentage(scene_cloud), "sceneCloudPercentage"


def _derive_pixel_counts(response: FieldIndexAvailableResponse) -> PixelCounts:
    valid_pixels = 0
    if response.selection and response.selection.valid_pixel_count is not None:
        valid_pixels = int(response.selection.valid_pixel_count)

    usable = response.statistics.usable_pixel_percentage if response.statistics else None
    if usable is not None and float(usable) > 0:
        coverage_pixels = round(valid_pixels * 100 / float(usable))
    else:
        coverage_pixels = 0

    masked_pixels = max(coverage_pixels - valid_pixels, 0)
    total_pixels = coverage_pixels
    nodata_pixels = max(total_pixels - coverage_pixels, 0)
    return PixelCounts(
        totalPixels=total_pixels,
        nodataPixels=nodata_pixels,
        coveragePixels=coverage_pixels,
        maskedPixels=masked_pixels,
        validPixels=valid_pixels,
    )


def _provenance_note(response: FieldIndexAvailableResponse) -> str:
    parts: list[str] = ["Pipeline Sentinel-2 scene selected"]
    if response.selection and response.selection.rule:
        parts.append(f"by {response.selection.rule}")
    if response.selection and response.selection.window_days is not None:
        parts.append(f"within +/- {response.selection.window_days} days")
    note = " ".join(parts) + "."
    if response.quality and response.quality.reason:
        note = f"{note} {response.quality.reason}."
    return note


def _pipeline_metadata(
    response: FieldIndexAvailableResponse,
    *,
    requested_date: date | str,
    cloud_masked_percent_basis: str,
    tile_proxy_url: str | None,
    stats_proxy_url: str | None,
    freshness: dict[str, Any] | None,
) -> dict[str, Any]:
    pipeline: dict[str, Any] = {
        "enabled": True,
        "status": response.status,
        "source": response.source,
        "providerRoute": response.provider_route,
        "requestedDate": _as_iso_date(requested_date),
        "selectedSceneDate": _as_iso_date(response.selected_scene_date),
        "pixelCountsBasis": PIXEL_COUNTS_BASIS,
        "cloudMaskedPercentBasis": cloud_masked_percent_basis,
        "coveragePercentBasis": COVERAGE_PERCENT_BASIS,
        "cloudMaskOptionsNote": PIPELINE_CLOUD_MASK_OPTIONS_NOTE,
    }
    if response.selection is not None:
        pipeline["selection"] = response.selection.model_dump(by_alias=True, exclude_none=True)
    if response.resolution is not None:
        pipeline["resolution"] = response.resolution.model_dump(by_alias=True, exclude_none=True)
    if response.quality is not None:
        pipeline["quality"] = response.quality.model_dump(by_alias=True, exclude_none=True)
    if response.versions:
        pipeline["versions"] = dict(response.versions)
    if response.class_statistics:
        pipeline["classStatistics"] = [
            item.model_dump(by_alias=True, exclude_none=True) for item in response.class_statistics
        ]
    # Only app-domain proxy URLs are surfaced; raw ingestion signed URLs are never copied.
    if tile_proxy_url:
        pipeline["tileUrl"] = tile_proxy_url
    if stats_proxy_url:
        pipeline["statsUrl"] = stats_proxy_url
    if freshness:
        pipeline["freshness"] = freshness
    return pipeline


def adapt_field_index_to_statistics(
    *,
    plot_id: str,
    response: FieldIndexAvailableResponse,
    cloud_mask: CloudMaskOptions,
    requested_date: date | str,
    expected_source_id: str = "sentinel-2-l2a",
    expected_index: str = "NDVI",
    tile_proxy_url: str | None = None,
    stats_proxy_url: str | None = None,
    freshness: dict[str, Any] | None = None,
) -> FieldStatisticsResponse:
    """Map an ingestion ``AVAILABLE`` field-index response to the app contract.

    ``plot_id`` is the app field id from the route and always wins over the
    ingestion ``fieldId``. Raises ``PIPELINE_CONTRACT_MISMATCH`` if ingestion
    reports an unexpected source or index.
    """

    if response.source and response.source != expected_source_id:
        raise _pipeline_contract_mismatch(
            "Ingestion returned an unexpected source for the pipeline stats branch.",
            expected=expected_source_id,
            received=response.source,
        )
    index_type = (response.index or expected_index).strip().upper()
    if index_type != expected_index:
        raise _pipeline_contract_mismatch(
            "Ingestion returned an unexpected index for the pipeline stats branch.",
            expected=expected_index,
            received=index_type,
        )

    stats = response.statistics
    cloud_masked_percent, cloud_masked_percent_basis = _cloud_masked_percent(response)

    statistics = IndexStatisticsModel(
        min=stats.min if stats else None,
        max=stats.max if stats else None,
        mean=stats.mean if stats else None,
        stddev=stats.std_dev if stats else None,
        validPixelPercent=_clamp_percentage(stats.usable_pixel_percentage if stats else None)
        or 0.0,
        cloudMaskedPercent=cloud_masked_percent or 0.0,
        # Available precomputed outputs are assumed full coverage (see basis field).
        coveragePercent=100.0,
    )
    pixel_counts = _derive_pixel_counts(response)

    metadata: dict[str, Any] = {
        "provider": "native",
        "scope": "field",
        "formula": PIPELINE_INDEX_FORMULA,
        "bands": list(PIPELINE_INDEX_BANDS),
        "spectralRoles": list(PIPELINE_INDEX_BANDS),
        "maskMethod": PIPELINE_MASK_METHOD,
        "cloudMaskOptions": cloud_mask.model_dump(by_alias=True),
        "warnings": [],
        "pipeline": _pipeline_metadata(
            response,
            requested_date=requested_date,
            cloud_masked_percent_basis=cloud_masked_percent_basis,
            tile_proxy_url=tile_proxy_url,
            stats_proxy_url=stats_proxy_url,
            freshness=freshness,
        ),
    }

    resolution_meters = response.resolution.processing_meters if response.resolution else None

    return FieldStatisticsResponse(
        plot_id=plot_id,
        index_type=index_type,
        source_id=response.source or expected_source_id,
        acquisition_date=_as_iso_date(requested_date) or "",
        cloud_mask=cloud_mask,
        statistics=statistics,
        pixel_counts=pixel_counts,
        metadata=metadata,
        resolved_source_id=response.source or expected_source_id,
        resolution_meters=resolution_meters,
        enhanced=False,
        basis_date=_as_iso_date(response.selected_scene_date),
        provenance_note=_provenance_note(response),
    )
