import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "infra" / "selfhosted" / "systemd"

EXPECTED_FILES = {
    "wrapper": "akasha-ingestion-job.sh",
    "runner": "akasha-ingestion-job-runner.sh",
    "forced_command": "akasha-ingestion-forced-command.sh",
    "env": "akasha-ingestion-jobs.env.example",
    "installer": "install-akasha-ingestion-jobs.sh",
}

FORBIDDEN_LITERAL_SECRETS = [
    "BHOONIDHI_PASSWORD=",
    "BHOONIDHI_USERNAME=",
    "S3_SECRET_KEY=",
    "AWS_SECRET_ACCESS_KEY=",
    "access_token=",
    "AKASHA_OBJECT_STORAGE_SECRET_KEY=",
]


def read_artifact(name: str) -> str:
    return (SYSTEMD_DIR / name).read_text()


def test_remote_job_artifacts_exist():
    for filename in EXPECTED_FILES.values():
        assert (SYSTEMD_DIR / filename).is_file(), filename


def test_env_example_contains_task_007_defaults_exactly():
    env = read_artifact(EXPECTED_FILES["env"])

    expected_defaults = [
        "AKASHA_INGESTION_JOB_ROOT=/srv/akasha/ingestion/jobs",
        (
            "AKASHA_INGESTION_ALLOWED_SOURCES="
            "resourcesat-2a-liss3-boa,resourcesat-2a-liss4-mx70-l2,resourcesat-2a-awifs-boa"
        ),
        "AKASHA_INGESTION_ALLOWED_AOIS=bangalore-60km",
        "AKASHA_INGESTION_DEFAULT_MAX_DOWNLOADS=3",
        "AKASHA_INGESTION_DEFAULT_MIN_COVERAGE_PERCENT=95",
        "AKASHA_INGESTION_LOG_RETENTION_DAYS=14",
        "AKASHA_INGESTION_NICE=10",
        "AKASHA_INGESTION_IONICE_CLASS=2",
        "AKASHA_INGESTION_IONICE_LEVEL=7",
        "AKASHA_SYNC_RAW_ROOT=/srv/akasha/data/raw/bhoonidhi",
        "AKASHA_SYNC_TEMP_ROOT=/srv/akasha/data/work/bhoonidhi",
        "AKASHA_SYNC_LEDGER_PATH=/srv/akasha/ingestion/ledger.sqlite",
        "AKASHA_SYNC_PULL_POLICY=never",
    ]
    for expected in expected_defaults:
        assert expected in env


def test_wrapper_contract_sources_env_starts_detached_and_writes_job_state():
    wrapper = read_artifact(EXPECTED_FILES["wrapper"])

    assert "/etc/akasha/ingestion-jobs.env" in wrapper
    assert "/srv/akasha/ingestion/jobs" in wrapper
    assert "request.json" in wrapper
    assert "mktemp" in wrapper
    assert "cat >\"${request_tmp}\"" in wrapper
    assert "status.json" in wrapper
    assert "queued" in wrapper
    assert "systemd-run" in wrapper
    assert "--collect" in wrapper
    assert "setsid" in wrapper
    assert "nohup" in wrapper
    assert "runner.pid" in wrapper
    assert "akasha-ingestion-job-runner.sh" in wrapper
    assert "chmod 640" in wrapper
    assert "uuid4" in wrapper


def test_runner_contract_uses_compose_worker_lock_redaction_and_group_only_artifacts():
    runner = read_artifact(EXPECTED_FILES["runner"])

    assert "AKASHA_COMPOSE_FILE" in runner
    assert "/srv/akasha/coolify-compose.yml" in runner
    assert "find /data/coolify/services" in runner
    assert "docker compose" in runner
    assert "ingestion-worker" in runner
    assert "python worker.py" in runner
    assert "priority_prefix" in runner
    assert "ionice -c" in runner
    assert "nice -n" in runner
    assert "AKASHA_INGESTION_NICE:-10" in runner
    assert "AKASHA_INGESTION_IONICE_CLASS:-2" in runner
    assert "AKASHA_INGESTION_IONICE_LEVEL:-7" in runner
    assert "bhoonidhi-sync" in runner
    assert "--pull \"${pull_policy}\"" in runner
    assert "AKASHA_SYNC_PULL_POLICY:-never" in runner
    assert "bhoonidhi-sync.${aoi_id}.worker.lock" in runner
    assert "command.txt" in runner
    assert "job.log" in runner
    assert "redact_stream" in runner
    assert "S3_SECRET_KEY" in runner
    assert "status.json" in runner
    assert "result.json" in runner
    assert "chmod 640" in runner
    assert "blocked_by_lock" in runner
    assert "invalid request.json" in runner
    assert "validation_failed" in runner


def test_installer_and_forced_command_contracts():
    installer = read_artifact(EXPECTED_FILES["installer"])
    forced = read_artifact(EXPECTED_FILES["forced_command"])

    assert "/opt/akasha/bin" in installer
    assert "/srv/akasha/ingestion/jobs" in installer
    assert "akasha-ingesters" in installer
    assert "install -d -m 2770" in installer
    assert "/etc/akasha/ingestion-jobs.env" in installer
    assert "--dry-run" in installer
    assert "--uninstall" in installer
    assert "authorized_keys" in installer
    assert "akasha-ingestion-forced-command.sh" in installer

    for subcommand in (
        "start",
        "status",
        "logs",
        "list",
        "retry",
        "validate",
        "doctor",
        "prune",
        "job-inspect",
        "job-artifact",
        "schedule-plan",
        "schedule-next",
    ):
        assert subcommand in forced
    assert "SSH_ORIGINAL_COMMAND" in forced
    assert "YYYY-MM-DD" in forced
    assert "--date" in forced
    assert "akasha-ingestion-job.sh" in forced
    assert "exec" in forced


def test_staging_wrapper_implements_schedule_inspection_commands():
    wrapper = read_artifact("akasha-ingestion-job.sh")
    assert "schedule_inspect" in wrapper
    assert "not implemented by the staging wrapper" not in wrapper
    assert "worker.py" in wrapper
    assert "schedule-plan" in wrapper
    assert "schedule-next" in wrapper


def test_artifacts_do_not_include_literal_secret_values():
    combined = "\n".join(read_artifact(filename) for filename in EXPECTED_FILES.values())

    for forbidden in FORBIDDEN_LITERAL_SECRETS:
        assert forbidden not in combined


def test_installer_dry_run_outputs_expected_job_setup_actions():
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
    assert "/opt/akasha/bin/akasha-ingestion-job.sh" in result.stdout
    assert "/opt/akasha/bin/akasha-ingestion-job-runner.sh" in result.stdout
    assert "/opt/akasha/bin/akasha-ingestion-forced-command.sh" in result.stdout
    assert "/srv/akasha/ingestion/jobs" in result.stdout
    assert "/etc/akasha/ingestion-jobs.env" in result.stdout
    assert "2770" in result.stdout
    assert "akasha-ingesters" in result.stdout
    assert "authorized_keys" in result.stdout
