"""Selected-field native analytics routes."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from ..api_models import CloudMaskOptions, FieldTrendPoint, FieldTrendResponse
from ..auth import CurrentTeam, CurrentUser, get_current_team, get_current_user
from ..cloud_mask import source_cloud_mask_mapping, source_excluded_mask_classes
from ..config import settings
from ..ingestion_client import (
    FieldIndexAvailableResponse,
    FieldIndexRequest,
    FieldIndexUnavailableResponse,
    IngestionClient,
    IngestionClientError,
    ReadinessResponse,
)
from ..ingestion_field_index_adapter import adapt_field_index_to_statistics
from ..raster import catalog_resolver as catalog
from ..raster import tiles
from ..raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
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
from ..repositories import pipeline_proxy_repo as proxy_repo
from ..routers.pipeline_proxy import (
    STATS_PROXY_URL_TEMPLATE,
    TILE_PROXY_URL_TEMPLATE,
)
from ..routers.product_router import _enforce_index_rate_limit
from ..schemas.analytics import FieldStatisticsRequest, FieldStatisticsResponse

logger = logging.getLogger("akasha.api.field_analytics")

router = APIRouter(
    prefix="/api",
    tags=["field-analytics"],
    dependencies=[Depends(get_current_team)],
)

MAX_TREND_DAYS = 365


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


PIPELINE_INDEX = "NDVI"
# MVP: ingestion receives a bounded cloud policy; per-class toggles are echoed
# only (see adapter cloudMaskOptionsNote). 20% matches the pinned contract example.
PIPELINE_DEFAULT_MAX_CLOUD_PERCENTAGE = 20


def _pipeline_stats_enabled(source_id: str, index_type: str) -> bool:
    """Feature gate for the ingestion-backed Sentinel-2 NDVI stats branch."""

    return (
        settings.ingestion_field_index_enabled
        and source_id == settings.ingestion_field_index_source_id
        and index_type == PIPELINE_INDEX
    )


async def _run_ingestion(func, *args, **kwargs):
    """Run a synchronous ingestion client call off the event loop.

    ``IngestionClientError`` carries an already-sanitized code/message/status and
    is re-raised as the standard ``AkashaError`` so it flows through the app error
    handler. Native fallback is intentionally *not* used here: when the pipeline
    flag is on we surface pipeline errors instead of silently degrading.
    """

    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except IngestionClientError as exc:
        raise AkashaError(exc.code, exc.message, exc.status_code, exc.details) from exc


def _pipeline_geometry(plot: dict[str, Any]) -> dict[str, Any]:
    geometry = plot.get("geometry")
    if not isinstance(geometry, dict):
        from ..raster.errors import invalid_geometry

        raise invalid_geometry(
            "Field geometry must be a Polygon or MultiPolygon for pipeline statistics.",
            geometryType=None,
        )
    # Reuse the shared guardrail: type, non-empty, topological validity, vertex
    # and geodesic-area limits. Preserves both Polygon and MultiPolygon support.
    validate_polygon(
        geometry,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
    )
    return geometry


def _readiness_details(source_id: str, readiness: ReadinessResponse | None) -> dict[str, Any]:
    details: dict[str, Any] = {"sourceId": source_id, "aoiId": settings.ingestion_aoi_id}
    if readiness is not None:
        if readiness.latest_processed_scene_date is not None:
            details["latestProcessedSceneDate"] = readiness.latest_processed_scene_date.isoformat()
        if readiness.stale_after is not None:
            details["staleAfter"] = readiness.stale_after.isoformat()
    return details


def _enforce_readiness(source_id: str, readiness: ReadinessResponse) -> None:
    if readiness.status == "STALE":
        raise AkashaError(
            "PIPELINE_STALE",
            "Sentinel-2 pipeline preload is stale for Bangalore 60 km.",
            503,
            {**_readiness_details(source_id, readiness), "retryable": True},
        )
    if readiness.status == "UNAVAILABLE":
        raise AkashaError(
            "PIPELINE_OUTPUT_UNAVAILABLE",
            "No precomputed Sentinel-2 NDVI output is available for this AOI.",
            404,
            {**_readiness_details(source_id, readiness), "retryable": False},
        )
    coverage = readiness.index_coverage.get(PIPELINE_INDEX)
    if coverage is None or not coverage.available or not readiness.available_dates:
        raise AkashaError(
            "PIPELINE_OUTPUT_UNAVAILABLE",
            "No precomputed Sentinel-2 NDVI output is available for this AOI.",
            404,
            {**_readiness_details(source_id, readiness), "retryable": False},
        )


def _freshness_metadata(readiness: ReadinessResponse | None) -> dict[str, Any] | None:
    if readiness is None:
        return None
    freshness: dict[str, Any] = {"status": readiness.status, "aoiId": readiness.aoi_id}
    if readiness.latest_processed_scene_date is not None:
        freshness["latestProcessedSceneDate"] = readiness.latest_processed_scene_date.isoformat()
    if readiness.stale_after is not None:
        freshness["staleAfter"] = readiness.stale_after.isoformat()
    return freshness


def _resolve_pipeline_date(
    acquisition_date: str | None, readiness: ReadinessResponse | None
) -> date:
    if acquisition_date:
        try:
            return date.fromisoformat(acquisition_date)
        except ValueError as exc:
            raise bad_request(
                "acquisitionDate must be an ISO date (YYYY-MM-DD).",
                code="INVALID_DATE",
                acquisitionDate=acquisition_date,
            ) from exc
    if readiness is not None and readiness.available_dates:
        return max(readiness.available_dates)
    return datetime.now(UTC).date()


def _pipeline_unavailable_error(
    response: FieldIndexUnavailableResponse, source_id: str, requested_date: date
) -> AkashaError:
    return AkashaError(
        "PIPELINE_OUTPUT_UNAVAILABLE",
        "No precomputed Sentinel-2 NDVI output is available for this field and date.",
        404,
        {
            "sourceId": source_id,
            "indexType": response.index,
            "requestedDate": requested_date.isoformat(),
            "reason": response.reason,
            "searchedSources": list(response.searched_sources),
            "retryable": False,
        },
    )


async def _build_pipeline_proxy_urls(
    *,
    response: FieldIndexAvailableResponse,
    plot_id: str,
    source_id: str,
    index_type: str,
    user: CurrentUser,
    team: CurrentTeam,
) -> tuple[str | None, str | None]:
    """Persist DB-backed proxy records and return opaque app-domain URLs.

    Ingestion signed ``statsUrl``/``tileUrl`` (and ``queryId``/``layerId``) are
    stored server-side only; the browser receives opaque ``proxyId`` URLs. Proxy
    persistence is best-effort: if the proxy store is unavailable we omit the
    optional URLs rather than failing the whole statistics response. The tile
    proxy is only minted when ``INGESTION_PIPELINE_TILE_LAYER_ENABLED`` is set.
    """

    team_id = team.id if team else user.current_team_id
    if not team_id:
        return None, None

    ttl = max(1, int(settings.ingestion_pipeline_proxy_ttl_seconds))
    now = datetime.now(UTC)

    def _capped_expiry(upstream_url: str) -> datetime | None:
        """Cap the proxy TTL to the upstream signed ``exp``.

        The upstream signed URL must carry a parseable expiry; otherwise the
        app cannot prove the opaque proxy will expire no later than the
        ingestion signature it wraps, so it fails closed and omits the proxy.
        """

        expires_at = now + timedelta(seconds=ttl)
        upstream_exp = _parse_signed_exp(upstream_url)
        if upstream_exp is None:
            return None
        if upstream_exp <= now:
            return None
        if upstream_exp < expires_at:
            expires_at = upstream_exp
        return expires_at

    async def _create(operation: str, upstream_url: str, expires_at: datetime) -> str | None:
        try:
            return await anyio.to_thread.run_sync(
                functools.partial(
                    proxy_repo.create_proxy_record,
                    operation=operation,
                    upstream_url=upstream_url,
                    user_id=str(user.id),
                    team_id=str(team_id),
                    field_id=plot_id,
                    source_id=source_id,
                    index_type=index_type,
                    expires_at=expires_at,
                    query_id=response.query_id,
                    layer_id=response.layer_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pipeline proxy record not persisted: %s", type(exc).__name__)
            return None

    stats_proxy_url: str | None = None
    if response.stats_url:
        expires_at = _capped_expiry(response.stats_url)
        if expires_at is not None:
            proxy_id = await _create("stats", response.stats_url, expires_at)
            if proxy_id:
                stats_proxy_url = STATS_PROXY_URL_TEMPLATE.format(proxy_id=proxy_id)

    tile_proxy_url: str | None = None
    if settings.ingestion_pipeline_tile_layer_enabled and response.tile_url:
        expires_at = _capped_expiry(response.tile_url)
        if expires_at is not None:
            proxy_id = await _create("tile", response.tile_url, expires_at)
            if proxy_id:
                tile_proxy_url = TILE_PROXY_URL_TEMPLATE.format(proxy_id=proxy_id)

    return stats_proxy_url, tile_proxy_url


def _parse_signed_exp(url: str) -> datetime | None:
    """Extract a signed ``exp`` epoch-seconds query parameter, if present."""

    from urllib.parse import parse_qs, urlparse

    try:
        query = urlparse(url).query
    except (TypeError, ValueError):
        return None
    values = parse_qs(query).get("exp")
    if not values:
        return None
    try:
        return datetime.fromtimestamp(int(values[0]), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


async def _pipeline_field_statistics(
    *,
    plot_id: str,
    plot: dict[str, Any],
    payload: FieldStatisticsRequest,
    request: Request,
    user: CurrentUser,
    team: CurrentTeam,
) -> FieldStatisticsResponse:
    client = IngestionClient()
    request_id = request.headers.get("X-Request-ID")

    # Readiness is mandatory whenever the Sentinel-2 NDVI pipeline stats branch is
    # taken: the plan requires field-index calls only when readiness is AVAILABLE
    # with NDVI coverage and available dates. We never call ingestion without it,
    # regardless of INGESTION_READINESS_ENABLED (that flag gates the separate
    # product source/date bridge, not this hard stats gate).
    readiness = await _run_ingestion(
        client.readiness, source_id=payload.source_id, request_id=request_id
    )
    _enforce_readiness(payload.source_id, readiness)

    requested_date = _resolve_pipeline_date(payload.acquisition_date, readiness)
    geometry = _pipeline_geometry(plot)
    field_request = FieldIndexRequest(
        geometry=geometry,
        crs="EPSG:4326",
        index=PIPELINE_INDEX,
        date=requested_date,
        fallback_policy="nearest_valid_scene",
        max_cloud_percentage=PIPELINE_DEFAULT_MAX_CLOUD_PERCENTAGE,
        field_id=plot_id,
    )
    response = await _run_ingestion(client.field_index, field_request, request_id=request_id)
    if isinstance(response, FieldIndexUnavailableResponse):
        raise _pipeline_unavailable_error(response, payload.source_id, requested_date)

    assert isinstance(response, FieldIndexAvailableResponse)
    stats_proxy_url, tile_proxy_url = await _build_pipeline_proxy_urls(
        response=response,
        plot_id=plot_id,
        source_id=payload.source_id,
        index_type=PIPELINE_INDEX,
        user=user,
        team=team,
    )
    return adapt_field_index_to_statistics(
        plot_id=plot_id,
        response=response,
        cloud_mask=payload.cloud_mask,
        requested_date=requested_date,
        expected_source_id=settings.ingestion_field_index_source_id,
        expected_index=PIPELINE_INDEX,
        stats_proxy_url=stats_proxy_url,
        tile_proxy_url=tile_proxy_url,
        freshness=_freshness_metadata(readiness),
    )


async def _pipeline_field_overlay(
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    acquisition_date: str,
    request: Request,
) -> tuple[bytes, str, dict[str, str]]:
    """Render a field-clipped NDVI overlay via the ingestion pipeline.

    Mirrors ``_pipeline_field_statistics`` selection: readiness is enforced, then
    ingestion computes/clips the overlay to the field polygon and returns a signed
    overlay URL, which the BFF fetches server-side and returns as an app-domain
    image (with georeferencing corners). No full-scene tiles are rendered.
    """

    client = IngestionClient()
    request_id = request.headers.get("X-Request-ID")
    readiness = await _run_ingestion(
        client.readiness, source_id=source_id, request_id=request_id
    )
    _enforce_readiness(source_id, readiness)
    requested_date = _resolve_pipeline_date(acquisition_date, readiness)
    geometry = _pipeline_geometry(plot)
    field_request = FieldIndexRequest(
        geometry=geometry,
        crs="EPSG:4326",
        index=PIPELINE_INDEX,
        date=requested_date,
        fallback_policy="nearest_valid_scene",
        max_cloud_percentage=PIPELINE_DEFAULT_MAX_CLOUD_PERCENTAGE,
        field_id=plot_id,
    )
    response = await _run_ingestion(client.field_index, field_request, request_id=request_id)
    if isinstance(response, FieldIndexUnavailableResponse):
        raise _pipeline_unavailable_error(response, source_id, requested_date)
    assert isinstance(response, FieldIndexAvailableResponse)
    if not response.overlay_url:
        raise bad_request(
            "Pipeline overlay is unavailable for this field and date.",
            code="PIPELINE_OVERLAY_UNAVAILABLE",
        )
    content, content_type, corners = await _run_ingestion(
        client.fetch_overlay, response.overlay_url, request_id=request_id
    )
    headers: dict[str, str] = {}
    if corners:
        headers["X-Akasha-Overlay-Corners"] = corners
    return content, content_type or "image/png", headers


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
    team: CurrentTeam = Depends(get_current_team),
) -> FieldStatisticsResponse:
    _enforce_index_rate_limit(request)
    plot = await _get_field_or_404(plot_id, user.id)
    index_type = _normalize_index(payload.index_type)

    # Feature-gated Sentinel-2 NDVI pipeline branch. When enabled it must not fall
    # back to native Sentinel-2: stale/missing readiness surfaces pipeline errors.
    if _pipeline_stats_enabled(payload.source_id, index_type):
        return await _pipeline_field_statistics(
            plot_id=plot_id,
            plot=plot,
            payload=payload,
            request=request,
            user=user,
            team=team,
        )

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
        from ..raster.errors import index_timeout

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
    request: Request,
    sourceId: str = Query(default=settings.default_source_id),
    acquisitionDate: str = Query(...),
    preferHighRes: bool = Query(default=True),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    plot = await _get_field_or_404(plot_id, user.id)
    normalized_index = _normalize_index(index_type)
    # Pipeline (Sentinel-2 NDVI) renders a field-clipped overlay via ingestion; the
    # native raster path has no COG for this source. Non-pipeline sources use the
    # native clipped-overlay renderer.
    if _pipeline_stats_enabled(sourceId, normalized_index):
        body, content_type, headers = await _pipeline_field_overlay(
            plot_id=plot_id,
            plot=plot,
            source_id=sourceId,
            acquisition_date=acquisitionDate,
            request=request,
        )
        return Response(content=body, media_type=content_type, headers=headers)
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
