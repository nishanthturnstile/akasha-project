# Akasha Developer Setup Guide

This guide is for a new developer setting up Akasha locally on **macOS** or **Windows**. It covers first-time setup, running backend and frontend separately, hot reload behavior, rebuild rules, and the schema migration workflow.

Akasha is a multi-service Dockerized app. For local development, the backend and geospatial dependencies run in Docker, while the frontend runs on the host through Vite for fast hot reload.

## 1. What runs where

| Part | Local runtime | Hot reload | Notes |
|---|---|---|---|
| FastAPI API/BFF | Docker `api` container | Yes, via `docker-compose.dev.yml` bind mount + Uvicorn reload | Avoids host GDAL/rasterio/PostGIS setup pain, especially on Windows. |
| Gateway/Caddy | Docker `web` container | No | Same-origin proxy for `/api/*` and `/tiles/*`; only public service in local/prod topology. |
| PostGIS | Docker | No | Local app schema and pgSTAC backing DB. |
| MinIO | Docker | No | Local S3-compatible COG/object storage. |
| STAC API | Docker | No | Catalog service backed by PostGIS/pgSTAC. |
| TiTiler | Docker | No | Display tiles only. |
| Local ingestion worker / SAR | Optional Docker overlay | No | Only for explicitly requested local catalog/raster work; remote mode excludes both. |
| React/Vite frontend | Host machine | Yes | Proxies `/api` and `/tiles` to the local Docker gateway. |

## 2. Prerequisites

### macOS

Install:

- Git
- Docker Desktop
- Node.js 20+
- `make` — usually available via Xcode command line tools or Homebrew
- Optional but useful: Homebrew

Quick checks:

```bash
git --version
docker compose version
node --version
npx --version
make --version
```

### Windows

Recommended setup:

- Git for Windows with **Git Bash**
- Docker Desktop using the WSL2 backend
- Node.js 20+
- Optional: WSL2 Ubuntu for better Docker bind-mount performance
- Optional: GNU Make. If `make` is unavailable, use the equivalent `bash scripts/dev-local.sh ...` commands shown below.

Quick checks from Git Bash or WSL:

```bash
git --version
docker compose version
node --version
npx --version
corepack --version
bash --version
```

Windows notes:

- Run local scripts from **Git Bash** or WSL, not PowerShell.
- Keep the repo path reasonably short; deep paths can make Windows tooling unhappy.
- The repo includes `.gitattributes` so shell scripts stay LF line-ended.
- Backend file watching uses polling by default (`WATCHFILES_FORCE_POLLING=true`) for Docker Desktop reliability.
- If `yarn` is not on `PATH`, use `corepack yarn ...`. The setup script also falls back to `npx --yes yarn ...` when Corepack is unavailable.

## 3. Clone and enter the repo

```bash
git clone <repo-url> akasha-project
cd akasha-project
```

If you are working from this existing workspace, start from the repository root:

```bash
cd "c:/Users/v-mnmurugan/thaarei projects/akasha/akasha-em-git"
```

Use the actual path on your machine.

## 4. First-time local setup

The recommended first-time command is:

```bash
make dev
```

If `make` is unavailable:

```bash
bash scripts/dev-local.sh
```

This command:

1. Checks required tools.
2. Creates ignored local env files if missing:
   - `infra/docker/.env`
   - `apps/frontend/.env`
3. Starts Docker services with the local dev overlay.
4. Waits for gateway/API health checks.
5. Applies API Alembic migrations.
6. Runs API storage checks.
7. Seeds catalog/storage via the optional local-ingestion overlay.
8. Starts Vite with hot reload.

The script prints the actual frontend, login, signup, and backend URLs. Default URLs are usually:

```text
Frontend: http://localhost:5173/
Sign up:  http://localhost:5173/signup
Login:    http://localhost:5173/login
Backend:  http://localhost:8080
```

Local development ports live in `infra/docker/.env`:

```env
WEB_PORT=8080
FRONTEND_PORT=5173
```

If either configured port is busy, the script updates that entry in
`infra/docker/.env` to the next free port and prints the actual URLs. Treat the
printed URLs as the source of truth.

### Inspect the local PostGIS database with DBeaver

The local dev overlay publishes PostGIS on the loopback interface only:

```text
127.0.0.1:15432 -> postgis:5432
```

This is for local GUI inspection only. Do not add a Postgres `ports:` mapping to
`infra/docker/docker-compose.yml`, because the base compose file stays
production-like and private.

Start the backend stack first:

```bash
make backend
```

If `make` is unavailable, use the equivalent script:

```bash
bash scripts/dev-local.sh --backend-only
```

Then create a DBeaver connection:

| Field | Value |
|---|---|
| Connection name | `Akasha Local PostGIS` |
| Host | `localhost` |
| Port | `15432` |
| Database | `POSTGRES_DB` from `infra/docker/.env` — default `akasha` |
| Username | `POSTGRES_USER` from `infra/docker/.env` — default `akasha_local` |
| Password | `POSTGRES_PASSWORD` from `infra/docker/.env` |

Useful schemas to browse:

- `akasha` — app-owned auth, team, plot, field, season, operation, and reporting tables.
- `pgstac` — catalog tables used by the STAC API.

Recommended read-only checks from DBeaver's SQL editor:

```sql
SELECT current_database(), current_user;
SELECT postgis_full_version();
```

### First user

There is **no bootstrap admin user**. Create the first local account through:

```text
http://localhost:5173/signup
```

Then sign in through:

```text
http://localhost:5173/login
```

Local sign-up is enabled in generated `infra/docker/.env` with:

```env
AUTH_ALLOW_SIGNUP=true
```

Hosted/staging/production environments keep sign-up closed unless intentionally enabled.

## 5. Remote-backed product development mode

Use this mode for the normal development product app when satellite data must come
from the single authoritative ingestion deployment on `akasha-staging`. It starts
only `web`, `api`, `titiler`, `stac-api`, `postgis`, and `minio` locally. The local
PostGIS and MinIO volumes are application-development state; they are separate from
the ingestion deployment and are never used as a satellite archive.

The mode uses the direct private endpoint `http://10.10.2.4:18080` from the API
container. It does not create an SSH tunnel and does not run provider downloads,
COG/composite processing, catalog seeding, `ingestion-worker`, or `ingestion-sar`.

### 5.1 Inject the private key and start

Read the existing ingestion key through the approved Coolify secret channel without
printing it. Supply it to the launcher as a process environment variable; do not put
it in `apps/frontend/.env`, a `VITE_*` variable, shell history, or a tracked file:

```bash
export INGESTION_API_KEY='<private Coolify value>'
make dev-remote
```

The launcher writes only non-secret development settings to the ignored
`infra/docker/.env` and starts a separate Compose project. The expected URLs are:

```text
http://localhost:15173/       Development UI
http://localhost:15173/signup Development signup
http://localhost:15173/login  Development login
http://localhost:18082/health Development gateway health
http://localhost:18082/api/health
http://localhost:18082/api/docs
```

Run `make backend-remote` or `make frontend-remote` when starting the two halves in
separate terminals. Stop this project with `make down-remote`.

The remote mode configures these server-side API values:

```env
WEB_PORT=18082
FRONTEND_PORT=15173
INGESTION_API_URL=http://10.10.2.4:18080
INGESTION_SIGNED_URL_ALLOWED_PREFIX=http://10.10.2.4:18080
INGESTION_SIGNED_URL_FETCH_PREFIX=http://10.10.2.4:18080
INGESTION_READINESS_ENABLED=true
INGESTION_FIELD_INDEX_ENABLED=true
INGESTION_RESOURCESAT_CUTOVER_ENABLED=true
INGESTION_RESOURCESAT_CUTOVER_SOURCE_IDS=resourcesat-2a-liss3-boa,resourcesat-2a-liss4-mx70-l2,resourcesat-2a-awifs-boa
ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false
INGESTION_SSH_TUNNEL_ENABLED=false
```

### 5.2 Remote mode smoke checks

After the gateway is healthy, the launcher runs the same non-secret BFF preflight
manually with:

```bash
docker compose -p akasha-product-dev \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.dev.yml \
  -f infra/docker/docker-compose.product-dev.yml \
  exec -T api python -m app.cli ingestion-check
```

The BFF health response must report `ingestionConfigured`,
`ingestionReadinessEnabled`, and `ingestionFieldIndexEnabled` as `true`, without
returning the API URL, API key, or signed URLs. A development user can then sign up,
log in, view remote sources/dates, and use ingestion-backed field analytics.

For the live product and ingestion checks, use:

```text
https://staging.gis.cidsaglobal.com/
https://staging.gis.cidsaglobal.com/api/health
https://staging.gis.cidsaglobal.com/api/docs
http://10.10.2.4:18080/health  (SSH terminal only)
```

Do not use `http://localhost:18080` on this host. If browser access to ingestion is
needed for a separate diagnostic, use a distinct tunnel such as:

```bash
ssh -N -L 18083:10.10.2.4:18080 <ssh-host-alias>
```

and browse `http://localhost:18083/health`.

### 5.3 Browser leak-check

Browser Network requests must remain same-origin local `/api/*` requests. They must
not contain `10.10.2.4`, `host.docker.internal`, `sig`, `kid`, `exp`, `op`, an API key,
MinIO, STAC, TiTiler, object-storage, or raw COG URLs. Signed ingestion resources are
fetched and adapted by the BFF only.

## Optional SSH-tunnel bridge (legacy alternative)

Use this opt-in mode when you want the local product app to use the deployed ingestion
pipeline for Sentinel-2 NDVI field analytics instead of local ResourceSat COGs. The
browser still talks only to the local app (`/api/*` through the local gateway or Vite
proxy). The local FastAPI BFF calls ingestion server-to-server through an SSH tunnel,
fetches any signed ingestion resources itself, and returns only app-domain responses to
the browser.

Security rules for this mode:

- Never commit a real `INGESTION_API_KEY`; use `CHANGE_ME` in examples and obtain the
  real value through the approved secret channel.
- Put the key only in `infra/docker/.env`. Do not put it in `apps/frontend/.env`, any
  `VITE_*` variable, screenshots, logs, tickets, or docs.
- Signed ingestion URLs and signing query parameters (`sig`, `kid`, `exp`, `op`) must
  never appear in browser-visible responses.
- Production and normal local defaults remain ResourceSat
  (`DEFAULT_SOURCE_ID=resourcesat-2a-liss3-boa`) unless this local opt-in is set.

Related background: [staging ingestion developer guide](staging-ingestion-developer-guide.md),
[data ingestion and satellite rules](data-ingestion-and-satellite-rules.md),
[engineering guardrails](engineering-dos-donts.md), and
[self-hosted deployment guide](../infra/selfhosted/README.md).

### Open the SSH tunnel

Run the tunnel in its own Git Bash, WSL, macOS, or Linux terminal and keep it open while
using the bridge. On Windows, prefer **Git Bash** or WSL; PowerShell is not the supported
shell for these Bash helpers.

```bash
bash scripts/local-ingestion-tunnel.sh --ssh-host akasha-control
```

Equivalent environment-variable form:

```bash
AKASHA_INGESTION_SSH_HOST=akasha-control bash scripts/local-ingestion-tunnel.sh
```

Use your approved SSH host or `user@host` alias if it differs from `akasha-control`. The
helper opens this tunnel and prints the matching non-secret `.env` values:

```text
127.0.0.1:18081 -> 10.10.2.4:18080
```

Fallback raw SSH command, useful for debugging the helper:

```bash
ssh -N -L 127.0.0.1:18081:10.10.2.4:18080 akasha-control
```

The helper intentionally does **not** print `INGESTION_API_KEY`.

### Set the local server-side `.env` values

Edit `infra/docker/.env` before starting or recreating the backend. These keys match the
local Docker env template and are consumed by the `api` container:

```env
DEFAULT_SOURCE_ID=sentinel-2-l2a
INGESTION_API_URL=http://host.docker.internal:18081
INGESTION_API_KEY=CHANGE_ME
INGESTION_READINESS_ENABLED=true
INGESTION_FIELD_INDEX_ENABLED=true
INGESTION_AOI_ID=bangalore_60km_geodesic_aoi
INGESTION_SIGNED_URL_ALLOWED_PREFIX=http://10.10.2.4:18080
INGESTION_SIGNED_URL_FETCH_PREFIX=http://host.docker.internal:18081
INGESTION_TREND_MAX_DATES=12
```

Replace only `INGESTION_API_KEY=CHANGE_ME` with the real key in your ignored local
`infra/docker/.env`. The signed URL allowed prefix must match the deployed ingestion
`AKASHA_PUBLIC_BASE_URL` exactly enough for BFF allow-list validation; the fetch prefix is
the Docker-container route back to your local tunnel.

For the local Sentinel-2-first workflow, these values are required **together**:

- `DEFAULT_SOURCE_ID=sentinel-2-l2a`
- `INGESTION_READINESS_ENABLED=true`
- `INGESTION_FIELD_INDEX_ENABLED=true`
- configured `INGESTION_API_URL`, `INGESTION_API_KEY`,
  `INGESTION_SIGNED_URL_ALLOWED_PREFIX`, and `INGESTION_SIGNED_URL_FETCH_PREFIX`

If readiness is omitted or disabled, Sentinel-2 is hidden from `/api/sources` and the
frontend chooses another effective source. If field-index is omitted or disabled,
statistics, trend, and overlay requests silently fall back to the native ResourceSat path,
which fails on a fresh checkout without local ResourceSat COGs.

### Start the local app

With the tunnel terminal still open, start the app in the usual way:

```bash
make dev
```

Or run the daily split flow:

```bash
make backend
make frontend
```

If you changed `infra/docker/.env` while the backend was already running, restart the
backend so the `api` container receives the new variables:

```bash
make down
make backend
make frontend
```

Then sign up or log in through the printed local frontend URL. The browser should continue
to use the local Vite/gateway origin only.

### Smoke checks

Run the bridge preflight inside the API container. It checks non-secret config,
`INGESTION_API_URL/health`, and authenticated Sentinel-2 readiness for
`INGESTION_AOI_ID` while redacting the key and signed URLs:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml exec -T api \
  python -m app.cli ingestion-check
```

Check the app health booleans through the local gateway. They must be present and should be
`true` for this mode; the response must not include URLs or keys:

```bash
WEB_PORT="$(awk -F= '$1 == "WEB_PORT" { print $2; exit }' infra/docker/.env)"
curl -fsS "http://localhost:${WEB_PORT:-8080}/health"
curl -fsS "http://localhost:${WEB_PORT:-8080}/api/health"
```

Look for:

```json
{
  "ingestionConfigured": true,
  "ingestionReadinessEnabled": true,
  "ingestionFieldIndexEnabled": true
}
```

Manual end-to-end checks require the live tunnel, a valid server-side key, and a local
logged-in user, so they are not part of automated docs validation:

1. Open the local app and confirm Sentinel-2 is the selected/default source.
2. Confirm `GET /api/sources/sentinel-2-l2a/dates` returns remote readiness dates,
   including the known-good smoke date `2026-03-20` when available.
3. Create or import the non-secret example field in
   [`reference/local-sentinel-2-smoke-field.geojson`](reference/local-sentinel-2-smoke-field.geojson).
4. Confirm the field overlay request returns `200 image/png`:
   `/api/fields/{fieldId}/overlay/NDVI.png?sourceId=sentinel-2-l2a&acquisitionDate=2026-03-20`.
5. Confirm field statistics and trend responses for the same field/source/date return
   `provider: "pipeline"`.
6. Confirm the UI shows Sentinel-2 10 m NDVI for the field analytics view.

### Browser leak-check

In browser DevTools, open the **Network** panel, enable **Preserve log**, and filter to
Fetch/XHR. Reload the local app and perform the Sentinel-2 date, overlay, statistics, and
trend actions above. The analytics flow must show only same-origin local app `/api/*`
requests. There must be **no** requests, response bodies, query strings, or copied URLs
containing:

- the ingestion host or IP, including `10.10.2.4`;
- `host.docker.internal`;
- signed URL parameters such as `sig`, `kid`, `exp`, or `op`;
- `INGESTION_API_KEY` or any API-key value;
- MinIO, STAC/pgSTAC, TiTiler, object-storage, or raw COG URLs.

If any of those appear in the browser network log, stop using the mode and treat it as a
security bug. The BFF must fetch signed ingestion resources server-side and return only
local app-domain `/api/*` responses.

## 6. Recommended daily workflow: backend and frontend separately

Use two terminals.

### Terminal 1 — backend/gateway/services

```bash
make backend
```

Equivalent without `make`:

```bash
bash scripts/dev-local.sh --backend-only
```

This starts/prepares:

- `web`
- `api`
- `titiler`
- `stac-api`
- `postgis`
- `minio`
- one-shot ingestion seed/check steps

It also applies API migrations and prints the gateway and signup/login URLs.

### Terminal 2 — frontend

```bash
make frontend
```

Equivalent without `make`:

```bash
bash scripts/dev-local.sh --frontend-only
```

This starts only Vite and verifies the backend gateway is reachable first.

## 7. Hot reload behavior

### Backend hot reload

Backend source edits under:

```text
apps/api/app/
```

hot reload inside the Docker `api` container through:

```text
infra/docker/docker-compose.dev.yml
```

That overlay bind-mounts API source and runs Uvicorn with reload enabled.

Use backend logs to confirm reloads:

```bash
make backend-logs
```

or:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml logs -f api
```

### Frontend hot reload

Frontend edits under:

```text
apps/frontend/src/
```

hot reload through Vite. The browser usually updates automatically.

### What does not hot reload

Some changes still require rebuild/restart. See the next section.

## 8. When to rebuild or restart

### Backend source code only

If you changed only Python source under `apps/api/app/`:

```text
No rebuild needed. Uvicorn reload handles it.
```

### Backend dependencies or Docker image content

Rebuild when changing:

- `apps/api/requirements.txt`
- `apps/api/Dockerfile`
- OS packages in Dockerfile
- files copied into the image but not bind-mounted

Run:

```bash
make backend-rebuild
```

### Frontend source only

If you changed files under `apps/frontend/src/`:

```text
No rebuild needed. Vite HMR handles it.
```

### Frontend dependencies

If you changed:

- `apps/frontend/package.json`
- `apps/frontend/yarn.lock`

restart Vite after installing dependencies:

```bash
cd apps/frontend
corepack yarn install --frozen-lockfile
```

If Corepack is unavailable, use the documented fallback:

```bash
cd apps/frontend
npx --yes yarn install --frozen-lockfile
```

Then restart:

```bash
make frontend
```

### Gateway/static production build

The local Vite workflow does not rebuild the baked production SPA. Rebuild `web` only when validating the production-style gateway image:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml build web
```

### Database or object-store reset

If local credentials or persisted data are broken and you intentionally want a clean local state:

```bash
make reset
make dev
```

`make reset` deletes local PostGIS/MinIO volumes.

## 9. Schema changes with SQLAlchemy + Alembic

API-owned app tables are defined in:

```text
apps/api/app/models.py
```

Migrations live in:

```text
apps/api/alembic/versions/
```

Catalog/pgSTAC migrations are owned by the ingestion worker, not the API.

### Rule for developers

Every SQLAlchemy model change must be committed with an Alembic migration.

Do not manually invent revision IDs. Use the helper target.

### Normal migration workflow

1. Start backend services:

```bash
make backend
```

2. Edit SQLAlchemy models in `apps/api/app/models.py`.

3. Generate a migration:

```bash
make db-revision MSG="add crop metadata"
```

4. Open the generated file in `apps/api/alembic/versions/` and review it carefully.

Check for:

- unintended table drops,
- unintended column drops,
- missing indexes,
- unsafe `NOT NULL` changes without backfill,
- source-specific schema assumptions.

5. Apply the migration locally:

```bash
make db-upgrade
```

6. Confirm the live DB revision:

```bash
make db-current
```

7. Confirm the code and DB agree:

```bash
make db-check
```

8. Confirm the repo has only one Alembic head:

```bash
make db-heads
```

9. Run tests/validation before committing:

```bash
cd apps/api
python -m pytest -q
```

### Parallel migration conflicts

If two developers create migrations from the same parent revision, Alembic will have multiple heads. CI will fail.

Fix it by rebasing on the latest branch, then either:

- update/regenerate your migration against the current head, or
- create an explicit merge revision:

```bash
make db-merge-heads MSG="merge migration heads"
```

Then rerun:

```bash
make db-heads
make db-upgrade
make db-check
```

### Production migration behavior

The API image runs app-schema migrations on startup for the current single-replica deployment model. Migration failure prevents the API from starting, which is intentional.

Before moving to multiple API replicas, migrate to a dedicated single-run migrator/pre-deploy job and let API startup only verify schema state.

## 10. Common commands

```bash
make help             # list developer commands
make dev              # backend + frontend together; Vite keeps running until Ctrl+C
make backend          # backend/gateway/services only
make frontend         # frontend only, backend must already be running; Ctrl+C stops Vite
make backend-logs     # follow API logs; Ctrl+C stops log following only
make backend-rebuild  # rebuild API image
make down             # stop Docker services, keep volumes
make reset            # destructive: stop services and delete local DB/object-store volumes
make test             # API tests
make validate         # Slice 0 validator
```

Additional validators:

```bash
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
```

Smoke test against a running gateway:

```bash
WEB_PORT="$(awk -F= '$1 == "WEB_PORT" { print $2; exit }' infra/docker/.env)"
python scripts/smoke-test.py "http://localhost:${WEB_PORT:-8080}"
```

If local auth is enabled, the product endpoints in the smoke test require login. Create/sign in with a local account first, then run:

```bash
WEB_PORT="$(awk -F= '$1 == "WEB_PORT" { print $2; exit }' infra/docker/.env)"
export AKASHA_SMOKE_USERNAME="you@example.com"
export AKASHA_SMOKE_PASSWORD="<your local password>"
python scripts/smoke-test.py "http://localhost:${WEB_PORT:-8080}" --login
```

Equivalent `make` wrapper:

```bash
WEB_PORT="$(awk -F= '$1 == "WEB_PORT" { print $2; exit }' infra/docker/.env)"
export AKASHA_SMOKE_USERNAME="you@example.com"
export AKASHA_SMOKE_PASSWORD="<your local password>"
AKASHA_SMOKE_LOGIN=1 make smoke BASE_URL="http://localhost:${WEB_PORT:-8080}"
```

Without `--login`/`AKASHA_SMOKE_LOGIN=1`, authenticated local stacks return `401` for product endpoints such as `/api/config`.
Raster tile/statistic checks can still report `BLOCKED` until real ResourceSat composite COGs are present in MinIO; that is expected for a metadata-only local seed.

## 11. Troubleshooting

### Docker engine is not reachable

Start Docker Desktop, wait until it is healthy, then retry:

```bash
make backend
```

### Frontend says backend is not reachable

Start backend first:

```bash
make backend
make frontend
```

### Port 8080 or 5173 is busy

The script updates `WEB_PORT` or `FRONTEND_PORT` in `infra/docker/.env` to the
next free port and prints the actual URL. Use the printed URL.

Check current Docker services:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml ps
```

### Sign-up says email already exists

Use the existing local account, or reset local volumes if you intentionally want a clean DB:

```bash
make reset
make dev
```

### Map basemap does not load

Local development should use OSM by default so repeated reloads do not consume
ArcGIS Location Platform billable basemap usage:

```env
VITE_BASEMAP_PROVIDER=osm
```

To validate the hosted ArcGIS basemap path, set the provider to Esri and add a
referrer-restricted key to:

```text
apps/frontend/.env
```

Example:

```env
VITE_BASEMAP_PROVIDER=esri
VITE_ESRI_API_KEY=<your referrer-restricted key with Basemaps privilege>
```

The billing model is not a Vite setting. The BFF returns it from `/api/config`.
For deliberate local Esri validation, set this in `infra/docker/.env`:

```env
# Validate compatibility first.
ESRI_BASEMAP_USAGE_MODEL=session

# Then validate direct-token tile usage.
# ESRI_BASEMAP_USAGE_MODEL=tile
```

Restart Vite after changing frontend env values. Recreate the API container after
changing `ESRI_BASEMAP_USAGE_MODEL`. In tile mode, browser network tools must show
the Basemap Styles request and no request whose path contains `/sessions/start`.

### Backend edit does not reload on Windows

The dev overlay sets polling by default. If reload still feels stale:

```bash
make backend-logs
make backend-rebuild
```

For best Docker Desktop performance, consider cloning the repo inside WSL2's Linux filesystem instead of under `/mnt/c`.

## 12. Cleanup guidance

Use these when the local environment gets confusing:

```bash
make down   # stop services, keep data
make reset  # delete local DB/object-store volumes
```

Do not delete committed seed files under `data/seed/`. Large/raw generated data belongs under ignored `data/raw/` and `data/work/`.

Ignored local files you can safely recreate:

- `infra/docker/.env`
- `apps/frontend/.env`
- Docker volumes created by the local compose stack

## 13. Command verification notes

Last checked on Windows/Git Bash on 2026-06-17 with Git 2.54, Docker Compose v5.1, Node 24, Corepack 0.34, and GNU Make 4.4:

- `make dev`, `make backend`, `make frontend`, `make backend-rebuild`, API log following, and the production-style `web` image build all start successfully.
- `make lint` and `make build` pass; `make build` uses cached Docker layers when images are already current.
- `make db-upgrade`, `make db-current`, `make db-check`, and `make db-heads` pass against the running Docker API/PostGIS stack.
- `make validate`, `python scripts/validate_slice0.py`, `python scripts/validate_slice1.py`, and `python scripts/validate_slice2.py` pass.
- `make test` passes for the API test suite (`221 passed, 2 skipped` in the verification run).
- Frontend `corepack yarn install --frozen-lockfile`, `corepack yarn build`, `corepack yarn lint`, and `corepack yarn test` pass (`191` frontend tests in the verification run).
- `python scripts/smoke-test.py ... --login` and `AKASHA_SMOKE_LOGIN=1 make smoke ...` pass when supplied a valid local account; unauthenticated smoke fails product checks with `401` when local auth is enabled.

The following commands are intentionally state-changing and should not be used as routine verification unless you mean it:

- `make reset` deletes local PostGIS and MinIO volumes.
- `make db-revision MSG="..."` creates a new Alembic migration file.
- `make db-merge-heads MSG="..."` creates an Alembic merge revision.

## 14. Quick start summary

For a new developer:

```bash
git clone <repo-url> akasha-project
cd akasha-project
make dev
```

Then open the printed `/signup` URL, create an account, and start working.

For daily development after first setup:

```bash
make backend
make frontend
```
