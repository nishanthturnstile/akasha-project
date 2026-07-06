"""Small server-to-server client for the standalone Akasha ingestion API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import Settings
from .raster.errors import upstream_error

_POINT_CACHE_TTL_SECONDS = 60.0
_FIELD_INDEX_POINT_CACHE: dict[tuple[str, str, str, str], tuple[float, str, str]] = {}


def is_ingestion_configured(settings: Settings) -> bool:
    return bool(settings.ingestion_api_url.strip() and settings.ingestion_api_key.strip())


def _base_url(settings: Settings) -> str:
    return settings.ingestion_api_url.rstrip("/")


def _request_json(
    settings: Settings,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if not is_ingestion_configured(settings):
        raise upstream_error(
            "Standalone ingestion API is not configured.",
            code="INGESTION_API_UNCONFIGURED",
        )

    body = None
    headers = {
        "Accept": "application/json",
        "X-API-Key": settings.ingestion_api_key,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{_base_url(settings)}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - private, configured upstream
            request,
            timeout=timeout_seconds or settings.ingestion_request_timeout_seconds,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = "Standalone ingestion API returned an error."
        try:
            details = json.loads(exc.read().decode("utf-8"))
            message = str(details.get("error", {}).get("message") or message)
        except Exception:  # noqa: BLE001
            details = {"status": exc.code}
        raise upstream_error(
            message,
            code="INGESTION_API_ERROR",
            upstreamStatus=exc.code,
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise upstream_error(
            "Standalone ingestion API is unreachable.",
            code="INGESTION_API_UNREACHABLE",
        ) from exc


def get_readiness(
    settings: Settings,
    *,
    source_id: str,
    aoi_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"sourceId": source_id, "aoiId": aoi_id})
    response = _request_json(
        settings,
        f"/api/v1/analytics/readiness?{query}",
        timeout_seconds=timeout_seconds,
    )
    return response.get("data") if response.get("success") else None


def request_field_index(
    settings: Settings,
    *,
    geometry: dict[str, Any],
    field_id: str,
    index_type: str,
    acquisition_date: str,
    max_cloud_percentage: float = 20.0,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    payload = {
        "geometry": geometry,
        "crs": "EPSG:4326",
        "index": index_type,
        "date": acquisition_date,
        "fallbackPolicy": "nearest_valid_scene",
        "maxCloudPercentage": max_cloud_percentage,
        "fieldId": field_id,
    }
    response = _request_json(
        settings,
        "/api/v1/analytics/field-index",
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    data = response.get("data")
    if not response.get("success") or not isinstance(data, dict):
        raise upstream_error(
            "Standalone ingestion field-index request failed.",
            code="INGESTION_FIELD_INDEX_ERROR",
        )
    return data


def _validate_and_rewrite_signed_url(settings: Settings, url: str) -> str:
    allowed_prefix = settings.ingestion_signed_url_allowed_prefix.rstrip("/")
    if not allowed_prefix or not url.startswith(f"{allowed_prefix}/"):
        raise upstream_error(
            "Standalone ingestion returned an unexpected signed URL.",
            code="INGESTION_UPSTREAM_FORBIDDEN",
        )
    fetch_prefix = (settings.ingestion_signed_url_fetch_prefix or allowed_prefix).rstrip("/")
    return fetch_prefix + url[len(allowed_prefix) :]


def fetch_signed_ingestion_binary(
    settings: Settings,
    url: str,
) -> tuple[bytes, str, dict[str, str]]:
    fetch_url = _validate_and_rewrite_signed_url(settings, url)
    try:
        with urllib.request.urlopen(  # noqa: S310 - signed URL is prefix-allowlisted above
            fetch_url,
            timeout=settings.ingestion_request_timeout_seconds,
        ) as response:
            headers = {key: value for key, value in response.headers.items()}
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return response.read(), content_type, headers
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise upstream_error(
            "Could not fetch standalone ingestion overlay.",
            code="INGESTION_OVERLAY_FETCH_FAILED",
        ) from exc


def fetch_signed_ingestion_json(settings: Settings, url: str) -> dict[str, Any]:
    fetch_url = _validate_and_rewrite_signed_url(settings, url)
    try:
        with urllib.request.urlopen(  # noqa: S310 - signed URL is prefix-allowlisted above
            fetch_url,
            timeout=settings.ingestion_request_timeout_seconds,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise upstream_error(
            "Could not fetch standalone ingestion JSON.",
            code="INGESTION_SIGNED_JSON_FETCH_FAILED",
        ) from exc


def _append_point_coordinates(point_url: str, *, lng: float, lat: float) -> str:
    parsed = urllib.parse.urlsplit(point_url)
    coordinates = urllib.parse.urlencode({"lng": lng, "lat": lat})
    query = f"{parsed.query}&{coordinates}" if parsed.query else coordinates
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _cached_point_url(
    key: tuple[str, str, str, str],
) -> tuple[str, str] | None:
    cached = _FIELD_INDEX_POINT_CACHE.get(key)
    if cached is None:
        return None
    expires_at, query_id, point_url = cached
    if expires_at <= time.monotonic():
        _FIELD_INDEX_POINT_CACHE.pop(key, None)
        return None
    return query_id, point_url


def _store_point_url(key: tuple[str, str, str, str], query_id: str, point_url: str) -> None:
    _FIELD_INDEX_POINT_CACHE[key] = (
        time.monotonic() + _POINT_CACHE_TTL_SECONDS,
        query_id,
        point_url,
    )


def request_field_index_point(
    settings: Settings,
    *,
    geometry: dict[str, Any],
    field_id: str,
    source_id: str,
    index_type: str,
    acquisition_date: str,
    lng: float,
    lat: float,
    max_cloud_percentage: float = 20.0,
) -> dict[str, Any]:
    key = (field_id, source_id, acquisition_date, index_type.upper())
    cached = _cached_point_url(key)
    if cached is None:
        result = request_field_index(
            settings,
            geometry=geometry,
            field_id=field_id,
            index_type=index_type,
            acquisition_date=acquisition_date,
            max_cloud_percentage=max_cloud_percentage,
        )
        if result.get("status") != "AVAILABLE":
            raise upstream_error(
                "Standalone ingestion point lookup is unavailable for this field/date.",
                code="INGESTION_POINT_UNAVAILABLE",
                reason=result.get("reason"),
            )
        query_id = str(result.get("queryId") or "")
        point_url = str(result.get("pointUrl") or "")
        if not query_id or not point_url:
            raise upstream_error(
                "Standalone ingestion point lookup is not available for this field/date.",
                code="INGESTION_POINT_UNAVAILABLE",
            )
        _store_point_url(key, query_id, point_url)
    else:
        query_id, point_url = cached

    point_response = fetch_signed_ingestion_json(
        settings,
        _append_point_coordinates(point_url, lng=lng, lat=lat),
    )
    if point_response.get("success") is False:
        raise upstream_error(
            "Standalone ingestion point lookup failed.",
            code="INGESTION_POINT_FETCH_FAILED",
        )
    data = point_response.get("data")
    if isinstance(data, dict):
        data.setdefault("queryId", query_id)
        return data
    if isinstance(point_response, dict):
        point_response.setdefault("queryId", query_id)
    return point_response
