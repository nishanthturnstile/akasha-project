#!/usr/bin/env bash
# Installs the Akasha ingestion scheduler systemd artifacts on the staging worker VM.
# Installs only the provider-agnostic scheduler artifacts; source-specific
# Bhoonidhi timers were removed during the scheduler cutover.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-akasha-ingestion-scheduler.sh [--enable] [--start] [--env-overwrite] [--dry-run]

Installs the Akasha multi-source ingestion scheduler wrapper, service, timer, and
env template on the staging worker VM.

The timer is NOT enabled or started by default — use --enable/--start only after
canary plan-only output has been validated and a source ownership decision has been made.

Options:
  --enable        Enable the timer unit (but do not start it).
  --start         Enable and immediately start the timer (implies --enable).
  --env-overwrite Overwrite /etc/akasha/ingestion-scheduler.env even if it exists.
  --dry-run       Print commands without executing them.
EOF
}

enable_timer=false
start_timer=false
overwrite_env=false
dry_run=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable)
      enable_timer=true
      ;;
    --start)
      start_timer=true
      enable_timer=true
      ;;
    --env-overwrite)
      overwrite_env=true
      ;;
    --dry-run)
      dry_run=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${EUID}" -eq 0 ]]; then
  sudo_cmd=()
else
  sudo_cmd=(sudo)
fi

run() {
  if [[ "${dry_run}" == "true" ]]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

install_with_mode() {
  local mode="$1"
  local source="$2"
  local target="$3"
  run "${sudo_cmd[@]}" install -m "${mode}" "${source}" "${target}"
}

run "${sudo_cmd[@]}" install -d -m 0755 /opt/akasha/bin /etc/akasha
run "${sudo_cmd[@]}" install -d -m 0750 /srv/akasha/ingestion/scheduler/jobs

install_with_mode 0755 "${script_dir}/akasha-ingestion-scheduler.sh" \
  /opt/akasha/bin/akasha-ingestion-scheduler.sh
install_with_mode 0644 "${script_dir}/akasha-ingestion-scheduler.service" \
  /etc/systemd/system/akasha-ingestion-scheduler.service
install_with_mode 0644 "${script_dir}/akasha-ingestion-scheduler.timer" \
  /etc/systemd/system/akasha-ingestion-scheduler.timer

if [[ "${overwrite_env}" == "true" || ! -f /etc/akasha/ingestion-scheduler.env ]]; then
  install_with_mode 0640 "${script_dir}/ingestion-scheduler.env.example" \
    /etc/akasha/ingestion-scheduler.env
else
  echo "Keeping existing /etc/akasha/ingestion-scheduler.env"
fi

run "${sudo_cmd[@]}" systemctl daemon-reload
if [[ "${enable_timer}" == "true" ]]; then
  run "${sudo_cmd[@]}" systemctl enable akasha-ingestion-scheduler.timer
fi
if [[ "${start_timer}" == "true" ]]; then
  run "${sudo_cmd[@]}" systemctl start akasha-ingestion-scheduler.timer
fi

cat <<'EOF'
Installed Akasha ingestion scheduler systemd artifacts.

Default posture: DISABLED/plan-only (AKASHA_SCHEDULER_ACTIVE=false in env file).

Next steps before enabling live runs:
  1. Review /etc/akasha/ingestion-scheduler.env and set ownership matrix.
  2. Run a plan-only check:
       sudo systemctl start akasha-ingestion-scheduler.service
       journalctl -u akasha-ingestion-scheduler.service -n 100 --no-pager
  3. When plan output is confirmed, set AKASHA_SCHEDULER_ACTIVE=true in the env file.
  4. Keep AKASHA_SCHEDULER_DRY_RUN=true and AKASHA_SCHEDULER_SOURCE=<one-source>
     for canary dry-run validation.
  5. When canary passes, set AKASHA_SCHEDULER_DRY_RUN=false for live runs.

Enable timer after validation:
  sudo systemctl enable --now akasha-ingestion-scheduler.timer
  sudo systemctl status akasha-ingestion-scheduler.timer --no-pager

Rollback:
  sudo systemctl disable --now akasha-ingestion-scheduler.timer
  Use akasha-ingestion-job.sh for bounded manual schedule-source runs while the timer is paused.
EOF
