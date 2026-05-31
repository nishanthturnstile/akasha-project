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
  - STAC API: `GET /_mgmt/ping`
- Provide a polished **LIVE Emergent “Service Skeleton Status Dashboard”** (existing CRA frontend) backed by the API skeleton endpoints (`/api/_skeleton/*`).
- Validate Slice 0 artifacts via **parse/lint + file/contract checks** (since Emergent has no Docker daemon). Runtime validation is deferred to **Railway / local Docker**.

**Status (now):** All Slice 0 deliverables are implemented and validated, including **formal E2E validation** via `testing_agent_v3` and a smoke test compatible with edge/CDN filters.

> **Slice 1 context (added):** Slice 1 (Storage/Catalog) is also complete as artifact-generation + static validation only (per user choice to defer live runtime exit-criteria checks to Railway). Slice 0 remains unchanged in behavior and UI.

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
  - `infra/gateway/Dockerfile` (multi-stage): build `apps/frontend` → serve via `caddy:2.10-alpine`.
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
  - Health path documented/used: `/_mgmt/ping`.
- ✅ **services/ingestion**
  - Worker CLI (no public HTTP surface).
  - Slice 0: `info` and `healthcheck`.
- ✅ **postgis + minio**
  - Compose uses pinned images:
    - `postgis/postgis:16-3.5` health = `pg_isready`.
    - `minio/minio:RELEASE.2025-09-07T16-13-09Z` health = `/minio/health/live`.
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
  - ✅ Root `.dockerignore` added to reduce web build context and exclude secrets and operator rasters.
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
- ✅ Formal E2E via `testing_agent_v3` **PASSED 16/16**.
- ✅ `scripts/smoke-test.py` updated to send a browser-like User-Agent so it works behind edge/CDN bot filters.

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

### Slice 0 next actions (DONE)

1. ✅ Ran formal E2E testing via `testing_agent_v3`.
2. ✅ Confirmed smoke test behavior against the live preview base URL.
3. ✅ (Workflow) Push to GitHub and deploy on Railway for runtime validation.

### Slice 1 next actions (Storage/Catalog — runtime checks deferred to Railway)

Even though Slice 1 artifacts are complete, the following runtime checks must be executed on Railway/local Docker to satisfy Slice 1 exit criteria:

1. Apply api-owned app schema (plots) once PostGIS is provisioned:
   - `python -m app.cli migrate`
   - Verify: `python -m app.cli check` (prints `SELECT postgis_version()` and confirms `akasha.plots` exists)
2. Seed catalog + storage (idempotent):
   - `python worker.py seed` (pgSTAC migrate → load STAC collection+item → ensure MinIO bucket+keys)
3. Verify Slice 1 exit criteria in one command:
   - `python worker.py verify`
     - checks PostGIS version
     - checks STAC API returns `/collections/sentinel-2-l2a`
     - checks MinIO bucket is reachable from the worker container

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
- ✅ No out-of-scope endpoints/features are implemented (no `/api/config`, no STAC/MinIO/PostGIS product logic, no raster/index logic, no map UX).
- ✅ Formal E2E run via `testing_agent_v3` against the live preview completed.

---

# Slice 1 Plan (Storage / Catalog) — Akasha Railway MVP (ADDED)

## 1) Objectives

- Stand up the **data foundation** (as Railway-compatible artifacts) while preserving Slice 0 service boundaries:
  - PostGIS **app schema** owned by the `api` for plots (named polygons) and app settings.
  - pgSTAC schema management owned by the ingestion worker (via **pypgstac**) backing `stac-api`.
  - Deterministic MinIO **bucket/key layout** for COG assets (`akasha-cogs`, keys under `sentinel-2-l2a/{acquisitionDate}/...`).
- Provide **idempotent seeding** keyed on:
  - `{satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}`
- Seed a Sentinel‑2 L2A **STAC collection + sample item** that matches:
  - Frozen 9-band analytic order: `[B04,B08,B05,B06,B07,B11,B12,B03,B02]`
  - True-colour RGB band positions: `[1,8,9]`
  - Reflectance convention: raw uint16 DN; `scale=0.0001`, `offset=-0.1` (**not -1000**)
  - SCL: uint8 categorical with classes `0..11`; default excluded classes `0,1,2,3,7,8,9,10,11`
  - Required extensions: `eo`, `raster`, `projection`, `classification` (and collection item-assets)
- Keep secrets safe:
  - `.env.example` placeholders only
  - No default credentials
  - Only `web` is public

**Status (now):** Slice 1 deliverables are implemented and statically validated in Emergent. The three runtime exit criteria are deferred to Railway/local Docker per user choice.

## 2) Implementation Steps

### Phase 1 — App schema (plots) owned by `api`

User stories:
1. As a developer, I want an idempotent SQL migration that creates `akasha.plots` with PostGIS geometry.
2. As an operator, I want a simple CLI to apply/check the app schema without introducing product endpoints.

Steps (COMPLETED):
- ✅ Added `apps/api/migrations/001_app_schema.sql` (idempotent) creating:
  - `akasha.plots` (uuid, name, geometry Polygon/4326, area_ha, timestamps, GIST index, updated_at trigger)
  - `akasha.index_requests` (audit)
  - `akasha.app_settings` (seeded defaults including Bangalore AOI)
- ✅ Added `apps/api/app/{db.py,cli.py}` with lazy psycopg import:
  - `python -m app.cli migrate`
  - `python -m app.cli check` (SELECT postgis_version + table presence)
- ✅ Updated `apps/api/requirements.txt` with `psycopg[binary]` (lazy imported)
- ✅ Updated `apps/api/Dockerfile` to `COPY migrations`.

### Phase 2 — Catalog (pgSTAC) + seed STAC collection/item

User stories:
1. As a developer, I want pgSTAC migrations driven by a pinned pypgstac version that matches the STAC API image.
2. As an operator, I want a deterministic STAC seed that matches the band-order and reflectance conventions.

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/catalog.py`:
  - `migrate_catalog()` (pypgstac)
  - `load_collection()` + `load_items()` via idempotent upsert
- ✅ Added seed STAC JSON:
  - `data/seed/stac/sentinel-2-l2a-collection.json`
  - `data/seed/stac/sentinel-2-l2a-sample-item.json`
  - Validated: frozen band order; scale/offset; SCL classes; proj EPSG 32643; idempotency props.

### Phase 3 — Object storage (MinIO) deterministic bucket/key layout

User stories:
1. As an operator, I want the MinIO bucket created and the deterministic keys present.
2. As a developer, I want placeholder objects created when real rasters are absent (operator-provided, not committed).

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/storage.py`:
  - `ensure_bucket()`
  - `seed_keys()` creates:
    - `akasha-cogs/sentinel-2-l2a/2026-01-15/analytic.tif`
    - `akasha-cogs/sentinel-2-l2a/2026-01-15/scl.tif`
  - If operator rasters are absent, uploads **empty placeholder objects** at those keys.
  - `bucket_reachable()` for runtime verification.

### Phase 4 — Idempotent seeding orchestration + exit-criteria verifier

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/scene.py`:
  - Deterministic `SceneIdentity` + `scene_key` and `item_id`
  - Sample scene key: `sentinel-2-l2a:L2A:43PGQ:2026-01-15T05:20:00Z:05.00`
- ✅ Added `services/ingestion/akasha_ingest/seed.py`:
  - `seed_all()` = pgSTAC migrate → load STAC → seed MinIO
- ✅ Added `services/ingestion/akasha_ingest/verify.py`:
  - PostGIS: `SELECT postgis_version()`
  - STAC API: `GET /collections/sentinel-2-l2a`
  - MinIO: bucket reachable/listable
- ✅ Upgraded `services/ingestion/worker.py` CLI to include:
  - `migrate-catalog`, `seed-stac`, `seed-minio`, `seed`, `verify` (plus info/scene-key/healthcheck)

### Phase 5 — Wiring, Railway/Compose alignment, and static validation

Steps (COMPLETED):
- ✅ Updated ingestion to build from repo root and include seed data:
  - `services/ingestion/Dockerfile` copies `data/seed`
  - `services/ingestion/railway.json` points to `services/ingestion/Dockerfile` and requires Railway Root Directory = repo root.
- ✅ Updated `infra/docker/docker-compose.yml` ingestion worker:
  - build context = repo root
  - env includes `S3_REGION`, `AKASHA_COG_BUCKET`, `SEED_DATA_DIR`.
- ✅ Added/updated seed layout:
  - `data/seed/{bangalore-aoi.geojson,sample-plot.geojson,README.md,.gitignore}`
- ✅ Updated root `.dockerignore` to exclude `data/seed/rasters` (operator-provided).
- ✅ Updated `infra/railway/README.md` with Slice 1 deploy+seed+verify sequence and ingestion root-dir note.
- ✅ Added `scripts/validate_slice1.py` and ran:
  - `scripts/validate_slice1.py` **PASSED 61/0**
  - `scripts/validate_slice0.py` **PASSED 94/0** (no regression)
  - Lint clean; py_compile OK; `worker.py info` works without heavy deps.

## 3) Next Actions

Runtime validation is deferred to Railway/local Docker per user choice.

1. Railway bootstrap sequence:
   - Provision `postgis` (with volume) and verify PostGIS is installed.
   - Deploy `api` and run: `python -m app.cli migrate`.
   - Deploy `stac-api`.
   - Deploy `ingestion-worker` and run: `python worker.py seed`.
2. Run the Slice 1 exit-criteria verifier:
   - `python worker.py verify`

## 4) Success Criteria (Slice 1 exit)

**Artifacts (done in Emergent):**
- ✅ App schema migration for plots exists and is idempotent.
- ✅ pgSTAC migration + STAC seed tooling exists (idempotent upsert).
- ✅ STAC collection seed conforms to frozen band order and reflectance conventions.
- ✅ MinIO bucket/key layout + placeholders are implemented.
- ✅ Static Slice 1 validator passes; Slice 0 unchanged.

**Runtime (must be executed on Railway/local Docker):**
- ⏳ (1) PostGIS verified via `SELECT postgis_version()` (`python -m app.cli check`).
- ⏳ (2) STAC API returns seeded collection `sentinel-2-l2a`.
- ⏳ (3) MinIO bucket reachable from ingestion/api containers (`python worker.py verify`).

**Scope guardrails upheld:**
- ✅ No raster/index math, no tile rendering, no `/api/indices/statistics`, no product BFF contracts, no frontend changes, no Wave 2 automation.
- ✅ Raw uint16 DN convention preserved; no pre-stretching.