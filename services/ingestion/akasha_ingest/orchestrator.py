"""Scheduler/orchestrator core for the Akasha ingestion scheduler.

Implements TASK-019, TASK-020, and Phase 5 integration (TASK-028/029) from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Responsibilities
----------------
- ``plan_due_sources``  — determine which sources/AOIs are due for a scheduler
  run without making any provider calls (dry-run safe, plan-only output).
- ``run_due_sources``   — execute all due sources sequentially up to an optional
  concurrency budget (Phase 4: sequential; async/parallel deferred to Phase 8).
- ``run_source_job``    — execute one source/AOI job through the full lifecycle:
  gate-checks → approved-runtime preflight → worker-lock acquire → provider
  adapter resolve → record artifacts → write job ledger + observability →
  release lock.

Scheduler ledger (JSON)
-----------------------
A lightweight per-source/AOI JSON ledger under ``<base_dir>/scheduler_ledger.json``
tracks ``lastSucceededAt``, ``lastWindowEnd``, and ``lastJobId`` for each
``source_id::aoi_id`` key.  This is **separate** from:

- The legacy Bhoonidhi product ledger in ``sync.py`` (per-window product states).
- The per-job artifact directories in ``jobs.py`` (full event timelines).
- The Phase 5 SQLite job ledger in ``job_ledger.py`` (per-job observability rows).

The JSON ledger is used only for cadence-based due decisions; per-job artifact
directories remain the source of truth for individual job state.

Phase 5 SQLite job ledger (optional)
--------------------------------------
When a *ledger_db_path* is provided to :func:`run_source_job` /
:func:`run_due_sources`, each job is recorded in the SQLite job ledger (see
``job_ledger.JobLedger``).  This is opt-in so existing callers that do not pass
``ledger_db_path`` continue to work unchanged.  The ledger coexists with the
JSON scheduler ledger and does not replace it.

Additionally, an ``observability.json`` artifact is written to the job directory
when a job reaches a terminal state, capturing a redacted provider input/response
summary, opaque manifest handles, verification info, and the next-due estimate.

Approved-runtime preflight (OPS-008)
--------------------------------------
Sources with ``host_pool == HostPool.STAGING_BHOONIDHI`` must not run real
(non-dry-run) provider calls unless one of the following is true:

1. The ``AKASHA_APPROVED_RUNTIME`` environment variable is set to ``"1"``,
   ``"true"``, or ``"yes"`` (case-insensitive).
2. ``approved_runtime=True`` is passed explicitly by the caller.
3. The job is a dry-run (``dry_run=True``) or a local test (``local_test=True``).

If none of the above is true, ``run_source_job`` records the job as
``SKIPPED_GATED`` with ``failureKind="approved_runtime_required"`` and returns
a result with that status.  No provider calls are made (fail-closed).

Fail-closed guards
------------------
- Unknown source IDs raise ``ValueError`` immediately.
- Unknown provider keys are caught via ``UnknownProviderError`` and recorded as
  ``FAILED``.
- ``DISABLED`` and ``MANUAL_ONLY`` schedule states are never auto-due.
- ``ARCHIVE_ON_DEMAND`` and ``REFERENCE`` cadences are never auto-due.
- ``AoiScope.OUT_OF_AOI`` and ``AoiScope.REFERENCE_ONLY`` are never planned.
- ``CommercialState.COMMERCIAL_BLOCKED`` sources are always ``SKIPPED_GATED``.
- ``bhoonidhi-sync`` command compatibility is preserved as a thin/manual worker
    CLI wrapper, while scheduler-owned ResourceSat jobs run through this
    orchestrator lifecycle.

Live execution
--------------
Approved ResourceSat/Bhoonidhi jobs execute the real
search/download/prepare/composite/ingest pipeline. Non-Bhoonidhi provider
pipelines remain fail-closed with ``pipeline_deferred`` until their adapter-
specific pipelines are implemented.

Stdlib only; no live provider calls at import time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .jobs import (
    ARTIFACT_TYPE_OBSERVABILITY,
    DEFAULT_JOB_BASE_DIR,
    JobStatus,
    ObservabilitySummary,
    append_event,
    create_job,
    finish_job,
    job_dir,
    make_artifact_handle,
    transition_status,
    write_observability,
)
from .scheduler_locks import (
    SchedulerLockError,
    acquire_global_lock,
    acquire_worker_lock,
    release_lock,
)
from .source_registry import (
    SOURCE_REGISTRY,
    AoiScope,
    CadenceClass,
    CommercialState,
    HostPool,
    OwnedBy,
    ProductExposure,
    ScheduleState,
    SourceStateRow,
    ValidationState,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default lock directory for scheduler and worker locks. Worker lock files land
#: directly in this directory using canonical ``<source>.<aoi>.worker.lock``
#: names so automatic and manual scheduler jobs do not dual-acquire.
DEFAULT_LOCK_DIR: str = "/srv/akasha/ingestion/"

#: Filename for the lightweight scheduler ledger under the base_dir.
LEDGER_FILENAME = "scheduler_ledger.json"

#: Redacted schedule snapshot consumed by the BFF admin ingestion schedules API.
SCHEDULE_STATE_FILENAME = "schedule_state.json"

#: Environment variable that approves non-dry-run execution for staging-only sources.
APPROVED_RUNTIME_ENV_VAR = "AKASHA_APPROVED_RUNTIME"
EOS04_SAR_SOURCE_ID = "eos-04-sar-mrs-l2b"

#: Mapping from CadenceClass string value to minimum days between auto-scheduled runs.
#: ``None`` means the source is never automatically due (archive/reference).
_CADENCE_INTERVAL_DAYS: dict[str, float] = {
    CadenceClass.MULTIPLE_PER_DAY: 0.5,
    CadenceClass.DAILY: 1.0,
    CadenceClass.TWO_TO_FIVE_DAYS: 2.0,
    CadenceClass.FIVE_TO_TEN_DAYS: 5.0,
    CadenceClass.TEN_TO_TWENTY_DAYS: 10.0,
    CadenceClass.GT_TWENTY_DAYS: 20.0,
}

#: Schedule states eligible for automatic due-source planning.
_AUTO_DUE_SCHEDULE_STATES: frozenset[ScheduleState] = frozenset(
    {ScheduleState.ROUTINE, ScheduleState.BACKGROUND_ONLY, ScheduleState.DRY_RUN}
)

#: Cadences that are never automatically due (must be triggered by explicit backfill).
_NEVER_AUTO_DUE_CADENCES: frozenset[CadenceClass] = frozenset(
    {CadenceClass.ARCHIVE_ON_DEMAND, CadenceClass.REFERENCE}
)

#: Provider adapter key for Bhoonidhi (ISRO) sources.
_BHOONIDHI_PROVIDER_KEY: str = "bhoonidhi"

#: Ordered list of pipeline stages the Bhoonidhi scheduler path will execute
#: when parity tests pass and the full Phase 7 pipeline is enabled.
#: Matches the stages in ``bhoonidhi-sync``:
#: search → download → prepare → composite → validate → ingest.
_BHOONIDHI_PLANNED_STAGES: list[str] = [
    "search",
    "download",
    "prepare",
    "composite",
    "validate",
    "ingest",
]

#: The stop point that is equivalent to ``bhoonidhi-sync --dry-run``.
#: ``bhoonidhi-sync --dry-run`` stops *before* download/prepare/composite/ingest.
_BHOONIDHI_PARITY_STOP_POINT: str = "before_download"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OrchestratorError(RuntimeError):
    """Base class for orchestrator-layer errors."""


class ApprovedRuntimeRequired(OrchestratorError):
    """Raised by direct callers that want a hard failure on approval absence.

    ``run_source_job`` records the job as ``SKIPPED_GATED`` and returns a
    result rather than raising.  CLI/operator paths that call ``run_source_job``
    and want a visible exit-code failure should raise this after inspecting the
    returned ``SourceJobResult.failure_kind == "approved_runtime_required"``.
    """

    def __init__(self, source_id: str, host_pool: str) -> None:
        super().__init__(
            f"Source '{source_id}' requires host_pool={host_pool!r}. "
            "Non-dry-run execution is not permitted without an approved-runtime signal. "
            f"Set {APPROVED_RUNTIME_ENV_VAR}=1 or pass approved_runtime=True, "
            "or use dry_run=True / local_test=True."
        )
        self.source_id = source_id
        self.host_pool = host_pool


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class DueDecision:
    """Due-source planning decision for one source/AOI pair.

    Produced by ``plan_due_sources``; consumed by ``run_due_sources`` and the
    CLI ``schedule-plan --json`` command (TASK-023).
    """

    source_id: str
    aoi_id: str
    provider: str
    schedule_state: str
    is_due: bool
    skip_reason: str | None
    """Human-readable reason the source was skipped (``None`` when ``is_due=True``)."""

    last_succeeded_at: str | None
    """ISO-8601 UTC of the last successful scheduler run, or ``None`` (first run)."""

    last_window_end: str | None
    """ISO-8601 date of the last successfully ingested window end, or ``None``."""

    next_due_at: str | None
    """ISO-8601 UTC estimate for the next scheduled run based on cadence."""

    window_start: str
    """ISO-8601 date for the start of the proposed search window."""

    window_end: str
    """ISO-8601 date for the end of the proposed search window."""

    manual_override: bool = False
    """``True`` if a manual override forced this source to be due."""

    host_pool: str = ""
    lifecycle_state: str = ""
    aoi_scope: str = ""
    product_exposure: str = ""
    commercial_state: str = ""
    validation_state: str = ""
    cadence_class: str = ""
    cadence_days: float | None = None
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for ``--json`` output."""
        return {
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "provider": self.provider,
            "scheduleState": self.schedule_state,
            "isDue": self.is_due,
            "skipReason": self.skip_reason,
            "lastSucceededAt": self.last_succeeded_at,
            "lastWindowEnd": self.last_window_end,
            "nextDueAt": self.next_due_at,
            "windowStart": self.window_start,
            "windowEnd": self.window_end,
            "manualOverride": self.manual_override,
            "hostPool": self.host_pool,
            "lifecycleState": self.lifecycle_state,
            "aoiScope": self.aoi_scope,
            "productExposure": self.product_exposure,
            "commercialState": self.commercial_state,
            "validationState": self.validation_state,
            "cadenceClass": self.cadence_class,
            "cadenceDays": self.cadence_days,
            "capabilities": list(self.capabilities),
        }


@dataclass
class SourceJobResult:
    """Outcome of running (or planning) one source/AOI job.

    Produced by ``run_source_job`` and collected by ``run_due_sources``.
    """

    job_id: str
    source_id: str
    aoi_id: str
    status: str
    """Final ``JobStatus`` value as a string."""

    dry_run: bool = False
    failure_kind: str | None = None
    failure_message: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for ``--json`` output."""
        return {
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "status": self.status,
            "dryRun": self.dry_run,
            "failureKind": self.failure_kind,
            "failureMessage": self.failure_message,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Lightweight scheduler ledger
# ---------------------------------------------------------------------------


class SchedulerLedger:
    """Lightweight JSON ledger tracking last-successful run per source/AOI.

    The ledger is distinct from the legacy Bhoonidhi product ledger in
    ``sync.py`` and from per-job artifact directories in ``jobs.py``.  It
    answers one question only: "When did this source/AOI last succeed?"
    That answer drives cadence-based due decisions in ``plan_due_sources``.

    File format::

        {
          "ledgerVersion": 1,
          "entries": {
            "<source_id>::<aoi_id>": {
              "lastSucceededAt": "2026-06-20T04:00:00Z",
              "lastWindowEnd": "2026-06-20",
              "lastJobId": "job_20260620T040000Z_abc123def456"
            }
          }
        }
    """

    LEDGER_VERSION = 1

    def __init__(self, base_dir: str | Path) -> None:
        self._path = Path(base_dir) / LEDGER_FILENAME
        self._entries: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._entries = raw.get("entries", {})
            except (json.JSONDecodeError, OSError):
                self._entries = {}
        else:
            self._entries = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ledgerVersion": self.LEDGER_VERSION,
            "entries": self._entries,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, self._path)

    @staticmethod
    def _key(source_id: str, aoi_id: str) -> str:
        return f"{source_id}::{aoi_id}"

    def get_entry(self, source_id: str, aoi_id: str) -> dict[str, Any]:
        """Return the ledger entry for a source/AOI, or an empty dict."""
        return self._entries.get(self._key(source_id, aoi_id), {})

    def record_success(
        self,
        source_id: str,
        aoi_id: str,
        *,
        job_id: str,
        window_end: str,
        succeeded_at: str | None = None,
    ) -> None:
        """Update the ledger entry after a successful run."""
        ts = succeeded_at or _now_iso()
        self._entries[self._key(source_id, aoi_id)] = {
            "lastSucceededAt": ts,
            "lastWindowEnd": window_end,
            "lastJobId": job_id,
        }
        self._save()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _now_iso(now: datetime | None = None) -> str:
    ts = now if now is not None else _now_utc()
    return ts.isoformat().replace("+00:00", "Z")


def _decision_due_reason(decision: DueDecision) -> str | None:
    if not decision.is_due:
        return decision.skip_reason
    if decision.manual_override:
        return "manual_override"
    if decision.last_succeeded_at is None:
        return "first_run"
    return "cadence_elapsed"


def _decision_is_overdue(decision: DueDecision, *, now: datetime) -> bool:
    next_due_at = decision.next_due_at
    if not decision.is_due or not next_due_at:
        return False
    try:
        due_at = datetime.fromisoformat(next_due_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return (now - due_at).total_seconds() > 24 * 3600


def write_schedule_snapshot(
    decisions: list[DueDecision],
    *,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    generated_at: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Write a redacted scheduler schedule snapshot for BFF monitoring.

    ``schedule-plan`` is allowed to produce operational visibility artifacts:
    it does not call providers, download, prepare, upload, or mutate the
    cadence ledger.  The snapshot lets the admin UI show source/AOI cadence and
    due state before the first successful scheduler run has created
    ``scheduler_ledger.json`` entries.
    """
    snapshot_now = now or _now_utc()
    payload = {
        "snapshotVersion": 1,
        "generatedAt": generated_at or _now_iso(snapshot_now),
        "schedules": [
            {
                "sourceId": decision.source_id,
                "provider": decision.provider,
                "adapter": decision.provider,
                "aoiId": decision.aoi_id or None,
                "lifecycleState": decision.lifecycle_state or None,
                "scheduleState": decision.schedule_state or None,
                "capabilities": list(decision.capabilities),
                "commercialState": decision.commercial_state or None,
                "aoiScope": decision.aoi_scope or None,
                "validationState": decision.validation_state or None,
                "scheduleEnabled": decision.schedule_state in _AUTO_DUE_SCHEDULE_STATES,
                "productExposure": decision.product_exposure or None,
                "lastRunAt": decision.last_succeeded_at,
                "lastSuccessAt": decision.last_succeeded_at,
                "lastFailureAt": None,
                "nextDueAt": decision.next_due_at,
                "isDue": decision.is_due,
                "isOverdue": _decision_is_overdue(decision, now=snapshot_now),
                "nextWindowStart": decision.window_start,
                "nextWindowEnd": decision.window_end,
                "cadenceDays": decision.cadence_days,
                "dueReason": _decision_due_reason(decision),
            }
            for decision in decisions
        ],
    }

    path = Path(base_dir) / SCHEDULE_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _cadence_interval_days(cadence: CadenceClass) -> float | None:
    """Return the minimum days between auto-scheduled runs, or None if never auto-due."""
    return _CADENCE_INTERVAL_DAYS.get(str(cadence))


def _compute_window(
    now: datetime,
    *,
    lookback_days: int = 12,
) -> tuple[str, str]:
    """Compute a (window_start, window_end) search window ending at today's date.

    Phase 4 default: ``lookback_days``-wide window ending at ``now.date()``.
    """
    end = now.date()
    start = end - timedelta(days=lookback_days - 1)
    return start.isoformat(), end.isoformat()


def _is_approved_runtime(approved_runtime: bool) -> bool:
    """Return True if the runtime is approved for staging-only providers."""
    if approved_runtime:
        return True
    env_val = os.environ.get(APPROVED_RUNTIME_ENV_VAR, "").strip().lower()
    return env_val in ("1", "true", "yes")


def _gate_reason(row: SourceStateRow, aoi_id: str) -> str | None:
    """Return a gate reason string if the source should not run, else None.

    Called for both planning and execution.  Fail-closed: any unresolvable
    combination produces a reason rather than silently skipping.
    """
    if row.schedule_state in (ScheduleState.DISABLED, ScheduleState.MANUAL_ONLY):
        return f"schedule_state={row.schedule_state.value}"

    if row.cadence in _NEVER_AUTO_DUE_CADENCES:
        return f"cadence={row.cadence.value} is archive/reference only"

    if row.aoi_scope in (AoiScope.OUT_OF_AOI, AoiScope.REFERENCE_ONLY):
        return f"aoi_scope={row.aoi_scope.value} (aoi_id={aoi_id!r})"

    if row.commercial_state == CommercialState.COMMERCIAL_BLOCKED:
        return "commercial_state=commercial_blocked"

    return None


def _run_source_gate_reason(row: SourceStateRow, aoi_id: str, *, trigger: str) -> str | None:
    """Return the execution gate for a direct source job.

    ``schedule_state=manual_only`` is intentionally allowed only for explicit
    manual wrapper runs. All other source gates remain fail-closed.
    """
    gate = _gate_reason(row, aoi_id)
    if gate == "schedule_state=manual_only" and trigger == "manual":
        return None
    return gate


def _is_eos04_manual_validation_search(
    source_id: str,
    row: SourceStateRow,
    *,
    trigger: str,
    is_dry: bool,
) -> bool:
    """Return True for the bounded EOS-04 search-only validation path."""
    return (
        source_id == EOS04_SAR_SOURCE_ID
        and row.schedule_state == ScheduleState.MANUAL_ONLY
        and trigger == "manual"
        and is_dry
        and _is_bhoonidhi_source(row)
    )


def _planning_ownership_gate(row: SourceStateRow, *, dry_run: bool) -> str | None:
    """Return an ownership gate reason for automatic due planning."""
    if row.owned_by == OwnedBy.MANUAL_ONLY:
        return "owned_by=manual_only; explicit manual override required"
    if row.owned_by == OwnedBy.SCHEDULER_DRY_RUN and not dry_run:
        return "owned_by=scheduler_dry_run; live scheduler ownership not enabled"
    return None


# ---------------------------------------------------------------------------
# Phase 7 helpers — Bhoonidhi scheduler path metadata (TASK-045/046/047)
# ---------------------------------------------------------------------------


def _is_bhoonidhi_source(row: SourceStateRow) -> bool:
    """Return ``True`` if this source uses the Bhoonidhi provider adapter.

    Used to gate Phase 7 metadata in dry-run plan events without introducing
    any live provider calls at import or call time.
    """
    return row.provider_adapter == _BHOONIDHI_PROVIDER_KEY


def _classify_pipeline_failure(exc: BaseException) -> str:
    """Map a ResourceSat pipeline exception to a monitoring failure-kind code."""
    msg = str(exc).lower()
    if "coverage" in msg:
        return "low_coverage"
    if "search" in msg or "429" in msg or "403" in msg or "auth" in msg:
        return "provider_auth_or_rate_limit"
    if "download failed" in msg:
        return "download_failed"
    if "stac" in msg or "pgstac" in msg:
        return "stac_registration_failed"
    if "storage upload" in msg or "minio" in msg:
        return "minio_upload_failed"
    if "conversion failed" in msg or "prepare" in msg or "gdal" in msg:
        return "prepare_failed"
    if "composite" in msg:
        return "composite_failed"
    return "ingest_failed"


def _source_thresholds(row: SourceStateRow, *, lookback_days: int = 12) -> dict[str, Any]:
    """Return source-level scheduling thresholds for Phase 7 observability.

    Values are sourced from the source registry row so that they reflect
    whatever the operator has configured; no live calls are made.
    """
    return {
        "minCoveragePercent": row.min_coverage_percent if row.min_coverage_percent else 95.0,
        "maxDownloads": row.max_downloads if row.max_downloads else None,
        "lookbackDays": lookback_days,
    }


def _planned_manifest_handles(
    source_id: str, aoi_id: str, window_end: str
) -> dict[str, str]:
    """Return opaque planned manifest handles for the scheduler dry-run plan.

    These are *planned* handles — the scheduler has not yet executed the
    pipeline.  Downstream tooling can use these to correlate a dry-run plan
    with eventual real artifacts if the run proceeds.

    Handle format: ``sched:<source_id>:<aoi_id>:<window_end>:<stage>``
    """
    prefix = f"sched:{source_id}:{aoi_id}:{window_end}"
    return {
        "searchManifestHandle": f"{prefix}:search",
        "downloadManifestHandle": f"{prefix}:download",
        "compositeManifestHandle": f"{prefix}:composite",
    }


# ---------------------------------------------------------------------------
# Phase 5 helpers — SQLite ledger + observability (TASK-028 / TASK-029)
# ---------------------------------------------------------------------------


def _ledger_from_path(db_path: str | Path | None) -> Any:
    """Return a :class:`~akasha_ingest.job_ledger.JobLedger` or ``None``.

    Uses a lazy import so the ``sqlite3``/``job_ledger`` module is only loaded
    when callers explicitly provide a *db_path*.  Existing callers that pass
    ``None`` (the default) are unaffected.
    """
    if db_path is None:
        return None
    from .job_ledger import JobLedger  # noqa: PLC0415

    return JobLedger(db_path)


def _write_observability_safe(
    job_id: str,
    source_id: str,
    aoi_id: str,
    provider: str,
    final_state: str,
    base_dir: str | Path,
    ledger: Any,
    *,
    scheduled_at: str,
    started_at: str | None,
    finished_at: str | None,
    window_start: str,
    window_end: str,
    sched_decision: str | None,
    next_due_at: str | None,
    failure_kind: str | None,
    provider_input_summary: dict[str, Any],
    provider_response_summary: dict[str, Any],
    verification_summary: dict[str, Any],
    found_count: int | None = None,
    selected_count: int | None = None,
    downloaded_count: int | None = None,
    rejected_count: int | None = None,
    failed_count: int | None = None,
) -> None:
    """Write ``observability.json`` and update the SQLite job ledger row.

    All errors are caught and suppressed: ledger/observability write failures
    must not propagate and affect the main job lifecycle.  The per-job
    ``status.json`` and ``result.json`` remain the authoritative state source.

    Parameters
    ----------
    job_id:
        Owning job ID.
    source_id, aoi_id, provider:
        Job identity fields.
    final_state:
        Final ``JobStatus`` string (e.g. ``"succeeded"``, ``"failed"``).
    base_dir:
        Root directory for job artifacts.
    ledger:
        :class:`~akasha_ingest.job_ledger.JobLedger` instance, or ``None``
        to skip SQLite writes.
    scheduled_at:
        ISO-8601 UTC timestamp of job creation.
    started_at:
        ISO-8601 UTC timestamp when RUNNING state was entered, or ``None``
        if the job was gated/blocked before execution began.
    finished_at:
        ISO-8601 UTC timestamp when the terminal state was entered.
    window_start, window_end:
        Search window ISO-8601 dates.
    sched_decision:
        Why this job was triggered (written to ledger and observability).
    next_due_at:
        ISO-8601 UTC estimate for the next run, or ``None``.
    failure_kind:
        Machine-readable failure category, or ``None``.
    provider_input_summary:
        Redacted summary of what was sent to the provider (Phase 4: search
        window + source state).
    provider_response_summary:
        Redacted provider response summary (Phase 4: empty).
    verification_summary:
        Redacted validation/verification pass summary.
    found_count, selected_count, downloaded_count, rejected_count, failed_count:
        Per-run item counts (all ``None`` in Phase 4 conservative runs).
    """
    obs_handle: str | None = None
    obs_path_str: str | None = None

    # -- Write observability.json --------------------------------------------
    try:
        obs = ObservabilitySummary(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            provider=provider,
            provider_input_summary=provider_input_summary,
            provider_response_summary=provider_response_summary,
            verification_summary=verification_summary,
            next_due_at=next_due_at,
            schedule_decision=sched_decision,
        )
        obs_path = write_observability(job_id, obs, base_dir)
        obs_path_str = str(obs_path)
        obs_handle = make_artifact_handle(job_id, ARTIFACT_TYPE_OBSERVABILITY)
        _ = obs_handle  # available for Phase 5+ API consumers
    except Exception:  # noqa: BLE001
        pass  # observability write failures must not surface to callers

    # -- Update SQLite ledger row --------------------------------------------
    if ledger is not None:
        try:
            ledger.update_job(
                job_id,
                state=final_state,
                started_at=started_at,
                finished_at=finished_at,
                failure_kind=failure_kind,
                schedule_decision=sched_decision,
                next_due_at=next_due_at,
                found_count=found_count,
                selected_count=selected_count,
                downloaded_count=downloaded_count,
                rejected_count=rejected_count,
                failed_count=failed_count,
                artifact_summary_path=obs_path_str,
            )
        except Exception:  # noqa: BLE001
            pass  # ledger write failures must not surface to callers


# ---------------------------------------------------------------------------
# plan_due_sources
# ---------------------------------------------------------------------------


def plan_due_sources(
    *,
    aoi_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    dry_run: bool = False,
    manual_overrides: dict[str, bool] | None = None,
    now: datetime | None = None,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    lookback_days: int = 12,
) -> list[DueDecision]:
    """Determine which sources are due for a scheduler run.

    No provider calls are made.  The result is a list of :class:`DueDecision`
    objects suitable for logging (``--json`` output) or passing to
    :func:`run_due_sources`.

    Due-source logic
    ----------------
    A source/AOI pair is **due** when ALL of the following hold:

    1. Its ``schedule_state`` is in ``{ROUTINE, BACKGROUND_ONLY, DRY_RUN}``.
    2. Its ``cadence`` is not ``ARCHIVE_ON_DEMAND`` or ``REFERENCE``.
    3. Its ``aoi_scope`` is not ``OUT_OF_AOI`` or ``REFERENCE_ONLY``.
    4. Its ``commercial_state`` is not ``COMMERCIAL_BLOCKED``.
    5. It is either a **first run** (no ledger entry) or the elapsed time since
       the last successful run exceeds the cadence-derived minimum interval.
    6. OR a ``manual_override`` entry forces it due regardless of (5).

    Parameters
    ----------
    aoi_ids:
        AOI IDs to consider.  ``None``/empty uses each source's
        ``default_aoi_ids``.
    source_ids:
        Restrict planning to these source IDs only.  ``None`` means all.
    dry_run:
        Informational flag included in decision output; does not affect which
        sources are considered due.
    manual_overrides:
        Map of ``"<source_id>::<aoi_id>"`` → ``True`` to force specific
        source/AOI pairs to be due regardless of cadence.
    now:
        UTC datetime override for deterministic tests.
    base_dir:
        Root directory for job artifacts and the scheduler ledger.
    lookback_days:
        Width (in days) of the proposed search window ending at ``now.date()``.

    Returns
    -------
    list[DueDecision]
        One entry per (source, aoi) pair considered.
    """
    _now = now or _now_utc()
    overrides = manual_overrides or {}
    ledger = SchedulerLedger(base_dir)
    window_start, window_end = _compute_window(_now, lookback_days=lookback_days)

    decisions: list[DueDecision] = []

    for source_id, row in SOURCE_REGISTRY.items():
        if source_ids is not None and source_id not in source_ids:
            continue

        aoi_list: list[str]
        if aoi_ids:
            aoi_list = list(aoi_ids)
        elif row.default_aoi_ids:
            aoi_list = list(row.default_aoi_ids)
        else:
            decisions.append(
                DueDecision(
                    source_id=source_id,
                    aoi_id="",
                    provider=row.provider_adapter,
                    schedule_state=row.schedule_state.value,
                    is_due=False,
                    skip_reason="no aoi configured for source",
                    last_succeeded_at=None,
                    last_window_end=None,
                    next_due_at=None,
                    window_start=window_start,
                    window_end=window_end,
                    host_pool=row.host_pool.value,
                    lifecycle_state=row.lifecycle_state.value,
                    aoi_scope=row.aoi_scope.value,
                    product_exposure=row.product_exposure.value,
                    commercial_state=row.commercial_state.value,
                    validation_state=row.validation_state.value,
                    cadence_class=row.cadence.value,
                    cadence_days=_cadence_interval_days(row.cadence),
                    capabilities=tuple(str(c) for c in row.capabilities),
                )
            )
            continue

        for aoi_id in aoi_list:
            override_key = f"{source_id}::{aoi_id}"
            is_manual = bool(overrides.get(override_key, False))

            # Read the ledger and compute cadence-derived observability fields up
            # front so that gated decisions still surface last-success/next-due
            # for monitoring instead of nulling them out.
            entry = ledger.get_entry(source_id, aoi_id)
            last_succeeded_at: str | None = entry.get("lastSucceededAt")
            last_window_end: str | None = entry.get("lastWindowEnd")
            interval_days = _cadence_interval_days(row.cadence)

            next_due_at: str | None = None
            if last_succeeded_at and interval_days is not None:
                try:
                    last_dt = datetime.fromisoformat(
                        last_succeeded_at.replace("Z", "+00:00")
                    )
                    next_due_at = (
                        (last_dt + timedelta(days=interval_days))
                        .isoformat()
                        .replace("+00:00", "Z")
                    )
                except (ValueError, TypeError):
                    next_due_at = None

            # The state gate (schedule/cadence/aoi/commercial) is more fundamental
            # than the cutover ownership gate, so report it first for observability.
            gate = _gate_reason(row, aoi_id) or _planning_ownership_gate(
                row, dry_run=dry_run
            )
            if gate and not is_manual:
                decisions.append(
                    DueDecision(
                        source_id=source_id,
                        aoi_id=aoi_id,
                        provider=row.provider_adapter,
                        schedule_state=row.schedule_state.value,
                        is_due=False,
                        skip_reason=f"gated: {gate}",
                        last_succeeded_at=last_succeeded_at,
                        last_window_end=last_window_end,
                        next_due_at=next_due_at,
                        window_start=window_start,
                        window_end=window_end,
                        manual_override=False,
                        host_pool=row.host_pool.value,
                        lifecycle_state=row.lifecycle_state.value,
                        aoi_scope=row.aoi_scope.value,
                        product_exposure=row.product_exposure.value,
                        commercial_state=row.commercial_state.value,
                        validation_state=row.validation_state.value,
                        cadence_class=row.cadence.value,
                        cadence_days=interval_days,
                        capabilities=tuple(str(c) for c in row.capabilities),
                    )
                )
                continue

            is_due = False
            skip_reason: str | None = None

            if is_manual:
                is_due = True
            elif interval_days is None:
                is_due = False
                skip_reason = (
                    f"cadence={row.cadence.value} requires explicit backfill trigger"
                )
            elif last_succeeded_at is None:
                # First-run: always due (TASK-020 explicit first-run behavior)
                is_due = True
            else:
                try:
                    last_dt = datetime.fromisoformat(
                        last_succeeded_at.replace("Z", "+00:00")
                    )
                    elapsed = (_now - last_dt).total_seconds()
                    if elapsed >= interval_days * 86400:
                        is_due = True
                    else:
                        remaining_h = (
                            last_dt + timedelta(days=interval_days) - _now
                        ).total_seconds() / 3600
                        skip_reason = (
                            f"not due yet; last succeeded {last_succeeded_at}, "
                            f"next due {next_due_at} "
                            f"({remaining_h:.1f}h remaining)"
                        )
                except (ValueError, TypeError):
                    # Unparseable timestamp — treat as first run (due, fail-open on parse)
                    is_due = True

            decisions.append(
                DueDecision(
                    source_id=source_id,
                    aoi_id=aoi_id,
                    provider=row.provider_adapter,
                    schedule_state=row.schedule_state.value,
                    is_due=is_due,
                    skip_reason=skip_reason,
                    last_succeeded_at=last_succeeded_at,
                    last_window_end=last_window_end,
                    next_due_at=next_due_at,
                    window_start=window_start,
                    window_end=window_end,
                    manual_override=is_manual,
                    host_pool=row.host_pool.value,
                    lifecycle_state=row.lifecycle_state.value,
                    aoi_scope=row.aoi_scope.value,
                    product_exposure=row.product_exposure.value,
                    commercial_state=row.commercial_state.value,
                    validation_state=row.validation_state.value,
                    cadence_class=row.cadence.value,
                    cadence_days=interval_days,
                    capabilities=tuple(str(c) for c in row.capabilities),
                )
            )

    return decisions


# ---------------------------------------------------------------------------
# run_source_job
# ---------------------------------------------------------------------------


def run_source_job(
    source_id: str,
    aoi_id: str,
    *,
    dry_run: bool = False,
    local_test: bool = False,
    approved_runtime: bool = False,
    window_start: str | None = None,
    window_end: str | None = None,
    trigger: str = "scheduler",
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    lock_dir: str | Path = DEFAULT_LOCK_DIR,
    lookback_days: int = 12,
    limit: int | None = None,
    max_downloads: int | None = None,
    min_coverage_percent: float | None = None,
    now: datetime | None = None,
    ledger_db_path: str | Path | None = None,
    schedule_decision: str | None = None,
    next_due_at: str | None = None,
) -> SourceJobResult:
    """Execute a single source/AOI ingestion job through the full lifecycle.

    Execution paths
    ---------------
    **dry-run / local-test**:
        Creates job artifacts (``request.json``, initial ``status.json``,
        ``events.jsonl``), appends a ``dry_run_plan`` event, then immediately
        finishes the job as ``SKIPPED_GATED / dry_run``.  No provider calls.

    **staging-only host without approved runtime**:
        Records ``SKIPPED_GATED / approved_runtime_required`` and returns.
        No provider calls, no exception raised (fail-closed behavior:
        the job is safely gated and the result is inspectable).

    **lock blocked**:
        Records ``BLOCKED_BY_LOCK`` and returns.  Another job for the same
        source/AOI is active; retry on the next scheduler pass.

    **approved ResourceSat/Bhoonidhi non-dry-run**:
        Resolves the provider adapter, acquires the worker lock, then executes
        the ResourceSat search/download/prepare/composite/ingest pipeline.
        Non-Bhoonidhi providers still fail closed with ``pipeline_deferred``.

    Parameters
    ----------
    source_id:
        Source ID from ``SOURCE_REGISTRY``.
    aoi_id:
        AOI identifier (e.g. ``"bangalore-60km"``).
    dry_run:
        Skip all provider calls; record a dry-run plan only.
    local_test:
        Alias for ``dry_run``; intended for test harnesses.
    approved_runtime:
        Explicit approval for non-dry-run staging-only execution.
    window_start, window_end:
        ISO-8601 dates for the search window.  Computed from cadence if ``None``.
    trigger:
        What triggered this job (``"scheduler"``, ``"manual"``, ``"backfill"``).
    base_dir:
        Root directory for job artifacts and the scheduler ledger.
    lock_dir:
        Directory for scheduler and worker lock files.
    lookback_days:
        Lookback window width for auto-computed windows.
    limit:
        Optional provider search result cap for manual/ad hoc runs.
    max_downloads:
        Optional per-run download cap overriding the registry default.
    min_coverage_percent:
        Optional composite validation threshold overriding the registry default.
    now:
        UTC datetime override for deterministic tests.
    ledger_db_path:
        Optional path to the SQLite job ledger database.  When provided, each
        job is recorded in :class:`~akasha_ingest.job_ledger.JobLedger`.
        Pass ``None`` (default) to skip ledger writes (existing callers are
        not affected).
    schedule_decision:
        Short string explaining why this job was triggered (e.g.
        ``"first_run"``, ``"cadence_due"``, ``"manual_override"``).  Written
        to the job ledger and observability artifact.  ``None`` uses the
        *trigger* value as a fallback.
    next_due_at:
        ISO-8601 UTC estimate for the next scheduled run.  Written to the
        observability artifact.  ``None`` if unknown or not applicable.

    Returns
    -------
    SourceJobResult

    Raises
    ------
    ValueError
        If ``source_id`` is not in ``SOURCE_REGISTRY``.
    """
    if source_id not in SOURCE_REGISTRY:
        raise ValueError(
            f"Unknown source_id {source_id!r}. "
            "Check SOURCE_REGISTRY in source_registry.py."
        )

    row = SOURCE_REGISTRY[source_id]
    _now = now or _now_utc()
    is_dry = dry_run or local_test

    if window_start is None or window_end is None:
        effective_lookback = row.composite_window_days or lookback_days
        ws, we = _compute_window(_now, lookback_days=effective_lookback)
        window_start = window_start or ws
        window_end = window_end or we

    job_id, _job_dir = create_job(
        source_id=source_id,
        aoi_id=aoi_id,
        provider=row.provider_adapter,
        window_start=window_start,
        window_end=window_end,
        dry_run=is_dry,
        trigger=trigger,
        base_dir=base_dir,
        now=_now,
    )

    # ── Phase 5: initialise ledger + observability tracking ────────────────
    _scheduled_at = _now_iso(_now)
    _job_started_at: str | None = None
    _sched_decision = schedule_decision or trigger
    _sql_ledger = _ledger_from_path(ledger_db_path)

    # Provider input summary (Phase 4: source state; Phase 7: Bhoonidhi scheduler path).
    _prov_input: dict[str, Any] = {
        "sourceId": source_id,
        "aoiId": aoi_id,
        "windowStart": window_start,
        "windowEnd": window_end,
        "lifecycleState": row.lifecycle_state.value,
        "scheduleState": row.schedule_state.value,
        "capabilities": [str(c) for c in row.capabilities],
        "commercialState": row.commercial_state.value,
        "aoiScope": row.aoi_scope.value,
        "cadenceClass": row.cadence.value,
        "hostPool": row.host_pool.value,
        "productExposure": row.product_exposure.value,
        "validationState": row.validation_state.value,
        "dryRun": is_dry,
        "phase": "phase7_scheduler_path" if _is_bhoonidhi_source(row) else "phase4_conservative",
    }

    if _sql_ledger is not None:
        try:
            _sql_ledger.upsert_job(
                job_id,
                source_id=source_id,
                provider=row.provider_adapter,
                aoi_id=aoi_id,
                state=str(JobStatus.PLANNED),
                scheduled_at=_scheduled_at,
                window_start=window_start,
                window_end=window_end,
                schedule_decision=_sched_decision,
                next_due_at=next_due_at,
            )
        except Exception:  # noqa: BLE001
            pass  # initial ledger write failures must not block job execution

    # ── Gate checks (state-based) — fail closed ────────────────────────────
    gate = _run_source_gate_reason(row, aoi_id, trigger=trigger)
    if gate:
        finish_job(
            job_id,
            JobStatus.SKIPPED_GATED,
            {"gateReason": gate, "sourceId": source_id, "aoiId": aoi_id},
            base_dir,
            failure_kind="gated",
            failure_message=gate,
            now=_now,
        )
        _write_observability_safe(
            job_id, source_id, aoi_id, row.provider_adapter,
            str(JobStatus.SKIPPED_GATED), base_dir, _sql_ledger,
            scheduled_at=_scheduled_at, started_at=None,
            finished_at=_now_iso(_now),
            window_start=window_start, window_end=window_end,
            sched_decision="gated", next_due_at=next_due_at,
            failure_kind="gated",
            provider_input_summary=_prov_input,
            provider_response_summary={},
            verification_summary={"gateReason": gate},
        )
        return SourceJobResult(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            status=str(JobStatus.SKIPPED_GATED),
            dry_run=is_dry,
            failure_kind="gated",
            failure_message=gate,
        )

    # ── EOS-04 manual validation dry-run: live search, no download/upload ──
    if _is_eos04_manual_validation_search(source_id, row, trigger=trigger, is_dry=is_dry):
        from akasha_ingest import bhoonidhi as _bh  # noqa: PLC0415
        from akasha_ingest import config as _cfg  # noqa: PLC0415
        from akasha_ingest import sync as _sync  # noqa: PLC0415

        client = None
        try:
            _aoi = _bh.load_aoi(None, aoi_id=aoi_id, aoi_dir=_cfg.AOI_CONFIG_DIR)
            collection = _bh.source_collection(source_id)
            datetime_range = _sync.datetime_range_for_window(window_start, window_end)
            client = _bh.BhoonidhiClient()
            items = client.search(
                collection=collection,
                datetime_range=datetime_range,
                intersects=_aoi["geometry"],
                limit=limit or 100,
            )
            manifest = _bh.build_search_manifest(
                source_id=source_id,
                collection=collection,
                aoi=_aoi,
                datetime_range=datetime_range,
                items=items,
            )
            manifest_path = job_dir(job_id, base_dir) / "coverage_manifest.json"
            _bh.write_manifest(manifest, manifest_path)
            found_count = len(items)
            selected_count = len(manifest.get("selection", {}).get("selected_product_ids", []))
            summary = {
                "sourceId": source_id,
                "aoiId": aoi_id,
                "provider": row.provider_adapter,
                "collection": collection,
                "windowStart": window_start,
                "windowEnd": window_end,
                "datetimeRange": datetime_range,
                "dryRun": True,
                "manualValidation": True,
                "stopPoint": "after_search_before_download",
                "foundCount": found_count,
                "selectedCount": selected_count,
                "downloadedCount": 0,
                "coverageManifest": str(manifest_path),
            }
            append_event(
                job_id,
                "manual_validation_search",
                {**summary, "coverageManifestHandle": make_artifact_handle(job_id, "coverage")},
                base_dir,
                now=_now,
            )
            finish_job(job_id, JobStatus.SUCCEEDED, summary, base_dir, now=_now)
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.SUCCEEDED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=None,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision="manual_validation_search",
                next_due_at=next_due_at,
                failure_kind=None,
                provider_input_summary={**_prov_input, "collection": collection},
                provider_response_summary={
                    "foundCount": found_count,
                    "selectedCount": selected_count,
                    "downloadedCount": 0,
                },
                verification_summary={"verdict": "search_only", "manifest": str(manifest_path)},
                found_count=found_count,
                selected_count=selected_count,
                downloaded_count=0,
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.SUCCEEDED),
                dry_run=True,
                summary=summary,
            )
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            failure_message = str(exc) or exc.__class__.__name__
            finish_job(
                job_id,
                JobStatus.FAILED,
                {"sourceId": source_id, "aoiId": aoi_id, "failureKind": "provider_search_failed"},
                base_dir,
                failure_kind="provider_search_failed",
                failure_message=failure_message,
                now=_now,
            )
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.FAILED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=None,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision="manual_validation_search",
                next_due_at=next_due_at,
                failure_kind="provider_search_failed",
                provider_input_summary=_prov_input,
                provider_response_summary={},
                verification_summary={"verdict": "failed", "reason": failure_message},
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.FAILED),
                dry_run=True,
                failure_kind="provider_search_failed",
                failure_message=failure_message,
            )
        finally:
            if client is not None:
                try:
                    client.logout(ignore_errors=True)
                except Exception:  # noqa: BLE001
                    pass

    # ── Dry-run / local-test path ──────────────────────────────────────────
    if is_dry:
        # Phase 7: build the dry-run plan payload, extending base fields with
        # Bhoonidhi-specific metadata (planned stages, parity stop point,
        # source thresholds, and manifest handles) when applicable.
        _dry_run_plan_payload: dict[str, Any] = {
            "sourceId": source_id,
            "aoiId": aoi_id,
            "windowStart": window_start,
            "windowEnd": window_end,
            "scheduleState": row.schedule_state.value,
            "hostPool": row.host_pool.value,
            "productExposure": row.product_exposure.value,
            "validationState": row.validation_state.value,
            "capabilities": [str(c) for c in row.capabilities],
        }
        if _is_bhoonidhi_source(row):
            _dry_run_plan_payload.update(
                {
                    "plannedStages": list(_BHOONIDHI_PLANNED_STAGES),
                    "parityStopPoint": _BHOONIDHI_PARITY_STOP_POINT,
                    "parityNote": (
                        "bhoonidhi-sync --dry-run stops before download/prepare/"
                        "composite/ingest; scheduler dry-run records the full "
                        "pipeline plan without live calls (Phase 7 parity mode)."
                    ),
                    "sourceThresholds": _source_thresholds(row, lookback_days=lookback_days),
                    "manifestHandles": _planned_manifest_handles(
                        source_id, aoi_id, window_end
                    ),
                    "phase": "phase7_scheduler_path",
                }
            )
        append_event(
            job_id,
            "dry_run_plan",
            _dry_run_plan_payload,
            base_dir,
            now=_now,
        )
        finish_job(
            job_id,
            JobStatus.SKIPPED_GATED,
            {"dryRun": True, "sourceId": source_id, "aoiId": aoi_id},
            base_dir,
            failure_kind="dry_run",
            failure_message="dry-run: no provider calls made",
            now=_now,
        )
        _write_observability_safe(
            job_id, source_id, aoi_id, row.provider_adapter,
            str(JobStatus.SKIPPED_GATED), base_dir, _sql_ledger,
            scheduled_at=_scheduled_at, started_at=None,
            finished_at=_now_iso(_now),
            window_start=window_start, window_end=window_end,
            sched_decision="dry_run", next_due_at=next_due_at,
            failure_kind="dry_run",
            provider_input_summary=_prov_input,
            provider_response_summary={},
            verification_summary={},
        )
        return SourceJobResult(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            status=str(JobStatus.SKIPPED_GATED),
            dry_run=True,
            failure_kind="dry_run",
            failure_message="dry-run: no provider calls made",
            summary={"dryRun": True},
        )

    # ── Approved-runtime preflight for staging-only providers (OPS-008) ────
    if row.host_pool == HostPool.STAGING_BHOONIDHI:
        if not _is_approved_runtime(approved_runtime):
            err_msg = (
                f"Source '{source_id}' requires host_pool={row.host_pool.value!r}. "
                f"Set {APPROVED_RUNTIME_ENV_VAR}=1 or pass approved_runtime=True. "
                "Use dry_run=True to plan without executing."
            )
            finish_job(
                job_id,
                JobStatus.SKIPPED_GATED,
                {"approvedRuntimeRequired": True, "sourceId": source_id},
                base_dir,
                failure_kind="approved_runtime_required",
                failure_message=err_msg,
                now=_now,
            )
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.SKIPPED_GATED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=None,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision="approved_runtime_required",
                next_due_at=next_due_at,
                failure_kind="approved_runtime_required",
                provider_input_summary=_prov_input,
                provider_response_summary={},
                verification_summary={},
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.SKIPPED_GATED),
                dry_run=False,
                failure_kind="approved_runtime_required",
                failure_message=err_msg,
            )

    # ── Acquire per-source/AOI worker lock ─────────────────────────────────
    worker_lock = None
    try:
        worker_lock = acquire_worker_lock(lock_dir, source_id, aoi_id)
    except SchedulerLockError as exc:
        finish_job(
            job_id,
            JobStatus.BLOCKED_BY_LOCK,
            {"sourceId": source_id, "aoiId": aoi_id},
            base_dir,
            failure_kind="lock_blocked",
            failure_message=str(exc),
            now=_now,
        )
        _write_observability_safe(
            job_id, source_id, aoi_id, row.provider_adapter,
            str(JobStatus.BLOCKED_BY_LOCK), base_dir, _sql_ledger,
            scheduled_at=_scheduled_at, started_at=None,
            finished_at=_now_iso(_now),
            window_start=window_start, window_end=window_end,
            sched_decision="lock_blocked", next_due_at=next_due_at,
            failure_kind="lock_blocked",
            provider_input_summary=_prov_input,
            provider_response_summary={},
            verification_summary={},
        )
        return SourceJobResult(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            status=str(JobStatus.BLOCKED_BY_LOCK),
            dry_run=False,
            failure_kind="lock_blocked",
            failure_message=str(exc),
        )

    try:
        transition_status(job_id, JobStatus.RUNNING, base_dir, now=_now)
        _job_started_at = _now_iso(_now)

        # ── Phase 4 conservative execution ─────────────────────────────────
        # Resolve the provider adapter (fail closed if unknown).
        # Full search/download/prepare/composite deferred to Phase 7 (TASK-045).
        from .providers.registry import (  # noqa: PLC0415 – intentional lazy import
            UnknownProviderError,
            get_provider_adapter,
        )

        try:
            _adapter = get_provider_adapter(row.provider_adapter)
        except UnknownProviderError as exc:
            finish_job(
                job_id,
                JobStatus.FAILED,
                {"sourceId": source_id, "providerKey": row.provider_adapter},
                base_dir,
                failure_kind="unknown_provider",
                failure_message=str(exc),
                now=_now,
            )
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.FAILED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=_job_started_at,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision=_sched_decision, next_due_at=next_due_at,
                failure_kind="unknown_provider",
                provider_input_summary=_prov_input,
                provider_response_summary={},
                verification_summary={},
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.FAILED),
                failure_kind="unknown_provider",
                failure_message=str(exc),
            )

        # ── Validation-failed gate for product-active paths ─────────────────
        # BACKGROUND_ONLY sources such as AWiFS are allowed to attempt search /
        # prepare again so they can recover from a previous low-coverage run.
        if (
            row.validation_state == ValidationState.VALIDATION_FAILED
            and row.product_exposure != ProductExposure.BACKGROUND_ONLY
        ):
            val_msg = (
                f"Source '{source_id}' has validation_state=VALIDATION_FAILED "
                f"(product_exposure={row.product_exposure.value}). "
                "Job records as VALIDATION_FAILED; scheduler ledger not updated."
            )
            finish_job(
                job_id,
                JobStatus.VALIDATION_FAILED,
                {
                    "sourceId": source_id,
                    "aoiId": aoi_id,
                    "validationState": row.validation_state.value,
                    "productExposure": row.product_exposure.value,
                },
                base_dir,
                failure_kind="low_coverage",
                failure_message=val_msg,
                now=_now,
            )
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.VALIDATION_FAILED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=_job_started_at,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision=_sched_decision, next_due_at=next_due_at,
                failure_kind="low_coverage",
                provider_input_summary=_prov_input,
                provider_response_summary={},
                verification_summary={
                    "validationState": row.validation_state.value,
                    "productExposure": row.product_exposure.value,
                    "verdict": "validation_failed",
                    "reason": "low_coverage",
                    # Phase 7 (TASK-046): readinessReasons surface why this source
                    # is blocked from product-active promotion.
                    "readinessReasons": list(row.readiness_reasons),
                },
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.VALIDATION_FAILED),
                dry_run=False,
                failure_kind="low_coverage",
                failure_message=val_msg,
            )

        # ── Live ResourceSat/Bhoonidhi ingestion pipeline ──────────────────
        if _is_bhoonidhi_source(row):
            from akasha_ingest import bhoonidhi as _bh
            from akasha_ingest import config as _cfg
            from akasha_ingest import sync as _sync
            from akasha_ingest.resourcesat_pipeline import (
                IngestParams,
                run_resourcesat_ingest,
            )

            _logs: list[str] = []
            try:
                _aoi = _bh.load_aoi(None, aoi_id=aoi_id, aoi_dir=_cfg.AOI_CONFIG_DIR)
                _params = IngestParams(
                    source_id=source_id,
                    aoi=_aoi,
                    aoi_id=aoi_id,
                    window_start=window_start,
                    window_end=window_end,
                    datetime_range=_sync.datetime_range_for_window(window_start, window_end),
                    limit=limit or 100,
                    max_downloads=(
                        max_downloads if max_downloads is not None else row.max_downloads or None
                    ),
                    min_coverage_percent=(
                        min_coverage_percent
                        if min_coverage_percent is not None
                        else row.min_coverage_percent or 95.0
                    ),
                )
                _ingest = run_resourcesat_ingest(_params, log=_logs.append)
            except (Exception, SystemExit) as exc:  # noqa: BLE001
                _fk = _classify_pipeline_failure(exc)
                _fmsg = str(exc) or exc.__class__.__name__
                finish_job(
                    job_id,
                    JobStatus.FAILED,
                    {
                        "sourceId": source_id,
                        "aoiId": aoi_id,
                        "provider": row.provider_adapter,
                        "windowStart": window_start,
                        "windowEnd": window_end,
                        "failureKind": _fk,
                    },
                    base_dir,
                    failure_kind=_fk,
                    failure_message=_fmsg,
                    now=_now,
                )
                _write_observability_safe(
                    job_id, source_id, aoi_id, row.provider_adapter,
                    str(JobStatus.FAILED), base_dir, _sql_ledger,
                    scheduled_at=_scheduled_at, started_at=_job_started_at,
                    finished_at=_now_iso(_now),
                    window_start=window_start, window_end=window_end,
                    sched_decision=_sched_decision, next_due_at=next_due_at,
                    failure_kind=_fk,
                    provider_input_summary=_prov_input,
                    provider_response_summary={},
                    verification_summary={"verdict": "failed", "failureKind": _fk},
                )
                return SourceJobResult(
                    job_id=job_id,
                    source_id=source_id,
                    aoi_id=aoi_id,
                    status=str(JobStatus.FAILED),
                    dry_run=False,
                    failure_kind=_fk,
                    failure_message=_fmsg,
                )

            _summary = {
                "sourceId": source_id,
                "aoiId": aoi_id,
                "provider": row.provider_adapter,
                "windowStart": window_start,
                "windowEnd": window_end,
                "phase": "phase7_scheduler_path",
                **_ingest.to_dict(),
            }
            finish_job(job_id, JobStatus.SUCCEEDED, _summary, base_dir, now=_now)
            try:
                SchedulerLedger(base_dir).record_success(
                    source_id,
                    aoi_id,
                    job_id=job_id,
                    window_end=window_end,
                    succeeded_at=_now_iso(_now),
                )
            except Exception:  # noqa: BLE001
                pass
            _write_observability_safe(
                job_id, source_id, aoi_id, row.provider_adapter,
                str(JobStatus.SUCCEEDED), base_dir, _sql_ledger,
                scheduled_at=_scheduled_at, started_at=_job_started_at,
                finished_at=_now_iso(_now),
                window_start=window_start, window_end=window_end,
                sched_decision=_sched_decision, next_due_at=next_due_at,
                failure_kind=None,
                provider_input_summary=_prov_input,
                provider_response_summary={
                    "foundCount": _ingest.found_count,
                    "selectedCount": _ingest.selected_count,
                    "downloadedCount": _ingest.downloaded_count,
                    "deferredCount": _ingest.deferred_count,
                },
                verification_summary=_ingest.to_dict(),
                found_count=_ingest.found_count,
                selected_count=_ingest.selected_count,
                downloaded_count=_ingest.downloaded_count,
            )
            return SourceJobResult(
                job_id=job_id,
                source_id=source_id,
                aoi_id=aoi_id,
                status=str(JobStatus.SUCCEEDED),
                dry_run=False,
                summary=_summary,
            )

        _phase_key = "phase7_scheduler_path" if _is_bhoonidhi_source(row) else "phase4_conservative"
        deferred_message = (
            "Live scheduler execution is fail-closed because the provider "
            "search/download/prepare/composite/ingest pipeline is not wired into "
            "the orchestrator yet. No scheduler success ledger entry was recorded."
        )
        summary: dict[str, Any] = {
            "sourceId": source_id,
            "aoiId": aoi_id,
            "provider": row.provider_adapter,
            "adapterResolved": True,
            "phase": _phase_key,
            "windowStart": window_start,
            "windowEnd": window_end,
            "scheduleState": row.schedule_state.value,
            "productExposure": row.product_exposure.value,
            "validationState": row.validation_state.value,
            "note": deferred_message,
        }

        result = finish_job(
            job_id,
            JobStatus.FAILED,
            summary,
            base_dir,
            failure_kind="pipeline_deferred",
            failure_message=deferred_message,
            now=_now,
        )

        _write_observability_safe(
            job_id, source_id, aoi_id, row.provider_adapter,
            str(JobStatus.FAILED), base_dir, _sql_ledger,
            scheduled_at=_scheduled_at, started_at=_job_started_at,
            finished_at=_now_iso(_now),
            window_start=window_start, window_end=window_end,
            sched_decision=_sched_decision, next_due_at=next_due_at,
            failure_kind="pipeline_deferred",
            provider_input_summary=_prov_input,
            provider_response_summary={},
            verification_summary={
                "validationState": row.validation_state.value,
                "productExposure": row.product_exposure.value,
                "verdict": "pipeline_deferred",
                "phase": _phase_key,
            },
        )

        return SourceJobResult(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            status=str(result.status),
            dry_run=False,
            failure_kind="pipeline_deferred",
            failure_message=deferred_message,
            summary=summary,
        )

    except Exception as exc:  # noqa: BLE001
        try:
            finish_job(
                job_id,
                JobStatus.FAILED,
                {"sourceId": source_id, "aoiId": aoi_id},
                base_dir,
                failure_kind="unexpected_error",
                failure_message=str(exc),
                now=_now,
            )
        except ValueError:
            # Job already reached a terminal state (e.g. finish_job(SUCCEEDED)
            # succeeded but a subsequent write raised); do not double-transition.
            pass
        _write_observability_safe(
            job_id, source_id, aoi_id, row.provider_adapter,
            str(JobStatus.FAILED), base_dir, _sql_ledger,
            scheduled_at=_scheduled_at, started_at=_job_started_at,
            finished_at=_now_iso(_now),
            window_start=window_start, window_end=window_end,
            sched_decision=_sched_decision, next_due_at=next_due_at,
            failure_kind="unexpected_error",
            provider_input_summary=_prov_input,
            provider_response_summary={},
            verification_summary={},
        )
        return SourceJobResult(
            job_id=job_id,
            source_id=source_id,
            aoi_id=aoi_id,
            status=str(JobStatus.FAILED),
            failure_kind="unexpected_error",
            failure_message=str(exc),
        )

    finally:
        if worker_lock is not None:
            release_lock(worker_lock)


# ---------------------------------------------------------------------------
# run_due_sources
# ---------------------------------------------------------------------------


def run_due_sources(
    decisions: list[DueDecision],
    *,
    dry_run: bool = False,
    local_test: bool = False,
    approved_runtime: bool = False,
    max_sources: int = 5,
    trigger: str = "scheduler",
    use_global_lock: bool = False,
    base_dir: str | Path = DEFAULT_JOB_BASE_DIR,
    lock_dir: str | Path = DEFAULT_LOCK_DIR,
    lookback_days: int = 12,
    now: datetime | None = None,
    ledger_db_path: str | Path | None = None,
) -> list[SourceJobResult]:
    """Execute all due sources from a :func:`plan_due_sources` result.

    Phase 4 implementation is **sequential** (one source/AOI at a time) up to
    ``max_sources``.  Async/parallel execution is deferred to Phase 8.

    Sources with ``is_due=False`` are silently skipped.

    Parameters
    ----------
    decisions:
        Output of :func:`plan_due_sources`.
    dry_run:
        Run all jobs in dry-run mode (no provider calls).
    local_test:
        Alias for ``dry_run`` for test harnesses.
    approved_runtime:
        Explicit approval for staging-only providers.
    max_sources:
        Maximum number of due sources to run in one scheduler pass.
    trigger:
        What triggered this run (``"scheduler"``, ``"manual"``).
    use_global_lock:
        If ``True``, acquire the global scheduler singleton lock under
        ``lock_dir`` before executing.  Prevents two simultaneous scheduler
        passes from running due sources concurrently (OPS-007).
    base_dir:
        Root directory for job artifacts and the scheduler ledger.
    lock_dir:
        Lock file directory.
    lookback_days:
        Passed through to :func:`run_source_job` for window computation.
    now:
        UTC datetime override for deterministic tests.
    ledger_db_path:
        Optional path to the SQLite job ledger database.  Passed through to
        :func:`run_source_job` for each due source.  ``None`` skips ledger writes.

    Returns
    -------
    list[SourceJobResult]
        Results for every due source that was attempted (up to ``max_sources``).
    """
    due = [d for d in decisions if d.is_due]

    global_lock = None
    if use_global_lock:
        global_lock = acquire_global_lock(lock_dir)

    try:
        results: list[SourceJobResult] = []
        for decision in due[:max_sources]:
            # Derive schedule_decision from the DueDecision fields.
            sched_decision: str
            if decision.manual_override:
                sched_decision = "manual_override"
            elif decision.last_succeeded_at is None:
                sched_decision = "first_run"
            else:
                sched_decision = "cadence_due"

            result = run_source_job(
                decision.source_id,
                decision.aoi_id,
                dry_run=dry_run,
                local_test=local_test,
                approved_runtime=approved_runtime,
                window_start=decision.window_start,
                window_end=decision.window_end,
                trigger=trigger,
                base_dir=base_dir,
                lock_dir=lock_dir,
                lookback_days=lookback_days,
                now=now,
                ledger_db_path=ledger_db_path,
                schedule_decision=sched_decision,
                next_due_at=decision.next_due_at,
            )
            results.append(result)
        return results

    finally:
        if global_lock is not None:
            release_lock(global_lock)
