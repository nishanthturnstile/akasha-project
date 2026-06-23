#!/usr/bin/env bash
set -euo pipefail

env_file="/etc/akasha/ingestion-jobs.env"
if [[ -f "${env_file}" ]]; then
  # shellcheck source=/dev/null
  source "${env_file}"
fi

JOB_ROOT="${AKASHA_INGESTION_JOB_ROOT:-/srv/akasha/ingestion/jobs}"
RAW_ROOT="${AKASHA_SYNC_RAW_ROOT:-/srv/akasha/data/raw/bhoonidhi}"
TEMP_ROOT="${AKASHA_SYNC_TEMP_ROOT:-/srv/akasha/data/work/bhoonidhi}"
LEDGER_PATH="${AKASHA_SYNC_LEDGER_PATH:-/srv/akasha/ingestion/ledger.sqlite}"

now_utc() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

redact_stream() {
  sed -E \
    -e 's#(S3_SECRET_KEY|AKASHA_OBJECT_STORAGE_SECRET_KEY|AWS_SECRET_ACCESS_KEY)=[^[:space:]&]+#\1=[REDACTED]#g' \
    -e 's#([A-Z0-9_]*(SECRET|TOKEN|PASSWORD|KEY)[A-Z0-9_]*)=[^[:space:]&]+#\1=[REDACTED]#g' \
    -e 's#(password|passwd|secret|token|access[_-]?key|signature|credential)(=|:)[^[:space:]&]+#\1\2[REDACTED]#Ig' \
    -e 's#(X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token)=[^&[:space:]]+#\1=[REDACTED]#Ig' \
    -e 's#s3://[^[:space:]]+#s3://[REDACTED]#g' \
    -e 's#https?://[^[:space:]]*(token|signature|X-Amz)[^[:space:]]*#https://[REDACTED]#Ig' \
    -e 's#([A-Za-z0-9.-]+\.(internal|local|lan))#[REDACTED-HOST]#Ig'
}

discover_compose() {
  local default_compose_file="/srv/akasha/coolify-compose.yml"
  if [[ -n "${AKASHA_COMPOSE_FILE:-}" ]]; then
    compose_file="${AKASHA_COMPOSE_FILE}"
  elif [[ -f "${default_compose_file}" ]]; then
    compose_file="${default_compose_file}"
  else
    compose_file="$(find /data/coolify/services -mindepth 2 -maxdepth 2 -name docker-compose.yml -print -quit 2>/dev/null || true)"
  fi
  if [[ -z "${compose_file:-}" || ! -f "${compose_file}" ]]; then
    return 1
  fi
  compose_dir="$(dirname "${compose_file}")"
  compose_args=()
  if [[ -n "${AKASHA_COMPOSE_PROJECT:-}" ]]; then
    compose_args=(-p "${AKASHA_COMPOSE_PROJECT}")
  fi
  pull_policy="${AKASHA_SYNC_PULL_POLICY:-never}"
  # The default policy expands to the safe command contract: docker compose ... --pull never.
}

update_status() {
  local state="$1"
  local exit_code="${2:-}"
  local failure_kind="${3:-}"
  local message="${4:-}"
  python - "${status_path}" "${state}" "${exit_code}" "${failure_kind}" "${message}" "${log_path}" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, state, exit_code, failure_kind, message, log_path = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as fh:
        status = json.load(fh)
except FileNotFoundError:
    status = {}
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
status["state"] = state
status["updated_at"] = now
status["log_path"] = log_path
if state == "running":
    status.setdefault("started_at", now)
if state != "running":
    status["completed_at"] = now
if exit_code != "":
    status["exit_code"] = int(exit_code)
if failure_kind:
    status["failure_kind"] = failure_kind
if message:
    status["message"] = message
with open(path, "w", encoding="utf-8") as fh:
    json.dump(status, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
  chmod 640 "${status_path}" 2>/dev/null || true
}

load_request() {
  eval "$(
    python - "${request_path}" \
      "${AKASHA_INGESTION_DEFAULT_MAX_DOWNLOADS:-3}" \
      "${AKASHA_INGESTION_DEFAULT_MIN_COVERAGE_PERCENT:-95}" <<'PY'
import json
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone

path, default_max, default_min = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with open(path, encoding="utf-8") as fh:
    req = json.load(fh)

def value(*names, default=None):
    for name in names:
        if name in req and req[name] not in (None, ""):
            return req[name]
    return default

def safe(name, raw, pattern=r"[A-Za-z0-9._:/,+@ -]+"):
    raw = str(raw)
    if not re.fullmatch(pattern, raw):
        raise SystemExit(f"invalid {name}: {raw}")
    return raw

source = safe("source_id", value("source_id", "source", default="resourcesat-2a-liss3-boa"), r"[A-Za-z0-9._-]+")
aoi = safe("aoi_id", value("aoi_id", "aoi", default="bangalore-60km"), r"[A-Za-z0-9._-]+")
window_days = int(value("window_days", default=45))
window_end = value("window_end", default=datetime.now(timezone.utc).date().isoformat())
window_start = value(
    "window_start",
    default=(datetime.fromisoformat(window_end).date() - timedelta(days=window_days - 1)).isoformat(),
)
fields = {
    "source_id": source,
    "aoi_id": aoi,
    "limit": int(value("limit", default=100)),
    "window_days": window_days,
    "window_start": safe("window_start", window_start, r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    "window_end": safe("window_end", window_end, r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    "max_downloads": int(value("max_downloads", default=default_max)),
    "min_coverage_percent": str(value("min_coverage_percent", default=default_min)),
    "backfill_days": str(value("backfill_days", default="0")),
    "backfill_step_days": str(value("backfill_step_days", default="")),
    "dry_run": str(bool(value("dry_run", default=False))).lower(),
    "overwrite": str(bool(value("overwrite", default=False))).lower(),
    "force_upload": str(bool(value("force_upload", default=False))).lower(),
    "retain_raw_downloads": str(bool(value("retain_raw_downloads", default=False))).lower(),
    "keep_intermediate": str(bool(value("keep_intermediate", default=False))).lower(),
}
for key, val in fields.items():
    print(f"{key}={shlex.quote(str(val))}")
PY
  )"
}

csv_contains() {
  local csv="$1"
  local needle="$2"
  IFS=',' read -r -a parts <<<"${csv}"
  for raw in "${parts[@]}"; do
    local item
    item="$(printf '%s' "${raw}" | xargs)"
    if [[ "${item}" == "${needle}" ]]; then
      return 0
    fi
  done
  return 1
}

compose_has_bhoonidhi_env() {
  grep -Eq "BHOONIDHI_USER_ID|BHOONIDHI_PASSWORD" "${compose_file}"
}

other_active_job_exists() {
  python - "${JOB_ROOT}" "${job_id}" "${source_id}" "${aoi_id}" <<'PY'
import json
import os
import sys

root, current_job, source, aoi = sys.argv[1:]
active = {"queued", "running"}
if not os.path.isdir(root):
    raise SystemExit(1)
for name in os.listdir(root):
    if name == current_job:
        continue
    status_path = os.path.join(root, name, "status.json")
    if not os.path.isfile(status_path):
        continue
    try:
        with open(status_path, encoding="utf-8") as fh:
            status = json.load(fh)
    except Exception:
        continue
    if (
        status.get("state") in active
        and status.get("source_id") == source
        and status.get("aoi_id") == aoi
    ):
        raise SystemExit(0)
raise SystemExit(1)
PY
}

write_result_json() {
  local exit_code="$1"
  python - "${request_path}" "${result_path}" "${TEMP_ROOT}" "${source_id}" "${aoi_id}" "${window_start}" "${window_end}" "${LEDGER_PATH}" "${exit_code}" <<'PY'
import glob
import json
import os
import sys

request_path, result_path, temp_root, source, aoi, window_start, window_end, ledger, exit_code = sys.argv[1:]
base = os.path.join(temp_root, source, aoi)
coverage = sorted(glob.glob(os.path.join(base, "**", "*coverage*manifest*.json"), recursive=True))
downloads = sorted(glob.glob(os.path.join(base, "**", "*download*manifest*.json"), recursive=True))
composites = sorted(glob.glob(os.path.join(base, "**", "prepare_manifest.json"), recursive=True))
composite_manifest = composites[-1] if composites else ""
composite_dir = os.path.dirname(composite_manifest) if composite_manifest else ""
analytic = os.path.join(composite_dir, "analytic.tif") if composite_dir else ""
mask = os.path.join(composite_dir, "mask.tif") if composite_dir else ""
composite_date = ""
if composite_dir:
    composite_date = os.path.basename(composite_dir)
result = {
    "source_id": source,
    "aoi_id": aoi,
    "window_start": window_start,
    "window_end": window_end,
    "ledger_path": ledger,
    "coverage_manifest": coverage,
    "download_manifest": downloads,
    "composite_manifest": composite_manifest,
    "analytic_cog": analytic if os.path.exists(analytic) else "",
    "mask_cog": mask if os.path.exists(mask) else "",
    "composite_date": composite_date,
    "verification_status": "not_run",
    "exit_code": int(exit_code),
}
with open(result_path, "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
  chmod 640 "${result_path}" 2>/dev/null || true
}

preflight() {
  [[ -d "${job_dir}" ]] || { update_status failed 2 preflight "job directory missing"; exit 2; }
  [[ -f "${request_path}" ]] || { update_status failed 2 preflight "request.json missing"; exit 2; }
  if [[ -e /srv/akasha && ! -w /srv/akasha ]]; then
    update_status failed 2 preflight "/srv/akasha is not writable"
    exit 2
  fi
  mkdir -p "${RAW_ROOT}" "${TEMP_ROOT}" "$(dirname "${LEDGER_PATH}")"
  discover_compose || { update_status failed 2 preflight "compose file not found; set AKASHA_COMPOSE_FILE"; exit 2; }
  grep -q "ingestion-worker" "${compose_file}" || { update_status failed 2 preflight "compose file does not include ingestion-worker"; exit 2; }
  compose_has_bhoonidhi_env || { update_status failed 2 preflight "compose file does not expose Bhoonidhi credentials to ingestion-worker"; exit 2; }
  csv_contains "${AKASHA_INGESTION_ALLOWED_SOURCES:-resourcesat-2a-liss3-boa,resourcesat-2a-liss4-mx70-l2,resourcesat-2a-awifs-boa}" "${source_id}" || {
    update_status failed 2 validation "source is not allowed"
    exit 2
  }
  csv_contains "${AKASHA_INGESTION_ALLOWED_AOIS:-bangalore-60km}" "${aoi_id}" || {
    update_status failed 2 validation "AOI is not allowed"
    exit 2
  }
  if other_active_job_exists; then
    update_status blocked_by_lock 75 lock "another queued/running job exists for source/AOI"
    exit 75
  fi
  worker_lock_path="/srv/akasha/ingestion/bhoonidhi-sync.${aoi_id}.worker.lock"
  mkdir -p "$(dirname "${worker_lock_path}")"
  if ! flock -n "${worker_lock_path}" -c true; then
    update_status blocked_by_lock 75 lock "shared worker lock is held"
    exit 75
  fi
}

run_job() {
  job_id="$1"
  [[ "${job_id}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid job id" >&2; exit 2; }
  job_dir="${JOB_ROOT}/${job_id}"
  request_path="${job_dir}/request.json"
  status_path="${job_dir}/status.json"
  command_path="${job_dir}/command.txt"
  log_path="${job_dir}/job.log"
  result_path="${job_dir}/result.json"
  touch "${log_path}"
  chmod 640 "${log_path}"
  if ! load_request; then
    update_status validation_failed 2 validation "invalid request.json"
    echo "invalid request.json" | redact_stream >>"${log_path}"
    exit 2
  fi
  preflight

  update_status running "" "" "running"
  local sync_args=(
    bhoonidhi-sync
    --source "${source_id}"
    --aoi "${aoi_id}"
    --limit "${limit}"
    --window-days "${window_days}"
    --raw-root "${RAW_ROOT}"
    --out-dir "${TEMP_ROOT}"
    --ledger-path "${LEDGER_PATH}"
    --max-downloads "${max_downloads}"
    --min-coverage-percent "${min_coverage_percent}"
    --lock-path "${worker_lock_path}"
  )
  if [[ "${backfill_days}" != "0" ]]; then
    sync_args+=(--backfill-days "${backfill_days}")
    if [[ -n "${backfill_step_days}" ]]; then
      sync_args+=(--backfill-step-days "${backfill_step_days}")
    fi
  else
    sync_args+=(--window-start "${window_start}" --window-end "${window_end}")
  fi
  [[ "${dry_run}" == "true" ]] && sync_args+=(--dry-run)
  [[ "${overwrite}" == "true" ]] && sync_args+=(--overwrite)
  [[ "${force_upload}" == "true" ]] && sync_args+=(--force)
  [[ "${retain_raw_downloads}" == "true" ]] && sync_args+=(--retain-raw-downloads)
  [[ "${keep_intermediate}" == "true" ]] && sync_args+=(--keep-intermediate)

  {
    printf '%q ' docker compose "${compose_args[@]}" -f "${compose_file}" run --rm --pull "${pull_policy}" ingestion-worker python worker.py "${sync_args[@]}"
    printf '\n'
  } | redact_stream >"${command_path}"
  chmod 640 "${command_path}"

  cd "${compose_dir}"
  set +e
  docker compose "${compose_args[@]}" -f "${compose_file}" run --rm --pull "${pull_policy}" ingestion-worker \
    python worker.py "${sync_args[@]}" 2>&1 | redact_stream | tee -a "${log_path}"
  local exit_code=${PIPESTATUS[0]}
  set -e

  write_result_json "${exit_code}"
  if [[ "${exit_code}" -eq 0 ]]; then
    update_status succeeded 0 "" "worker completed"
  elif grep -Eiq "validation|verify|coverage" "${log_path}"; then
    update_status validation_failed "${exit_code}" validation "worker validation failed"
  else
    update_status failed "${exit_code}" worker "worker failed"
  fi
  exit "${exit_code}"
}

doctor() {
  discover_compose || { echo "compose: missing"; exit 1; }
  echo "compose=${compose_file}"
  grep -q "ingestion-worker" "${compose_file}" || { echo "ingestion-worker: missing"; exit 1; }
  compose_has_bhoonidhi_env || { echo "bhoonidhi env: missing from compose"; exit 1; }
  command -v docker >/dev/null 2>&1 || { echo "docker: missing"; exit 1; }
  mkdir -p "${JOB_ROOT}" "${RAW_ROOT}" "${TEMP_ROOT}" "$(dirname "${LEDGER_PATH}")"
  [[ -w "${JOB_ROOT}" ]] || { echo "job root not writable: ${JOB_ROOT}"; exit 1; }
  echo "job_root=${JOB_ROOT}"
  echo "pull_policy=${AKASHA_SYNC_PULL_POLICY:-never}"
}

validate_target() {
  discover_compose || { echo "compose: missing"; exit 1; }
  local manifest=""
  if [[ $# -eq 1 && "$1" =~ ^[A-Za-z0-9._-]+$ ]]; then
    local job_result="${JOB_ROOT}/$1/result.json"
    [[ -f "${job_result}" ]] || { echo "result.json not found for $1"; exit 2; }
    manifest="$(python - "${job_result}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("composite_manifest", ""))
PY
)"
  else
    local source_id="resourcesat-2a-liss3-boa"
    local aoi_id="bangalore-60km"
    local date_selector="latest"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --source)
          [[ $# -ge 2 ]] || { echo "--source requires a value" >&2; exit 2; }
          source_id="$2"
          shift 2
          ;;
        --aoi)
          [[ $# -ge 2 ]] || { echo "--aoi requires a value" >&2; exit 2; }
          aoi_id="$2"
          shift 2
          ;;
        --date)
          [[ $# -ge 2 ]] || { echo "--date requires a value" >&2; exit 2; }
          date_selector="$2"
          shift 2
          ;;
        *)
          echo "unknown validate argument: $1" >&2
          exit 2
          ;;
      esac
    done
    manifest="$(python - "${TEMP_ROOT}" "${source_id}" "${aoi_id}" "${date_selector}" <<'PY'
import glob
import os
import re
import sys

temp_root, source, aoi, date_selector = sys.argv[1:]
if not re.fullmatch(r"[A-Za-z0-9._-]+", source):
    raise SystemExit("invalid source")
if not re.fullmatch(r"[A-Za-z0-9._-]+", aoi):
    raise SystemExit("invalid aoi")
if date_selector != "latest" and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_selector):
    raise SystemExit("invalid date; expected latest or YYYY-MM-DD")
base = os.path.join(temp_root, source, aoi)
if date_selector == "latest":
    matches = sorted(glob.glob(os.path.join(base, "**", "prepare_manifest.json"), recursive=True))
else:
    matches = sorted(glob.glob(os.path.join(base, "**", date_selector, "prepare_manifest.json"), recursive=True))
print(matches[-1] if matches else "")
PY
)"
  fi
  if [[ -z "${manifest}" ]]; then
    echo "no composite produced; nothing to validate"
    exit 0
  fi
  cd "${compose_dir}"
  docker compose "${compose_args[@]}" -f "${compose_file}" run --rm --pull "${pull_policy}" ingestion-worker \
    python worker.py verify-composite --manifest "${manifest}"
}

case "${1:-}" in
  --doctor)
    doctor
    ;;
  --validate)
    shift
    validate_target "$@"
    ;;
  "")
    echo "job id required" >&2
    exit 2
    ;;
  *)
    run_job "$1"
    ;;
esac
