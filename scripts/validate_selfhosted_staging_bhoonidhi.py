#!/usr/bin/env python3
"""Validate the self-hosted staging Bhoonidhi deployment over SSH.

This script is intentionally stdlib-only so it can be run from an operator
workstation after a Coolify deploy. It verifies that staging is running the
expected immutable image tag, then runs the worker checks that prove the
Phase 3 Bhoonidhi path is healthy enough to enable the systemd timer.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

REPO_ROOT = Path(__file__).resolve().parents[1]
AKASHA_IMAGES = (
    "akasha-web",
    "akasha-api",
    "akasha-ingestion-worker",
    "akasha-ingestion-sar",
)
CheckCommand: TypeAlias = str | list[str]


@dataclass(frozen=True)
class Check:
    name: str
    command: CheckCommand
    timeout_seconds: int = 120
    required: bool = True
    stop_on_failure: bool = False
    remote: bool = True


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def _run_ssh(host: str, command: str, *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    script = command.replace("\r\n", "\n").replace("\r", "\n").encode()
    result = subprocess.run(
        ["ssh", host, "bash", "-s"],
        cwd=REPO_ROOT,
        input=script,
        capture_output=True,
        timeout=timeout_seconds,
    )
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=result.stdout.decode(errors="replace"),
        stderr=result.stderr.decode(errors="replace"),
    )


def _run_local(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def _remote_script(*lines: str) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            *lines,
        ]
    )


def _compose_prefix() -> str:
    return r'''
compose_file="${AKASHA_COMPOSE_FILE:-}"
if [[ -z "${compose_file}" ]]; then
  compose_file="$(
    find /data/coolify/services \
      -mindepth 2 \
      -maxdepth 2 \
      -name docker-compose.yml \
      -print \
      -quit 2>/dev/null || true
  )"
fi
if [[ -z "${compose_file}" || ! -f "${compose_file}" ]]; then
  echo "compose file not found; set AKASHA_COMPOSE_FILE" >&2
  exit 1
fi
compose_dir="$(dirname "${compose_file}")"
cd "${compose_dir}"
echo "compose_file=${compose_file}"
'''


def _checks(args: argparse.Namespace) -> list[Check]:
    expected = shlex.quote(args.expected_sha)
    image_checks = ""
    if not args.skip_image_check:
        image_checks = rf'''
expected_sha={expected}
images="$(docker compose -f "${{compose_file}}" config --images)"
printf "%s\n" "${{images}}"
for image in {' '.join(AKASHA_IMAGES)}; do
  expected_ref="ghcr.io/akasha-techcatalyst/${{image}}:${{expected_sha}}"
  printf "%s\n" "${{images}}" | grep -q "${{expected_ref}}" || {{
    echo "missing expected image tag for ${{image}}:${{expected_sha}}" >&2
    exit 1
  }}
done
for container in web api; do
  name="$(docker compose -f "${{compose_file}}" ps -q "${{container}}")"
  test -n "${{name}}"
  revision="$(
    docker inspect "${{name}}" \
      --format '{{{{ index .Config.Labels "org.opencontainers.image.revision" }}}}'
  )"
  test "${{revision}}" = "${{expected_sha}}" || {{
    echo "${{container}} revision ${{revision}} != ${{expected_sha}}" >&2
    exit 1
  }}
done
'''

    historical_window = ""
    if not args.skip_historical_dry_run:
        historical_window = rf'''
docker compose -f "${{compose_file}}" run --rm --pull never ingestion-worker \
  python worker.py bhoonidhi-sync \
  --source resourcesat-2a-liss3-boa \
  --aoi bangalore-60km \
  --lookback-days 120 \
  --limit 20 \
  --window-start {shlex.quote(args.historical_start)} \
  --window-end {shlex.quote(args.historical_end)} \
  --raw-root /srv/akasha/data/raw/bhoonidhi \
  --out-dir /srv/akasha/data/work/bhoonidhi/staging-validation \
  --ledger-path /srv/akasha/ingestion/staging-validation.sqlite \
  --lock-path /srv/akasha/ingestion/staging-validation.lock \
  --max-downloads 1 \
  --dry-run
'''

    checks = [
        Check(
            "compose image tag and running revision",
            _remote_script(
                _compose_prefix(),
                image_checks or 'docker compose -f "${compose_file}" config --images',
            ),
            stop_on_failure=not args.skip_image_check,
        ),
        Check(
            "container health",
            _remote_script(
                _compose_prefix(),
                r'''
docker compose -f "${compose_file}" ps
for service in web api stac-api titiler postgis minio; do
  id="$(docker compose -f "${compose_file}" ps -q "${service}")"
  test -n "${id}" || { echo "${service} container missing" >&2; exit 1; }
  status="$(
    docker inspect "${id}" \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}'
  )"
  test "${status}" = "healthy" || test "${status}" = "running" || {
    echo "${service} status ${status}" >&2
    exit 1
  }
done
''',
            ),
        ),
        Check(
            "worker verify",
            _remote_script(
                _compose_prefix(),
                (
                    'docker compose -f "${compose_file}" run --rm --pull never '
                    "ingestion-worker python worker.py verify"
                ),
            ),
            timeout_seconds=180,
        ),
        Check(
            "worker verify-cogs",
            _remote_script(
                _compose_prefix(),
                (
                    'docker compose -f "${compose_file}" run --rm --pull never '
                    "ingestion-worker python worker.py verify-cogs"
                ),
            ),
            timeout_seconds=180,
        ),
        Check(
            "Bhoonidhi current-window search exits cleanly",
            _remote_script(
                _compose_prefix(),
                r'''
docker compose -f "${compose_file}" run --rm --pull never ingestion-worker \
  python worker.py bhoonidhi-search \
  --source resourcesat-2a-liss3-boa \
  --aoi bangalore-60km \
  --lookback-days 45 \
  --limit 20 \
  --out-dir /srv/akasha/data/work/bhoonidhi/current-window-validation
''',
            ),
            timeout_seconds=240,
        ),
        Check(
            "Bhoonidhi historical dry-run sync",
            _remote_script(_compose_prefix(), historical_window or "echo skipped"),
            timeout_seconds=300,
            required=not args.skip_historical_dry_run,
        ),
        Check(
            "scheduler systemd timer installed",
            _remote_script(
                "echo skipped"
                if args.skip_timer_check
                else (
                    "systemctl list-unit-files akasha-ingestion-scheduler.timer --no-pager "
                    "| grep -q akasha-ingestion-scheduler.timer"
                ),
            ),
            timeout_seconds=30,
            required=not args.skip_timer_check,
        ),
    ]
    public_smoke = _public_smoke_check(args)
    if public_smoke is not None:
        checks.append(public_smoke)
    return checks


def _public_smoke_check(args: argparse.Namespace) -> Check | None:
    if not args.public_origin:
        return None
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts/smoke-test.py"),
        args.public_origin.rstrip("/"),
    ]
    if args.smoke_login or args.require_monitoring_clean:
        command.append("--login")
    if args.require_raster:
        command.append("--require-raster")
    if args.require_monitoring_clean:
        command.append("--require-monitoring-clean")
    required = (
        args.require_public_smoke
        or args.smoke_login
        or args.require_raster
        or args.require_monitoring_clean
    )
    return Check(
        "public gateway smoke",
        command,
        timeout_seconds=240,
        required=required,
        remote=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.environ.get("AKASHA_STAGING_SSH_HOST", "akasha-staging"),
    )
    parser.add_argument(
        "--expected-sha",
        default=os.environ.get("AKASHA_EXPECTED_IMAGE_TAG") or _git_head(),
    )
    parser.add_argument("--skip-image-check", action="store_true")
    parser.add_argument("--skip-timer-check", action="store_true")
    parser.add_argument("--skip-historical-dry-run", action="store_true")
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Run remaining checks after a required gate fails.",
    )
    parser.add_argument(
        "--public-origin",
        default=os.environ.get("AKASHA_PUBLIC_ORIGIN", ""),
        help=(
            "Optional public gateway origin to validate with scripts/smoke-test.py. "
            "Runs as a warning unless --require-public-smoke, --smoke-login, "
            "--require-raster, or --require-monitoring-clean is set."
        ),
    )
    parser.add_argument(
        "--require-public-smoke",
        action="store_true",
        help="Make --public-origin smoke-test.py failures block validation.",
    )
    parser.add_argument(
        "--smoke-login",
        action="store_true",
        help="Run smoke-test.py --login using AKASHA_SMOKE_USERNAME/PASSWORD.",
    )
    parser.add_argument(
        "--require-raster",
        action="store_true",
        help="Require real tile/statistics raster checks in public smoke.",
    )
    parser.add_argument(
        "--require-monitoring-clean",
        action="store_true",
        help="Require authenticated operator monitoring clean gate in public smoke.",
    )
    parser.add_argument("--historical-start", default="2026-03-19")
    parser.add_argument("--historical-end", default="2026-05-02")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Validating staging host {args.host} for image tag {args.expected_sha}")
    failed = 0
    for check in _checks(args):
        print(f"\n==> {check.name}")
        try:
            if check.remote:
                assert isinstance(check.command, str)
                result = _run_ssh(
                    args.host,
                    check.command,
                    timeout_seconds=check.timeout_seconds,
                )
            else:
                assert isinstance(check.command, list)
                result = _run_local(check.command, timeout_seconds=check.timeout_seconds)
        except subprocess.TimeoutExpired:
            print(f"[FAIL] {check.name}: timed out after {check.timeout_seconds}s")
            failed += 1 if check.required else 0
            if check.required and check.stop_on_failure and not args.continue_after_failure:
                break
            continue
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.returncode == 0:
            print(f"[PASS] {check.name}")
            continue
        if result.stderr.strip():
            print(result.stderr.rstrip(), file=sys.stderr)
        label = "FAIL" if check.required else "WARN"
        print(f"[{label}] {check.name}: exit {result.returncode}")
        failed += 1 if check.required else 0
        if check.required and check.stop_on_failure and not args.continue_after_failure:
            print(
                "Stopping after failed required gate. "
                "Use --continue-after-failure to run all checks."
            )
            break
    if failed:
        print(f"\nValidation failed: {failed} required check(s) failed.")
        return 1
    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
