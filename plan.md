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

> **Slice 1 context:** Slice 1 (Storage/Catalog) is complete as artifact-generation + static validation (runtime checks deferred to Railway).
>
> **Slice 2 context:** Slice 2 (Raster de-risk) is also complete as code/artifacts + static/synthetic validation (runtime checks involving real COGs/MinIO/TiTiler deferred to Railway/local Docker).

---

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
  - Skeleton endpoints + `_skeleton` contracts.
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
  - CRA “Service Skeleton Status Dashboard” implemented and left as-is for subsequent slices.

Conclude Phase 2 (COMPLETED):
- ✅ Ran `scripts/validate_slice0.py` (PASSED 94/0).
- ✅ Ran unit tests for api skeleton.
- ✅ Confirmed live endpoints and dashboard rendering.
- ✅ `scripts/smoke-test.py` exists for Slice 0 and later evolved for Slice 2.

**Emergent ingress note (for test planning):** In the Emergent preview, externally reachable health is `GET /api/health` (ingress routes `/api/*`). `GET /health` is a Railway/container health path intended for the `api` service itself and may not be reachable on the preview URL.

---

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
     - checks MinIO bucket is reachable and deterministic keys exist

### Slice 2 next actions (Raster de-risk — runtime checks deferred to Railway/local Docker)

Even though Slice 2 code/artifacts are complete and **statically + synthetically validated** (no Docker in Emergent), the following runtime checks must be executed on Railway/local Docker to satisfy Phase 2 exit criteria:

1. Upload **real (non-empty)** COGs to MinIO:
   - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/analytic.tif`
   - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/scl.tif`
   - (COG prep runbook: `docs/sentinel-2-l2a-cog-prep-runbook.md`)
2. Verify real COG presence (not Slice 1 placeholders):
   - `python services/ingestion/worker.py verify-cogs`
3. Render one real RGB tile (gateway/BFF→TiTiler proxy):
   - `GET /api/tiles/sentinel-2-l2a/2025-09-14/rgb/12/2937/1881.png` returns PNG.
4. Compute one real masked NDVI statistic and compare to QGIS/notebook reference:
   - `POST /api/indices/statistics` with `data/seed/phase2-ndvi-sample-polygon.geojson`.

---

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
  - Dashboard renders and shows topology/health/pinned images/repo tree/scope/roadmap/env matrix.
- ✅ No out-of-scope endpoints/features are implemented **for Slice 0**.

---

# Slice 1 Plan (Storage / Catalog) — Akasha Railway MVP (UPDATED)

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
  - Reflectance convention: raw uint16 DN; `scale=0.0001`, `offset=-0.1`
  - SCL: uint8 categorical with classes `0..11`; default excluded classes `0,1,2,3,7,8,9,10,11`
  - Required extensions: `eo`, `raster`, `projection`, `classification`
- Keep secrets safe:
  - `.env.example` placeholders only
  - No default credentials
  - Only `web` is public

**Status (now):** Slice 1 deliverables are implemented and statically validated in Emergent. Runtime exit criteria remain deferred to Railway/local Docker.

## 2) Implementation Steps

### Phase 1 — App schema (plots) owned by `api` (DONE)

- ✅ `apps/api/migrations/001_app_schema.sql` (idempotent) creating:
  - `akasha.plots`, `akasha.index_requests`, `akasha.app_settings`.
- ✅ `apps/api/app/{db.py,cli.py}` with lazy psycopg import:
  - `python -m app.cli migrate`
  - `python -m app.cli check`.

### Phase 2 — Catalog (pgSTAC) + seed STAC collection/item (DONE)

- ✅ `services/ingestion/akasha_ingest/catalog.py` (pypgstac migrate + upsert loaders).
- ✅ Seed STAC JSON:
  - `data/seed/stac/sentinel-2-l2a-collection.json`
  - `data/seed/stac/sentinel-2-l2a-sample-item.json` (updated in Slice 2 to real 2025-09-14/43PHP scene).

### Phase 3 — Object storage (MinIO) deterministic bucket/key layout (DONE)

- ✅ `services/ingestion/akasha_ingest/storage.py`:
  - `ensure_bucket()`
  - `seed_keys()` uploads local rasters if present else placeholder objects
  - `bucket_reachable(required_keys=...)` verifies deterministic keys exist.

### Phase 4 — Idempotent seeding orchestration + exit-criteria verifier (DONE)

- ✅ `services/ingestion/akasha_ingest/scene.py` (`SceneIdentity`, deterministic keys).
- ✅ `services/ingestion/akasha_ingest/seed.py` orchestration.
- ✅ `services/ingestion/akasha_ingest/verify.py` runtime checks.
- ✅ Worker CLI supports: migrate-catalog, seed-stac, seed-minio, seed, verify.

### Phase 5 — Wiring, Railway/Compose alignment, and static validation (DONE)

- ✅ Updated docker-compose wiring + `.env.example` placeholders.
- ✅ Added `scripts/validate_slice1.py` and kept `scripts/validate_slice0.py` green.

## 3) Next Actions

Runtime validation deferred to Railway/local Docker:

1. `python -m app.cli migrate`
2. `python worker.py seed`
3. `python worker.py verify`

## 4) Success Criteria (Slice 1 exit)

**Artifacts (done in Emergent):**
- ✅ App schema migration exists + is idempotent.
- ✅ pgSTAC migration + STAC seed tooling exists (idempotent upsert).
- ✅ STAC seed conforms to frozen band order and reflectance conventions.
- ✅ MinIO bucket/key layout + placeholders implemented.
- ✅ `validate_slice0.py` and `validate_slice1.py` pass.

**Runtime (must be executed on Railway/local Docker):**
- ⏳ PostGIS verified.
- ⏳ STAC API returns collection.
- ⏳ MinIO reachable and deterministic keys exist.

---

# Slice 2 Plan (Phase 2 — Raster de-risk milestone) — Akasha Railway MVP (UPDATED)

## 1) Objectives

Implement **Phase 2 — Raster de-risk milestone** only (per `docs/prompts/phase-2-raster-de-risk-emergent-prompt.md`).

Primary deliverables:
1. Update the seed scene identity and STAC sample item to match the real generated scene **2025‑09‑14 / 43PHP / processing baseline 05.11**.
2. Add the minimal BFF APIs needed to:
   - expose config/source/date/layer metadata
   - proxy a same-origin RGB tile request to TiTiler
   - compute SCL-masked, offset/scale-corrected index statistics **in the BFF** (not TiTiler statistics)
3. Add a **repeatable validation path**:
   - keep Slice 0/1 validators green
   - add a Slice 2 validator that is meaningful in Emergent **without** real COGs

**Important constraint (current environment):**
- In Emergent, the real COG rasters are **missing** (git-ignored, ~2.24 GiB) and Docker services (MinIO/TiTiler) are unavailable.
- Therefore runtime validation of “real RGB tile PNG” and “real masked NDVI for the real scene” is **BLOCKED** here.
- The BFF explicitly returns a clean `503 RASTER_BACKEND_UNAVAILABLE` when the raster backend is absent.

**Status (now):** Slice 2 deliverables are complete and verified:
- `validate_slice0.py` **94/0**
- `validate_slice1.py` **67/0** (updated for the real scene)
- `validate_slice2.py` **76/0** (includes synthetic dual-COG E2E proof)
- `pytest` **24/24**
- smoke-test **8 passed / 0 failed / 2 blocked** (tile/stat blocked as expected)
- `testing_agent_v3`: backend **13/13** (100%), no bugs; expected 503s confirmed.

Out of scope (unchanged):
- Full frontend map UX/auth/custom domains
- Plot CRUD UX (later slice)
- Wave 2 automation
- Production hardening

## 2) Implementation Steps

> Pre-step: re-run `python scripts/validate_slice0.py` and `python scripts/validate_slice1.py` and fix any regressions before proceeding.

### Phase A — Scene/catalog metadata alignment (2025-09-14 real scene) (DONE)

- ✅ Updated `services/ingestion/akasha_ingest/scene.py`:
  - `mgrs_tile="43PHP"`
  - `acquisition_datetime="2025-09-14T05:06:49.024000Z"`
  - `processing_baseline="05.11"`
- ✅ Updated `data/seed/stac/sentinel-2-l2a-sample-item.json` to the real scene:
  - id: `sentinel-2-l2a_43PHP_20250914_0511`
  - bbox/geometry footprint polygon
  - properties: platform `sentinel-2b`, `eo:cloud_cover=17.153746`, full `proj:*`
  - assets: `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/{analytic,scl}.tif`
  - frozen analytic band order `[B04,B08,B05,B06,B07,B11,B12,B03,B02]`
- ✅ Updated `data/seed/stac/sentinel-2-l2a-collection.json` extent to contain the real scene bbox.
- ✅ Updated `data/seed/README.md` deterministic scene section.
- ✅ Updated `scripts/validate_slice1.py` expected constants so it stays green.

Exit:
- ✅ `python scripts/validate_slice1.py` passes (**67/0**).

### Phase B — BFF raster/stat core modules (backend-only; testable) (DONE)

- ✅ Added `apps/api/app/raster/` package implementing:
  - `indices.py`: supported indices registry (NDVI/NDRE/NDMI/NDWI_GREEN_NIR), band-name→position mapping, RGB positions `[1,8,9]`.
  - `statistics_core.py`: **pure numpy** masked statistics engine (offset/scale + SCL mask + pixel accounting + min/max/mean/stddev).
  - `catalog_resolver.py`: STAC API resolution (when configured) + seed JSON fallback.
  - `raster_reader.py`: lazy rasterio dual-COG window read + geometry mask + GDAL/S3 env.
  - `geo_validate.py`: lazy shapely/pyproj geometry validation + geodesic area guardrail.
  - `tiles.py`: TiTiler RGB tile URL builder + server-side fetch.
  - `errors.py`: standard Akasha error shape + exception handler.
  - `models.py`: Pydantic request/response models.
  - `service.py`: orchestration glue.

Constraints satisfied:
- ✅ All heavy deps are lazily imported so importing the FastAPI app stays safe.

Exit:
- ✅ Unit tests + `validate_slice2.py` prove offset/scale correctness and mask/pixel accounting.

### Phase C — Minimal Phase 2 BFF endpoints/contracts (DONE)

- ✅ Implemented endpoints (router `apps/api/app/product.py` + wired into `main.py`):
  - `GET /api/config`
  - `GET /api/sources`
  - `GET /api/sources/{sourceId}/dates`
  - `GET /api/layers/default`
  - `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png` (BFF→TiTiler proxy)
  - `POST /api/indices/statistics` (masked index statistics)
- ✅ Design decision preserved: tile route is under `/api/tiles/...` (Emergent ingress compatibility).
- ✅ Standard error response shape enforced globally:
  - `{ "error": {"code": "...", "message": "...", "details": {...}} }`.

Exit:
- ✅ Live preview verified for config/sources/dates/layers, and the tile/stat routes return clean 503 when the raster backend is absent.

### Phase D — Dependencies + infra wiring (Docker/Compose/Railway artifacts) (DONE)

- ✅ Updated `apps/api/requirements.txt` with pinned raster deps:
  - `rasterio`, `rio-tiler`, `shapely`, `pyproj`, `numpy`.
- ✅ Updated `apps/api/Dockerfile` with `libexpat1` runtime lib.
- ✅ Updated `infra/docker/docker-compose.yml`:
  - TiTiler `PORT=8000`
  - `api` has AWS/GDAL env so rasterio can read MinIO
  - `AKASHA_RGB_RESCALE` exposed to api.
- ✅ Updated env docs/examples:
  - `apps/api/.env.example`
  - `infra/railway/ENV_MATRIX.md`
  - `apps/api/app/skeleton.py` env matrix
  - ROADMAP advanced: slice0+slice1 done, slice2 active.

Exit:
- ✅ `validate_slice0.py` remains green.

### Phase E — Storage seeding quality: distinguish real COGs vs placeholders (DONE)

- ✅ Enhanced `services/ingestion/akasha_ingest/storage.py`:
  - real uploads tagged (`akasha-placeholder=false`)
  - placeholders explicitly tagged and detected.
  - `verify_real_cogs()` asserts objects exist and are non-empty + not placeholders.
- ✅ Enhanced `services/ingestion/akasha_ingest/verify.py`:
  - `run_phase2()` includes non-empty real COG checks.
- ✅ Worker CLI:
  - `python worker.py verify-cogs`.

Exit:
- ✅ Static validation in `validate_slice2.py` confirms these symbols + CLI command exist.

### Phase F — Fixtures + tests + validation scripts (DONE)

- ✅ Added in-footprint polygon fixture:
  - `data/seed/phase2-ndvi-sample-polygon.geojson`.
- ✅ Added pytest suite:
  - `apps/api/tests/test_slice2.py` (18 tests)
  - Full test suite: **24/24**.
- ✅ Added `scripts/validate_slice2.py`:
  - static checks + pure numpy NDVI reference
  - in-process TestClient contract checks
  - synthetic dual-COG rasterio E2E (when rasterio is available)
  - BLOCKED runtime checklist.
- ✅ Extended `scripts/smoke-test.py`:
  - Phase 2 product endpoints must pass
  - tile/stat are treated as BLOCKED (not failure) when 502/503.

Exit:
- ✅ `validate_slice0.py` **94/0**, `validate_slice1.py` **67/0**, `validate_slice2.py` **76/0**.
- ✅ smoke-test: **8/0 + 2 blocked**.
- ✅ `testing_agent_v3`: **13/13** backend.

### Phase G — Documentation updates (DONE)

- ✅ Updated `docs/emergent-context.md` with Phase 2 handoff and blocked criteria.
- ✅ Updated `docs/mvp-execution-plan.md` Phase 2 status block.
- ✅ Updated `scripts/README.md` with `validate_slice2.py` + smoke behavior.
- ✅ Updated `apps/api/README.md` to document Slice 2 endpoints.
- ✅ Updated `data/seed/README.md` deterministic scene section.

## 3) Next Actions (for operator / Railway or local Docker)

Once real COGs are uploaded to MinIO:

1. Build images:
   - `docker compose -f infra/docker/docker-compose.yml build ingestion-worker api`
2. Start services:
   - `docker compose -f infra/docker/docker-compose.yml up -d postgis minio stac-api titiler api web`
3. Apply app schema:
   - `docker compose -f infra/docker/docker-compose.yml run --rm api python -m app.cli migrate`
4. Seed STAC + ensure MinIO keys exist:
   - `docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py seed --force`
5. Verify storage/catalog (Slice 1):
   - `docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify`
6. Verify Phase 2 real COG presence:
   - `docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify-cogs`
7. Prove Phase 2 end-to-end:
   - `python scripts/smoke-test.py http://localhost:8080` (or Railway URL)
   - Confirm real RGB tile returns PNG
   - Confirm `POST /api/indices/statistics` returns JSON
   - Compare NDVI against QGIS/notebook reference for `data/seed/phase2-ndvi-sample-polygon.geojson`.

## 4) Success Criteria (Slice 2 exit)

**Artifacts + static/synthetic validation (must pass in Emergent):**
- ✅ Real scene identity + STAC item updated to 2025-09-14/43PHP/05.11.
- ✅ Deterministic keys match `sentinel-2-l2a/2025-09-14/{analytic,scl}.tif`.
- ✅ Slice 0 and Slice 1 validators remain green.
- ✅ `validate_slice2.py` exists and passes (static + synthetic NDVI de-risk).
- ✅ New endpoints exist with stable response shapes.
- ✅ Heavy deps are lazily imported so the live preview stays healthy.
- ✅ No secrets or large rasters are committed.

**Runtime (Railway/local Docker; blocked in Emergent due to missing real COGs):**
- ⏳ `worker.py verify-cogs` passes (non-empty real COG objects in MinIO).
- ⏳ STAC API returns the updated real STAC item with correct assets.
- ⏳ One RGB tile returns a PNG through the gateway/BFF→TiTiler path.
- ⏳ `POST /api/indices/statistics` returns cloud/SCL-masked NDVI JSON for an in-footprint polygon.
- ⏳ NDVI result compared against a QGIS/notebook reference for the same polygon.
