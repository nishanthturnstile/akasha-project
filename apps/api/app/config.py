"""Application configuration for the Akasha BFF.

Slice 0 (skeleton): we *load* the documented environment variables so the
service is forward-compatible, but we do NOT use them for business logic yet
(no database, no STAC, no TiTiler calls). Those arrive in later slices.

All values come from the environment. Never hard-code secrets or internal URLs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Typed view over the documented `api` service environment variables.

    Mirrors railway-deployment-guide.md -> `api` env block. Slice 0 only reads
    `app_env` and CORS for behavior; the rest are parsed for readiness/visibility.
    """

    app_env: str = field(default_factory=lambda: _get("APP_ENV", "development"))

    # Internal service URLs (consumed in later slices). Never exposed publicly.
    database_url: str = field(default_factory=lambda: _get("DATABASE_URL", ""))
    stac_api_url: str = field(default_factory=lambda: _get("STAC_API_URL", ""))
    titiler_url: str = field(default_factory=lambda: _get("TITILER_URL", ""))
    sentinel1_vv_rescale: str = field(
        default_factory=lambda: _get("AKASHA_S1_VV_RESCALE", "-25,5")
    )

    # AOI / source defaults
    default_source_id: str = field(
        default_factory=lambda: _get("DEFAULT_SOURCE_ID", "sentinel-2-l2a")
    )
    default_aoi_id: str = field(default_factory=lambda: _get("DEFAULT_AOI_ID", "bangalore"))

    # Guardrail limits (enforced in Slice 3+, surfaced here for readiness)
    usable_pixel_threshold_percent: int = field(
        default_factory=lambda: _get_int("USABLE_PIXEL_THRESHOLD_PERCENT", 70)
    )
    max_polygon_area_ha: int = field(default_factory=lambda: _get_int("MAX_POLYGON_AREA_HA", 50))
    max_polygon_vertices: int = field(
        default_factory=lambda: _get_int("MAX_POLYGON_VERTICES", 5000)
    )
    index_request_timeout_seconds: int = field(
        default_factory=lambda: _get_int("INDEX_REQUEST_TIMEOUT_SECONDS", 30)
    )
    rate_limit_index_per_minute: int = field(
        default_factory=lambda: _get_int("RATE_LIMIT_INDEX_PER_MINUTE", 30)
    )
    max_request_body_bytes: int = field(
        default_factory=lambda: _get_int("MAX_REQUEST_BODY_BYTES", 1_048_576)
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Comma-separated origins. Supports CORS_ALLOWED_ORIGINS (doc name)
        and CORS_ORIGINS (Emergent template name). Defaults to '*' for the
        local skeleton preview only.
        """
        raw = _get("CORS_ALLOWED_ORIGINS") or _get("CORS_ORIGINS", "*")
        return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]


settings = Settings()
