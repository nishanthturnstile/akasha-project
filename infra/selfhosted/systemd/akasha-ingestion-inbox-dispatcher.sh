#!/usr/bin/env bash
set -euo pipefail
umask 007

log() {
  printf '[%s] akasha-inbox-dispatcher: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

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

env_file="/etc/akasha/ingestion-jobs.env"
if [[ -f "${env_file}" ]]; then
  # shellcheck source=/dev/null
  source "${env_file}"
fi

INBOX_DIR="${AKASHA_INGESTION_INBOX_DIR:-/srv/akasha/ingestion-inbox}"
RETENTION_DAYS="${AKASHA_INGESTION_INBOX_RETENTION_DAYS:-14}"
WRAPPER="${AKASHA_INGESTION_JOB_WRAPPER:-/opt/akasha/bin/akasha-ingestion-job.sh}"

case "${INBOX_DIR}" in
  /srv/akasha|/srv/akasha/*) ;;
  *)
    log "unsafe inbox path outside /srv/akasha: ${INBOX_DIR}" >&2
    exit 1
    ;;
esac

if [[ ! "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  log "invalid AKASHA_INGESTION_INBOX_RETENTION_DAYS=${RETENTION_DAYS}" >&2
  exit 1
fi

mkdir -p "${INBOX_DIR}" "${INBOX_DIR}/submitted" "${INBOX_DIR}/failed"
chmod 770 "${INBOX_DIR}" "${INBOX_DIR}/submitted" "${INBOX_DIR}/failed" 2>/dev/null || true

move_request_dir() {
  local request_dir="$1"
  local state="$2"
  local request_id
  request_id="$(basename "${request_dir}")"
  local target="${INBOX_DIR}/${state}/${request_id}"
  rm -rf -- "${target}"
  mv -- "${request_dir}" "${target}"
  chmod -R u+rwX,g+rwX,o-rwx "${target}" 2>/dev/null || true
}

move_unsafe_request_dir() {
  local request_dir="$1"
  local request_id safe_id target
  request_id="$(basename "${request_dir}")"
  safe_id="${request_id//[^A-Za-z0-9._-]/_}"
  if [[ -z "${safe_id}" ]]; then
    safe_id="unsafe"
  fi
  target="${INBOX_DIR}/failed/unsafe-${safe_id}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  {
    printf 'dispatch failed for unsafe request id\n'
  } >"${request_dir}/dispatch_error.txt" 2>/dev/null || true
  mv -- "${request_dir}" "${target}"
  chmod -R u+rwX,g+rwX,o-rwx "${target}" 2>/dev/null || true
}

dispatch_one() {
  local request_path="$1"
  local request_dir request_id lock_file output status
  request_dir="$(dirname "${request_path}")"
  request_id="$(basename "${request_dir}")"

  if [[ ! "${request_id}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    log "failing unsafe request id: ${request_id}" >&2
    move_unsafe_request_dir "${request_dir}"
    return 0
  fi

  lock_file="${request_dir}/.dispatch.lock"
  exec 9>"${lock_file}"
  if ! flock -n 9; then
    log "request ${request_id} already locked; skipping"
    return 0
  fi

  if [[ ! -f "${request_path}" ]]; then
    log "request ${request_id} disappeared before dispatch; skipping"
    return 0
  fi

  log "dispatching request ${request_id}"
  set +e
  output="$("${WRAPPER}" start "${request_path}" 2>&1 | redact_stream)"
  status=$?
  set -e

  if [[ "${status}" -eq 0 ]]; then
    if [[ -n "${output}" ]]; then
      printf '%s\n' "${output}"
    fi
    move_request_dir "${request_dir}" "submitted"
    log "submitted request ${request_id}"
  else
    {
      printf 'dispatch failed for request %s with exit status %s\n' "${request_id}" "${status}"
      if [[ -n "${output}" ]]; then
        printf '%s\n' "${output}"
      fi
    } >"${request_dir}/dispatch_error.txt"
    chmod 640 "${request_dir}/dispatch_error.txt" 2>/dev/null || true
    move_request_dir "${request_dir}" "failed"
    log "failed request ${request_id}; moved to failed"
  fi
}

prune_old_entries() {
  local state
  for state in submitted failed; do
    find "${INBOX_DIR}/${state}" -mindepth 1 -maxdepth 1 -type d -mtime +"${RETENTION_DAYS}" -exec rm -rf -- {} +
  done
}

shopt -s nullglob
for request_path in "${INBOX_DIR}"/*/request.json; do
  dispatch_one "${request_path}"
done
shopt -u nullglob

prune_old_entries
