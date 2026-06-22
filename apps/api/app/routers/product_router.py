"""Akasha BFF product endpoints (Slice 2 — Phase 2 raster de-risk).

Minimal product surface needed to verify the raster proof path end-to-end:

  * GET  /api/config
  * GET  /api/sources
  * GET  /api/sources/{sourceId}/dates
  * GET  /api/layers/default
  * GET  /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png   (legacy RGB)
  * GET  /api/tiles/{sourceId}/{acquisitionDate}/{displayMode}/{z}/{x}/{y}.png
  * POST /api/indices/statistics                                       (BFF masked NDVI)
"""

from __future__ import annotations

import asyncio
from functools import partial
import os
import time
from datetime import date, timedelta
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from ..aoi import load_aoi_configs, select_default_aoi
from ..auth import get_current_team
from ..config import settings
from ..raster import catalog_resolver as catalog
from ..raster import tiles
from ..raster.errors import (
    bad_request,
    index_timeout,
    mosaic_tiles_unavailable,
    rate_limited,
    upstream_error,
)
from ..raster.indices import (
    DEFAULT_INDEX,
    SUPPORTED_INDICES,
    fcc_band_positions,
    get_index,
    index_tile_expression,
    rgb_band_positions,
)
from ..raster.models import StatisticsRequest, StatisticsResponse
from ..raster.service import compute_statistics

router = APIRouter(prefix="/api", tags=["product"], dependencies=[Depends(get_current_team)])

_RATE_BUCKETS: dict[str, list[float]] = {}


def _basemap_config() -> dict[str, Any]:
    return {
        "provider": settings.basemap_provider,
        "style": settings.esri_basemap_style,
        "styleFamily": settings.esri_basemap_style_family,
        "usageModel": settings.esri_basemap_usage_model,
        "places": settings.esri_basemap_places,
        "sessionDurationSeconds": settings.esri_basemap_session_seconds,
    }


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _enforce_index_rate_limit(request: Request) -> None:
    limit = settings.rate_limit_index_per_minute
    if limit <= 0:
        return
    now = time.monotonic()
    cutoff = now - 60.0
    client_id = _client_id(request)
    hits = [ts for ts in _RATE_BUCKETS.get(client_id, []) if ts >= cutoff]
    if len(hits) >= limit:
        raise rate_limited(
            "Too many index-statistics requests. Please retry later.",
            limitPerMinute=limit,
        )
    hits.append(now)
    _RATE_BUCKETS[client_id] = hits


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """App configuration: AOI, map defaults, limits, and global optical index defaults."""
    aois = load_aoi_configs()
    return {
        "appName": os.environ.get("PUBLIC_APP_NAME", "Akasha"),
        "aoi": select_default_aoi(aois),
        "aois": aois,
        "basemapStyleUrl": "",
        "basemap": _basemap_config(),
        "maxPolygonAreaHa": settings.max_polygon_area_ha,
        "maxPolygonVertices": settings.max_polygon_vertices,
        "usablePixelThresholdPercent": settings.usable_pixel_threshold_percent,
        "supportedIndices": SUPPORTED_INDICES,
        "defaultIndex": DEFAULT_INDEX,
        "indexFieldsKind": "global-optical-defaults",
        "indexAvailabilitySource": "/api/sources",
    }


@router.get("/sources")
async def get_sources() -> list[dict[str, Any]]:
    """Satellite/product source list derived from the source registry/STAC metadata."""
    return catalog.list_sources()


def _filter_source_dates(
    dates: list[dict[str, Any]],
    *,
    start_date: date | None,
    end_date: date | None,
    lookback_days: int | None,
) -> list[dict[str, Any]]:
    """Optionally window source dates while preserving the newest-first contract."""
    if not dates or (start_date is None and end_date is None and lookback_days is None):
        return dates

    parsed: list[tuple[date, dict[str, Any]]] = []
    for entry in dates:
        raw = entry.get("acquisitionDate")
        if not isinstance(raw, str):
            continue
        try:
            parsed.append((date.fromisoformat(raw), entry))
        except ValueError:
            continue

    if not parsed:
        return []

    window_end = end_date or max(item_date for item_date, _entry in parsed)
    window_start = start_date
    if window_start is None and lookback_days is not None:
        window_start = window_end - timedelta(days=lookback_days - 1)

    if window_start and window_start > window_end:
        raise bad_request(
            "startDate must be on or before endDate.",
            code="INVALID_DATE_RANGE",
            startDate=window_start.isoformat(),
            endDate=window_end.isoformat(),
        )

    return [
        entry
        for item_date, entry in parsed
        if (window_start is None or item_date >= window_start) and item_date <= window_end
    ]


@router.get("/sources/{source_id}/dates")
async def get_source_dates(
    source_id: str,
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    lookbackDays: int | None = Query(default=None, ge=1, le=366),
) -> list[dict[str, Any]]:
    """Available acquisition dates with source-specific metadata semantics."""
    return _filter_source_dates(
        catalog.list_dates(source_id),
        start_date=startDate,
        end_date=endDate,
        lookback_days=lookbackDays,
    )


@router.get("/layers/default")
async def get_default_layer(sourceId: str | None = None) -> dict[str, Any]:
    """Default source/date/layer metadata + same-origin tile template."""
    source_id = sourceId or settings.default_source_id or catalog.COLLECTION_ID
    source = catalog.get_source(source_id)
    dates = catalog.list_dates(source_id)
    selectable_dates = [d for d in dates if bool(d.get("tileAvailable", True))]
    date_pool = selectable_dates or dates
    map_display_modes = list(source.get("mapDisplayModes", source["displayModes"]))
    default_map_display_mode = str(
        source.get("defaultMapDisplayMode", source["defaultDisplayMode"])
    )
    if not date_pool:
        display_mode = default_map_display_mode
        return {
            "sourceId": source_id,
            "acquisitionDate": None,
            "displayMode": display_mode,
            "displayModes": source["displayModes"],
            "defaultDisplayMode": source["defaultDisplayMode"],
            "mapDisplayModes": map_display_modes,
            "defaultMapDisplayMode": default_map_display_mode,
            "kind": source["kind"],
            "tileUrlTemplate": None,
            "bounds": None,
            "minzoom": 8,
            "maxzoom": 14,
            "attribution": source["attribution"],
            "sceneCount": 0,
            "usablePixelPercent": None,
            "cloudMaskedPercent": None,
            "coveragePercent": None,
            "metricsProvisional": bool(source.get("metricsProvisional", False)),
            "tileAvailable": False,
            "unavailableReason": source.get("gatedReason") or "No catalog dates are available.",
        }
    date = next((d for d in date_pool if d["isLatestUsable"]), date_pool[0])
    acquisition_date = date["acquisitionDate"]
    items = catalog.items_for_date(source_id, acquisition_date)
    display_mode = default_map_display_mode
    tile_url_template = (
        None
        if display_mode in catalog.supported_indices(source_id)
        else catalog.tile_url_template(source_id, acquisition_date)
    )
    return {
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "displayMode": display_mode,
        "displayModes": source["displayModes"],
        "defaultDisplayMode": source["defaultDisplayMode"],
        "mapDisplayModes": map_display_modes,
        "defaultMapDisplayMode": default_map_display_mode,
        "kind": source["kind"],
        "tileUrlTemplate": tile_url_template,
        "bounds": catalog.merged_bbox(items),
        "minzoom": 8,
        "maxzoom": 14,
        "attribution": source["attribution"],
        "sceneCount": date.get("sceneCount"),
        "usablePixelPercent": date.get("usablePixelPercent"),
        "cloudMaskedPercent": date.get("cloudMaskedPercent"),
        "coveragePercent": date.get("coveragePercent"),
        "metricsProvisional": bool(date.get("metricsProvisional", False)),
        "tileAvailable": bool(date.get("tileAvailable", True)),
        "unavailableReason": date.get("unavailableReason"),
    }


async def _render_rgb_tile(
    source_id: str, acquisition_date: str, z: int, x: int, y: int
) -> Response:
    source = catalog.get_source(source_id)
    if "RGB" not in source["displayModes"]:
        raise bad_request(
            f"Display mode 'RGB' is not supported for source '{source_id}'.",
            code="UNSUPPORTED_DISPLAY_MODE",
            sourceId=source_id,
            displayMode="RGB",
            supportedDisplayModes=source["displayModes"],
        )

    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    assets = assets_for_date[0]
    try:
        positions = rgb_band_positions(assets["bandNames"])
        for item_assets in assets_for_date[1:]:
            item_positions = rgb_band_positions(item_assets["bandNames"])
            if item_positions != positions:
                raise upstream_error(
                    "Same-date STAC items use inconsistent RGB band positions.",
                    code="INCONSISTENT_RGB_BANDS",
                )
    except KeyError as exc:
        raise upstream_error(
            "STAC analytic asset is missing a required true-colour RGB band.",
            code="MISSING_RGB_BANDS",
            missingBand=str(exc).strip("'"),
            availableBands=assets.get("bandNames", []),
        ) from exc
    if len(assets_for_date) == 1:
        body, content_type = await anyio.to_thread.run_sync(
            partial(
                tiles.render_rgb_tile,
                analytic_href=assets["analyticHref"],
                rgb_positions=positions,
                z=z,
                x=x,
                y=y,
            )
        )
    else:
        url = tiles.build_mosaic_rgb_tile_url(
            analytic_hrefs=[item_assets["analyticHref"] for item_assets in assets_for_date],
            rgb_positions=positions,
            z=z,
            x=x,
            y=y,
        )
        body, content_type = await anyio.to_thread.run_sync(tiles.fetch_tile, url)
    return Response(content=body, media_type=content_type)


async def _render_sar_vv_grayscale_tile(
    source_id: str, acquisition_date: str, z: int, x: int, y: int
) -> Response:
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    if len(assets_for_date) != 1:
        raise mosaic_tiles_unavailable(
            "Date-level SAR tiles for multiple scenes require a configured mosaic backend.",
            sceneCount=len(assets_for_date),
            supportedSceneCount=1,
        )
    assets = assets_for_date[0]
    band_position = _sar_display_band_position(
        assets,
        source_id=source_id,
        acquisition_date=acquisition_date,
    )
    url = tiles.build_sar_vv_grayscale_tile_url(
        backscatter_href=assets["backscatterHref"],
        vv_position=band_position,
        z=z,
        x=x,
        y=y,
    )
    body, content_type = await anyio.to_thread.run_sync(tiles.fetch_tile, url)
    return Response(content=body, media_type=content_type)


def _sar_display_band_position(
    assets: dict[str, Any], *, source_id: str, acquisition_date: str
) -> int:
    """Resolve the backscatter band to render in grayscale.

    Prefer VV when present (Sentinel-1, quad-pol NISAR); otherwise fall back to
    the first backscatter band so single-/dual-pol products without VV (e.g.
    EOS-04 SAR-MRS HH/HV) still render. SAR display is polarization-agnostic
    grayscale backscatter and the href stays internal (proxied via the BFF).
    """
    band_names = [str(name) for name in assets.get("bandNames", [])]
    for index, name in enumerate(band_names, start=1):
        normalized = name.strip().upper()
        if normalized == "VV" or normalized.startswith("VV_") or normalized.startswith("VV-"):
            return index
    if band_names:
        return 1
    raise bad_request(
        "SAR backscatter display requires at least one backscatter band.",
        code="MISSING_BACKSCATTER_BAND",
        sourceId=source_id,
        acquisitionDate=acquisition_date,
        itemId=assets.get("itemId"),
        availablePolarizations=band_names,
    )


async def _render_context_tile(
    source_id: str, acquisition_date: str, display_mode: str, z: int, x: int, y: int
) -> Response:
    source = catalog.get_source(source_id)
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    if len(assets_for_date) != 1:
        raise mosaic_tiles_unavailable(
            (
                f"Date-level {display_mode} tiles for multiple scenes require a configured "
                "mosaic backend."
            ),
            sceneCount=len(assets_for_date),
            supportedSceneCount=1,
        )
    assets = assets_for_date[0]
    mode = display_mode.upper()
    bidx = [1] if mode == "NDVI_CONTEXT" else None
    colormap_name = "rdylgn" if mode == "NDVI_CONTEXT" else None
    url = tiles.build_context_tile_url(
        asset_href=assets["contextHref"],
        z=z,
        x=x,
        y=y,
        rescale=source.get("defaultRescale"),
        bidx=bidx,
        colormap_name=colormap_name,
    )
    body, content_type = await anyio.to_thread.run_sync(tiles.fetch_tile, url)
    return Response(content=body, media_type=content_type)


async def _render_fcc_tile(
    source_id: str, acquisition_date: str, z: int, x: int, y: int
) -> Response:
    source = catalog.get_source(source_id)
    if "FCC" not in source["displayModes"]:
        raise bad_request(
            f"Display mode 'FCC' is not supported for source '{source_id}'.",
            code="UNSUPPORTED_DISPLAY_MODE",
            sourceId=source_id,
            displayMode="FCC",
            supportedDisplayModes=source["displayModes"],
        )

    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    assets = assets_for_date[0]
    try:
        positions = fcc_band_positions(assets["bandNames"], assets.get("bandRoleMapping", {}))
        for item_assets in assets_for_date[1:]:
            item_positions = fcc_band_positions(
                item_assets["bandNames"], item_assets.get("bandRoleMapping", {})
            )
            if item_positions != positions:
                raise upstream_error(
                    "Same-date STAC items use inconsistent FCC band positions.",
                    code="INCONSISTENT_FCC_BANDS",
                )
    except KeyError as exc:
        raise upstream_error(
            "STAC analytic asset is missing a required false-colour composite role.",
            code="MISSING_FCC_BANDS",
            missingRole=str(exc).strip("'"),
            availableBands=assets.get("bandNames", []),
            bandRoleMapping=assets.get("bandRoleMapping", {}),
        ) from exc

    if len(assets_for_date) == 1:
        body, content_type = await anyio.to_thread.run_sync(
            partial(
                tiles.render_rgb_tile,
                analytic_href=assets["analyticHref"],
                rgb_positions=positions,
                z=z,
                x=x,
                y=y,
            )
        )
    else:
        url = tiles.build_mosaic_rgb_tile_url(
            analytic_hrefs=[item_assets["analyticHref"] for item_assets in assets_for_date],
            rgb_positions=positions,
            z=z,
            x=x,
            y=y,
        )
        body, content_type = await anyio.to_thread.run_sync(tiles.fetch_tile, url)
    return Response(content=body, media_type=content_type)


async def _render_index_tile(
    source_id: str, acquisition_date: str, index_type: str, z: int, x: int, y: int
) -> Response:
    """Render a colorized, reflectance-corrected index tile (NDVI/NDRE/MSAVI/NDMI).

    Phase 1 is unmasked: TiTiler computes the index expression from the analytic
    COG and colorizes it. Clouds are not SCL-masked here (the BFF statistics path
    remains the masked, analytic source of truth).
    """
    index_def = get_index(index_type)
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    if len(assets_for_date) != 1:
        raise mosaic_tiles_unavailable(
            "Date-level index tiles for multiple scenes require a configured mosaic backend.",
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
            offset=float(assets.get("offset", 0.0)),
        )
    except KeyError as exc:
        raise upstream_error(
            "STAC analytic asset is missing a band required for this index.",
            code="MISSING_INDEX_BANDS",
            indexType=index_type,
            missingRole=str(exc).strip("'"),
            availableBands=assets.get("bandNames", []),
            bandRoleMapping=assets.get("bandRoleMapping", {}),
        ) from exc
    url = tiles.build_index_tile_url(
        analytic_href=assets["analyticHref"],
        expression=expression,
        rescale=index_def.display_rescale_str,
        colormap_name=index_def.display_colormap,
        z=z,
        x=x,
        y=y,
    )
    body, content_type = await anyio.to_thread.run_sync(tiles.fetch_tile, url)
    return Response(content=body, media_type=content_type)


@router.get("/tiles/{source_id}/{acquisition_date}/rgb/{z}/{x}/{y}.png")
async def get_rgb_tile(source_id: str, acquisition_date: str, z: int, x: int, y: int) -> Response:
    """Legacy same-origin RGB tile route preserved for Sentinel-2 compatibility."""
    return await _render_rgb_tile(source_id, acquisition_date, z, x, y)


@router.get("/tiles/{source_id}/{acquisition_date}/{display_mode}/{z}/{x}/{y}.png")
async def get_display_mode_tile(
    source_id: str, acquisition_date: str, display_mode: str, z: int, x: int, y: int
) -> Response:
    """Display-mode-aware same-origin tile route."""
    source = catalog.get_source(source_id)
    normalized_mode = display_mode.upper()
    if normalized_mode not in source["displayModes"]:
        raise bad_request(
            f"Display mode '{display_mode}' is not supported for source '{source_id}'.",
            code="UNSUPPORTED_DISPLAY_MODE",
            sourceId=source_id,
            displayMode=display_mode,
            supportedDisplayModes=source["displayModes"],
        )
    if normalized_mode == "RGB":
        return await _render_rgb_tile(source_id, acquisition_date, z, x, y)
    if normalized_mode == "FCC":
        return await _render_fcc_tile(source_id, acquisition_date, z, x, y)
    if normalized_mode == "VV_GRAYSCALE":
        return await _render_sar_vv_grayscale_tile(source_id, acquisition_date, z, x, y)
    if normalized_mode in catalog.supported_indices(source_id):
        return await _render_index_tile(source_id, acquisition_date, normalized_mode, z, x, y)
    if normalized_mode in {"CONTEXT", "NDVI_CONTEXT"}:
        return await _render_context_tile(source_id, acquisition_date, normalized_mode, z, x, y)
    raise bad_request(
        f"Display mode '{display_mode}' is not implemented for source '{source_id}'.",
        code="UNSUPPORTED_DISPLAY_MODE",
        sourceId=source_id,
        displayMode=display_mode,
        supportedDisplayModes=source["displayModes"],
    )


@router.post("/indices/statistics", response_model=StatisticsResponse)
async def post_index_statistics(
    request: Request, payload: StatisticsRequest = Body(...)
) -> dict[str, Any]:
    """Compute source-mask-aware, offset-corrected optical index statistics."""
    geometry = payload.geometry.model_dump()
    if not payload.sourceId:
        raise bad_request("sourceId is required.", code="MISSING_SOURCE")
    _enforce_index_rate_limit(request)

    def _compute() -> dict[str, Any]:
        return compute_statistics(
            geometry=geometry,
            source_id=payload.sourceId,
            acquisition_date=payload.acquisitionDate,
            index_type=payload.indexType or DEFAULT_INDEX,
            max_area_ha=settings.max_polygon_area_ha,
            max_vertices=settings.max_polygon_vertices,
        )

    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(_compute),
            timeout=settings.index_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise index_timeout(
            "Index-statistics request exceeded INDEX_REQUEST_TIMEOUT_SECONDS.",
            timeoutSeconds=settings.index_request_timeout_seconds,
        ) from exc
