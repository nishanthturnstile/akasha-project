#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-akasha-ingestion-jobs.sh [--dry-run] [--uninstall]

Installs the restricted Akasha staging ingestion job wrapper scripts on the
staging worker VM. Existing /etc/akasha/ingestion-jobs.env is preserved.
EOF
}

dry_run=false
uninstall=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=true
      ;;
    --uninstall)
      uninstall=true
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

if [[ "${uninstall}" == "true" ]]; then
  run "${sudo_cmd[@]}" rm -f \
    /opt/akasha/bin/akasha-ingestion-job.sh \
    /opt/akasha/bin/akasha-ingestion-job-runner.sh \
    /opt/akasha/bin/akasha-ingestion-forced-command.sh \
    /opt/akasha/bin/akasha-ingestion-inbox-dispatcher.sh \
    /etc/systemd/system/akasha-ingestion-inbox-dispatcher.service \
    /etc/systemd/system/akasha-ingestion-inbox-dispatcher.path \
    /etc/systemd/system/akasha-ingestion-inbox-dispatcher.timer
  run "${sudo_cmd[@]}" systemctl daemon-reload
  cat <<'EOF'
Uninstalled Akasha ingestion job wrapper scripts.
Kept /srv/akasha ingestion data, ingestion inbox history, and /etc/akasha/ingestion-jobs.env.
EOF
  exit 0
fi

run "${sudo_cmd[@]}" install -d -m 0755 /opt/akasha/bin /etc/akasha
if [[ "${dry_run}" == "true" ]] || getent group akasha-ingesters >/dev/null 2>&1; then
  run "${sudo_cmd[@]}" install -d -m 2770 -o root -g akasha-ingesters /srv/akasha/ingestion/jobs
  run "${sudo_cmd[@]}" install -d -m 0770 -o root -g akasha-ingesters /srv/akasha/ingestion-inbox
  run "${sudo_cmd[@]}" install -d -m 0770 -o root -g akasha-ingesters /srv/akasha/ingestion-inbox/submitted /srv/akasha/ingestion-inbox/failed
else
  run "${sudo_cmd[@]}" install -d -m 2770 /srv/akasha/ingestion/jobs
  run "${sudo_cmd[@]}" install -d -m 0770 /srv/akasha/ingestion-inbox
  run "${sudo_cmd[@]}" install -d -m 0770 /srv/akasha/ingestion-inbox/submitted /srv/akasha/ingestion-inbox/failed
  echo "Warning: group akasha-ingesters does not exist yet; create it and chgrp /srv/akasha/ingestion/jobs plus /srv/akasha/ingestion-inbox." >&2
fi

install_with_mode 0755 "${script_dir}/akasha-ingestion-job.sh" \
  /opt/akasha/bin/akasha-ingestion-job.sh
install_with_mode 0755 "${script_dir}/akasha-ingestion-job-runner.sh" \
  /opt/akasha/bin/akasha-ingestion-job-runner.sh
install_with_mode 0755 "${script_dir}/akasha-ingestion-forced-command.sh" \
  /opt/akasha/bin/akasha-ingestion-forced-command.sh
install_with_mode 0755 "${script_dir}/akasha-ingestion-inbox-dispatcher.sh" \
  /opt/akasha/bin/akasha-ingestion-inbox-dispatcher.sh
install_with_mode 0644 "${script_dir}/akasha-ingestion-inbox-dispatcher.service" \
  /etc/systemd/system/akasha-ingestion-inbox-dispatcher.service
install_with_mode 0644 "${script_dir}/akasha-ingestion-inbox-dispatcher.path" \
  /etc/systemd/system/akasha-ingestion-inbox-dispatcher.path
install_with_mode 0644 "${script_dir}/akasha-ingestion-inbox-dispatcher.timer" \
  /etc/systemd/system/akasha-ingestion-inbox-dispatcher.timer

if [[ ! -f /etc/akasha/ingestion-jobs.env ]]; then
  install_with_mode 0640 "${script_dir}/akasha-ingestion-jobs.env.example" \
    /etc/akasha/ingestion-jobs.env
else
  echo "Keeping existing /etc/akasha/ingestion-jobs.env"
fi

run "${sudo_cmd[@]}" systemctl daemon-reload

cat <<'EOF'
Installed Akasha restricted ingestion job scripts.

authorized_keys forced-command line template:
  command="/opt/akasha/bin/akasha-ingestion-forced-command.sh",restrict ssh-ed25519 <team-public-key> <developer>

Next checks:
  /opt/akasha/bin/akasha-ingestion-job.sh doctor
  /opt/akasha/bin/akasha-ingestion-job.sh list --limit 5

Admin ingestion inbox dispatcher:
  sudo systemctl enable --now akasha-ingestion-inbox-dispatcher.path
  sudo systemctl enable --now akasha-ingestion-inbox-dispatcher.timer
  sudo systemctl start akasha-ingestion-inbox-dispatcher.service

Rollback:
  sudo systemctl disable --now akasha-ingestion-inbox-dispatcher.path akasha-ingestion-inbox-dispatcher.timer
  sudo systemctl stop akasha-ingestion-inbox-dispatcher.service

This installer does not enable akasha-ingestion-scheduler.timer.
EOF
