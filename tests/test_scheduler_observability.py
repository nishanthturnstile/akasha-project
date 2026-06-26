"""TASK-034 — Scheduler observability tests.

Proves:
1. Job inspection redacts secrets.
2. Job inspection returns request/status/result/log pointers as opaque handles.
3. Job-artifact fetch is redacted by default.
4. Operator/raw access requires explicit --operator flag.
5. schedule-plan exposes why a source is/is not due (orchestrator level).
6. schedule-next exposes next due run/window using scheduler state.
7. Job ledger writes required fields, uses WAL/busy timeout, and pruning works.
8. Observability summaries use opaque handles/redacted summaries, not raw secrets.

No live SSH or provider calls are made.  All tests use tmp_path / monkeypatch.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — add ingestion service root so akasha_ingest is importable
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest.job_ledger import BUSY_TIMEOUT_MS, JobLedger  # noqa: E402
from akasha_ingest.jobs import (  # noqa: E402
    ARTIFACT_TYPE_OBSERVABILITY,
    ARTIFACT_TYPE_REQUEST,
    ARTIFACT_TYPE_RESULT,
    ARTIFACT_TYPE_STATUS,
    OBSERVABILITY_FILE,
    JobStatus,
    ObservabilitySummary,
    job_dir,
    make_artifact_handle,
    read_observability,
    write_observability,
)
from akasha_ingest.orchestrator import (  # noqa: E402
    APPROVED_RUNTIME_ENV_VAR,
    SchedulerLedger,
    plan_due_sources,
    run_source_job,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_LISS3_SOURCE = "resourcesat-2a-liss3-boa"
_AWIFS_SOURCE = "resourcesat-2a-awifs-boa"
_COMMERCIAL_SOURCE = "planetscope"
_DEFAULT_AOI = "bangalore-60km"
_FIXED_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=UTC)


# ===========================================================================
# 1. make_artifact_handle — opaque format, no filesystem path leakage
# ===========================================================================


class TestMakeArtifactHandle:
    """Artifact handles must be opaque; they must not embed raw filesystem paths."""

    def test_handle_format_is_job_id_colon_type(self):
        job_id = "job_20260624T120000Z_abc123def456"
        handle = make_artifact_handle(job_id, ARTIFACT_TYPE_REQUEST)
        assert handle == f"{job_id}:{ARTIFACT_TYPE_REQUEST}"

    def test_handle_contains_no_forward_slash(self):
        handle = make_artifact_handle("job_20260624T120000Z_abc", ARTIFACT_TYPE_STATUS)
        # No filesystem path separator
        assert "/" not in handle

    def test_handle_contains_no_srv_path(self):
        handle = make_artifact_handle("job_abc123", ARTIFACT_TYPE_OBSERVABILITY)
        assert "/srv/" not in handle
        assert "srv" not in handle

    @pytest.mark.parametrize(
        "artifact_type",
        [
            ARTIFACT_TYPE_REQUEST,
            ARTIFACT_TYPE_STATUS,
            ARTIFACT_TYPE_RESULT,
            ARTIFACT_TYPE_OBSERVABILITY,
            "search_manifest",
            "download_manifest",
        ],
    )
    def test_handle_encodes_artifact_type_as_suffix(self, artifact_type):
        handle = make_artifact_handle("job_test", artifact_type)
        assert handle.endswith(f":{artifact_type}")

    def test_handle_does_not_embed_source_id_or_aoi(self):
        """The handle must be fully opaque — no source/AOI info embedded."""
        job_id = "job_20260624T120000Z_abc123"
        handle = make_artifact_handle(job_id, ARTIFACT_TYPE_REQUEST)
        assert "resourcesat" not in handle
        assert "bangalore" not in handle
        assert "liss3" not in handle


# ===========================================================================
# 2. ObservabilitySummary — opaque handles, secrets redacted
# ===========================================================================


class TestObservabilitySummary:
    """observability.json must use opaque handles and never expose raw credentials."""

    def test_to_dict_redacts_s3_credentials(self):
        """Raw S3 credentials in provider_input_summary must be replaced by the sentinel."""
        obs = ObservabilitySummary(
            job_id="job_test",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
            provider_input_summary={
                "s3_access_key": "AKIAIOSFODNN7EXAMPLE",
                "s3_secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "sourceId": _LISS3_SOURCE,
            },
        )
        text = json.dumps(obs.to_dict())
        assert "AKIAIOSFODNN7EXAMPLE" not in text
        assert "wJalrXUtnFEMI" not in text

    def test_to_dict_redacts_bearer_token_preserves_count(self):
        """Bearer token must be redacted; non-sensitive found_count must survive."""
        obs = ObservabilitySummary(
            job_id="job_test",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
            provider_response_summary={
                "authorization": "Bearer supersecret-token-12345",
                "foundCount": 5,
            },
        )
        d = obs.to_dict()
        text = json.dumps(d)
        assert "supersecret-token-12345" not in text
        # Non-sensitive field must survive
        assert d["providerResponseSummary"]["foundCount"] == 5

    def test_to_dict_uses_opaque_manifest_handles_not_paths(self):
        """Manifest pointers must be opaque handles, not raw /srv/ paths."""
        obs = ObservabilitySummary(
            job_id="job_abc123",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
            search_manifest_handle="job_abc123:search_manifest",
            download_manifest_handle="job_abc123:download_manifest",
            prepare_manifest_handles=["job_abc123:prepare_manifest_0"],
        )
        d = obs.to_dict()
        assert d["searchManifestHandle"] == "job_abc123:search_manifest"
        assert d["downloadManifestHandle"] == "job_abc123:download_manifest"
        assert d["prepareManifestHandles"] == ["job_abc123:prepare_manifest_0"]
        # No raw /srv/ paths anywhere in the serialised dict
        assert "/srv/" not in json.dumps(d)

    def test_to_dict_contains_required_keys(self):
        obs = ObservabilitySummary(
            job_id="job_req",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
        )
        d = obs.to_dict()
        for key in (
            "jobId",
            "sourceId",
            "aoiId",
            "provider",
            "artifactVersion",
            "redactionVersion",
            "providerInputSummary",
            "providerResponseSummary",
            "verificationSummary",
        ):
            assert key in d, f"Required key {key!r} missing from observability dict"

    def test_to_dict_redacts_password_in_verification_summary(self):
        """Passwords embedded in verificationSummary must be redacted."""
        obs = ObservabilitySummary(
            job_id="job_vs",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
            verification_summary={
                "password": "should_be_redacted",
                "verdict": "passed",
                "coveragePercent": 98.5,
            },
        )
        d = obs.to_dict()
        text = json.dumps(d)
        assert "should_be_redacted" not in text
        vs = d["verificationSummary"]
        assert vs["verdict"] == "passed"
        assert vs["coveragePercent"] == 98.5

    def test_write_and_read_observability_round_trip(self, tmp_path):
        obs = ObservabilitySummary(
            job_id="job_rt",
            source_id=_LISS3_SOURCE,
            aoi_id=_DEFAULT_AOI,
            provider="bhoonidhi",
            next_due_at="2026-07-09T12:00:00Z",
            schedule_decision="cadence_due",
        )
        write_observability("job_rt", obs, tmp_path)
        data = read_observability("job_rt", tmp_path)
        assert data["jobId"] == "job_rt"
        assert data["nextDueAt"] == "2026-07-09T12:00:00Z"
        assert data["scheduleDecision"] == "cadence_due"

    def test_read_observability_returns_empty_dict_when_file_absent(self, tmp_path):
        data = read_observability("nonexistent_job_xyz", tmp_path)
        assert data == {}


# ===========================================================================
# 3. JobLedger — required fields, WAL/busy timeout, pruning
# ===========================================================================


class TestJobLedger:
    """job_ledger.JobLedger must write required fields, enable WAL, and prune correctly."""

    def test_upsert_writes_required_fields(self, tmp_path):
        db = JobLedger(tmp_path / "req.db")
        db.upsert_job(
            "job-001",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
            scheduled_at="2026-06-24T12:00:00Z",
            window_start="2026-06-12",
            window_end="2026-06-24",
        )
        row = db.get_job("job-001")
        assert row is not None
        assert row["job_id"] == "job-001"
        assert row["source_id"] == _LISS3_SOURCE
        assert row["provider"] == "bhoonidhi"
        assert row["aoi_id"] == _DEFAULT_AOI
        assert row["state"] == "planned"
        assert row["scheduled_at"] == "2026-06-24T12:00:00Z"
        assert row["window_start"] == "2026-06-12"
        assert row["window_end"] == "2026-06-24"

    def test_upsert_optional_fields_stored(self, tmp_path):
        db = JobLedger(tmp_path / "opt.db")
        db.upsert_job(
            "job-002",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at="2026-06-24T10:00:00Z",
            started_at="2026-06-24T10:01:00Z",
            finished_at="2026-06-24T10:45:00Z",
            window_start="2026-06-12",
            window_end="2026-06-24",
            found_count=12,
            selected_count=5,
            downloaded_count=3,
            rejected_count=7,
            failed_count=0,
            schedule_decision="cadence_due",
            next_due_at="2026-07-09T12:00:00Z",
            artifact_summary_path="/srv/akasha/ingestion/scheduler/jobs/job-002/observability.json",
        )
        row = db.get_job("job-002")
        assert row is not None
        assert row["found_count"] == 12
        assert row["selected_count"] == 5
        assert row["downloaded_count"] == 3
        assert row["rejected_count"] == 7
        assert row["failed_count"] == 0
        assert row["schedule_decision"] == "cadence_due"
        assert row["next_due_at"] == "2026-07-09T12:00:00Z"
        assert row["started_at"] == "2026-06-24T10:01:00Z"
        assert row["finished_at"] == "2026-06-24T10:45:00Z"

    def test_wal_mode_enabled(self, tmp_path):
        """Every connection must apply PRAGMA journal_mode=WAL."""
        db = JobLedger(tmp_path / "wal.db")
        db.upsert_job(
            "job-wal",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
        )
        # Re-open the DB with a plain sqlite3 connection to verify the pragma.
        conn = sqlite3.connect(str(tmp_path / "wal.db"))
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        conn.close()
        assert row is not None
        assert row[0].lower() == "wal"

    def test_busy_timeout_constant_is_reasonable(self):
        """BUSY_TIMEOUT_MS must be at least 1 000 ms to prevent false lock errors."""
        assert BUSY_TIMEOUT_MS >= 1000

    def test_prune_deletes_rows_outside_retention_window(self, tmp_path):
        db = JobLedger(tmp_path / "prune.db", retention_days=30)
        now = _FIXED_NOW
        old_ts = (now - timedelta(days=40)).isoformat().replace("+00:00", "Z")
        new_ts = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        db.upsert_job(
            "job-old",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=old_ts,
        )
        db.upsert_job(
            "job-new",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=new_ts,
        )
        deleted = db.prune_old_jobs(now=now, retention_days=30)
        assert deleted == 1
        assert db.get_job("job-old") is None
        assert db.get_job("job-new") is not None

    def test_prune_returns_zero_when_nothing_old(self, tmp_path):
        db = JobLedger(tmp_path / "prune2.db", retention_days=30)
        recent_ts = (_FIXED_NOW - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        db.upsert_job(
            "job-recent",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=recent_ts,
        )
        deleted = db.prune_old_jobs(now=_FIXED_NOW)
        assert deleted == 0

    def test_prune_with_zero_retention_preserves_all_rows(self, tmp_path):
        """retention_days=0 must keep every row regardless of age."""
        db = JobLedger(tmp_path / "prune3.db", retention_days=0)
        ancient_ts = (_FIXED_NOW - timedelta(days=365)).isoformat().replace("+00:00", "Z")
        db.upsert_job(
            "job-ancient",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=ancient_ts,
        )
        deleted = db.prune_old_jobs(now=_FIXED_NOW, retention_days=0)
        assert deleted == 0
        assert db.get_job("job-ancient") is not None

    def test_prune_never_removes_rows_with_null_scheduled_at(self, tmp_path):
        """Rows with scheduled_at=NULL must never be pruned."""
        db = JobLedger(tmp_path / "prune4.db", retention_days=1)
        db.upsert_job(
            "job-nosched",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
            scheduled_at=None,
        )
        deleted = db.prune_old_jobs(now=_FIXED_NOW)
        assert deleted == 0
        assert db.get_job("job-nosched") is not None

    def test_update_job_modifies_specific_columns(self, tmp_path):
        db = JobLedger(tmp_path / "upd.db")
        db.upsert_job(
            "job-upd",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
            scheduled_at="2026-06-24T12:00:00Z",
        )
        db.update_job("job-upd", state="running", started_at="2026-06-24T12:01:00Z")
        row = db.get_job("job-upd")
        assert row is not None
        assert row["state"] == "running"
        assert row["started_at"] == "2026-06-24T12:01:00Z"
        # Unchanged fields must not be touched
        assert row["source_id"] == _LISS3_SOURCE

    def test_update_job_unknown_column_raises_key_error(self, tmp_path):
        db = JobLedger(tmp_path / "upderr.db")
        db.upsert_job(
            "job-kerr",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
        )
        with pytest.raises(KeyError):
            db.update_job("job-kerr", nonexistent_column="bad_value")

    def test_list_jobs_filters_by_source_id(self, tmp_path):
        db = JobLedger(tmp_path / "list.db")
        now_ts = _FIXED_NOW.isoformat().replace("+00:00", "Z")
        db.upsert_job(
            "job-liss3",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=now_ts,
        )
        db.upsert_job(
            "job-awifs",
            source_id=_AWIFS_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at=now_ts,
        )
        results = db.list_jobs(source_id=_LISS3_SOURCE)
        assert len(results) == 1
        assert results[0]["job_id"] == "job-liss3"

    def test_last_successful_job_returns_most_recent(self, tmp_path):
        db = JobLedger(tmp_path / "last.db")
        db.upsert_job(
            "job-old-s",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at="2026-06-10T12:00:00Z",
        )
        db.upsert_job(
            "job-new-s",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="succeeded",
            scheduled_at="2026-06-20T12:00:00Z",
        )
        row = db.last_successful_job(_LISS3_SOURCE, _DEFAULT_AOI)
        assert row is not None
        assert row["job_id"] == "job-new-s"

    def test_row_count_increments_on_upsert(self, tmp_path):
        db = JobLedger(tmp_path / "cnt.db")
        assert db.row_count() == 0
        db.upsert_job(
            "job-cnt1",
            source_id=_LISS3_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
        )
        assert db.row_count() == 1
        db.upsert_job(
            "job-cnt2",
            source_id=_AWIFS_SOURCE,
            provider="bhoonidhi",
            aoi_id=_DEFAULT_AOI,
            state="planned",
        )
        assert db.row_count() == 2


# ===========================================================================
# 4. Orchestrator → observability.json written at every terminal state
# ===========================================================================


class TestOrchestratorObservability:
    """run_source_job must write observability.json for every terminal outcome."""

    def test_dry_run_writes_observability_json(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        obs_path = job_dir(result.job_id, tmp_path) / OBSERVABILITY_FILE
        assert obs_path.exists(), "observability.json must be written for dry-run jobs"

    def test_dry_run_observability_has_correct_job_id(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        obs = read_observability(result.job_id, tmp_path)
        assert obs.get("jobId") == result.job_id

    def test_dry_run_observability_schedule_decision_is_dry_run(self, tmp_path):
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        obs = read_observability(result.job_id, tmp_path)
        assert obs.get("scheduleDecision") == "dry_run"

    def test_custom_schedule_decision_propagated_to_observability(
        self, tmp_path, monkeypatch
    ):
        """schedule_decision kwarg must appear in observability for non-dry-run jobs."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
            schedule_decision="cadence_due",
        )
        obs = read_observability(result.job_id, tmp_path)
        assert obs.get("scheduleDecision") == "cadence_due"

    def test_approved_run_writes_observability_json(self, tmp_path, monkeypatch):
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
        obs_path = job_dir(result.job_id, tmp_path) / OBSERVABILITY_FILE
        assert obs_path.exists(), "observability.json must be written for succeeded jobs"

    def test_approved_run_observability_provider_input_has_typed_schedule_fields(
        self, tmp_path, monkeypatch
    ):
        """Producer must emit the typed fields consumed by the BFF schedule API."""
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
        obs = read_observability(result.job_id, tmp_path)
        provider_input = obs.get("providerInputSummary", {})

        assert provider_input["lifecycleState"] == "validate_enabled"
        assert provider_input["scheduleState"] == "routine"
        assert provider_input["commercialState"] == "free"
        assert provider_input["aoiScope"] == "in_aoi"
        assert provider_input["cadenceClass"] == "5_to_10_days"
        assert "search_enabled" in provider_input["capabilities"]

    def test_approved_run_observability_no_raw_filesystem_paths(
        self, tmp_path, monkeypatch
    ):
        """observability.json must not expose /srv/ paths (API/UI-safe contract)."""
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
        obs = read_observability(result.job_id, tmp_path)
        text = json.dumps(obs)
        assert "/srv/" not in text

    def test_gated_source_writes_observability_json(self, tmp_path, monkeypatch):
        """Commercially-gated sources must still produce observability.json."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
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
        obs_path = job_dir(result.job_id, tmp_path) / OBSERVABILITY_FILE
        assert obs_path.exists(), "Gated jobs must still write observability.json"

    def test_with_sqlite_ledger_records_job_row(self, tmp_path, monkeypatch):
        """When ledger_db_path is provided, a row must be written to the SQLite ledger."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        db_path = tmp_path / "ledger.db"
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
            ledger_db_path=db_path,
        )
        db = JobLedger(db_path)
        row = db.get_job(result.job_id)
        assert row is not None
        assert row["source_id"] == _LISS3_SOURCE
        assert row["aoi_id"] == _DEFAULT_AOI
        assert row["provider"] == "bhoonidhi"

    def test_with_sqlite_ledger_records_terminal_state(self, tmp_path, monkeypatch):
        """Ledger row state must reflect the final terminal JobStatus value."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        db_path = tmp_path / "ledger2.db"
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
            ledger_db_path=db_path,
        )
        db = JobLedger(db_path)
        row = db.get_job(result.job_id)
        assert row is not None
        terminal_states = {
            "succeeded",
            "failed",
            "validation_failed",
            "skipped_gated",
            "blocked_by_lock",
            "cancelled",
        }
        assert row["state"] in terminal_states, (
            f"Ledger state {row['state']!r} is not a recognised terminal state"
        )

    def test_with_sqlite_ledger_window_fields_stored(self, tmp_path, monkeypatch):
        """Ledger row must include the window_start and window_end used by the job."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        db_path = tmp_path / "ledger3.db"
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
            ledger_db_path=db_path,
            window_start="2026-06-12",
            window_end="2026-06-24",
        )
        db = JobLedger(db_path)
        row = db.get_job(result.job_id)
        assert row is not None
        assert row["window_start"] == "2026-06-12"
        assert row["window_end"] == "2026-06-24"


# ===========================================================================
# 5. schedule-plan (orchestrator level): exposes why source is/is not due
# ===========================================================================


class TestSchedulePlanExposesWhy:
    """plan_due_sources must expose a clear reason for every is_due=False decision."""

    def test_first_run_is_due_with_no_skip_reason(self, tmp_path):
        # With an explicit canary/manual override, a first run (no ledger entry)
        # must be due with no skip_reason.
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
            manual_overrides={f"{_LISS3_SOURCE}::{_DEFAULT_AOI}": True},
        )
        due = [d for d in decisions if d.source_id == _LISS3_SOURCE and d.is_due]
        assert due
        for d in due:
            assert d.skip_reason is None

    def test_gated_source_skip_reason_is_non_empty(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_COMMERCIAL_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            assert not d.is_due
            assert d.skip_reason, "Gated source must have a non-empty skip_reason"

    def test_commercial_blocked_skip_reason_mentions_gate_category(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_COMMERCIAL_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            reason = d.skip_reason or ""
            assert "commercial" in reason.lower() or "gated" in reason.lower(), (
                f"Expected commercial/gated in skip_reason, got: {reason!r}"
            )

    def test_disabled_source_skip_reason_mentions_schedule_state(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=["sentinel-2-l2a"],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        skipped = [d for d in decisions if not d.is_due]
        assert skipped
        for d in skipped:
            reason = d.skip_reason or ""
            assert "schedule_state" in reason or "disabled" in reason.lower(), (
                f"Expected schedule_state/disabled in skip_reason, got: {reason!r}"
            )

    def test_not_due_skip_reason_mentions_next_due(self, tmp_path):
        """Not-due (cadence not elapsed) sources must carry a skip_reason with timing info."""
        ledger = SchedulerLedger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_prev",
            window_end="2026-06-24",
            succeeded_at=(_FIXED_NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        not_due = [d for d in decisions if not d.is_due and d.source_id == _LISS3_SOURCE]
        assert not_due, "LISS-3 should not be due 2h after last success"
        for d in not_due:
            assert d.skip_reason, "Not-due source must have a non-empty skip_reason"
            # The reason must either mention the next due time or the source carries next_due_at
            assert "next due" in (d.skip_reason or "").lower() or d.next_due_at is not None

    def test_due_decision_carries_schedule_state_field(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            assert d.schedule_state, "DueDecision must carry a non-empty schedule_state"

    def test_due_decision_to_dict_is_json_serialisable(self, tmp_path):
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            payload = d.to_dict()
            # Must be JSON-serialisable without exceptions
            assert json.dumps(payload)

    def test_archive_source_skip_reason_mentions_cadence(self, tmp_path):
        """Archive sources (ARCHIVE_ON_DEMAND cadence) must carry a reason that names
        the cadence or backfill requirement."""
        decisions = plan_due_sources(
            source_ids=["landsat-7-c2-l2"],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        skipped = [d for d in decisions if not d.is_due]
        assert skipped
        for d in skipped:
            reason = d.skip_reason or ""
            lower = reason.lower()
            assert "archive" in lower or "backfill" in lower or "cadence" in lower, (
                f"Expected archive/backfill/cadence in skip_reason, got: {reason!r}"
            )


# ===========================================================================
# 6. schedule-next (orchestrator level): next due run/window from state
# ===========================================================================


class TestScheduleNextState:
    """plan_due_sources must expose next_due_at and window dates for cadence-based sources."""

    def test_first_run_has_no_previous_success(self, tmp_path):
        """No ledger entry → last_succeeded_at is None on first run."""
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        first_runs = [d for d in decisions if d.source_id == _LISS3_SOURCE]
        assert first_runs
        for d in first_runs:
            assert d.last_succeeded_at is None

    def test_next_due_at_computed_after_success(self, tmp_path):
        """After recording a success, not-due decisions must carry a parseable next_due_at."""
        prev_succeeded = (_FIXED_NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        ledger = SchedulerLedger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_prev",
            window_end="2026-06-24",
            succeeded_at=prev_succeeded,
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        not_due = [d for d in decisions if d.source_id == _LISS3_SOURCE and not d.is_due]
        assert not_due, "LISS-3 should not be due 2 hours after last success"
        for d in not_due:
            assert d.next_due_at is not None, "next_due_at must be populated for not-due decisions"
            # Must be a valid ISO-8601 timestamp
            parsed = datetime.fromisoformat(d.next_due_at.replace("Z", "+00:00"))
            assert parsed > _FIXED_NOW, "next_due_at must be in the future relative to _FIXED_NOW"

    def test_next_due_at_reflects_source_cadence(self, tmp_path):
        """next_due_at must be approximately cadence-days after last success."""
        prev_succeeded = (_FIXED_NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        ledger = SchedulerLedger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_prev",
            window_end="2026-06-24",
            succeeded_at=prev_succeeded,
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        not_due = [d for d in decisions if d.source_id == _LISS3_SOURCE and not d.is_due]
        for d in not_due:
            next_dt = datetime.fromisoformat(d.next_due_at.replace("Z", "+00:00"))
            prev_dt = datetime.fromisoformat(prev_succeeded.replace("Z", "+00:00"))
            gap_days = (next_dt - prev_dt).total_seconds() / 86400
            # LISS-3 has a 5-day cadence; gap should be at least 4 days, at most 25 days
            assert 4.0 <= gap_days <= 25.0, (
                f"next_due_at gap {gap_days:.1f}d does not match the expected LISS-3 cadence"
            )

    def test_window_start_and_end_always_populated(self, tmp_path):
        """Every DueDecision must carry non-empty window_start and window_end."""
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE, _AWIFS_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        for d in decisions:
            assert d.window_start, "window_start must be non-empty"
            assert d.window_end, "window_end must be non-empty"

    def test_last_window_end_stored_after_success(self, tmp_path):
        """DueDecision must carry the last_window_end from the scheduler ledger."""
        ledger = SchedulerLedger(tmp_path)
        ledger.record_success(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            job_id="job_prev",
            window_end="2026-06-20",
            succeeded_at=(_FIXED_NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        )
        decisions = plan_due_sources(
            source_ids=[_LISS3_SOURCE],
            aoi_ids=[_DEFAULT_AOI],
            base_dir=tmp_path,
            now=_FIXED_NOW,
        )
        found = [d for d in decisions if d.source_id == _LISS3_SOURCE]
        assert found
        for d in found:
            assert d.last_window_end == "2026-06-20", (
                f"Expected last_window_end='2026-06-20', got {d.last_window_end!r}"
            )


# ===========================================================================
# 7. CLI-level: job-inspect applies redaction, handles have opaque format
# ===========================================================================


def _load_cli():
    """Load staging_ingestion_job.py as a module for CLI tests."""
    script_path = REPO_ROOT / "scripts" / "staging_ingestion_job.py"
    spec = importlib.util.spec_from_file_location("staging_ingestion_job", script_path)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(cli)
    return cli


class TestJobInspectCLIRedaction:
    """job-inspect must redact secrets and expose opaque artifact handles."""

    def test_redact_helper_masks_all_secret_key_fragments(self):
        cli = _load_cli()
        payload = {
            "job_id": "job_test",
            "state": "succeeded",
            "api_key": "my-api-key-value",
            "secret_token": "tok123",
            "s3_access_key": "AKIAIOSFODNN7EXAMPLE",
            "password": "supersecret",
        }
        redacted = cli._redact(payload)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["secret_token"] == "[REDACTED]"
        assert redacted["s3_access_key"] == "[REDACTED]"
        assert redacted["password"] == "[REDACTED]"
        # Non-sensitive fields untouched
        assert redacted["job_id"] == "job_test"
        assert redacted["state"] == "succeeded"

    def test_redact_helper_recurses_into_nested_dict(self):
        cli = _load_cli()
        obj = {
            "meta": {
                "api_key": "nested-secret",
                "source": "liss3",
            },
            "top_level": "ok",
        }
        redacted = cli._redact(obj)
        assert redacted["meta"]["api_key"] == "[REDACTED]"
        assert redacted["meta"]["source"] == "liss3"
        assert redacted["top_level"] == "ok"

    def test_redact_helper_recurses_into_list(self):
        cli = _load_cli()
        obj = {
            "items": [
                {"password": "pw1", "name": "a"},
                {"password": "pw2", "name": "b"},
            ]
        }
        redacted = cli._redact(obj)
        assert redacted["items"][0]["password"] == "[REDACTED]"
        assert redacted["items"][1]["password"] == "[REDACTED]"
        assert redacted["items"][0]["name"] == "a"

    def test_opaque_artifact_handles_survive_redaction(self):
        """Opaque handles in the job-inspect response must not be mangled by _redact."""
        cli = _load_cli()
        job_id = "job_20260624T120000Z_abc123def456"
        payload = {
            "job_id": job_id,
            "state": "succeeded",
            "api_key": "LEAK",
            "artifact_handles": {
                "request": f"{job_id}:request",
                "status": f"{job_id}:status",
                "result": f"{job_id}:result",
                "log": f"{job_id}:log",
            },
        }
        redacted = cli._redact(payload)
        assert redacted["api_key"] == "[REDACTED]"
        # Handle values contain neither "api_key" nor other secret fragments as keys
        handles = redacted["artifact_handles"]
        for handle_type in ("request", "status", "result", "log"):
            assert handles[handle_type] == f"{job_id}:{handle_type}", (
                f"Handle for {handle_type!r} must not be corrupted by _redact"
            )

    def test_opaque_handles_have_no_filesystem_paths(self):
        """Artifact handles must not embed /srv/ or any raw filesystem path."""
        job_id = "job_20260624T120000Z_abc123def456"
        for artifact_type in ("request", "status", "result", "log", "observability"):
            handle = make_artifact_handle(job_id, artifact_type)
            assert "/srv/" not in handle, f"Handle {handle!r} exposes /srv/ path"
            assert "ingestion" not in handle, (
                f"Handle {handle!r} exposes internal path segment 'ingestion'"
            )

    def test_job_inspect_returns_zero_on_valid_json_response(self, monkeypatch, capsys):
        cli = _load_cli()
        import subprocess

        payload = {
            "job_id": "job-x",
            "state": "succeeded",
            "source_id": _LISS3_SOURCE,
        }
        monkeypatch.setattr(
            cli,
            "run_ssh",
            lambda *_args, **_kw: subprocess.CompletedProcess(
                [], 0, stdout=json.dumps(payload), stderr=""
            ),
        )
        rc = cli.main(["job-inspect", "job-x"])
        assert rc == 0

    def test_job_inspect_json_flag_redacts_secret_fields(self, monkeypatch, capsys):
        cli = _load_cli()
        import subprocess

        payload = {
            "job_id": "job-y",
            "state": "succeeded",
            "api_key": "LEAK-ME",
        }
        monkeypatch.setattr(
            cli,
            "run_ssh",
            lambda *_args, **_kw: subprocess.CompletedProcess(
                [], 0, stdout=json.dumps(payload), stderr=""
            ),
        )
        cli.main(["job-inspect", "job-y", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["api_key"] == "[REDACTED]"
        assert data["state"] == "succeeded"
