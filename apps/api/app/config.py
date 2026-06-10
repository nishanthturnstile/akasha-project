"""Application configuration for the Akasha BFF.

Slice 0 (skeleton): we *load* the documented environment variables so the
service is forward-compatible, but we do NOT use them for business logic yet
(no database, no STAC, no TiTiler calls). Those arrive in later slices.

All values come from the environment. Never hard-code secrets or internal URLs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_LOCAL_CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


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
    sentinel1_vv_rescale: str = field(default_factory=lambda: _get("AKASHA_S1_VV_RESCALE", "-25,5"))

    # AOI / source defaults
    default_source_id: str = field(
        default_factory=lambda: _get("DEFAULT_SOURCE_ID", "sentinel-2-l2a")
    )
    default_aoi_id: str = field(default_factory=lambda: _get("DEFAULT_AOI_ID", "bangalore"))

    # Public basemap metadata surfaced to the frontend. Credentials are configured
    # on the web build as a referrer-restricted VITE_ESRI_API_KEY, not exposed here.
    basemap_provider: str = field(default_factory=lambda: _get("BASEMAP_PROVIDER", "esri"))
    esri_basemap_style: str = field(
        default_factory=lambda: _get("ESRI_BASEMAP_STYLE", "arcgis/imagery")
    )
    esri_basemap_style_family: str = field(
        default_factory=lambda: _get("ESRI_BASEMAP_STYLE_FAMILY", "arcgis")
    )
    esri_basemap_usage_model: str = field(
        default_factory=lambda: _get("ESRI_BASEMAP_USAGE_MODEL", "session")
    )
    esri_basemap_places: str = field(default_factory=lambda: _get("ESRI_BASEMAP_PLACES", "none"))
    esri_basemap_session_seconds: int = field(
        default_factory=lambda: _get_int("ESRI_BASEMAP_SESSION_SECONDS", 43_200)
    )

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

    # Phase 12 auth/team foundations. AUTH_MODE=disabled requires explicit local opt-in.
    auth_mode: str = field(default_factory=lambda: _get("AUTH_MODE", "disabled"))
    auth_allow_disabled: bool = field(
        default_factory=lambda: _get_bool("AUTH_ALLOW_DISABLED", False)
    )
    auth_dev_user_email: str = field(
        default_factory=lambda: _get("AUTH_DEV_USER_EMAIL", "dev@akasha.local")
    )
    auth_dev_team_name: str = field(
        default_factory=lambda: _get("AUTH_DEV_TEAM_NAME", "Akasha Dev Team")
    )
    auth_session_cookie_name: str = field(
        default_factory=lambda: _get("AUTH_SESSION_COOKIE_NAME", "akasha_session")
    )
    auth_session_ttl_minutes: int = field(
        default_factory=lambda: _get_int("AUTH_SESSION_TTL_MINUTES", 480)
    )
    auth_remember_ttl_days: int = field(
        default_factory=lambda: _get_int("AUTH_REMEMBER_TTL_DAYS", 30)
    )
    auth_password_pepper: str = field(default_factory=lambda: _get("AUTH_PASSWORD_PEPPER", ""))
    auth_allow_bootstrap: bool = field(
        default_factory=lambda: _get_bool("AUTH_ALLOW_BOOTSTRAP", False)
    )
    auth_bootstrap_token: str = field(default_factory=lambda: _get("AUTH_BOOTSTRAP_TOKEN", ""))
    auth_cookie_secure: bool = field(default_factory=lambda: _get_bool("AUTH_COOKIE_SECURE", True))
    auth_login_rate_limit_per_minute: int = field(
        default_factory=lambda: _get_int("AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", 10)
    )
    auth_bootstrap_rate_limit_per_hour: int = field(
        default_factory=lambda: _get_int("AUTH_BOOTSTRAP_RATE_LIMIT_PER_HOUR", 5)
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Comma-separated origins. Supports CORS_ALLOWED_ORIGINS (doc name)
        and CORS_ORIGINS (Emergent template name).

        Credentialed auth cookies must never be paired with wildcard CORS.
        """
        raw = _get("CORS_ALLOWED_ORIGINS") or _get("CORS_ORIGINS", "")
        if not raw:
            if self.app_env.lower() in {"development", "local", "test"}:
                return list(_LOCAL_CORS_ALLOWED_ORIGINS)
            return []
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if "*" in origins:
            if self.app_env.lower() in {"development", "local", "test"}:
                return list(_LOCAL_CORS_ALLOWED_ORIGINS)
            raise RuntimeError(
                "CORS wildcard is not allowed for credentialed auth; "
                "set CORS_ALLOWED_ORIGINS to exact public origins."
            )
        return origins


settings = Settings()
