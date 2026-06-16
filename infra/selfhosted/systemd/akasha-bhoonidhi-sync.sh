#!/usr/bin/env bash
set -euo pipefail

default_compose_file="/srv/akasha/coolify-compose.yml"
if [[ -n "${AKASHA_COMPOSE_FILE:-}" ]]; then
  compose_file="${AKASHA_COMPOSE_FILE}"
elif [[ -f "${default_compose_file}" ]]; then
  compose_file="${default_compose_file}"
else
  compose_file="$(find /data/coolify/services -mindepth 2 -maxdepth 2 -name docker-compose.yml -print -quit 2>/dev/null || true)"
fi
if [[ -z "${compose_file}" || ! -f "${compose_file}" ]]; then
  echo "Akasha Bhoonidhi sync: compose file not found; set AKASHA_COMPOSE_FILE." >&2
  exit 1
fi
compose_dir="$(dirname "${compose_file}")"
source_id="${AKASHA_SYNC_SOURCE:-resourcesat-2a-liss3-boa}"
aoi_id="${AKASHA_SYNC_AOI:-bangalore-60km}"
window_days="${AKASHA_SYNC_WINDOW_DAYS:-45}"
window_end="${AKASHA_SYNC_WINDOW_END:-$(date -u +%F)}"
window_offset=$((window_days - 1))
window_start="${AKASHA_SYNC_WINDOW_START:-$(date -u -d "${window_end} -${window_offset} days" +%F)}"
backfill_days="${AKASHA_SYNC_BACKFILL_DAYS:-0}"
pull_policy="${AKASHA_SYNC_PULL_POLICY:-never}"

compose_args=()
if [[ -n "${AKASHA_COMPOSE_PROJECT:-}" ]]; then
  compose_args=(-p "${AKASHA_COMPOSE_PROJECT}")
fi

sync_args=(
  bhoonidhi-sync
  --source "${source_id}"
  --aoi "${aoi_id}"
  --lookback-days "${AKASHA_SYNC_LOOKBACK_DAYS:-45}"
  --limit "${AKASHA_SYNC_LIMIT:-100}"
  --window-days "${window_days}"
  --raw-root "${AKASHA_SYNC_RAW_ROOT:-/srv/akasha/data/raw/bhoonidhi}"
  --out-dir "${AKASHA_SYNC_TEMP_ROOT:-/srv/akasha/data/work/bhoonidhi}"
  --ledger-path "${AKASHA_SYNC_LEDGER_PATH:-/srv/akasha/ingestion/ledger.sqlite}"
  --lock-path "${AKASHA_SYNC_WORKER_LOCK_PATH:-/srv/akasha/ingestion/bhoonidhi-sync.worker.lock}"
  --max-downloads "${AKASHA_SYNC_MAX_DOWNLOADS:-3}"
  --min-coverage-percent "${AKASHA_SYNC_MIN_COVERAGE_PERCENT:-95}"
)

if [[ "${backfill_days}" != "0" ]]; then
  sync_args+=(--backfill-days "${backfill_days}")
  if [[ -n "${AKASHA_SYNC_BACKFILL_STEP_DAYS:-}" ]]; then
    sync_args+=(--backfill-step-days "${AKASHA_SYNC_BACKFILL_STEP_DAYS}")
  fi
  if [[ -n "${AKASHA_SYNC_BACKFILL_ANCHOR_DATE:-}" ]]; then
    sync_args+=(--backfill-anchor-date "${AKASHA_SYNC_BACKFILL_ANCHOR_DATE}")
  fi
  if [[ -n "${AKASHA_SYNC_BACKFILL_STATE_PATH:-}" ]]; then
    sync_args+=(--backfill-state-path "${AKASHA_SYNC_BACKFILL_STATE_PATH}")
  fi
else
  sync_args+=(--window-start "${window_start}" --window-end "${window_end}")
fi

if [[ -n "${AKASHA_SYNC_AOI_PATH:-}" ]]; then
  sync_args+=(--aoi-path "${AKASHA_SYNC_AOI_PATH}")
fi
if [[ -n "${AKASHA_SYNC_AOI_DIR:-}" ]]; then
  sync_args+=(--aoi-dir "${AKASHA_SYNC_AOI_DIR}")
fi
if [[ "${AKASHA_SYNC_RETAIN_RAW_DOWNLOADS:-false}" == "true" ]]; then
  sync_args+=(--retain-raw-downloads)
fi
if [[ "${AKASHA_SYNC_KEEP_INTERMEDIATE:-false}" == "true" ]]; then
  sync_args+=(--keep-intermediate)
fi
if [[ "${AKASHA_SYNC_FORCE_UPLOAD:-false}" == "true" ]]; then
  sync_args+=(--force)
fi
if [[ "${AKASHA_SYNC_OVERWRITE:-false}" == "true" ]]; then
  sync_args+=(--overwrite)
fi
if [[ "${AKASHA_SYNC_DRY_RUN:-false}" == "true" ]]; then
  sync_args+=(--dry-run)
fi

echo "Akasha Bhoonidhi sync: source=${source_id} aoi=${aoi_id} backfill_days=${backfill_days} window=${window_start}..${window_end}"
cd "${compose_dir}"
exec docker compose "${compose_args[@]}" -f "${compose_file}" run --rm --pull "${pull_policy}" ingestion-worker \
  python worker.py "${sync_args[@]}"
