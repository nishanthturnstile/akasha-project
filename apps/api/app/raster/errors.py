"""Standard Akasha BFF error shape + helpers (architecture-tech-stack.md).

Error response:
    { "error": { "code": "POLYGON_TOO_LARGE", "message": "...", "details": {} } }

Status codes (architecture-tech-stack.md § Error response):
  400 bad request / validation, 422 invalid geometry, 413 polygon too large,
  429 rate limited, 504 index timeout, 502 upstream (TiTiler/STAC) failure.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
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
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


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


def raster_backend_unavailable(message: str, **details: Any) -> AkashaError:
    """503: COG/MinIO/TiTiler backend not reachable from this environment.

    Used (e.g.) in the Emergent preview where MinIO/COGs are not available; the
    code path is real but the runtime dependency is absent.
    """
    return AkashaError("RASTER_BACKEND_UNAVAILABLE", message, 503, details or None)


async def akasha_error_handler(_: Request, exc: AkashaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())
