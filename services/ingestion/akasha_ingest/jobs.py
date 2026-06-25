"""Scheduler job IDs, artifact directories, and lifecycle helpers.

Implements TASK-021 and TASK-028 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Responsibilities
----------------
- Generate opaque, deterministic-enough job IDs (timestamp + short UUID4 hex).
  No raw filesystem paths or provider IDs are embedded in job IDs.
- Create canonical job artifact directories under a configurable base path.
- Write and update per-job artifact files:
    - ``request.json``      — redacted scheduler request parameters.
    - ``status.json``       — current job lifecycle state + metadata.
    - ``command.txt``       — CLI/invocation string written before execution.
    - ``result.json``       — redacted final outcome after the job finishes.
    - ``events.jsonl``      — append-only structured event timeline (one JSON
                              object per line, ISO-8601 timestamps).
    - ``observability.json`` — rich redacted observability summary (TASK-028):
                              provider input summary, provider response summary,
                              canonical manifest handles, verification summary,
                              and next-due estimate.
- Expose a clear status lifecycle enum covering every state the scheduler
  may assign: planned / queued / running / succeeded / failed /
  validation_failed / blocked_by_lock / cancelled / skipped_not_due /
  skipped_gated.
- Apply ``redact_value`` from ``akasha_ingest.manifests`` before writing any
  payload containing provider inputs, parameters, or error details.

Design constraints
------------------
- stdlib only — no live provider calls, no third-party imports.
- No circular dependencies: imports only from ``akasha_ingest.manifests``
  (for ``redact_value`` / ``REDACTION_VERSION``) and Python stdlib.
- Thread-safe artifact writes use ``os.replace`` (atomic rename) for the
  status file; events use append-mode with a flush call.
- Callers must pass an explicit ``base_dir``; tests use temp directories.
  Production default is ``/srv/akasha/ingestion/scheduler/jobs``.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .manifests import REDACTION_VERSION, redact_value

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Production base directory for job artifacts (Phase 0 contract).
DEFAULT_JOB_BASE_DIR: str = "/srv/akasha/ingestion/scheduler/jobs"

#: Artifact file names written under each job directory.
REQUEST_FILE = "request.json"
STATUS_FILE = "status.json"
COMMAND_FILE = "command.txt"
RESULT_FILE = "result.json"
EVENTS_FILE = "events.jsonl"
#: Rich observability summary (TASK-028); API/UI-safe, all secrets redacted.
OBSERVABILITY_FILE = "observability.json"

#: Version for the job artifact schema (bump when breaking changes are made).
JOB_ARTIFACT_VERSION = 1

#: Artifact-type tokens used as the second component of opaque artifact handles.
#: Raw file names are never exposed to API/UI callers; callers receive a handle
#: and the server resolves it to the actual file path.
ARTIFACT_TYPE_REQUEST = "request"
ARTIFACT_TYPE_STATUS = "status"
ARTIFACT_TYPE_RESULT = "result"
ARTIFACT_TYPE_EVENTS = "events"
ARTIFACT_TYPE_OBSERVABILITY = "observability"
ARTIFACT_TYPE_SEARCH_MANIFEST = "search_manifest"
ARTIFACT_TYPE_DOWNLOAD_MANIFEST = "download_manifest"
ARTIFACT_TYPE_PREPARE_MANIFEST = "prepare_manifest"


# ---------------------------------------------------------------------------
# Job status lifecycle enum
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    """Canonical scheduler job lifecycle states.

    States progress forward (planned → queued → running → terminal).
    Any state may transition directly to a terminal state if the job is
    cancelled, blocked, or skipped before it reaches ``running``.
    """

    PLANNED = "planned"
    """Job has been identified as due but not yet enqueued for execution."""

    QUEUED = "queued"
    """Job is in the execution queue; a worker has not started it yet."""

    RUNNING = "running"
    """Worker has started executing the job (provider calls may be live)."""

    SUCCEEDED = "succeeded"
    """Job completed successfully; all required artifacts were produced."""

    FAILED = "failed"
    """Job terminated with an unexpected error (provider, disk, network)."""

    VALIDATION_FAILED = "validation_failed"
    """Job finished but the produced output did not pass validation checks.
    The source/product remains gated; see ``failureKind`` for detail."""

    BLOCKED_BY_LOCK = "blocked_by_lock"
    """A concurrency lock prevented this job from starting (another job
    for the same source/AOI is already running)."""

    CANCELLED = "cancelled"
    """Job was explicitly cancelled by an operator before it completed."""

    SKIPPED_NOT_DUE = "skipped_not_due"
    """Scheduler determined this source is not yet due based on cadence."""

    SKIPPED_GATED = "skipped_gated"
    """Source is gated (commercial_blocked, background_only, out_of_AOI,
    or a capability flag is disabled) and will not run in product mode."""


#: Terminal states — once a job reaches these, its status file must not
#: transition to another state.
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.VALIDATION_FAILED,
        JobStatus.BLOCKED_BY_LOCK,
        JobStatus.CANCELLED,
        JobStatus.SKIPPED_NOT_DUE,
        JobStatus.SKIPPED_GATED,
    }
)

#: Non-terminal states — job may still transition forward.
ACTIVE_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.PLANNED,
        JobStatus.QUEUED,
        JobStatus.RUNNING,
    }
)


# ---------------------------------------------------------------------------
# Job ID generation
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def make_job_id(*, source_id: str, aoi_id: str, now: datetime | None = None) -> str:
    """Generate an opaque, globally unique job ID.

    Format: ``job_{yyyymmddTHHMMSSZ}_{short_uuid}``

    The timestamp component makes IDs sortable and human-readable in logs.
    The UUID4 suffix ensures uniqueness even when jobs are created in rapid
    succession for the same source/AOI.

    No raw filesystem paths or provider credentials are embedded in the ID.

    Parameters
    ----------
    source_id:
        Source identifier (used only to seed entropy — *not* embedded in ID).
    aoi_id:
        AOI identifier (used only for entropy context — *not* embedded in ID).
    now:
        Optional UTC datetime override; defaults to ``datetime.now(UTC)``.
        Pass a fixed datetime in tests for determinism.

    Returns
    -------
    str
        An opaque job ID string safe to use as a directory name or database key.
    """
    _ = source_id  # consumed for entropy context; not embedded
    _ = aoi_id
    ts = now if now is not None else _utc_now()
    ts_part = ts.strftime("%Y%m%dT%H%M%SZ")
    uid_part = uuid.uuid4().hex[:12]
    return f"job_{ts_part}_{uid_part}"


# ---------------------------------------------------------------------------
# Artifact directory management
# ---------------------------------------------------------------------------


def job_dir(job_id: str, base_dir: str | Path = DEFAULT_JOB_BASE_DIR) -> Path:
    """Return the canonical artifact directory path for *job_id*.

    The directory is **not** created by this function; call
    :func:`create_job_dir` to ensure it exists.
    """
    return Path(base_dir) / job_id


def create_job_dir(job_id: str, base_dir: str | Path = DEFAULT_JOB_BASE_DIR) -> Path:
    """Create and return the artifact directory for *job_id*.

    Creates all intermediate parent directories if they do not exist.
    Idempotent — safe to call if the directory already exists.
    """
    d = job_dir(job_id, base_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Artifact dataclasses
# ---------------------------------------------------------------------------


@dataclass
class JobRequest:
    """Parameters that caused this job to be scheduled.

    Written to ``request.json`` before any provider call is made.
    All provider-supplied parameters (credentials, tokens) are redacted
    via :func:`akasha_ingest.manifests.redact_value` before storage.
    """

    job_id: str
    source_id: str
    aoi_id: str
    provider: str
    scheduled_at: str
    """ISO-8601 UTC timestamp when the job was first created."""

    window_start: str
    """ISO-8601 date or datetime (inclusive) of the search/composite window."""

    window_end: str
    """ISO-8601 date or datetime (inclusive) of the search/composite window."""

    dry_run: bool = False
    trigger: str = "scheduler"
    """What caused this job: ``scheduler``, ``manual``, ``backfill``, etc."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Additional source/provider-specific request metadata (will be redacted)."""

    artifact_version: int = JOB_ARTIFACT_VERSION
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a redaction-safe dict suitable for writing to disk."""
        return {
            "artifactVersion": self.artifact_version,
            "redactionVersion": self.redaction_version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "provider": self.provider,
            "scheduledAt": self.scheduled_at,
            "windowStart": self.window_start,
            "windowEnd": self.window_end,
            "dryRun": self.dry_run,
            "trigger": self.trigger,
            "extra": redact_value(self.extra),
        }


@dataclass
class JobStatusRecord:
    """Mutable job lifecycle state written to ``status.json``.

    Updated atomically (write-to-temp + ``os.replace``) on each state
    transition so readers always see a consistent snapshot.
    """

    job_id: str
    source_id: str
    aoi_id: str
    provider: str
    status: JobStatus
    created_at: str
    updated_at: str

    started_at: str | None = None
    finished_at: str | None = None
    failure_kind: str | None = None
    """Machine-readable failure category, e.g. ``"low_coverage"``, ``"auth"``."""

    failure_message: str | None = None
    """Short human-readable summary (do not include secrets)."""

    next_due_at: str | None = None
    """ISO-8601 UTC estimate for when this source is next due."""

    found_count: int | None = None
    selected_count: int | None = None
    downloaded_count: int | None = None
    rejected_count: int | None = None
    failed_count: int | None = None

    artifact_version: int = JOB_ARTIFACT_VERSION
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactVersion": self.artifact_version,
            "redactionVersion": self.redaction_version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "provider": self.provider,
            "status": str(self.status),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "failureKind": self.failure_kind,
            "failureMessage": self.failure_message,
            "nextDueAt": self.next_due_at,
            "foundCount": self.found_count,
            "selectedCount": self.selected_count,
            "downloadedCount": self.downloaded_count,
            "rejectedCount": self.rejected_count,
            "failedCount": self.failed_count,
        }


@dataclass
class JobResult:
    """Final outcome written to ``result.json`` when a job reaches a terminal state."""

    job_id: str
    source_id: str
    aoi_id: str
    status: JobStatus
    finished_at: str

    failure_kind: str | None = None
    failure_message: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    """Redacted summary stats: counts, coverage %, manifest paths, etc."""

    artifact_version: int = JOB_ARTIFACT_VERSION
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactVersion": self.artifact_version,
            "redactionVersion": self.redaction_version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "status": str(self.status),
            "finishedAt": self.finished_at,
            "failureKind": self.failure_kind,
            "failureMessage": self.failure_message,
            "summary": redact_value(self.summary),
        }


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically using a sibling temp file."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def write_request(
    job_id: str,
    request: JobRequest,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> Path:
    """Write ``request.json`` for *job_id*.

    Applies :func:`~akasha_ingest.manifests.redact_value` to ``extra``
    before serialisation.

    Returns
    -------
    Path
        The path of the written file.
    """
    d = create_job_dir(job_id, base_dir)
    path = d / REQUEST_FILE
    _write_json_atomic(path, request.to_dict())
    return path


def write_status(
    job_id: str,
    record: JobStatusRecord,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> Path:
    """Write (or overwrite) ``status.json`` for *job_id* atomically.

    Returns
    -------
    Path
        The path of the written file.
    """
    d = create_job_dir(job_id, base_dir)
    path = d / STATUS_FILE
    _write_json_atomic(path, record.to_dict())
    return path


def write_command(
    job_id: str,
    command: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> Path:
    """Write the CLI/invocation string to ``command.txt``.

    The command string is written as-is; callers must ensure no secrets are
    passed as inline arguments (use env vars instead).

    Returns
    -------
    Path
        The path of the written file.
    """
    d = create_job_dir(job_id, base_dir)
    path = d / COMMAND_FILE
    path.write_text(command, encoding="utf-8")
    return path


def write_result(
    job_id: str,
    result: JobResult,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> Path:
    """Write ``result.json`` for *job_id*.

    Applies :func:`~akasha_ingest.manifests.redact_value` to ``summary``
    before serialisation.

    Returns
    -------
    Path
        The path of the written file.
    """
    d = create_job_dir(job_id, base_dir)
    path = d / RESULT_FILE
    _write_json_atomic(path, result.to_dict())
    return path


def append_event(
    job_id: str,
    event_type: str,
    payload: dict[str, Any],
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    *,
    now: datetime | None = None,
) -> None:
    """Append one structured event to ``events.jsonl``.

    Each line is a complete JSON object with at minimum:
    - ``timestamp`` — ISO-8601 UTC string.
    - ``jobId``     — the owning job ID.
    - ``eventType`` — caller-supplied category string.
    - ``payload``   — redacted event-specific data.

    Parameters
    ----------
    job_id:
        The job this event belongs to.
    event_type:
        Short category string, e.g. ``"status_change"``, ``"search_done"``,
        ``"download_progress"``, ``"validation_result"``, ``"error"``.
    payload:
        Arbitrary dict with event detail; secrets are redacted before writing.
    base_dir:
        Root under which job directories are stored.
    now:
        UTC datetime override (useful in tests for deterministic timestamps).
    """
    ts = (now if now is not None else _utc_now()).isoformat().replace("+00:00", "Z")
    entry: dict[str, Any] = {
        "timestamp": ts,
        "jobId": job_id,
        "eventType": event_type,
        "payload": redact_value(payload),
    }
    d = create_job_dir(job_id, base_dir)
    events_path = d / EVENTS_FILE
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False))
        fh.write("\n")
        fh.flush()


# ---------------------------------------------------------------------------
# High-level lifecycle helpers
# ---------------------------------------------------------------------------


def _now_iso(now: datetime | None = None) -> str:
    ts = now if now is not None else _utc_now()
    return ts.isoformat().replace("+00:00", "Z")


def create_job(
    *,
    source_id: str,
    aoi_id: str,
    provider: str,
    window_start: str,
    window_end: str,
    dry_run: bool = False,
    trigger: str = "scheduler",
    extra: dict[str, Any] | None = None,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    now: datetime | None = None,
) -> tuple[str, Path]:
    """Create a new job: generate ID, write ``request.json`` and initial ``status.json``.

    Parameters
    ----------
    source_id, aoi_id, provider:
        Identify the source being scheduled.
    window_start, window_end:
        ISO-8601 dates/datetimes for the search window.
    dry_run:
        Whether this is a dry-run invocation.
    trigger:
        What triggered the job (``"scheduler"``, ``"manual"``, ``"backfill"``).
    extra:
        Optional extra request metadata; redacted before writing.
    base_dir:
        Root directory for job artifacts.
    now:
        UTC datetime override for tests.

    Returns
    -------
    tuple[str, Path]
        ``(job_id, job_directory)``.
    """
    ts_str = _now_iso(now)
    job_id = make_job_id(source_id=source_id, aoi_id=aoi_id, now=now)
    request = JobRequest(
        job_id=job_id,
        source_id=source_id,
        aoi_id=aoi_id,
        provider=provider,
        scheduled_at=ts_str,
        window_start=window_start,
        window_end=window_end,
        dry_run=dry_run,
        trigger=trigger,
        extra=extra or {},
    )
    status = JobStatusRecord(
        job_id=job_id,
        source_id=source_id,
        aoi_id=aoi_id,
        provider=provider,
        status=JobStatus.PLANNED,
        created_at=ts_str,
        updated_at=ts_str,
    )
    d = create_job_dir(job_id, base_dir)
    write_request(job_id, request, base_dir)
    write_status(job_id, status, base_dir)
    append_event(
        job_id,
        "job_created",
        {"sourceId": source_id, "aoiId": aoi_id, "provider": provider, "trigger": trigger},
        base_dir,
        now=now,
    )
    return job_id, d


def transition_status(
    job_id: str,
    new_status: JobStatus,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    *,
    failure_kind: str | None = None,
    failure_message: str | None = None,
    next_due_at: str | None = None,
    found_count: int | None = None,
    selected_count: int | None = None,
    downloaded_count: int | None = None,
    rejected_count: int | None = None,
    failed_count: int | None = None,
    now: datetime | None = None,
) -> JobStatusRecord:
    """Read current ``status.json``, apply transition, and write back atomically.

    Also appends a ``status_change`` event to ``events.jsonl``.

    Raises
    ------
    ValueError
        If the current status is already terminal and ``new_status`` is
        different (guards against accidental double-transition).

    Returns
    -------
    JobStatusRecord
        The updated status record.
    """
    d = job_dir(job_id, base_dir)
    status_path = d / STATUS_FILE
    if not status_path.exists():
        raise FileNotFoundError(f"status.json not found for job {job_id!r} in {d}")

    raw = json.loads(status_path.read_text(encoding="utf-8"))
    current_status = JobStatus(raw["status"])

    if current_status in TERMINAL_STATUSES and new_status != current_status:
        raise ValueError(
            f"Job {job_id!r} is already in terminal state {current_status!r}; "
            f"cannot transition to {new_status!r}."
        )

    ts_str = _now_iso(now)
    record = JobStatusRecord(
        job_id=job_id,
        source_id=raw["sourceId"],
        aoi_id=raw["aoiId"],
        provider=raw["provider"],
        status=new_status,
        created_at=raw["createdAt"],
        updated_at=ts_str,
        started_at=raw.get("startedAt"),
        finished_at=raw.get("finishedAt"),
        failure_kind=failure_kind if failure_kind is not None else raw.get("failureKind"),
        failure_message=(
            failure_message if failure_message is not None else raw.get("failureMessage")
        ),
        next_due_at=next_due_at if next_due_at is not None else raw.get("nextDueAt"),
        found_count=found_count if found_count is not None else raw.get("foundCount"),
        selected_count=(
            selected_count if selected_count is not None else raw.get("selectedCount")
        ),
        downloaded_count=(
            downloaded_count if downloaded_count is not None else raw.get("downloadedCount")
        ),
        rejected_count=(
            rejected_count if rejected_count is not None else raw.get("rejectedCount")
        ),
        failed_count=failed_count if failed_count is not None else raw.get("failedCount"),
    )

    # Set started_at on first transition to running.
    if new_status == JobStatus.RUNNING and record.started_at is None:
        record.started_at = ts_str
    # Set finished_at when entering a terminal state.
    if new_status in TERMINAL_STATUSES and record.finished_at is None:
        record.finished_at = ts_str

    write_status(job_id, record, base_dir)
    append_event(
        job_id,
        "status_change",
        {
            "from": str(current_status),
            "to": str(new_status),
            "failureKind": failure_kind,
        },
        base_dir,
        now=now,
    )
    return record


def finish_job(
    job_id: str,
    status: JobStatus,
    summary: dict[str, Any],
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    *,
    failure_kind: str | None = None,
    failure_message: str | None = None,
    now: datetime | None = None,
) -> JobResult:
    """Transition a job to a terminal state and write ``result.json``.

    Calls :func:`transition_status` then writes the result artifact.

    Parameters
    ----------
    job_id:
        The job to finalise.
    status:
        Must be a member of :data:`TERMINAL_STATUSES`.
    summary:
        Outcome summary dict; secrets are redacted before writing.
    base_dir:
        Root directory for job artifacts.
    failure_kind, failure_message:
        Forwarded to :func:`transition_status`.
    now:
        UTC datetime override for tests.

    Returns
    -------
    JobResult
        The written result record.
    """
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"finish_job requires a terminal status; got {status!r}.")

    ts_str = _now_iso(now)
    transition_status(
        job_id,
        status,
        base_dir,
        failure_kind=failure_kind,
        failure_message=failure_message,
        now=now,
    )
    result = JobResult(
        job_id=job_id,
        source_id="",  # read from status on disk for full fidelity
        aoi_id="",
        status=status,
        finished_at=ts_str,
        failure_kind=failure_kind,
        failure_message=failure_message,
        summary=summary,
    )
    # Populate source_id/aoi_id from the status file written above.
    status_path = job_dir(job_id, base_dir) / STATUS_FILE
    if status_path.exists():
        raw = json.loads(status_path.read_text(encoding="utf-8"))
        result.source_id = raw.get("sourceId", "")
        result.aoi_id = raw.get("aoiId", "")
    write_result(job_id, result, base_dir)
    return result


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def read_status(
    job_id: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> dict[str, Any]:
    """Read and return the raw status dict from ``status.json``.

    Raises
    ------
    FileNotFoundError
        If the status file does not exist.
    """
    path = job_dir(job_id, base_dir) / STATUS_FILE
    if not path.exists():
        raise FileNotFoundError(f"status.json not found for job {job_id!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_request(
    job_id: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> dict[str, Any]:
    """Read and return the raw request dict from ``request.json``."""
    path = job_dir(job_id, base_dir) / REQUEST_FILE
    if not path.exists():
        raise FileNotFoundError(f"request.json not found for job {job_id!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_result(
    job_id: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> dict[str, Any]:
    """Read and return the raw result dict from ``result.json``."""
    path = job_dir(job_id, base_dir) / RESULT_FILE
    if not path.exists():
        raise FileNotFoundError(f"result.json not found for job {job_id!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_events(
    job_id: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> list[dict[str, Any]]:
    """Read all event timeline entries from ``events.jsonl``.

    Returns an empty list if the events file does not exist.
    """
    path = job_dir(job_id, base_dir) / EVENTS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# Opaque artifact handles (TASK-028)
# ---------------------------------------------------------------------------


def make_artifact_handle(job_id: str, artifact_type: str) -> str:
    """Return an opaque artifact handle for API/UI consumption.

    The handle encodes the job ID and artifact type without exposing filesystem
    paths.  CLI/operator callers can resolve it to an actual file path by
    combining :func:`job_dir` with the known artifact file name.

    Format: ``"{job_id}:{artifact_type}"``

    Parameters
    ----------
    job_id:
        The owning job ID (already an opaque identifier).
    artifact_type:
        One of the ``ARTIFACT_TYPE_*`` constants (e.g. ``"search_manifest"``).

    Returns
    -------
    str
        An opaque handle safe for API/UI exposure (no filesystem paths).
    """
    return f"{job_id}:{artifact_type}"


# ---------------------------------------------------------------------------
# ObservabilitySummary dataclass + writer (TASK-028)
# ---------------------------------------------------------------------------


@dataclass
class ObservabilitySummary:
    """Rich observability snapshot written to ``observability.json``.

    Contains redacted provider input/response summaries, opaque manifest
    handles (not raw filesystem paths), a redacted verification summary,
    and the next-due estimate.

    API/UI callers receive this artifact (via opaque handles); raw file paths
    and full provider payloads are CLI/operator-only.

    Fields
    ------
    provider_input_summary:
        Redacted summary of what was sent to the provider API (search
        parameters, window, AOI, band/cloud-cover filters).  Empty dict for
        Phase 4 conservative runs that made no live provider calls.
    provider_response_summary:
        Redacted summary of what the provider returned (found_count,
        selected_count, rejection reasons, cloud-cover stats).  Empty dict
        for Phase 4.
    search_manifest_handle:
        Opaque handle for the canonical search manifest file.  ``None`` if no
        search manifest was produced (e.g. Phase 4 or dry-run jobs).  Callers
        resolve this via the job artifact API, not by reading the path directly.
    download_manifest_handle:
        Opaque handle for the download manifest file.  ``None`` if no download
        occurred.
    prepare_manifest_handles:
        Opaque handles for per-scene prepare manifests.  Empty list if no
        prepare pass occurred.
    verification_summary:
        Redacted summary of the validation/verification pass (coverage %, band
        count, mask classes found, pass/fail verdict).  Empty dict if no
        verification was run.
    next_due_at:
        ISO-8601 UTC estimate for the next scheduled run, or ``None`` if the
        cadence is irregular or the source is gated.
    schedule_decision:
        Short string describing why this job was triggered:
        ``"first_run"``, ``"cadence_due"``, ``"manual_override"``,
        ``"dry_run"``, ``"gated"``, ``"lock_blocked"``.
    """

    job_id: str
    source_id: str
    aoi_id: str
    provider: str

    provider_input_summary: dict[str, Any] = field(default_factory=dict)
    provider_response_summary: dict[str, Any] = field(default_factory=dict)

    search_manifest_handle: str | None = None
    download_manifest_handle: str | None = None
    prepare_manifest_handles: list[str] = field(default_factory=list)

    verification_summary: dict[str, Any] = field(default_factory=dict)
    next_due_at: str | None = None
    schedule_decision: str | None = None

    artifact_version: int = JOB_ARTIFACT_VERSION
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a redaction-safe dict suitable for writing to disk or an API."""
        return {
            "artifactVersion": self.artifact_version,
            "redactionVersion": self.redaction_version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "provider": self.provider,
            "providerInputSummary": redact_value(self.provider_input_summary),
            "providerResponseSummary": redact_value(self.provider_response_summary),
            "searchManifestHandle": self.search_manifest_handle,
            "downloadManifestHandle": self.download_manifest_handle,
            "prepareManifestHandles": list(self.prepare_manifest_handles),
            "verificationSummary": redact_value(self.verification_summary),
            "nextDueAt": self.next_due_at,
            "scheduleDecision": self.schedule_decision,
        }


def write_observability(
    job_id: str,
    summary: ObservabilitySummary,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> Path:
    """Write ``observability.json`` for *job_id*.

    All sensitive fields in ``provider_input_summary``,
    ``provider_response_summary``, and ``verification_summary`` are redacted
    via :func:`~akasha_ingest.manifests.redact_value` before serialisation.

    Returns
    -------
    Path
        The path of the written file.
    """
    d = create_job_dir(job_id, base_dir)
    path = d / OBSERVABILITY_FILE
    _write_json_atomic(path, summary.to_dict())
    return path


def read_observability(
    job_id: str,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
) -> dict[str, Any]:
    """Read and return the raw observability dict from ``observability.json``.

    Returns an empty dict if the file does not exist yet (e.g. job still
    running or observability was never written).
    """
    path = job_dir(job_id, base_dir) / OBSERVABILITY_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
