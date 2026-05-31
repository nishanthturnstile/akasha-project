"""Akasha BFF product endpoints (Slice 2 — Phase 2 raster de-risk).

Minimal product surface needed to verify the raster proof path end-to-end:

  * GET  /api/config
  * GET  /api/sources
  * GET  /api/sources/{sourceId}/dates
  * GET  /api/layers/default
  * GET  /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png   (BFF->TiTiler proxy)
  * POST /api/indices/statistics                                       (BFF masked NDVI)

Design notes:
  * The tile route lives under `/api/tiles/...` (not `/tiles/...`) so it is
    reachable both behind the Caddy gateway (`/api/*` -> api) and the Emergent
    ingress (which routes only `/api/*` to the backend). MinIO object URLs and
    credentials stay server-side.
  * Heavy geospatial deps (rasterio/shapely/pyproj) are imported lazily inside
    `app.raster.*`, so importing this module never requires them.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import Response

from .config import settings
from .raster import catalog_resolver as catalog
from .raster import tiles
from .raster.errors import bad_request
from .raster.indices import DEFAULT_INDEX, SUPPORTED_INDICES, rgb_band_positions
from .raster.models import StatisticsRequest
from .raster.service import compute_statistics

router = APIRouter(prefix="/api", tags=["product"])

# Bangalore AOI defaults (data-ingestion/architecture). Configurable, not magic
# in components — the frontend reads these from /api/config.
_AOI = {
    "id": "bangalore",
    "name": "Bangalore",
    "center": [77.59, 12.97],
    "zoom": 11,
    "bounds": [77.4, 12.8, 77.8, 13.2],
}
_ATTRIBUTION = "Copernicus Sentinel-2"


def _basemap_style_url() -> str:
    return os.environ.get("VITE_BASEMAP_STYLE_URL") or os.environ.get("BASEMAP_STYLE_URL", "")


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """App configuration: AOI, map defaults, limits, supported indices."""
    return {
        "appName": os.environ.get("PUBLIC_APP_NAME", "Akasha"),
        "aoi": _AOI,
        "basemapStyleUrl": _basemap_style_url(),
        "maxPolygonAreaHa": settings.max_polygon_area_ha,
        "maxPolygonVertices": settings.max_polygon_vertices,
        "usablePixelThresholdPercent": settings.usable_pixel_threshold_percent,
        "supportedIndices": SUPPORTED_INDICES,
        "defaultIndex": DEFAULT_INDEX,
    }


@router.get("/sources")
async def get_sources() -> list[dict[str, Any]]:
    """Satellite/product source list derived from STAC collections."""
    source_id = catalog.COLLECTION_ID
    return [
        {
            "id": source_id,
            "label": catalog.SOURCE_LABEL,
            "provider": catalog.SOURCE_PROVIDER,
            "supportedIndices": catalog.supported_indices(source_id),
        }
    ]


@router.get("/sources/{source_id}/dates")
async def get_source_dates(source_id: str) -> list[dict[str, Any]]:
    """Available acquisition dates with AOI cloud/usable-pixel percentages."""
    return catalog.list_dates(source_id)


@router.get("/layers/default")
async def get_default_layer() -> dict[str, Any]:
    """Default source/date/layer metadata + same-origin RGB tile template."""
    source_id = catalog.COLLECTION_ID
    item = catalog.latest_item(source_id)
    props = item.get("properties", {})
    acquisition_date = props.get("akasha:acquisition_date") or (props.get("datetime", "") or "")[:10]
    return {
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "tileUrlTemplate": (
            f"/api/tiles/{source_id}/{acquisition_date}/rgb/{{z}}/{{x}}/{{y}}.png"
        ),
        "bounds": item.get("bbox"),
        "minzoom": 8,
        "maxzoom": 14,
        "attribution": _ATTRIBUTION,
        "usablePixelPercent": props.get("akasha:usable_pixel_percent"),
        "metricsProvisional": bool(props.get("akasha:metrics_provisional", False)),
    }


@router.get("/tiles/{source_id}/{acquisition_date}/rgb/{z}/{x}/{y}.png")
async def get_rgb_tile(
    source_id: str, acquisition_date: str, z: int, x: int, y: int
) -> Response:
    """Proxy one true-colour RGB PNG tile from TiTiler (server-side).

    Builds the TiTiler request from the analytic COG + RGB band positions
    [1, 8, 9] = (B04, B03, B02). The COG url/credentials are never exposed to
    the browser. Raises AkashaError (502/503) if TiTiler/MinIO is unavailable.
    """
    assets = catalog.resolve_assets(source_id, acquisition_date)
    positions = rgb_band_positions(assets["bandNames"])
    url = tiles.build_rgb_tile_url(
        analytic_href=assets["analyticHref"],
        rgb_positions=positions,
        z=z,
        x=x,
        y=y,
    )
    body, content_type = tiles.fetch_tile(url)
    return Response(content=body, media_type=content_type)


@router.post("/indices/statistics")
async def post_index_statistics(payload: StatisticsRequest = Body(...)) -> dict[str, Any]:
    """Compute cloud/SCL-masked, offset-corrected index statistics in the BFF.

    Reads the analytic + SCL COG windows for the request polygon via rasterio,
    applies per-band scale/offset, applies the SCL mask, then computes
    min/max/mean/stddev and the pixel-percentage fields.
    """
    geometry = payload.geometry.model_dump()
    if not payload.sourceId:
        raise bad_request("sourceId is required.", code="MISSING_SOURCE")
    return compute_statistics(
        geometry=geometry,
        source_id=payload.sourceId,
        acquisition_date=payload.acquisitionDate,
        index_type=payload.indexType or DEFAULT_INDEX,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
    )
