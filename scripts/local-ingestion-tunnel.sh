#!/usr/bin/env bash
set -euo pipefail

LOCAL_HOST="127.0.0.1"
LOCAL_PORT="${AKASHA_INGESTION_TUNNEL_LOCAL_PORT:-18081}"
REMOTE_HOST="${AKASHA_INGESTION_TUNNEL_REMOTE_HOST:-10.10.2.4}"
REMOTE_PORT="${AKASHA_INGESTION_TUNNEL_REMOTE_PORT:-18080}"
SSH_HOST="${AKASHA_INGESTION_SSH_HOST:-${SSH_HOST:-}}"
SSH_EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  bash scripts/local-ingestion-tunnel.sh --ssh-host user@bastion
  AKASHA_INGESTION_SSH_HOST=user@bastion bash scripts/local-ingestion-tunnel.sh

Options:
  --ssh-host HOST       SSH host used for the tunnel. Can also be set with
                        AKASHA_INGESTION_SSH_HOST.
  --local-port PORT     Local listen port (default: 18081).
  --remote-host HOST    Remote ingestion host reachable from SSH host
                        (default: 10.10.2.4).
  --remote-port PORT    Remote ingestion port (default: 18080).
  --                   Pass remaining args directly to ssh.
  -h, --help            Show this help.

Windows Git Bash notes:
  - Run this from Git Bash or WSL with OpenSSH available on PATH.
  - Keep the terminal open while using the bridge; Ctrl+C closes the tunnel.
  - Docker Desktop already resolves host.docker.internal. Linux Docker Engine
    gets the same name from infra/docker/docker-compose.dev.yml.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host)
      SSH_HOST="${2:-}"
      shift 2
      ;;
    --local-port)
      LOCAL_PORT="${2:-}"
      shift 2
      ;;
    --remote-host)
      REMOTE_HOST="${2:-}"
      shift 2
      ;;
    --remote-port)
      REMOTE_PORT="${2:-}"
      shift 2
      ;;
    --)
      shift
      SSH_EXTRA_ARGS+=("$@")
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -z "$SSH_HOST" ]]; then
        SSH_HOST="$1"
      else
        SSH_EXTRA_ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

require_port() {
  local label="$1"
  local port="$2"
  if [[ ! "$port" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
    echo "$label must be a TCP port between 1 and 65535: $port" >&2
    exit 2
  fi
}

if [[ -z "$SSH_HOST" ]]; then
  echo "Missing SSH host. Use --ssh-host user@host or AKASHA_INGESTION_SSH_HOST." >&2
  usage >&2
  exit 2
fi

require_port "--local-port" "$LOCAL_PORT"
require_port "--remote-port" "$REMOTE_PORT"

cat <<EOF
Opening Akasha ingestion tunnel:
  ${LOCAL_HOST}:${LOCAL_PORT} -> ${REMOTE_HOST}:${REMOTE_PORT} via ${SSH_HOST}

Set these values in infra/docker/.env for the local bridge:
DEFAULT_SOURCE_ID=sentinel-2-l2a
INGESTION_API_URL=http://host.docker.internal:${LOCAL_PORT}
INGESTION_READINESS_ENABLED=true
INGESTION_FIELD_INDEX_ENABLED=true
INGESTION_AOI_ID=bangalore_60km_geodesic_aoi
INGESTION_SIGNED_URL_ALLOWED_PREFIX=http://${REMOTE_HOST}:${REMOTE_PORT}
INGESTION_SIGNED_URL_FETCH_PREFIX=http://host.docker.internal:${LOCAL_PORT}
INGESTION_TREND_MAX_DATES=12

Set the server-side ingestion API key manually in infra/docker/.env.
This script intentionally does not print it.

Press Ctrl+C to close the tunnel.
EOF

exec ssh -N \
  -L "${LOCAL_HOST}:${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}" \
  "${SSH_EXTRA_ARGS[@]}" \
  "$SSH_HOST"
