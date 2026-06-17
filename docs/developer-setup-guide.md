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
| Ingestion worker | Docker one-shot | No | Seeds catalog/storage and runs ingestion jobs. |
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
7. Seeds catalog/storage via the ingestion worker.
8. Starts Vite with hot reload.

The script prints the actual frontend, login, signup, and backend URLs. Default URLs are usually:

```text
Frontend: http://localhost:5173/
Sign up:  http://localhost:5173/signup
Login:    http://localhost:5173/login
Backend:  http://localhost:8080
```

If ports are busy, or if `infra/docker/.env` already has a different `WEB_PORT`, the script picks/reuses the working port and prints the actual URL. Treat the printed URLs as the source of truth.

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

## 5. Recommended daily workflow: backend and frontend separately

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

## 6. Hot reload behavior

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

## 7. When to rebuild or restart

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

## 8. Schema changes with SQLAlchemy + Alembic

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

## 9. Common commands

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

## 10. Troubleshooting

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

The script chooses the next free port and prints the actual URL. Use the printed URL.

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

Add an Esri basemap key to:

```text
apps/frontend/.env
```

Example:

```env
VITE_ESRI_API_KEY=<your referrer-restricted key with Basemaps privilege>
```

Restart Vite after changing frontend env values.

### Backend edit does not reload on Windows

The dev overlay sets polling by default. If reload still feels stale:

```bash
make backend-logs
make backend-rebuild
```

For best Docker Desktop performance, consider cloning the repo inside WSL2's Linux filesystem instead of under `/mnt/c`.

## 11. Cleanup guidance

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

## 12. Command verification notes

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

## 13. Quick start summary

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
