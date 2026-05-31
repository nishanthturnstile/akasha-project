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
  - CRA “Service Skeleton Status Dashboard” implemented and left as-is for subsequent slices.

Conclude Phase 2 (COMPLETED):
- ✅ Ran `scripts/validate_slice0.py` (PASSED 94/0).
- ✅ Ran unit tests for api skeleton.
- ✅ Confirmed live endpoints and dashboard rendering.
- ✅ `scripts/smoke-test.py` includes Slice 0 checks and lists future checks as SKIPPED.

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
- ✅ No out-of-scope endpoints/features are implemented (no `/api/config`, no raster/index logic, no map UX) **for Slice 0**.

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

**Status (now):** Slice 1 deliverables are implemented and statically validated in Emergent. The runtime exit criteria are deferred to Railway/local Docker.

## 2) Implementation Steps

### Phase 1 — App schema (plots) owned by `api`

Steps (COMPLETED):
- ✅ Added `apps/api/migrations/001_app_schema.sql` (idempotent) creating:
  - `akasha.plots`, `akasha.index_requests`, `akasha.app_settings`.
- ✅ Added `apps/api/app/{db.py,cli.py}` with lazy psycopg import:
  - `python -m app.cli migrate`
  - `python -m app.cli check` (SELECT postgis_version + table presence + API→MinIO liveness).

### Phase 2 — Catalog (pgSTAC) + seed STAC collection/item

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/catalog.py` (pypgstac migrate + upsert loaders).
- ✅ Added seed STAC JSON:
  - `data/seed/stac/sentinel-2-l2a-collection.json`
  - `data/seed/stac/sentinel-2-l2a-sample-item.json`

### Phase 3 — Object storage (MinIO) deterministic bucket/key layout

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/storage.py`:
  - `ensure_bucket()`
  - `seed_keys()` uploads local rasters if present else placeholder objects
  - `bucket_reachable(required_keys=...)` verifies deterministic keys exist.

### Phase 4 — Idempotent seeding orchestration + exit-criteria verifier

Steps (COMPLETED):
- ✅ Added `services/ingestion/akasha_ingest/scene.py` (`SceneIdentity`, deterministic keys).
- ✅ Added `services/ingestion/akasha_ingest/seed.py` orchestration.
- ✅ Added `services/ingestion/akasha_ingest/verify.py` runtime checks.
- ✅ Worker CLI supports: migrate-catalog, seed-stac, seed-minio, seed, verify.

### Phase 5 — Wiring, Railway/Compose alignment, and static validation

Steps (COMPLETED):
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

# Slice 2 Plan (Phase 2 — Raster de-risk milestone) — Akasha Railway MVP (NEW)

## 1) Objectives

Implement **Phase 2 — Raster de-risk milestone** only (per `docs/prompts/phase-2-raster-de-risk-emergent-prompt.md`).

Primary deliverables:
1. Update the seed scene identity and STAC sample item to match the real generated scene **2025‑09‑14 / 43PHP / processing baseline 05.11**.
2. Add the minimal BFF APIs needed to:
   - expose config/source/date/layer metadata for smoke tests
   - proxy a same-origin RGB tile request to TiTiler
   - compute SCL-masked, offset/scale-corrected NDVI statistics **in the BFF** (not TiTiler statistics)
3. Add a **repeatable validation path**:
   - keep Slice 0/1 validators green
   - add a Slice 2 validator that is meaningful in Emergent **without** real COGs

**Important constraint (current environment):**
- In Emergent, the real COG rasters (`data/seed/rasters/2025-09-14/*.tif`) are **missing** (git-ignored, ~2.24 GiB). Raster libs are not preinstalled.
- Therefore, **runtime** validation of:
  - “one RGB tile returns a PNG through TiTiler” and
  - “one real masked NDVI statistic for the real scene”

  is **BLOCKED** in Emergent and must be done on Railway/local Docker after an operator uploads real COGs to MinIO.

**What Slice 2 will still deliver in Emergent:**
- All code, metadata, and infra artifacts.
- Static validation + **synthetic raster fixtures** to de-risk math correctness and endpoint behavior, without fabricating the real scene’s COGs and without committing large rasters.

Out of scope (unchanged):
- Full frontend map UX/auth/custom domains/future sources
- Wave 2 automation
- Production hardening

## 2) Implementation Steps

> Pre-step: re-run `python scripts/validate_slice0.py` and `python scripts/validate_slice1.py` and fix any regressions before proceeding.

### Phase A — Scene/catalog metadata alignment (2025-09-14 real scene)

User stories:
1. As an operator, I want the seed STAC item + deterministic keys to match the real prepared COG scene.
2. As a developer, I want existing validators to remain correct and keep passing after the seed scene changes.

Steps:
- Update `services/ingestion/akasha_ingest/scene.py`:
  - `mgrs_tile="43PHP"`
  - `acquisition_datetime="2025-09-14T05:06:49.024000Z"`
  - `processing_baseline="05.11"`
- Update `data/seed/stac/sentinel-2-l2a-sample-item.json` to match the prepared rasters:
  - id: `sentinel-2-l2a_43PHP_20250914_0511`
  - bbox/geometry footprint polygon from the prompt
  - properties: platform `sentinel-2b`, `eo:cloud_cover=17.153746`, proj fields (`epsg`, `shape`, `transform`, `proj:bbox`)
  - assets: `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/{analytic,scl}.tif`
  - maintain frozen analytic band order `[B04,B08,B05,B06,B07,B11,B12,B03,B02]`
- Update `data/seed/README.md` deterministic scene section to the new scene.
- Update `scripts/validate_slice1.py` expected constants (scene_key/item_id/keys) so it remains green.
- Optionally update `data/seed/stac/sentinel-2-l2a-collection.json` extent bbox to reflect the new footprint if appropriate (while preserving the Bangalore AOI concept).

Exit (static):
- `python scripts/validate_slice1.py` passes.

### Phase B — BFF raster/stat core modules (backend-only; testable)

User stories:
1. As a developer, I want a pure-numpy, unit-testable masked-statistics engine.
2. As a developer, I want the raster I/O layer to be isolated and lazily imported so the live preview never crashes.

Steps:
- Add an `apps/api/app/raster/` package (or similar) implementing:
  - `indices.py`: supported indices registry (`NDVI`, `NDRE`, `NDMI`, `NDWI_GREEN_NIR`), formulas, and band-name→position mapping using STAC `eo:bands`.
  - `statistics_core.py`: **pure numpy** computation:
    - apply nodata/out-of-coverage
    - apply SCL exclusion classes `0,1,2,3,7,8,9,10,11`
    - apply reflectance correction `ref = dn * 0.0001 - 0.1`
    - compute index (at minimum NDVI; others supported if low effort)
    - compute `min/max/mean/stddev` on valid pixels
    - compute pixel-accounting + percentages:
      - `totalPixels, nodataPixels, coveragePixels, sclExcludedPixels, validPixels`
      - `validPixelPercent, cloudMaskedPercent, coveragePercent`
  - `catalog_resolver.py`:
    - resolve analytic/scl asset hrefs for a given source/date
    - prefer STAC API call; fallback to local seed JSON in `data/seed/stac` (for offline/static testing)
  - `raster_reader.py` (lazy imports):
    - rasterio-based window read for analytic + SCL for a geometry
    - build geometry mask using `rasterio.features.geometry_mask`
    - support `s3://` hrefs via GDAL/AWS env (server-side)
  - `geo_validate.py` (lazy imports):
    - validate GeoJSON Polygon
    - enforce max area (ha) if possible
    - enforce max vertices
  - `errors.py`: standard error response shape `{ "error": {code,message,details} }` and consistent HTTPException raising.

Constraints:
- All heavy deps (`rasterio`, `rio-tiler`, `shapely`, `pyproj`) must be **lazy-imported** to avoid breaking the Emergent live preview process.

Exit (static/synthetic):
- Unit tests for `statistics_core.py` validate offset/scale correctness + SCL masking using synthetic arrays.

### Phase C — Minimal Phase 2 BFF endpoints/contracts

User stories:
1. As an operator, I want minimal BFF endpoints so smoke tests can be added.
2. As a developer, I want a same-origin tile URL template that does not expose MinIO credentials or raw asset URLs to the browser.

Steps:
- Implement endpoints in `apps/api/app/main.py` (or a new router module) with minimal contracts from `docs/architecture-tech-stack.md`:
  - `GET /api/config`
  - `GET /api/sources`
  - `GET /api/sources/{sourceId}/dates`
  - `GET /api/layers/default`
  - `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png`
    - BFF → TiTiler proxy, server-side
    - builds TiTiler request using analytic URL + RGB bidx `[1,8,9]` and a reasonable rescale
    - streams PNG back to client
  - `POST /api/indices/statistics`
    - accepts GeoJSON geometry + sourceId + acquisitionDate + indexType
    - resolves assets, reads analytic/SCL windows, applies correction + mask, returns normalized JSON

Design decision (Emergent/public preview compatibility):
- Tile route is under `/api/tiles/...` rather than `/tiles/...` because Emergent ingress only routes `/api/*` to the backend; non-`/api` paths go to the frontend.
- `GET /api/layers/default` returns a `tileUrlTemplate` pointing at `/api/tiles/...`.

Exit criteria (static/synthetic):
- FastAPI TestClient tests confirm endpoints exist and response shapes are stable.

### Phase D — Dependencies + infra wiring (Docker/Compose/Railway artifacts)

User stories:
1. As a developer, I want the api container to have raster dependencies for real runtime on Railway/local Docker.
2. As an operator, I want TiTiler to bind correctly to port 8000 and read MinIO using S3-compatible GDAL env.

Steps:
- Update `apps/api/requirements.txt` with pinned raster/HTTP deps (keeping imports lazy):
  - `rasterio`, `rio-tiler`, `shapely`, `pyproj`, `httpx` or `requests`
- Update `apps/api/Dockerfile` to install required OS libs for rasterio wheels as needed (e.g., `libexpat1`).
- Update `infra/docker/docker-compose.yml`:
  - ensure TiTiler has `PORT=8000`
  - wire api with `S3_ENDPOINT_URL` + AWS/GDAL env needed for rasterio/GDAL to read MinIO
- Update `.env.example` files:
  - `apps/api/.env.example` (server-side S3/GDAL vars)
  - `services/titiler/.env.example` (explicit `PORT=8000` + GDAL S3 vars)
- Update `infra/railway/ENV_MATRIX.md` and `apps/api/app/skeleton.py` env matrix if new vars are required.
- Update healthcheck path assumptions remain correct:
  - STAC API health path `/_mgmt/ping`
  - TiTiler health `/healthz`

Exit criteria (static):
- `python scripts/validate_slice0.py` passes (no infra regressions).

### Phase E — Storage seeding quality: distinguish real COGs vs placeholders

User stories:
1. As an operator, I want Phase 2 verification to fail if COG objects are still empty placeholders.

Steps:
- Enhance `services/ingestion/akasha_ingest/storage.py` and/or `verify.py` to:
  - detect placeholder metadata (`akasha-placeholder=true`) and/or `ContentLength==0`
  - add a Phase 2 check function that asserts `ContentLength > 0` for analytic + SCL keys
  - improve logging so uploads are clearly “real COG uploaded” vs “placeholder created”.

Exit criteria:
- Static unit tests validate placeholder detection logic.

### Phase F — Fixtures + tests + validation scripts

User stories:
1. As a developer, I want a `validate_slice2.py` that verifies contracts without Docker.
2. As an operator, I want a smoke path that can be run on Railway/local Docker to fully prove Phase 2 once COGs are present.

Steps:
- Add a new fixture polygon file (in-footprint for 2025-09-14) for Phase 2 smoke:
  - `data/seed/infootprint-2025-09-14-polygon.geojson` (or similar)
  - keep existing `sample-plot.geojson` (used later for plot UX) unchanged.
- Add `apps/api/tests/test_slice2_statistics_core.py` (or similar) covering:
  - offset/scale effect does not cancel
  - SCL class exclusions
  - pixel accounting
  - deterministic numeric reference NDVI for synthetic arrays
- Add `scripts/validate_slice2.py`:
  - static checks: required files exist, endpoints registered, requirements pinned
  - synthetic check: create small synthetic arrays and run `statistics_core` end-to-end
  - optional: FastAPI TestClient checks endpoint response shape
  - report which runtime checks are blocked by missing real COGs.
- Extend `scripts/smoke-test.py`:
  - implement Phase 2 checks when running against a real stack:
    - `/api/config`, `/api/sources`, `/api/sources/{id}/dates`, `/api/layers/default`
    - fetch one PNG tile (via `/api/tiles/...`)
    - `POST /api/indices/statistics`
  - In Emergent, leave these as SKIPPED or “BLOCKED” depending on environment.

Exit criteria (Emergent):
- `python scripts/validate_slice0.py` passes.
- `python scripts/validate_slice1.py` passes.
- `python scripts/validate_slice2.py` passes (static + synthetic).
- `pytest` for new tests passes.

### Phase G — Documentation updates

Steps:
- Update `docs/emergent-context.md` handoff notes for Slice 2 (including the “blocked in Emergent” rationale).
- Update `docs/mvp-execution-plan.md` Phase 2 notes (status + how to verify on Railway).
- Update `data/seed/README.md` to reflect new deterministic scene/date and clarify placeholder vs real COGs.
- Update `scripts/README.md` with new `validate_slice2.py` and smoke instructions.

## 3) Next Actions (for operator / Railway or local Docker)

Once real COGs are available in `data/seed/rasters/2025-09-14/` (local dev) or uploaded to Railway MinIO:

1. Build images:
   - `docker compose -f infra/docker/docker-compose.yml build ingestion-worker api`
2. Start services:
   - `docker compose -f infra/docker/docker-compose.yml up -d postgis minio stac-api titiler api web`
3. Apply app schema:
   - `docker compose -f infra/docker/docker-compose.yml run --rm api python -m app.cli migrate`
4. Seed STAC + upload **real** COGs:
   - `docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py seed --force`
5. Verify storage/catalog:
   - `docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify`
6. Verify Phase 2 (new smoke path):
   - `python scripts/smoke-test.py http://localhost:8080` (or `WEB_PORT=18080`)

## 4) Success Criteria (Slice 2 exit)

**Artifacts + static/synthetic validation (must pass in Emergent):**
- ✅ `SAMPLE_SCENE` and seed STAC item updated to 2025-09-14/43PHP/05.11.
- ✅ Deterministic keys updated to `sentinel-2-l2a/2025-09-14/{analytic,scl}.tif`.
- ✅ Slice 0 and Slice 1 validators remain green.
- ✅ Slice 2 validator exists and passes (static + synthetic math verification).
- ✅ New endpoints exist with stable response shapes; heavy deps are lazily imported so the live preview stays healthy.
- ✅ No secrets or large rasters are committed.

**Runtime (Railway/local Docker; blocked in Emergent due to missing real COGs):**
- ⏳ `worker.py seed --force` uploads **non-empty** real COG objects to MinIO at deterministic keys (ContentLength > 0).
- ⏳ STAC API returns the updated real STAC item with correct assets.
- ⏳ One RGB tile returns a PNG through the gateway/TiTiler path.
- ⏳ `POST /api/indices/statistics` returns cloud/SCL-masked NDVI JSON for an in-footprint polygon.
- ⏳ NDVI result compared against a QGIS/notebook reference for the same polygon.
