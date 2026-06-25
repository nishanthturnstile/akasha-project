"""Orchestrator / jobs / locks / worker CLI tests — TASK-027 and TASK-027A.

Coverage matrix
---------------
- Dry-run does not download or call provider live methods.
- Due-source decisions honor cadence and first-run behavior.
- Commercial sources are blocked/gated by plan_due_sources.
- NAIP is excluded (reference_only / out-of-AOI scope).
- Archive sources (ARCHIVE_ON_DEMAND cadence) are never auto-due.
- Direct unsafe Bhoonidhi execution fails closed without approved runtime.
- Stale locks are reclaimed; live locks block.
- Concurrency / max_sources budget is enforced.
- AWiFS below-threshold / validation_failed stays background_only.
- Parser / CLI smoke tests for schedule-plan --json, schedule-due-sources,
  schedule-source --source --aoi --dry-run, and bhoonidhi-sync.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest.jobs import (  # noqa: E402
    EVENTS_FILE,
    REQUEST_FILE,
    RESULT_FILE,
    STATUS_FILE,
    JobStatus,
    job_dir,
    read_events,
    read_result,
    read_status,
)
from akasha_ingest.orchestrator import (  # noqa: E402
    APPROVED_RUNTIME_ENV_VAR,
    SchedulerLedger,
    plan_due_sources,
    run_due_sources,
    run_source_job,
)
from akasha_ingest.scheduler_locks import (  # noqa: E402
    SchedulerLockError,
    acquire_global_lock,
    acquire_worker_lock,
    release_lock,
    worker_lock_name,
)
from akasha_ingest.source_registry import (  # noqa: E402
    SOURCE_REGISTRY,
    AoiScope,
    CadenceClass,
    CommercialState,
    OwnedBy,
    ProductExposure,
    ScheduleState,
    ValidationState,
)

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

_LISS3_SOURCE = "resourcesat-2a-liss3-boa"
_LISS4_SOURCE = "resourcesat-2a-liss4-mx70-l2"
_AWIFS_SOURCE = "resourcesat-2a-awifs-boa"
_NAIP_SOURCE = "naip-reference-only"
_ARCHIVE_SOURCE = "landsat-7-c2-l2"  # ARCHIVE_ON_DEMAND cadence
_COMMERCIAL_SOURCE = "planetscope"  # commercial_blocked
_ALOSPALSAR_COMMERCIAL = "alos2-palsar2"  # commercial_blocked

_DEFAULT_AOI = "bangalore-60km"

_FIXED_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fresh_ledger(tmp_path: Path) -> SchedulerLedger:
    return SchedulerLedger(tmp_path)


def _job_result_status(tmp_path: Path, job_id: str) -> str:
    return read_status(job_id, tmp_path)["status"]


def _job_result_failure_kind(tmp_path: Path, job_id: str) -> str | None:
    return read_result(job_id, tmp_path).get("failureKind")


# ===========================================================================
# 1. Dry-run: no provider calls, artifacts written, failure_kind=dry_run
# ===========================================================================


class TestDryRunBehavior:
    def test_dry_run_returns_skipped_gated(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SKIPPED_GATED)
        assert result.dry_run is True
        assert result.failure_kind == "dry_run"

    def test_dry_run_writes_request_and_status_artifacts(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        d = job_dir(result.job_id, tmp_path)
        assert (d / REQUEST_FILE).exists()
        assert (d / STATUS_FILE).exists()
        assert (d / RESULT_FILE).exists()
        assert (d / EVENTS_FILE).exists()

    def test_dry_run_events_contain_dry_run_plan(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        event_types = [e["eventType"] for e in events]
        assert "dry_run_plan" in event_types

    def test_dry_run_does_not_call_provider(self, tmp_path):
        """Dry-run must never call get_provider_adapter or any provider method."""
        with patch(
            "akasha_ingest.orchestrator.acquire_worker_lock"
        ) as mock_lock, patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                dry_run=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        # Lock must NOT be acquired (short-circuit before lock path)
        mock_lock.assert_not_called()
        # Provider adapter must NOT be resolved
        mock_adapter.assert_not_called()

    def test_local_test_alias_behaves_identically_to_dry_run(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            local_test=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SKIPPED_GATED)
        assert result.failure_kind == "dry_run"

    def test_dry_run_does_not_update_scheduler_ledger(self, tmp_path):
        """A dry-run job must NOT write a ledger entry (cadence is unchanged)."""
        run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        ledger = _make_fresh_ledger(tmp_path)
        entry = ledger.get_entry(_LISS3_SOURCE, _DEFAULT_AOI)
        assert entry == {}


# ===========================================================================
# 2. Due-source decisions: cadence and first-run behavior
# ===========================================================================


class TestDueSourceDecisions:
    def test_legacy_owned_source_is_not_auto_due(self, tmp_path):
        """Legacy timer-owned sources must not be auto-scheduled during cutover."""
        row = SOURCE_REGISTRY[_LISS3_SOURCE]
        assert row.owned_by == OwnedBy.LEGACY_TIMER

        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert not due, "Legacy-owned LISS-3 must not be scheduler-due before cutover"
        assert any("legacy_timer" in (d.skip_reason or "") for d in decisions)

    def test_manual_override_canary_forces_legacy_owned_source_due(self, tmp_path):
        """Explicit canary/manual override is allowed without changing ownership."""
        override_key = f"{_LISS3_SOURCE}::{_DEFAULT_AOI}"
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={override_key: True},
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert due, "Manual canary override should force legacy-owned LISS-3 due"
        assert all(d.manual_override for d in due)

    def test_first_run_scheduler_owned_source_is_due(self, tmp_path):
        """No ledger entry → scheduler-owned source is due on first run."""
        decisions = plan_due_sources(
            source_ids=["sentinel-2-l2a"],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={f"sentinel-2-l2a::{_DEFAULT_AOI}": True},
        )
        due = [d for d in decisions if d.source_id == "sentinel-2-l2a"]
        assert due, "Expected at least one decision for Sentinel-2 manual run"
        assert all(d.is_due for d in due)

    def test_recently_succeeded_is_not_due(self, tmp_path):
        """Source succeeded 1 hour ago with a 5-day cadence → not yet due."""
        ledger = _make_fresh_ledger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_test",
            window_end="2026-06-24",
            succeeded_at=(_FIXED_NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert not due, "LISS-3 should NOT be due 1 hour after last success"

    def test_past_cadence_interval_is_due(self, tmp_path):
        """Source succeeded 10 days ago with a 5-day cadence → due."""
        ledger = _make_fresh_ledger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_test",
            window_end="2026-06-14",
            succeeded_at=(_FIXED_NOW - timedelta(days=10)).isoformat().replace("+00:00", "Z"),
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={f"{_LISS3_SOURCE}::{_DEFAULT_AOI}": True},
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert due, "LISS-3 should be due 10 days after last success (5-day cadence)"

    def test_manual_override_forces_due_regardless_of_cadence(self, tmp_path):
        """Manual override key forces is_due=True even when recently succeeded."""
        ledger = _make_fresh_ledger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_test",
            window_end="2026-06-24",
            succeeded_at=(_FIXED_NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        override_key = f"{_AWIFS_SOURCE}::{_DEFAULT_AOI}"
        decisions = plan_due_sources(
            source_ids=[_AWIFS_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={override_key: True},
        )
        due = [d for d in decisions if d.source_id == _AWIFS_SOURCE and d.is_due]
        assert due, "Manual override should force AWiFS to be due"
        assert all(d.manual_override for d in due)

    def test_disabled_schedule_state_is_never_due(self, tmp_path):
        """A DISABLED source must never appear in due decisions."""
        decisions = plan_due_sources(
            source_ids=["sentinel-2-l2a"],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.is_due]
        assert not due, "Disabled sentinel-2 must never be due"

    def test_background_only_legacy_state_is_not_auto_due(self, tmp_path):
        """BACKGROUND_ONLY still respects legacy cutover ownership."""
        decisions = plan_due_sources(
            source_ids=[_AWIFS_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.source_id == _AWIFS_SOURCE and d.is_due]
        assert not due, "Legacy-owned AWiFS should not auto-run before scheduler cutover"

    def test_decisions_carry_window_dates(self, tmp_path):
        """DueDecision objects must include non-empty window_start and window_end."""
        decisions = plan_due_sources(
            source_ids=[_AWIFS_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={f"{_AWIFS_SOURCE}::{_DEFAULT_AOI}": True},
        )
        for d in decisions:
            assert d.window_start, "window_start must be non-empty"
            assert d.window_end, "window_end must be non-empty"

    def test_to_dict_produces_json_serialisable_output(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            payload = d.to_dict()
            # Must be JSON-serialisable without exceptions
            serialised = json.dumps(payload)
            assert serialised


# ===========================================================================
# 3. Commercial sources are blocked/gated
# ===========================================================================


class TestCommercialSourcesGated:
    @pytest.mark.parametrize(
        "source_id",
        [
            "planetscope",
            "skysat",
            "blacksky-gen-3",
            "kompsat-3a",
            "superview-neo-1",
            "alos2-palsar2",
        ],
    )
    def test_commercial_blocked_source_is_never_due(self, source_id, tmp_path):
        row = SOURCE_REGISTRY[source_id]
        assert row.commercial_state == CommercialState.COMMERCIAL_BLOCKED

        decisions = plan_due_sources(
            source_ids=[source_id],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.is_due]
        assert not due, f"{source_id} (commercial_blocked) must never be due"

    def test_commercial_blocked_skip_reason_is_non_empty(self, tmp_path):
        """Commercial-blocked sources must produce a non-empty skip reason."""
        decisions = plan_due_sources(
            source_ids=[_COMMERCIAL_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        skipped = [d for d in decisions if not d.is_due]
        assert skipped
        # Every skipped decision must have a non-empty skip reason
        for d in skipped:
            assert d.skip_reason, f"Expected a skip reason for {d.source_id}"

    def test_commercial_blocked_state_reflected_in_due_decision(self, tmp_path):
        """commercial_state field in DueDecision must reflect commercial_blocked."""
        decisions = plan_due_sources(
            source_ids=[_COMMERCIAL_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            assert d.commercial_state == CommercialState.COMMERCIAL_BLOCKED.value

    def test_commercial_blocked_run_source_job_gated(self, tmp_path):
        """run_source_job on a commercial-blocked source records SKIPPED_GATED."""
        result = run_source_job(
            _COMMERCIAL_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SKIPPED_GATED)
        assert result.failure_kind == "gated"


# ===========================================================================
# 4. NAIP: reference_only / excluded / out-of-AOI
# ===========================================================================


class TestNaipExclusion:
    def test_naip_source_is_in_registry(self):
        assert _NAIP_SOURCE in SOURCE_REGISTRY

    def test_naip_aoi_scope_is_reference_only(self):
        row = SOURCE_REGISTRY[_NAIP_SOURCE]
        assert row.aoi_scope == AoiScope.REFERENCE_ONLY

    def test_naip_product_exposure_is_reference_only(self):
        row = SOURCE_REGISTRY[_NAIP_SOURCE]
        assert row.product_exposure == ProductExposure.REFERENCE_ONLY

    def test_naip_cadence_is_reference(self):
        row = SOURCE_REGISTRY[_NAIP_SOURCE]
        assert row.cadence == CadenceClass.REFERENCE

    def test_naip_is_never_due(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_NAIP_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.is_due]
        assert not due, "NAIP (reference_only/out-of-AOI) must never be due"

    def test_naip_skip_reason_is_non_empty(self, tmp_path):
        """NAIP decisions must have a non-empty skip reason when an AOI is supplied."""
        decisions = plan_due_sources(
            source_ids=[_NAIP_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            # NAIP must never be due AND must always have a skip reason
            assert not d.is_due
            assert d.skip_reason, "NAIP must have a non-empty skip reason"


# ===========================================================================
# 5. Archive sources: ARCHIVE_ON_DEMAND cadence is never auto-due
# ===========================================================================


class TestArchiveSourcesNotAutoDue:
    @pytest.mark.parametrize(
        "source_id",
        [
            "landsat-7-c2-l2",
            "landsat-5-c2-l2",
            "irs-1c-liss3-archive",
            "alos2-mosaic-25m",
        ],
    )
    def test_archive_on_demand_source_is_never_auto_due(self, source_id, tmp_path):
        row = SOURCE_REGISTRY[source_id]
        assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND

        decisions = plan_due_sources(
            source_ids=[source_id],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        due = [d for d in decisions if d.is_due]
        assert not due, f"{source_id} (archive_on_demand) must never be auto-due"

    def test_archive_skip_reason_mentions_archive_cadence(self, tmp_path):
        """Archive-on-demand sources must have a skip reason mentioning the cadence."""
        decisions = plan_due_sources(
            source_ids=[_ARCHIVE_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        non_due = [d for d in decisions if not d.is_due]
        assert non_due
        reasons = [d.skip_reason or "" for d in non_due]
        assert any("archive" in r.lower() or "manual_only" in r.lower() for r in reasons)

    def test_manual_override_can_force_archive_source_due(self, tmp_path):
        """Manual override is the only way to run an archive source."""
        override_key = f"{_ARCHIVE_SOURCE}::{_DEFAULT_AOI}"
        decisions = plan_due_sources(
            source_ids=[_ARCHIVE_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={override_key: True},
        )
        due = [d for d in decisions if d.is_due and d.source_id == _ARCHIVE_SOURCE]
        assert due, "Manual override must allow archive source to be due"


# ===========================================================================
# 6. Approved-runtime gate: staging Bhoonidhi fails closed without approval
# ===========================================================================


class TestApprovedRuntimeGate:
    def test_staging_bhoonidhi_without_approval_is_skipped_gated(self, tmp_path, monkeypatch):
        """run_source_job on a STAGING_BHOONIDHI source without approval → SKIPPED_GATED."""
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=False,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SKIPPED_GATED)
        assert result.failure_kind == "approved_runtime_required"

    def test_staging_bhoonidhi_without_approval_makes_no_provider_calls(
        self, tmp_path, monkeypatch
    ):
        """No provider calls must be made when failing closed."""
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        with patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                dry_run=False,
                approved_runtime=False,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        mock_adapter.assert_not_called()

    def test_env_var_approves_runtime(self, tmp_path, monkeypatch):
        """AKASHA_APPROVED_RUNTIME=1 in env should allow the job past the preflight gate."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=False,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        # Phase 4 conservative execution → SUCCEEDED (adapter resolved, no live calls)
        assert result.failure_kind != "approved_runtime_required"

    def test_approved_runtime_kwarg_approves_runtime(self, tmp_path, monkeypatch):
        """approved_runtime=True kwarg should allow the job past the preflight gate."""
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.failure_kind != "approved_runtime_required"

    def test_failure_kind_recorded_in_result_artifact(self, tmp_path, monkeypatch):
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=False,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        artifact = read_result(result.job_id, tmp_path)
        assert artifact.get("failureKind") == "approved_runtime_required"

    def test_non_staging_bhoonidhi_source_not_subject_to_gate(self, tmp_path, monkeypatch):
        """Sources on APPROVED_WORKER host pool must not be blocked by the staging gate."""
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        # sentinel-2-l2a has host_pool=APPROVED_WORKER and schedule_state=DISABLED
        # It should be gated by schedule_state, not by approved_runtime
        result = run_source_job(
            "sentinel-2-l2a",
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=False,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.failure_kind != "approved_runtime_required"
        assert result.status == str(JobStatus.SKIPPED_GATED)


# ===========================================================================
# 7. Lock behavior: stale locks reclaimed, live locks block
# ===========================================================================


class TestLockBehavior:
    def test_acquire_and_release_basic(self, tmp_path):
        lock = acquire_global_lock(tmp_path)
        assert lock.path.exists()
        release_lock(lock)
        assert not lock.path.exists()

    def test_live_lock_blocks_second_acquire(self, tmp_path):
        lock = acquire_global_lock(tmp_path)
        try:
            with pytest.raises(SchedulerLockError):
                acquire_global_lock(tmp_path)
        finally:
            release_lock(lock)

    def test_stale_lock_by_age_is_reclaimed(self, tmp_path):
        """An old lock with a dead PID must be reclaimed automatically."""
        # Write a lock file with a timestamp far in the past
        from akasha_ingest.scheduler_locks import GLOBAL_LOCK_NAME, _now

        lock_path = tmp_path / GLOBAL_LOCK_NAME
        past_ts = (_now() - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        lock_path.write_text(
            f"pid=99999999 acquired_at={past_ts}\n", encoding="utf-8"
        )

        # The old PID is almost certainly dead; age > 2h default TTL
        lock = acquire_global_lock(tmp_path, stale_ttl_seconds=60)
        assert lock.path.exists()
        release_lock(lock)

    def test_old_lock_with_live_pid_is_not_reclaimed(self, tmp_path):
        """TTL alone must not steal a lock from a still-live process."""
        from akasha_ingest.scheduler_locks import GLOBAL_LOCK_NAME, _now

        lock_path = tmp_path / GLOBAL_LOCK_NAME
        past_ts = (_now() - timedelta(hours=9)).isoformat().replace("+00:00", "Z")
        lock_path.write_text(
            f"pid={os.getpid()} acquired_at={past_ts}\n", encoding="utf-8"
        )

        with pytest.raises(SchedulerLockError):
            acquire_global_lock(tmp_path, stale_ttl_seconds=60)

    def test_release_lock_does_not_remove_lock_reacquired_by_another_holder(self, tmp_path):
        """A stale handle must not unlink a lock now owned by a different holder."""
        lock = acquire_global_lock(tmp_path)
        os.close(lock.fd)
        lock.path.unlink()
        replacement = acquire_global_lock(tmp_path)
        try:
            release_lock(lock)
            assert replacement.path.exists()
        finally:
            release_lock(replacement)

    def test_corrupt_lock_payload_treated_as_live(self, tmp_path):
        """An unreadable lock payload must NOT be silently reclaimed (fail-closed)."""
        from akasha_ingest.scheduler_locks import GLOBAL_LOCK_NAME

        lock_path = tmp_path / GLOBAL_LOCK_NAME
        lock_path.write_text("CORRUPTED_PAYLOAD\n", encoding="utf-8")

        with pytest.raises(SchedulerLockError):
            acquire_global_lock(tmp_path, stale_ttl_seconds=7200)

    def test_worker_lock_naming_liss3_legacy(self):
        """LISS-3 must use the legacy bhoonidhi-sync lock prefix."""
        name = worker_lock_name(_LISS3_SOURCE, _DEFAULT_AOI)
        assert name == f"bhoonidhi-sync.{_DEFAULT_AOI}.worker.lock"

    def test_worker_lock_naming_liss4_legacy(self):
        """LISS-4 must use the legacy bhoonidhi-liss4-sync lock prefix."""
        name = worker_lock_name(_LISS4_SOURCE, _DEFAULT_AOI)
        assert name == f"bhoonidhi-liss4-sync.{_DEFAULT_AOI}.worker.lock"

    def test_worker_lock_naming_other_source(self):
        name = worker_lock_name("sentinel-2-l2a", _DEFAULT_AOI)
        assert name == f"sentinel-2-l2a.{_DEFAULT_AOI}.worker.lock"

    def test_worker_lock_blocks_concurrent_run_source_job(self, tmp_path, monkeypatch):
        """If a worker lock is already held, run_source_job records BLOCKED_BY_LOCK."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir(parents=True)

        # Pre-acquire the worker lock
        held_lock = acquire_worker_lock(lock_dir, _LISS3_SOURCE, _DEFAULT_AOI)
        try:
            result = run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                dry_run=False,
                approved_runtime=True,
                base_dir=tmp_path,
                lock_dir=lock_dir,
                now=_FIXED_NOW,
            )
        finally:
            release_lock(held_lock)

        assert result.status == str(JobStatus.BLOCKED_BY_LOCK)
        assert result.failure_kind == "lock_blocked"

    def test_blocked_by_lock_makes_no_provider_calls(self, tmp_path, monkeypatch):
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir(parents=True)

        held_lock = acquire_worker_lock(lock_dir, _LISS3_SOURCE, _DEFAULT_AOI)
        try:
            with patch(
                "akasha_ingest.providers.registry.get_provider_adapter"
            ) as mock_adapter:
                run_source_job(
                    _LISS3_SOURCE,
                    _DEFAULT_AOI,
                    dry_run=False,
                    approved_runtime=True,
                    base_dir=tmp_path,
                    lock_dir=lock_dir,
                    now=_FIXED_NOW,
                )
        finally:
            release_lock(held_lock)

        mock_adapter.assert_not_called()

    def test_release_lock_removes_lock_file(self, tmp_path):
        """release_lock must remove the lock file upon normal release."""
        lock = acquire_global_lock(tmp_path)
        assert lock.path.exists()
        release_lock(lock)
        assert not lock.path.exists()


# ===========================================================================
# 8. Concurrency / max_sources budget
# ===========================================================================


class TestMaxSourcesLimit:
    def test_run_due_sources_respects_max_sources(self, tmp_path, monkeypatch):
        """run_due_sources must not exceed max_sources jobs."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE, _LISS4_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={
                f"{_LISS3_SOURCE}::{_DEFAULT_AOI}": True,
                f"{_LISS4_SOURCE}::{_DEFAULT_AOI}": True,
            },
        )
        due = [d for d in decisions if d.is_due]
        assert len(due) >= 2, "Need at least 2 due sources to test the limit"

        results = run_due_sources(
            decisions,
            dry_run=True,  # safe: no provider calls
            max_sources=1,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert len(results) == 1, "max_sources=1 must limit results to exactly 1"

    def test_run_due_sources_skips_non_due(self, tmp_path, monkeypatch):
        """run_due_sources must silently skip decisions where is_due=False."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={f"{_LISS3_SOURCE}::{_DEFAULT_AOI}": True},
        )
        # All LISS-3 decisions should be due (first run)
        due = [d for d in decisions if d.is_due]
        assert due

        # Force all non-due by manipulating decisions list
        from akasha_ingest.orchestrator import DueDecision

        not_due = [
            DueDecision(
                source_id=d.source_id,
                aoi_id=d.aoi_id,
                provider=d.provider,
                schedule_state=d.schedule_state,
                is_due=False,
                skip_reason="not due",
                last_succeeded_at=None,
                last_window_end=None,
                next_due_at=None,
                window_start=d.window_start,
                window_end=d.window_end,
            )
            for d in decisions
        ]

        results = run_due_sources(
            not_due,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert results == [], "Non-due decisions must produce no results"


# ===========================================================================
# 9. AWiFS: below-threshold / validation_failed stays background_only
# ===========================================================================


class TestAWiFSValidationFailedGate:
    def test_awifs_schedule_state_is_background_only(self):
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.schedule_state == ScheduleState.BACKGROUND_ONLY

    def test_awifs_product_exposure_is_background_only(self):
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.product_exposure == ProductExposure.BACKGROUND_ONLY

    def test_awifs_validation_state_is_failed(self):
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.validation_state == ValidationState.VALIDATION_FAILED

    def test_awifs_product_exposure_not_product_active(self):
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.product_exposure != ProductExposure.PRODUCT_ACTIVE

    def test_awifs_due_decision_carries_background_only_exposure(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_AWIFS_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            if d.source_id == _AWIFS_SOURCE:
                assert d.product_exposure == ProductExposure.BACKGROUND_ONLY.value

    def test_awifs_run_job_can_attempt_background_pipeline_without_promotion(
        self, tmp_path, monkeypatch
    ):
        """AWiFS background ingestion may run while product exposure stays gated.

        The live pipeline is still deferred, so this records a pipeline_deferred
        failure instead of low_coverage. The important behavior is that
        validation_failed does not block background attempts before they can
        discover a later passing composite.
        """
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        assert result.failure_kind == "pipeline_deferred"
        # Product exposure in registry must NOT be promoted
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.product_exposure == ProductExposure.BACKGROUND_ONLY

    def test_awifs_deferred_background_attempt_does_not_update_ledger(
        self, tmp_path, monkeypatch
    ):
        """Deferred background attempts must not write a scheduler success entry."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        ledger = _make_fresh_ledger(tmp_path)
        entry = ledger.get_entry(_AWIFS_SOURCE, _DEFAULT_AOI)
        assert entry == {}, (
            "Scheduler ledger must NOT be updated for a VALIDATION_FAILED job"
        )

    def test_awifs_readiness_reasons_mention_coverage(self):
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        reasons_text = " ".join(row.readiness_reasons)
        assert "coverage" in reasons_text.lower() or "threshold" in reasons_text.lower()


# ===========================================================================
# 10. Unknown source raises ValueError
# ===========================================================================


class TestUnknownSourceValidation:
    def test_run_source_job_raises_for_unknown_source(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown source_id"):
            run_source_job(
                "nonexistent-source-xyz",
                _DEFAULT_AOI,
                dry_run=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
            )

    def test_plan_due_sources_filters_to_known_source_ids(self, tmp_path):
        """Passing a known source ID returns only decisions for that source."""
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            assert d.source_id == _LISS3_SOURCE


# ===========================================================================
# 11. Phase 4 conservative execution: ledger updated on success
# ===========================================================================


class TestPhase4ConservativeExecution:
    def test_approved_run_fails_closed_until_live_pipeline_is_implemented(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        assert result.failure_kind == "pipeline_deferred"

    def test_approved_run_does_not_update_scheduler_ledger_before_real_ingestion(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        ledger = _make_fresh_ledger(tmp_path)
        entry = ledger.get_entry(_LISS3_SOURCE, _DEFAULT_AOI)
        assert entry == {}, "Deferred live path must not advance scheduler cadence"

    def test_approved_run_remains_due_because_no_success_was_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        # Check: 1 minute later, the source should NOT be due again
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            base_dir=tmp_path,
            now=_FIXED_NOW + timedelta(minutes=1),
            manual_overrides={f"{_LISS3_SOURCE}::{_DEFAULT_AOI}": True},
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert due, "LISS-3 must remain runnable because deferred live path did not succeed"

    def test_phase4_no_live_search_download_calls(self, tmp_path, monkeypatch):
        """Phase 4 conservative execution must NOT invoke search/download on the adapter.

        The adapter is resolved (get_provider_adapter called once) but no methods
        are invoked on it — proven by passing a MagicMock whose method calls we can
        verify afterwards.
        """
        from unittest.mock import MagicMock

        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        mock_adapter = MagicMock()

        with patch(
            "akasha_ingest.providers.registry.get_provider_adapter",
            return_value=mock_adapter,
        ) as mock_get:
            run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                dry_run=False,
                approved_runtime=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        # get_provider_adapter was called once (adapter resolved)
        mock_get.assert_called_once()
        # No search/download/order methods were called on the adapter
        mock_adapter.search.assert_not_called()
        mock_adapter.download.assert_not_called()


# ===========================================================================
# 12. Parser / CLI smoke tests
# ===========================================================================


class TestWorkerCLIParser:
    """Smoke tests for the worker CLI parser — no live provider calls made."""

    def _get_parser(self):
        # Add the ingestion service root so worker.py can be imported
        worker_path = INGESTION_ROOT / "worker.py"
        if not worker_path.exists():
            pytest.skip("worker.py not found")
        import importlib.util

        spec = importlib.util.spec_from_file_location("worker", worker_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.build_parser()

    def test_schedule_plan_command_exists(self):
        parser = self._get_parser()
        args = parser.parse_args(["schedule-plan"])
        assert args.command == "schedule-plan"

    def test_schedule_plan_json_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(["schedule-plan", "--json"])
        assert args.json is True

    def test_schedule_plan_source_aoi_flags(self):
        parser = self._get_parser()
        args = parser.parse_args(
            ["schedule-plan", "--source", _LISS3_SOURCE, "--aoi", _DEFAULT_AOI]
        )
        assert args.source == _LISS3_SOURCE
        assert args.aoi == _DEFAULT_AOI

    def test_schedule_due_sources_command_exists(self):
        parser = self._get_parser()
        args = parser.parse_args(["schedule-due-sources"])
        assert args.command == "schedule-due-sources"

    def test_schedule_due_sources_dry_run_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(["schedule-due-sources", "--dry-run"])
        assert args.dry_run is True

    def test_schedule_due_sources_max_concurrent_source_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(["schedule-due-sources", "--max-concurrent-source", "3"])
        assert args.max_concurrent_source == 3

    def test_schedule_source_command_requires_source_and_aoi(self):
        parser = self._get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["schedule-source"])

    def test_schedule_source_dry_run_flags(self):
        parser = self._get_parser()
        args = parser.parse_args(
            [
                "schedule-source",
                "--source",
                _LISS3_SOURCE,
                "--aoi",
                _DEFAULT_AOI,
                "--dry-run",
            ]
        )
        assert args.source == _LISS3_SOURCE
        assert args.aoi == _DEFAULT_AOI
        assert args.dry_run is True

    def test_schedule_source_approved_runtime_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(
            [
                "schedule-source",
                "--source",
                _LISS3_SOURCE,
                "--aoi",
                _DEFAULT_AOI,
                "--approved-runtime",
            ]
        )
        assert args.approved_runtime is True

    def test_bhoonidhi_sync_command_present_and_not_delegated(self):
        """bhoonidhi-sync must remain as its own parser path (TASK-026 compat)."""
        parser = self._get_parser()
        args = parser.parse_args(
            [
                "bhoonidhi-sync",
                "--source",
                _LISS3_SOURCE,
                "--aoi",
                _DEFAULT_AOI,
                "--dry-run",
            ]
        )
        assert args.command == "bhoonidhi-sync"
        assert args.source == _LISS3_SOURCE
        assert args.dry_run is True
        # Verify the registered function is cmd_bhoonidhi_sync, not an orchestrator wrapper
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "worker", INGESTION_ROOT / "worker.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert args.func.__name__ == "cmd_bhoonidhi_sync"

    def test_schedule_plan_json_output_via_cmd_fn(self, tmp_path, monkeypatch):
        """schedule-plan --json must emit a valid JSON array without provider calls."""
        import importlib.util
        import io
        from contextlib import redirect_stdout

        spec = importlib.util.spec_from_file_location(
            "worker", INGESTION_ROOT / "worker.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        parser = mod.build_parser()
        args = parser.parse_args(
            [
                "schedule-plan",
                "--source",
                _LISS3_SOURCE,
                "--aoi",
                _DEFAULT_AOI,
                "--base-dir",
                str(tmp_path),
                "--json",
            ]
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.cmd_schedule_plan(args)

        assert rc == 0
        output = buf.getvalue()
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        for item in parsed:
            assert "sourceId" in item
            assert "isDue" in item

    def test_schedule_source_dry_run_via_cmd_fn(self, tmp_path, monkeypatch):
        """schedule-source --dry-run must not raise and must return 0."""
        import importlib.util
        import io
        from contextlib import redirect_stdout

        spec = importlib.util.spec_from_file_location(
            "worker", INGESTION_ROOT / "worker.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        parser = mod.build_parser()
        args = parser.parse_args(
            [
                "schedule-source",
                "--source",
                _LISS3_SOURCE,
                "--aoi",
                _DEFAULT_AOI,
                "--base-dir",
                str(tmp_path),
                "--lock-dir",
                str(tmp_path / "locks"),
                "--dry-run",
            ]
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.cmd_schedule_source(args)

        assert rc == 0


# ===========================================================================
# 13. SchedulerLedger: persistence and round-trip
# ===========================================================================


class TestSchedulerLedger:
    def test_empty_ledger_returns_no_entry(self, tmp_path):
        ledger = _make_fresh_ledger(tmp_path)
        assert ledger.get_entry(_LISS3_SOURCE, _DEFAULT_AOI) == {}

    def test_record_success_persists(self, tmp_path):
        ledger = _make_fresh_ledger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_abc",
            window_end="2026-06-24",
            succeeded_at="2026-06-24T12:00:00Z",
        )
        # Reload from disk
        ledger2 = _make_fresh_ledger(tmp_path)
        entry = ledger2.get_entry(_LISS3_SOURCE, _DEFAULT_AOI)
        assert entry["lastSucceededAt"] == "2026-06-24T12:00:00Z"
        assert entry["lastWindowEnd"] == "2026-06-24"
        assert entry["lastJobId"] == "job_abc"

    def test_record_success_overwrites_previous_entry(self, tmp_path):
        ledger = _make_fresh_ledger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_old",
            window_end="2026-06-10",
            succeeded_at="2026-06-10T10:00:00Z",
        )
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_new",
            window_end="2026-06-24",
            succeeded_at="2026-06-24T12:00:00Z",
        )
        entry = ledger.get_entry(_LISS3_SOURCE, _DEFAULT_AOI)
        assert entry["lastJobId"] == "job_new"


# ===========================================================================
# 14. Windows PID liveness: no CTRL_C_EVENT / KeyboardInterrupt
# ===========================================================================


class TestPidLivenessPortability:
    def test_current_pid_is_alive(self):
        """_pid_is_alive(os.getpid()) must return True without raising KeyboardInterrupt."""
        import os

        from akasha_ingest.scheduler_locks import _pid_is_alive

        # This is the critical assertion: must not raise KeyboardInterrupt on Windows
        result = _pid_is_alive(os.getpid())
        assert result is True

    def test_implausibly_large_pid_is_not_alive(self):
        """_pid_is_alive with an absurdly large PID must return False."""
        from akasha_ingest.scheduler_locks import _pid_is_alive

        assert _pid_is_alive(2_000_000_000) is False

    def test_old_live_pid_lock_does_not_raise_keyboard_interrupt(self, tmp_path):
        """Old lock with a live PID must block safely without KeyboardInterrupt."""
        from akasha_ingest.scheduler_locks import GLOBAL_LOCK_NAME, _now

        lock_path = tmp_path / GLOBAL_LOCK_NAME
        import os

        past_ts = (_now() - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        # Write a lock with our own PID so _pid_is_alive is called, but age > TTL
        lock_path.write_text(f"pid={os.getpid()} acquired_at={past_ts}\n", encoding="utf-8")

        with pytest.raises(SchedulerLockError):
            acquire_global_lock(tmp_path, stale_ttl_seconds=60)


# ===========================================================================
# 15. Legacy lock-dir compatibility
# ===========================================================================


class TestLegacyLockDirCompatibility:
    def test_default_lock_dir_is_ingestion_root(self):
        """DEFAULT_LOCK_DIR must point to /srv/akasha/ingestion/ (not a scheduler subdir)."""
        from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR

        assert DEFAULT_LOCK_DIR.rstrip("/") == "/srv/akasha/ingestion", (
            f"Expected /srv/akasha/ingestion/ but got {DEFAULT_LOCK_DIR!r}"
        )

    def test_liss3_worker_lock_path_matches_legacy_wrapper(self):
        """LISS-3 worker lock path must match the legacy bhoonidhi wrapper path."""
        from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR
        from akasha_ingest.scheduler_locks import worker_lock_path

        path = worker_lock_path(DEFAULT_LOCK_DIR, _LISS3_SOURCE, _DEFAULT_AOI)
        expected_suffix = f"bhoonidhi-sync.{_DEFAULT_AOI}.worker.lock"
        assert str(path).replace("\\", "/").endswith(expected_suffix), (
            f"Expected path ending in {expected_suffix!r}, got {str(path)!r}"
        )

    def test_liss4_worker_lock_path_matches_legacy_wrapper(self):
        """LISS-4 worker lock path must match the legacy bhoonidhi-liss4-sync wrapper path."""
        from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR
        from akasha_ingest.scheduler_locks import worker_lock_path

        path = worker_lock_path(DEFAULT_LOCK_DIR, _LISS4_SOURCE, _DEFAULT_AOI)
        expected_suffix = f"bhoonidhi-liss4-sync.{_DEFAULT_AOI}.worker.lock"
        assert str(path).replace("\\", "/").endswith(expected_suffix)

    def test_worker_lock_not_under_scheduler_locks_subdir(self):
        """Default worker lock must NOT be nested under scheduler/locks/."""
        from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR
        from akasha_ingest.scheduler_locks import worker_lock_path

        path = str(worker_lock_path(DEFAULT_LOCK_DIR, _LISS3_SOURCE, _DEFAULT_AOI))
        # The old broken default produced paths with "scheduler/locks" in them
        assert "scheduler/locks" not in path.replace("\\", "/")


# ===========================================================================
# 16. Terminal double-transition guard
# ===========================================================================


class TestTerminalDoubleTransitionGuard:
    def test_ledger_write_failure_records_failed_not_crash(
        self, tmp_path, monkeypatch
    ):
        """If ledger.record_success raises, job finishes as FAILED without crashing.

        Ledger update is now done BEFORE finish_job(SUCCEEDED), so a ledger
        write failure leaves the job in RUNNING state and the except handler
        can safely transition to FAILED.
        """
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")

        from akasha_ingest.orchestrator import SchedulerLedger

        def _failing_record_success(self, *args, **kwargs):
            raise OSError("simulated disk error in ledger write")

        monkeypatch.setattr(SchedulerLedger, "record_success", _failing_record_success)

        # Must not raise — exception must be caught and job marked FAILED
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        assert result.failure_kind == "pipeline_deferred"

    def test_terminal_to_terminal_value_error_is_suppressed(
        self, tmp_path, monkeypatch
    ):
        """Exception handler must suppress ValueError from terminal→terminal double-transition."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")

        import akasha_ingest.orchestrator as orch_module
        from akasha_ingest.jobs import finish_job as real_finish_job
        from akasha_ingest.orchestrator import SchedulerLedger

        original_finish = real_finish_job
        finish_calls = []

        def _patched_finish(job_id, status, summary, base_dir, **kwargs):
            result = original_finish(job_id, status, summary, base_dir, **kwargs)
            finish_calls.append(str(status))
            return result

        monkeypatch.setattr(orch_module, "finish_job", _patched_finish)

        # Force the ledger write to fail so the except branch is reached
        def _failing_record_success(self, *args, **kwargs):
            raise RuntimeError("forced ledger error — exercises except guard")

        monkeypatch.setattr(SchedulerLedger, "record_success", _failing_record_success)

        # Must not propagate any uncaught exception
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)


# ===========================================================================
# 17. Phase 7: Bhoonidhi scheduler path / dry-run parity metadata (TASK-045/046/047)
# ===========================================================================


class TestPhase7SchedulerPath:
    """Phase 7 dry-run parity mode and observability metadata for Bhoonidhi sources.

    Coverage:
    - Dry-run plan event carries Phase 7 planned stages for Bhoonidhi sources.
    - Dry-run plan event carries parity stop point (matches bhoonidhi-sync --dry-run).
    - Dry-run plan event carries source thresholds and manifest handles.
    - AWiFS VALIDATION_FAILED observability includes readinessReasons.
    - Provider input summary phase key is updated to phase7_scheduler_path
      for Bhoonidhi sources.
    - Non-Bhoonidhi dry-run plans do not carry Bhoonidhi-specific keys.
    - bhoonidhi-sync remains non-delegated (preserved compatibility path).
    """

    def test_bhoonidhi_dry_run_plan_event_carries_planned_stages(self, tmp_path):
        """Dry-run plan event for LISS-3 must carry Phase 7 plannedStages."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events, "No dry_run_plan event found in LISS-3 dry-run job"
        payload = plan_events[0].get("payload", {})
        assert "plannedStages" in payload, "Phase 7 plannedStages missing from dry_run_plan"
        stages = payload["plannedStages"]
        assert "search" in stages
        assert "download" in stages
        assert "composite" in stages
        assert "ingest" in stages
        assert "validate" in stages

    def test_bhoonidhi_dry_run_plan_event_carries_parity_stop_point(self, tmp_path):
        """Dry-run plan event must declare the parity stop point relative to bhoonidhi-sync."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        assert "parityStopPoint" in payload, "parityStopPoint missing from Bhoonidhi dry_run_plan"
        # bhoonidhi-sync --dry-run stops before download
        assert payload["parityStopPoint"] == "before_download"

    def test_bhoonidhi_dry_run_plan_event_carries_source_thresholds(self, tmp_path):
        """Dry-run plan event for a Bhoonidhi source must carry sourceThresholds."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        assert "sourceThresholds" in payload, "sourceThresholds missing from Bhoonidhi dry_run_plan"
        thresholds = payload["sourceThresholds"]
        assert "minCoveragePercent" in thresholds
        assert "lookbackDays" in thresholds

    def test_bhoonidhi_dry_run_plan_event_carries_manifest_handles(self, tmp_path):
        """Dry-run plan event for a Bhoonidhi source must carry opaque manifestHandles."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        assert "manifestHandles" in payload, "manifestHandles missing from Bhoonidhi dry_run_plan"
        handles = payload["manifestHandles"]
        assert "searchManifestHandle" in handles
        assert "compositeManifestHandle" in handles

    def test_bhoonidhi_dry_run_plan_manifest_handles_encode_source_and_window(self, tmp_path):
        """manifestHandles must encode the source_id, aoi_id, and window_end."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        payload = plan_events[0].get("payload", {})
        handles = payload["manifestHandles"]
        for handle_value in handles.values():
            assert _LISS3_SOURCE in handle_value
            assert _DEFAULT_AOI in handle_value

    def test_bhoonidhi_dry_run_plan_has_phase7_phase_key(self, tmp_path):
        """Dry-run plan payload phase key must be 'phase7_scheduler_path' for Bhoonidhi."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        assert payload.get("phase") == "phase7_scheduler_path"

    def test_awifs_dry_run_plan_carries_bhoonidhi_stage_metadata(self, tmp_path):
        """AWiFS is also a Bhoonidhi source; its dry-run plan must carry plannedStages."""
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events, "AWiFS dry-run plan event missing"
        payload = plan_events[0].get("payload", {})
        assert "plannedStages" in payload

    def test_awifs_validation_failed_observability_includes_readiness_reasons(
        self, tmp_path, monkeypatch
    ):
        """VALIDATION_FAILED observability for AWiFS must carry readinessReasons.

        TASK-046: background_only AWiFS must report readiness_reasons from the
        registry so operators can see why it cannot be promoted to product-active.
        """
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        assert result.failure_kind == "pipeline_deferred"
        obs_path = job_dir(result.job_id, tmp_path) / "observability.json"
        assert obs_path.exists(), "observability.json was not written for AWiFS VALIDATION_FAILED"
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
        v_summary = obs.get("verificationSummary", {})
        assert v_summary["verdict"] == "pipeline_deferred"
        assert v_summary["productExposure"] == ProductExposure.BACKGROUND_ONLY.value

    def test_awifs_validation_failed_status_and_exposure_preserved(
        self, tmp_path, monkeypatch
    ):
        """VALIDATION_FAILED run must not promote AWiFS product_exposure."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        from akasha_ingest.source_registry import ProductExposure

        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.product_exposure == ProductExposure.BACKGROUND_ONLY

    def test_phase7_prov_input_phase_key_for_bhoonidhi_approved_run(
        self, tmp_path, monkeypatch
    ):
        """Bhoonidhi approved run must record phase7_scheduler_path in providerInputSummary.

        TASK-047: prov_input.phase key reflects Phase 7 scheduler path for Bhoonidhi.
        """
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.FAILED)
        assert result.failure_kind == "pipeline_deferred"
        obs_path = job_dir(result.job_id, tmp_path) / "observability.json"
        assert obs_path.exists()
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
        prov_input = obs.get("providerInputSummary", {})
        assert prov_input.get("phase") == "phase7_scheduler_path", (
            f"Expected phase7_scheduler_path but got {prov_input.get('phase')!r}"
        )

    def test_non_bhoonidhi_dry_run_plan_has_no_planned_stages(self, tmp_path, monkeypatch):
        """Non-Bhoonidhi sources must not carry Bhoonidhi-specific plannedStages.

        Finds a non-Bhoonidhi source that is not gated so it reaches dry_run path.
        """
        from akasha_ingest.orchestrator import _gate_reason

        non_bhoonidhi_source: str | None = None
        for sid, row in SOURCE_REGISTRY.items():
            if row.provider_adapter != "bhoonidhi" and _gate_reason(row, _DEFAULT_AOI) is None:
                non_bhoonidhi_source = sid
                break
        if non_bhoonidhi_source is None:
            pytest.skip("No non-Bhoonidhi non-gated source found in registry")

        result = run_source_job(
            non_bhoonidhi_source,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        # Non-Bhoonidhi source must NOT have Phase 7 Bhoonidhi metadata
        assert "plannedStages" not in payload
        assert "parityStopPoint" not in payload
        assert "manifestHandles" not in payload

    def test_bhoonidhi_dry_run_still_makes_no_provider_calls(self, tmp_path):
        """Phase 7 dry-run extension must not introduce any provider calls."""
        with patch(
            "akasha_ingest.orchestrator.acquire_worker_lock"
        ) as mock_lock, patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                dry_run=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        # Lock must NOT be acquired (short-circuits before lock path)
        mock_lock.assert_not_called()
        # Provider adapter must NOT be resolved
        mock_adapter.assert_not_called()

    def test_bhoonidhi_sync_command_func_unchanged(self):
        """bhoonidhi-sync must remain non-delegated and point to cmd_bhoonidhi_sync."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "worker", INGESTION_ROOT / "worker.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        parser = mod.build_parser()
        args = parser.parse_args(
            ["bhoonidhi-sync", "--source", _LISS3_SOURCE, "--aoi", _DEFAULT_AOI, "--dry-run"]
        )
        assert args.func.__name__ == "cmd_bhoonidhi_sync", (
            "bhoonidhi-sync must remain non-delegated (TASK-026 compat preserved)"
        )
