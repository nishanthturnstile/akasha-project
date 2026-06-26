#!/usr/bin/env bash
# Akasha ingestion scheduler wrapper — safe orchestrator for the one-timer multi-source model.
#
# Design: runs schedule-plan (plan/dry-run only) by default. Three explicit overrides
# are required for a live run:
#   AKASHA_SCHEDULER_ACTIVE=true
#   AKASHA_SCHEDULER_APPROVED_RUNTIME=true
#   AKASHA_SCHEDULER_DRY_RUN=false
#
# ROLLBACK: sudo systemctl disable --now akasha-ingestion-scheduler.timer
#           Use akasha-ingestion-job.sh for bounded manual scheduler runs while
#           the timer is paused. Deleted Bhoonidhi timers are not rollback targets.
#
# STAGING GUARDRAILS enforced here:
#   - All data stays on /srv/akasha (no /tmp, /, /var/tmp, /var/lib/docker).
#   - Global scheduler lock: /srv/akasha/ingestion/scheduler.global.lock (held by flock
#     in the service unit). Worker source/AOI locks live in the same directory
#     for both automatic and manual scheduler jobs.
#   - ionice/nice applied to docker compose runs.
#   - Secrets and S3/MinIO paths are redacted from all log output.
#   - No direct heavy ad hoc downloads: this script only invokes schedule-plan or
#     schedule-due-sources; heavy ingestion is dispatched through the orchestrator.
#   - Approved-runtime signal (--approved-runtime) is passed to the worker only when
#     both AKASHA_SCHEDULER_ACTIVE=true and AKASHA_SCHEDULER_APPROVED_RUNTIME=true.
#   - Rollback-friendly: each run logs timer name, commit, and cutover state summary.

set -euo pipefail

log() {
  printf '[%s] akasha-scheduler: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Redact secrets and internal paths from docker compose output before it reaches
# the journal. Mirrors the redact_stream function in akasha-ingestion-job-runner.sh.
redact_stream() {
  sed -E \
    -e 's#(S3_SECRET_KEY|AKASHA_OBJECT_STORAGE_SECRET_KEY|AWS_SECRET_ACCESS_KEY|AKASHA_BHOONIDHI_PASSWORD)=[^[:space:]&]+#\1=[REDACTED]#g' \
    -e 's#([A-Z0-9_]*(SECRET|TOKEN|PASSWORD|KEY)[A-Z0-9_]*)=[^[:space:]&]+#\1=[REDACTED]#g' \
    -e 's#(password|passwd|secret|token|access[_-]?key|signature|credential)(=|:)[^[:space:]&]+#\1\2[REDACTED]#Ig' \
    -e 's#(X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token)=[^&[:space:]]+#\1=[REDACTED]#Ig' \
    -e 's#s3://[^[:space:]]+#s3://[REDACTED]#g' \
    -e 's#https?://[^[:space:]]*(token|signature|X-Amz)[^[:space:]]*#https://[REDACTED]#Ig' \
    -e 's#([A-Za-z0-9.-]+\.(internal|local|lan))#[REDACTED-HOST]#Ig'
}

# ── Source env file ────────────────────────────────────────────────────────────
# systemd's EnvironmentFile already injects the vars, but source it again for
# resilience when the script is invoked outside systemd (e.g. manual dry-run).
env_file="/etc/akasha/ingestion-scheduler.env"
if [[ -f "${env_file}" ]]; then
  # shellcheck source=/dev/null
  source "${env_file}"
fi

# ── Bounded defaults ───────────────────────────────────────────────────────────
# Safety posture: disabled/plan-only until each flag is explicitly set.
AKASHA_SCHEDULER_ACTIVE="${AKASHA_SCHEDULER_ACTIVE:-false}"
AKASHA_SCHEDULER_DRY_RUN="${AKASHA_SCHEDULER_DRY_RUN:-true}"
AKASHA_SCHEDULER_APPROVED_RUNTIME="${AKASHA_SCHEDULER_APPROVED_RUNTIME:-false}"
AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES="${AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES:-2}"
AKASHA_SCHEDULER_WINDOW_DAYS="${AKASHA_SCHEDULER_WINDOW_DAYS:-12}"
AKASHA_SCHEDULER_BASE_DIR="${AKASHA_SCHEDULER_BASE_DIR:-/srv/akasha/ingestion/scheduler/jobs}"
AKASHA_SCHEDULER_LOCK_DIR="${AKASHA_SCHEDULER_LOCK_DIR:-/srv/akasha/ingestion}"
AKASHA_SCHEDULER_LEDGER_DB_PATH="${AKASHA_SCHEDULER_LEDGER_DB_PATH:-/srv/akasha/ingestion/scheduler/job_ledger.db}"

ensure_under_srv_akasha() {
  local path="$1"
  case "${path}" in
    /srv/akasha|/srv/akasha/*) ;;
    *)
      log "unsafe scheduler path outside /srv/akasha: ${path}" >&2
      exit 1
      ;;
  esac
}

ensure_under_srv_akasha "${AKASHA_SCHEDULER_BASE_DIR}"
ensure_under_srv_akasha "${AKASHA_SCHEDULER_LOCK_DIR}"
ensure_under_srv_akasha "${AKASHA_SCHEDULER_LEDGER_DB_PATH}"

# ── ionice/nice priority prefix ───────────────────────────────────────────────
# Keeps raster-heavy container jobs from starving SSH and the Azure VM Agent.
priority_cmd=()
if command -v ionice >/dev/null 2>&1; then
  priority_cmd+=(ionice -c "${AKASHA_INGESTION_IONICE_CLASS:-2}" -n "${AKASHA_INGESTION_IONICE_LEVEL:-7}")
fi
if command -v nice >/dev/null 2>&1; then
  priority_cmd+=(nice -n "${AKASHA_INGESTION_NICE:-10}")
fi

# ── Compose file discovery ────────────────────────────────────────────────────
default_compose_file="/srv/akasha/coolify-compose.yml"
if [[ -n "${AKASHA_COMPOSE_FILE:-}" ]]; then
  compose_file="${AKASHA_COMPOSE_FILE}"
elif [[ -f "${default_compose_file}" ]]; then
  compose_file="${default_compose_file}"
else
  compose_file="$(find /data/coolify/services -mindepth 2 -maxdepth 2 -name docker-compose.yml -print -quit 2>/dev/null || true)"
fi
if [[ -z "${compose_file:-}" || ! -f "${compose_file}" ]]; then
  log "compose file not found; set AKASHA_COMPOSE_FILE" >&2
  exit 1
fi
compose_dir="$(dirname "${compose_file}")"
pull_policy="${AKASHA_SYNC_PULL_POLICY:-never}"

compose_args=()
if [[ -n "${AKASHA_COMPOSE_PROJECT:-}" ]]; then
  compose_args=(-p "${AKASHA_COMPOSE_PROJECT}")
fi

# ── Ensure required directories ───────────────────────────────────────────────
# All raster/raw/work/COG/job data must stay under /srv/akasha (OPS-002).
# Worker lock dir: shared by automatic scheduler jobs and ad hoc
# akasha-ingestion-job-runner.sh jobs, using canonical
# <source>.<aoi>.worker.lock filenames.
mkdir -p "${AKASHA_SCHEDULER_BASE_DIR}" "${AKASHA_SCHEDULER_LOCK_DIR}"
chmod 750 "${AKASHA_SCHEDULER_BASE_DIR}" 2>/dev/null || true

cd "${compose_dir}"

# ── Rollback-friendly run header ──────────────────────────────────────────────
log "=== ingestion scheduler run start ==="
log "timer=akasha-ingestion-scheduler.timer  active=${AKASHA_SCHEDULER_ACTIVE}  dry_run=${AKASHA_SCHEDULER_DRY_RUN}  approved_runtime=${AKASHA_SCHEDULER_APPROVED_RUNTIME}"
log "max_concurrent_sources=${AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES}  window_days=${AKASHA_SCHEDULER_WINDOW_DAYS}"
log "base_dir=${AKASHA_SCHEDULER_BASE_DIR}  lock_dir=${AKASHA_SCHEDULER_LOCK_DIR}"
if [[ "${AKASHA_SCHEDULER_ACTIVE}" != "true" ]]; then
  log "ROLLBACK info: pause this timer and use bounded manual scheduler runs if needed"
fi

# ── Plan-only mode (AKASHA_SCHEDULER_ACTIVE != true) ─────────────────────────
if [[ "${AKASHA_SCHEDULER_ACTIVE}" != "true" ]]; then
  log "AKASHA_SCHEDULER_ACTIVE is not 'true' — running schedule-plan (plan/dry-run only; no provider calls)"

  plan_cmd=(
    schedule-plan
    --json
    --window-days "${AKASHA_SCHEDULER_WINDOW_DAYS}"
    --base-dir "${AKASHA_SCHEDULER_BASE_DIR}"
  )
  if [[ -n "${AKASHA_SCHEDULER_SOURCE:-}" ]]; then
    plan_cmd+=(--source "${AKASHA_SCHEDULER_SOURCE}")
  fi
  if [[ -n "${AKASHA_SCHEDULER_AOI:-}" ]]; then
    plan_cmd+=(--aoi "${AKASHA_SCHEDULER_AOI}")
  fi

  log "exec: docker compose run ingestion-worker python worker.py schedule-plan --json [redacted paths]"
  "${priority_cmd[@]}" \
    docker compose "${compose_args[@]}" -f "${compose_file}" \
    run --rm --pull "${pull_policy}" \
    ingestion-worker \
    python worker.py "${plan_cmd[@]}" 2>&1 | redact_stream

  log "=== ingestion scheduler run end (plan-only) ==="
  exit 0
fi

# ── Approved-runtime gate ─────────────────────────────────────────────────────
# AKASHA_SCHEDULER_ACTIVE=true, but AKASHA_SCHEDULER_APPROVED_RUNTIME must also
# be explicitly set to permit staging-only provider (Bhoonidhi) calls (OPS-008).
if [[ "${AKASHA_SCHEDULER_APPROVED_RUNTIME}" != "true" ]]; then
  log "WARNING: AKASHA_SCHEDULER_ACTIVE=true but AKASHA_SCHEDULER_APPROVED_RUNTIME is not 'true'" >&2
  log "To enable live scheduler runs set AKASHA_SCHEDULER_APPROVED_RUNTIME=true in ${env_file}" >&2
  log "Falling back to schedule-plan (plan-only); no provider calls will be made" >&2

  plan_cmd=(
    schedule-plan
    --json
    --window-days "${AKASHA_SCHEDULER_WINDOW_DAYS}"
    --base-dir "${AKASHA_SCHEDULER_BASE_DIR}"
  )
  if [[ -n "${AKASHA_SCHEDULER_SOURCE:-}" ]]; then
    plan_cmd+=(--source "${AKASHA_SCHEDULER_SOURCE}")
  fi
  if [[ -n "${AKASHA_SCHEDULER_AOI:-}" ]]; then
    plan_cmd+=(--aoi "${AKASHA_SCHEDULER_AOI}")
  fi

  "${priority_cmd[@]}" \
    docker compose "${compose_args[@]}" -f "${compose_file}" \
    run --rm --pull "${pull_policy}" \
    ingestion-worker \
    python worker.py "${plan_cmd[@]}" 2>&1 | redact_stream

  log "=== ingestion scheduler run end (plan-only; approved_runtime not set) ==="
  exit 0
fi

# ── Active mode: schedule-due-sources ─────────────────────────────────────────
# Both AKASHA_SCHEDULER_ACTIVE=true and AKASHA_SCHEDULER_APPROVED_RUNTIME=true.
# Default is still --dry-run (AKASHA_SCHEDULER_DRY_RUN=true) until explicitly
# cleared for production, providing a canary/dry-run posture during cutover.
if [[ "${AKASHA_SCHEDULER_DRY_RUN}" == "true" ]]; then
  log "Active mode: DRY-RUN (AKASHA_SCHEDULER_DRY_RUN=true) — creates job artifacts, no provider calls"
else
  log "Active mode: LIVE requested — ResourceSat/Bhoonidhi sources run through the orchestrator pipeline"
fi

due_cmd=(
  schedule-due-sources
  --max-concurrent-source "${AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES}"
  --window-days "${AKASHA_SCHEDULER_WINDOW_DAYS}"
  --base-dir "${AKASHA_SCHEDULER_BASE_DIR}"
  --lock-dir "${AKASHA_SCHEDULER_LOCK_DIR}"
  --ledger-db-path "${AKASHA_SCHEDULER_LEDGER_DB_PATH}"
  --json
  --approved-runtime
)

if [[ "${AKASHA_SCHEDULER_DRY_RUN}" == "true" ]]; then
  due_cmd+=(--dry-run)
fi

# Optional source/AOI filters (canary: restrict to one source/AOI during cutover).
if [[ -n "${AKASHA_SCHEDULER_SOURCE:-}" ]]; then
  due_cmd+=(--source "${AKASHA_SCHEDULER_SOURCE}")
fi
if [[ -n "${AKASHA_SCHEDULER_AOI:-}" ]]; then
  due_cmd+=(--aoi "${AKASHA_SCHEDULER_AOI}")
fi

log "exec: docker compose run ingestion-worker python worker.py schedule-due-sources [redacted paths]"
"${priority_cmd[@]}" \
  docker compose "${compose_args[@]}" -f "${compose_file}" \
  run --rm --pull "${pull_policy}" \
  -e AKASHA_APPROVED_RUNTIME=ingestion-scheduler-wrapper \
  ingestion-worker \
  python worker.py "${due_cmd[@]}" 2>&1 | redact_stream

log "=== ingestion scheduler run end (active dry_run=${AKASHA_SCHEDULER_DRY_RUN}) ==="
