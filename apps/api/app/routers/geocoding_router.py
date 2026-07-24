from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query

from ..auth import get_current_team
from ..raster.errors import AkashaError, upstream_error

router = APIRouter(
    prefix="/api/geocoding",
    tags=["geocoding"],
    dependencies=[Depends(get_current_team)],
)

_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_CACHE_TTL_SECONDS = 300
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def _search_provider(query: str) -> list[dict[str, Any]]:
    headers = {
        "Accept-Language": "en",
        "User-Agent": "AkashaCropMonitoring/1.0 (location-search)",
    }
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": "5",
        "addressdetails": "0",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            response = await client.get(_NOMINATIM_SEARCH_URL, params=params, headers=headers)
    except httpx.TimeoutException as exc:
        raise AkashaError(
            "GEOCODING_TIMEOUT",
            "Location search timed out. Please try again.",
            504,
        ) from exc
    except httpx.HTTPError as exc:
        raise upstream_error(
            "Location search is temporarily unavailable.",
            code="GEOCODING_UNAVAILABLE",
        ) from exc

    if response.status_code == 429:
        raise AkashaError(
            "GEOCODING_RATE_LIMITED",
            "Location search is busy. Please wait a moment and try again.",
            429,
        )
    if response.is_error:
        raise upstream_error(
            "Location search is temporarily unavailable.",
            code="GEOCODING_UNAVAILABLE",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise upstream_error(
            "Location search returned an invalid response.",
            code="GEOCODING_INVALID_RESPONSE",
        ) from exc
    if not isinstance(payload, list):
        raise upstream_error(
            "Location search returned an invalid response.",
            code="GEOCODING_INVALID_RESPONSE",
        )
    return payload


@router.get("/search")
async def search_locations(
    q: str = Query(min_length=2, max_length=120),
) -> dict[str, list[dict[str, Any]]]:
    normalized = " ".join(q.split())
    cache_key = normalized.casefold()
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return {"results": cached[1]}

    payload = await _search_provider(normalized)
    results: list[dict[str, Any]] = []
    for item in payload:
        try:
            longitude = float(item["lon"])
            latitude = float(item["lat"])
            bounds = item.get("boundingbox")
            bbox = (
                [
                    float(bounds[2]),
                    float(bounds[0]),
                    float(bounds[3]),
                    float(bounds[1]),
                ]
                if isinstance(bounds, list) and len(bounds) == 4
                else None
            )
            label = str(item["display_name"]).strip()
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if not label or not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            continue
        results.append(
            {
                "label": label,
                "center": [longitude, latitude],
                "bbox": bbox,
                "type": "place",
            }
        )

    if len(_CACHE) >= 256:
        oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
        _CACHE.pop(oldest, None)
    _CACHE[cache_key] = (time.monotonic(), results)
    return {"results": results}
