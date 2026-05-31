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

**Status (now):** All Slice 0 deliverables are implemented and validated, including formal E2E validation via `testing_agent_v3` and a smoke test compatible with edge/CDN filters.

> **Slice 1 context:** Slice 1 (Storage/Catalog) is complete as artifact-generation + static validation (runtime checks deferred to Railway).
>
> **Slice 2 context:** Slice 2 (Raster de-risk) is complete as code/artifacts + static/synthetic validation (runtime checks involving real COGs/MinIO/TiTiler deferred to Railway/local Docker).
>
> **Slice 3 context:** Slice 3 (BFF API implementation) is **next**. Phase 2 already delivered config/sources/dates/layers/tiles/statistics + standard error shape + polygon validation. Slice 3 adds **only Plot CRUD + GeoJSON import/export**.

---

## 2) Implementation Steps

### Phase 1 — Core POC (Isolated): “Skeleton Integrity + Health Contract”

Core workflow (Slice 0): generate the full multi-service skeleton artifacts and prove their health contracts + Railway readiness without running Docker.

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
  - Uses FastAPI lifespan handler (no deprecated `on_event`).
- ✅ Added `scripts/validate_slice0.py`:
  - Parses `infra/docker/docker-compose.yml`
  - Verifies required services exist and only `web` publishes host ports
  - Verifies healthchecks + persistent volumes for `postgis`/`minio`
  - Verifies pinned image tags + pinned base images in Dockerfiles
  - Verifies Railway healthcheck paths in `railway.json` files
  - Ensures `.env.example` values for secret-like vars are placeholders
- ✅ Ran POC checks in Emergent:
  - `scripts/validate_slice0.py` PASSED (94/0)
  - `apps/api` unit tests passed

### Phase 2 — V1 App Development (Slice 0 deliverables)

User stories:
1. As an operator, I want a single public `web` service that serves the frontend and proxies `/api/*` and `/tiles/*` same-origin.
2. As a developer, I want `docker-compose up` (outside Emergent) to bring up web/api/titiler/stac/postgis/minio/ingestion with correct networking.
3. As a developer, I want each internal service to have a documented health endpoint and Railway healthcheck path.
4. As a developer, I want a Vite+TS `apps/frontend` skeleton that can be built into the `web` gateway container.
5. As a developer, I want the live Emergent dashboard to clearly show service status, required env vars, and what’s intentionally out of scope.

Steps (COMPLETED):
- ✅ Web gateway (Railway public only) via Caddy (`/health`, `/api/*`, `/tiles/*`, SPA fallback)
- ✅ `apps/frontend` Vite skeleton (Railway-deployable target)
- ✅ `apps/api` skeleton with health + `_skeleton` endpoints
- ✅ `services/titiler`, `services/stac-api` wrapper configs
- ✅ `services/ingestion` worker skeleton + CLI
- ✅ `postgis` + `minio` docker-compose layout + pinned images + volumes
- ✅ `infra/docker` + `infra/railway` deployment artifacts
- ✅ Shared formatting/linting conventions
- ✅ Live Emergent preview wiring (FastAPI + React Service Dashboard)

Conclude Phase 2 (COMPLETED):
- ✅ `scripts/validate_slice0.py` passes
- ✅ Dashboard works; skeleton endpoints stable

**Emergent ingress note (for test planning):** In the Emergent preview, externally reachable health is `GET /api/health` (ingress routes `/api/*`). `GET /health` is a Railway/container health path intended for the `api` service itself.

---

## 3) Next Actions

### Slice 0 next actions (DONE)

1. ✅ Ran formal E2E testing via `testing_agent_v3`.
2. ✅ Confirmed smoke test behavior against the live preview base URL.
3. ✅ Push to GitHub and deploy on Railway for runtime validation.

### Slice 1 next actions (Storage/Catalog — runtime checks deferred to Railway)

Even though Slice 1 artifacts are complete, runtime exit criteria must be executed on Railway/local Docker:

1. Apply api-owned app schema:
   - `python -m app.cli migrate`
   - `python -m app.cli check`
2. Seed catalog + storage:
   - `python worker.py seed`
3. Verify Slice 1:
   - `python worker.py verify`

### Slice 2 next actions (Raster de-risk — runtime checks deferred to Railway/local Docker)

Even though Slice 2 code/artifacts are complete and statically + synthetically validated, runtime exit criteria must be executed on Railway/local Docker:

1. Upload real (non-empty) COGs to MinIO:
   - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/analytic.tif`
   - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/scl.tif`
2. Verify real COG presence:
   - `python services/ingestion/worker.py verify-cogs`
3. Render one real RGB tile:
   - `GET /api/tiles/sentinel-2-l2a/2025-09-14/rgb/12/2937/1881.png`
4. Compute one real masked NDVI statistic and compare to QGIS/notebook reference:
   - `POST /api/indices/statistics` with `data/seed/phase2-ndvi-sample-polygon.geojson`

### Slice 3 next actions (Phase 3 — BFF API implementation)

Proceed with Slice 3 only after confirming Slice 0/1/2 validation remains green.

---

## 4) Success Criteria (Slice 0 exit)

- ✅ Repo structure matches docs
- ✅ Required Dockerfiles exist; images pinned
- ✅ docker-compose is valid and respects public/private service rules
- ✅ `.env.example` placeholders only
- ✅ Live preview `/api/health` and `_skeleton` endpoints work

---

# Slice 1 Plan (Storage / Catalog) — Akasha Railway MVP (UPDATED)

## 1) Objectives

- Stand up the data foundation (Railway-ready artifacts): PostGIS app schema, pgSTAC catalog, MinIO bucket/key layout, STAC seeds.
- Keep secrets safe; only `web` is public.

**Status (now):** Slice 1 deliverables are implemented and statically validated in Emergent. Runtime exit criteria deferred to Railway/local Docker.

## 2) Implementation Steps

### Phase 1 — App schema (plots) owned by `api` (DONE)

- ✅ `apps/api/migrations/001_app_schema.sql` creates `akasha.plots`, `akasha.index_requests`, `akasha.app_settings`.
- ✅ `apps/api/app/{db.py,cli.py}` provide lazy psycopg migration CLI.

### Phase 2 — Catalog (pgSTAC) + seed STAC collection/item (DONE)

- ✅ Ingestion worker manages pgSTAC.
- ✅ STAC seed JSON exists under `data/seed/stac/`.

### Phase 3 — Object storage (MinIO) deterministic bucket/key layout (DONE)

- ✅ MinIO bucket `akasha-cogs` + deterministic keys.

### Phase 4 — Idempotent seeding orchestration + exit-criteria verifier (DONE)

- ✅ Ingestion worker `seed` + `verify`.

### Phase 5 — Wiring and static validation (DONE)

- ✅ `scripts/validate_slice1.py` exists and passes.

## 3) Next Actions

Runtime checks on Railway/local Docker:
- `python -m app.cli migrate`
- `python worker.py seed`
- `python worker.py verify`

## 4) Success Criteria (Slice 1 exit)

Artifacts:
- ✅ Schema/migrations + seeds exist
- ✅ `validate_slice0.py` and `validate_slice1.py` pass

Runtime (Railway/local Docker):
- ⏳ PostGIS verified
- ⏳ STAC API returns collection
- ⏳ MinIO reachable and keys exist

---

# Slice 2 Plan (Phase 2 — Raster de-risk milestone) — Akasha Railway MVP (UPDATED)

## 1) Objectives

Implement Phase 2 raster proof path: BFF endpoints for config/sources/dates/layers, a BFF→TiTiler RGB tile proxy, and a BFF-computed SCL-masked, offset/scale-corrected index statistics endpoint.

**Status (now):** Slice 2 deliverables are complete and verified:
- `validate_slice0.py` 94/0
- `validate_slice1.py` 67/0
- `validate_slice2.py` 76/0
- pytest 24/24
- smoke-test passes with blocked raster steps in Emergent

Runtime exit criteria remain deferred to Railway/local Docker due to missing real COGs/MinIO/TiTiler in the Emergent environment.

## 2) Implementation Steps

All Slice 2 phases are DONE (see prior sections in this plan). No further work in Slice 2 unless integrating with later slices.

## 3) Next Actions

On Railway/local Docker only:
- Upload real COGs
- `worker.py verify-cogs`
- Verify one RGB tile and one masked NDVI statistic

## 4) Success Criteria (Slice 2 exit)

Artifacts + synthetic validation:
- ✅ endpoints exist and return stable contracts
- ✅ no secrets committed

Runtime (Railway/local Docker):
- ⏳ real RGB tile returns PNG
- ⏳ real masked NDVI stats match reference

---

# Slice 3 Plan (Phase 3 — BFF API implementation) — Akasha Railway MVP (NEW)

## 1) Objectives

Implement **Phase 3 — BFF API implementation** for the FastAPI backend, focusing **only** on:

- Plot CRUD endpoints
- GeoJSON import/export endpoints
- Database migration to support both `Polygon` and `MultiPolygon`

**Do NOT** redo or regress already completed Phase 2 endpoints:
- `GET /api/config`
- `GET /api/sources`
- `GET /api/sources/{sourceId}/dates`
- `GET /api/layers/default`
- `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png`
- `POST /api/indices/statistics`

**Constraints:**
- No Docker/PostGIS available in Emergent: Plot endpoints must return a clean **503 `PLOTS_BACKEND_UNAVAILABLE`** when DB is unreachable.
- Unit tests must not require a live DB; they must monkeypatch a persistence layer.
- Never leak `DATABASE_URL`, internal service URLs, MinIO/STAC/TiTiler URLs, credentials, raw COG paths, SQL text, or stack traces to API responses.

## 2) Implementation Steps

### Phase A — Pre-check regressions (MUST STAY GREEN)

- Re-run:
  - `python scripts/validate_slice0.py`
  - `python scripts/validate_slice1.py`
  - `python scripts/validate_slice2.py`
  - `cd apps/api && python -m pytest -q tests/test_health.py tests/test_slice2.py`

### Phase B — DB migration: allow Polygon + MultiPolygon

Create:
- `apps/api/migrations/002_plots_polygon_multipolygon.sql`

Requirements:
1. Idempotent; use `--;;` separators.
2. Preserve existing rows.
3. Keep SRID 4326.
4. Allow both POLYGON and MULTIPOLYGON.
5. Keep validity check.
6. Preserve/recreate GIST index.

Recommended approach:
- `ALTER TABLE akasha.plots ALTER COLUMN geometry TYPE geometry(Geometry, 4326) USING ST_SetSRID(geometry,4326);`
- Drop/replace constraint to enforce:
  - `GeometryType(geometry) IN ('POLYGON','MULTIPOLYGON') AND ST_IsValid(geometry)`
- Ensure `plots_geometry_gix` exists.

### Phase C — Error handling extension

- Extend `apps/api/app/raster/errors.py` with:
  - `plots_backend_unavailable()` → 503 `PLOTS_BACKEND_UNAVAILABLE`.

### Phase D — Persistence layer (raw SQL; lazy psycopg)

Create:
- `apps/api/app/plots_repo.py`

Responsibilities:
- Raw SQL only, parameter binding only (no string formatting).
- Lazy psycopg import.
- Functions:
  - `list_plots()` (newest first)
  - `get_plot(plot_id)`
  - `create_plot(name, geometry_geojson)`
  - `update_plot(plot_id, name?, geometry?)`
  - `delete_plot(plot_id)`
  - `create_plots_bulk([{name, geometry}, ...])`
- Write geometry with:
  - `ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)`
- Read geometry with:
  - `ST_AsGeoJSON(geometry)` parsed to object
- Return rows normalized to frontend contract:
  - `id`, `name`, `geometry` (dict), `areaHa`, `createdAt`, `updatedAt`.

### Phase E — Router + models: Plot CRUD + GeoJSON import/export

Create:
- `apps/api/app/plots.py`

Implementation details:
- APIRouter under `/api`.
- Use Pydantic v2 request/response models.
- Use `validate_polygon()` for geometry validation, area computation, and to enforce:
  - `settings.max_polygon_area_ha`
  - `settings.max_polygon_vertices`
- Run blocking DB calls in `anyio.to_thread.run_sync`.
- DB unavailable/unreachable → sanitized 503 via `plots_backend_unavailable()`.

Endpoints:
- `GET /api/plots` → list plots (newest first)
- `POST /api/plots` → 201, create plot
- `GET /api/plots/{plotId}` → 200 or 404
- `PATCH /api/plots/{plotId}` → update name and/or geometry; if neither provided → 400 `NO_UPDATE_FIELDS`
- `DELETE /api/plots/{plotId}` → 204 or 404
- `POST /api/plots/import/geojson` → accept FeatureCollection / Feature / raw Polygon/MultiPolygon; partial import with `imported` + `rejected` and bounded maximum feature count (e.g. 500)
- `GET /api/plots/{plotId}/export.geojson` → GeoJSON Feature, `application/geo+json`

Optional (only if simple):
- `GET /api/plots/export.geojson` → FeatureCollection

Import rules:
- Only Polygon/MultiPolygon in EPSG:4326.
- Name precedence: `properties.name` → `properties.Name` → `properties.title` → `Imported plot N`.
- Sanitize/trim names; reject blank.
- Do not echo huge payloads on reject.

### Phase F — Wire router and version bump

- Register plots router in `apps/api/app/main.py`.
- Bump `APP_VERSION` to `0.3.0-slice3` **only if** tests pass.
- Update module docstring to include Slice 3 endpoints.

### Phase G — Tests (no DB required)

Create:
- `apps/api/tests/test_slice3.py`

Test strategy:
- Monkeypatch `plots_repo` functions with an in-memory store.
- Validate API contracts + error shapes.

Required coverage (from prompt):
1. POST /api/plots returns 201 typed payload
2. GET /api/plots returns list typed payloads
3. GET /api/plots/{id} returns plot or 404 standard error
4. PATCH updates name and/or geometry
5. PATCH with no fields → 400 `NO_UPDATE_FIELDS`
6. DELETE returns 204, missing returns 404
7. invalid geometry → 422 `INVALID_GEOMETRY`
8. oversized → 413 `POLYGON_TOO_LARGE`
9. too many vertices → 400 `TOO_MANY_VERTICES`
10. import endpoint partial success: imported + rejected
11. export.geojson media type is `application/geo+json`
12. security scan: responses never contain `DATABASE_URL`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`, `MINIO`, raw COG paths, private internal service URLs, stack traces, or SQL

Also run regression tests:
- `apps/api/tests/test_health.py`
- `apps/api/tests/test_slice2.py`

### Phase H — Documentation (brief)

- Update `apps/api/README.md` to add a small Slice 3 section listing the new endpoints.

## 3) Validation Commands

From repo root:

```bash
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
```

From `apps/api`:

```bash
python -m pytest tests/test_health.py tests/test_slice2.py tests/test_slice3.py -q
```

## 4) Success Criteria (Slice 3 exit)

- Plot CRUD endpoints exist and return typed frontend-ready JSON.
- GeoJSON import/export endpoints exist and match the specified contracts.
- Invalid polygons fail with standard error shape.
- Oversized polygons fail with `POLYGON_TOO_LARGE`.
- Polygon + MultiPolygon are supported via DB migration (preferred) and validated.
- No credential/internal URL leakage in responses.
- Regression: Slice 2 endpoints unchanged; tests stay green.
- All tests pass without needing Docker/PostGIS in Emergent.

**Runtime note (preview/dev):** If `DATABASE_URL` is missing/unreachable, plot endpoints return `503 PLOTS_BACKEND_UNAVAILABLE` (sanitized).

---

# Slice 4 Plan (Phase 4 — Frontend Map & Layer UX) — Akasha Railway MVP (NEW)

## 1) Objectives

Build the first real product UI in `apps/frontend` (Vite + React 18 + TS): a MapLibre map over
Bangalore, a Sentinel-2 true-colour raster overlay driven by API tile metadata, and an
orbital-glass `LayerPanel` (source selector, date list with cloud-usability chips, visibility
toggle, opacity slider). Follow `docs/design-system.md` exactly (default **dark**, with an in-app
light/dark toggle per user request).

**Confirmed user decisions (this session):**
- Repoint the Emergent preview: `/app/frontend` (readonly supervisor runs `yarn start` on port 3000)
  must launch the Vite app from `apps/frontend` on port 3000.
- Basemap: `config.basemapStyleUrl` → `VITE_BASEMAP_STYLE_URL` → bundled **local ink fallback** style
  (no public CDN/OSM).
- Pin latest stable deps (already installed in `apps/frontend`).
- Default **dark**, toggleable to light.
- Offline behaviour OK: tiles return `503` locally (no TiTiler/MinIO) → only the ink basemap + full
  panel UX is shown locally; real imagery renders on Railway.

## 2) Implementation Steps

### Phase A — Data foundation (DONE criteria: typed, no `any` on API boundary)
- `src/types/api.ts` — AppConfig, Source, SceneDate, DefaultLayer, ApiErrorShape.
- `src/lib/api.ts` — typed same-origin client (getConfig/getSources/getDates/getDefaultLayer) +
  `ApiError` carrying `code`/`message`.
- `src/lib/queryClient.ts`, `src/lib/queries.ts` — TanStack Query client + hooks.
- `src/lib/usability.ts` — cloud-usability mapping (`>=70 success / 40–70 warning / <40 destructive /
  missing nodata`).
- `src/lib/selectDefaultDate.ts` — isLatestUsable → threshold fallback → newest.
- `src/lib/satelliteLayer.ts` — pure map-layer swap util (raster source/layer only; never setStyle).
- `src/map/basemap.ts` — style resolution + local ink fallback `StyleSpecification`.
- `src/lib/utils.ts` — `cn`.

### Phase B — UI primitives (shadcn, restyled to tokens)
- `src/components/ui/{button,card,slider,switch,tooltip,badge,scroll-area,skeleton,separator}.tsx`.

### Phase C — Map + Layer components
- `components/map/MapLayerManager.tsx` (MapLibre lifecycle; date change swaps raster only).
- `components/map/MapControls.tsx`.
- `components/layers/{LayerPanel,SourceSelector,DateList,CloudUsabilityChip,OpacitySlider,VisibilityToggle}.tsx`.
- `components/scaffold/{PlotToolbar,IndexPanel}.tsx` (disabled glass placeholders for Phase 5).
- `components/ThemeToggle.tsx`.

### Phase D — Wiring
- `pages/MapPage.tsx`, `App.tsx`, `main.tsx` (QueryClientProvider, fonts, maplibre css, default dark).
- `index.html` title; `tsconfig.json` + `vite.config.ts` (`@` alias, vitest config, allowedHosts).

### Phase E — Repoint preview
- Edit `/app/frontend/package.json` `start` → `cd /app/apps/frontend && yarn dev --host 0.0.0.0 --port 3000`.
- `supervisorctl restart frontend`; verify on preview URL.

### Phase F — Tests
- Vitest + Testing Library: cloud chip mapping, default-date selection, api error mapping,
  layer-swap-does-not-touch-basemap.

## 3) Exit Criteria
- Map centered on Bangalore; basemap via precedence rule (ink fallback offline; no public CDN).
- Latest usable scene selected by default; date change swaps only the raster layer.
- LayerPanel: source/date/cloud chip/visibility/opacity, all per design system.
- Loading/empty/error states implemented and calm.
- No hard-coded COG/MinIO/STAC/TiTiler URLs (grep clean).
- `yarn lint`, `yarn build`, `yarn test` succeed.
- Live preview serves the Vite MapPage on port 3000.

**Status (now): IN PROGRESS.**
