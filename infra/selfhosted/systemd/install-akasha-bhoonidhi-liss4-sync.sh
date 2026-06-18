#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-akasha-bhoonidhi-liss4-sync.sh [--enable] [--start] [--env-overwrite] [--dry-run]

Installs the Akasha Bhoonidhi LISS-4 sync systemd wrapper, service, timer,
and env template on the staging worker VM. Existing
/etc/akasha/bhoonidhi-liss4-sync.env is preserved unless --env-overwrite is
passed. LISS-3 sync units are not modified.
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
install_with_mode 0755 "${script_dir}/akasha-bhoonidhi-liss4-sync.sh" \
  /opt/akasha/bin/akasha-bhoonidhi-liss4-sync.sh
install_with_mode 0644 "${script_dir}/akasha-bhoonidhi-liss4-sync.service" \
  /etc/systemd/system/akasha-bhoonidhi-liss4-sync.service
install_with_mode 0644 "${script_dir}/akasha-bhoonidhi-liss4-sync.timer" \
  /etc/systemd/system/akasha-bhoonidhi-liss4-sync.timer

if [[ "${overwrite_env}" == "true" || ! -f /etc/akasha/bhoonidhi-liss4-sync.env ]]; then
  install_with_mode 0600 "${script_dir}/akasha-bhoonidhi-liss4-sync.env.example" \
    /etc/akasha/bhoonidhi-liss4-sync.env
else
  echo "Keeping existing /etc/akasha/bhoonidhi-liss4-sync.env"
fi

run "${sudo_cmd[@]}" systemctl daemon-reload
if [[ "${enable_timer}" == "true" ]]; then
  run "${sudo_cmd[@]}" systemctl enable akasha-bhoonidhi-liss4-sync.timer
fi
if [[ "${start_timer}" == "true" ]]; then
  run "${sudo_cmd[@]}" systemctl start akasha-bhoonidhi-liss4-sync.timer
fi

cat <<EOF
Installed Akasha Bhoonidhi LISS-4 sync systemd artifacts.

Next checks:
  sudo systemctl status akasha-bhoonidhi-liss4-sync.timer --no-pager
  sudo systemctl start akasha-bhoonidhi-liss4-sync.service
  journalctl -u akasha-bhoonidhi-liss4-sync.service -n 200 --no-pager

For a safe first run, set AKASHA_SYNC_DRY_RUN=true in /etc/akasha/bhoonidhi-liss4-sync.env.
EOF

