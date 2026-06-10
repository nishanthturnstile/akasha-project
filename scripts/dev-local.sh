#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_DIR="$ROOT_DIR/infra/docker"
FRONTEND_DIR="$ROOT_DIR/apps/frontend"
ENV_FILE="$DOCKER_DIR/.env"
FRONTEND_ENV_FILE="$FRONTEND_DIR/.env"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"
START_FRONTEND=true

if [[ "${1:-}" == "--backend-only" ]]; then
  START_FRONTEND=false
elif [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  bash scripts/dev-local.sh                 Start Docker stack + hot-reload Vite frontend.
  bash scripts/dev-local.sh --backend-only  Start/prepare only the Docker backend/gateway stack.

Optional env vars:
  WEB_PORT                         Host port for the Docker gateway when .env is created (default: 8080).
  FRONTEND_PORT                    Preferred Vite dev-server port (default: 5173; next free port if busy).
  VITE_ESRI_API_KEY                Esri basemap key copied into generated local env files.
  AKASHA_LOCAL_ADMIN_USER          Local bootstrap username (default: admin).
  AKASHA_LOCAL_ADMIN_PASSWORD      Local bootstrap password (default: AkashaLocal2026!).
EOF
  exit 0
fi

log() {
  printf '\n\033[1;36m==> %s\033[0m\n' "$*"
}

warn() {
  printf '\n\033[1;33mWARN: %s\033[0m\n' "$*" >&2
}

die() {
  printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2
  exit 1
}

require_command() {
  local name="$1"
  local hint="$2"
  command -v "$name" >/dev/null 2>&1 || die "$name is required. $hint"
}

preflight() {
  require_command docker "Install/start Docker Desktop, then retry."
  require_command curl "Install curl or run from Git Bash/WSL, then retry."

  docker version >/dev/null 2>&1 || die "Docker is installed, but the Docker engine is not reachable. Start Docker Desktop and retry."

  if [[ "$START_FRONTEND" == true ]] \
    && ! command -v yarn >/dev/null 2>&1 \
    && ! command -v corepack >/dev/null 2>&1 \
    && ! command -v npx >/dev/null 2>&1; then
    die "Frontend startup needs yarn, corepack, or npx. Install Node.js 20+ and retry."
  fi
}

random_secret() {
  if command -v python >/dev/null 2>&1; then
    python - <<'PY'
import secrets
print(secrets.token_urlsafe(36))
PY
  elif command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(36))
PY
  elif command -v node >/dev/null 2>&1; then
    node -e "console.log(require('crypto').randomBytes(36).toString('base64url'))"
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 36 | tr -d '\n' | tr '/+' '_-'
  else
    printf 'local-%s-%s' "$(date +%s)" "$RANDOM"
  fi
}

port_is_listening() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] || return 1

  if command -v python >/dev/null 2>&1; then
    PORT="$port" python - <<'PY'
import os
import socket
import sys

port = int(os.environ["PORT"])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
finally:
    sock.close()
PY
  elif command -v python3 >/dev/null 2>&1; then
    PORT="$port" python3 - <<'PY'
import os
import socket
import sys

port = int(os.environ["PORT"])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
finally:
    sock.close()
PY
  elif command -v node >/dev/null 2>&1; then
    PORT="$port" node -e '
const net = require("node:net");
const port = Number(process.env.PORT);
const socket = net.connect({ host: "127.0.0.1", port }, () => {
  socket.destroy();
  process.exit(0);
});
socket.setTimeout(500);
socket.on("timeout", () => { socket.destroy(); process.exit(1); });
socket.on("error", () => process.exit(1));
'
  else
    return 1
  fi
}

find_free_port() {
  local start_port="$1"
  [[ "$start_port" =~ ^[0-9]+$ ]] || start_port=8080

  if command -v python >/dev/null 2>&1; then
    START_PORT="$start_port" python - <<'PY'
import os
import socket
import sys

port = max(1, int(os.environ["START_PORT"]))
while port <= 65535:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        print(port)
        sys.exit(0)
    except OSError:
        port += 1
    finally:
        sock.close()
sys.exit(1)
PY
  elif command -v python3 >/dev/null 2>&1; then
    START_PORT="$start_port" python3 - <<'PY'
import os
import socket
import sys

port = max(1, int(os.environ["START_PORT"]))
while port <= 65535:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        print(port)
        sys.exit(0)
    except OSError:
        port += 1
    finally:
        sock.close()
sys.exit(1)
PY
  else
    local port="$start_port"
    while port_is_listening "$port" && [[ "$port" -lt 65535 ]]; do
      port=$((port + 1))
    done
    echo "$port"
  fi
}

read_env_value() {
  local key="$1"
  local file="$2"
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

upsert_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  if grep -q "^${key}=" "$file"; then
    awk -v key="$key" -v value="$value" '
      BEGIN { replaced = 0 }
      $0 ~ "^" key "=" { print key "=" value; replaced = 1; next }
      { print }
      END { if (!replaced) print key "=" value }
    ' "$file" > "$tmp_file"
  else
    cat "$file" > "$tmp_file"
    printf '\n%s=%s\n' "$key" "$value" >> "$tmp_file"
  fi

  mv "$tmp_file" "$file"
}

is_placeholder_or_empty() {
  local value="${1:-}"
  [[ -z "$value" || "$value" == CHANGE_ME* || "$value" == \<* ]]
}

gateway_health_ok() {
  local port="$1"
  [[ "$(curl -fsS --max-time 2 "http://localhost:${port}/health" 2>/dev/null || true)" == "ok" ]]
}

ensure_web_port_available() {
  local web_port next_port
  web_port="$(read_env_value WEB_PORT "$ENV_FILE")"
  if [[ ! "$web_port" =~ ^[0-9]+$ ]]; then
    warn "WEB_PORT is missing or invalid in infra/docker/.env; using 8080."
    web_port=8080
    upsert_env_value WEB_PORT "$web_port" "$ENV_FILE"
  fi

  if port_is_listening "$web_port"; then
    if gateway_health_ok "$web_port"; then
      log "WEB_PORT=$web_port already has the Akasha gateway responding; reusing it."
      return
    fi

    next_port="$(find_free_port $((web_port + 1)))"
    warn "WEB_PORT=$web_port is already in use by another process. Updating infra/docker/.env to WEB_PORT=$next_port."
    upsert_env_value WEB_PORT "$next_port" "$ENV_FILE"
  fi
}

choose_frontend_port() {
  local requested_port next_port
  requested_port="${FRONTEND_PORT:-5173}"
  if [[ ! "$requested_port" =~ ^[0-9]+$ ]]; then
    warn "FRONTEND_PORT=$requested_port is invalid; using 5173."
    requested_port=5173
  fi

  if port_is_listening "$requested_port"; then
    next_port="$(find_free_port $((requested_port + 1)))"
    warn "Frontend port $requested_port is already in use. Starting Vite on $next_port instead."
    echo "$next_port"
    return
  fi

  echo "$requested_port"
}

ensure_docker_env() {
  if [[ -f "$ENV_FILE" ]]; then
    log "Using existing infra/docker/.env"
    if is_placeholder_or_empty "$(read_env_value AUTH_BOOTSTRAP_TOKEN "$ENV_FILE")"; then
      log "Adding missing AUTH_BOOTSTRAP_TOKEN to infra/docker/.env"
      upsert_env_value AUTH_BOOTSTRAP_TOKEN "$(random_secret)" "$ENV_FILE"
    fi
    if [[ -z "$(read_env_value AUTH_ALLOW_BOOTSTRAP "$ENV_FILE")" ]]; then
      upsert_env_value AUTH_ALLOW_BOOTSTRAP "true" "$ENV_FILE"
    fi
    if [[ -z "$(read_env_value AUTH_PASSWORD_PEPPER "$ENV_FILE")" ]]; then
      log "Adding missing AUTH_PASSWORD_PEPPER to infra/docker/.env"
      upsert_env_value AUTH_PASSWORD_PEPPER "$(random_secret)" "$ENV_FILE"
    fi
    return
  fi

  log "Creating infra/docker/.env with generated local-only secrets"
  cat > "$ENV_FILE" <<EOF
# Generated by scripts/dev-local.sh for local development. Do not commit.
WEB_PORT=${WEB_PORT:-8080}
PUBLIC_APP_NAME=Akasha
PUBLIC_DEFAULT_AOI_NAME=Bangalore

POSTGRES_USER=akasha
POSTGRES_PASSWORD=$(random_secret)
POSTGRES_DB=akasha

MINIO_ROOT_USER=akasha_minio
MINIO_ROOT_PASSWORD=$(random_secret)

# Frontend build-time Esri basemap settings. Set VITE_ESRI_API_KEY to a
# referrer-restricted ArcGIS Location Platform key with Basemaps privilege.
VITE_ESRI_API_KEY=${VITE_ESRI_API_KEY:-}
VITE_ESRI_BASEMAP_STYLE=arcgis/imagery
VITE_ESRI_BASEMAP_STYLE_FAMILY=arcgis
VITE_ESRI_BASEMAP_PLACES=none
VITE_ESRI_BASEMAP_SESSION_SECONDS=43200

AUTH_PASSWORD_PEPPER=$(random_secret)
AUTH_ALLOW_BOOTSTRAP=true
AUTH_BOOTSTRAP_TOKEN=$(random_secret)

AKASHA_S1_VV_RESCALE=-25,5
SNAP_CACHE_SIZE=8G
SNAP_PARALLELISM=4
SNAP_JAVA_MAX_HEAP=12g
AKASHA_S1_DEM_SOURCE=Copernicus 30m Global DEM
AKASHA_S1_FALLBACK_DEM_SOURCE=SRTM 1Sec HGT
AKASHA_S1_TARGET_CRS=EPSG:4326
AKASHA_S1_PIXEL_SPACING_METERS=10
AKASHA_S1_VH_RESCALE=-30,-5
EOF
}

ensure_frontend_env() {
  if [[ -f "$FRONTEND_ENV_FILE" ]]; then
    return
  fi

  local esri_key
  esri_key="$(read_env_value VITE_ESRI_API_KEY "$ENV_FILE")"
  if is_placeholder_or_empty "$esri_key"; then
    esri_key="${VITE_ESRI_API_KEY:-}"
  fi

  log "Creating apps/frontend/.env for Vite"
  cat > "$FRONTEND_ENV_FILE" <<EOF
# Generated by scripts/dev-local.sh for local Vite development. Do not commit.
VITE_ESRI_API_KEY=$esri_key
VITE_ESRI_BASEMAP_STYLE=arcgis/imagery
VITE_ESRI_BASEMAP_STYLE_FAMILY=arcgis
VITE_ESRI_BASEMAP_PLACES=none
VITE_ESRI_BASEMAP_SESSION_SECONDS=43200
EOF

  if is_placeholder_or_empty "$esri_key"; then
    warn "No VITE_ESRI_API_KEY is configured. The app will start, but the map will ask for an Esri basemap key. Add it to apps/frontend/.env."
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-90}"
  local i

  for ((i = 1; i <= attempts; i += 1)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf 'OK: %s (%s)\n' "$label" "$url"
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for $label at $url" >&2
  return 1
}

run_yarn() {
  if command -v yarn >/dev/null 2>&1; then
    yarn "$@"
  elif command -v corepack >/dev/null 2>&1; then
    corepack yarn "$@"
  else
    npx --yes yarn "$@"
  fi
}

json_escape() {
  local value="$1"
  if command -v python >/dev/null 2>&1; then
    VALUE="$value" python - <<'PY'
import json, os
print(json.dumps(os.environ["VALUE"])[1:-1])
PY
  elif command -v python3 >/dev/null 2>&1; then
    VALUE="$value" python3 - <<'PY'
import json, os
print(json.dumps(os.environ["VALUE"])[1:-1])
PY
  else
    printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g'
  fi
}

bootstrap_local_admin() {
  local gateway_url="$1"
  local token username password payload status body_file

  token="$(read_env_value AUTH_BOOTSTRAP_TOKEN "$ENV_FILE")"
  username="${AKASHA_LOCAL_ADMIN_USER:-admin}"
  password="${AKASHA_LOCAL_ADMIN_PASSWORD:-AkashaLocal2026!}"
  body_file="$(mktemp)"

  payload="{\"username\":\"$(json_escape "$username")\",\"password\":\"$(json_escape "$password")\",\"email\":\"admin@akasha.local\",\"displayName\":\"Akasha Local Admin\",\"teamName\":\"Akasha Local Team\",\"bootstrapToken\":\"$(json_escape "$token")\"}"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "$gateway_url/api/auth/bootstrap" || true)"

  rm -f "$body_file"

  case "$status" in
    200|201)
      echo "OK: created local admin user '$username'"
      ;;
    403)
      echo "OK: local admin bootstrap skipped (a password user already exists or bootstrap is disabled)"
      ;;
    *)
      warn "Local admin bootstrap returned HTTP $status. You can still bootstrap manually if needed."
      ;;
  esac
}

start_backend() {
  log "Starting Docker backend/gateway stack"
  docker compose -f "$COMPOSE_FILE" up --build -d

  local web_port gateway_url
  web_port="$(read_env_value WEB_PORT "$ENV_FILE")"
  web_port="${web_port:-8080}"
  gateway_url="http://localhost:${web_port}"

  log "Waiting for backend health checks"
  wait_for_url "$gateway_url/health" "gateway health"
  wait_for_url "$gateway_url/api/health" "API health via gateway"

  log "Applying API migrations and seeding catalog/storage"
  docker compose -f "$COMPOSE_FILE" exec -T api python -m app.cli db upgrade
  docker compose -f "$COMPOSE_FILE" exec -T api python -m app.cli check
  docker compose -f "$COMPOSE_FILE" run --rm ingestion-worker python worker.py seed

  log "Preparing local admin account"
  bootstrap_local_admin "$gateway_url"

  printf '%s' "$gateway_url"
}

preflight
ensure_docker_env
ensure_web_port_available
ensure_frontend_env
GATEWAY_URL="$(start_backend | tee /dev/stderr | tail -n 1)"

if [[ "$START_FRONTEND" != true ]]; then
  log "Backend is ready"
  echo "Gateway:  $GATEWAY_URL"
  echo "Login:    $GATEWAY_URL/login"
  echo "Username: ${AKASHA_LOCAL_ADMIN_USER:-admin}"
  echo "Password: ${AKASHA_LOCAL_ADMIN_PASSWORD:-AkashaLocal2026!}"
  exit 0
fi

log "Starting Vite frontend with hot reload"
cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
  run_yarn install --frozen-lockfile
fi

FRONTEND_DEV_PORT="$(choose_frontend_port)"

echo "Frontend: http://localhost:${FRONTEND_DEV_PORT}/"
echo "Login:    http://localhost:${FRONTEND_DEV_PORT}/login"
echo "Backend:  $GATEWAY_URL"
echo "Username: ${AKASHA_LOCAL_ADMIN_USER:-admin}"
echo "Password: ${AKASHA_LOCAL_ADMIN_PASSWORD:-AkashaLocal2026!}"
echo "Press Ctrl+C to stop Vite. Docker services keep running; stop them with: make down"

AKASHA_DEV_PROXY_TARGET="$GATEWAY_URL" run_yarn dev --host 127.0.0.1 --port "$FRONTEND_DEV_PORT" --strictPort
