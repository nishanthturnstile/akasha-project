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


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _local_cors_allowed_origins() -> list[str]:
    ports: list[str] = []
    for port in (_get("FRONTEND_PORT", "5173"), _get("WEB_PORT", "8080")):
        if port and port not in ports:
            ports.append(port)

    return [
        f"http://{host}:{port}"
        for host in ("localhost", "127.0.0.1")
        for port in ports
    ]


@dataclass
class Settings:
    """Typed view over the documented `api` service environment variables.

    Mirrors the `api` env block in infra/selfhosted/env.example. Slice 0 only
    reads `app_env` and CORS for behavior; the rest are parsed for
    readiness/visibility.
    """

    app_env: str = field(default_factory=lambda: _get("APP_ENV", "development"))

    # Internal service URLs (consumed in later slices). Never exposed publicly.
    database_url: str = field(default_factory=lambda: _get("DATABASE_URL", ""))
    stac_api_url: str = field(default_factory=lambda: _get("STAC_API_URL", ""))
    titiler_url: str = field(default_factory=lambda: _get("TITILER_URL", ""))
    s3_endpoint_url: str = field(default_factory=lambda: _get("S3_ENDPOINT_URL", ""))
    s3_access_key: str = field(default_factory=lambda: _get("AWS_ACCESS_KEY_ID", ""))
    s3_secret_key: str = field(default_factory=lambda: _get("AWS_SECRET_ACCESS_KEY", ""))
    s3_region: str = field(default_factory=lambda: _get("AWS_REGION", "us-east-1"))
    cog_bucket: str = field(default_factory=lambda: _get("AKASHA_COG_BUCKET", "akasha-cogs"))
    sentinel1_vv_rescale: str = field(default_factory=lambda: _get("AKASHA_S1_VV_RESCALE", "-25,5"))

    # AOI / source defaults
    default_source_id: str = field(
        default_factory=lambda: _get("DEFAULT_SOURCE_ID", "resourcesat-2a-liss3-boa")
    )
    default_aoi_id: str = field(default_factory=lambda: _get("DEFAULT_AOI_ID", ""))
    aoi_config_path: str = field(
        default_factory=lambda: _get("AOI_CONFIG_PATH", "data/seed/bangalore-60km-aoi.geojson")
    )
    aoi_config_dir: str = field(default_factory=lambda: _get("AOI_CONFIG_DIR", ""))

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
    source_freshness_stale_days: int = field(
        default_factory=lambda: _get_int("SOURCE_FRESHNESS_STALE_DAYS", 45)
    )
    source_coverage_threshold_percent: int = field(
        default_factory=lambda: _get_int("SOURCE_COVERAGE_THRESHOLD_PERCENT", 95)
    )
    max_request_body_bytes: int = field(
        default_factory=lambda: _get_int("MAX_REQUEST_BODY_BYTES", 1_048_576)
    )

    # Temporary staging diagnostic for Bhoonidhi ResourceSat BOA product inspection.
    # Keep disabled by default; secrets are server-side only and never browser-visible.
    bhoonidhi_diagnostics_enabled: bool = field(
        default_factory=lambda: _get_bool("BHOONIDHI_DIAGNOSTICS_ENABLED", False)
    )
    bhoonidhi_user_id: str = field(default_factory=lambda: _get("BHOONIDHI_USER_ID", ""))
    bhoonidhi_password: str = field(default_factory=lambda: _get("BHOONIDHI_PASSWORD", ""))
    bhoonidhi_api_base: str = field(
        default_factory=lambda: _get("BHOONIDHI_API_BASE", "https://bhoonidhi-api.nrsc.gov.in")
    )
    bhoonidhi_download_root: str = field(
        default_factory=lambda: _get("BHOONIDHI_DOWNLOAD_ROOT", "/tmp/akasha-bhoonidhi-diagnostics")
    )
    bhoonidhi_download_timeout_seconds: int = field(
        default_factory=lambda: _get_int("BHOONIDHI_DOWNLOAD_TIMEOUT_SECONDS", 300)
    )
    bhoonidhi_max_download_bytes: int = field(
        default_factory=lambda: _get_int("BHOONIDHI_MAX_DOWNLOAD_BYTES", 5_368_709_120)
    )
    bhoonidhi_ledger_path: str = field(
        default_factory=lambda: _get("BHOONIDHI_LEDGER_PATH", "/srv/akasha/ingestion/ledger.sqlite")
    )

    # Best-resolution resolver: date window for LISS-4 enhancement lookup.
    best_resolution_window_days: int = field(
        default_factory=lambda: _get_int("AKASHA_BEST_RESOLUTION_WINDOW_DAYS", 12)
    )

    # SAR support for cloudy optical field analytics. This does not fabricate
    # optical indices; it only finds/reads nearby EOS-04 backscatter as context.
    sar_support_window_days: int = field(
        default_factory=lambda: _get_int("AKASHA_SAR_SUPPORT_WINDOW_DAYS", 7)
    )
    sar_support_cloud_threshold_percent: int = field(
        default_factory=lambda: _get_int("AKASHA_SAR_SUPPORT_CLOUD_THRESHOLD_PERCENT", 20)
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
    auth_allow_signup: bool = field(default_factory=lambda: _get_bool("AUTH_ALLOW_SIGNUP", False))
    auth_cookie_secure: bool = field(default_factory=lambda: _get_bool("AUTH_COOKIE_SECURE", True))
    auth_login_rate_limit_per_minute: int = field(
        default_factory=lambda: _get_int("AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", 10)
    )
    auth_signup_rate_limit_per_hour: int = field(
        default_factory=lambda: _get_int("AUTH_SIGNUP_RATE_LIMIT_PER_HOUR", 20)
    )

    # Phase 9 scheduler observability — read-only paths for BFF monitoring APIs.
    # Defaults point at canonical staging paths; endpoints degrade gracefully when
    # the configured directory or SQLite DB is absent.
    # REQ-016: BFF may only read redacted scheduler snapshots/summaries through
    # explicit config, never raw provider archives or unrestricted job directories.
    scheduler_jobs_dir: str = field(
        default_factory=lambda: _get(
            "SCHEDULER_JOBS_DIR", "/srv/akasha/ingestion/scheduler/jobs"
        )
    )
    """Read-only mount path for per-job scheduler artifact directories.
    Set SCHEDULER_JOBS_DIR to override. Endpoints remain unavailable if the
    directory does not exist at runtime."""

    scheduler_job_ledger_path: str = field(
        default_factory=lambda: _get(
            "SCHEDULER_JOB_LEDGER_PATH",
            "/srv/akasha/ingestion/scheduler/job_ledger.db",
        )
    )
    """Read-only path to the scheduler SQLite job ledger (job_ledger.py schema).
    Set SCHEDULER_JOB_LEDGER_PATH to override. Endpoints degrade gracefully if
    the file does not exist."""

    ingestion_job_inbox_dir: str = field(
        default_factory=lambda: _get(
            "INGESTION_JOB_INBOX_DIR", "/srv/akasha/ingestion-inbox"
        )
    )
    """Write-only handoff directory for admin-triggered ingestion job requests.
    Set INGESTION_JOB_INBOX_DIR to override. Trigger endpoint returns
    unavailable if the directory does not exist."""

    admin_ingestion_live_trigger_enabled: bool = field(
        default_factory=lambda: _get_bool("ADMIN_INGESTION_LIVE_TRIGGER_ENABLED", False)
    )
    """Gate for non-dry-run admin ingestion triggers. Disabled by default."""

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Comma-separated origins. Supports CORS_ALLOWED_ORIGINS (doc name)
        and CORS_ORIGINS (Emergent template name).

        Credentialed auth cookies must never be paired with wildcard CORS.
        """
        raw = _get("CORS_ALLOWED_ORIGINS") or _get("CORS_ORIGINS", "")
        if not raw:
            if self.app_env.lower() in {"development", "local", "test"}:
                return _local_cors_allowed_origins()
            return []
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if "*" in origins:
            if self.app_env.lower() in {"development", "local", "test"}:
                return _local_cors_allowed_origins()
            raise RuntimeError(
                "CORS wildcard is not allowed for credentialed auth; "
                "set CORS_ALLOWED_ORIGINS to exact public origins."
            )
        return origins


settings = Settings()
