"""Small server-to-server client for the standalone Akasha ingestion API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import Settings
from .raster.errors import upstream_error


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
            timeout=settings.ingestion_request_timeout_seconds,
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


def get_readiness(settings: Settings, *, source_id: str, aoi_id: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"sourceId": source_id, "aoiId": aoi_id})
    response = _request_json(settings, f"/api/v1/analytics/readiness?{query}")
    return response.get("data") if response.get("success") else None


def request_field_index(
    settings: Settings,
    *,
    geometry: dict[str, Any],
    field_id: str,
    index_type: str,
    acquisition_date: str,
    max_cloud_percentage: float = 20.0,
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
    )
    data = response.get("data")
    if not response.get("success") or not isinstance(data, dict):
        raise upstream_error(
            "Standalone ingestion field-index request failed.",
            code="INGESTION_FIELD_INDEX_ERROR",
        )
    return data


def fetch_signed_ingestion_binary(
    settings: Settings,
    url: str,
) -> tuple[bytes, str, dict[str, str]]:
    base = _base_url(settings)
    if not url.startswith(f"{base}/"):
        raise upstream_error(
            "Standalone ingestion returned an unexpected signed URL.",
            code="INGESTION_UPSTREAM_FORBIDDEN",
        )
    try:
        with urllib.request.urlopen(  # noqa: S310 - signed URL is prefix-allowlisted above
            url,
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
