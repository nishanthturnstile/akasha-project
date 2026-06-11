"""Standard Akasha BFF error shape + helpers (architecture-tech-stack.md).

Error response:
    { "error": { "code": "POLYGON_TOO_LARGE", "message": "...", "details": {} } }

Status codes (architecture-tech-stack.md § Error response):
  400 bad request / validation, 422 invalid geometry, 413 polygon too large,
  429 rate limited, 504 index timeout, 502 upstream (TiTiler/STAC) failure.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AkashaError(Exception):
    """Domain error carrying a stable machine code + HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": sanitize_error_value(self.message),
                "details": sanitize_error_value(self.details),
            }
        }


_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(?:s3|https?|postgres(?:ql)?|mysql|mongodb|redis)://\S+"),
    re.compile(r"(?i)/vsi(?:s3|curl)/\S+"),
    re.compile(r"(?i)\b[\w.-]+\.internal(?::\d+)?\b"),
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|token|credential|access[_-]?key)\b\S*"
    ),
    re.compile(r"(?is)\bTraceback\b.*"),
    re.compile(r"(?is)\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+.+"),
]


def _sanitize_string(value: str) -> str:
    sanitized = value
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    return sanitized


def sanitize_error_value(value: Any) -> Any:
    """Remove infrastructure and credential details from API error payload values."""
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, dict):
        return {str(k): sanitize_error_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_error_value(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_error_value(v) for v in value]
    return value


# --- Convenience constructors for the common cases -------------------------
def bad_request(message: str, code: str = "BAD_REQUEST", **details: Any) -> AkashaError:
    return AkashaError(code, message, 400, details or None)


def invalid_geometry(message: str, **details: Any) -> AkashaError:
    return AkashaError("INVALID_GEOMETRY", message, 422, details or None)


def polygon_too_large(message: str, **details: Any) -> AkashaError:
    return AkashaError("POLYGON_TOO_LARGE", message, 413, details or None)


def not_found(message: str, code: str = "NOT_FOUND", **details: Any) -> AkashaError:
    return AkashaError(code, message, 404, details or None)


def upstream_error(message: str, code: str = "UPSTREAM_ERROR", **details: Any) -> AkashaError:
    return AkashaError(code, message, 502, details or None)


def rate_limited(message: str, **details: Any) -> AkashaError:
    return AkashaError("RATE_LIMITED", message, 429, details or None)


def index_timeout(message: str, **details: Any) -> AkashaError:
    return AkashaError("INDEX_TIMEOUT", message, 504, details or None)


def raster_backend_unavailable(message: str, **details: Any) -> AkashaError:
    """503: COG/MinIO/TiTiler backend not reachable from this environment.

    Used (e.g.) in the Emergent preview where MinIO/COGs are not available; the
    code path is real but the runtime dependency is absent.
    """
    return AkashaError("RASTER_BACKEND_UNAVAILABLE", message, 503, details or None)


def mosaic_tiles_unavailable(message: str, **details: Any) -> AkashaError:
    """503: date-level tile rendering requires unavailable mosaic support."""
    return AkashaError("MOSAIC_TILES_UNAVAILABLE", message, 503, details or None)


def multi_scene_statistics_unavailable(message: str, **details: Any) -> AkashaError:
    """503: statistics needs a single selected scene until mosaic stats are supported."""
    return AkashaError("MULTI_SCENE_STATISTICS_UNAVAILABLE", message, 503, details or None)


def plots_backend_unavailable(message: str, **details: Any) -> AkashaError:
    """503: the plots database (PostGIS) is unreachable from this environment.

    Used (e.g.) in the Emergent preview/dev where PostGIS is not provisioned;
    the code path is real but the runtime dependency is absent. The message must
    stay sanitized (no DSN, credentials, hostnames, or driver text).
    """
    return AkashaError("PLOTS_BACKEND_UNAVAILABLE", message, 503, details or None)


def seasons_backend_unavailable(message: str, **details: Any) -> AkashaError:
    """503: the seasons storage is unreachable from this environment."""
    return AkashaError("SEASONS_BACKEND_UNAVAILABLE", message, 503, details or None)


async def akasha_error_handler(_: Request, exc: AkashaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


def _sanitized_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Return FastAPI/Pydantic validation errors without echoing request input.

    Pydantic's raw error objects can include the rejected `input` value. That is
    helpful locally but unsafe for the BFF contract because clients may submit
    secrets or bulky GeoJSON payloads. Keep only stable machine-readable fields.
    """
    sanitized: list[dict[str, Any]] = []
    for err in exc.errors():
        sanitized.append(
            {
                "type": err.get("type"),
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg"),
            }
        )
    return sanitized


async def request_validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    """Standardize framework-level request validation failures.

    Keeps the API-wide error shape `{error:{code,message,details}}` even when a
    request fails before our route handler runs (for example missing required
    JSON fields or invalid body type).
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": _sanitized_validation_errors(exc)},
            }
        },
    )
