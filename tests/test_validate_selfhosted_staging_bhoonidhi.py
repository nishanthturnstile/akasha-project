import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts/validate_selfhosted_staging_bhoonidhi.py"
)
spec = importlib.util.spec_from_file_location("akasha_staging_bhoonidhi_validator", SCRIPT_PATH)
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
assert spec.loader is not None
spec.loader.exec_module(validator)


def test_run_ssh_sends_binary_lf_script(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator._run_ssh(
        "akasha-staging",
        "set -euo pipefail\r\necho ok\r\n",
        timeout_seconds=5,
    )

    assert captured["command"] == ["ssh", "akasha-staging", "bash", "-s"]
    assert captured["input"] == b"set -euo pipefail\necho ok\n"
    assert result.stdout == "ok\n"
    assert result.stderr == ""


def test_main_stops_after_image_gate_failure(monkeypatch, capsys):
    calls = []
    checks = [
        validator.Check("image gate", "image", stop_on_failure=True),
        validator.Check("current search", "search"),
    ]

    monkeypatch.setattr(validator, "_checks", lambda _args: checks)
    monkeypatch.setattr(
        validator,
        "_run_ssh",
        lambda _host, command, timeout_seconds: calls.append(command)
        or subprocess.CompletedProcess(["ssh"], 1, stdout="", stderr="missing tag"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_selfhosted_staging_bhoonidhi.py",
            "--expected-sha",
            "abc123",
            "--skip-timer-check",
        ],
    )

    assert validator.main() == 1

    output = capsys.readouterr()
    assert calls == ["image"]
    assert "Stopping after failed required gate" in output.out
    assert "missing tag" in output.err


def test_main_can_continue_after_required_failure(monkeypatch):
    calls = []
    checks = [
        validator.Check("image gate", "image", stop_on_failure=True),
        validator.Check("current search", "search"),
    ]

    def fake_run(_host, command, timeout_seconds):
        calls.append(command)
        if command == "image":
            return subprocess.CompletedProcess(["ssh"], 1, stdout="", stderr="")
        return subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr="")

    monkeypatch.setattr(validator, "_checks", lambda _args: checks)
    monkeypatch.setattr(validator, "_run_ssh", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_selfhosted_staging_bhoonidhi.py",
            "--expected-sha",
            "abc123",
            "--continue-after-failure",
        ],
    )

    assert validator.main() == 1
    assert calls == ["image", "search"]


def test_public_smoke_check_builds_authenticated_monitoring_command():
    class Args:
        public_origin = "https://staging.gis.cidsaglobal.com/"
        require_public_smoke = False
        smoke_login = False
        require_raster = True
        require_monitoring_clean = True

    check = validator._public_smoke_check(Args())

    assert check is not None
    assert check.name == "public gateway smoke"
    assert check.remote is False
    assert check.command[-4:] == [
        "https://staging.gis.cidsaglobal.com",
        "--login",
        "--require-raster",
        "--require-monitoring-clean",
    ]
    assert check.required is True


def test_public_smoke_check_is_warning_without_strict_flags():
    class Args:
        public_origin = "https://staging.gis.cidsaglobal.com/"
        require_public_smoke = False
        smoke_login = False
        require_raster = False
        require_monitoring_clean = False

    check = validator._public_smoke_check(Args())

    assert check is not None
    assert check.command == [
        sys.executable,
        str(validator.REPO_ROOT / "scripts/smoke-test.py"),
        "https://staging.gis.cidsaglobal.com",
    ]
    assert check.required is False


def test_public_smoke_check_can_be_required_without_login():
    class Args:
        public_origin = "https://staging.gis.cidsaglobal.com/"
        require_public_smoke = True
        smoke_login = False
        require_raster = False
        require_monitoring_clean = False

    check = validator._public_smoke_check(Args())

    assert check is not None
    assert check.required is True
