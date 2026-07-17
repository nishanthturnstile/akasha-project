#!/usr/bin/env python3
"""Live acceptance check across akasha-control and akasha-staging.

Required environment variables:
AKASHA_APP_URL, AKASHA_INGESTION_URL, AKASHA_INGESTION_API_KEY,
AKASHA_APP_USERNAME, and AKASHA_APP_PASSWORD.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

SOURCES = (
    "sentinel-2-l2a",
    "resourcesat-2a-liss3-boa",
    "resourcesat-2a-liss4-mx70-l2",
    "resourcesat-2a-awifs-boa",
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _json_request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def _url(base: str, path: str, **query: str) -> str:
    url = f"{base.rstrip('/')}{path}"
    return f"{url}?{urllib.parse.urlencode(query)}" if query else url


def main() -> int:
    try:
        app_url = _required("AKASHA_APP_URL")
        ingestion_url = _required("AKASHA_INGESTION_URL")
        ingestion_key = _required("AKASHA_INGESTION_API_KEY")
        username = _required("AKASHA_APP_USERNAME")
        password = _required("AKASHA_APP_PASSWORD")
        aoi_id = os.environ.get("AKASHA_INGESTION_AOI_ID", "bangalore_60km_geodesic_aoi")

        ingestion = urllib.request.build_opener()
        ingestion_headers = {"X-API-Key": ingestion_key}
        readiness_dates: dict[str, str] = {}
        for source_id in SOURCES:
            envelope = _json_request(
                ingestion,
                _url(
                    ingestion_url,
                    "/api/v1/analytics/readiness",
                    sourceId=source_id,
                    aoiId=aoi_id,
                ),
                headers=ingestion_headers,
            )
            readiness = envelope.get("data") or {}
            dates = readiness.get("availableDates") or []
            if readiness.get("status") != "AVAILABLE" or not dates:
                reasons = readiness.get("unavailableReasons") or []
                raise RuntimeError(f"{source_id} ingestion readiness failed: {reasons}")
            readiness_dates[source_id] = max(str(value) for value in dates)

        cookie_jar = CookieJar()
        app = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        _json_request(
            app,
            _url(app_url, "/api/auth/login"),
            method="POST",
            payload={"username": username, "password": password, "rememberMe": False},
        )
        source_payloads = _json_request(app, _url(app_url, "/api/sources"))
        sources_by_id = {item["id"]: item for item in source_payloads}
        if set(sources_by_id) != set(SOURCES):
            raise RuntimeError(f"web app source contract mismatch: {sorted(sources_by_id)}")
        for source_id in SOURCES:
            if sources_by_id[source_id].get("pipelineBacked") is not True:
                raise RuntimeError(f"{source_id} is not advertised as pipelineBacked")

        fields = _json_request(app, _url(app_url, "/api/fields"))
        configured_field = os.environ.get("AKASHA_ACCEPTANCE_FIELD_ID", "").strip()
        field_id = configured_field or (str(fields[0]["id"]) if fields else "")
        if not field_id:
            raise RuntimeError("No acceptance field is available for the configured user")

        for source_id in SOURCES:
            source_dates = _json_request(
                app,
                _url(app_url, f"/api/sources/{source_id}/dates"),
            )
            if not source_dates:
                raise RuntimeError(f"{source_id} has no web-app dates")
            field_dates = _json_request(
                app,
                _url(
                    app_url,
                    f"/api/fields/{field_id}/dates",
                    sourceId=source_id,
                    indexType="NDVI",
                ),
                timeout=120,
            )
            # The product BFF intentionally filters unavailable ingestion dates;
            # every entry returned by this endpoint is field-usable.
            if not field_dates:
                raise RuntimeError(f"{source_id} has no usable NDVI date for field {field_id}")
            acquisition_date = str(field_dates[0]["acquisitionDate"])
            stats = _json_request(
                app,
                _url(app_url, f"/api/fields/{field_id}/indices/statistics"),
                method="POST",
                payload={
                    "sourceId": source_id,
                    "acquisitionDate": acquisition_date,
                    "indexType": "NDVI",
                },
                timeout=120,
            )
            if stats.get("sourceId") != source_id:
                raise RuntimeError(f"{source_id} statistics returned mismatched provenance")

        print("Four-source live acceptance passed:")
        for source_id in SOURCES:
            print(f"- {source_id}: ready through ingestion, BFF, and field NDVI statistics")
        return 0
    except (RuntimeError, urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        print(f"Four-source live acceptance failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
