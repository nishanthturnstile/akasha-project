import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "staging_ingestion_job.py"
spec = importlib.util.spec_from_file_location("staging_ingestion_job", SCRIPT_PATH)
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
assert spec.loader is not None
spec.loader.exec_module(cli)


def completed(args, stdout="", returncode=0):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")


def test_parser_accepts_all_documented_subcommands():
    parser = cli.build_parser()

    cases = [
        (["trigger", "--host", "staging", "--dry-run"], "trigger"),
        (["status", "job-1", "--json"], "status"),
        (["logs", "job-1", "--tail", "25", "--follow"], "logs"),
        (["list", "--limit", "5"], "list"),
        (["retry", "job-1", "--overwrite", "--force-upload"], "retry"),
        (["validate", "job-1"], "validate"),
        (["sync-local", "job-1", "--import-local", "--verify-local"], "sync-local"),
        (["doctor", "--azure-resource-group", "rg", "--azure-vm", "vm"], "doctor"),
    ]

    for argv, command in cases:
        assert parser.parse_args(argv).command == command


def test_run_ssh_uses_list_args_and_never_local_shell(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return completed(command, stdout="ok\n")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = cli.run_ssh("akasha-staging", ["status", "job-1"], input_text="{}", capture=True)

    assert result.stdout == "ok\n"
    assert captured["command"] == [
        "ssh",
        "akasha-staging",
        cli.REMOTE_COMMAND,
        "status",
        "job-1",
    ]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["input"] == "{}"


def test_trigger_sends_default_filled_canonical_request(monkeypatch, capsys):
    sent = {}

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 22, 8, 0, 1, tzinfo=UTC)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)
    monkeypatch.setattr(cli.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(cli.getpass, "getuser", lambda: "dev")
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "workstation")

    def fake_run_ssh(host, remote_args, *, input_text=None, capture=True):
        sent["host"] = host
        sent["remote_args"] = remote_args
        sent["request"] = json.loads(input_text)
        return completed(["ssh"], stdout='{"accepted": true}\n')

    monkeypatch.setattr(cli, "run_ssh", fake_run_ssh)

    assert cli.main(["trigger", "--host", "staging", "--dry-run"]) == 0

    request = sent["request"]
    assert sent["host"] == "staging"
    assert sent["remote_args"] == ["start"]
    assert request == {
        "job_id": "ingest-20260622T080001Z-abcdef12",
        "source_id": "resourcesat-2a-liss3-boa",
        "provider": "bhoonidhi",
        "aoi_id": "bangalore-60km",
        "window_start": "",
        "window_end": "2026-06-22",
        "window_days": 45,
        "backfill_days": 0,
        "backfill_step_days": None,
        "limit": 100,
        "max_downloads": 3,
        "min_coverage_percent": 95.0,
        "dry_run": True,
        "overwrite": False,
        "force_upload": False,
        "retain_raw_downloads": False,
        "keep_intermediate": False,
        "requested_by": "dev@workstation",
        "notes": "",
    }
    output = capsys.readouterr().out
    assert "job_id: ingest-20260622T080001Z-abcdef12" in output
    assert "status ingest-20260622T080001Z-abcdef12" in output
    assert "logs ingest-20260622T080001Z-abcdef12 --follow" in output


def test_trigger_wait_stops_on_terminal_state(monkeypatch, capsys):
    statuses = iter(
        [
            {"state": "running", "request": {"source_id": "s", "aoi_id": "a"}},
            {"state": "blocked_by_lock", "request": {"source_id": "s", "aoi_id": "a"}},
        ]
    )
    calls = []

    monkeypatch.setattr(
        cli,
        "build_request",
        lambda _args: {"job_id": "job-1", "source_id": "s", "aoi_id": "a"},
    )
    monkeypatch.setattr(cli.time, "monotonic", lambda: len(calls))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    def fake_run_ssh(_host, remote_args, *, input_text=None, capture=True):
        calls.append(remote_args)
        if remote_args == ["start"]:
            return completed(["ssh"], stdout="{}\n")
        return completed(["ssh"], stdout=json.dumps(next(statuses)))

    monkeypatch.setattr(cli, "run_ssh", fake_run_ssh)

    assert cli.main(["trigger", "--wait", "--wait-interval", "1"]) == 0
    assert calls == [["start"], ["status", "job-1"], ["status", "job-1"]]
    assert "state: blocked_by_lock" in capsys.readouterr().out


def test_trigger_wait_timeout_returns_nonzero(monkeypatch, capsys):
    ticks = iter([0.0, 0.0, 2.0])

    monkeypatch.setattr(
        cli,
        "build_request",
        lambda _args: {"job_id": "job-1", "source_id": "s", "aoi_id": "a"},
    )
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        cli,
        "run_ssh",
        lambda _host, remote_args, **_kwargs: completed(
            ["ssh"],
            stdout="{}\n" if remote_args == ["start"] else '{"state":"running"}\n',
        ),
    )

    assert cli.main(["trigger", "--wait", "--wait-timeout", "1", "--wait-interval", "1"]) == 2
    output = capsys.readouterr().out
    assert "timed out waiting for job-1" in output
    assert "status job-1" in output


def test_status_formats_human_summary(monkeypatch, capsys):
    payload = {
        "state": "validation_failed",
        "request": {
            "source_id": "resourcesat-2a-liss3-boa",
            "aoi_id": "bangalore-60km",
            "window_start": "2026-05-01",
            "window_end": "2026-06-22",
        },
        "exit_code": 4,
        "failure_kind": "coverage",
        "message": "coverage below threshold",
        "log_path": "/srv/akasha/ingestion/jobs/job-1/job.log",
        "result": {"composite_date": "2026-06-22"},
    }
    monkeypatch.setattr(
        cli,
        "run_ssh",
        lambda *_args, **_kwargs: completed(["ssh"], json.dumps(payload)),
    )

    assert cli.main(["status", "job-1"]) == 0

    output = capsys.readouterr().out
    assert "state: validation_failed" in output
    assert "source: resourcesat-2a-liss3-boa" in output
    assert "AOI: bangalore-60km" in output
    assert "window: 2026-05-01..2026-06-22" in output
    assert "exit_code: 4" in output
    assert "failure_kind: coverage" in output
    assert "message: coverage below threshold" in output
    assert "log_path: /srv/akasha/ingestion/jobs/job-1/job.log" in output
    assert "composite_date: 2026-06-22" in output


def test_logs_follow_uses_popen_list_command(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    assert cli.main(["logs", "job-1", "--host", "staging", "--follow"]) == 0
    assert captured["command"] == [
        "ssh",
        "staging",
        cli.REMOTE_COMMAND,
        "logs",
        "job-1",
        "--follow",
    ]
    assert captured["kwargs"]["shell"] is False


def test_retry_forwards_overwrite_force_upload_and_notes(monkeypatch, capsys):
    captured = {}

    def fake_run_ssh(_host, remote_args, **_kwargs):
        captured["remote_args"] = remote_args
        return completed(["ssh"], '{"job_id":"job-2"}\n')

    monkeypatch.setattr(cli, "run_ssh", fake_run_ssh)

    assert (
        cli.main(["retry", "job-1", "--overwrite", "--force-upload", "--notes", "try again"])
        == 0
    )
    assert captured["remote_args"] == [
        "retry",
        "job-1",
        "--overwrite",
        "--force-upload",
        "--notes",
        "try again",
    ]
    assert "new job_id: job-2" in capsys.readouterr().out


def test_validate_no_composite_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_ssh",
        lambda *_args, **_kwargs: completed(
            ["ssh"],
            '{"status":"no_composite","result":{"composite_date":""}}\n',
            returncode=0,
        ),
    )

    assert cli.main(["validate", "job-1"]) == 0
    assert "no composite produced; nothing to validate" in capsys.readouterr().out


def test_validate_failure_prints_stdout_json_detail(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_ssh",
        lambda *_args, **_kwargs: completed(
            ["ssh"],
            json.dumps(
                {
                    "status": "validation_failed",
                    "manifest": (
                        "/srv/akasha/data/seed/rasters/source/composite/aoi/date/"
                        "prepare_manifest.json"
                    ),
                    "detail": "coverage below threshold",
                }
            ),
            returncode=4,
        ),
    )

    assert cli.main(["validate", "job-1"]) == 4
    output = capsys.readouterr().out
    assert "validation: validation_failed" in output
    expected_manifest = (
        "manifest: /srv/akasha/data/seed/rasters/source/composite/aoi/date/"
        "prepare_manifest.json"
    )
    assert expected_manifest in output
    assert "detail: coverage below threshold" in output


def test_sync_local_job_id_delegates_to_bundle_script(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return completed(command)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert (
        cli.main(
            [
                "sync-local",
                "job-1",
                "--host",
                "staging",
                "--import-local",
                "--verify-local",
                "--overwrite",
                "--force-upload",
            ]
        )
        == 0
    )

    assert captured["command"] == [
        sys.executable,
        str(cli.REPO_ROOT / "scripts" / "sync_staging_raster_bundle.py"),
        "--host",
        "staging",
        "--job-id",
        "job-1",
        "--import-local",
        "--verify-local",
        "--overwrite",
        "--force-upload",
    ]
    assert captured["kwargs"]["shell"] is False


def test_doctor_returns_failure_when_required_checks_fail(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: None if name == "docker" else f"C:\\bin\\{name}.exe",
    )
    monkeypatch.setattr(cli, "run_ssh", lambda *_args, **_kwargs: completed(["ssh"], "ok\n"))
    monkeypatch.setattr(cli, "check_local_seed_write", lambda: (True, "ok"))
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kwargs: completed(command))

    assert cli.main(["doctor"]) == 1
    assert "FAIL docker executable" in capsys.readouterr().out
