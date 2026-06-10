# Akasha — Railway MVP

Geospatial MVP for browsing true-colour Sentinel-2 imagery over an Area of
Interest (Bangalore) and computing cloud-masked vegetation-index statistics for
user-drawn plots. Railway-first, but fully portable to Docker Compose / on-prem.

> **Status: Slice 4 implementation in progress.** Slice 0 (skeleton), Slice 1
> (storage/catalog), Slice 2 (raster de-risk), and Slice 3 (BFF product + plot
> contracts) are implemented. The canonical frontend map/product shell now lives
> in `apps/frontend`. Railway/local Docker still run the same multi-service
> topology described below.

## Architecture (one public service)

```
Browser ──> web (Caddy + React SPA)  ── /api/*  ──> api (FastAPI BFF)
                  │                   ── /tiles/* ─> titiler (rio-tiler/GDAL)
                  │
   api ──> stac-api (pgSTAC) ──> postgis (PostgreSQL + PostGIS)
   api ──> titiler ──> minio (S3-compatible COG storage)
   ingestion-worker ──> minio / stac-api / postgis
```

Only the **`web`** gateway is publicly reachable. The browser calls `/api/*`
and `/tiles/*` on that same origin; the gateway proxies to the internal `api`
and `titiler` services. `api`, `titiler`, `stac-api`, `postgis`, and `minio`
are never given a public domain.

## Repository layout

```text
apps/
  frontend/          Canonical React + Vite + TypeScript SPA
  api/               Canonical FastAPI BFF (/api product, plot, auth, ops APIs)
services/
  titiler/           TiTiler image/config (RGB display tiles)
  stac-api/          stac-fastapi-pgstac wrapper/config
  ingestion/         Python ingestion worker and STAC/MinIO seed loader
  ingestion-sar/     Sentinel-1/SAR preprocessing runtime
infra/
  gateway/           Caddy reverse proxy + multi-stage web Dockerfile
  railway/           Per-service Railway config + env matrix + deploy notes
  docker/            Local docker-compose.yml (dev / on-prem portability)
docs/                Source-of-truth product/architecture/deploy docs
scripts/             validate_slice0.py + smoke-test.py
```

When changing application behavior, edit `apps/api` and `apps/frontend`.

## Services & health endpoints

| Service | Public | Internal port | Health | Image (pinned) |
|---|---:|---:|---|---|
| web (gateway) | yes | 80 | `GET /health` | `caddy:2.10-alpine` + React build |
| api (FastAPI BFF) | no | 8000 | `GET /health` | `python:3.11-slim` |
| titiler | no | 8000 | `GET /healthz` | `ghcr.io/developmentseed/titiler:1.0.0` |
| stac-api | no | 8080 | `GET /_mgmt/ping` | `ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2` |
| postgis | no | 5432 | `pg_isready` | `postgis/postgis:16-3.5` |
| minio | no | 9000 | `/minio/health/live` | `minio/minio:RELEASE.2025-09-07T16-13-09Z` |
| ingestion-worker | no | — | CLI | `python:3.11.14-slim-bookworm` |

## Local development: one command with frontend hot reload

This is the recommended workflow for day-to-day development. It runs the
backend/API/data services in Docker, runs the React/Vite frontend locally for
hot reload, and keeps the browser contract exactly like production:
same-origin `/api/*` and `/tiles/*` through the gateway.

### Prerequisites

- **Docker Desktop** (or Docker Engine) with Compose: `docker compose version`
- **Node.js 20+** with `npx` available
- **Git Bash**, WSL, macOS/Linux shell, or another shell that can run `bash`
- Optional: `make`. If `make` is not installed, use the `bash` command below.

### Start everything

From the repository root:

```bash
make dev
```

If `make` is unavailable:

```bash
bash scripts/dev-local.sh
```

The command does the boring-but-important setup automatically:

1. Verifies required local tools are available and Docker Desktop/Engine is running
2. Creates ignored local env files if missing:
   - `infra/docker/.env` with generated local-only Docker secrets
   - `apps/frontend/.env` for Vite basemap settings
3. Checks whether the configured Docker gateway port is already occupied
4. Starts the Docker stack: `web`, `api`, `titiler`, `stac-api`, `postgis`, `minio`
5. Waits for gateway/API health checks
6. Applies API migrations with `python -m app.cli db upgrade`
7. Runs API storage checks with `python -m app.cli check`
8. Seeds catalog/storage with `worker.py seed`
9. Bootstraps a local admin user if no password user exists
10. Starts Vite with hot reload, using the next free frontend port if `5173` is busy

The same command is safe for both **first run** and **repeat runs**. Migrations,
API checks, and seed loading are intentionally idempotent, so the team does not
need a separate “first-time setup” command.

Open:

```text
http://localhost:5173/   # default; use the URL printed by the script if 5173 is busy
```

Local login:

```text
URL:      http://localhost:5173/login   # default; use the printed frontend port if changed
Username: admin
Password: AkashaLocal2026!
```

You can override the local bootstrap credentials before first run:

```bash
AKASHA_LOCAL_ADMIN_USER=myadmin AKASHA_LOCAL_ADMIN_PASSWORD='change-me-local-only' make dev
```

### Esri basemap key

The app can start without an Esri key, but the map view needs one to render the
configured Esri imagery basemap. Add your referrer-restricted ArcGIS Location
Platform key to `apps/frontend/.env`:

```env
VITE_ESRI_API_KEY=<your referrer-restricted key with Basemaps privilege>
```

If you set `VITE_ESRI_API_KEY` before the first `make dev`, the script copies it
into both generated local env files.

### Backend/gateway only

If you want the Docker stack prepared without starting Vite:

```bash
make up
```

or:

```bash
bash scripts/dev-local.sh --backend-only
```

The gateway URL is based on `WEB_PORT` in `infra/docker/.env`. The default is
`http://localhost:8080`. If that port is already occupied by the Akasha gateway,
the script reuses it. If another process owns the port, the script updates
`WEB_PORT` to the next free port and prints the actual backend URL. Vite reads
that value automatically, so you do not need to manually set
`AKASHA_DEV_PROXY_TARGET` for normal local development.

The frontend prefers `FRONTEND_PORT=5173`. If that port is already in use, the
script starts Vite on the next free port and prints the actual frontend/login
URL. Set `FRONTEND_PORT` only when you intentionally want a different preferred
port.

### Stop, restart, reset

Stop only the hot-reload frontend with `Ctrl+C`. Docker services keep running.

```bash
make down      # stop Docker services, keep local data volumes
make reset     # stop Docker services and delete PostGIS/MinIO volumes
make dev       # start again from a clean or existing state
```

If PostgreSQL or MinIO credentials were changed after volumes already existed,
run `make reset` once so Docker recreates the volumes with the new credentials.

### Troubleshooting quick checks

```bash
docker compose -f infra/docker/docker-compose.yml ps
curl http://localhost:5173/api/health
docker compose -f infra/docker/docker-compose.yml logs api --tail=100
```

Common causes:

- `Docker engine is not reachable`: Docker Desktop is installed but not running;
  start it and rerun `make dev`.
- `Frontend startup needs yarn, corepack, or npx`: install Node.js 20+ and rerun
  `make dev`.
- `curl http://localhost:5173/api/health` fails: Vite is not running, or the
  Docker gateway is unhealthy. If the script selected a different frontend
  port, use that printed port instead of `5173`.
- `http://localhost:8080` fails but containers are healthy: check the printed
  backend URL or `WEB_PORT` in `infra/docker/.env`; this workspace may use
  `18080` or another free port.
- Map says the basemap is not configured: set `VITE_ESRI_API_KEY` in
  `apps/frontend/.env` and restart Vite.
- Auth bootstrap is skipped: a local password user already exists; use the
  existing local account or run `make reset` if you intentionally want a clean
  database.

### Optional static validation — no Docker required

```bash
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
```

Domain invariants seeded by this flow: frozen analytic band order
`[B04,B08,B05,B06,B07,B11,B12,B03,B02]`; true-colour RGB = bands `[1,8,9]`;
reflectance `scale 0.0001` / `offset -0.1`. See
[`data/seed/README.md`](data/seed/README.md) and
[`infra/railway/README.md`](infra/railway/README.md) for the seed layout and the
Railway equivalents of these commands.

## Deploy to Railway

Each service is a **separate** Railway service. See
[`infra/railway/README.md`](infra/railway/README.md) for the service→config
matrix, environment variables ([`ENV_MATRIX.md`](infra/railway/ENV_MATRIX.md)),
and the deployment sequence.

## Slice roadmap

| Slice | Focus | Status |
|---|---|---|
| 0 | Repository & service skeleton | **done** |
| 1 | Database, catalog & object storage foundation | **done** |
| 2 | Raster de-risk (tile + masked NDVI statistic) | **done** |
| 3 | BFF API implementation | **done** |
| 4 | Frontend map & layer UX | **implemented; active hardening** |
| 5 | Plot & index UX | planned |
| 6 | Railway deployment hardening | planned |
| 7 | Acceptance & QA | planned |

Engineering guardrails: [`docs/engineering-dos-donts.md`](docs/engineering-dos-donts.md).

---

### Azure akasha-control login

```bash
ssh -i ~/.ssh/id_ed25519_thaarei akashaadmin@20.204.163.166

or

ssh akasha-control
```

### Preview note

This repository now keeps only the canonical multi-service tree. The old
root-level Emergent preview shims (`backend/` and `frontend/`) were removed so
there is one backend and one frontend source of truth: `apps/api` and
`apps/frontend`.
