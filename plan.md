# Slice 0 Plan (Skeleton Only) — Akasha Railway MVP (UPDATED)

## 1) Objectives

- Produce a **Railway-compatible multi-service monorepo skeleton** matching the documented topology:
  - **Only `web` (gateway) is public**.
  - `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker` are private.
- Add **per-service Dockerfiles**, **Railway configs**, **local Docker Compose** (as files), and **`.env.example`** files containing **placeholders only**.
- Implement **health endpoints/contracts** for:
  - Gateway: `GET /health` (inside the `web` service)
  - API: `GET /health` (container/railway health) and `GET /api/health` (same-origin gateway/ingress)
  - TiTiler: `GET /healthz`
  - STAC API: `GET /_mgmt/health`
- Provide a polished **LIVE Emergent “Service Skeleton Status Dashboard”** (existing CRA frontend) backed by the API skeleton endpoints (`/api/_skeleton/*`).
- Validate Slice 0 artifacts via **parse/lint + file/contract checks** (since Emergent has no Docker daemon). Runtime validation is deferred to **Railway / local Docker**.

**Status (now):** All Slice 0 build deliverables are implemented and validated. Remaining work is **formal E2E validation via testing_agent_v3** plus documenting the Emergent ingress nuance for `/health`.

## 2) Implementation Steps

### Phase 1 — Core POC (Isolated): “Skeleton Integrity + Health Contract”

Core workflow (Slice 0): generate the full multi-service skeleton artifacts and prove their **health contracts** + **Railway readiness** without running Docker.

User stories:
1. As a developer, I want `scripts/validate_slice0.py` to fail fast if any required service Dockerfile/config is missing.
2. As a developer, I want pinned image versions checked so Railway builds don’t break due to floating/nonexistent tags.
3. As a developer, I want docker-compose YAML to be syntactically valid and include all services with correct healthchecks.
4. As a developer, I want `.env.example` files to contain placeholders only so no secrets leak.
5. As a developer, I want api `/health` and `/api/health` to return 200 consistently so Railway health checks are reliable.

Steps (COMPLETED):
- ✅ Created monorepo folders per docs: `apps/`, `services/`, `infra/`, `scripts/`, and preserved `/app/docs`.
- ✅ Implemented canonical skeleton FastAPI app in `apps/api` with:
  - `GET /health` (200 JSON)
  - `GET /api/health` (200 JSON)
  - `GET /api/_skeleton/services` (service registry: public rule, health paths, live/defined)
  - `GET /api/_skeleton/manifest` (slice metadata, pinned images, scope, optional repo tree)
  - `GET /api/_skeleton/env-matrix` (env var names per service; placeholders only)
  - Uses FastAPI **lifespan** handler (no deprecated `on_event`).
- ✅ Added `scripts/validate_slice0.py`:
  - Parses `infra/docker/docker-compose.yml`
  - Verifies required services exist (7) and only `web` publishes host ports
  - Verifies healthchecks + persistent volumes for `postgis`/`minio`
  - Verifies pinned image tags + pinned base images in Dockerfiles
  - Verifies Railway healthcheck paths in `railway.json` files
  - Ensures `.env.example` values for secret-like vars are placeholders
- ✅ Ran POC checks in Emergent:
  - `scripts/validate_slice0.py` **PASSED 94/0**
  - `apps/api` unit tests **6/6 passed**

### Phase 2 — V1 App Development (Slice 0 deliverables)

User stories:
1. As an operator, I want a single public `web` service that serves the frontend and proxies `/api/*` and `/tiles/*` same-origin.
2. As a developer, I want `docker-compose up` (outside Emergent) to bring up web/api/titiler/stac/postgis/minio/ingestion with correct networking.
3. As a developer, I want each internal service to have a documented health endpoint and Railway healthcheck path.
4. As a developer, I want a Vite+TS `apps/frontend` skeleton that can be built into the `web` gateway container.
5. As a developer, I want the live Emergent dashboard to clearly show service status, required env vars, and what’s intentionally out of scope.

Steps (COMPLETED):
- ✅ **Web gateway (Railway public only)**
  - `infra/gateway/Caddyfile`:
    - `/health` → `200 ok`
    - `/api/*` → reverse-proxy to `api`
    - `/tiles/*` → reverse-proxy to `titiler`
    - `/*` → static SPA + history fallback
  - `infra/gateway/Dockerfile` (multi-stage): build `apps/frontend` → serve via `caddy:2.8-alpine`.
- ✅ **apps/frontend (Railway-deployable skeleton; NOT the live preview)**
  - Vite + React + TypeScript placeholder landing page.
  - Proves same-origin contract by fetching `/api/_skeleton/services`.
  - Includes Dockerfile (optional standalone), `.env.example`, and a generated `yarn.lock`.
- ✅ **apps/api (Railway-deployable skeleton)**
  - Dockerfile (`python:3.11-slim`) + pinned minimal deps.
  - Only skeleton endpoints (no BFF product endpoints like `/api/config`).
- ✅ **services/titiler**
  - Wrapper Dockerfile pinned to `ghcr.io/developmentseed/titiler:1.0.0`.
  - Health path documented/used: `/healthz`.
- ✅ **services/stac-api**
  - Dockerfile pinned to `ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2`.
  - Health path documented/used: `/_mgmt/health`.
- ✅ **services/ingestion**
  - Skeleton worker CLI (no ingestion) pinned to `python:3.11-slim`.
  - `worker.py info` and `worker.py healthcheck` (env validation), no public HTTP surface.
- ✅ **postgis + minio**
  - Compose uses pinned images:
    - `postgis/postgis:16-3.5` health = `pg_isready`.
    - `minio/minio:RELEASE.2025-10-15T17-29-55Z` health = `/minio/health/live`.
  - Persistent volumes: `postgis_data`, `minio_data`.
  - `MINIO_BROWSER=off`.
- ✅ **infra/docker**
  - `infra/docker/docker-compose.yml` defines 7 services with healthchecks.
  - Only `web` publishes a host port.
  - `infra/docker/.env.example` provides non-default placeholders.
- ✅ **infra/railway**
  - `infra/railway/README.md` includes service→config matrix and deployment sequence.
  - `infra/railway/ENV_MATRIX.md` matches the deployment guide (no aliases).
  - `infra/railway/web.railway.json` and root `/railway.json` exist.
  - Per-service `railway.json` exists in each code service folder.
- ✅ **Shared conventions**
  - `pyproject.toml` (ruff/black/isort), `.editorconfig`, `.prettierrc.json`, `Makefile`, `.gitignore`, root `README.md`.
- ✅ **LIVE Emergent preview**
  - `/app/backend/server.py` mounts the canonical `apps/api` FastAPI app (DRY).
  - `/api/*` endpoints reachable and returning 200 in the live preview.
  - CRA “Service Skeleton Status Dashboard” implemented with:
    - Service topology cards (7)
    - Request-flow diagram showing public-origin rule
    - Live health checks (3 endpoints)
    - Pinned images table
    - Monorepo tree
    - In-scope vs deferred scope lists
    - 8-step roadmap
    - Interactive env-matrix accordion
    - Loading and error states

Conclude Phase 2 (COMPLETED):
- ✅ Ran `scripts/validate_slice0.py` (PASSED 94/0).
- ✅ Ran unit tests for api skeleton (6/6).
- ✅ Confirmed live endpoints and dashboard rendering via screenshots.

**Emergent ingress note (for test planning):** In the Emergent preview, externally reachable health is `GET /api/health` (ingress routes `/api/*`). `GET /health` is a Railway/container health path intended for the `api` service itself and may not be reachable on the preview URL.

### Phase 3 — Adding More Features (explicitly NOT implemented in Slice 0)

User stories (for later; document only):
1. As a user, I want `/api/config` to drive map defaults and limits.
2. As a user, I want to browse sources/dates with cloud/usable-pixel metrics.
3. As a user, I want true-colour tiles to render from MinIO via TiTiler.
4. As a user, I want to draw/import a plot polygon and save it.
5. As a user, I want cloud-masked NDVI stats computed by the BFF.

(Do not implement; keep contracts unpolluted and folders ready.)

## 3) Next Actions

1. **Run formal E2E testing via `testing_agent_v3`**:
   - Validate frontend dashboard loads.
   - Validate API skeleton endpoints:
     - `GET /api/health`
     - `GET /api/_skeleton/services`
     - `GET /api/_skeleton/manifest`
     - `GET /api/_skeleton/env-matrix`
   - Validate loading/error handling (simulate backend down if feasible).
2. Confirm smoke test behavior against the live preview base URL:
   - `python scripts/smoke-test.py https://railway-mvp-slice.preview.emergentagent.com`
3. (Optional, Railway workflow) Push to GitHub and deploy on Railway; verify:
   - `web` public domain serves `/health`.
   - `web` proxies `/api/*` to `api` and `/tiles/*` to `titiler`.
   - `api`, `titiler`, `stac-api` healthchecks are green.
   - `postgis` and `minio` have volumes attached and remain private.

## 4) Success Criteria (Slice 0 exit)

- ✅ Repo structure matches docs: `apps/*`, `services/*`, `infra/*`, `docs/*`, `scripts/*`.
- ✅ All required Dockerfiles exist; image versions are pinned as specified.
- ✅ `infra/docker/docker-compose.yml` is valid YAML and defines: web, api, titiler, stac-api, postgis, minio, ingestion-worker.
- ✅ Only `web` publishes a host port; `postgis` and `minio` have persistent volumes.
- ✅ `.env.example` files exist per service and contain placeholders only (no default creds).
- ✅ Live preview:
  - `GET /api/health` returns 200
  - `GET /api/_skeleton/services` returns expected JSON
  - `GET /api/_skeleton/manifest` returns pinned images + scope
  - Dashboard renders, shows topology, health, pinned images, repo tree, scope, roadmap, and env matrix.
- ✅ No out-of-scope endpoints/features are implemented (no `/api/config`, no STAC/MinIO/PostGIS logic, no raster/index logic, no map UX).
- ⏳ Remaining to mark complete: formal E2E run via `testing_agent_v3` against the live preview.
