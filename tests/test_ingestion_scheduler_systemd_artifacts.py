"""Tests for the ingestion-scheduler systemd artifacts (TASK-052).

Asserts that scheduler artifacts exist and preserve staging-safe behaviour without
executing real systemd commands. Mirrors test_bhoonidhi_systemd_artifacts.py in
structure and naming conventions.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "infra" / "selfhosted" / "systemd"

EXPECTED_FILES = {
    "timer": "akasha-ingestion-scheduler.timer",
    "service": "akasha-ingestion-scheduler.service",
    "wrapper": "akasha-ingestion-scheduler.sh",
    "env_example": "ingestion-scheduler.env.example",
    "installer": "install-akasha-ingestion-scheduler.sh",
}


def read_artifact(key: str) -> str:
    return (SYSTEMD_DIR / EXPECTED_FILES[key]).read_text()


# ── Artifact existence ────────────────────────────────────────────────────────


def test_scheduler_artifacts_all_exist():
    """All five scheduler artifacts must be present on disk."""
    for key, filename in EXPECTED_FILES.items():
        assert (SYSTEMD_DIR / filename).is_file(), (
            f"missing scheduler artifact '{key}': {filename}"
        )


# ── Timer unit ────────────────────────────────────────────────────────────────


def test_timer_cadence_is_safe_and_persistent():
    """Timer must run every few hours (not too frequently), set Persistent=true."""
    timer = read_artifact("timer")
    # Cadence: every 4 hours — conservative enough not to hammer the staging VM.
    assert "OnCalendar=*-*-* 00/4:00:00" in timer
    # RandomizedDelaySec reduces thundering-herd risk.
    assert "RandomizedDelaySec=" in timer
    # Persistent=true ensures missed runs are caught up after VM restarts.
    assert "Persistent=true" in timer


def test_timer_references_correct_service_unit():
    timer = read_artifact("timer")
    assert "Unit=akasha-ingestion-scheduler.service" in timer


def test_timer_install_section_wants_timers_target():
    """Timer must be in [Install] section referencing timers.target."""
    timer = read_artifact("timer")
    assert "WantedBy=timers.target" in timer


def test_timer_not_enabled_by_default_comment():
    """Timer comments must explicitly document that it is disabled by default."""
    timer = read_artifact("timer")
    # Must mention that INSTALL is DISABLED by default.
    assert "INSTALL DISABLED" in timer or "disabled" in timer.lower()
    # Must mention rollback or re-enable of legacy timers.
    assert "ROLLBACK" in timer or "rollback" in timer.lower()


# ── Service unit ──────────────────────────────────────────────────────────────


def test_service_uses_env_file():
    """Service unit must reference the scheduler env file via EnvironmentFile."""
    service = read_artifact("service")
    assert "EnvironmentFile=-/etc/akasha/ingestion-scheduler.env" in service


def test_service_working_directory_is_srv_akasha():
    """WorkingDirectory must be /srv/akasha (staging guardrail OPS-002)."""
    service = read_artifact("service")
    assert "WorkingDirectory=/srv/akasha" in service


def test_service_acquires_global_scheduler_lock():
    """Service must acquire the global scheduler lock via flock before the wrapper."""
    service = read_artifact("service")
    # flock -n: fail immediately if already running
    assert "flock" in service
    assert "-n" in service
    assert "/srv/akasha/ingestion/scheduler.global.lock" in service


def test_service_wrapper_path_is_canonical():
    """ExecStart must reference the canonical /opt/akasha/bin wrapper path."""
    service = read_artifact("service")
    assert "/opt/akasha/bin/akasha-ingestion-scheduler.sh" in service


def test_service_timeout_is_generous():
    """Timeout must accommodate sequential multi-source runs (>= 1 hour)."""
    service = read_artifact("service")
    assert "TimeoutStartSec=" in service
    # At least 1 hour: 1h, 2h, 4h, 8h, etc.
    timeout_line = next(
        (line for line in service.splitlines() if "TimeoutStartSec=" in line),
        None,
    )
    assert timeout_line is not None, "TimeoutStartSec not found in service unit"
    # Must specify hours (h suffix) — not just seconds
    assert "h" in timeout_line, f"Expected hour-based timeout, got: {timeout_line}"


def test_service_uses_journal_logging():
    """Service must log to the journal (StandardOutput/StandardError = journal)."""
    service = read_artifact("service")
    assert "StandardOutput=journal" in service
    assert "StandardError=journal" in service


def test_service_type_is_oneshot():
    """Scheduler service must be oneshot (runs and exits, not a daemon)."""
    service = read_artifact("service")
    assert "Type=oneshot" in service


def test_service_creates_required_staging_directories():
    """ExecStartPre must create required /srv/akasha sub-directories."""
    service = read_artifact("service")
    assert "/srv/akasha/ingestion" in service
    assert "/srv/akasha/data/raw/bhoonidhi" in service
    assert "/srv/akasha/data/work/bhoonidhi" in service


# ── Wrapper script ────────────────────────────────────────────────────────────


def test_wrapper_defaults_to_plan_only_safe_posture():
    """Wrapper must default all three activation flags to their safe values."""
    wrapper = read_artifact("wrapper")
    # Active flag defaults to false → plan-only, no provider calls.
    assert 'AKASHA_SCHEDULER_ACTIVE="${AKASHA_SCHEDULER_ACTIVE:-false}"' in wrapper
    # Dry-run defaults to true (extra safety layer even when active).
    assert 'AKASHA_SCHEDULER_DRY_RUN="${AKASHA_SCHEDULER_DRY_RUN:-true}"' in wrapper
    # Approved-runtime defaults to false → Bhoonidhi calls blocked.
    assert (
        'AKASHA_SCHEDULER_APPROVED_RUNTIME="${AKASHA_SCHEDULER_APPROVED_RUNTIME:-false}"'
        in wrapper
    )


def test_wrapper_uses_schedule_plan_when_not_active():
    """When AKASHA_SCHEDULER_ACTIVE != true the wrapper must run schedule-plan."""
    wrapper = read_artifact("wrapper")
    assert "schedule-plan" in wrapper
    # The plan-only branch must be the default path.
    # Bash conditional: [[ "${AKASHA_SCHEDULER_ACTIVE}" != "true" ]]
    assert '"${AKASHA_SCHEDULER_ACTIVE}" != "true"' in wrapper


def test_wrapper_uses_schedule_due_sources_only_when_active():
    """schedule-due-sources must be invoked only in the active + approved path."""
    wrapper = read_artifact("wrapper")
    assert "schedule-due-sources" in wrapper
    # Must also check approved_runtime gate before calling due-sources.
    assert "AKASHA_SCHEDULER_APPROVED_RUNTIME" in wrapper


def test_wrapper_passes_approved_runtime_only_when_active_and_approved():
    """--approved-runtime flag must appear only in the active+approved code path."""
    wrapper = read_artifact("wrapper")
    # The flag must be present.
    assert "--approved-runtime" in wrapper
    # It must be gated: the due_cmd array includes it only after both checks pass.
    # Verify the approved_runtime gate exists before the first non-comment due_cmd usage.
    lines = wrapper.splitlines()
    # Find the first non-comment line containing --approved-runtime (the actual usage in due_cmd).
    approved_runtime_line = next(
        (
            i
            for i, line in enumerate(lines)
            if "--approved-runtime" in line and not line.strip().startswith("#")
        ),
        None,
    )
    # Bash gate: [[ "${AKASHA_SCHEDULER_APPROVED_RUNTIME}" != "true" ]]
    active_check_line = next(
        (
            i
            for i, line in enumerate(lines)
            if '"${AKASHA_SCHEDULER_APPROVED_RUNTIME}" != "true"' in line
        ),
        None,
    )
    assert approved_runtime_line is not None, "--approved-runtime not found in non-comment code"
    assert active_check_line is not None, (
        'approved_runtime gate check ([[ "${AKASHA_SCHEDULER_APPROVED_RUNTIME}" != "true" ]]) '
        "not found in wrapper"
    )
    # The --approved-runtime due_cmd entry must come after the approved_runtime gate check.
    assert approved_runtime_line > active_check_line, (
        "--approved-runtime must appear after the approved_runtime gate check"
    )


def test_wrapper_uses_bounded_defaults_for_concurrency_window_dirs():
    """Wrapper must have bounded defaults for max-concurrent, window, base/lock dirs."""
    wrapper = read_artifact("wrapper")
    assert "AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES" in wrapper
    assert "AKASHA_SCHEDULER_WINDOW_DAYS" in wrapper
    assert "AKASHA_SCHEDULER_BASE_DIR" in wrapper
    assert "AKASHA_SCHEDULER_LOCK_DIR" in wrapper
    # Default base dir must match the canonical BFF/ingestion jobs directory.
    assert "/srv/akasha/ingestion/scheduler/jobs" in wrapper
    assert "/srv/akasha/ingestion/scheduler-jobs" not in wrapper
    # Default lock dir must be under /srv/akasha.
    assert "/srv/akasha/ingestion" in wrapper


def test_wrapper_rejects_scheduler_paths_outside_srv_akasha():
    wrapper = read_artifact("wrapper")
    assert "ensure_under_srv_akasha" in wrapper
    assert 'ensure_under_srv_akasha "${AKASHA_SCHEDULER_BASE_DIR}"' in wrapper
    assert 'ensure_under_srv_akasha "${AKASHA_SCHEDULER_LOCK_DIR}"' in wrapper
    assert 'ensure_under_srv_akasha "${AKASHA_SCHEDULER_LEDGER_DB_PATH}"' in wrapper
    assert "--ledger-db-path" in wrapper


def test_service_and_installer_use_canonical_scheduler_jobs_dir():
    service = read_artifact("service")
    installer = read_artifact("installer")
    assert "/srv/akasha/ingestion/scheduler/jobs" in service
    assert "/srv/akasha/ingestion/scheduler/jobs" in installer
    assert "/srv/akasha/ingestion/scheduler-jobs" not in service
    assert "/srv/akasha/ingestion/scheduler-jobs" not in installer


def test_wrapper_uses_ionice_and_nice():
    """Wrapper must apply ionice/nice to limit I/O and CPU priority."""
    wrapper = read_artifact("wrapper")
    assert "ionice" in wrapper
    assert "nice" in wrapper
    assert "AKASHA_INGESTION_IONICE_CLASS" in wrapper
    assert "AKASHA_INGESTION_IONICE_LEVEL" in wrapper
    assert "AKASHA_INGESTION_NICE" in wrapper
    assert '"${priority_cmd[@]}"' in wrapper
    assert 'priority_cmd[@]+"' not in wrapper


def test_wrapper_ionice_nice_uses_array_prefix():
    """priority_cmd array must be used to wrap docker compose calls."""
    wrapper = read_artifact("wrapper")
    # Array initialised before commands.
    assert "priority_cmd=()" in wrapper
    assert "priority_cmd+=(ionice" in wrapper
    assert "priority_cmd+=(nice" in wrapper
    # Safe array expansion used at docker compose call sites.
    assert "priority_cmd[@]" in wrapper


def test_wrapper_array_expansion_is_safe_under_nounset():
    """priority_cmd array expansion must handle empty-array case under set -u."""
    wrapper = read_artifact("wrapper")
    # Direct array expansion is safe for empty arrays in bash and avoids trying
    # to execute the entire prefix as one quoted command.
    assert '"${priority_cmd[@]}"' in wrapper
    assert 'priority_cmd[@]+"' not in wrapper


def test_wrapper_applies_redact_stream_to_docker_output():
    """All docker compose output must be piped through redact_stream."""
    wrapper = read_artifact("wrapper")
    assert "redact_stream" in wrapper
    # redact_stream must be defined in the script, not just called.
    assert "redact_stream()" in wrapper
    # Secrets patterns must be covered.
    assert "S3_SECRET_KEY" in wrapper
    assert "AKASHA_OBJECT_STORAGE_SECRET_KEY" in wrapper


def test_wrapper_data_paths_stay_under_srv_akasha():
    """All staging data paths referenced in the wrapper must stay under /srv/akasha (OPS-002)."""
    wrapper = read_artifact("wrapper")
    # Non-comment lines must not reference /tmp or /var/tmp as actual paths.
    # (Comments may mention these as *forbidden* paths in the guardrail documentation.)
    non_comment_lines = [
        line for line in wrapper.splitlines()
        if not line.strip().startswith("#")
    ]
    non_comment_text = "\n".join(non_comment_lines)
    # /tmp must not appear in executable code (only allowed in comments as guardrail docs).
    assert "/tmp" not in non_comment_text, (
        "/tmp referenced in non-comment lines of wrapper; data must stay under /srv/akasha"
    )
    assert "/var/tmp" not in non_comment_text, (
        "/var/tmp referenced in non-comment lines of wrapper"
    )
    # Default scheduler paths used in the wrapper must be under /srv/akasha.
    assert "/srv/akasha/ingestion/scheduler/jobs" in non_comment_text
    assert "/srv/akasha/ingestion" in non_comment_text
    # Raw/work bhoonidhi paths are created by ExecStartPre in the service unit
    # and configured via the env file — not hardcoded in the wrapper itself.
    # Verify the service unit handles directory creation.
    service = read_artifact("service")
    assert "/srv/akasha/data/raw/bhoonidhi" in service
    assert "/srv/akasha/data/work/bhoonidhi" in service


def test_wrapper_lock_dir_compatible_with_legacy_bhoonidhi_worker_locks():
    """Lock directory must be /srv/akasha/ingestion (shared with Bhoonidhi worker locks)."""
    wrapper = read_artifact("wrapper")
    # LOCK_DIR default is the same dir that holds bhoonidhi-sync.*.worker.lock files.
    assert "/srv/akasha/ingestion" in wrapper
    # Global scheduler lock is separate from the per-source worker locks.
    assert "scheduler.global.lock" in wrapper
    # The wrapper must document that ResourceSat jobs reuse legacy worker lock names.
    assert "reuse the legacy worker lock filenames" in wrapper
    assert "bhoonidhi-sync.<aoi>.worker.lock" in wrapper
    assert "mutually exclusive" in wrapper
    assert "scheduler.<src>.<aoi>.lock" not in wrapper


def test_wrapper_uses_compose_file_discovery():
    """Wrapper must support Coolify compose auto-discovery like the sync scripts."""
    wrapper = read_artifact("wrapper")
    assert "AKASHA_COMPOSE_FILE" in wrapper
    assert "/srv/akasha/coolify-compose.yml" in wrapper
    assert "find /data/coolify/services" in wrapper
    assert "AKASHA_SYNC_PULL_POLICY" in wrapper


def test_wrapper_sources_env_file_for_resilience():
    """Wrapper must source /etc/akasha/ingestion-scheduler.env for out-of-systemd runs."""
    wrapper = read_artifact("wrapper")
    assert "/etc/akasha/ingestion-scheduler.env" in wrapper
    assert "source " in wrapper or ". " in wrapper


def test_wrapper_logs_rollback_info_when_not_active():
    """Wrapper must log rollback information when running in plan-only mode."""
    wrapper = read_artifact("wrapper")
    assert "ROLLBACK" in wrapper or "rollback" in wrapper.lower()
    # Must mention legacy timers in rollback context.
    assert "legacy" in wrapper.lower() or "source-specific" in wrapper.lower()


def test_wrapper_includes_run_header_for_observability():
    """Wrapper must log a structured run header including key config values."""
    wrapper = read_artifact("wrapper")
    assert "ingestion scheduler run" in wrapper.lower()
    assert "active=" in wrapper or "active=${" in wrapper
    assert "dry_run=" in wrapper or "dry_run=${" in wrapper
    assert "approved_runtime=" in wrapper or "approved_runtime=${" in wrapper


# ── Environment example ───────────────────────────────────────────────────────


def test_env_example_contains_scheduler_activation_defaults():
    """Env example must set all three activation flags to safe defaults."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_ACTIVE=false" in env
    assert "AKASHA_SCHEDULER_DRY_RUN=true" in env
    assert "AKASHA_SCHEDULER_APPROVED_RUNTIME=false" in env


def test_env_example_contains_concurrency_and_window_defaults():
    """Env example must include max-concurrent-sources and window-days defaults."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES=2" in env
    assert "AKASHA_SCHEDULER_WINDOW_DAYS=12" in env


def test_env_example_contains_safe_path_defaults():
    """Env example must define base-dir and lock-dir under /srv/akasha."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_BASE_DIR=/srv/akasha/ingestion/scheduler/jobs" in env
    assert "AKASHA_SCHEDULER_LOCK_DIR=/srv/akasha/ingestion" in env


def test_env_example_contains_io_priority_defaults():
    """Env example must define ionice/nice priority settings."""
    env = read_artifact("env_example")
    assert "AKASHA_INGESTION_NICE=10" in env
    assert "AKASHA_INGESTION_IONICE_CLASS=2" in env
    assert "AKASHA_INGESTION_IONICE_LEVEL=7" in env


def test_env_example_contains_storage_path_defaults():
    """Env example must include shared raw/work/ledger storage paths."""
    env = read_artifact("env_example")
    assert "AKASHA_SYNC_RAW_ROOT=/srv/akasha/data/raw/bhoonidhi" in env
    assert "AKASHA_SYNC_TEMP_ROOT=/srv/akasha/data/work/bhoonidhi" in env
    assert "AKASHA_SYNC_LEDGER_PATH=/srv/akasha/ingestion/ledger.sqlite" in env
    # Pull policy shared with sync wrappers.
    assert "AKASHA_SYNC_PULL_POLICY=never" in env


def test_env_example_contains_stale_lock_ttl_setting():
    """Env example must document the stale-lock TTL knob."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_LOCK_STALE_TTL" in env


def test_env_example_contains_retention_prune_setting():
    """Env example must document the job-artifact retention/prune setting."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_JOB_RETENTION_DAYS" in env


def test_env_example_contains_provider_knobs_for_bhoonidhi():
    """Env example must include commented-out Bhoonidhi provider knobs."""
    env = read_artifact("env_example")
    # Bhoonidhi credentials are commented out (not set as literals).
    assert "AKASHA_BHOONIDHI" in env or "BHOONIDHI" in env
    # Credentials must be commented-out, not hardcoded.
    assert "AKASHA_BHOONIDHI_PASSWORD=<" in env or "BHOONIDHI_PASSWORD=<" in env or (
        "AKASHA_BHOONIDHI_PASSWORD" in env
        and not any(
            line.strip().startswith("AKASHA_BHOONIDHI_PASSWORD=")
            and not line.strip().startswith("#")
            and "<" not in line
            for line in env.splitlines()
        )
    )


def test_env_example_contains_ownership_matrix():
    """Env example must include the legacy-timer/scheduler ownership matrix."""
    env = read_artifact("env_example")
    # Must mention ownership tracking.
    assert "ownedBy" in env or "ownership" in env.lower()
    # Must list known sources.
    assert "resourcesat-2a-liss3-boa" in env
    assert "resourcesat-2a-liss4-mx70-l2" in env
    # Must include rollback commands.
    assert "systemctl enable" in env or "systemctl" in env


def test_env_example_contains_rollback_commands():
    """Env example must document rollback commands for legacy timers."""
    env = read_artifact("env_example")
    assert "ROLLBACK" in env
    assert "systemctl" in env
    # Should mention stopping the scheduler timer.
    assert "akasha-ingestion-scheduler.timer" in env


def test_env_example_contains_canary_filter_knobs():
    """Env example must document canary/source-filter options."""
    env = read_artifact("env_example")
    assert "AKASHA_SCHEDULER_SOURCE" in env
    assert "AKASHA_SCHEDULER_AOI" in env


def test_env_example_documents_cutover_states():
    """Env example must describe the scheduler cutover state progression."""
    env = read_artifact("env_example")
    # Must mention canary and production states.
    assert "canary" in env.lower()
    assert "disabled" in env.lower()
    # Must mention the cutover state variable.
    assert "CUTOVER_STATE" in env or "cutover" in env.lower()


def test_env_example_no_literal_secrets():
    """Env example must not contain hardcoded secret values."""
    env = read_artifact("env_example")
    forbidden = [
        "BHOONIDHI_PASSWORD=",
        "BHOONIDHI_USERNAME=",
        "S3_SECRET_KEY=",
        "AWS_SECRET_ACCESS_KEY=",
        "access_token=",
        "AKASHA_OBJECT_STORAGE_SECRET_KEY=",
    ]
    for forbidden_literal in forbidden:
        # Allow commented-out lines.
        for line in env.splitlines():
            if forbidden_literal in line and not line.strip().startswith("#"):
                pytest.fail(
                    f"literal secret key assignment found in env_example: {line!r}"
                )


# ── Installer ─────────────────────────────────────────────────────────────────


def test_installer_installs_to_canonical_paths():
    """Installer must copy artifacts to the expected system paths."""
    installer = read_artifact("installer")
    assert "/opt/akasha/bin/akasha-ingestion-scheduler.sh" in installer
    assert "/etc/systemd/system/akasha-ingestion-scheduler.service" in installer
    assert "/etc/systemd/system/akasha-ingestion-scheduler.timer" in installer
    assert "/etc/akasha/ingestion-scheduler.env" in installer


def test_installer_does_not_enable_timer_by_default():
    """Installer must NOT enable the timer unless --enable or --start is given."""
    installer = read_artifact("installer")
    # --enable and --start flags must exist.
    assert "--enable" in installer
    assert "--start" in installer
    # The enable/start systemctl commands must be conditional on those flags.
    # Look for something like `if [[ "${enable_timer}" == "true" ]]`
    assert "enable_timer" in installer or "enable" in installer
    assert "start_timer" in installer or "start" in installer


def test_installer_supports_dry_run_mode():
    """Installer must support --dry-run mode that prints commands without executing."""
    installer = read_artifact("installer")
    assert "--dry-run" in installer
    assert "dry_run" in installer


def test_installer_runs_daemon_reload():
    """Installer must run systemctl daemon-reload after installing units."""
    installer = read_artifact("installer")
    assert "systemctl daemon-reload" in installer


def test_installer_creates_scheduler_jobs_directory():
    """Installer must create /srv/akasha/ingestion/scheduler/jobs directory."""
    installer = read_artifact("installer")
    assert "/srv/akasha/ingestion/scheduler/jobs" in installer


def test_installer_env_skip_existing():
    """Installer must skip overwriting existing env file unless --env-overwrite given."""
    installer = read_artifact("installer")
    # Must have a conditional overwrite guard.
    assert "overwrite_env" in installer or "env-overwrite" in installer


def test_installer_prints_next_steps_and_rollback():
    """Installer must print post-install guidance including rollback commands."""
    installer = read_artifact("installer")
    # Must mention enabling the timer explicitly after validation.
    assert "systemctl enable" in installer
    # Must mention rollback.
    assert "Rollback" in installer or "rollback" in installer.lower()
    # Must mention the canary/dry-run steps.
    assert "canary" in installer.lower() or "dry-run" in installer.lower() or "DRY_RUN" in installer


# ── Compatibility / docs comments across artifacts ────────────────────────────


def test_artifacts_mention_compatibility_mode():
    """At least one artifact must document compatibility mode / legacy timer."""
    combined = "\n".join(read_artifact(k) for k in EXPECTED_FILES)
    # The docs should mention compatibility with legacy per-source timers.
    assert "compatibility" in combined.lower() or "legacy" in combined.lower()


def test_artifacts_mention_one_owner_rule():
    """Artifacts must state that scheduler and legacy timer must not own the same source."""
    combined = "\n".join(read_artifact(k) for k in EXPECTED_FILES)
    # One-owner rule: NEVER let scheduler and legacy timer own the same source/AOI.
    assert (
        "simultaneously" in combined.lower()
        or "NEVER" in combined
        or "never" in combined.lower()
    )


def test_artifacts_mention_canary_flow():
    """Artifacts must describe the canary validation flow."""
    combined = "\n".join(read_artifact(k) for k in EXPECTED_FILES)
    assert "canary" in combined.lower()


def test_artifacts_mention_rollback():
    """Artifacts must describe rollback from the scheduler to legacy timers."""
    combined = "\n".join(read_artifact(k) for k in EXPECTED_FILES)
    assert "ROLLBACK" in combined or "rollback" in combined.lower()
    # Rollback must mention re-enabling legacy timers.
    assert "akasha-bhoonidhi-sync.timer" in combined


# ── Installer dry-run (bash-only) ─────────────────────────────────────────────


def test_installer_dry_run_default_outputs_install_paths_but_no_enable():
    """Dry-run without --enable/--start must print install paths, no systemctl enable."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if "system32" in bash.lower():
        pytest.skip("WSL bash cannot access this Windows workspace path directly")

    installer = SYSTEMD_DIR / EXPECTED_FILES["installer"]
    result = subprocess.run(
        [bash, str(installer), "--dry-run"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/opt/akasha/bin/akasha-ingestion-scheduler.sh" in result.stdout
    assert "/etc/systemd/system/akasha-ingestion-scheduler.service" in result.stdout
    assert "/etc/systemd/system/akasha-ingestion-scheduler.timer" in result.stdout
    assert "/etc/akasha/ingestion-scheduler.env" in result.stdout
    assert "systemctl daemon-reload" in result.stdout
    # Must NOT enable or start the timer in default dry-run mode.
    assert "systemctl enable akasha-ingestion-scheduler.timer" not in result.stdout
    assert "systemctl start akasha-ingestion-scheduler.timer" not in result.stdout


def test_installer_dry_run_with_enable_outputs_enable_command():
    """Dry-run with --enable must print systemctl enable but not start."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if "system32" in bash.lower():
        pytest.skip("WSL bash cannot access this Windows workspace path directly")

    installer = SYSTEMD_DIR / EXPECTED_FILES["installer"]
    result = subprocess.run(
        [bash, str(installer), "--dry-run", "--enable"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/opt/akasha/bin/akasha-ingestion-scheduler.sh" in result.stdout
    assert "systemctl enable akasha-ingestion-scheduler.timer" in result.stdout
    assert "systemctl start akasha-ingestion-scheduler.timer" not in result.stdout


def test_installer_dry_run_with_start_outputs_enable_and_start():
    """Dry-run with --start must print both systemctl enable and start."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if "system32" in bash.lower():
        pytest.skip("WSL bash cannot access this Windows workspace path directly")

    installer = SYSTEMD_DIR / EXPECTED_FILES["installer"]
    result = subprocess.run(
        [bash, str(installer), "--dry-run", "--enable", "--start"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/opt/akasha/bin/akasha-ingestion-scheduler.sh" in result.stdout
    assert "/etc/systemd/system/akasha-ingestion-scheduler.service" in result.stdout
    assert "/etc/systemd/system/akasha-ingestion-scheduler.timer" in result.stdout
    assert "/etc/akasha/ingestion-scheduler.env" in result.stdout
    assert "/srv/akasha/ingestion/scheduler/jobs" in result.stdout
    assert "systemctl daemon-reload" in result.stdout
    assert "systemctl enable akasha-ingestion-scheduler.timer" in result.stdout
    assert "systemctl start akasha-ingestion-scheduler.timer" in result.stdout
