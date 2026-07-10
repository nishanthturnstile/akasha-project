from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.ingestion_client import (
    FIELD_INDEX_PATH,
    READINESS_PATH,
    FieldIndexAvailableResponse,
    FieldIndexRequest,
    FieldIndexUnavailableResponse,
    IngestionClient,
    IngestionClientConfigError,
    IngestionClientError,
)

API_URL = "https://ingestion.internal"
API_KEY = "test-secret-ingestion-key"


def _available_body() -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "status": "AVAILABLE",
            "queryId": "q_01JZ8H7P5ZNDVI",
            "fieldId": "field_123",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "selectedSceneDate": "2026-01-13",
            "source": "sentinel-2-l2a",
            "providerRoute": "earthsearch:sentinel-2-l2a",
            "resolution": {
                "nativeMeters": 10,
                "processingMeters": 10,
                "displayMeters": 10,
            },
            "layerId": "layer_01JZ8H7P5Z",
            "tileUrl": (
                "https://ingestion.internal/tiles/layer_01JZ8H7P5Z/{z}/{x}/{y}.png"
                "?op=tile&exp=1783071196&kid=default&sig=SIGNED"
            ),
            "statsUrl": (
                "https://ingestion.internal/api/v1/analytics/field-index/"
                "q_01JZ8H7P5ZNDVI?op=stats&exp=1783071196&kid=default&sig=SIGNED"
            ),
            "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
            "statistics": {
                "min": 0.12,
                "max": 0.86,
                "mean": 0.54,
                "median": 0.55,
                "stdDev": 0.08,
                "usablePixelPercentage": 92.5,
                "cloudPercentage": 4.2,
            },
            "classStatistics": [
                {
                    "class": "healthy",
                    "valueRange": [0.4, 1.0],
                    "areaSqM": 28100.0,
                    "areaPercentage": 81.3,
                }
            ],
            "visualization": {
                "displayProfile": "ndvi-v1",
                "thresholdProfile": "ndvi-thresholds-v1",
                "legend": [{"label": "healthy", "color": "#2f7d32", "min": 0.4, "max": 1.0}],
            },
            "versions": {"analytics": "phase2-sentinel2-v1"},
            "quality": {"status": "GOOD", "reason": "OK", "warnings": []},
        },
        "error": None,
    }


def _unavailable_body() -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "status": "UNAVAILABLE",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "reason": "No optical scene within +/- 7 days",
            "searchedSources": ["sentinel-2-l2a"],
        },
        "error": None,
    }


def _readiness_body(status: str) -> dict[str, Any]:
    if status == "AVAILABLE":
        data = {
            "status": "AVAILABLE",
            "sourceId": "sentinel-2-l2a",
            "aoiId": "bangalore_60km_geodesic_aoi",
            "latestProcessedSceneDate": "2026-01-13",
            "latestSuccessfulJobCompletedAt": "2026-01-14T02:30:00Z",
            "staleAfter": "2026-01-21T02:30:00Z",
            "availableDates": ["2026-01-13", "2026-01-06"],
            "indexCoverage": {
                "NDVI": {"available": True, "dateCount": 2, "coveragePercent": 100.0}
            },
            "lastSuccessfulJob": {
                "jobId": "job_01JZ8H",
                "status": "SUCCEEDED",
                "completedAt": "2026-01-14T02:30:00Z",
            },
            "unavailableReasons": [],
        }
    elif status == "STALE":
        data = {
            "status": "STALE",
            "sourceId": "sentinel-2-l2a",
            "aoiId": "bangalore_60km_geodesic_aoi",
            "latestProcessedSceneDate": "2026-01-01",
            "latestSuccessfulJobCompletedAt": "2026-01-02T02:30:00Z",
            "staleAfter": "2026-01-09T02:30:00Z",
            "availableDates": ["2026-01-01"],
            "indexCoverage": {
                "NDVI": {"available": True, "dateCount": 1, "coveragePercent": 100.0}
            },
            "lastSuccessfulJob": {
                "jobId": "job_01JYOLD",
                "status": "SUCCEEDED",
                "completedAt": "2026-01-02T02:30:00Z",
            },
            "unavailableReasons": [
                {"code": "PRELOAD_STALE", "message": "Latest preload is stale."}
            ],
        }
    else:
        data = {
            "status": "UNAVAILABLE",
            "sourceId": "sentinel-2-l2a",
            "aoiId": "bangalore_60km_geodesic_aoi",
            "latestProcessedSceneDate": None,
            "latestSuccessfulJobCompletedAt": None,
            "staleAfter": None,
            "availableDates": [],
            "indexCoverage": {
                "NDVI": {"available": False, "dateCount": 0, "coveragePercent": 0.0}
            },
            "lastSuccessfulJob": None,
            "unavailableReasons": [
                {"code": "NO_PRELOAD_OUTPUTS", "message": "No precomputed outputs."}
            ],
        }
    return {"success": True, "data": data, "error": None}


def _request_payload() -> FieldIndexRequest:
    return FieldIndexRequest(
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [77.5901, 12.9716],
                    [77.5911, 12.9716],
                    [77.5911, 12.9726],
                    [77.5901, 12.9726],
                    [77.5901, 12.9716],
                ]
            ],
        },
        index="NDVI",
        date="2026-01-15",
        maxCloudPercentage=20,
        fieldId="field_123",
    )


def _client_for(handler) -> IngestionClient:
    return IngestionClient(
        api_url=API_URL,
        api_key=API_KEY,
        timeout_seconds=3,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_field_index_available_posts_camel_case_and_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == FIELD_INDEX_PATH
        assert request.headers["X-API-Key"] == API_KEY
        assert request.headers["X-Request-ID"] == "req-123"
        payload = json.loads(request.content)
        assert payload["fallbackPolicy"] == "nearest_valid_scene"
        assert payload["maxCloudPercentage"] == 20
        assert payload["fieldId"] == "field_123"
        assert payload["sourceId"] == "sentinel-2-l2a"
        return httpx.Response(200, json=_available_body(), request=request)

    result = _client_for(handler).field_index(_request_payload(), request_id="req-123")

    assert isinstance(result, FieldIndexAvailableResponse)
    assert result.status == "AVAILABLE"
    assert result.statistics is not None
    assert result.statistics.std_dev == pytest.approx(0.08)
    assert result.class_statistics[0].class_name == "healthy"
    assert result.tile_url and "sig=SIGNED" in result.tile_url


def test_fetch_binary_rejects_urls_outside_configured_ingestion_origin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unexpected request")

    with pytest.raises(IngestionClientError) as exc:
        _client_for(handler).fetch_binary("https://attacker.example/stats?sig=SIGNED")

    assert exc.value.code == "PIPELINE_UPSTREAM_FORBIDDEN"
    assert exc.value.status_code == 502


def test_field_index_unavailable_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_unavailable_body(), request=request)

    result = _client_for(handler).field_index(_request_payload())

    assert isinstance(result, FieldIndexUnavailableResponse)
    assert result.status == "UNAVAILABLE"
    assert result.reason == "No optical scene within +/- 7 days"
    assert result.searched_sources == ["sentinel-2-l2a"]


@pytest.mark.parametrize("status", ["AVAILABLE", "STALE", "UNAVAILABLE"])
def test_readiness_statuses(status: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == READINESS_PATH
        assert request.url.params["sourceId"] == "sentinel-2-l2a"
        assert request.url.params["aoiId"] == "bangalore_60km_geodesic_aoi"
        return httpx.Response(200, json=_readiness_body(status), request=request)

    result = _client_for(handler).readiness(
        source_id="sentinel-2-l2a",
        aoi_id="bangalore_60km_geodesic_aoi",
    )

    assert result.status == status
    assert result.index_coverage["NDVI"].available is (status != "UNAVAILABLE")


@pytest.mark.parametrize(
    ("upstream_status", "expected_code", "expected_retryable"),
    [
        (401, "PIPELINE_AUTH_FAILED", False),
        (403, "PIPELINE_AUTH_FAILED", False),
        (429, "PIPELINE_RATE_LIMITED", False),
        (500, "PIPELINE_UPSTREAM_ERROR", True),
    ],
)
def test_non_2xx_envelopes_map_by_http_status(
    upstream_status: int, expected_code: str, expected_retryable: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            upstream_status,
            json={
                "success": False,
                "data": None,
                "error": {
                    "code": str(upstream_status),
                    "message": (
                        f"Bad upstream at https://ingestion.internal/path?sig=SECRET "
                        f"with {API_KEY}"
                    ),
                },
            },
            request=request,
        )

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    exc = exc_info.value
    assert exc.code == expected_code
    assert exc.retryable is expected_retryable
    assert exc.upstream_status == upstream_status
    assert "ingestion.internal" not in str(exc)
    assert "sig=SECRET" not in str(exc)
    assert API_KEY not in str(exc)


@pytest.mark.parametrize(
    ("retry_after", "expected_retryable", "expected_seconds"),
    [
        ("10", True, 10),
        (None, False, None),
        ("not-a-delay", False, None),
        ("120", False, None),
        ("-1", False, None),
    ],
)
def test_429_retryable_only_with_valid_bounded_retry_after(
    retry_after: str | None, expected_retryable: bool, expected_seconds: int | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        return httpx.Response(
            429,
            headers=headers,
            json={
                "success": False,
                "data": None,
                "error": {
                    "code": "429",
                    "message": "Rate limited by https://ingestion.internal/api?sig=SECRET",
                },
            },
            request=request,
        )

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    exc = exc_info.value
    assert exc.code == "PIPELINE_RATE_LIMITED"
    assert exc.retryable is expected_retryable
    assert exc.details["upstreamStatus"] == 429
    if expected_seconds is None:
        assert "retryAfterSeconds" not in exc.details
    else:
        assert exc.details["retryAfterSeconds"] == expected_seconds
    assert "ingestion.internal" not in str(exc.to_payload())
    assert "sig=SECRET" not in str(exc.to_payload())


def test_raw_fastapi_detail_body_is_sanitized_and_mapped_by_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "detail": (
                    "Failed calling https://ingestion.internal/api?exp=1&kid=x&sig=y "
                    f"with key {API_KEY}"
                )
            },
            request=request,
        )

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    exc = exc_info.value
    assert exc.code == "PIPELINE_UPSTREAM_ERROR"
    assert exc.details == {"upstreamStatus": 500}
    assert "ingestion.internal" not in str(exc.to_payload())
    assert "sig=y" not in str(exc.to_payload())
    assert API_KEY not in str(exc.to_payload())


def test_success_false_uses_numeric_string_error_code_as_advisory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "data": None,
                "error": {"code": "404", "message": "No output for signed URL"},
            },
            request=request,
        )

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    assert exc_info.value.code == "PIPELINE_OUTPUT_UNAVAILABLE"
    assert exc_info.value.details == {"ingestionErrorCode": "404"}


def test_timeout_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            f"Timed out calling https://ingestion.internal/path?sig=SECRET with {API_KEY}",
            request=request,
        )

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    exc = exc_info.value
    assert exc.code == "PIPELINE_UPSTREAM_TIMEOUT"
    assert exc.status_code == 504
    assert exc.retryable is True
    assert "ingestion.internal" not in str(exc)
    assert "SECRET" not in str(exc)
    assert API_KEY not in str(exc)


def test_connection_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused by ingestion.internal", request=request)

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    assert exc_info.value.code == "PIPELINE_UPSTREAM_UNAVAILABLE"
    assert exc_info.value.status_code == 503


def test_invalid_json_raises_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    assert exc_info.value.code == "PIPELINE_INVALID_RESPONSE"


def test_success_envelope_missing_data_raises_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "error": None}, request=request)

    with pytest.raises(IngestionClientError) as exc_info:
        _client_for(handler).field_index(_request_payload())

    assert exc_info.value.code == "PIPELINE_INVALID_RESPONSE"


@pytest.mark.parametrize(
    ("api_url", "api_key", "missing"),
    [
        ("", API_KEY, ["INGESTION_API_URL"]),
        (API_URL, "", ["INGESTION_API_KEY"]),
        ("", "", ["INGESTION_API_URL", "INGESTION_API_KEY"]),
    ],
)
def test_url_or_key_not_configured(api_url: str, api_key: str, missing: list[str]) -> None:
    client = IngestionClient(api_url=api_url, api_key=api_key)

    with pytest.raises(IngestionClientConfigError) as exc_info:
        client.field_index(_request_payload())

    assert exc_info.value.code == "PIPELINE_NOT_CONFIGURED"
    assert exc_info.value.details == {"missing": missing}
