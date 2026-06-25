#!/usr/bin/env bash
set -euo pipefail

env_file="/etc/akasha/ingestion-jobs.env"
if [[ -f "${env_file}" ]]; then
  # shellcheck source=/dev/null
  source "${env_file}"
fi

JOB_ROOT="${AKASHA_INGESTION_JOB_ROOT:-/srv/akasha/ingestion/jobs}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${AKASHA_INGESTION_RUNNER:-/opt/akasha/bin/akasha-ingestion-job-runner.sh}"
if [[ ! -x "${RUNNER}" && -x "${SCRIPT_DIR}/akasha-ingestion-job-runner.sh" ]]; then
  RUNNER="${SCRIPT_DIR}/akasha-ingestion-job-runner.sh"
fi
TERMINAL_STATES="succeeded failed blocked_by_lock validation_failed cancelled"

usage() {
  cat <<'EOF'
Usage: akasha-ingestion-job.sh <subcommand> [args]

Subcommands:
  start [request.json|-]       Queue a request and launch the runner detached.
  status <job_id>              Print status.json.
  logs <job_id> [--tail N] [--follow]
  list [--limit N]             Print newest jobs as NDJSON.
  retry <job_id> [--overwrite] [--force-upload] [--notes TEXT]
  validate (<job_id>|--source SOURCE --aoi AOI --date latest|YYYY-MM-DD)
  job-inspect <job_id> [--json]
  job-artifact <job_id> <request|status|coverage|download|result|log> [--operator]
  schedule-plan --source SOURCE --aoi AOI [--json]
  schedule-next --source SOURCE --aoi AOI
  doctor                       Check staging-side prerequisites.
  prune                        Delete old terminal job directories.
EOF
}

die() {
  echo "akasha ingestion job: $*" >&2
  exit 2
}

job_dir_for() {
  local job_id="$1"
  [[ "${job_id}" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid job id: ${job_id}"
  printf '%s/%s' "${JOB_ROOT}" "${job_id}"
}

write_request_and_queued_status() {
  local request_path="${1:-}"
  local request_tmp=""
  if [[ -z "${request_path}" || "${request_path}" == "-" ]]; then
    request_tmp="$(mktemp)"
    cat >"${request_tmp}"
    request_path="${request_tmp}"
  fi
  python - "${JOB_ROOT}" "${request_path}" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone
from uuid import uuid4

job_root, request_path = sys.argv[1], sys.argv[2]
with open(request_path, encoding="utf-8") as fh:
  request = json.load(fh)

job_id = request.get("job_id")
if not job_id:
    job_id = "ingest-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    request["job_id"] = job_id
if not re.fullmatch(r"[A-Za-z0-9._-]+", job_id):
    raise SystemExit(f"invalid job_id: {job_id}")

source_id = request.get("source_id", "resourcesat-2a-liss3-boa")
aoi_id = request.get("aoi_id") or request.get("aoi", "bangalore-60km")
request["source_id"] = source_id
request["aoi_id"] = aoi_id
request.setdefault("aoi", aoi_id)

job_dir = os.path.join(job_root, job_id)
os.makedirs(job_dir, mode=0o750, exist_ok=False)
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
status = {
    "job_id": job_id,
    "state": "queued",
    "source_id": source_id,
    "aoi_id": aoi_id,
    "created_at": now,
    "updated_at": now,
    "log_path": os.path.join(job_dir, "job.log"),
    "message": "queued",
}

with open(os.path.join(job_dir, "request.json"), "w", encoding="utf-8") as fh:
    json.dump(request, fh, indent=2, sort_keys=True)
    fh.write("\n")
with open(os.path.join(job_dir, "status.json"), "w", encoding="utf-8") as fh:
    json.dump(status, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(job_id)
PY
  if [[ -n "${request_tmp}" ]]; then
    rm -f "${request_tmp}"
  fi
}

start_job() {
  local request_path="${1:-}"
  mkdir -p "${JOB_ROOT}"
  chmod 750 "${JOB_ROOT}" 2>/dev/null || true
  local job_id
  job_id="$(write_request_and_queued_status "${request_path}")"
  local job_dir
  job_dir="$(job_dir_for "${job_id}")"
  chmod 640 "${job_dir}/request.json" "${job_dir}/status.json"

  if command -v systemd-run >/dev/null 2>&1; then
    local unit="akasha-ingest-job-${job_id}"
    systemctl reset-failed "${unit}.service" >/dev/null 2>&1 || true
    if systemd-run --collect --unit "${unit}" "${RUNNER}" "${job_id}" >"${job_dir}/runner.launch.log" 2>&1; then
      chmod 640 "${job_dir}/runner.launch.log" 2>/dev/null || true
      printf '{"job_id":"%s","state":"queued"}\n' "${job_id}"
      return 0
    fi
    chmod 640 "${job_dir}/runner.launch.log" 2>/dev/null || true
  fi

  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "${RUNNER}" "${job_id}" >>"${job_dir}/runner.launch.log" 2>&1 &
  else
    nohup "${RUNNER}" "${job_id}" >>"${job_dir}/runner.launch.log" 2>&1 &
  fi
  echo "$!" >"${job_dir}/runner.pid"
  chmod 640 "${job_dir}/runner.pid" "${job_dir}/runner.launch.log" 2>/dev/null || true
  printf '{"job_id":"%s","state":"queued"}\n' "${job_id}"
}

status_job() {
  [[ $# -eq 1 ]] || die "status requires <job_id>"
  local job_dir
  job_dir="$(job_dir_for "$1")"
  [[ -f "${job_dir}/status.json" ]] || die "status not found for $1"
  cat "${job_dir}/status.json"
}

logs_job() {
  [[ $# -ge 1 ]] || die "logs requires <job_id>"
  local job_id="$1"
  shift
  local tail_lines=""
  local follow=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tail)
        [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || die "--tail requires a number"
        tail_lines="$2"
        shift 2
        ;;
      --follow)
        follow=true
        shift
        ;;
      *)
        die "unknown logs argument: $1"
        ;;
    esac
  done
  local job_dir log_path
  job_dir="$(job_dir_for "${job_id}")"
  log_path="${job_dir}/job.log"
  touch "${log_path}"
  chmod 640 "${log_path}" 2>/dev/null || true
  if [[ "${follow}" == "true" ]]; then
    if [[ -n "${tail_lines}" ]]; then
      tail -n "${tail_lines}" -F "${log_path}" &
    else
      tail -n +1 -F "${log_path}" &
    fi
    local tail_pid=$!
    while kill -0 "${tail_pid}" >/dev/null 2>&1; do
      local state
      state="$(python - "${job_dir}/status.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("state", "unknown"))
PY
)"
      if [[ " ${TERMINAL_STATES} " == *" ${state} "* ]]; then
        sleep 1
        kill "${tail_pid}" >/dev/null 2>&1 || true
        wait "${tail_pid}" 2>/dev/null || true
        return 0
      fi
      sleep 2
    done
  elif [[ -n "${tail_lines}" ]]; then
    tail -n "${tail_lines}" "${log_path}"
  else
    cat "${log_path}"
  fi
}

redact_json_file() {
  local file_path="$1"
  python - "${file_path}" <<'PY'
import json
import re
import sys

path = sys.argv[1]
secret_fragments = ("password", "secret", "token", "api_key", "access_key", "credential", "authorization")
raw_path_re = re.compile(r"((?:/srv/akasha|/data/coolify|/var/lib/docker|/tmp|/var/tmp)/[^\s\"']+)")

def redact(value):
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(f in k.lower() for f in secret_fragments) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return raw_path_re.sub("[REDACTED_PATH]", value)
    return value

with open(path, encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps(redact(payload), sort_keys=True))
PY
}

redact_text_file() {
  local file_path="$1"
  python - "${file_path}" <<'PY'
import re
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8", errors="replace").read()
text = re.sub(r"((?:/srv/akasha|/data/coolify|/var/lib/docker|/tmp|/var/tmp)/[^\s\"']+)", "[REDACTED_PATH]", text)
text = re.sub(r"(?i)(Bearer|Basic|Token)\s+[A-Za-z0-9+/=._-]{8,}", r"\1 [REDACTED]", text)
text = re.sub(r"(?i)(password|secret|token|api[_-]?key|access[_-]?key|credential)(=|:)\s*[^,\s]+", r"\1\2[REDACTED]", text)
print(text, end="" if text.endswith("\n") else "\n")
PY
}

artifact_path_for() {
  local job_dir="$1"
  local artifact="$2"
  case "${artifact}" in
    request) printf '%s/request.json' "${job_dir}" ;;
    status) printf '%s/status.json' "${job_dir}" ;;
    result) printf '%s/result.json' "${job_dir}" ;;
    log) printf '%s/job.log' "${job_dir}" ;;
    coverage) find "${job_dir}" -name 'coverage_manifest*.json' -print -quit 2>/dev/null ;;
    download) find "${job_dir}" -name 'download_manifest*.json' -print -quit 2>/dev/null ;;
    *) return 1 ;;
  esac
}

inspect_job() {
  [[ $# -ge 1 ]] || die "job-inspect requires <job_id>"
  local job_id="$1"
  local job_dir
  job_dir="$(job_dir_for "${job_id}")"
  [[ -d "${job_dir}" ]] || die "job not found: ${job_id}"
  python - "${job_dir}" <<'PY'
import json
import os
import re
import sys

job_dir = sys.argv[1]
secret_fragments = ("password", "secret", "token", "api_key", "access_key", "credential", "authorization")
raw_path_re = re.compile(r"((?:/srv/akasha|/data/coolify|/var/lib/docker|/tmp|/var/tmp)/[^\s\"']+)")

def load(name):
    path = os.path.join(job_dir, name)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def redact(value):
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(f in k.lower() for f in secret_fragments) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return raw_path_re.sub("[REDACTED_PATH]", value)
    return value

status = load("status.json")
request = load("request.json")
result = load("result.json")
observability = load("observability.json")
summary = {
    **status,
    "request": request,
    "result": result,
    "observability": observability,
    "artifactHandles": {
        "request": f"{status.get('job_id') or request.get('job_id')}:request",
        "status": f"{status.get('job_id') or request.get('job_id')}:status",
        "result": f"{status.get('job_id') or request.get('job_id')}:result",
        "log": f"{status.get('job_id') or request.get('job_id')}:log",
    },
}
print(json.dumps(redact(summary), sort_keys=True))
PY
}

job_artifact() {
  [[ $# -ge 2 ]] || die "job-artifact requires <job_id> <artifact>"
  local job_id="$1"
  local artifact="$2"
  shift 2
  local operator=false
  if [[ $# -gt 0 ]]; then
    [[ "$1" == "--operator" && $# -eq 1 ]] || die "invalid job-artifact arguments"
    operator=true
  fi
  local job_dir artifact_path
  job_dir="$(job_dir_for "${job_id}")"
  [[ -d "${job_dir}" ]] || die "job not found: ${job_id}"
  artifact_path="$(artifact_path_for "${job_dir}" "${artifact}")"
  [[ -n "${artifact_path}" && -f "${artifact_path}" ]] || die "artifact not found: ${artifact}"
  if [[ "${operator}" == "true" ]]; then
    cat "${artifact_path}"
    return 0
  fi
  if [[ "${artifact}" == "log" ]]; then
    redact_text_file "${artifact_path}"
  else
    redact_json_file "${artifact_path}"
  fi
}

list_jobs() {
  local limit=20
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --limit)
        [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || die "--limit requires a number"
        limit="$2"
        shift 2
        ;;
      *)
        die "unknown list argument: $1"
        ;;
    esac
  done
  python - "${JOB_ROOT}" "${limit}" <<'PY'
import json
import os
import sys

job_root, limit = sys.argv[1], int(sys.argv[2])
rows = []
if os.path.isdir(job_root):
    for name in os.listdir(job_root):
        status_path = os.path.join(job_root, name, "status.json")
        if not os.path.isfile(status_path):
            continue
        try:
            with open(status_path, encoding="utf-8") as fh:
                status = json.load(fh)
        except Exception:
            continue
        rows.append((os.path.getmtime(status_path), status))
for _, status in sorted(rows, reverse=True)[:limit]:
    print(json.dumps(status, sort_keys=True))
PY
}

retry_job() {
  [[ $# -ge 1 ]] || die "retry requires <job_id>"
  local old_job_id="$1"
  shift
  local overwrite=false
  local force_upload=false
  local notes=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --overwrite)
        overwrite=true
        shift
        ;;
      --force-upload)
        force_upload=true
        shift
        ;;
      --notes)
        [[ $# -ge 2 ]] || die "--notes requires text"
        notes="$2"
        shift 2
        ;;
      *)
        die "unknown retry argument: $1"
        ;;
    esac
  done
  local old_dir
  old_dir="$(job_dir_for "${old_job_id}")"
  [[ -f "${old_dir}/request.json" ]] || die "request not found for ${old_job_id}"
  python - "${old_dir}/request.json" "${overwrite}" "${force_upload}" "${notes}" <<'PY' | start_job "-"
import json
import sys
from datetime import datetime, timezone
from uuid import uuid4

request_path, overwrite, force_upload, notes = sys.argv[1:]
with open(request_path, encoding="utf-8") as fh:
    request = json.load(fh)
request["job_id"] = "ingest-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
request["dry_run"] = False
if overwrite == "true":
    request["overwrite"] = True
if force_upload == "true":
    request["force_upload"] = True
if notes:
    prior = request.get("notes")
    request["notes"] = f"{prior}; retry: {notes}" if prior else f"retry: {notes}"
json.dump(request, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
PY
}

validate_job() {
  "${RUNNER}" --validate "$@"
}

doctor_job() {
  "${RUNNER}" --doctor
}

prune_jobs() {
  python - "${JOB_ROOT}" "${AKASHA_INGESTION_LOG_RETENTION_DAYS:-14}" <<'PY'
import json
import os
import shutil
import sys
import time

job_root, days = sys.argv[1], int(sys.argv[2])
terminal = {"succeeded", "failed", "blocked_by_lock", "validation_failed", "cancelled"}
cutoff = time.time() - days * 86400
if not os.path.isdir(job_root):
    raise SystemExit(0)
for name in os.listdir(job_root):
    job_dir = os.path.join(job_root, name)
    status_path = os.path.join(job_dir, "status.json")
    if not os.path.isfile(status_path):
        continue
    try:
        with open(status_path, encoding="utf-8") as fh:
            state = json.load(fh).get("state")
    except Exception:
        continue
    if state in terminal and os.path.getmtime(status_path) < cutoff:
        shutil.rmtree(job_dir)
        print(name)
PY
}

schedule_inspect() {
  local subcommand="$1"
  shift
  local compose_file="${AKASHA_COMPOSE_FILE:-}"
  if [[ -z "${compose_file}" ]]; then
    if [[ -f /srv/akasha/coolify-compose.yml ]]; then
      compose_file="/srv/akasha/coolify-compose.yml"
    else
      compose_file="$(find /data/coolify/services -mindepth 2 -maxdepth 2 -name docker-compose.yml -print -quit 2>/dev/null || true)"
    fi
  fi
  [[ -n "${compose_file}" && -f "${compose_file}" ]] || die "compose file not found; set AKASHA_COMPOSE_FILE"

  local compose_args=()
  if [[ -n "${AKASHA_COMPOSE_PROJECT:-}" ]]; then
    compose_args=(-p "${AKASHA_COMPOSE_PROJECT}")
  fi

  local worker_cmd=("${subcommand}" "$@")
  if [[ "${subcommand}" == "schedule-plan" ]]; then
    worker_cmd+=(--json)
  fi

  docker compose "${compose_args[@]}" -f "${compose_file}" \
    run --rm --pull "${AKASHA_SYNC_PULL_POLICY:-never}" \
    ingestion-worker \
    python worker.py "${worker_cmd[@]}"
}

case "${1:-}" in
  start)
    shift
    [[ $# -le 1 ]] || die "start accepts at most one request path"
    start_job "${1:-}"
    ;;
  status)
    shift
    status_job "$@"
    ;;
  logs)
    shift
    logs_job "$@"
    ;;
  list)
    shift
    list_jobs "$@"
    ;;
  retry)
    shift
    retry_job "$@"
    ;;
  validate)
    shift
    validate_job "$@"
    ;;
  job-inspect)
    shift
    inspect_job "$@"
    ;;
  job-artifact)
    shift
    job_artifact "$@"
    ;;
  schedule-plan|schedule-next)
    subcommand="$1"
    shift
    schedule_inspect "${subcommand}" "$@"
    ;;
  doctor)
    shift
    [[ $# -eq 0 ]] || die "doctor takes no arguments"
    doctor_job
    ;;
  prune)
    shift
    [[ $# -eq 0 ]] || die "prune takes no arguments"
    prune_jobs
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    die "unknown subcommand: $1"
    ;;
esac
