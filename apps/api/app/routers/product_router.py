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
import os
import time
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from ..aoi import load_aoi_config
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
    rgb_band_positions,
)
from ..raster.models import StatisticsRequest
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
    return {
        "appName": os.environ.get("PUBLIC_APP_NAME", "Akasha"),
        "aoi": load_aoi_config(),
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


@router.get("/sources/{source_id}/dates")
async def get_source_dates(source_id: str) -> list[dict[str, Any]]:
    """Available acquisition dates with source-specific metadata semantics."""
    return catalog.list_dates(source_id)


@router.get("/layers/default")
async def get_default_layer(sourceId: str | None = None) -> dict[str, Any]:
    """Default source/date/layer metadata + same-origin tile template."""
    source_id = sourceId or settings.default_source_id or catalog.COLLECTION_ID
    source = catalog.get_source(source_id)
    dates = catalog.list_dates(source_id)
    selectable_dates = [d for d in dates if bool(d.get("tileAvailable", True))]
    date_pool = selectable_dates or dates
    if not date_pool:
        display_mode = source["defaultDisplayMode"]
        return {
            "sourceId": source_id,
            "acquisitionDate": None,
            "displayMode": display_mode,
            "displayModes": source["displayModes"],
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
    display_mode = source["defaultDisplayMode"]
    return {
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "displayMode": display_mode,
        "displayModes": source["displayModes"],
        "kind": source["kind"],
        "tileUrlTemplate": catalog.tile_url_template(source_id, acquisition_date),
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
        url = tiles.build_rgb_tile_url(
            analytic_href=assets["analyticHref"],
            rgb_positions=positions,
            z=z,
            x=x,
            y=y,
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


async def _render_sentinel1_vv_tile(
    source_id: str, acquisition_date: str, z: int, x: int, y: int
) -> Response:
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    if len(assets_for_date) != 1:
        raise mosaic_tiles_unavailable(
            "Date-level Sentinel-1 tiles for multiple scenes require a configured mosaic backend.",
            sceneCount=len(assets_for_date),
            supportedSceneCount=1,
        )
    url = tiles.build_sentinel1_vv_tile_url(
        backscatter_href=assets_for_date[0]["backscatterHref"],
        z=z,
        x=x,
        y=y,
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
        url = tiles.build_rgb_tile_url(
            analytic_href=assets["analyticHref"],
            rgb_positions=positions,
            z=z,
            x=x,
            y=y,
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
        return await _render_sentinel1_vv_tile(source_id, acquisition_date, z, x, y)
    raise bad_request(
        f"Display mode '{display_mode}' is not implemented for source '{source_id}'.",
        code="UNSUPPORTED_DISPLAY_MODE",
        sourceId=source_id,
        displayMode=display_mode,
        supportedDisplayModes=source["displayModes"],
    )


@router.post("/indices/statistics")
async def post_index_statistics(
    request: Request, payload: StatisticsRequest = Body(...)
) -> dict[str, Any]:
    """Compute cloud/SCL-masked, offset-corrected optical index statistics."""
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
