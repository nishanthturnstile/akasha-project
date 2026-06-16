"""Selected-field native analytics routes."""

from __future__ import annotations

import asyncio
import functools
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response
from pydantic import Field

from . import plots_repo
from .api_models import ApiModel, CloudMaskOptions, FieldTrendPoint, FieldTrendResponse
from .auth import CurrentTeam, get_current_team
from .cloud_mask import source_cloud_mask_mapping, source_excluded_mask_classes
from .config import settings
from .product import _enforce_index_rate_limit
from .raster import catalog_resolver as catalog
from .raster import tiles
from .raster.errors import (
    AkashaError,
    bad_request,
    mosaic_tiles_unavailable,
    not_found,
    plots_backend_unavailable,
)
from .raster.indices import DEFAULT_INDEX, get_index, index_tile_expression
from .raster.models import IndexStatisticsModel, PixelCounts
from .raster.service import compute_statistics

logger = logging.getLogger("akasha.api.field_analytics")

router = APIRouter(
    prefix="/api",
    tags=["field-analytics"],
    dependencies=[Depends(get_current_team)],
)

MAX_TREND_DAYS = 365


class FieldStatisticsRequest(ApiModel):
    source_id: str = settings.default_source_id
    acquisition_date: str | None = None
    index_type: str = DEFAULT_INDEX
    cloud_mask: CloudMaskOptions = Field(default_factory=CloudMaskOptions)


class FieldStatisticsResponse(ApiModel):
    plot_id: str
    provider: Literal["native"] = "native"
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


async def _get_plot_or_404(plot_id: str, team_id: str | None = None) -> dict[str, Any]:
    plot = await _run_blocking(plots_repo.get_plot, plot_id, team_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


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
    source = catalog.get_source(source_id)
    mask_mapping = source_cloud_mask_mapping(source, cloud_mask)
    computed = compute_statistics(
        geometry=plot["geometry"],
        source_id=source_id,
        acquisition_date=acquisition_date,
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
        # EOS-style "cloud cover in AOI": the in-field percentage masked as
        # cloud/shadow/cirrus by the active cloud-mask config. This is the value
        # the `maxCloudCoverInAoi` scene filter compares against.
        cloud_percent=result.statistics.cloudMaskedPercent,
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
    cloud_filtered_count = 0
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
            point = _trend_point_from_stats(stats)
            # EOS `max_cloud_cover_in_aoi` parity: drop scenes whose in-field
            # cloud cover exceeds the threshold. Scenes we could not evaluate
            # (cloud_percent is None) are kept and flagged, never silently lost.
            if (
                max_cloud_cover_in_aoi is not None
                and point.cloud_percent is not None
                and point.cloud_percent > max_cloud_cover_in_aoi
            ):
                cloud_filtered_count += 1
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
            "cloudFilteredSceneCount": cloud_filtered_count,
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
    team: CurrentTeam = Depends(get_current_team),
) -> FieldStatisticsResponse:
    _enforce_index_rate_limit(request)
    plot = await _get_plot_or_404(plot_id, team.id)
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
    sourceId: str = Query(default=settings.default_source_id),
    maxCloudCoverInAoi: float | None = Query(default=None),
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
    team: CurrentTeam = Depends(get_current_team),
) -> FieldTrendResponse:
    default_start, default_end = _default_range()
    date_start = startDate or default_start
    date_end = endDate or default_end
    _validate_range(date_start, date_end)
    if maxCloudCoverInAoi is not None and not 0.0 <= maxCloudCoverInAoi <= 100.0:
        raise bad_request(
            "maxCloudCoverInAoi must be between 0 and 100.",
            code="INVALID_CLOUD_COVER",
            maxCloudCoverInAoi=maxCloudCoverInAoi,
        )

    index_type = _normalize_index(indexType)
    plot = await _get_plot_or_404(plot_id, team.id)
    cloud_mask = CloudMaskOptions(
        clouds=clouds,
        cloud_shadows=cloudShadows,
        cirrus=cirrus,
    )
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


_OVERLAY_TARGET_PX = 512


def _overlay_dimensions(geometry: dict[str, Any]) -> tuple[int, int]:
    """Output (width, height) for the field overlay image.

    Matches the geometry's lng/lat bbox aspect with the longer side capped at
    _OVERLAY_TARGET_PX, so TiTiler rasterizes the clipped polygon edge smoothly
    instead of at the blocky native COG resolution.
    """
    xs: list[float] = []
    ys: list[float] = []

    def _walk(node: Any) -> None:
        if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
        elif isinstance(node, (list, tuple)):
            for child in node:
                _walk(child)

    _walk(geometry.get("coordinates"))
    if not xs or not ys:
        return _OVERLAY_TARGET_PX, _OVERLAY_TARGET_PX
    dlon = max(1e-9, max(xs) - min(xs))
    dlat = max(1e-9, max(ys) - min(ys))
    if dlon >= dlat:
        return _OVERLAY_TARGET_PX, max(1, round(_OVERLAY_TARGET_PX * dlat / dlon))
    return max(1, round(_OVERLAY_TARGET_PX * dlon / dlat)), _OVERLAY_TARGET_PX


def _render_field_index_overlay(
    *,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
) -> Response:
    """EOS-style field-clipped index image: colorized index inside the polygon,
    transparent outside, rendered by TiTiler /cog/feature."""
    supported = catalog.supported_indices(source_id)
    if index_type not in supported:
        raise bad_request(
            f"Unsupported index '{index_type}' for source '{source_id}'.",
            code="UNSUPPORTED_INDEX",
            sourceId=source_id,
            indexType=index_type,
            supported=supported,
        )
    index_def = get_index(index_type)
    if not acquisition_date:
        acquisition_date = catalog.latest_item(source_id)["properties"]["akasha:acquisition_date"]
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    if len(assets_for_date) != 1:
        raise mosaic_tiles_unavailable(
            "Date-level index overlays for multiple scenes require a configured mosaic backend.",
            sceneCount=len(assets_for_date),
            supportedSceneCount=1,
        )
    assets = assets_for_date[0]
    try:
        expression = index_tile_expression(
            assets["bandNames"],
            assets.get("bandRoleMapping", {}),
            index_def,
            scale=float(assets.get("scale", 0.0001)),
            offset=float(assets.get("offset", -0.1)),
        )
    except KeyError as exc:
        raise bad_request(
            "Scene is missing a band required for this index.",
            code="MISSING_INDEX_BANDS",
            indexType=index_type,
            missingRole=str(exc).strip("'"),
        ) from exc
    geometry = plot["geometry"]
    width, height = _overlay_dimensions(geometry)
    feature = {"type": "Feature", "properties": {}, "geometry": geometry}
    body, content_type = tiles.fetch_feature_overlay(
        analytic_href=assets["analyticHref"],
        feature=feature,
        expression=expression,
        rescale=index_def.display_rescale_str,
        colormap_name=index_def.display_colormap,
        width=width,
        height=height,
    )
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/fields/{plot_id}/overlay/{index_type}.png")
async def get_field_index_overlay(
    plot_id: str,
    index_type: str,
    request: Request,
    sourceId: str = Query(default=settings.default_source_id),
    acquisitionDate: str | None = Query(default=None),
    team: CurrentTeam = Depends(get_current_team),
) -> Response:
    """Same-origin field-clipped index overlay PNG (transparent outside the field).

    The browser overlays this image at the field's bounds to colour only the plot
    (EOS-style), keeping base imagery around it.
    """
    _enforce_index_rate_limit(request)
    plot = await _get_plot_or_404(plot_id, team.id)
    index_type = _normalize_index(index_type)
    return await _run_blocking(
        _render_field_index_overlay,
        plot=plot,
        source_id=sourceId,
        acquisition_date=acquisitionDate,
        index_type=index_type,
    )
