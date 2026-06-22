#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import os
import re
import shlex
import sys

wrapper = "/opt/akasha/bin/akasha-ingestion-job.sh"
allowed = {"start", "status", "logs", "list", "retry", "validate", "doctor", "prune"}
job_id = re.compile(r"^[A-Za-z0-9._-]+$")
safe_path = re.compile(r"^[A-Za-z0-9._=:/,@+-]+$")
safe_id = re.compile(r"^[A-Za-z0-9._-]+$")
safe_date = re.compile(r"^(latest|[0-9]{4}-[0-9]{2}-[0-9]{2})$")
safe_text = re.compile(r"^[A-Za-z0-9 .,:;_@+=/\-]+$")

def fail(message: str) -> None:
    raise SystemExit(message)

def require_job(value: str) -> None:
    if not job_id.fullmatch(value):
        fail(f"invalid job id: {value!r}")

def require_id(value: str, name: str) -> None:
    if not safe_id.fullmatch(value):
        fail(f"invalid {name}: {value!r}")

def require_date(value: str) -> None:
    if not safe_date.fullmatch(value):
        fail("invalid --date value; expected latest or YYYY-MM-DD")

def require_safe(value: str, name: str = "argument") -> None:
    if not safe_path.fullmatch(value):
        fail(f"invalid {name}: {value!r}")

def validate_args(argv: list[str]) -> None:
    subcommand, rest = argv[0], argv[1:]
    if subcommand == "start":
        if len(rest) > 1:
            fail("start accepts at most one request path")
        if rest and rest[0] != "-":
            require_safe(rest[0], "request path")
        return
    if subcommand == "status":
        if len(rest) != 1:
            fail("status requires one job id")
        require_job(rest[0])
        return
    if subcommand == "logs":
        if not rest:
            fail("logs requires a job id")
        require_job(rest[0])
        i = 1
        while i < len(rest):
            if rest[i] == "--follow":
                i += 1
            elif rest[i] == "--tail":
                if i + 1 >= len(rest) or not rest[i + 1].isdigit():
                    fail("--tail requires a numeric value")
                i += 2
            else:
                fail(f"invalid logs argument: {rest[i]!r}")
        return
    if subcommand == "list":
        if not rest:
            return
        if len(rest) == 2 and rest[0] == "--limit" and rest[1].isdigit():
            return
        fail("invalid list arguments")
    if subcommand == "retry":
        if not rest:
            fail("retry requires a job id")
        require_job(rest[0])
        i = 1
        while i < len(rest):
            if rest[i] in {"--overwrite", "--force-upload"}:
                i += 1
            elif rest[i] == "--notes":
                if i + 1 >= len(rest) or not safe_text.fullmatch(rest[i + 1]):
                    fail("--notes requires safe text")
                i += 2
            else:
                fail(f"invalid retry argument: {rest[i]!r}")
        return
    if subcommand == "validate":
        if len(rest) == 1:
            require_job(rest[0])
            return
        i = 0
        seen = set()
        while i < len(rest):
            if rest[i] not in {"--source", "--aoi", "--date"}:
                fail(f"invalid validate argument: {rest[i]!r}")
            if i + 1 >= len(rest):
                fail(f"{rest[i]} requires a value")
            if rest[i] in {"--source", "--aoi"}:
                require_id(rest[i + 1], rest[i])
            else:
                require_date(rest[i + 1])
            seen.add(rest[i])
            i += 2
        if seen != {"--source", "--aoi", "--date"}:
            fail("validate requires source, aoi, and date in explicit mode")
        return
    if subcommand in {"doctor", "prune"}:
        if rest:
            fail(f"{subcommand} takes no arguments")
        return
    fail("command not allowed")

command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
if not command:
    fail("missing SSH_ORIGINAL_COMMAND")
try:
    argv = shlex.split(command)
except ValueError as exc:
    fail(f"invalid command: {exc}")
if argv and os.path.basename(argv[0]) == "akasha-ingestion-job.sh":
    argv = argv[1:]
if not argv or argv[0] not in allowed:
    fail("command not allowed")
validate_args(argv)
os.execv(wrapper, [wrapper, *argv])
PY
