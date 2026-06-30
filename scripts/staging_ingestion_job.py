"""Local CLI for staging ingestion jobs.

The CLI submits and inspects jobs through the restricted staging-side wrapper.
It intentionally uses list-based subprocess calls so it works on Windows and
never interpolates a local shell command.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_HOST_ENV = "AKASHA_STAGING_SSH_HOST"
DEFAULT_HOST = "akasha-staging"
REMOTE_COMMAND = "/opt/akasha/bin/akasha-ingestion-job.sh"
DEFAULT_SOURCE = "resourcesat-2a-liss3-boa"
DEFAULT_AOI = "bangalore-60km"

TERMINAL_STATES = {
    "succeeded",
    "failed",
    "blocked_by_lock",
    "validation_failed",
    "cancelled",
}

ARTIFACT_TYPES = ("request", "status", "coverage", "download", "result", "log")

# Keys whose values are always redacted in local output.
_REDACT_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "credential",
    "authorization",
)

_RAW_PATH_RE = re.compile(
    r"(?P<path>(?:/srv/akasha|/data/coolify|/var/lib/docker|/tmp|/var/tmp)"
    r"/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)"
)


def default_host() -> str:
    return os.environ.get(DEFAULT_HOST_ENV, DEFAULT_HOST)


def run_ssh(
    host: str,
    remote_args: list[str],
    *,
    input_text: str | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = ["ssh", host, REMOTE_COMMAND, *remote_args]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        input=input_text,
        capture_output=capture,
        check=False,
        shell=False,
    )


def _add_host(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=default_host(), help="SSH host for the staging VM.")


def _json_loads(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    return json.loads(text)


def _print_completed_error(result: subprocess.CompletedProcess[str]) -> None:
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")


def _job_id() -> str:
    now = datetime.now(UTC)
    return f"ingest-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _requested_by() -> str:
    return f"{getpass.getuser()}@{socket.gethostname()}"


def build_request(args: argparse.Namespace) -> dict[str, Any]:
    today_utc = datetime.now(UTC).date().isoformat()
    return {
        "job_id": _job_id(),
        "source_id": args.source,
        "provider": args.provider,
        "aoi_id": args.aoi,
        "window_start": args.window_start or "",
        "window_end": args.window_end or today_utc,
        "window_days": args.window_days,
        "backfill_days": args.backfill_days,
        "backfill_step_days": args.backfill_step_days,
        "limit": args.limit,
        "max_downloads": args.max_downloads,
        "min_coverage_percent": args.min_coverage_percent,
        "dry_run": bool(args.dry_run),
        "overwrite": bool(args.overwrite),
        "force_upload": bool(args.force_upload),
        "retain_raw_downloads": bool(args.retain_raw_downloads),
        "keep_intermediate": bool(args.keep_intermediate),
        "input_scale": args.input_scale,
        "polarizations": args.polarizations or "",
        "requested_by": args.requested_by or _requested_by(),
        "notes": args.notes or "",
    }


def _source_from_status(status: dict[str, Any]) -> str:
    request = status.get("request") or {}
    return str(status.get("source_id") or request.get("source_id") or "")


def _aoi_from_status(status: dict[str, Any]) -> str:
    request = status.get("request") or {}
    return str(status.get("aoi_id") or request.get("aoi_id") or "")


def print_resume_commands(host: str, job_id: str) -> None:
    print(f"  python scripts/staging_ingestion_job.py status {job_id} --host {host}")
    print(f"  python scripts/staging_ingestion_job.py logs {job_id} --follow --host {host}")
    print(f"  python scripts/staging_ingestion_job.py validate {job_id} --host {host}")
    print(f"  python scripts/staging_ingestion_job.py sync-local {job_id} --host {host}")


def _remote_status(host: str, job_id: str) -> dict[str, Any]:
    result = run_ssh(host, ["status", job_id])
    if result.returncode != 0:
        _print_completed_error(result)
        return {"state": "failed", "message": f"status command exited {result.returncode}"}
    return _json_loads(result.stdout)


def command_trigger(args: argparse.Namespace) -> int:
    request = build_request(args)
    input_text = json.dumps(request, sort_keys=True) + "\n"
    result = run_ssh(args.host, ["start"], input_text=input_text)
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode

    job_id = str(request["job_id"])
    print(f"job_id: {job_id}")
    print(f"source_id: {request['source_id']}")
    print(f"aoi_id: {request['aoi_id']}")
    print("next:")
    print_resume_commands(args.host, job_id)

    if not args.wait:
        return 0

    started = time.monotonic()
    while True:
        status = _remote_status(args.host, job_id)
        state = str(status.get("state") or "unknown")
        print(f"state: {state}")
        if state in TERMINAL_STATES:
            return 0
        if time.monotonic() - started >= args.wait_timeout:
            print(f"timed out waiting for {job_id} after {args.wait_timeout:g}s")
            print("resume with:")
            print_resume_commands(args.host, job_id)
            return 2
        time.sleep(args.wait_interval)


def _format_window(status: dict[str, Any]) -> str:
    request = status.get("request") or {}
    start = status.get("window_start") or request.get("window_start") or ""
    end = status.get("window_end") or request.get("window_end") or ""
    return f"{start}..{end}"


def _format_status_summary(status: dict[str, Any]) -> str:
    result = status.get("result") or {}
    lines = [
        f"state: {status.get('state', '')}",
        f"source: {_source_from_status(status)}",
        f"AOI: {_aoi_from_status(status)}",
        f"window: {_format_window(status)}",
        f"exit_code: {status.get('exit_code', '')}",
        f"failure_kind: {status.get('failure_kind', '')}",
        f"message: {status.get('message', '')}",
        f"log_path: {status.get('log_path', '')}",
    ]
    composite_date = status.get("composite_date") or result.get("composite_date")
    if composite_date is not None:
        lines.append(f"composite_date: {composite_date}")
    return "\n".join(lines)


def command_status(args: argparse.Namespace) -> int:
    result = run_ssh(args.host, ["status", args.job_id])
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    status = _json_loads(result.stdout)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(_format_status_summary(status))
    return 0


def command_logs(args: argparse.Namespace) -> int:
    remote_args = ["logs", args.job_id]
    if args.tail is not None:
        remote_args.extend(["--tail", str(args.tail)])
    if args.follow:
        remote_args.append("--follow")
        proc = subprocess.Popen(
            ["ssh", args.host, REMOTE_COMMAND, *remote_args],
            cwd=REPO_ROOT,
            shell=False,
            text=True,
        )
        return proc.wait()

    result = run_ssh(args.host, remote_args)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        _print_completed_error(result)
    return result.returncode


def command_list(args: argparse.Namespace) -> int:
    result = run_ssh(args.host, ["list", "--limit", str(args.limit)])
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    jobs = [_json_loads(line) for line in result.stdout.splitlines() if line.strip()]
    print(f"{'job_id':<34} {'state':<18} {'source':<28} {'aoi':<16} {'updated_at':<24} message")
    for job in jobs:
        print(
            f"{str(job.get('job_id', '')):<34} "
            f"{str(job.get('state', '')):<18} "
            f"{_source_from_status(job):<28} "
            f"{_aoi_from_status(job):<16} "
            f"{str(job.get('updated_at', '')):<24} "
            f"{job.get('message', '')}"
        )
    return 0


def command_retry(args: argparse.Namespace) -> int:
    remote_args = ["retry", args.job_id]
    if args.overwrite:
        remote_args.append("--overwrite")
    if args.force_upload:
        remote_args.append("--force-upload")
    if args.notes:
        remote_args.extend(["--notes", args.notes])
    result = run_ssh(args.host, remote_args)
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    payload = _json_loads(result.stdout)
    new_job_id = payload.get("job_id")
    if new_job_id:
        print(f"new job_id: {new_job_id}")
    elif result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    return 0


def _validation_no_composite(payload: dict[str, Any]) -> bool:
    result = payload.get("result") or {}
    return (
        payload.get("status") == "no_composite"
        or payload.get("state") == "no_composite"
        or payload.get("no_composite") is True
        or (
            "composite_date" in result
            and not result.get("composite_date")
            and payload.get("status") in {"skipped", "no_composite", "succeeded", None}
        )
    )


def command_validate(args: argparse.Namespace) -> int:
    if args.job_id:
        remote_args = ["validate", args.job_id]
    else:
        remote_args = [
            "validate",
            "--source",
            args.source,
            "--aoi",
            args.aoi,
            "--date",
            args.date,
        ]
    result = run_ssh(args.host, remote_args)
    try:
        payload = _json_loads(result.stdout)
    except json.JSONDecodeError:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.returncode != 0:
            _print_completed_error(result)
        return result.returncode
    if _validation_no_composite(payload):
        print("no composite produced; nothing to validate")
        return 0
    verification = (
        payload.get("verification") or payload.get("result", {}).get("verification") or {}
    )
    status = (
        payload.get("status") or payload.get("state") or verification.get("status") or "unknown"
    )
    manifest = payload.get("manifest") or payload.get("result", {}).get("composite_manifest") or ""
    detail = (
        payload.get("detail")
        or payload.get("message")
        or verification.get("detail")
        or verification
    )
    print(f"validation: {status}")
    if manifest:
        print(f"manifest: {manifest}")
    if detail:
        print(f"detail: {detail}")
    if result.returncode != 0:
        _print_completed_error(result)
    return result.returncode


def command_sync_local(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "sync_staging_raster_bundle.py"),
        "--host",
        args.host,
    ]
    if args.job_id:
        command.extend(["--job-id", args.job_id])
    else:
        command.extend(["--source", args.source, "--aoi", args.aoi, "--date", args.date])
    if args.import_local:
        command.append("--import-local")
    if args.verify_local:
        command.append("--verify-local")
    if args.overwrite:
        command.append("--overwrite")
    if args.force_upload:
        command.append("--force-upload")

    result = subprocess.run(command, cwd=REPO_ROOT, text=True, check=False, shell=False)
    return result.returncode


def _run_local_check(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )
    message = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, message


def check_local_seed_write() -> tuple[bool, str]:
    seed_root = REPO_ROOT / "data" / "seed" / "rasters"
    marker = seed_root / ".akasha-cli-doctor-write-test"
    try:
        seed_root.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
        marker.unlink()
        return True, str(seed_root)
    except OSError as exc:
        return False, str(exc)


def _doctor_line(name: str, ok: bool, detail: str = "") -> None:
    status = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"{status} {name}{suffix}")


def command_doctor(args: argparse.Namespace) -> int:
    failures = 0

    ssh_path = shutil.which("ssh")
    _doctor_line("ssh executable", ssh_path is not None, ssh_path or "not found")
    failures += 0 if ssh_path else 1

    if ssh_path:
        remote = run_ssh(args.host, ["doctor"])
        remote_ok = remote.returncode == 0
        _doctor_line(
            "remote wrapper/doctor",
            remote_ok,
            (remote.stdout or remote.stderr or "").strip(),
        )
        failures += 0 if remote_ok else 1
    else:
        failures += 1

    if args.azure_resource_group or args.azure_vm:
        az_path = shutil.which("az")
        _doctor_line("az executable", az_path is not None, az_path or "not found")
        if az_path and args.azure_resource_group and args.azure_vm:
            ok, detail = _run_local_check(
                [
                    "az",
                    "vm",
                    "show",
                    "--resource-group",
                    args.azure_resource_group,
                    "--name",
                    args.azure_vm,
                    "--query",
                    "identity",
                    "-o",
                    "json",
                ]
            )
            _doctor_line("azure VM identity", ok, detail)
            failures += 0 if ok else 1
        else:
            failures += 1

    docker_path = shutil.which("docker")
    _doctor_line("docker executable", docker_path is not None, docker_path or "not found")
    failures += 0 if docker_path else 1
    if docker_path:
        ok, detail = _run_local_check(["docker", "--version"])
        _doctor_line("docker version", ok, detail)
        failures += 0 if ok else 1
        ok, detail = _run_local_check(["docker", "compose", "version"])
        _doctor_line("docker compose version", ok, detail)
        failures += 0 if ok else 1

    ok, detail = check_local_seed_write()
    _doctor_line("data/seed/rasters write access", ok, detail)
    failures += 0 if ok else 1

    return 1 if failures else 0


def _should_redact_key(key: str) -> bool:
    lower = key.lower()
    return any(frag in lower for frag in _REDACT_KEY_FRAGMENTS)


def _redact(obj: Any) -> Any:
    """Recursively redact sensitive keys from a decoded JSON structure."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if _should_redact_key(k) else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    if isinstance(obj, str):
        return _RAW_PATH_RE.sub("[REDACTED_PATH]", obj)
    return obj


def _format_inspect_summary(data: dict[str, Any]) -> str:
    fields = (
        "job_id",
        "state",
        "source_id",
        "aoi_id",
        "window_start",
        "window_end",
        "exit_code",
        "failure_kind",
        "message",
        "composite_date",
        "updated_at",
    )
    lines = [f"{k}: {data[k]}" for k in fields if k in data and data[k] is not None]
    return "\n".join(lines)


def command_job_inspect(args: argparse.Namespace) -> int:
    result = run_ssh(args.host, ["job-inspect", args.job_id])
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    try:
        data = _json_loads(result.stdout)
    except json.JSONDecodeError:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        return result.returncode
    redacted = _redact(data)
    if args.json:
        print(json.dumps(redacted, indent=2, sort_keys=True))
    else:
        print(_format_inspect_summary(redacted))
    return 0


def command_job_artifact(args: argparse.Namespace) -> int:
    remote_args = ["job-artifact", args.job_id, args.artifact]
    if args.operator:
        remote_args.append("--operator")
    result = run_ssh(args.host, remote_args)
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    if not result.stdout:
        return 0
    # Operator mode emits raw output; non-operator output is locally redacted
    # even when the remote wrapper returns path-bearing plain text logs.
    if args.operator:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        return 0
    # Non-operator JSON artifacts: redact before printing.
    try:
        data = _json_loads(result.stdout)
        print(json.dumps(_redact(data), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError):
        redacted = _redact(result.stdout)
        print(redacted, end="" if str(redacted).endswith("\n") else "\n")
    return 0


def _format_schedule_plan_summary(data: dict[str, Any]) -> str:
    fields = (
        "source_id",
        "aoi_id",
        "due",
        "reason",
        "next_window_start",
        "next_window_end",
        "last_run",
        "last_state",
    )
    lines = [f"{k}: {data[k]}" for k in fields if k in data and data[k] is not None]
    return "\n".join(lines)


def command_schedule_plan(args: argparse.Namespace) -> int:
    remote_args = ["schedule-plan", "--source", args.source, "--aoi", args.aoi]
    result = run_ssh(args.host, remote_args)
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    try:
        data = _json_loads(result.stdout)
    except json.JSONDecodeError:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        return result.returncode
    if args.json:
        print(json.dumps(_redact(data), indent=2, sort_keys=True))
    else:
        print(_format_schedule_plan_summary(data))
    return 0


def _format_schedule_next_summary(data: dict[str, Any]) -> str:
    fields = (
        "source_id",
        "aoi_id",
        "next_due",
        "window_start",
        "window_end",
        "cadence_days",
        "reason",
    )
    lines = [f"{k}: {data[k]}" for k in fields if k in data and data[k] is not None]
    return "\n".join(lines)


def command_schedule_next(args: argparse.Namespace) -> int:
    remote_args = ["schedule-next", "--source", args.source, "--aoi", args.aoi]
    result = run_ssh(args.host, remote_args)
    if result.returncode != 0:
        _print_completed_error(result)
        return result.returncode
    try:
        data = _json_loads(result.stdout)
    except json.JSONDecodeError:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        return result.returncode
    print(_format_schedule_next_summary(data))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    trigger = subparsers.add_parser("trigger", help="Submit an ingestion job.")
    _add_host(trigger)
    trigger.add_argument("--source", default=DEFAULT_SOURCE)
    trigger.add_argument("--provider", default="bhoonidhi")
    trigger.add_argument("--aoi", default=DEFAULT_AOI)
    trigger.add_argument("--window-start", default="")
    trigger.add_argument("--window-end", default="")
    trigger.add_argument("--window-days", type=int, default=45)
    trigger.add_argument("--backfill-days", type=int, default=0)
    trigger.add_argument("--backfill-step-days", type=int, default=None)
    trigger.add_argument("--limit", type=int, default=100)
    trigger.add_argument("--max-downloads", type=int, default=3)
    trigger.add_argument("--min-coverage-percent", type=float, default=95.0)
    trigger.add_argument("--dry-run", action="store_true")
    trigger.add_argument("--overwrite", action="store_true")
    trigger.add_argument("--force-upload", action="store_true")
    trigger.add_argument("--retain-raw-downloads", action="store_true")
    trigger.add_argument("--keep-intermediate", action="store_true")
    trigger.add_argument(
        "--input-scale",
        choices=("auto", "linear", "amplitude", "db"),
        default="auto",
        help="EOS-04 source pixel scale for validation prepare step.",
    )
    trigger.add_argument(
        "--polarizations",
        default="",
        help="EOS-04 comma-separated polarizations, e.g. HH,HV or RH,RV.",
    )
    trigger.add_argument("--requested-by", default="")
    trigger.add_argument("--notes", default="")
    trigger.add_argument("--wait", action="store_true")
    trigger.add_argument("--wait-interval", type=float, default=10.0)
    trigger.add_argument("--wait-timeout", type=float, default=1800.0)
    trigger.set_defaults(func=command_trigger)

    status = subparsers.add_parser("status", help="Show job status.")
    _add_host(status)
    status.add_argument("job_id")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    logs = subparsers.add_parser("logs", help="Show or follow job logs.")
    _add_host(logs)
    logs.add_argument("job_id")
    logs.add_argument("--tail", type=int)
    logs.add_argument("--follow", action="store_true")
    logs.set_defaults(func=command_logs)

    list_cmd = subparsers.add_parser("list", help="List recent jobs.")
    _add_host(list_cmd)
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=command_list)

    retry = subparsers.add_parser("retry", help="Retry a failed job.")
    _add_host(retry)
    retry.add_argument("job_id")
    retry.add_argument("--overwrite", action="store_true")
    retry.add_argument("--force-upload", action="store_true")
    retry.add_argument("--notes", default="")
    retry.set_defaults(func=command_retry)

    validate = subparsers.add_parser("validate", help="Validate a job or source/AOI composite.")
    _add_host(validate)
    validate.add_argument("job_id", nargs="?")
    validate.add_argument("--source", default=DEFAULT_SOURCE)
    validate.add_argument("--aoi", default=DEFAULT_AOI)
    validate.add_argument("--date", default="latest")
    validate.set_defaults(func=command_validate)

    sync_local = subparsers.add_parser("sync-local", help="Pull final COGs into local dev.")
    _add_host(sync_local)
    sync_local.add_argument("job_id", nargs="?")
    sync_local.add_argument("--source", default=DEFAULT_SOURCE)
    sync_local.add_argument("--aoi", default=DEFAULT_AOI)
    sync_local.add_argument("--date", default="latest")
    sync_local.add_argument("--import-local", action="store_true")
    sync_local.add_argument("--verify-local", action="store_true")
    sync_local.add_argument("--overwrite", action="store_true")
    sync_local.add_argument("--force-upload", action="store_true")
    sync_local.set_defaults(func=command_sync_local)

    doctor = subparsers.add_parser("doctor", help="Check local and remote prerequisites.")
    _add_host(doctor)
    doctor.add_argument("--azure-resource-group")
    doctor.add_argument("--azure-vm")
    doctor.set_defaults(func=command_doctor)

    job_inspect = subparsers.add_parser(
        "job-inspect",
        help="Fetch a combined redacted job summary from staging artifacts.",
    )
    _add_host(job_inspect)
    job_inspect.add_argument("job_id")
    job_inspect.add_argument("--json", action="store_true", help="Output raw redacted JSON.")
    job_inspect.set_defaults(func=command_job_inspect)

    job_artifact = subparsers.add_parser(
        "job-artifact",
        help="Fetch a specific job artifact (redacted by default).",
    )
    _add_host(job_artifact)
    job_artifact.add_argument("job_id")
    job_artifact.add_argument(
        "artifact",
        choices=ARTIFACT_TYPES,
        help="Artifact type to fetch.",
    )
    job_artifact.add_argument(
        "--operator",
        action="store_true",
        help="Operator mode: emit raw paths/logs without local redaction.",
    )
    job_artifact.set_defaults(func=command_job_artifact)

    schedule_plan = subparsers.add_parser(
        "schedule-plan",
        help="Inspect why a source is or is not due for ingestion.",
    )
    _add_host(schedule_plan)
    schedule_plan.add_argument("--source", default=DEFAULT_SOURCE)
    schedule_plan.add_argument("--aoi", default=DEFAULT_AOI)
    schedule_plan.add_argument("--json", action="store_true", help="Output redacted JSON.")
    schedule_plan.set_defaults(func=command_schedule_plan)

    schedule_next = subparsers.add_parser(
        "schedule-next",
        help="Show the next due run/window from scheduler state.",
    )
    _add_host(schedule_next)
    schedule_next.add_argument("--source", default=DEFAULT_SOURCE)
    schedule_next.add_argument("--aoi", default=DEFAULT_AOI)
    schedule_next.set_defaults(func=command_schedule_next)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
