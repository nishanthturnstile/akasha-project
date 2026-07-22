from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, model_validator

from ..auth import get_current_team
from ..config import settings
from ..ingestion_client import (
    fetch_latest_imagery_thumbnail,
    fetch_latest_imagery_tile,
    search_latest_imagery,
)
from ..raster.errors import bad_request

router = APIRouter(
    prefix="/api/imagery",
    tags=["imagery"],
    dependencies=[Depends(get_current_team)],
)
logger = logging.getLogger("akasha.api.latest_imagery")
_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SEARCH_CACHE_TTL_SECONDS = 300


class LatestImagerySearchRequest(BaseModel):
    viewport: dict[str, Any]

    @model_validator(mode="after")
    def validate_viewport(self):
        if self.viewport.get("type") != "Polygon":
            raise ValueError("viewport must be a GeoJSON Polygon")
        coordinates = self.viewport.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("viewport coordinates are required")
        ring = coordinates[0]
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("viewport exterior ring requires at least four positions")
        if any(
            not isinstance(point, list)
            or len(point) < 2
            or not all(isinstance(value, (int, float)) for value in point[:2])
            for point in ring
        ):
            raise ValueError("viewport positions must contain numeric longitude and latitude")
        if ring[0][:2] != ring[-1][:2]:
            raise ValueError("viewport exterior ring must be closed")
        return self


def _viewport_diagonal_meters(viewport: dict[str, Any]) -> float:
    ring = viewport["coordinates"][0]
    longitudes = [float(point[0]) for point in ring]
    latitudes = [float(point[1]) for point in ring]
    west, east = min(longitudes), max(longitudes)
    south, north = min(latitudes), max(latitudes)
    mean_lat = math.radians((south + north) / 2)
    dx = math.radians(east - west) * 6_371_008.8 * math.cos(mean_lat)
    dy = math.radians(north - south) * 6_371_008.8
    return math.hypot(dx, dy)


@router.post("/search")
async def search_latest(payload: LatestImagerySearchRequest) -> dict[str, Any]:
    if not settings.latest_imagery_enabled:
        raise bad_request("Latest Image is not enabled.", code="LATEST_IMAGERY_NOT_ENTITLED")
    diagonal = _viewport_diagonal_meters(payload.viewport)
    if diagonal > settings.latest_imagery_max_viewport_meters:
        raise bad_request(
            "Zoom in before searching for imagery.",
            code="LATEST_IMAGERY_VIEWPORT_TOO_LARGE",
            diagonalMeters=round(diagonal),
            maximumMeters=settings.latest_imagery_max_viewport_meters,
        )
    normalized_viewport = json.dumps(payload.viewport, sort_keys=True, separators=(",", ":"))
    cache_key = ":".join(
        (
            "latest-image-s2-l2a-v1",
            normalized_viewport,
            "365",
            "sentinel-2-l2a",
            "L2A",
            "10",
            str(settings.latest_imagery_result_limit),
        )
    )
    started = time.monotonic()
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL_SECONDS:
        result = cached[1]
    else:
        result = search_latest_imagery(
            settings,
            viewport=payload.viewport,
            source_id="sentinel-2-l2a",
            processing_level="L2A",
            lookback_days=365,
            max_cloud_percent=10,
            limit=settings.latest_imagery_result_limit,
        )
        if len(_SEARCH_CACHE) >= 256:
            oldest = min(_SEARCH_CACHE, key=lambda key: _SEARCH_CACHE[key][0])
            _SEARCH_CACHE.pop(oldest, None)
        _SEARCH_CACHE[cache_key] = (time.monotonic(), result)
    candidates = []
    for candidate in result.get("candidates", []):
        scene_id = str(candidate["sceneId"])
        candidates.append(
            {
                key: candidate.get(key)
                for key in (
                    "sceneId",
                    "acquisitionDate",
                    "acquisitionDatetime",
                    "sourceId",
                    "sensor",
                    "processingLevel",
                    "cloudPercent",
                    "coveragePercent",
                    "coverageStatus",
                    "usable",
                    "bounds",
                    "unavailableReason",
                )
            }
            | {
                "tileUrlTemplate": f"/api/imagery/scenes/{scene_id}/tiles/{{z}}/{{x}}/{{y}}.png",
                "thumbnailUrl": f"/api/imagery/scenes/{scene_id}/thumbnail.png",
            }
        )
    logger.info(
        "latest imagery search completed duration_ms=%d result_count=%d cached=%s",
        round((time.monotonic() - started) * 1000),
        len(candidates),
        bool(cached),
    )
    return {**result, "candidates": candidates, "viewportDiagonalMeters": round(diagonal, 2)}


@router.get("/scenes/{scene_id}/tiles/{z}/{x}/{y}.png")
async def latest_tile(scene_id: str, z: int, x: int, y: int) -> Response:
    content, content_type = fetch_latest_imagery_tile(settings, scene_id=scene_id, z=z, x=x, y=y)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/scenes/{scene_id}/thumbnail.png")
async def latest_thumbnail(scene_id: str) -> Response:
    content, content_type = fetch_latest_imagery_thumbnail(settings, scene_id=scene_id)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
