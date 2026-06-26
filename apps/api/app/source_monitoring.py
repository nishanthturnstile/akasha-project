"""Operator-facing imagery source freshness and coverage status."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import ConfigDict, Field

from .api_models import ApiModel
from .auth import require_role
from .config import settings
from .raster import catalog_resolver as catalog

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(require_role("owner", "admin"))],
)


class MonitoringApiModel(ApiModel):
    model_config = ConfigDict(extra="allow")


class MonitoringFailure(MonitoringApiModel):
    product_id: str | None = None
    source_id: str | None = None
    scene_key: str | None = None
    status: str | None = None
    retries: int = 0
    bytes: int = 0
    updated_at: str | None = None
    failure_kind: str
    error: str | None = None


class MonitoringLedgerSource(MonitoringApiModel):
    source_id: str
    status_counts: dict[str, int] = Field(default_factory=dict)
    bytes: int = 0
    last_updated_at: str | None = None
    failure_counts_by_kind: dict[str, int] = Field(default_factory=dict)
    last_failure: MonitoringFailure | None = None
    latest_successful_composite_date: str | None = None
    latest_successful_composite_product_id: str | None = None
    latest_successful_composite_aoi_id: str | None = None
    latest_successful_composite_updated_at: str | None = None
    latest_successful_composites: list[dict[str, str | None]] = Field(default_factory=list)
    latest_successful_search_aoi_id: str | None = None
    latest_successful_search_datetime_range: str | None = None
    latest_successful_search_updated_at: str | None = None


class IngestionLedgerSummary(MonitoringApiModel):
    status: str
    path: str | None = None
    row_count: int | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)
    bytes: int | None = None
    last_updated_at: str | None = None
    failure_counts_by_kind: dict[str, int] = Field(default_factory=dict)
    last_failures: list[MonitoringFailure] = Field(default_factory=list)
    by_source: list[MonitoringLedgerSource] = Field(default_factory=list)
    last_error: str | None = None


class StoragePrefixUsage(MonitoringApiModel):
    prefix: str
    object_count: int
    bytes: int
    zero_byte_object_count: int = 0


class StorageUsage(MonitoringApiModel):
    status: str
    bucket: str | None = None
    object_count: int | None = None
    bytes: int | None = None
    zero_byte_object_count: int | None = None
    by_prefix: list[StoragePrefixUsage] = Field(default_factory=list)
    last_error: str | None = None


class ImagerySourceMonitoringSource(MonitoringApiModel):
    source_id: str
    status: Literal["ok", "warning", "error"] = "ok"
    status_reasons: list[str] = Field(default_factory=list)
    label: str | None = None
    provider: str | None = None
    kind: str | None = None
    availability_status: str | None = None
    analysis_level: str | None = None
    refresh_policy: str | None = None
    latest_available_date: str | None = None
    latest_usable_date: str | None = None
    days_since_latest_available: int | None = None
    stale_after_days: int
    is_stale: bool
    date_count: int
    tile_available_date_count: int
    coverage_percent: float | None = None
    usable_pixel_percent: float | None = None
    cloud_masked_percent: float | None = None
    metrics_provisional: bool = False
    gated_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    tile_unavailable_reasons: list[str] = Field(default_factory=list)
    last_error: str | None = None
    latest_successful_composite_date: str | None = None
    latest_successful_composite_product_id: str | None = None
    latest_successful_composite_aoi_id: str | None = None
    latest_successful_composite_updated_at: str | None = None
    latest_successful_composites: list[dict[str, str | None]] = Field(default_factory=list)
    days_since_latest_successful_composite: int | None = None
    is_successful_composite_stale: bool
    latest_successful_search_aoi_id: str | None = None
    latest_successful_search_datetime_range: str | None = None
    latest_successful_search_updated_at: str | None = None
    days_since_latest_successful_search: int | None = None
    is_successful_search_stale: bool
    is_upstream_data_stale: bool = False
    ingestion_failure_counts_by_kind: dict[str, int] = Field(default_factory=dict)
    last_ingestion_failure: MonitoringFailure | None = None
    has_unresolved_ingestion_failure: bool = False
    # Scheduler job linkage (Phase 9 — TASK-059). All fields are optional so
    # that existing callers remain unaffected when the ledger is not configured.
    latest_scheduler_job_id: str | None = None
    latest_scheduler_job_state: str | None = None
    latest_scheduler_job_updated_at: str | None = None
    scheduler_next_due_at: str | None = None
    scheduler_is_due: bool = False
    scheduler_is_overdue: bool = False
    scheduler_due_reason: str | None = None


class ImagerySourceMonitoringResponse(MonitoringApiModel):
    generated_at: str
    status: Literal["ok", "warning", "error"] = "ok"
    status_reasons: list[str] = Field(default_factory=list)
    stale_after_days: int
    coverage_threshold_percent: int
    usable_pixel_threshold_percent: int
    sources: list[ImagerySourceMonitoringSource]
    storage: StorageUsage
    ingestion_ledger: IngestionLedgerSummary


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def _latest_date(
    dates: list[dict[str, Any]], *, usable_only: bool = False
) -> dict[str, Any] | None:
    candidates = [
        entry
        for entry in dates
        if _parse_date(entry.get("acquisitionDate")) is not None
        and (not usable_only or bool(entry.get("isLatestUsable")))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: _parse_date(entry.get("acquisitionDate")) or date.min)


def _redact_error(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    replacements = [
        (r"(?i)(password|token|secret|access[_-]?key)(=|:)\s*[^,\s]+", r"\1\2[REDACTED]"),
        (r"(?i)(Bearer)\s+[A-Za-z0-9._~+/-]+", r"\1 [REDACTED]"),
        (
            r"(?i)(?:[A-Z]:\\[^ \t\r\n,;]+|/srv/akasha/[^ \t\r\n,;]+|"
            r"/tmp/[^ \t\r\n,;]+|/var/tmp/[^ \t\r\n,;]+)",
            "[REDACTED_PATH]",
        ),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text[:300]


def _sanitize_monitoring_payload(value: Any) -> Any:
    """Remove frontend-unsafe paths from nested monitoring payloads."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "path":
                sanitized[key] = None
            elif isinstance(item, str):
                sanitized[key] = _redact_error(item)
            else:
                sanitized[key] = _sanitize_monitoring_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_monitoring_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_error(value)
    return value


def _failure_kind(status: str | None, error: str | None) -> str:
    haystack = f"{status or ''} {error or ''}".lower()
    if any(token in haystack for token in ("auth", "token", "session", "403")):
        return "bhoonidhi_auth"
    if any(token in haystack for token in ("search", "data/search", "429")):
        return "bhoonidhi_search"
    if any(token in haystack for token in ("download", "not online", "412", "504")):
        return "bhoonidhi_download"
    if any(
        token in haystack
        for token in (
            "storage upload",
            "minio",
            "object storage",
            "s3",
            "head_bucket",
            "upload_file",
            "putobject",
        )
    ):
        return "storage_upload"
    if any(token in haystack for token in ("prepare", "convert", "cog", "raster", "gdal")):
        return "conversion"
    if "composite" in haystack:
        return "composite"
    if any(token in haystack for token in ("stac", "pgstac", "register")):
        return "stac_registration"
    return "ingestion"


def _composite_record(product_id: Any) -> dict[str, str] | None:
    parts = str(product_id or "").split(":")
    if len(parts) != 3 or parts[0] != "composite":
        return None
    composite_date = _parse_date(parts[2])
    if composite_date is None:
        return None
    return {"aoiId": parts[1], "date": composite_date.isoformat()}


def _search_record(product_id: Any) -> dict[str, str] | None:
    parts = str(product_id or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "sync":
        return None
    datetime_range = parts[2]
    if "/" not in datetime_range:
        return None
    return {"aoiId": parts[1], "datetimeRange": datetime_range}


def _empty_ledger_source(source_id: str) -> dict[str, Any]:
    return {
        "sourceId": source_id,
        "statusCounts": {},
        "bytes": 0,
        "lastUpdatedAt": None,
        "failureCountsByKind": {},
        "lastFailure": None,
        "latestSuccessfulCompositeDate": None,
        "latestSuccessfulCompositeProductId": None,
        "latestSuccessfulCompositeAoiId": None,
        "latestSuccessfulCompositeUpdatedAt": None,
        "latestSuccessfulComposites": [],
        "latestSuccessfulSearchAoiId": None,
        "latestSuccessfulSearchDatetimeRange": None,
        "latestSuccessfulSearchUpdatedAt": None,
    }


def _ledger_failure_payload(row: sqlite3.Row, *, error: str | None, kind: str) -> dict[str, Any]:
    return {
        "productId": row["product_id"],
        "sourceId": row["source_id"],
        "sceneKey": row["scene_key"],
        "status": row["status"],
        "retries": int(row["retries"] or 0),
        "bytes": int(row["bytes"] or 0),
        "updatedAt": row["updated_at"],
        "failureKind": kind,
        "error": error,
    }


def _ingestion_ledger_summary() -> dict[str, Any]:
    path = Path(settings.bhoonidhi_ledger_path)
    if not settings.bhoonidhi_ledger_path.strip():
        return {"status": "unconfigured", "path": None}
    if not path.is_file():
        return {"status": "missing", "path": None}

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                select status, count(*) as count, coalesce(sum(bytes), 0) as bytes,
                       max(updated_at) as last_updated_at
                from ingestion_ledger
                group by status
                """).fetchall()
            failure_rows = conn.execute("""
                select product_id, source_id, scene_key, status, retries, bytes, error, updated_at
                from ingestion_ledger
                where status = 'failed' or error is not null
                order by updated_at desc
                """).fetchall()
            last_failures = conn.execute("""
                select product_id, source_id, scene_key, status, retries, bytes, error, updated_at
                from ingestion_ledger
                where status = 'failed' or error is not null
                order by updated_at desc
                limit 5
                """).fetchall()
            source_rows = conn.execute("""
                select source_id, status, count(*) as count, coalesce(sum(bytes), 0) as bytes,
                       max(updated_at) as last_updated_at
                from ingestion_ledger
                group by source_id, status
                """).fetchall()
            successful_composite_rows = conn.execute("""
                select product_id, source_id, scene_key, status, updated_at
                from ingestion_ledger
                where status = 'composited' and product_id like 'composite:%'
                order by updated_at desc
                """).fetchall()
            successful_search_rows = conn.execute("""
                select product_id, source_id, scene_key, status, updated_at
                from ingestion_ledger
                where status = 'searched' and product_id like 'sync:%'
                order by updated_at desc
                """).fetchall()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - monitoring must remain fail-soft.
        return {
            "status": "unavailable",
            "path": None,
            "lastError": _redact_error(f"{exc.__class__.__name__}: {str(exc)[:200]}"),
        }

    status_counts = {str(row["status"]): int(row["count"]) for row in rows}
    status_bytes = {str(row["status"]): int(row["bytes"] or 0) for row in rows}
    total_rows = sum(status_counts.values())
    total_bytes = sum(status_bytes.values())
    last_updated_at = max(
        (row["last_updated_at"] for row in rows if row["last_updated_at"]),
        default=None,
    )

    failures_payload: list[dict[str, Any]] = []
    failure_counts: Counter[str] = Counter()
    per_source_failure_counts: dict[str, Counter[str]] = {}
    per_source_last_failure: dict[str, dict[str, Any]] = {}
    per_source_composites_by_aoi: dict[str, dict[str, dict[str, str | None]]] = {}
    for row in failure_rows:
        error = _redact_error(row["error"])
        kind = _failure_kind(str(row["status"]), error)
        failure_counts[kind] += 1
        source_id = str(row["source_id"])
        per_source_failure_counts.setdefault(source_id, Counter())[kind] += 1
        payload = _ledger_failure_payload(row, error=error, kind=kind)
        previous = per_source_last_failure.get(source_id)
        if previous is None or str(payload["updatedAt"] or "") > str(previous["updatedAt"] or ""):
            per_source_last_failure[source_id] = payload

    for row in last_failures:
        error = _redact_error(row["error"])
        kind = _failure_kind(str(row["status"]), error)
        failures_payload.append(_ledger_failure_payload(row, error=error, kind=kind))

    by_source: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        source_id = str(row["source_id"])
        source = by_source.setdefault(
            source_id,
            _empty_ledger_source(source_id),
        )
        source["statusCounts"][str(row["status"])] = int(row["count"])
        source["bytes"] += int(row["bytes"] or 0)
        if row["last_updated_at"]:
            source["lastUpdatedAt"] = max(
                source["lastUpdatedAt"] or row["last_updated_at"], row["last_updated_at"]
            )

    for row in successful_composite_rows:
        record = _composite_record(row["product_id"])
        if record is None:
            continue
        source_id = str(row["source_id"])
        source = by_source.setdefault(
            source_id,
            _empty_ledger_source(source_id),
        )
        composite_entry = {
            "aoiId": record["aoiId"],
            "date": record["date"],
            "productId": row["product_id"],
            "updatedAt": row["updated_at"],
        }
        by_aoi = per_source_composites_by_aoi.setdefault(source_id, {})
        previous_for_aoi = by_aoi.get(record["aoiId"])
        previous_date = _parse_date(previous_for_aoi.get("date") if previous_for_aoi else None)
        candidate_date = _parse_date(record["date"])
        if (
            previous_for_aoi is None
            or previous_date is None
            or (
                candidate_date is not None
                and (
                    candidate_date > previous_date
                    or (
                        candidate_date == previous_date
                        and str(row["updated_at"] or "")
                        > str(previous_for_aoi.get("updatedAt") or "")
                    )
                )
            )
        ):
            by_aoi[record["aoiId"]] = composite_entry
        existing = _parse_date(source["latestSuccessfulCompositeDate"])
        candidate = _parse_date(record["date"])
        if candidate is None or (existing is not None and candidate <= existing):
            continue
        source["latestSuccessfulCompositeDate"] = record["date"]
        source["latestSuccessfulCompositeProductId"] = row["product_id"]
        source["latestSuccessfulCompositeAoiId"] = record["aoiId"]
        source["latestSuccessfulCompositeUpdatedAt"] = row["updated_at"]

    for row in successful_search_rows:
        record = _search_record(row["product_id"])
        if record is None:
            continue
        source_id = str(row["source_id"])
        source = by_source.setdefault(source_id, _empty_ledger_source(source_id))
        previous_updated_at = str(source.get("latestSuccessfulSearchUpdatedAt") or "")
        candidate_updated_at = str(row["updated_at"] or "")
        if previous_updated_at and candidate_updated_at <= previous_updated_at:
            continue
        source["latestSuccessfulSearchAoiId"] = record["aoiId"]
        source["latestSuccessfulSearchDatetimeRange"] = record["datetimeRange"]
        source["latestSuccessfulSearchUpdatedAt"] = row["updated_at"]

    for source_id, by_aoi in per_source_composites_by_aoi.items():
        source = by_source.setdefault(source_id, _empty_ledger_source(source_id))
        source["latestSuccessfulComposites"] = sorted(
            by_aoi.values(),
            key=lambda item: (str(item.get("aoiId") or ""), str(item.get("date") or "")),
        )

    for source_id, counts in per_source_failure_counts.items():
        source = by_source.setdefault(source_id, _empty_ledger_source(source_id))
        source["failureCountsByKind"] = dict(counts)
        source["lastFailure"] = per_source_last_failure.get(source_id)

    return {
        "status": "ok",
        "path": None,
        "rowCount": total_rows,
        "statusCounts": status_counts,
        "bytes": total_bytes,
        "lastUpdatedAt": last_updated_at,
        "failureCountsByKind": dict(failure_counts),
        "lastFailures": failures_payload,
        "bySource": list(by_source.values()),
    }



# ---------------------------------------------------------------------------
# Scheduler job ledger helpers (Phase 9 — TASK-059)
# ---------------------------------------------------------------------------

#: Grace period in hours after ``next_due_at`` before a job is considered overdue.
_SCHEDULER_OVERDUE_GRACE_HOURS: int = 24


def _scheduler_jobs_by_source() -> dict[str, dict[str, Any]]:
    """Return the latest scheduler job summary keyed by ``source_id``.

    Reads the Phase 5 SQLite job ledger in *read-only* mode.  Returns an empty
    dict if the ledger is not configured, file is missing, or any read error
    occurs — callers must handle absent scheduler data gracefully.

    Only safe, non-secret fields are returned: ``job_id``, ``state``,
    ``updatedAt`` (resolved from finished/started/scheduled timestamps),
    ``nextDueAt``, and ``scheduleDecision``.  Raw paths (``artifact_summary_path``)
    and provider-specific fields are never included.
    """
    path_str = getattr(settings, "scheduler_job_ledger_path", "")
    if not path_str or not path_str.strip():
        return {}
    path = Path(path_str)
    if not path.is_file():
        return {}
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT job_id, source_id, state,
                       scheduled_at, started_at, finished_at,
                       next_due_at, schedule_decision
                FROM scheduler_jobs
                ORDER BY coalesce(scheduled_at, '1970-01-01T00:00:00') DESC
            """).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - monitoring must remain fail-soft.
        return {}

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = str(row["source_id"])
        if source_id in result:
            continue  # keep only the latest (first in DESC order)
        updated_at = row["finished_at"] or row["started_at"] or row["scheduled_at"]
        result[source_id] = {
            "jobId": row["job_id"],
            "state": row["state"],
            "updatedAt": updated_at,
            "nextDueAt": row["next_due_at"],
            "scheduleDecision": row["schedule_decision"],
        }
    return result


def _scheduler_due_fields(
    scheduler_job: dict[str, Any] | None, *, now: datetime
) -> dict[str, Any]:
    """Derive schedule due/overdue state from the latest scheduler job row.

    Returns the seven scheduler-linkage fields that are injected into each
    ``ImagerySourceMonitoringSource`` payload.
    """
    if not scheduler_job:
        return {
            "latestSchedulerJobId": None,
            "latestSchedulerJobState": None,
            "latestSchedulerJobUpdatedAt": None,
            "schedulerNextDueAt": None,
            "schedulerIsDue": False,
            "schedulerIsOverdue": False,
            "schedulerDueReason": None,
        }

    job_id = scheduler_job.get("jobId")
    state = scheduler_job.get("state")
    updated_at = scheduler_job.get("updatedAt")
    next_due_at_raw = scheduler_job.get("nextDueAt")
    schedule_decision = scheduler_job.get("scheduleDecision")

    next_due_at_dt = _parse_datetime(next_due_at_raw)
    is_due = next_due_at_dt is not None and next_due_at_dt <= now
    is_overdue = False
    due_reason: str | None = None

    if is_due:
        elapsed_hours = (now - next_due_at_dt).total_seconds() / 3600
        is_overdue = elapsed_hours > _SCHEDULER_OVERDUE_GRACE_HOURS
        if schedule_decision:
            due_reason = str(schedule_decision)
        else:
            due_reason = "cadence_elapsed"

    return {
        "latestSchedulerJobId": job_id,
        "latestSchedulerJobState": state,
        "latestSchedulerJobUpdatedAt": updated_at,
        "schedulerNextDueAt": next_due_at_raw,
        "schedulerIsDue": is_due,
        "schedulerIsOverdue": is_overdue,
        "schedulerDueReason": due_reason,
    }


def _s3_client():
    import boto3  # noqa: PLC0415
    from botocore.config import Config as BotoConfig  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _storage_usage() -> dict[str, Any]:
    if not (
        settings.s3_endpoint_url.strip()
        and settings.s3_access_key.strip()
        and settings.s3_secret_key.strip()
        and settings.cog_bucket.strip()
    ):
        return {"status": "unconfigured", "bucket": settings.cog_bucket or None}

    try:
        client = _s3_client()
        client.head_bucket(Bucket=settings.cog_bucket)
        paginator = client.get_paginator("list_objects_v2")
        object_count = 0
        total_bytes = 0
        zero_byte_object_count = 0
        by_prefix: dict[str, dict[str, Any]] = {}
        for page in paginator.paginate(Bucket=settings.cog_bucket):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key") or "")
                size = int(obj.get("Size") or 0)
                prefix = key.split("/", 1)[0] if "/" in key else "_root"
                bucket = by_prefix.setdefault(
                    prefix,
                    {
                        "prefix": prefix,
                        "objectCount": 0,
                        "bytes": 0,
                        "zeroByteObjectCount": 0,
                    },
                )
                bucket["objectCount"] += 1
                bucket["bytes"] += size
                if size == 0:
                    bucket["zeroByteObjectCount"] += 1
                    zero_byte_object_count += 1
                object_count += 1
                total_bytes += size
        return {
            "status": "ok",
            "bucket": settings.cog_bucket,
            "objectCount": object_count,
            "bytes": total_bytes,
            "zeroByteObjectCount": zero_byte_object_count,
            "byPrefix": sorted(by_prefix.values(), key=lambda item: str(item["prefix"])),
        }
    except Exception as exc:  # noqa: BLE001 - monitoring must remain fail-soft.
        return {
            "status": "unavailable",
            "bucket": settings.cog_bucket,
            "lastError": f"{exc.__class__.__name__}: {str(exc)[:200]}",
        }


def _ledger_source_fields(ledger_source: dict[str, Any] | None) -> dict[str, Any]:
    ledger_source = ledger_source or {}
    return {
        "latestSuccessfulCompositeDate": ledger_source.get("latestSuccessfulCompositeDate"),
        "latestSuccessfulCompositeProductId": ledger_source.get(
            "latestSuccessfulCompositeProductId"
        ),
        "latestSuccessfulCompositeAoiId": ledger_source.get("latestSuccessfulCompositeAoiId"),
        "latestSuccessfulCompositeUpdatedAt": ledger_source.get(
            "latestSuccessfulCompositeUpdatedAt"
        ),
        "latestSuccessfulComposites": ledger_source.get("latestSuccessfulComposites") or [],
        "latestSuccessfulSearchAoiId": ledger_source.get("latestSuccessfulSearchAoiId"),
        "latestSuccessfulSearchDatetimeRange": ledger_source.get(
            "latestSuccessfulSearchDatetimeRange"
        ),
        "latestSuccessfulSearchUpdatedAt": ledger_source.get(
            "latestSuccessfulSearchUpdatedAt"
        ),
        "ingestionFailureCountsByKind": ledger_source.get("failureCountsByKind") or {},
        "lastIngestionFailure": ledger_source.get("lastFailure"),
    }


def _successful_composite_freshness(
    ledger_fields: dict[str, Any], *, today: date, availability: str
) -> dict[str, Any]:
    latest_day = _parse_date(ledger_fields.get("latestSuccessfulCompositeDate"))
    days_since = (today - latest_day).days if latest_day else None
    stale = (
        availability != "gated"
        and days_since is not None
        and days_since > settings.source_freshness_stale_days
    )
    return {
        "daysSinceLatestSuccessfulComposite": days_since,
        "isSuccessfulCompositeStale": stale,
    }


def _successful_search_freshness(
    ledger_fields: dict[str, Any],
    *,
    today: date,
    availability: str,
    is_field_optical: bool,
) -> dict[str, Any]:
    latest_search = _parse_datetime(ledger_fields.get("latestSuccessfulSearchUpdatedAt"))
    days_since = (today - latest_search.date()).days if latest_search else None
    stale = (
        availability != "gated"
        and is_field_optical
        and days_since is not None
        and days_since > settings.source_freshness_stale_days
    )
    missing = availability != "gated" and is_field_optical and latest_search is None
    return {
        "daysSinceLatestSuccessfulSearch": days_since,
        "isSuccessfulSearchStale": stale,
        "isSuccessfulSearchMissing": missing,
    }


def _unresolved_ingestion_failure(ledger_fields: dict[str, Any]) -> bool:
    failure = ledger_fields.get("lastIngestionFailure")
    if not isinstance(failure, dict):
        return False
    failure_at = _parse_datetime(failure.get("updatedAt"))
    if failure_at is None:
        return True
    successful_timestamps = [
        _parse_datetime(ledger_fields.get("latestSuccessfulSearchUpdatedAt")),
        _parse_datetime(ledger_fields.get("latestSuccessfulCompositeUpdatedAt")),
    ]
    latest_success = max(
        (value for value in successful_timestamps if value is not None),
        default=None,
    )
    return latest_success is None or failure_at > latest_success


def _source_status(payload: dict[str, Any]) -> dict[str, Any]:
    availability = str(payload.get("availabilityStatus") or "active")
    warnings = {str(value) for value in payload.get("warnings", [])}
    reasons: list[str] = []
    has_error = False
    has_warning = False

    if availability == "gated":
        has_warning = True
        reasons.append("SOURCE_GATED")

    if payload.get("lastError"):
        has_error = True
        reasons.append("MONITORING_LOOKUP_FAILED")

    upstream_stale_allowed = bool(payload.get("isUpstreamDataStale"))
    warning_error_reasons = {
        "DATE_LOOKUP_FAILED",
        "NO_AVAILABLE_DATES",
        "LATEST_SUCCESSFUL_SEARCH_STALE",
        "NO_SUCCESSFUL_SEARCH",
        "UNRESOLVED_INGESTION_FAILURE",
        "NO_TILE_AVAILABLE_DATES",
        "LOW_COVERAGE_PERCENT",
        "LOW_USABLE_PIXEL_PERCENT",
    }
    for warning in sorted(warnings):
        if warning == "SOURCE_GATED":
            continue
        if warning in {
            "LATEST_DATE_STALE",
            "LATEST_SUCCESSFUL_COMPOSITE_STALE",
            "UPSTREAM_DATA_STALE",
        } and upstream_stale_allowed:
            has_warning = True
            reasons.append(warning)
            continue
        if warning in {"LATEST_DATE_STALE", "LATEST_SUCCESSFUL_COMPOSITE_STALE"}:
            has_error = True
            reasons.append(warning)
            continue
        if availability != "gated" and warning in warning_error_reasons:
            has_error = True
        else:
            has_warning = True
        reasons.append(warning)

    if (
        availability != "gated"
        and payload.get("kind") == "optical"
        and payload.get("analysisLevel") == "field"
        and not payload.get("latestSuccessfulCompositeDate")
    ):
        has_error = True
        reasons.append("NO_SUCCESSFUL_COMPOSITE")

    if payload.get("tileUnavailableReasons") and "NO_TILE_AVAILABLE_DATES" not in reasons:
        has_warning = True
        reasons.append("SOME_TILE_UNAVAILABLE_DATES")

    if has_error:
        status = "error"
    elif has_warning:
        status = "warning"
    else:
        status = "ok"
    return {
        **payload,
        "status": status,
        "statusReasons": list(dict.fromkeys(reasons)),
    }


def _summarize_source(
    source: dict[str, Any],
    *,
    today: date,
    ledger_source: dict[str, Any] | None = None,
    scheduler_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    source_id = source["id"]
    availability = source.get("availabilityStatus") or "active"
    warnings: list[str] = []
    ledger_fields = _ledger_source_fields(ledger_source)
    scheduler_fields = _scheduler_due_fields(scheduler_job, now=now)
    is_field_optical = source.get("kind") == "optical" and source.get("analysisLevel") == "field"
    composite_freshness = _successful_composite_freshness(
        ledger_fields,
        today=today,
        availability=availability,
    )
    if composite_freshness["isSuccessfulCompositeStale"]:
        warnings.append("LATEST_SUCCESSFUL_COMPOSITE_STALE")
    search_freshness = _successful_search_freshness(
        ledger_fields,
        today=today,
        availability=availability,
        is_field_optical=is_field_optical,
    )
    if search_freshness["isSuccessfulSearchMissing"]:
        warnings.append("NO_SUCCESSFUL_SEARCH")
    elif search_freshness["isSuccessfulSearchStale"]:
        warnings.append("LATEST_SUCCESSFUL_SEARCH_STALE")
    has_unresolved_ingestion_failure = _unresolved_ingestion_failure(ledger_fields)
    if availability != "gated" and has_unresolved_ingestion_failure:
        warnings.append("UNRESOLVED_INGESTION_FAILURE")

    try:
        dates = catalog.list_dates(source_id)
    except Exception as exc:  # noqa: BLE001 - monitoring must degrade per source.
        is_gated = availability == "gated"
        lookup_warnings = ["SOURCE_GATED"] if is_gated else ["DATE_LOOKUP_FAILED"]
        return _source_status({
            "sourceId": source_id,
            "label": source.get("label"),
            "provider": source.get("provider"),
            "kind": source.get("kind"),
            "availabilityStatus": availability,
            "analysisLevel": source.get("analysisLevel"),
            "refreshPolicy": source.get("refreshPolicy"),
            "latestAvailableDate": None,
            "latestUsableDate": None,
            "daysSinceLatestAvailable": None,
            "staleAfterDays": settings.source_freshness_stale_days,
            "isStale": not is_gated,
            "dateCount": 0,
            "tileAvailableDateCount": 0,
            "coveragePercent": None,
            "usablePixelPercent": None,
            "cloudMaskedPercent": None,
            "metricsProvisional": bool(source.get("metricsProvisional", False)),
            "gatedReason": source.get("gatedReason"),
            "warnings": [*warnings, *lookup_warnings],
            "tileUnavailableReasons": [],
            "lastError": f"{exc.__class__.__name__}: {str(exc)[:200]}",
            **ledger_fields,
            **composite_freshness,
            "daysSinceLatestSuccessfulSearch": search_freshness[
                "daysSinceLatestSuccessfulSearch"
            ],
            "isSuccessfulSearchStale": search_freshness["isSuccessfulSearchStale"],
            "isUpstreamDataStale": False,
            "hasUnresolvedIngestionFailure": has_unresolved_ingestion_failure,
            **scheduler_fields,
        })

    tile_available_dates = [entry for entry in dates if bool(entry.get("tileAvailable", True))]
    tile_unavailable_reasons = sorted(
        {
            str(entry.get("unavailableReason")).strip()
            for entry in dates
            if not bool(entry.get("tileAvailable", True))
            and str(entry.get("unavailableReason") or "").strip()
        }
    )
    latest_available = _latest_date(dates)
    latest_usable = _latest_date(tile_available_dates, usable_only=True) or _latest_date(
        tile_available_dates
    )

    latest_available_day = _parse_date(
        latest_available.get("acquisitionDate") if latest_available else None
    )
    days_since_latest = (today - latest_available_day).days if latest_available_day else None

    is_gated = availability == "gated"
    stale = False
    has_fresh_successful_search = (
        is_field_optical
        and not search_freshness["isSuccessfulSearchMissing"]
        and not search_freshness["isSuccessfulSearchStale"]
    )
    if is_gated:
        warnings.append("SOURCE_GATED")
    elif latest_available_day is None:
        stale = True
        warnings.append("NO_AVAILABLE_DATES")
    elif days_since_latest is not None and days_since_latest > settings.source_freshness_stale_days:
        stale = True
        warnings.append("LATEST_DATE_STALE")

    if dates and not tile_available_dates:
        warnings.append("NO_TILE_AVAILABLE_DATES")

    latest_metrics = latest_usable or latest_available or {}
    coverage_percent = latest_metrics.get("coveragePercent")
    if (
        not is_gated
        and is_field_optical
        and isinstance(coverage_percent, (int, float))
        and float(coverage_percent) < settings.source_coverage_threshold_percent
    ):
        warnings.append("LOW_COVERAGE_PERCENT")
    usable_pixel_percent = latest_metrics.get("usablePixelPercent")
    if (
        not is_gated
        and is_field_optical
        and isinstance(usable_pixel_percent, (int, float))
        and float(usable_pixel_percent) < settings.usable_pixel_threshold_percent
    ):
        warnings.append("LOW_USABLE_PIXEL_PERCENT")
    latest_composite_date = ledger_fields.get("latestSuccessfulCompositeDate")
    is_upstream_data_stale = (
        stale
        and has_fresh_successful_search
        and latest_available_day is not None
        and latest_composite_date == (
            latest_available.get("acquisitionDate") if latest_available else None
        )
    )
    if is_upstream_data_stale:
        warnings.append("UPSTREAM_DATA_STALE")
    return _source_status({
        "sourceId": source_id,
        "label": source.get("label"),
        "provider": source.get("provider"),
        "kind": source.get("kind"),
        "availabilityStatus": availability,
        "analysisLevel": source.get("analysisLevel"),
        "refreshPolicy": source.get("refreshPolicy"),
        "latestAvailableDate": (
            latest_available.get("acquisitionDate") if latest_available else None
        ),
        "latestUsableDate": latest_usable.get("acquisitionDate") if latest_usable else None,
        "daysSinceLatestAvailable": days_since_latest,
        "staleAfterDays": settings.source_freshness_stale_days,
        "isStale": stale,
        "dateCount": len(dates),
        "tileAvailableDateCount": len(tile_available_dates),
        "coveragePercent": coverage_percent,
        "usablePixelPercent": usable_pixel_percent,
        "cloudMaskedPercent": latest_metrics.get("cloudMaskedPercent"),
        "metricsProvisional": bool(
            latest_metrics.get("metricsProvisional", source.get("metricsProvisional", False))
        ),
        "gatedReason": source.get("gatedReason"),
        "warnings": warnings,
        "tileUnavailableReasons": tile_unavailable_reasons,
        **ledger_fields,
        **composite_freshness,
        "daysSinceLatestSuccessfulSearch": search_freshness[
            "daysSinceLatestSuccessfulSearch"
        ],
        "isSuccessfulSearchStale": search_freshness["isSuccessfulSearchStale"],
        "isUpstreamDataStale": is_upstream_data_stale,
        "hasUnresolvedIngestionFailure": has_unresolved_ingestion_failure,
        **scheduler_fields,
    })


def _overall_monitoring_status(
    *,
    sources: list[dict[str, Any]],
    storage: dict[str, Any],
    ingestion_ledger: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    has_error = False
    has_warning = False

    storage_status = storage.get("status")
    if storage_status not in {"ok", "disabled"}:
        if storage_status in {"unavailable", "error"}:
            has_error = True
            reasons.append("STORAGE_UNAVAILABLE")
        else:
            has_warning = True
            reasons.append("STORAGE_NOT_READY")
    zero_count = storage.get("zeroByteObjectCount")
    if isinstance(zero_count, int) and zero_count > 0:
        has_error = True
        reasons.append("ZERO_BYTE_STORAGE_OBJECTS")

    ledger_status = ingestion_ledger.get("status")
    if ledger_status in {"unavailable", "error"}:
        has_error = True
        reasons.append("INGESTION_LEDGER_UNAVAILABLE")
    elif ledger_status in {"missing", "unconfigured"}:
        has_warning = True
        reasons.append("INGESTION_LEDGER_NOT_READY")

    for source in sources:
        source_status = source.get("status")
        source_id = str(source.get("sourceId") or "unknown-source")
        if source_status == "error":
            has_error = True
            reasons.append(f"SOURCE_ERROR:{source_id}")
        elif source_status == "warning":
            has_warning = True
            reasons.append(f"SOURCE_WARNING:{source_id}")

    if has_error:
        status = "error"
    elif has_warning:
        status = "warning"
    else:
        status = "ok"
    return {"status": status, "statusReasons": list(dict.fromkeys(reasons))}


@router.get("/imagery-sources", response_model=ImagerySourceMonitoringResponse)
async def get_imagery_source_monitoring() -> ImagerySourceMonitoringResponse:
    """Freshness and coverage status for operator refresh triage."""
    generated_at = _now()
    today = generated_at.date()
    ingestion_ledger = _sanitize_monitoring_payload(_ingestion_ledger_summary())
    ledger_sources = {
        str(source.get("sourceId")): source
        for source in ingestion_ledger.get("bySource", [])
        if isinstance(source, dict) and source.get("sourceId")
    }
    scheduler_jobs = _scheduler_jobs_by_source()
    sources = [
        _summarize_source(
            source,
            today=today,
            ledger_source=ledger_sources.get(str(source.get("id"))),
            scheduler_job=scheduler_jobs.get(str(source.get("id"))),
        )
        for source in catalog.list_sources()
    ]
    storage = _storage_usage()
    status_payload = _overall_monitoring_status(
        sources=sources,
        storage=storage,
        ingestion_ledger=ingestion_ledger,
    )
    return {
        "generatedAt": generated_at.isoformat().replace("+00:00", "Z"),
        **status_payload,
        "staleAfterDays": settings.source_freshness_stale_days,
        "coverageThresholdPercent": settings.source_coverage_threshold_percent,
        "usablePixelThresholdPercent": settings.usable_pixel_threshold_percent,
        "sources": sources,
        "storage": storage,
        "ingestionLedger": ingestion_ledger,
    }
