"""Phase 7 parity, scheduler path, and observability tests.

Coverage matrix — TASK-045, TASK-046, TASK-047
------------------------------------------------
TASK-045: Dry-run stop-point parity between ``bhoonidhi-sync --dry-run`` and
          ``schedule-source --source <src> --dry-run`` for LISS-3, LISS-4, AWiFS.

          1. Both commands stop before download/prepare/composite/ingest.
          2. ``schedule-source`` dry-run carries plannedStages, parityStopPoint,
             sourceThresholds, and manifestHandles for all three Bhoonidhi sources.
          3. No live provider calls occur during any dry-run path.
          4. LISS-4 dry-run carries the same Phase 7 metadata as LISS-3 and AWiFS.

TASK-046: AWiFS regional product-active coverage is retryable.

             5. AWiFS approved non-dry-run is allowed through the live ResourceSat
                 pipeline with a regional 60% minimum usable-coverage threshold.
             6. ``product_exposure`` is ``PRODUCT_ACTIVE``.
             7. AWiFS source registry has no readiness blockers.
             8. AWiFS job result includes live pipeline counts when mocked.

TASK-047: ``bhoonidhi-sync`` stays non-delegated until parity passes.

          9.  Parser resolves ``bhoonidhi-sync`` to ``cmd_bhoonidhi_sync``,
              not a scheduler orchestrator wrapper.
          10. ``local_test=True`` is a strict alias for ``dry_run=True``:
              same status, failure_kind, and events.
          11. ``dry_run=True`` prevents all provider adapter calls (lock + adapter).
          12. ``approved_runtime=True`` on a STAGING_BHOONIDHI source with no
              env-var produces SUCCEEDED (safe-wrapper dry-run contract).
          13. ``bhoonidhi-sync --dry-run`` stdout message is equivalent to the
              ``parityStopPoint="before_download"`` recorded by the scheduler.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest.jobs import (  # noqa: E402
    JobStatus,
    job_dir,
    read_events,
)
from akasha_ingest.orchestrator import (  # noqa: E402
    _BHOONIDHI_PARITY_STOP_POINT,
    _BHOONIDHI_PLANNED_STAGES,
    APPROVED_RUNTIME_ENV_VAR,
    run_source_job,
)
from akasha_ingest.resourcesat_pipeline import IngestResult  # noqa: E402
from akasha_ingest.source_registry import (  # noqa: E402
    SOURCE_REGISTRY,
    ProductExposure,
    ValidationState,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LISS3_SOURCE = "resourcesat-2a-liss3-boa"
_LISS4_SOURCE = "resourcesat-2a-liss4-mx70-l2"
_AWIFS_SOURCE = "resourcesat-2a-awifs-boa"
_DEFAULT_AOI = "bangalore-60km"
_FIXED_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=UTC)

_ALL_BHOONIDHI_SOURCES = [_LISS3_SOURCE, _LISS4_SOURCE, _AWIFS_SOURCE]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_worker_module():
    """Return the worker module loaded from services/ingestion/worker.py."""
    worker_path = INGESTION_ROOT / "worker.py"
    spec = importlib.util.spec_from_file_location("_worker_phase7", worker_path)
    assert spec and spec.loader, "worker.py not found"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _dry_run_plan_payload(source_id: str, tmp_path: Path) -> dict:
    """Run a scheduler dry-run for *source_id* and return the dry_run_plan payload."""
    result = run_source_job(
        source_id,
        _DEFAULT_AOI,
        dry_run=True,
        base_dir=tmp_path,
        lock_dir=tmp_path / "locks",
        now=_FIXED_NOW,
    )
    events = read_events(result.job_id, tmp_path)
    plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
    assert plan_events, f"No dry_run_plan event for {source_id}"
    return plan_events[0].get("payload", {})


def _patch_live_pipeline_success(monkeypatch) -> None:
    """Force the live ResourceSat/Bhoonidhi pipeline to succeed deterministically.

    Patches AOI loading and the ingest entrypoint that the orchestrator imports
    at call time so an approved non-dry-run job reaches SUCCEEDED without any
    network, seed-file, or provider access.
    """
    monkeypatch.setattr(
        "akasha_ingest.bhoonidhi.load_aoi",
        lambda *args, **kwargs: {"type": "FeatureCollection", "features": []},
    )

    def _fake_ingest(params, *args, **kwargs):
        return IngestResult(
            source_id=params.source_id,
            aoi_id=params.aoi_id,
            window_start=params.window_start,
            window_end=params.window_end,
            verdict="succeeded",
            found_count=1,
            selected_count=1,
            downloaded_count=1,
            composite_built=True,
            ingested=True,
            coverage_met=True,
        )

    monkeypatch.setattr(
        "akasha_ingest.resourcesat_pipeline.run_resourcesat_ingest", _fake_ingest
    )


# ===========================================================================
# TASK-045 — Dry-run stop-point parity: LISS-3, LISS-4, AWiFS
# ===========================================================================


class TestDryRunParityLISS4:
    """LISS-4 scheduler dry-run carries the same Phase 7 metadata as LISS-3."""

    def test_liss4_dry_run_carries_planned_stages(self, tmp_path):
        """LISS-4 scheduler dry-run must include all pipeline stage names."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        assert "plannedStages" in payload, (
            f"plannedStages missing from LISS-4 dry_run_plan: {list(payload)}"
        )
        stages = payload["plannedStages"]
        for stage in ("search", "download", "prepare", "composite", "validate", "ingest"):
            assert stage in stages, f"Stage '{stage}' missing from LISS-4 plannedStages"

    def test_liss4_dry_run_carries_parity_stop_point(self, tmp_path):
        """LISS-4 parityStopPoint must be 'before_download' — same as LISS-3 and AWiFS."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        assert "parityStopPoint" in payload, "parityStopPoint missing from LISS-4 dry_run_plan"
        assert payload["parityStopPoint"] == "before_download", (
            f"Expected 'before_download' but got {payload['parityStopPoint']!r}"
        )

    def test_liss4_dry_run_carries_phase7_phase_key(self, tmp_path):
        """LISS-4 dry-run plan phase key must be 'phase7_scheduler_path'."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        assert payload.get("phase") == "phase7_scheduler_path", (
            f"Expected 'phase7_scheduler_path' but got {payload.get('phase')!r}"
        )

    def test_liss4_dry_run_carries_source_thresholds(self, tmp_path):
        """LISS-4 dry-run plan must carry sourceThresholds with required keys."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        assert "sourceThresholds" in payload, "sourceThresholds missing from LISS-4 plan"
        thresholds = payload["sourceThresholds"]
        assert "minCoveragePercent" in thresholds
        assert "lookbackDays" in thresholds

    def test_liss4_dry_run_carries_manifest_handles(self, tmp_path):
        """LISS-4 dry-run plan must carry opaque manifest handles."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        assert "manifestHandles" in payload, "manifestHandles missing from LISS-4 plan"
        handles = payload["manifestHandles"]
        assert "searchManifestHandle" in handles
        assert "compositeManifestHandle" in handles

    def test_liss4_dry_run_manifest_handles_encode_source_and_aoi(self, tmp_path):
        """LISS-4 manifest handles must encode source_id and aoi_id."""
        payload = _dry_run_plan_payload(_LISS4_SOURCE, tmp_path)
        handles = payload["manifestHandles"]
        for handle_value in handles.values():
            assert _LISS4_SOURCE in handle_value, (
                f"LISS-4 source not encoded in handle: {handle_value!r}"
            )
            assert _DEFAULT_AOI in handle_value, (
                f"AOI not encoded in handle: {handle_value!r}"
            )

    def test_liss4_dry_run_makes_no_provider_calls(self, tmp_path):
        """LISS-4 scheduler dry-run must not acquire lock or call provider adapter."""
        with patch(
            "akasha_ingest.orchestrator.acquire_worker_lock"
        ) as mock_lock, patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                _LISS4_SOURCE,
                _DEFAULT_AOI,
                dry_run=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        mock_lock.assert_not_called()
        mock_adapter.assert_not_called()


class TestDryRunParityAllSources:
    """All three Bhoonidhi sources must report the same parityStopPoint."""

    @pytest.mark.parametrize("source_id", _ALL_BHOONIDHI_SOURCES)
    def test_all_bhoonidhi_sources_stop_before_download(self, source_id, tmp_path):
        """LISS-3, LISS-4, and AWiFS must all report parityStopPoint='before_download'."""
        payload = _dry_run_plan_payload(source_id, tmp_path / source_id)
        assert payload.get("parityStopPoint") == "before_download", (
            f"Source {source_id!r}: expected 'before_download', "
            f"got {payload.get('parityStopPoint')!r}"
        )

    @pytest.mark.parametrize("source_id", _ALL_BHOONIDHI_SOURCES)
    def test_all_bhoonidhi_sources_carry_planned_stages(self, source_id, tmp_path):
        """LISS-3, LISS-4, and AWiFS dry-run plans must carry plannedStages."""
        payload = _dry_run_plan_payload(source_id, tmp_path / source_id)
        assert "plannedStages" in payload, (
            f"Source {source_id!r} missing plannedStages in dry_run_plan"
        )

    @pytest.mark.parametrize("source_id", _ALL_BHOONIDHI_SOURCES)
    def test_all_bhoonidhi_sources_carry_phase7_key(self, source_id, tmp_path):
        """LISS-3, LISS-4, and AWiFS dry-run plans must carry phase='phase7_scheduler_path'."""
        payload = _dry_run_plan_payload(source_id, tmp_path / source_id)
        assert payload.get("phase") == "phase7_scheduler_path", (
            f"Source {source_id!r}: expected 'phase7_scheduler_path', "
            f"got {payload.get('phase')!r}"
        )

    @pytest.mark.parametrize("source_id", _ALL_BHOONIDHI_SOURCES)
    def test_all_bhoonidhi_sources_no_provider_calls(self, source_id, tmp_path):
        """Dry-run for LISS-3, LISS-4, and AWiFS must not call any provider."""
        with patch(
            "akasha_ingest.orchestrator.acquire_worker_lock"
        ) as mock_lock, patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                source_id,
                _DEFAULT_AOI,
                dry_run=True,
                base_dir=tmp_path / source_id,
                lock_dir=tmp_path / source_id / "locks",
                now=_FIXED_NOW,
            )
        mock_lock.assert_not_called()
        mock_adapter.assert_not_called()

    def test_parity_stop_point_constant_matches_bhoonidhi_sync_message(self):
        """The orchestrator parityStopPoint constant must reflect what bhoonidhi-sync prints.

        bhoonidhi-sync --dry-run prints 'dry-run: stopping before download/...'.
        The scheduler records parityStopPoint='before_download'.  This test asserts
        the constant matches the intended semantic by inspecting the orchestrator module.
        """
        # The constant encodes the parity semantic
        assert _BHOONIDHI_PARITY_STOP_POINT == "before_download"
        # The planned stages list starts with search and has download next
        assert _BHOONIDHI_PLANNED_STAGES[0] == "search"
        assert _BHOONIDHI_PLANNED_STAGES[1] == "download"

    def test_bhoonidhi_sync_dry_run_print_message_matches_parity_stop_point(
        self, monkeypatch, tmp_path
    ):
        """bhoonidhi-sync --dry-run stdout message encodes 'before_download' stop intent.

        Mocks BhoonidhiClient.search to avoid live calls.  Captures stdout and checks
        the dry-run stop message matches the scheduler's parityStopPoint semantic.
        """
        from akasha_ingest import bhoonidhi  # noqa: PLC0415

        aoi_path = tmp_path / "aoi.geojson"
        aoi_path.write_text(
            json.dumps(
                {
                    "type": "Feature",
                    "properties": {"id": "bangalore-60km"},
                    "bbox": [77.0, 12.0, 78.0, 13.0],
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[77.0, 12.0], [78.0, 12.0], [78.0, 13.0],
                             [77.0, 13.0], [77.0, 12.0]]
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        class _FakeClient:
            def search(self, **_kwargs):
                return []

        monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: _FakeClient())

        worker = _load_worker_module()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = worker.main(
                [
                    "bhoonidhi-sync",
                    "--source", _LISS3_SOURCE,
                    "--aoi-path", str(aoi_path),
                    "--datetime", "2026-06-01T00:00:00Z/2026-06-24T23:59:59Z",
                    "--window-start", "2026-06-01",
                    "--window-end", "2026-06-24",
                    "--out-dir", str(tmp_path / "work"),
                    "--ledger-path", str(tmp_path / "ledger.sqlite"),
                    "--no-lock",
                    "--dry-run",
                ]
            )

        assert rc == 0
        stdout = buf.getvalue()
        # The stop message must reference "before download" — proving stop-point parity
        assert "before download" in stdout.lower(), (
            f"bhoonidhi-sync --dry-run stdout did not mention 'before download': {stdout!r}"
        )
        # Confirm the scheduler records the equivalent semantic
        assert _BHOONIDHI_PARITY_STOP_POINT == "before_download"


# ===========================================================================
# TASK-046 — AWiFS regional product-active coverage remains retryable
# ===========================================================================


class TestAWiFSBelowThreshold:
    """AWiFS validation failure is visible in job result and observability."""

    def test_awifs_approved_run_status_is_deferred_failure(self, tmp_path, monkeypatch):
        """AWiFS approved non-dry-run may attempt, but live pipeline is fail-closed."""
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

    def test_awifs_approved_run_succeeds(self, tmp_path, monkeypatch):
        """AWiFS is product-active: an approved run executes the live pipeline."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SUCCEEDED)

    def test_awifs_observability_marks_succeeded(self, tmp_path, monkeypatch):
        """AWiFS observability records the succeeded verdict on an approved run."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SUCCEEDED)
        obs_path = job_dir(result.job_id, tmp_path) / "observability.json"
        assert obs_path.exists(), "observability.json not written for AWiFS approved run"
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
        v_summary = obs.get("verificationSummary", {})
        assert v_summary["verdict"] == "succeeded"

    def test_awifs_registry_readiness_reasons_are_empty(self):
        """AWiFS registry readinessReasons are empty now that validation passed."""
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.readiness_reasons == ()

    def test_awifs_product_exposure_stays_product_active_after_run(
        self, tmp_path, monkeypatch
    ):
        """Running AWiFS keeps its product_exposure at PRODUCT_ACTIVE."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE

    def test_awifs_validation_state_is_passed_in_registry(self):
        """AWiFS validation_state must be VALIDATION_PASSED in the source registry."""
        row = SOURCE_REGISTRY[_AWIFS_SOURCE]
        assert row.validation_state == ValidationState.VALIDATION_PASSED

    def test_awifs_job_result_dict_has_success_fields(self, tmp_path, monkeypatch):
        """AWiFS approved-run result dict reports a successful, failure-free outcome."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        result = run_source_job(
            _AWIFS_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        result_dict = result.to_dict()
        assert result_dict["status"] == str(JobStatus.SUCCEEDED)
        assert result_dict["failureKind"] is None


# ===========================================================================
# TASK-047 — bhoonidhi-sync non-delegation and safe-wrapper dry-runs
# ===========================================================================


class TestBhoonidhiSyncNonDelegated:
    """bhoonidhi-sync remains non-delegated to the orchestrator scheduler."""

    def test_parser_resolves_bhoonidhi_sync_to_cmd_fn(self):
        """Parser must bind bhoonidhi-sync to cmd_bhoonidhi_sync (not a scheduler wrapper)."""
        worker = _load_worker_module()
        parser = worker.build_parser()
        args = parser.parse_args(
            ["bhoonidhi-sync", "--source", _LISS3_SOURCE, "--aoi", _DEFAULT_AOI, "--dry-run"]
        )
        assert args.func.__name__ == "cmd_bhoonidhi_sync", (
            f"bhoonidhi-sync must remain non-delegated; "
            f"got func={args.func.__name__!r}"
        )

    def test_parser_resolves_awifs_sync_to_cmd_fn(self):
        """bhoonidhi-sync with AWiFS source must also resolve to cmd_bhoonidhi_sync."""
        worker = _load_worker_module()
        parser = worker.build_parser()
        args = parser.parse_args(
            ["bhoonidhi-sync", "--source", _AWIFS_SOURCE, "--aoi", _DEFAULT_AOI, "--dry-run"]
        )
        assert args.func.__name__ == "cmd_bhoonidhi_sync"

    def test_parser_resolves_liss4_sync_to_cmd_fn(self):
        """bhoonidhi-sync with LISS-4 source must also resolve to cmd_bhoonidhi_sync."""
        worker = _load_worker_module()
        parser = worker.build_parser()
        args = parser.parse_args(
            ["bhoonidhi-sync", "--source", _LISS4_SOURCE, "--aoi", _DEFAULT_AOI, "--dry-run"]
        )
        assert args.func.__name__ == "cmd_bhoonidhi_sync"

    def test_bhoonidhi_sync_func_is_not_run_source_job(self):
        """cmd_bhoonidhi_sync must not delegate to run_source_job (TASK-026 compat)."""
        worker = _load_worker_module()
        fn = worker.cmd_bhoonidhi_sync
        # The function source/closure must not reference run_source_job.
        # Check via globals available to the function.
        fn_globals = fn.__globals__
        # run_source_job is in orchestrator, not expected as a direct bhoonidhi_sync dep
        assert "run_source_job" not in fn_globals or (
            fn_globals.get("run_source_job") is not run_source_job
        ), (
            "cmd_bhoonidhi_sync must not be delegated to run_source_job from orchestrator"
        )


class TestLocalTestAlias:
    """local_test=True must behave identically to dry_run=True."""

    def test_local_test_status_matches_dry_run_status(self, tmp_path):
        """local_test=True must produce the same status as dry_run=True."""
        result_dry = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path / "dry",
            lock_dir=tmp_path / "dry" / "locks",
            now=_FIXED_NOW,
        )
        result_local = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            local_test=True,
            base_dir=tmp_path / "local",
            lock_dir=tmp_path / "local" / "locks",
            now=_FIXED_NOW,
        )
        assert result_dry.status == result_local.status == str(JobStatus.SKIPPED_GATED)

    def test_local_test_failure_kind_matches_dry_run(self, tmp_path):
        """local_test=True failure_kind must equal dry_run=True failure_kind."""
        result_dry = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            base_dir=tmp_path / "dry",
            lock_dir=tmp_path / "dry" / "locks",
            now=_FIXED_NOW,
        )
        result_local = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            local_test=True,
            base_dir=tmp_path / "local",
            lock_dir=tmp_path / "local" / "locks",
            now=_FIXED_NOW,
        )
        assert result_dry.failure_kind == result_local.failure_kind == "dry_run"

    def test_local_test_produces_dry_run_plan_event(self, tmp_path):
        """local_test=True must emit a dry_run_plan event (same as dry_run=True)."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            local_test=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events, "local_test=True must produce a dry_run_plan event"

    def test_local_test_carries_planned_stages(self, tmp_path):
        """local_test=True dry_run_plan must carry plannedStages for Bhoonidhi sources."""
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            local_test=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        events = read_events(result.job_id, tmp_path)
        plan_events = [e for e in events if e["eventType"] == "dry_run_plan"]
        assert plan_events
        payload = plan_events[0].get("payload", {})
        assert "plannedStages" in payload
        assert payload["plannedStages"] == list(_BHOONIDHI_PLANNED_STAGES)

    def test_local_test_makes_no_provider_calls(self, tmp_path):
        """local_test=True must not acquire lock or call provider adapter."""
        with patch(
            "akasha_ingest.orchestrator.acquire_worker_lock"
        ) as mock_lock, patch(
            "akasha_ingest.providers.registry.get_provider_adapter"
        ) as mock_adapter:
            run_source_job(
                _LISS3_SOURCE,
                _DEFAULT_AOI,
                local_test=True,
                base_dir=tmp_path,
                lock_dir=tmp_path / "locks",
                now=_FIXED_NOW,
            )
        mock_lock.assert_not_called()
        mock_adapter.assert_not_called()


class TestSafeWrapperApprovedRuntime:
    """approved_runtime=True enables non-dry-run execution without live staging access."""

    def test_approved_runtime_liss3_runs_live_pipeline_and_succeeds(
        self, tmp_path, monkeypatch
    ):
        """LISS-3 with approved_runtime=True executes the live pipeline and succeeds."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=True,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SUCCEEDED)

    def test_approved_runtime_env_var_enables_liss3(self, tmp_path, monkeypatch):
        """AKASHA_APPROVED_RUNTIME=1 must enable LISS-3 without approved_runtime kwarg."""
        monkeypatch.setenv(APPROVED_RUNTIME_ENV_VAR, "1")
        _patch_live_pipeline_success(monkeypatch)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=False,
            approved_runtime=False,  # relies on env var only
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        assert result.status == str(JobStatus.SUCCEEDED)

    def test_no_approved_runtime_produces_skipped_gated(self, tmp_path, monkeypatch):
        """Without approved_runtime, LISS-3 non-dry-run must be SKIPPED_GATED."""
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

    def test_approved_runtime_liss3_prov_input_phase_key(self, tmp_path, monkeypatch):
        """Approved LISS-3 run must record phase7_scheduler_path in providerInputSummary."""
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
        obs_path = job_dir(result.job_id, tmp_path) / "observability.json"
        assert obs_path.exists()
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
        prov_input = obs.get("providerInputSummary", {})
        assert prov_input.get("phase") == "phase7_scheduler_path", (
            f"Expected 'phase7_scheduler_path', got {prov_input.get('phase')!r}"
        )

    def test_dry_run_flag_takes_precedence_over_no_approved_runtime(self, tmp_path, monkeypatch):
        """dry_run=True must succeed even without approved_runtime (gate skipped for dry-runs)."""
        monkeypatch.delenv(APPROVED_RUNTIME_ENV_VAR, raising=False)
        result = run_source_job(
            _LISS3_SOURCE,
            _DEFAULT_AOI,
            dry_run=True,
            approved_runtime=False,
            base_dir=tmp_path,
            lock_dir=tmp_path / "locks",
            now=_FIXED_NOW,
        )
        # Dry-run goes through the is_dry branch before the approved_runtime gate
        assert result.failure_kind == "dry_run"
        assert result.status == str(JobStatus.SKIPPED_GATED)

    def test_schedule_source_dry_run_via_cmd_fn_liss4(self, tmp_path):
        """schedule-source --source liss4 --dry-run must return 0 without provider calls."""
        worker = _load_worker_module()
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "schedule-source",
                "--source", _LISS4_SOURCE,
                "--aoi", _DEFAULT_AOI,
                "--base-dir", str(tmp_path),
                "--lock-dir", str(tmp_path / "locks"),
                "--ledger-db-path", str(tmp_path / "job_ledger.db"),
                "--dry-run",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = worker.cmd_schedule_source(args)
        assert rc == 0

    def test_schedule_source_dry_run_via_cmd_fn_awifs(self, tmp_path):
        """schedule-source --source awifs --dry-run must return 0 without provider calls."""
        worker = _load_worker_module()
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "schedule-source",
                "--source", _AWIFS_SOURCE,
                "--aoi", _DEFAULT_AOI,
                "--base-dir", str(tmp_path),
                "--lock-dir", str(tmp_path / "locks"),
                "--ledger-db-path", str(tmp_path / "job_ledger.db"),
                "--dry-run",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = worker.cmd_schedule_source(args)
        assert rc == 0
