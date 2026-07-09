"""Server-side client for the standalone Akasha ingestion analytics API."""

from __future__ import annotations

import re
import time
import urllib.parse
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from math import ceil
from typing import Any, Generic, Literal, TypeVar

import httpx
from pydantic import Field, ValidationError

from .api_models import ApiModel
from .config import Settings, settings
from .raster.errors import upstream_error

T = TypeVar("T")

FIELD_INDEX_PATH = "/api/v1/analytics/field-index"
READINESS_PATH = "/api/v1/analytics/readiness"
MAX_RETRY_AFTER_SECONDS = 30
_POINT_CACHE_TTL_SECONDS = 60.0
_FIELD_INDEX_POINT_CACHE: dict[tuple[str, str, str, str], tuple[float, str, str]] = {}


class IngestionClientError(Exception):
    """Sanitized client error for server-side ingestion failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        upstream_status: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> None:
        safe_message = str(redact_ingestion_value(message, api_key=api_key))
        safe_details = redact_ingestion_value(details or {}, api_key=api_key)
        super().__init__(safe_message)
        self.code = code
        self.message = safe_message
        self.status_code = status_code
        self.upstream_status = upstream_status
        self.retryable = retryable
        self.details = safe_details if isinstance(safe_details, dict) else {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class IngestionClientConfigError(IngestionClientError):
    """Raised when the ingestion client is not configured."""


class IngestionErrorEnvelope(ApiModel):
    code: str | int | None = None
    message: str | None = None
    details: dict[str, Any] | None = None


class ApiEnvelope(ApiModel, Generic[T]):
    success: bool
    data: T | None = None
    error: IngestionErrorEnvelope | None = None


class FieldIndexRequest(ApiModel):
    geometry: dict[str, Any]
    crs: str = "EPSG:4326"
    index: str
    date: date
    fallback_policy: str = "nearest_valid_scene"
    max_cloud_percentage: int | float | None = None
    field_id: str | None = None


class Resolution(ApiModel):
    native_meters: float | None = None
    processing_meters: float | None = None
    display_meters: float | None = None


class Selection(ApiModel):
    window_days: int | None = None
    rule: str | None = None
    valid_pixel_count: int | None = None


class FieldIndexStatistics(ApiModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std_dev: float | None = None
    usable_pixel_percentage: float | None = None
    cloud_percentage: float | None = None


class ClassStatistic(ApiModel):
    class_name: str = Field(alias="class")
    value_range: list[float] | None = None
    area_sq_m: float | None = None
    area_percentage: float | None = None


class LegendItem(ApiModel):
    label: str | None = None
    color: str | None = None
    value: float | None = None
    min: float | None = None
    max: float | None = None


class Visualization(ApiModel):
    display_profile: str | None = None
    threshold_profile: str | None = None
    legend: list[LegendItem] = Field(default_factory=list)


class Quality(ApiModel):
    status: str | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FieldIndexAvailableResponse(ApiModel):
    status: Literal["AVAILABLE"]
    query_id: str
    field_id: str | None = None
    index: str
    requested_date: date
    selected_scene_date: date | None = None
    source: str | None = None
    provider_route: str | None = None
    resolution: Resolution | None = None
    layer_id: str | None = None
    tile_url: str | None = None
    stats_url: str | None = None
    overlay_url: str | None = None
    point_url: str | None = None
    selection: Selection | None = None
    statistics: FieldIndexStatistics | None = None
    class_statistics: list[ClassStatistic] = Field(default_factory=list)
    visualization: Visualization | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    quality: Quality | None = None


class FieldIndexUnavailableResponse(ApiModel):
    status: Literal["UNAVAILABLE"]
    index: str
    requested_date: date
    reason: str
    searched_sources: list[str] = Field(default_factory=list)


FieldIndexResponse = FieldIndexAvailableResponse | FieldIndexUnavailableResponse


class ReadinessCoverage(ApiModel):
    available: bool
    date_count: int = 0
    coverage_percent: float | None = None


class LastSuccessfulJob(ApiModel):
    job_id: str
    status: str
    completed_at: datetime


class UnavailableReason(ApiModel):
    code: str
    message: str


class ReadinessResponse(ApiModel):
    status: Literal["AVAILABLE", "STALE", "UNAVAILABLE"]
    source_id: str
    aoi_id: str
    latest_processed_scene_date: date | None = None
    latest_successful_job_completed_at: datetime | None = None
    stale_after: datetime | None = None
    available_dates: list[date] = Field(default_factory=list)
    index_coverage: dict[str, ReadinessCoverage] = Field(default_factory=dict)
    last_successful_job: LastSuccessfulJob | None = None
    unavailable_reasons: list[UnavailableReason] = Field(default_factory=list)


_URL_RE = re.compile(r"(?i)\bhttps?://[^\s\"'<>]+")
_HOST_RE = re.compile(
    r"(?i)(?<![A-Z0-9_])"
    r"\b[A-Z0-9.-]*(?:ingestion|minio|s3|pgstac|stac|titiler|postgis)"
    r"[A-Z0-9.-]*(?::\d+)?\b"
    r"(?![A-Z0-9_])"
)
_SIGNED_QUERY_RE = re.compile(r"(?i)([?&](?:sig|kid|exp|token|api[_-]?key|key)=)[^&\s\"'<>]+")


def _redact_string(value: str, *, api_key: str | None = None) -> str:
    sanitized = value
    if api_key:
        sanitized = sanitized.replace(api_key, "[redacted]")
    sanitized = _URL_RE.sub("[redacted-url]", sanitized)
    sanitized = _SIGNED_QUERY_RE.sub(r"\1[redacted]", sanitized)
    sanitized = _HOST_RE.sub("[redacted-host]", sanitized)
    return sanitized


def redact_ingestion_value(value: Any, *, api_key: str | None = None) -> Any:
    """Remove API keys, ingestion hostnames, and signed URL material."""

    if isinstance(value, str):
        return _redact_string(value, api_key=api_key)
    if isinstance(value, dict):
        return {str(k): redact_ingestion_value(v, api_key=api_key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_ingestion_value(v, api_key=api_key) for v in value]
    if isinstance(value, tuple):
        return [redact_ingestion_value(v, api_key=api_key) for v in value]
    return value


def _status_mapping(status_code: int) -> tuple[str, int, bool, str]:
    if status_code in {400, 422}:
        return "PIPELINE_BAD_REQUEST", 400, False, "Ingestion pipeline rejected the request."
    if status_code in {401, 403}:
        return "PIPELINE_AUTH_FAILED", 502, False, "Ingestion pipeline authentication failed."
    if status_code == 404:
        return (
            "PIPELINE_OUTPUT_UNAVAILABLE",
            404,
            False,
            "Ingestion pipeline output is unavailable.",
        )
    if status_code == 429:
        return "PIPELINE_RATE_LIMITED", 429, False, "Ingestion pipeline is rate limited."
    if status_code == 500:
        return "PIPELINE_UPSTREAM_ERROR", 502, True, "Ingestion pipeline returned an error."
    if status_code in {502, 503, 504}:
        return (
            "PIPELINE_UPSTREAM_UNAVAILABLE",
            503,
            True,
            "Ingestion pipeline is unavailable.",
        )
    return "PIPELINE_UPSTREAM_ERROR", 502, True, "Ingestion pipeline returned an error."


def _advisory_status(error: IngestionErrorEnvelope | None) -> int | None:
    if error is None or error.code is None:
        return None
    try:
        return int(str(error.code))
    except ValueError:
        return None


def _bounded_retry_after_seconds(headers: httpx.Headers) -> int | None:
    raw = headers.get("Retry-After")
    if raw is None or not raw.strip():
        return None

    value = raw.strip()
    try:
        seconds = int(value, 10)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = ceil((retry_at - datetime.now(UTC)).total_seconds())

    if seconds < 0 or seconds > MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds


class IngestionClient:
    """Small synchronous server-to-server client for ingestion analytics."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_url = (settings.ingestion_api_url if api_url is None else api_url).strip()
        self.api_key = (settings.ingestion_api_key if api_key is None else api_key).strip()
        self.timeout_seconds = (
            float(settings.ingestion_request_timeout_seconds)
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        self._http_client = http_client

    def field_index(
        self,
        request: FieldIndexRequest | dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> FieldIndexResponse:
        payload = FieldIndexRequest.model_validate(request)
        data = self._request_json(
            "POST",
            FIELD_INDEX_PATH,
            json=payload.model_dump(mode="json", by_alias=True, exclude_none=True),
            request_id=request_id,
        )
        status = str(data.get("status", "")).upper() if isinstance(data, dict) else ""
        model = (
            FieldIndexAvailableResponse if status == "AVAILABLE" else FieldIndexUnavailableResponse
        )
        if status not in {"AVAILABLE", "UNAVAILABLE"}:
            raise self._invalid_response("Ingestion returned an invalid field-index status.")
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise self._invalid_response(
                "Ingestion returned an invalid field-index response."
            ) from exc

    def readiness(
        self,
        *,
        source_id: str | None = None,
        aoi_id: str | None = None,
        request_id: str | None = None,
    ) -> ReadinessResponse:
        data = self._request_json(
            "GET",
            READINESS_PATH,
            params={
                "sourceId": source_id or settings.ingestion_field_index_source_id,
                "aoiId": aoi_id or settings.ingestion_aoi_id,
            },
            request_id=request_id,
        )
        try:
            return ReadinessResponse.model_validate(data)
        except ValidationError as exc:
            raise self._invalid_response(
                "Ingestion returned an invalid readiness response."
            ) from exc

    def fetch_binary(
        self,
        url: str,
        *,
        request_id: str | None = None,
    ) -> tuple[bytes, str]:
        """Proxy a GET to a server-side ingestion URL, returning ``(content, content_type)``.

        Used by the app-domain pipeline proxy for opaque stats/tile requests. The
        ``url`` is ingestion signed-URL material stored server-side only; it is
        never returned to the browser. Failures are sanitized via
        ``IngestionClientError`` so no ingestion host/URL/key leaks upstream.
        """

        response = self._send_binary_get(url, request_id=request_id)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, content_type

    def fetch_overlay(
        self,
        url: str,
        *,
        request_id: str | None = None,
    ) -> tuple[bytes, str, str | None]:
        """Proxy a GET to a signed ingestion overlay URL.

        Returns ``(content, content_type, overlay_corners)`` where
        ``overlay_corners`` is the raw ``X-Akasha-Overlay-Corners`` header value
        (a JSON array of ``[lng, lat]`` corners) or ``None`` when absent. Used to
        render the field-clipped index overlay image on the map.
        """

        response = self._send_binary_get(url, request_id=request_id)
        content_type = response.headers.get("Content-Type", "image/png")
        corners = response.headers.get("X-Akasha-Overlay-Corners")
        return response.content, content_type, corners

    def _send_binary_get(
        self,
        url: str,
        *,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Send an authenticated GET to a server-side ingestion URL.

        The ``url`` must be ingestion signed-URL material (must start with the
        configured ingestion API URL); it is never returned to the browser.
        Failures are sanitized via ``IngestionClientError``.
        """

        self._ensure_configured()
        allowed_prefix = f"{self.api_url.rstrip('/')}/"
        if not url.startswith(allowed_prefix):
            raise IngestionClientError(
                "PIPELINE_UPSTREAM_FORBIDDEN",
                "Ingestion pipeline URL is not permitted.",
                status_code=502,
                retryable=False,
                api_key=self.api_key,
            )
        headers = {"X-API-Key": self.api_key}
        if request_id:
            headers["X-Request-ID"] = request_id

        try:
            response = self._send("GET", url, headers=headers, json=None, params=None)
        except httpx.TimeoutException as exc:
            raise IngestionClientError(
                "PIPELINE_UPSTREAM_TIMEOUT",
                "Ingestion pipeline request timed out.",
                status_code=504,
                retryable=True,
                details={"timeoutSeconds": self.timeout_seconds},
                api_key=self.api_key,
            ) from exc
        except httpx.TransportError as exc:
            raise IngestionClientError(
                "PIPELINE_UPSTREAM_UNAVAILABLE",
                "Ingestion pipeline is unavailable.",
                status_code=503,
                retryable=True,
                api_key=self.api_key,
            ) from exc

        if response.status_code >= 400:
            body = None
            try:
                body = response.json()
            except ValueError:
                body = None
            raise self._error_from_http_status(response.status_code, body, response.headers)

        return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()
        url = f"{self.api_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        }
        if request_id:
            headers["X-Request-ID"] = request_id

        try:
            response = self._send(method, url, headers=headers, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise IngestionClientError(
                "PIPELINE_UPSTREAM_TIMEOUT",
                "Ingestion pipeline request timed out.",
                status_code=504,
                retryable=True,
                details={"timeoutSeconds": self.timeout_seconds},
                api_key=self.api_key,
            ) from exc
        except httpx.TransportError as exc:
            raise IngestionClientError(
                "PIPELINE_UPSTREAM_UNAVAILABLE",
                "Ingestion pipeline is unavailable.",
                status_code=503,
                retryable=True,
                api_key=self.api_key,
            ) from exc

        body = self._decode_json(response)
        if response.status_code >= 400:
            raise self._error_from_http_status(response.status_code, body, response.headers)

        envelope = self._parse_envelope(body)
        if not envelope.success:
            raise self._error_from_envelope(envelope)
        if envelope.data is None:
            raise self._invalid_response("Ingestion returned a success envelope without data.")
        if not isinstance(envelope.data, dict):
            raise self._invalid_response("Ingestion returned an invalid data payload.")
        return envelope.data

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None,
        params: dict[str, Any] | None,
    ) -> httpx.Response:
        if self._http_client is not None:
            return self._http_client.request(method, url, headers=headers, json=json, params=params)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.request(method, url, headers=headers, json=json, params=params)

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            if response.status_code >= 400:
                raise self._error_from_http_status(
                    response.status_code, None, response.headers
                ) from exc
            raise self._invalid_response("Ingestion returned invalid JSON.") from exc

    def _parse_envelope(self, body: Any) -> ApiEnvelope[dict[str, Any]]:
        if not isinstance(body, dict):
            raise self._invalid_response("Ingestion returned a non-object response.")
        try:
            return ApiEnvelope[dict[str, Any]].model_validate(body)
        except ValidationError as exc:
            raise self._invalid_response(
                "Ingestion returned an invalid response envelope."
            ) from exc

    def _error_from_envelope(self, envelope: ApiEnvelope[dict[str, Any]]) -> IngestionClientError:
        advisory_status = _advisory_status(envelope.error)
        status_for_mapping = advisory_status or 500
        code, status_code, retryable, message = _status_mapping(status_for_mapping)
        details = {"ingestionErrorCode": str(envelope.error.code)} if envelope.error else {}
        return IngestionClientError(
            code,
            message,
            status_code=status_code,
            upstream_status=200,
            retryable=retryable,
            details=details,
            api_key=self.api_key,
        )

    def _error_from_http_status(
        self, status_code: int, body: Any | None, headers: httpx.Headers
    ) -> IngestionClientError:
        error_code: str | None = None
        if isinstance(body, dict):
            try:
                envelope = ApiEnvelope[Any].model_validate(body)
                if envelope.error and envelope.error.code is not None:
                    error_code = str(envelope.error.code)
            except ValidationError:
                error_code = None
        code, app_status_code, retryable, message = _status_mapping(status_code)
        details: dict[str, Any] = {"upstreamStatus": status_code}
        if status_code == 429:
            retry_after_seconds = _bounded_retry_after_seconds(headers)
            retryable = retry_after_seconds is not None
            if retry_after_seconds is not None:
                details["retryAfterSeconds"] = retry_after_seconds
        if error_code:
            details["ingestionErrorCode"] = error_code
        return IngestionClientError(
            code,
            message,
            status_code=app_status_code,
            upstream_status=status_code,
            retryable=retryable,
            details=details,
            api_key=self.api_key,
        )

    def _invalid_response(self, message: str) -> IngestionClientError:
        return IngestionClientError(
            "PIPELINE_INVALID_RESPONSE",
            message,
            status_code=502,
            retryable=False,
            api_key=self.api_key,
        )

    def _ensure_configured(self) -> None:
        if self.api_url and self.api_key:
            return
        missing = []
        if not self.api_url:
            missing.append("INGESTION_API_URL")
        if not self.api_key:
            missing.append("INGESTION_API_KEY")
        raise IngestionClientConfigError(
            "PIPELINE_NOT_CONFIGURED",
            "Ingestion pipeline is not configured.",
            status_code=503,
            retryable=False,
            details={"missing": missing},
        )


def is_ingestion_configured(settings_obj: Settings) -> bool:
    return bool(settings_obj.ingestion_api_url.strip() and settings_obj.ingestion_api_key.strip())


def _client_for(settings_obj: Settings, timeout_seconds: float | None = None) -> IngestionClient:
    return IngestionClient(
        api_url=settings_obj.ingestion_api_url,
        api_key=settings_obj.ingestion_api_key,
        timeout_seconds=timeout_seconds or settings_obj.ingestion_request_timeout_seconds,
    )


def _raise_ingestion_api_error(exc: IngestionClientError, *, default_code: str) -> None:
    if isinstance(exc, IngestionClientConfigError):
        raise upstream_error(
            "Standalone ingestion API is not configured.",
            code="INGESTION_API_UNCONFIGURED",
            **exc.details,
        ) from exc
    raise upstream_error(
        exc.message,
        code=default_code,
        retryable=exc.retryable,
        upstreamStatus=exc.upstream_status,
        **exc.details,
    ) from exc


def get_readiness(
    settings_obj: Settings,
    *,
    source_id: str,
    aoi_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    try:
        readiness = _client_for(settings_obj, timeout_seconds).readiness(
            source_id=source_id,
            aoi_id=aoi_id,
        )
    except IngestionClientError as exc:
        _raise_ingestion_api_error(exc, default_code="INGESTION_API_ERROR")
    return readiness.model_dump(mode="json", by_alias=True)


def request_field_index(
    settings_obj: Settings,
    *,
    geometry: dict[str, Any],
    field_id: str,
    source_id: str,
    index_type: str,
    acquisition_date: str,
    max_cloud_percentage: float = 20.0,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    try:
        result = _client_for(settings_obj, timeout_seconds).field_index(
            {
                "geometry": geometry,
                "crs": "EPSG:4326",
                "index": index_type,
                "date": acquisition_date,
                "fallbackPolicy": "nearest_valid_scene",
                "maxCloudPercentage": max_cloud_percentage,
                "fieldId": field_id,
            }
        )
    except IngestionClientError as exc:
        _raise_ingestion_api_error(exc, default_code="INGESTION_FIELD_INDEX_ERROR")
    return result.model_dump(mode="json", by_alias=True)


def _validate_and_rewrite_signed_url(settings_obj: Settings, url: str) -> str:
    allowed_prefix = settings_obj.ingestion_signed_url_allowed_prefix.rstrip("/")
    if not allowed_prefix or not url.startswith(f"{allowed_prefix}/"):
        raise upstream_error(
            "Standalone ingestion returned an unexpected signed URL.",
            code="INGESTION_UPSTREAM_FORBIDDEN",
        )
    fetch_prefix = (settings_obj.ingestion_signed_url_fetch_prefix or allowed_prefix).rstrip("/")
    return fetch_prefix + url[len(allowed_prefix) :]


def fetch_signed_ingestion_binary(
    settings_obj: Settings,
    url: str,
) -> tuple[bytes, str, dict[str, str]]:
    fetch_url = _validate_and_rewrite_signed_url(settings_obj, url)
    try:
        with httpx.Client(timeout=settings_obj.ingestion_request_timeout_seconds) as client:
            response = client.get(fetch_url)
        if response.status_code >= 400:
            raise IngestionClientError(
                "INGESTION_OVERLAY_FETCH_FAILED",
                "Could not fetch standalone ingestion overlay.",
                status_code=502,
                upstream_status=response.status_code,
            )
    except (httpx.TimeoutException, httpx.TransportError, IngestionClientError) as exc:
        if isinstance(exc, IngestionClientError):
            raise upstream_error(
                exc.message,
                code=exc.code,
                upstreamStatus=exc.upstream_status,
            ) from exc
        raise upstream_error(
            "Could not fetch standalone ingestion overlay.",
            code="INGESTION_OVERLAY_FETCH_FAILED",
        ) from exc
    headers = {key: value for key, value in response.headers.items()}
    for name in ("X-Akasha-Overlay-Corners", "X-Akasha-Overlay-Stretch"):
        value = response.headers.get(name)
        if value is not None:
            headers[name] = value
    return (
        response.content,
        response.headers.get("Content-Type", "application/octet-stream"),
        headers,
    )


def fetch_signed_ingestion_json(settings_obj: Settings, url: str) -> dict[str, Any]:
    fetch_url = _validate_and_rewrite_signed_url(settings_obj, url)
    try:
        with httpx.Client(timeout=settings_obj.ingestion_request_timeout_seconds) as client:
            response = client.get(fetch_url)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise upstream_error(
            "Could not fetch standalone ingestion JSON.",
            code="INGESTION_SIGNED_JSON_FETCH_FAILED",
        ) from exc
    return data if isinstance(data, dict) else {}


def _append_point_coordinates(point_url: str, *, lng: float, lat: float) -> str:
    parsed = urllib.parse.urlsplit(point_url)
    coordinates = urllib.parse.urlencode({"lng": lng, "lat": lat})
    query = f"{parsed.query}&{coordinates}" if parsed.query else coordinates
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _cached_point_url(key: tuple[str, str, str, str]) -> tuple[str, str] | None:
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
    settings_obj: Settings,
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
            settings_obj,
            geometry=geometry,
            field_id=field_id,
            source_id=source_id,
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
        settings_obj,
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
    point_response.setdefault("queryId", query_id)
    return point_response
