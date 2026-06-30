"""Ingestion scheduler monitoring endpoints for the Akasha BFF.

Implements TASK-054, TASK-056, TASK-057, TASK-058 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Routes (all under /api/monitoring, owner/admin-gated via require_role):
    GET /api/monitoring/ingestion-schedules
        Per-source schedule state: last run, last success, last failure,
        next due window, cadence, typed source-state fields.

    GET /api/monitoring/ingestion-jobs
        Paginated, filtered list of scheduler job summaries.
        Filters: limit, cursor, sourceId, aoiId, state, startedAfter,
        startedBefore.

    GET /api/monitoring/ingestion-jobs/{jobId}
        Redacted job detail with request summary, provider input/response
        summaries, manifest handles, verification problems, rejection reasons,
        and ledger rows.  Raw server paths are never included.

Data access contract (REQ-016 / SEC-006):
    The BFF reads only from two explicitly configured read-only paths:
        settings.scheduler_jobs_dir       — per-job artifact subdirectories
        settings.scheduler_job_ledger_path — SQLite job ledger (job_ledger.py)

    Neither path is exposed to the browser; opaque artifact handles of the
    form ``"<jobId>:<artifactType>"`` are returned instead of file paths.

    If neither path is configured or the files are absent, endpoints return
    status "unconfigured" or "unavailable" with empty result sets.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field, field_validator

from .api_models import ApiModel
from .auth import CurrentUser, get_current_user, require_role
from .config import settings
from .raster import catalog_resolver as catalog
from .raster.errors import AkashaError

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(require_role("owner", "admin"))],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Map cadence-class string → approximate days between scheduled runs.
#: Zero means the cadence is not routine (archive/reference).
_CADENCE_DAYS: dict[str, float] = {
    "multiple_per_day": 0.5,
    "daily": 1.0,
    "2_to_5_days": 3.0,
    "5_to_10_days": 7.0,
    "10_to_20_days": 14.0,
    "gt_20_days": 24.0,
    "archive_on_demand": 0.0,
    "reference": 0.0,
}

#: Schedule states that count as "scheduling enabled" for the front-end flag.
_SCHEDULE_ENABLED_STATES: frozenset[str] = frozenset({"routine", "background_only", "dry_run"})

#: Schedule states that an owner/admin may trigger from the admin ingestion console.
#: ``manual_only`` is intentionally included: no timer owns those sources, but operators
#: may still submit bounded, lock-protected sync requests through the inbox bridge.
_TRIGGER_ENABLED_STATES: frozenset[str] = _SCHEDULE_ENABLED_STATES | frozenset({"manual_only"})

#: Product-exposure values that should appear in the admin console even when they are not
#: selectable map/product layers.  This is separate from raster ``availabilityStatus``.
_ADMIN_MANAGEABLE_PRODUCT_EXPOSURES: frozenset[str] = frozenset(
    {"product_active", "background_only", "reference_only"}
)

#: Scheduler next-due grace period before a due source is considered overdue.
_SCHEDULER_OVERDUE_GRACE_HOURS: int = 24

#: Scheduler ledger JSON filename (matches LEDGER_FILENAME in orchestrator.py).
_SCHEDULER_LEDGER_FILENAME = "scheduler_ledger.json"

#: Redacted schedule snapshot filename written by schedule-plan.
_SCHEDULE_STATE_FILENAME = "schedule_state.json"

#: SQLite WAL busy timeout in milliseconds (read-only queries).
_SQLITE_BUSY_TIMEOUT_MS = 5_000
_SAFE_TRIGGER_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: Default cursor sentinel (no cursor = start from newest).
_CURSOR_NONE = ""

#: Maximum rows scanned in file-based fallback to avoid scanning huge directories.
_MAX_DIR_SCAN = 2_000

#: Maximum event records returned to the browser for one job timeline request.
_EVENT_LIMIT = 200

_REDACTED = "[REDACTED]"
_REDACTED_PATH = "[REDACTED_PATH]"
_REDACTED_HOST = "[REDACTED_HOST]"
_REDACTED_QUERY = "[REDACTED_QUERY]"

_TERMINAL_JOB_STATUSES: frozenset[str] = frozenset(
    {
        "succeeded",
        "failed",
        "validation_failed",
        "blocked_by_lock",
        "cancelled",
        "skipped_not_due",
        "skipped_gated",
    }
)
_ACTIVE_JOB_STATUSES: frozenset[str] = frozenset({"planned", "queued", "running"})
_SAFE_JOB_STATUSES: frozenset[str] = _TERMINAL_JOB_STATUSES | _ACTIVE_JOB_STATUSES

_INTERNAL_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "host.docker.internal",
        "docker.for.win.localhost",
        "minio",
        "postgis",
        "postgres",
        "stac-api",
        "titiler",
        "ingestion-worker",
        "redis",
        "caddy",
        "web",
    }
)

_SIGNED_URL_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "xamzalgorithm",
        "xamzcredential",
        "xamzdate",
        "xamzexpires",
        "xamzsecuritytoken",
        "xamzsignature",
        "xamzsignedheaders",
        "awsaccesskeyid",
        "signature",
        "expires",
        "googleaccessid",
        "xgoogalgorithm",
        "xgoogcredential",
        "xgoogdate",
        "xgoogexpires",
        "xgoogsignature",
        "xgoogsignedheaders",
        "sig",
        "se",
        "sp",
        "sr",
        "sv",
        "st",
        "token",
        "accesskeyid",
        "credential",
    }
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class _JobsApiModel(ApiModel):
    model_config = ConfigDict(extra="allow")


class IngestionScheduleItem(_JobsApiModel):
    """One entry in the ingestion-schedules list (per source + AOI)."""

    source_id: str
    provider: str | None = None
    adapter: str | None = None
    aoi_id: str | None = None
    # typed source-state fields (populated from scheduler observability artifacts)
    lifecycle_state: str | None = None
    schedule_state: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    commercial_state: str | None = None
    aoi_scope: str | None = None
    validation_state: str | None = None
    # schedule control
    schedule_enabled: bool = False
    product_exposure: str | None = None
    # timing
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    next_due_at: str | None = None
    is_due: bool = False
    is_overdue: bool = False
    next_window_start: str | None = None
    next_window_end: str | None = None
    # cadence
    cadence_days: float | None = None
    # reason
    due_reason: str | None = None


class IngestionScheduleResponse(_JobsApiModel):
    status: str
    generated_at: str
    schedules: list[IngestionScheduleItem] = Field(default_factory=list)
    last_error: str | None = None


class IngestionSourceLastJob(_JobsApiModel):
    """Latest scheduler job summary for the simplified satellite view."""

    job_id: str
    state: str
    run_at: str | None = None
    found_count: int | None = None
    selected_count: int | None = None
    downloaded_count: int | None = None
    rejected_count: int | None = None
    window_start: str | None = None
    window_end: str | None = None
    failure_kind: str | None = None
    message: str | None = None


class IngestionSourceSummary(_JobsApiModel):
    """One satellite/source row for the simplified ingestion dashboard."""

    source_id: str
    label: str
    provider: str | None = None
    kind: str | None = None
    availability_status: str | None = None
    active: bool
    admin_manageable: bool = False
    sync_enabled: bool = False
    gated_reason: str | None = None
    aoi_id: str | None = None
    schedule_state: str | None = None
    schedule_enabled: bool = False
    product_exposure: str | None = None
    validation_state: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    cadence_days: float | None = None
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    next_due_at: str | None = None
    is_due: bool = False
    is_overdue: bool = False
    latest_composite_date: str | None = None
    last_job: IngestionSourceLastJob | None = None


class IngestionSourcesResponse(_JobsApiModel):
    status: str
    generated_at: str
    sources: list[IngestionSourceSummary] = Field(default_factory=list)
    live_trigger_enabled: bool
    last_error: str | None = None


class IngestionProductItem(_JobsApiModel):
    """One downloaded/provider product row for a source."""

    product_id: str
    scene_key: str | None = None
    acquisition_date: str | None = None
    status: str
    bytes: int = 0
    updated_at: str | None = None
    error: str | None = None


class IngestionSourceProductsResponse(_JobsApiModel):
    status: str
    generated_at: str
    source_id: str
    products: list[IngestionProductItem] = Field(default_factory=list)
    last_error: str | None = None


class IngestionJobSummary(_JobsApiModel):
    """One row in the job list — minimal fields for a list view."""

    job_id: str
    source_id: str
    provider: str | None = None
    aoi_id: str | None = None
    state: str
    window_start: str | None = None
    window_end: str | None = None
    found_count: int | None = None
    selected_count: int | None = None
    downloaded_count: int | None = None
    rejected_count: int | None = None
    failure_kind: str | None = None
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None


class IngestionJobListResponse(_JobsApiModel):
    status: str
    generated_at: str
    jobs: list[IngestionJobSummary] = Field(default_factory=list)
    next_cursor: str | None = None
    last_error: str | None = None


class IngestionJobDetail(_JobsApiModel):
    """Full redacted job detail for the /ingestion-jobs/{jobId} endpoint."""

    job_id: str
    source_id: str
    provider: str | None = None
    aoi_id: str | None = None
    state: str
    # redacted request parameters (already redacted at scheduler write time)
    request: dict[str, Any] = Field(default_factory=dict)
    # from observability.json — all secrets removed at scheduler write time
    provider_input_summary: dict[str, Any] = Field(default_factory=dict)
    provider_response_summary: dict[str, Any] = Field(default_factory=dict)
    search_manifest_handle: str | None = None
    download_manifest_handle: str | None = None
    prepare_manifest_handles: list[str] = Field(default_factory=list)
    verification_summary: dict[str, Any] = Field(default_factory=dict)
    schedule_decision: str | None = None
    next_due_at: str | None = None
    # counts and timing
    window_start: str | None = None
    window_end: str | None = None
    found_count: int | None = None
    selected_count: int | None = None
    downloaded_count: int | None = None
    rejected_count: int | None = None
    failure_kind: str | None = None
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    # derived from verification/response summaries (problem strings only, no paths)
    validation_problems: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    # opaque artifact handles — frontend consumers use these, never raw paths
    artifact_handles: dict[str, str] = Field(default_factory=dict)
    # recent ledger rows for this job (from SQLite, if configured)
    ledger_rows: list[dict[str, Any]] = Field(default_factory=list)


class IngestionJobEvent(_JobsApiModel):
    """One sanitized scheduler event for an ingestion job timeline."""

    timestamp: str
    event_type: str
    stage: str
    status: str
    message: str
    payload: dict[str, Any]


class IngestionJobEventsResponse(_JobsApiModel):
    """Bounded, redacted event stream for one ingestion job."""

    status: str
    generated_at: str
    job_id: str
    events: list[IngestionJobEvent] = Field(default_factory=list)
    truncated: bool
    scanned_count: int
    total_events_scanned: int
    total_valid_events: int
    malformed_events_skipped: int = 0
    returned_count: int = 0
    event_limit: int = _EVENT_LIMIT
    last_error: str | None = None


class TriggerIngestionJobRequest(ApiModel):
    """Admin request to enqueue a Bhoonidhi ingestion job through the inbox."""

    source_id: str
    aoi_id: str = "bangalore-60km"
    window_days: int = Field(12, ge=1, le=90)
    window_start: str | None = None
    window_end: str | None = None
    dry_run: bool = True
    confirm_live: bool = False
    limit: int = Field(100, ge=1, le=500)
    max_downloads: int = Field(1, ge=1, le=20)
    min_coverage_percent: float = Field(95.0, ge=0, le=100)
    notes: str = Field("", max_length=500)

    @field_validator("source_id", "aoi_id")
    @classmethod
    def _safe_identifier(cls, value: str) -> str:
        if not _SAFE_TRIGGER_IDENTIFIER_RE.fullmatch(value):
            raise ValueError("must match ^[A-Za-z0-9._-]+$")
        return value

    @field_validator("window_start", "window_end")
    @classmethod
    def _safe_window_datetime(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("must be an ISO-8601 date or datetime") from exc
        return text


class TriggerIngestionJobResponse(ApiModel):
    status: Literal["submitted", "rejected", "unavailable"]
    job_request_id: str | None = None
    dry_run: bool
    jobs_url: str
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _schedule_due_flags(next_due_at: Any, *, now: datetime) -> tuple[bool, bool]:
    next_due_at_dt = _parse_datetime(next_due_at)
    is_due = next_due_at_dt is not None and next_due_at_dt <= now
    is_overdue = False

    if is_due:
        elapsed_hours = (now - next_due_at_dt).total_seconds() / 3600
        is_overdue = elapsed_hours > _SCHEDULER_OVERDUE_GRACE_HOURS

    return is_due, is_overdue


def _redact_error(value: Any) -> str | None:
    """Redact credential-shaped substrings from error messages."""
    if value is None:
        return None
    text = str(value)
    text = _redact_urls(text)
    for pattern, repl in [
        (
            r"(?i)\b(?:Authorization|Proxy-Authorization)\s*:\s*Bearer\s+" r"[A-Za-z0-9._~+/\-]+=*",
            rf"auth_header={_REDACTED}",
        ),
        (
            r"(?i)\b(?:X-Api-Key|X-Amz-Security-Token)\s*:\s*[^ \t\r\n,;]+",
            rf"auth_header={_REDACTED}",
        ),
        (
            r"(?i)([\"'])([^\"']*(?:PASSWORD|PASSWD|TOKEN|SECRET|ACCESS[_\-]?KEY|"
            r"SECRET[_\-]?KEY|SESSION[_\-]?TOKEN|CREDENTIAL)[^\"']*)(\1\s*:\s*)"
            r"([\"'])([^\"']*)(\4)",
            rf"\1\2\3\4{_REDACTED}\6",
        ),
        (
            r"(?i)\b([A-Z0-9_\-]*(?:PASSWORD|PASSWD|TOKEN|SECRET|ACCESS[_\-]?KEY|"
            r"SECRET[_\-]?KEY|SESSION[_\-]?TOKEN|CREDENTIAL)[A-Z0-9_\-]*)(\s*[=:]\s*)\S+",
            rf"\1\2{_REDACTED}",
        ),
        (r"(?i)(Bearer)\s+[A-Za-z0-9._~+/\-]+=*", rf"\1 {_REDACTED}"),
        (
            r"(?i)(?:\b[A-Z]:\\[^ \t\r\n,;\"'()\[\]<>]+|"
            r"\\\\[^ \t\r\n,;\"'()\[\]<>]+|"
            r"(?<!\w)/(?:srv/akasha|tmp|var/tmp)(?:/[^ \t\r\n,;\"'()\[\]<>]+)?)",
            _REDACTED_PATH,
        ),
    ]:
        text = re.sub(pattern, repl, text)
    text = _redact_internal_hosts(text)
    return text[:300]


def _redact_string_list(values: list[str]) -> list[str]:
    redacted: list[str] = []
    for value in values:
        safe = _redact_error(value)
        if safe is not None:
            redacted.append(safe)
    return redacted


def _safe_failure_kind(value: Any) -> str | None:
    """Return a browser-safe failure kind string."""
    return _redact_error(value)


def _is_raw_path_key(key: str) -> bool:
    """Return True for nested monitoring keys that commonly carry host paths."""
    compact = key.replace("_", "").replace("-", "").lower()
    return compact.endswith("path") or compact in {
        "artifactsummarypath",
        "basedir",
        "downloadpath",
        "localpath",
        "localfile",
        "localuri",
        "rawroot",
        "rootdir",
        "outdir",
        "outputdir",
        "outputpath",
        "scratchdir",
        "workdir",
        "tempdir",
        "ledgerpath",
        "downloadedpath",
    }


def _compact_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_sensitive_key(key: str) -> bool:
    """Return True when a payload key is likely to contain credentials."""
    compact = _compact_key(key)
    if compact in {
        "authorization",
        "proxyauthorization",
        "cookie",
        "setcookie",
        "xapikey",
        "apikey",
        "password",
        "passwd",
        "token",
        "secret",
        "awsaccesskeyid",
        "awssecretaccesskey",
        "awssessiontoken",
        "minioaccesskey",
        "miniosecretkey",
        "s3accesskey",
        "s3secretkey",
        "bhoonidhiusername",
        "bhoonidhipassword",
    }:
        return True
    return any(
        marker in compact
        for marker in (
            "password",
            "passwd",
            "secret",
            "accesstoken",
            "refreshtoken",
            "bearertoken",
            "sessiontoken",
            "apikey",
            "accesskey",
            "secretkey",
            "credential",
            "authorization",
        )
    )


def _is_sensitive_query_key(key: str) -> bool:
    compact = _compact_key(key)
    return compact in _SIGNED_URL_QUERY_KEYS or _is_sensitive_key(key)


def _is_internal_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.strip("[]").lower().rstrip(".")
    if host in _INTERNAL_HOSTNAMES:
        return True
    if host.endswith((".internal", ".local", ".svc", ".svc.cluster.local")):
        return True
    return bool(re.match(r"^(?:127\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)", host))


def _redact_urls(text: str) -> str:
    """Redact internal URL hosts and signed/credential query strings."""

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in ".,;)]}":
            trailing = url[-1] + trailing
            url = url[:-1]
        try:
            parts = urlsplit(url)
        except ValueError:
            return _REDACTED + trailing

        netloc = _REDACTED_HOST if _is_internal_hostname(parts.hostname) else parts.netloc
        query = parts.query
        if query:
            query_keys = [key for key, _ in parse_qsl(query, keep_blank_values=True)]
            if any(_is_sensitive_query_key(key) for key in query_keys):
                query = _REDACTED_QUERY
        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)) + trailing

    return re.sub(r"\bhttps?://[^\s\"'<>]+", replace_url, text)


def _redact_internal_hosts(text: str) -> str:
    """Redact bare internal hostnames and RFC1918 loopback/private IPs."""
    host_pattern = (
        r"(?i)\b(?:localhost|host\.docker\.internal|docker\.for\.win\.localhost|"
        r"minio|postgis|postgres|stac-api|titiler|ingestion-worker|redis|caddy|web)"
        r"(?::\d+)?\b"
    )
    private_ip_pattern = (
        r"\b(?:127\.\d{1,3}\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?\b"
    )
    text = re.sub(host_pattern, _REDACTED_HOST, text)
    return re.sub(private_ip_pattern, _REDACTED_HOST, text)


def _sanitize_monitoring_value(value: Any) -> Any:
    """Recursively remove host paths/secrets from scheduler artifacts.

    Scheduler writers redact known secrets, but the BFF is the final browser
    boundary. Be defensive here: drop path-shaped keys and redact path-shaped
    substrings from arbitrary strings before returning monitoring payloads.
    """
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if _is_raw_path_key(key_text):
                continue
            if _is_sensitive_key(key_text):
                continue
            safe[key_text] = _sanitize_monitoring_value(nested)
        return safe
    if isinstance(value, list):
        return [_sanitize_monitoring_value(item) for item in value]
    if isinstance(value, str):
        return _redact_error(value)
    return value


def _validate_job_id_or_raise(job_id: str) -> None:
    """Validate a scheduler job ID path segment before using it in paths."""
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise HTTPException(status_code=400, detail="Invalid jobId")


def _safe_status(value: Any) -> str | None:
    if value is None:
        return None
    status = str(_sanitize_monitoring_value(value)).lower()
    return status if status in _SAFE_JOB_STATUSES else None


def _safe_event_text(value: Any) -> str | None:
    safe = _sanitize_monitoring_value(value)
    if safe is None:
        return None
    return str(safe)


def _event_payload(raw_payload: Any) -> dict[str, Any]:
    safe_payload = _sanitize_monitoring_value(raw_payload)
    if isinstance(safe_payload, dict):
        return safe_payload
    if safe_payload is None:
        return {}
    return {"value": safe_payload}


def _event_status(event_type: str, raw: dict[str, Any], payload: dict[str, Any]) -> str:
    """Return a safe normalized event status."""
    if event_type in {"job_created", "dry_run_plan"}:
        return "planned"
    if event_type != "status_change":
        return "unknown"

    for candidate in (payload.get("to"), payload.get("status"), raw.get("status")):
        status = _safe_status(candidate)
        if status is not None:
            return status
    return "unknown"


def _event_stage(event_type: str, status: str) -> str:
    """Map current emitted scheduler event types to timeline stages."""
    if event_type in {"job_created", "dry_run_plan"}:
        return "planned"
    if event_type == "status_change":
        if status in _TERMINAL_JOB_STATUSES:
            return "terminal"
        if status in _ACTIVE_JOB_STATUSES:
            return "running"
    return "unknown"


def _event_message(
    event_type: str, status: str, raw: dict[str, Any], payload: dict[str, Any]
) -> str:
    message = (
        payload.get("message")
        or payload.get("failureMessage")
        or raw.get("message")
        or raw.get("failureMessage")
    )
    safe_message = _safe_event_text(message)
    if safe_message:
        return safe_message
    if event_type == "job_created":
        return "Job created"
    if event_type == "dry_run_plan":
        return "Dry-run plan recorded"
    if event_type == "status_change":
        return f"Status changed to {status}"
    return "Scheduler event"


def _normalize_event(raw: dict[str, Any]) -> IngestionJobEvent:
    """Convert one raw events.jsonl object into a sanitized response event."""
    event_type = _safe_event_text(raw.get("eventType") or raw.get("event_type")) or "unknown"
    payload = _event_payload(raw.get("payload") or {})
    status = _event_status(event_type, raw, payload)
    return IngestionJobEvent(
        timestamp=_safe_event_text(raw.get("timestamp")) or "",
        event_type=event_type,
        stage=_event_stage(event_type, status),
        status=status,
        message=_event_message(event_type, status, raw, payload),
        payload=payload,
    )


def _read_job_events(path: Path) -> tuple[list[IngestionJobEvent], int, int, int]:
    """Read latest safe events from events.jsonl in chronological order."""
    latest: deque[IngestionJobEvent] = deque(maxlen=_EVENT_LIMIT)
    total_events_scanned = 0
    total_valid_events = 0
    malformed_events_skipped = 0

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            total_events_scanned += 1
            try:
                raw = json.loads(stripped)
                if not isinstance(raw, dict):
                    malformed_events_skipped += 1
                    continue
                event = _normalize_event(raw)
            except Exception:  # noqa: BLE001 — malformed event lines must not crash API
                malformed_events_skipped += 1
                continue
            total_valid_events += 1
            latest.append(event)

    return list(latest), total_events_scanned, total_valid_events, malformed_events_skipped


def _encode_ledger_cursor(scheduled_at: str, job_id: str) -> str:
    return f"{scheduled_at}|{job_id}"


def _decode_ledger_cursor(cursor: str) -> tuple[str, str]:
    if "|" not in cursor:
        return cursor, ""
    scheduled_at, job_id = cursor.split("|", 1)
    return scheduled_at, job_id


def _safe_read_json(path: Path) -> dict[str, Any]:
    """Read JSON from *path*; return empty dict on any I/O or parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — monitoring must remain fail-soft
        return {}


def _resolve_jobs_dir() -> Path | None:
    """Return the configured scheduler jobs directory, or None if absent."""
    raw = getattr(settings, "scheduler_jobs_dir", "")
    if not raw or not raw.strip():
        return None
    p = Path(raw.strip())
    if not p.is_dir():
        return None
    return p


def _resolve_inbox_dir() -> Path | None:
    """Return the configured ingestion trigger inbox directory, or None if absent."""
    raw = getattr(settings, "ingestion_job_inbox_dir", "")
    if not raw or not raw.strip():
        return None
    p = Path(raw.strip())
    if not p.is_dir():
        return None
    return p


def _resolve_ledger_db() -> Path | None:
    """Return the configured SQLite job ledger path, or None if absent."""
    raw = getattr(settings, "scheduler_job_ledger_path", "")
    if not raw or not raw.strip():
        return None
    p = Path(raw.strip())
    if not p.is_file():
        return None
    return p


def _read_scheduler_ledger(jobs_dir: Path) -> dict[str, Any]:
    """Read scheduler_ledger.json from *jobs_dir*; return {} on any error."""
    path = jobs_dir / _SCHEDULER_LEDGER_FILENAME
    if not path.is_file():
        return {}
    return _safe_read_json(path)


def _read_schedule_snapshot(jobs_dir: Path) -> dict[str, Any]:
    """Read schedule_state.json from *jobs_dir*; return {} on any error."""
    path = jobs_dir / _SCHEDULE_STATE_FILENAME
    if not path.is_file():
        return {}
    return _safe_read_json(path)


def _bool_from_snapshot(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _float_from_snapshot(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _str_from_snapshot(value: Any) -> str | None:
    if value is None:
        return None
    text = str(_sanitize_monitoring_value(value)).strip()
    return text or None


def _capabilities_from_snapshot(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    safe: list[str] = []
    for item in value:
        text = _str_from_snapshot(item)
        if text:
            safe.append(text)
    return safe


def _snapshot_schedule_to_item(
    raw: dict[str, Any], *, now: datetime
) -> IngestionScheduleItem | None:
    source_id = _str_from_snapshot(raw.get("sourceId"))
    if not source_id:
        return None
    next_due_at = _str_from_snapshot(raw.get("nextDueAt"))
    fallback_due, fallback_overdue = _schedule_due_flags(next_due_at, now=now)
    return IngestionScheduleItem(
        source_id=source_id,
        provider=_str_from_snapshot(raw.get("provider")),
        adapter=_str_from_snapshot(raw.get("adapter") or raw.get("provider")),
        aoi_id=_str_from_snapshot(raw.get("aoiId")),
        lifecycle_state=_str_from_snapshot(raw.get("lifecycleState")),
        schedule_state=_str_from_snapshot(raw.get("scheduleState")),
        capabilities=_capabilities_from_snapshot(raw.get("capabilities")),
        commercial_state=_str_from_snapshot(raw.get("commercialState")),
        aoi_scope=_str_from_snapshot(raw.get("aoiScope")),
        validation_state=_str_from_snapshot(raw.get("validationState")),
        schedule_enabled=_bool_from_snapshot(raw.get("scheduleEnabled")),
        product_exposure=_str_from_snapshot(raw.get("productExposure")),
        last_run_at=_str_from_snapshot(raw.get("lastRunAt")),
        last_success_at=_str_from_snapshot(raw.get("lastSuccessAt")),
        last_failure_at=_str_from_snapshot(raw.get("lastFailureAt")),
        next_due_at=next_due_at,
        is_due=_bool_from_snapshot(raw.get("isDue"), default=fallback_due),
        is_overdue=_bool_from_snapshot(raw.get("isOverdue"), default=fallback_overdue),
        next_window_start=_str_from_snapshot(raw.get("nextWindowStart")),
        next_window_end=_str_from_snapshot(raw.get("nextWindowEnd")),
        cadence_days=_float_from_snapshot(raw.get("cadenceDays")),
        due_reason=_str_from_snapshot(raw.get("dueReason")),
    )


def _snapshot_schedule_items(
    snapshot: dict[str, Any], *, now: datetime
) -> list[IngestionScheduleItem]:
    raw_schedules = snapshot.get("schedules")
    if not isinstance(raw_schedules, list):
        return []
    schedules: list[IngestionScheduleItem] = []
    for raw in raw_schedules:
        if not isinstance(raw, dict):
            continue
        item = _snapshot_schedule_to_item(raw, now=now)
        if item is not None:
            schedules.append(item)
    return schedules


def _list_job_dirs_sorted(jobs_dir: Path) -> list[Path]:
    """Return job subdirectories sorted newest-first.

    Job IDs are formatted ``job_YYYYMMDDTHHMMSSZ_<uid>`` so reverse
    lexicographic sort yields newest-first ordering without parsing timestamps.
    Silently returns [] on any OS error.
    """
    try:
        candidates = [p for p in jobs_dir.iterdir() if p.is_dir() and p.name.startswith("job_")]
    except OSError:
        return []
    return sorted(candidates, key=lambda p: p.name, reverse=True)


def _status_json_to_summary(data: dict[str, Any]) -> IngestionJobSummary | None:
    """Convert a status.json dict to a job summary; return None if malformed."""
    job_id = data.get("jobId")
    source_id = data.get("sourceId")
    state = data.get("status")
    if not job_id or not source_id or not state:
        return None
    updated_at = data.get("updatedAt") or data.get("finishedAt") or data.get("startedAt")
    return IngestionJobSummary(
        job_id=str(job_id),
        source_id=str(source_id),
        provider=data.get("provider"),
        aoi_id=data.get("aoiId"),
        state=str(state),
        window_start=data.get("windowStart"),
        window_end=data.get("windowEnd"),
        found_count=data.get("foundCount"),
        selected_count=data.get("selectedCount"),
        downloaded_count=data.get("downloadedCount"),
        rejected_count=data.get("rejectedCount"),
        failure_kind=_safe_failure_kind(data.get("failureKind")),
        message=_redact_error(data.get("failureMessage")),
        started_at=data.get("startedAt"),
        finished_at=data.get("finishedAt"),
        updated_at=updated_at,
    )


def _ledger_row_to_summary(row: dict[str, Any]) -> IngestionJobSummary:
    """Convert a scheduler_jobs SQLite row to a job summary."""
    updated_at = row.get("finished_at") or row.get("started_at") or row.get("scheduled_at")
    return IngestionJobSummary(
        job_id=str(row["job_id"]),
        source_id=str(row["source_id"]),
        provider=row.get("provider"),
        aoi_id=row.get("aoi_id"),
        state=str(row["state"]),
        window_start=row.get("window_start"),
        window_end=row.get("window_end"),
        found_count=row.get("found_count"),
        selected_count=row.get("selected_count"),
        downloaded_count=row.get("downloaded_count"),
        rejected_count=row.get("rejected_count"),
        failure_kind=_safe_failure_kind(row.get("failure_kind")),
        message=None,
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        updated_at=updated_at,
    )


def _ledger_row_to_source_last_job(row: dict[str, Any]) -> IngestionSourceLastJob:
    """Convert a scheduler_jobs SQLite row to a source-card last-job summary."""
    run_at = row.get("finished_at") or row.get("started_at") or row.get("scheduled_at")
    return IngestionSourceLastJob(
        job_id=str(row["job_id"]),
        state=str(row["state"]),
        run_at=run_at,
        found_count=row.get("found_count"),
        selected_count=row.get("selected_count"),
        downloaded_count=row.get("downloaded_count"),
        rejected_count=row.get("rejected_count"),
        window_start=row.get("window_start"),
        window_end=row.get("window_end"),
        failure_kind=_safe_failure_kind(row.get("failure_kind")),
        message=_redact_error(row.get("message")),
    )


def _latest_jobs_with_counts_by_source(db: Path) -> dict[str, IngestionSourceLastJob]:
    """Return the newest scheduler job for each source, including counts."""
    conn = _open_ledger_ro(db)
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT job_id, source_id, provider, aoi_id, state, "
                "scheduled_at, started_at, finished_at, window_start, window_end, "
                "found_count, selected_count, downloaded_count, rejected_count, "
                "failed_count, failure_kind, schedule_decision, next_due_at "
                "FROM scheduler_jobs "
                "ORDER BY coalesce(scheduled_at, '') DESC, job_id DESC"
            ).fetchall()
        ]
    finally:
        conn.close()

    latest: dict[str, IngestionSourceLastJob] = {}
    for row in rows:
        source_id = str(row.get("source_id") or "")
        if not source_id or source_id in latest:
            continue
        latest[source_id] = _ledger_row_to_source_last_job(row)
    return latest


def _resolve_product_ledger_db() -> Path | None:
    """Return the configured per-product Bhoonidhi ledger path, or None if absent."""
    raw = getattr(settings, "bhoonidhi_ledger_path", "")
    if not raw or not raw.strip():
        return None
    p = Path(raw.strip())
    if not p.is_file():
        return None
    return p


def _open_product_ledger_ro(db: Path) -> sqlite3.Connection:
    """Open the per-product ingestion ledger read-only."""
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS};")
    return conn


def _extract_date_from_identifier(value: Any) -> str | None:
    """Extract a YYYY-MM-DD acquisition/composite date from a scene/product identifier."""
    if value is None:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})(?:T|$)", str(value))
    return match.group(1) if match else None


def _latest_composite_dates_by_source(db: Path) -> dict[str, str]:
    """Return latest successful composite date per source from the product ledger."""
    conn = _open_product_ledger_ro(db)
    try:
        rows = conn.execute(
            "SELECT product_id, source_id, scene_key, updated_at "
            "FROM ingestion_ledger "
            "WHERE status = 'composited' AND product_id LIKE 'composite:%' "
            "ORDER BY coalesce(updated_at, '') DESC"
        ).fetchall()
    finally:
        conn.close()

    latest: dict[str, tuple[str, str]] = {}
    for row in rows:
        source_id = str(row["source_id"])
        date_text = _extract_date_from_identifier(
            row["product_id"]
        ) or _extract_date_from_identifier(row["scene_key"])
        if not date_text:
            continue
        updated_at = str(row["updated_at"] or "")
        previous = latest.get(source_id)
        if previous is None or (date_text, updated_at) > previous:
            latest[source_id] = (date_text, updated_at)
    return {source_id: date_text for source_id, (date_text, _updated_at) in latest.items()}


def _product_row_to_item(row: sqlite3.Row) -> IngestionProductItem:
    scene_key = row["scene_key"]
    return IngestionProductItem(
        product_id=str(row["product_id"]),
        scene_key=str(scene_key) if scene_key else None,
        acquisition_date=_extract_date_from_identifier(scene_key) or _extract_date_from_identifier(
            row["product_id"]
        ),
        status=str(row["status"]),
        bytes=int(row["bytes"] or 0),
        updated_at=row["updated_at"],
        error=_redact_error(row["error"]),
    )


def _source_products(db: Path, source_id: str, *, limit: int) -> list[IngestionProductItem]:
    """Return recent real provider products for one source, excluding synthetic rows."""
    conn = _open_product_ledger_ro(db)
    try:
        rows = conn.execute(
            "SELECT product_id, source_id, scene_key, status, retries, bytes, error, updated_at "
            "FROM ingestion_ledger "
            "WHERE source_id = ? "
            "AND product_id NOT LIKE 'sync:%' "
            "AND product_id NOT LIKE 'composite:%' "
            "ORDER BY coalesce(updated_at, '') DESC, product_id DESC LIMIT ?",
            (source_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [_product_row_to_item(row) for row in rows]


def _open_ledger_ro(db: Path) -> sqlite3.Connection:
    """Open the SQLite ledger from the BFF's read-only scheduler mount.

    The API container bind-mounts `/srv/akasha/ingestion` as read-only by
    design. SQLite's plain `mode=ro` can still try to create lock/shared-memory
    sidecar files for WAL databases, which fails on that mount. `immutable=1`
    keeps this endpoint strictly read-only and works for append-only monitoring
    snapshots where the API can tolerate reading the latest checkpointed state.
    """
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS};")
    return conn


def _schedule_item_supports_admin_trigger(item: IngestionScheduleItem | None) -> bool:
    """Return whether an owner/admin may submit a bounded manual sync for *item*."""
    if item is None or not item.aoi_id:
        return False
    if item.schedule_state not in _TRIGGER_ENABLED_STATES:
        return False
    if item.schedule_enabled:
        return True
    capabilities = set(item.capabilities or [])
    return item.schedule_state == "manual_only" and {
        "search_enabled",
        "download_enabled",
    }.issubset(capabilities)


def _source_is_admin_manageable(
    *, availability_status: str, schedule: IngestionScheduleItem | None, sync_enabled: bool
) -> bool:
    """Return whether a source belongs in the admin-managed satellite section."""
    if availability_status == "active" or sync_enabled:
        return True
    product_exposure = schedule.product_exposure if schedule else None
    return product_exposure in _ADMIN_MANAGEABLE_PRODUCT_EXPOSURES


def _allowed_trigger_sources() -> set[tuple[str, str]]:
    """Return source/AOI pairs that owners/admins may trigger from the console."""
    schedules = get_ingestion_schedules()
    allowed: set[tuple[str, str]] = set()
    for item in schedules.schedules:
        if _schedule_item_supports_admin_trigger(item) and item.aoi_id:
            allowed.add((item.source_id, item.aoi_id))
    return allowed


def _new_ingestion_job_request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    job_request_id = f"ingest-ui-{timestamp}-{uuid.uuid4().hex[:8]}"
    _validate_job_id_or_raise(job_request_id)
    if not _SAFE_TRIGGER_IDENTIFIER_RE.fullmatch(job_request_id):
        raise HTTPException(status_code=500, detail="Invalid generated request id")
    return job_request_id


def _trigger_request_payload(
    request: TriggerIngestionJobRequest,
    *,
    job_request_id: str,
    dry_run: bool,
    user: CurrentUser,
) -> dict[str, Any]:
    safe_notes = str(_sanitize_monitoring_value(request.notes)).strip()
    return {
        "job_id": job_request_id,
        "source_id": request.source_id,
        "provider": "bhoonidhi",
        "aoi_id": request.aoi_id,
        "window_days": request.window_days,
        "window_start": request.window_start or "",
        "window_end": request.window_end or "",
        "limit": request.limit,
        "max_downloads": request.max_downloads,
        "min_coverage_percent": request.min_coverage_percent,
        "dry_run": dry_run,
        "overwrite": False,
        "force_upload": False,
        "retain_raw_downloads": False,
        "keep_intermediate": False,
        "requested_by": f"{user.email}@bff",
        "notes": safe_notes,
    }


def _query_ledger_jobs(
    db: Path,
    *,
    limit: int,
    cursor: str | None,
    source_id_filter: str | None,
    aoi_id_filter: str | None,
    state_filter: str | None,
    started_after: str | None,
    started_before: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Query the SQLite ledger with filters; return (rows, next_cursor)."""
    conditions: list[str] = []
    params: list[Any] = []

    if cursor:
        cursor_scheduled_at, cursor_job_id = _decode_ledger_cursor(cursor)
        if cursor_job_id:
            conditions.append(
                "(coalesce(scheduled_at, '') < ? OR "
                "(coalesce(scheduled_at, '') = ? AND job_id < ?))"
            )
            params.extend([cursor_scheduled_at, cursor_scheduled_at, cursor_job_id])
        else:
            conditions.append("coalesce(scheduled_at, '') < ?")
            params.append(cursor_scheduled_at)
    if source_id_filter:
        conditions.append("source_id = ?")
        params.append(source_id_filter)
    if aoi_id_filter:
        conditions.append("aoi_id = ?")
        params.append(aoi_id_filter)
    if state_filter:
        conditions.append("state = ?")
        params.append(state_filter)
    if started_after:
        conditions.append("started_at > ?")
        params.append(started_after)
    if started_before:
        conditions.append("started_at < ?")
        params.append(started_before)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    # Fetch limit+1 to detect whether there is a next page.
    fetch_limit = limit + 1
    params.append(fetch_limit)
    sql = (
        f"SELECT job_id, source_id, provider, aoi_id, state, "
        f"scheduled_at, started_at, finished_at, window_start, window_end, "
        f"found_count, selected_count, downloaded_count, rejected_count, "
        f"failed_count, failure_kind, schedule_decision, next_due_at "
        f"FROM scheduler_jobs {where} "
        f"ORDER BY coalesce(scheduled_at, '') DESC, job_id DESC LIMIT ?"
    )
    conn = _open_ledger_ro(db)
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        # Cursor is the last returned row key; includes job_id to avoid ties dropping rows.
        last_scheduled_at = rows[-1].get("scheduled_at") or ""
        last_job_id = rows[-1].get("job_id") or ""
        next_cursor = (
            _encode_ledger_cursor(str(last_scheduled_at), str(last_job_id))
            if last_scheduled_at and last_job_id
            else None
        )

    return rows, next_cursor


def _list_jobs_from_dirs(
    jobs_dir: Path,
    *,
    limit: int,
    cursor: str | None,
    source_id_filter: str | None,
    aoi_id_filter: str | None,
    state_filter: str | None,
    started_after: str | None,
    started_before: str | None,
) -> tuple[list[IngestionJobSummary], str | None]:
    """Scan job artifact directories and return filtered, paginated summaries."""
    all_dirs = _list_job_dirs_sorted(jobs_dir)

    results: list[IngestionJobSummary] = []
    past_cursor = cursor is None  # if no cursor, start immediately
    next_cursor: str | None = None
    scanned = 0

    for job_dir in all_dirs:
        if scanned >= _MAX_DIR_SCAN:
            break
        scanned += 1

        # Cursor skip: pass directories until we reach the cursor job, then start.
        if not past_cursor:
            if job_dir.name == cursor:
                past_cursor = True
            continue

        status_path = job_dir / "status.json"
        if not status_path.is_file():
            continue
        data = _safe_read_json(status_path)
        if not data:
            continue

        # Apply filters.
        if source_id_filter and data.get("sourceId") != source_id_filter:
            continue
        if aoi_id_filter and data.get("aoiId") != aoi_id_filter:
            continue
        if state_filter and data.get("status") != state_filter:
            continue
        if started_after and (data.get("startedAt") or "") <= started_after:
            continue
        if started_before and (data.get("startedAt") or "") >= started_before:
            continue

        # Also need windowStart/windowEnd from request.json for file-based path.
        req_path = job_dir / "request.json"
        req = _safe_read_json(req_path) if req_path.is_file() else {}
        if req:
            data.setdefault("windowStart", req.get("windowStart"))
            data.setdefault("windowEnd", req.get("windowEnd"))

        summary = _status_json_to_summary(data)
        if summary is None:
            continue

        results.append(summary)
        if len(results) == limit:
            # Cursor is the last returned job; the next page starts after it.
            next_cursor = job_dir.name
            break

    return results, next_cursor


def _build_artifact_handles(job_id: str, obs: dict[str, Any]) -> dict[str, str]:
    """Return opaque artifact handles — never raw filesystem paths."""
    handles: dict[str, str] = {
        artifact_type: f"{job_id}:{artifact_type}"
        for artifact_type in ("request", "status", "result", "events", "observability")
    }
    if obs.get("searchManifestHandle"):
        handles["search_manifest"] = str(obs["searchManifestHandle"])
    if obs.get("downloadManifestHandle"):
        handles["download_manifest"] = str(obs["downloadManifestHandle"])
    for i, h in enumerate(obs.get("prepareManifestHandles") or []):
        handles[f"prepare_manifest_{i}"] = str(h)
    return handles


def _extract_validation_problems(verification_summary: dict[str, Any]) -> list[str]:
    """Extract problem/failure strings from a verification summary dict."""
    problems: list[str] = []
    for key in ("problems", "checks", "errors", "failures"):
        items = verification_summary.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    problems.append(item)
                elif isinstance(item, dict):
                    msg = item.get("message") or item.get("check") or item.get("problem")
                    if msg:
                        problems.append(str(msg))
    verdict = verification_summary.get("verdict") or verification_summary.get("result")
    if verdict and str(verdict).lower() not in {"pass", "passed", "ok"}:
        problems.append(f"verdict={verdict}")
    gate_reason = verification_summary.get("gateReason")
    if gate_reason:
        problems.append(str(gate_reason))
    return list(dict.fromkeys(_redact_string_list(problems)))  # deduplicate, preserve order


def _extract_rejection_reasons(response_summary: dict[str, Any]) -> list[str]:
    """Extract candidate rejection reason strings from a provider response summary."""
    reasons: list[str] = []
    for key in ("rejectionReasons", "skipReasons", "rejectedReasons", "filterReasons"):
        items = response_summary.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    reasons.append(item)
                elif isinstance(item, dict):
                    msg = item.get("reason") or item.get("message") or item.get("skipReason")
                    if msg:
                        reasons.append(str(msg))
    return list(dict.fromkeys(_redact_string_list(reasons)))


def _ledger_rows_for_job(db: Path, job_id: str) -> list[dict[str, Any]]:
    """Return sanitised ledger rows for *job_id* (no raw artifact paths)."""
    try:
        conn = _open_ledger_ro(db)
        try:
            rows = conn.execute(
                "SELECT job_id, source_id, provider, aoi_id, state, "
                "scheduled_at, started_at, finished_at, window_start, window_end, "
                "found_count, selected_count, downloaded_count, rejected_count, "
                "failed_count, failure_kind, schedule_decision, next_due_at "
                "FROM scheduler_jobs WHERE job_id = ? LIMIT 1",
                (job_id,),
            ).fetchall()
        finally:
            conn.close()
        # artifact_summary_path is intentionally excluded (raw path — SEC-006)
        safe_rows: list[dict[str, Any]] = []
        for row in rows:
            safe_row = _sanitize_monitoring_value(dict(row))
            if isinstance(safe_row, dict):
                safe_rows.append(safe_row)
        return safe_rows
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Schedules endpoint
# ---------------------------------------------------------------------------


@router.get("/ingestion-schedules", response_model=IngestionScheduleResponse)
def get_ingestion_schedules() -> IngestionScheduleResponse:
    """Return per-source/AOI schedule state.

    Reads from the scheduler JSON ledger (``scheduler_ledger.json``) plus the
    latest job's ``observability.json`` for each source/AOI pair.  Also reads
    the SQLite job ledger to populate last-failure timestamps if available.
    """
    generated_at = _now_iso()
    now = _parse_datetime(generated_at) or datetime.now(UTC)
    jobs_dir = _resolve_jobs_dir()

    if jobs_dir is None:
        return IngestionScheduleResponse(
            status="unconfigured",
            generated_at=generated_at,
            schedules=[],
        )

    try:
        scheduler_ledger = _read_scheduler_ledger(jobs_dir)
    except Exception as exc:  # noqa: BLE001
        return IngestionScheduleResponse(
            status="unavailable",
            generated_at=generated_at,
            last_error=_redact_error(str(exc)),
        )

    schedule_snapshot = _read_schedule_snapshot(jobs_dir)
    snapshot_schedules = _snapshot_schedule_items(schedule_snapshot, now=now)
    if snapshot_schedules:
        return IngestionScheduleResponse(
            status="ok",
            generated_at=_str_from_snapshot(schedule_snapshot.get("generatedAt")) or generated_at,
            schedules=snapshot_schedules,
        )

    entries: dict[str, Any] = scheduler_ledger.get("entries") or {}

    # Enrich with last-run and last-failure timestamps from SQLite if configured.
    last_failure_by_schedule: dict[tuple[str, str | None], str] = {}
    last_run_by_schedule: dict[tuple[str, str | None], str] = {}
    db = _resolve_ledger_db()
    if db is not None:
        try:
            conn = _open_ledger_ro(db)
            try:
                for row in conn.execute(
                    "SELECT source_id, aoi_id, "
                    "MAX(coalesce(finished_at, scheduled_at)) AS latest_at "
                    "FROM scheduler_jobs "
                    "WHERE state IN ('failed', 'validation_failed') "
                    "GROUP BY source_id, aoi_id"
                ).fetchall():
                    source_key = str(row["source_id"])
                    aoi_key = row["aoi_id"] if row["aoi_id"] is None else str(row["aoi_id"])
                    last_failure_by_schedule[(source_key, aoi_key)] = str(row["latest_at"] or "")
                for row in conn.execute(
                    "SELECT source_id, aoi_id, MAX(coalesce(scheduled_at, '')) AS latest_at "
                    "FROM scheduler_jobs GROUP BY source_id, aoi_id"
                ).fetchall():
                    source_key = str(row["source_id"])
                    aoi_key = row["aoi_id"] if row["aoi_id"] is None else str(row["aoi_id"])
                    last_run_by_schedule[(source_key, aoi_key)] = str(row["latest_at"] or "")
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 — monitoring must remain fail-soft
            pass

    schedules: list[IngestionScheduleItem] = []
    for key, entry in entries.items():
        # Ledger key format: "{source_id}::{aoi_id}"
        parts = key.split("::", 1)
        source_id = parts[0] if parts else key
        aoi_id = parts[1] if len(parts) > 1 else None

        last_success_at: str | None = entry.get("lastSucceededAt")
        last_job_id: str | None = entry.get("lastJobId")
        last_window_end: str | None = entry.get("lastWindowEnd")

        # Read the latest job's observability + request artifacts for state fields.
        obs: dict[str, Any] = {}
        req: dict[str, Any] = {}
        if last_job_id:
            obs_path = jobs_dir / last_job_id / "observability.json"
            req_path = jobs_dir / last_job_id / "request.json"
            if obs_path.is_file():
                obs = _safe_read_json(obs_path)
            if req_path.is_file():
                req = _safe_read_json(req_path)

        prov_input: dict[str, Any] = obs.get("providerInputSummary") or {}
        schedule_state: str | None = prov_input.get("scheduleState")
        provider: str | None = req.get("provider") or prov_input.get("provider")

        # Cadence info may appear in prov_input or verification summary.
        verification: dict[str, Any] = obs.get("verificationSummary") or {}
        cadence_str: str | None = prov_input.get("cadenceClass") or verification.get("cadenceClass")
        cadence_days: float | None = _CADENCE_DAYS.get(cadence_str) if cadence_str else None

        schedule_key = (source_id, aoi_id)
        fallback_source_key = (source_id, None)
        failure_at = (
            last_failure_by_schedule.get(schedule_key)
            or (last_failure_by_schedule.get(fallback_source_key) if aoi_id is None else None)
            or None
        )
        run_at = (
            last_run_by_schedule.get(schedule_key)
            or (last_run_by_schedule.get(fallback_source_key) if aoi_id is None else None)
            or None
        )
        next_due_at = obs.get("nextDueAt")
        is_due, is_overdue = _schedule_due_flags(next_due_at, now=now)

        schedules.append(
            IngestionScheduleItem(
                source_id=source_id,
                provider=provider,
                adapter=provider,
                aoi_id=aoi_id,
                lifecycle_state=prov_input.get("lifecycleState"),
                schedule_state=schedule_state,
                capabilities=list(prov_input.get("capabilities") or []),
                commercial_state=prov_input.get("commercialState"),
                aoi_scope=prov_input.get("aoiScope"),
                validation_state=prov_input.get("validationState"),
                schedule_enabled=(
                    schedule_state in _SCHEDULE_ENABLED_STATES if schedule_state else False
                ),
                product_exposure=prov_input.get("productExposure"),
                last_run_at=run_at,
                last_success_at=last_success_at,
                last_failure_at=failure_at,
                next_due_at=next_due_at,
                is_due=is_due,
                is_overdue=is_overdue,
                next_window_start=last_window_end,
                next_window_end=None,
                cadence_days=cadence_days,
                due_reason=obs.get("scheduleDecision"),
            )
        )

    return IngestionScheduleResponse(
        status="ok",
        generated_at=generated_at,
        schedules=schedules,
    )


# ---------------------------------------------------------------------------
# Simplified satellite-centric source endpoints
# ---------------------------------------------------------------------------


@router.get("/ingestion-sources", response_model=IngestionSourcesResponse)
def list_ingestion_sources() -> IngestionSourcesResponse:
    """Return satellite/source rows for the simplified ingestion dashboard.

    This endpoint intentionally reshapes existing scheduler/catalog state into
    an operator-friendly source list: available satellites, last/next run, last
    job counts, and latest composite date. It is read-only and fail-soft.
    """
    generated_at = _now_iso()
    last_error: str | None = None

    schedules_response = get_ingestion_schedules()
    schedule_by_source: dict[str, IngestionScheduleItem] = {}
    for schedule in schedules_response.schedules:
        existing = schedule_by_source.get(schedule.source_id)
        if existing is None or (schedule.schedule_enabled and not existing.schedule_enabled):
            schedule_by_source[schedule.source_id] = schedule
    if schedules_response.status == "unavailable" and schedules_response.last_error:
        last_error = schedules_response.last_error

    last_jobs_by_source: dict[str, IngestionSourceLastJob] = {}
    db = _resolve_ledger_db()
    if db is not None:
        try:
            last_jobs_by_source = _latest_jobs_with_counts_by_source(db)
        except Exception as exc:  # noqa: BLE001 — monitoring must remain fail-soft
            last_error = _redact_error(str(exc))

    latest_composite_by_source: dict[str, str] = {}
    product_db = _resolve_product_ledger_db()
    if product_db is not None:
        try:
            latest_composite_by_source = _latest_composite_dates_by_source(product_db)
        except Exception as exc:  # noqa: BLE001 — monitoring must remain fail-soft
            last_error = _redact_error(str(exc))

    sources: list[IngestionSourceSummary] = []
    for source in catalog.list_sources():
        source_id = str(source["id"])
        schedule = schedule_by_source.get(source_id)
        availability_status = str(source.get("availabilityStatus") or "active")
        last_job = last_jobs_by_source.get(source_id)
        sync_enabled = _schedule_item_supports_admin_trigger(schedule)
        admin_manageable = _source_is_admin_manageable(
            availability_status=availability_status,
            schedule=schedule,
            sync_enabled=sync_enabled,
        )
        last_run_at = schedule.last_run_at if schedule else None
        last_success_at = schedule.last_success_at if schedule else None
        last_failure_at = schedule.last_failure_at if schedule else None
        if last_job and not last_run_at:
            last_run_at = last_job.run_at
        if last_job and last_job.state == "succeeded" and not last_success_at:
            last_success_at = last_job.run_at
        if last_job and last_job.state in {"failed", "validation_failed"} and not last_failure_at:
            last_failure_at = last_job.run_at
        sources.append(
            IngestionSourceSummary(
                source_id=source_id,
                label=str(source.get("label") or source_id),
                provider=source.get("provider"),
                kind=source.get("kind"),
                availability_status=availability_status,
                active=availability_status == "active",
                admin_manageable=admin_manageable,
                sync_enabled=sync_enabled,
                gated_reason=source.get("gatedReason"),
                aoi_id=schedule.aoi_id if schedule else None,
                schedule_state=schedule.schedule_state if schedule else None,
                schedule_enabled=schedule.schedule_enabled if schedule else False,
                product_exposure=schedule.product_exposure if schedule else None,
                validation_state=schedule.validation_state if schedule else None,
                capabilities=schedule.capabilities if schedule else [],
                cadence_days=schedule.cadence_days if schedule else None,
                last_run_at=last_run_at,
                last_success_at=last_success_at,
                last_failure_at=last_failure_at,
                next_due_at=schedule.next_due_at if schedule else None,
                is_due=schedule.is_due if schedule else False,
                is_overdue=schedule.is_overdue if schedule else False,
                latest_composite_date=latest_composite_by_source.get(source_id),
                last_job=last_job,
            )
        )

    sources.sort(
        key=lambda item: (0 if item.admin_manageable else 1, 0 if item.active else 1, item.label)
    )

    return IngestionSourcesResponse(
        status="ok" if last_error is None else "unavailable",
        generated_at=generated_at,
        sources=sources,
        live_trigger_enabled=bool(getattr(settings, "admin_ingestion_live_trigger_enabled", False)),
        last_error=last_error,
    )


@router.get(
    "/ingestion-sources/{source_id}/products",
    response_model=IngestionSourceProductsResponse,
)
def list_ingestion_source_products(
    source_id: str,
    limit: int = Query(25, ge=1, le=100, description="Maximum products to return"),
) -> IngestionSourceProductsResponse:
    """Return recent per-product rows for one satellite source.

    The underlying Bhoonidhi ledger contains both real provider products and
    synthetic bookkeeping rows. This endpoint returns only real provider rows.
    """
    generated_at = _now_iso()
    if not _SAFE_TRIGGER_IDENTIFIER_RE.fullmatch(source_id):
        raise HTTPException(status_code=400, detail="Invalid sourceId")

    raw = getattr(settings, "bhoonidhi_ledger_path", "")
    if not raw or not raw.strip():
        return IngestionSourceProductsResponse(
            status="unconfigured",
            generated_at=generated_at,
            source_id=source_id,
            products=[],
        )

    db = _resolve_product_ledger_db()
    if db is None:
        return IngestionSourceProductsResponse(
            status="missing",
            generated_at=generated_at,
            source_id=source_id,
            products=[],
        )

    try:
        products = _source_products(db, source_id, limit=limit)
    except Exception as exc:  # noqa: BLE001 — monitoring must remain fail-soft
        return IngestionSourceProductsResponse(
            status="unavailable",
            generated_at=generated_at,
            source_id=source_id,
            products=[],
            last_error=_redact_error(str(exc)),
        )

    return IngestionSourceProductsResponse(
        status="ok",
        generated_at=generated_at,
        source_id=source_id,
        products=products,
    )


# ---------------------------------------------------------------------------
# Job list endpoint
# ---------------------------------------------------------------------------


@router.get("/ingestion-jobs", response_model=IngestionJobListResponse)
def list_ingestion_jobs(
    limit: int = Query(50, ge=1, le=200, description="Maximum jobs to return"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
    source_id: str | None = Query(
        None,
        alias="sourceId",
        description="Filter by sourceId (exact match)",
    ),
    aoi_id: str | None = Query(
        None,
        alias="aoiId",
        description="Filter by aoiId (exact match)",
    ),
    state: str | None = Query(None, description="Filter by job state (exact match)"),
    started_after: str | None = Query(
        None,
        alias="startedAfter",
        description="ISO-8601: include jobs started after this timestamp",
    ),
    started_before: str | None = Query(
        None,
        alias="startedBefore",
        description="ISO-8601: include jobs started before this timestamp",
    ),
) -> IngestionJobListResponse:
    """Return a paginated, filtered list of ingestion job summaries.

    Primary source is the SQLite job ledger (``scheduler_job_ledger_path``).
    Falls back to scanning job artifact directories (``scheduler_jobs_dir``) if
    the ledger is not available.  Returns status "unconfigured" when neither
    path is set or exists.
    """
    generated_at = _now_iso()
    db = _resolve_ledger_db()
    jobs_dir = _resolve_jobs_dir()

    if db is None and jobs_dir is None:
        return IngestionJobListResponse(
            status="unconfigured",
            generated_at=generated_at,
        )

    jobs: list[IngestionJobSummary] = []
    next_cursor: str | None = None
    last_error: str | None = None

    if db is not None:
        try:
            rows, next_cursor = _query_ledger_jobs(
                db,
                limit=limit,
                cursor=cursor,
                source_id_filter=source_id,
                aoi_id_filter=aoi_id,
                state_filter=state,
                started_after=started_after,
                started_before=started_before,
            )
            jobs = [_ledger_row_to_summary(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            last_error = _redact_error(str(exc))
    elif jobs_dir is not None:
        try:
            jobs, next_cursor = _list_jobs_from_dirs(
                jobs_dir,
                limit=limit,
                cursor=cursor,
                source_id_filter=source_id,
                aoi_id_filter=aoi_id,
                state_filter=state,
                started_after=started_after,
                started_before=started_before,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = _redact_error(str(exc))

    return IngestionJobListResponse(
        status="ok" if last_error is None else "unavailable",
        generated_at=generated_at,
        jobs=jobs,
        next_cursor=next_cursor,
        last_error=last_error,
    )


# ---------------------------------------------------------------------------
# Admin ingestion trigger endpoint
# ---------------------------------------------------------------------------


@router.post("/ingestion-jobs/trigger", response_model=TriggerIngestionJobResponse)
def trigger_ingestion_job(
    request: TriggerIngestionJobRequest,
    user: CurrentUser = Depends(get_current_user),
) -> TriggerIngestionJobResponse:
    """Enqueue an admin-triggered ingestion request into the scheduler inbox."""

    allowed_sources = _allowed_trigger_sources()
    if (request.source_id, request.aoi_id) not in allowed_sources:
        raise AkashaError(
            "SOURCE_NOT_SCHEDULABLE",
            "This source and AOI are not enabled for scheduled ingestion.",
            400,
        )

    is_live_gate_enabled = bool(getattr(settings, "admin_ingestion_live_trigger_enabled", False))
    dry_run = request.dry_run
    if not is_live_gate_enabled:
        dry_run = True
    elif not dry_run and not request.confirm_live:
        raise AkashaError(
            "LIVE_CONFIRMATION_REQUIRED",
            "Live ingestion requires explicit confirmation.",
            400,
        )

    inbox_dir = _resolve_inbox_dir()
    if inbox_dir is None:
        return TriggerIngestionJobResponse(
            status="unavailable",
            dry_run=dry_run,
            jobs_url=f"/admin/ingestion/jobs?sourceId={request.source_id}",
            message="Ingestion trigger inbox is not configured or unavailable.",
        )

    job_request_id = _new_ingestion_job_request_id()
    job_dir = inbox_dir / job_request_id
    request_path = job_dir / "request.json"
    tmp_path = job_dir / "request.json.tmp"
    payload = _trigger_request_payload(
        request,
        job_request_id=job_request_id,
        dry_run=dry_run,
        user=user,
    )

    try:
        job_dir.mkdir(mode=0o750)
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, request_path)
    except Exception as exc:  # noqa: BLE001
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise AkashaError(
            "INGESTION_TRIGGER_UNAVAILABLE",
            "Ingestion trigger inbox is unavailable.",
            503,
        ) from exc

    return TriggerIngestionJobResponse(
        status="submitted",
        job_request_id=job_request_id,
        dry_run=dry_run,
        jobs_url=f"/admin/ingestion/jobs?sourceId={request.source_id}",
        message="Ingestion job request submitted.",
    )


# ---------------------------------------------------------------------------
# Job events endpoint
# ---------------------------------------------------------------------------


@router.get("/ingestion-jobs/{job_id}/events", response_model=IngestionJobEventsResponse)
def get_ingestion_job_events(job_id: str) -> IngestionJobEventsResponse:
    """Return the latest bounded, sanitized timeline events for one job."""
    generated_at = _now_iso()
    jobs_dir = _resolve_jobs_dir()
    if jobs_dir is None:
        raise HTTPException(status_code=404, detail="Scheduler jobs directory not configured")

    _validate_job_id_or_raise(job_id)

    jdir = jobs_dir / job_id
    if not jdir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")

    status_path = jdir / "status.json"
    status_data = _safe_read_json(status_path) if status_path.is_file() else {}
    if not status_data.get("jobId"):
        raise HTTPException(status_code=404, detail="Job status not found")

    events_path = jdir / "events.jsonl"
    if not events_path.is_file():
        return IngestionJobEventsResponse(
            status="ok",
            generated_at=generated_at,
            job_id=job_id,
            events=[],
            truncated=False,
            scanned_count=0,
            total_events_scanned=0,
            total_valid_events=0,
            malformed_events_skipped=0,
            returned_count=0,
        )

    try:
        events, total_scanned, total_valid, malformed_skipped = _read_job_events(events_path)
    except OSError as exc:
        return IngestionJobEventsResponse(
            status="unavailable",
            generated_at=generated_at,
            job_id=job_id,
            events=[],
            truncated=False,
            scanned_count=0,
            total_events_scanned=0,
            total_valid_events=0,
            malformed_events_skipped=0,
            returned_count=0,
            last_error=_redact_error(str(exc)),
        )

    return IngestionJobEventsResponse(
        status="ok",
        generated_at=generated_at,
        job_id=job_id,
        events=events,
        truncated=total_valid > _EVENT_LIMIT,
        scanned_count=total_scanned,
        total_events_scanned=total_scanned,
        total_valid_events=total_valid,
        malformed_events_skipped=malformed_skipped,
        returned_count=len(events),
    )


# ---------------------------------------------------------------------------
# Job detail endpoint
# ---------------------------------------------------------------------------


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobDetail)
def get_ingestion_job(job_id: str) -> IngestionJobDetail:
    """Return a redacted detail view for one ingestion job.

    Reads ``status.json``, ``request.json``, ``result.json``, and
    ``observability.json`` from the configured job artifact directory.  Raw
    filesystem paths and full provider logs are never included in the response
    (SEC-006).  Opaque artifact handles of the form ``"<jobId>:<type>"`` are
    returned so callers can request specific artifacts via operator CLI.
    """
    jobs_dir = _resolve_jobs_dir()
    if jobs_dir is None:
        raise HTTPException(status_code=404, detail="Scheduler jobs directory not configured")

    # Sanitise job_id: only allow the expected format to prevent path traversal.
    _validate_job_id_or_raise(job_id)

    jdir = jobs_dir / job_id
    if not jdir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")

    status_data = _safe_read_json(jdir / "status.json")
    if not status_data.get("jobId"):
        raise HTTPException(status_code=404, detail="Job status not found")

    req_data = _safe_read_json(jdir / "request.json")
    result_data = _safe_read_json(jdir / "result.json")
    obs_data = _safe_read_json(jdir / "observability.json")

    source_id = str(status_data.get("sourceId") or req_data.get("sourceId") or "")
    provider = str(status_data.get("provider") or req_data.get("provider") or "")
    aoi_id = str(status_data.get("aoiId") or req_data.get("aoiId") or "") or None
    state = str(status_data.get("status") or "unknown")

    window_start = req_data.get("windowStart") or status_data.get("windowStart")
    window_end = req_data.get("windowEnd") or status_data.get("windowEnd")

    prov_input: dict[str, Any] = _sanitize_monitoring_value(
        obs_data.get("providerInputSummary") or {}
    )
    prov_response: dict[str, Any] = _sanitize_monitoring_value(
        obs_data.get("providerResponseSummary") or {}
    )
    verification: dict[str, Any] = _sanitize_monitoring_value(
        obs_data.get("verificationSummary") or {}
    )

    # Strip artifact_summary_path from any result data (raw server path — SEC-006).
    safe_result: dict[str, Any] = _sanitize_monitoring_value(
        {k: v for k, v in result_data.items() if k != "artifactSummaryPath"}
    )

    # Build safe request payload (already redacted at scheduler write time).
    safe_request: dict[str, Any] = _sanitize_monitoring_value(
        {k: v for k, v in req_data.items() if k not in {"artifactVersion", "redactionVersion"}}
    )

    updated_at = (
        status_data.get("updatedAt")
        or status_data.get("finishedAt")
        or status_data.get("startedAt")
    )

    # Opaque handles — expose jobId:type tokens, never raw paths.
    artifact_handles = _build_artifact_handles(job_id, obs_data)

    # Validation problems and rejection reasons (string-only, no paths).
    validation_problems = _extract_validation_problems(verification)
    rejection_reasons = _extract_rejection_reasons(prov_response)

    # Ledger rows from SQLite if configured (no artifact_summary_path column).
    db = _resolve_ledger_db()
    ledger_rows: list[dict[str, Any]] = _ledger_rows_for_job(db, job_id) if db else []

    return IngestionJobDetail(
        job_id=job_id,
        source_id=source_id,
        provider=provider or None,
        aoi_id=aoi_id,
        state=state,
        request=safe_request,
        provider_input_summary=prov_input,
        provider_response_summary=prov_response,
        search_manifest_handle=obs_data.get("searchManifestHandle"),
        download_manifest_handle=obs_data.get("downloadManifestHandle"),
        prepare_manifest_handles=list(obs_data.get("prepareManifestHandles") or []),
        verification_summary=verification,
        schedule_decision=obs_data.get("scheduleDecision"),
        next_due_at=obs_data.get("nextDueAt") or status_data.get("nextDueAt"),
        window_start=window_start,
        window_end=window_end,
        found_count=status_data.get("foundCount"),
        selected_count=status_data.get("selectedCount"),
        downloaded_count=status_data.get("downloadedCount"),
        rejected_count=status_data.get("rejectedCount"),
        failure_kind=_safe_failure_kind(status_data.get("failureKind")),
        message=_redact_error(
            status_data.get("failureMessage") or safe_result.get("failureMessage")
        ),
        started_at=status_data.get("startedAt"),
        finished_at=status_data.get("finishedAt"),
        updated_at=updated_at,
        validation_problems=validation_problems,
        rejection_reasons=rejection_reasons,
        artifact_handles=artifact_handles,
        ledger_rows=ledger_rows,
    )
