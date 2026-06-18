# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Akasha is a geospatial MVP that has grown into a farm-management platform: browse
ISRO ResourceSat LISS-3 FCC composites over the Bangalore 60 km Area of Interest
and compute **cloud-masked vegetation-index statistics** (NDVI/NDMI/NDWI/MSAVI)
for user-drawn plots and fields. It is a Dockerized **multi-service** application (not one
collapsed service), deployed on a self-hosted Coolify (Azure VM) and portable to local Docker
Compose / on-prem. Legacy Sentinel support remains for explicit regression or migration work, but
it is not production-selectable by default.

Development is **slice-by-slice**: Slices 0–3 (skeleton, storage/catalog, raster de-risk, BFF
product + plot contracts) are implemented; **Slice 4 is in progress**. On top of the raster core,
a farm-management product layer has been added (auth/teams, fields/seasons, field operations,
scouting, reports/risk) plus a second imagery source (ISRO Bhoonidhi / ResourceSat LISS-3).
Build only the requested slice/feature; preserve API/data contracts from earlier slices. The
slice roadmap and per-slice doc scope live in [docs/platform-plan.md](docs/platform-plan.md).

## Canonical application tree

This is the most important thing to understand before editing.

- [apps/api/](apps/api/) — FastAPI BFF (the backend, package `app`)
- [apps/frontend/](apps/frontend/) — React 18 + Vite + TypeScript SPA
- [services/ingestion/](services/ingestion/), [services/ingestion-sar/](services/ingestion-sar/), [services/titiler/](services/titiler/), [services/stac-api/](services/stac-api/), [services/minio/](services/minio/)
- [infra/gateway/](infra/gateway/) (Caddy reverse proxy), [infra/docker/](infra/docker/) (local), [infra/selfhosted/](infra/selfhosted/) (Coolify/Azure)

The old root-level Emergent preview shims (`backend/` and `frontend/`) were
removed. When asked to change backend or frontend behavior, edit
`apps/api` / `apps/frontend`.

## Commands

Run from repo root unless noted. The `Makefile` wraps the common ones (`make help`).

### Python (BFF + ingestion) — tooling configured in [pyproject.toml](pyproject.toml)
```bash
ruff check apps/api services/ingestion scripts          # lint (line-length 100, py311)
black apps/api services/ingestion && isort apps/api services/ingestion   # format

pip install -r apps/api/requirements-dev.txt             # BFF runtime + test deps (pytest, httpx)
cd apps/api && python -m pytest -q                       # BFF unit tests
cd apps/api && python -m pytest tests/test_slice2.py -q  # one test file
cd apps/api && python -m pytest tests/test_slice2.py::<name>   # one test
python -m pytest tests/ -q                               # repo-root tests (script unit tests)
```

### Frontend (canonical SPA — uses yarn@1.22.22)
```bash
cd apps/frontend
yarn install --frozen-lockfile
yarn dev          # vite dev server
yarn build        # tsc typecheck (both tsconfigs) + vite build
yarn lint         # eslint
yarn test         # vitest run
yarn test:watch
```

### Validators & smoke tests (no Docker required)
```bash
python scripts/validate_slice0.py   # skeleton artifacts (needs pyyaml)
python scripts/validate_slice1.py   # storage/catalog artifacts
python scripts/validate_slice2.py   # raster de-risk: static + synthetic NDVI pipeline (uses rasterio if installed)
python scripts/smoke-test.py http://localhost:8080   # hits a running gateway (stdlib only)
```

### Local full stack (requires Docker)
```bash
make dev         # RECOMMENDED: Docker stack + local Vite hot-reload + idempotent migrate/seed; first user signs up via /signup
make up          # docker compose -f infra/docker/docker-compose.yml up --build -d (backend/gateway only)
make down        # stop;  make reset = down -v (delete volumes);  make logs
```
See [README.md](README.md) for the full `make dev` workflow, local signup/login, and Esri basemap key setup.

### Operational CLIs (run inside the api / ingestion containers)
```bash
# api service — app schema (auth/plots/fields/seasons/ops) migrations; NOT product endpoints.
# App schema is SQLAlchemy ORM (app/models.py) managed by Alembic (apps/api/alembic).
python -m app.cli db upgrade         # apply Alembic revisions (migrate is a compat alias)
python -m app.cli db current         # show current Alembic revision
python -m app.cli check              # postgis_version() + akasha schema + MinIO liveness

# ingestion worker — catalog (pgSTAC) + object storage
python worker.py seed                # pgSTAC migrate -> load collection/item -> create MinIO bucket/keys
python worker.py ingest-manifest     # upload prepared COGs + load STAC items from prepare_manifest.json
python worker.py bhoonidhi-search    # ISRO Bhoonidhi: discover ResourceSat LISS-3 BOA products over AOI
python worker.py bhoonidhi-download   # download products from a Bhoonidhi coverage manifest
python worker.py verify              # Slice 1 exit criteria
python worker.py verify-cogs         # Phase 2: also require non-empty real COGs
python worker.py verify-manifest-cogs # verify COGs referenced by a prepare manifest
```

## Architecture

### Service topology & the one-public-service rule
```
Browser ─> web (Caddy + React SPA)  ──/api/*──> api (FastAPI BFF)
                 │                   ──/tiles/*─> titiler (rio-tiler/GDAL)
   api ─> stac-api (pgSTAC) ─> postgis (PostgreSQL + PostGIS)
   api ─> titiler ─> minio (S3-compatible COG storage)
   ingestion-worker ─> minio / stac-api / postgis / Bhoonidhi (ISRO)
```
**Only the `web` gateway is publicly reachable.** The browser calls `/api/*` and `/tiles/*` on
that same origin; the gateway proxies to internal `api`/`titiler`. `api`, `titiler`, `stac-api`,
`postgis`, `minio` never get a public domain. The frontend must never talk directly to MinIO,
PostGIS, STAC, or TiTiler, and must never hard-code COG/object URLs. This rule holds on
self-hosted Coolify ([infra/selfhosted/](infra/selfhosted/)) and local Docker alike.

### BFF (`apps/api/app`) — the core
- [main.py](apps/api/app/main.py) wires ~16 routers under `/api`, all sharing the standard error
  shape `{ "error": { code, message, details } }`:
  - **Ops/visibility:** `/health`, `/api/_skeleton/*`.
  - **Raster product (Slices 2–3):** [product.py](apps/api/app/product.py) (config/sources/dates/layers/tiles/statistics),
    [plots.py](apps/api/app/plots.py) (plot CRUD + GeoJSON import/export).
  - **Auth/account:** [auth_router.py](apps/api/app/routers/auth_router.py) (login/logout/signup/password),
    [account.py](apps/api/app/account.py) (me, API keys, notifications).
  - **Farm entities:** [fields.py](apps/api/app/fields.py), [seasons.py](apps/api/app/seasons.py),
    [field_groups.py](apps/api/app/field_groups.py), [field_analytics.py](apps/api/app/field_analytics.py),
    [field_exports.py](apps/api/app/field_exports.py).
  - **Operations layer:** [operations.py](apps/api/app/operations.py) (activity log),
    [scout_tasks.py](apps/api/app/scout_tasks.py), [data_manager.py](apps/api/app/data_manager.py),
    [reports.py](apps/api/app/reports.py), [risk.py](apps/api/app/risk.py).
  - **Staging-only:** [bhoonidhi_diagnostics.py](apps/api/app/bhoonidhi_diagnostics.py)
    (gated behind `BHOONIDHI_DIAGNOSTICS_ENABLED`).
- Heavy geospatial deps (rasterio/shapely/pyproj/rio-tiler) are **imported lazily** inside
  `app.raster.*` so importing `app.main` never requires them (keeps the Emergent preview healthy).
- [app/raster/](apps/api/app/raster/) is the masked-statistics engine, decomposed for testability:
  `service.py` orchestrates → `catalog_resolver.py` (STAC API + seed-JSON fallback + multi-source
  registry) + `geo_validate.py` (polygon area/vertex limits) + `raster_reader.py` (rasterio
  dual-COG windows, GDAL/S3) + `indices.py` (band registry, name→position) + `statistics_core.py`
  (pure-numpy math).

### Auth & app schema: SQLAlchemy ORM + Alembic (not Better Auth)
Auth is a **hand-rolled** cookie-session system (Argon2 password hashing + pepper, lockout/rate
limiting, HMAC session tokens, team RBAC roles owner/admin/member/viewer) — **not** Better Auth.
Core primitives live in [app/auth.py](apps/api/app/auth.py) / [app/auth_repo.py](apps/api/app/auth_repo.py);
local/dev can disable it with `AUTH_MODE=disabled`. See [docs/auth-team-admin-plan.md](docs/auth-team-admin-plan.md).

All app tables (`akasha` schema: users/teams/memberships/sessions/api_keys, plots, fields,
field_groups, seasons, field_seasons, field_activities, scout_tasks, attachments,
uploaded_datasets, notifications, report_templates, index_requests, app_settings) are defined as
**SQLAlchemy ORM models** in [app/models.py](apps/api/app/models.py) and migrated with **Alembic**
([apps/api/alembic/](apps/api/alembic/)) via `app.cli db upgrade`. The old raw-SQL
`apps/api/migrations/*.sql` path is legacy/empty; do not add new SQL there.

### Statistics are computed in the BFF, not TiTiler
**TiTiler serves display tiles only.** Cloud-masked index statistics are computed in the BFF
with rasterio/rio-tiler, because vanilla TiTiler `/cog/statistics` takes a single `url` and cannot
apply a categorical mask from a second mask COG. The BFF reads the analytic COG window **and** the
source-declared mask COG window for the request polygon, applies per-band scale/offset, applies the
source-specific mask, then computes stats + pixel-percentage fields.

### Catalog & storage ownership
STAC/pgSTAC owns collections, items, asset URLs, acquisition timestamps, cloud metrics, projection
and band metadata — the BFF **reads** this and does not duplicate it into app tables. App tables
(auth/plots/fields/seasons/ops, see [app/models.py](apps/api/app/models.py)) are owned by the api
and migrated via Alembic (`app.cli db upgrade`). Catalog (pgSTAC) migrations are owned by the
ingestion worker. `catalog_resolver.py` holds a multi-source registry where ISRO
`resourcesat-2a-liss3-boa` is the active production source. AWiFS, LISS-4, EOS-04/06, NISAR,
Cartosat, and archive/context sources are gated until validation; Sentinel-2/Sentinel-1 remain
legacy opt-in only.

## Domain rules (hard guardrails — see [docs/engineering-dos-donts.md](docs/engineering-dos-donts.md) and [docs/data-ingestion-and-satellite-rules.md](docs/data-ingestion-and-satellite-rules.md))

These are easy to get wrong and are enforced across the raster/catalog code:

- **ResourceSat LISS-3 analytic band order** (4 bands): `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`.
  STAC `eo:bands`/`raster:bands` must match exactly. TiTiler expressions are **positional**
  (`b1`,`b2`,...), so band NAME->POSITION translation happens only in [indices.py](apps/api/app/raster/indices.py); never hard-code positions elsewhere.
- **ResourceSat display is FCC** with role order `NIR,RED,GREEN` (`bidx=3,2,1`). Do not use
  Sentinel true-colour RGB positions `[1,8,9]`.
- **ResourceSat reflectance correction:** raw uint16 DN is stored; apply
  `corrected = dn * 0.0001 + 0.0`. Do not apply Sentinel-2's `-0.1` offset.
- **ResourceSat cloud/validity mask:** there is **no SCL**. Use the Akasha threshold mask v1
  classes `0=nodata,1=valid,2=cloud,3=shadow,4=water`; keep `{1,4}` by default.
- **Resampling:** nearest-neighbour for categorical masks (and their overviews); bilinear/cubic for
  continuous reflectance. Analytic COG and mask COG stay as **separate** assets.
- **Indices** are normalized-difference `(a-b)/(a+b)`: NDVI=(NIR-RED), NDMI=(NIR-SWIR1),
  NDWI_GREEN_NIR=(GREEN-NIR). MSAVI is a non-normalized formula. ResourceSat does not support
  NDRE/RECI; SAR sources are never optical-index sources.
- **ISRO ResourceSat LISS-3 BOA differs from Sentinel-2** (see [indices.py](apps/api/app/raster/indices.py),
  [scripts/prepare_resourcesat_liss3_boa_cogs.py](scripts/prepare_resourcesat_liss3_boa_cogs.py)):
  **4 analytic bands** `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`; reflectance offset is
  **`0.0`** (not `-0.1`); there is **no SCL** — a provisional "Akasha threshold mask v1" (classes
  0=nodata,1=valid,2=cloud,3=shadow,4=water; keep `{1,4}`) is generated instead; display uses an
  **FCC** false-colour composite (NIR/RED/GREEN, no blue band). Multi-scene compositing uses a
  "most-recent valid pixel" rule ([services/ingestion/akasha_ingest/composite.py](services/ingestion/akasha_ingest/composite.py)).
- **Determinism/idempotency:** scene key =
  `{satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}`.
  ResourceSat object keys use `s3://akasha-cogs/{source}/scene/{date}/{sceneComponent}/analytic.tif|mask.tif`
  for scenes and `s3://akasha-cogs/{source}/composite/{aoiId}/{date}/analytic.tif|mask.tif` for
  composites. `upsert` is the normal STAC load mode; uploads skip existing keys unless `--force`.

## Data & ingestion pipeline

Real COGs are large and **not committed** (`data/raw/`, `data/work/` are gitignored). ResourceSat
LISS-3 BOA is ingested via Bhoonidhi: `worker.py bhoonidhi-search` / `bhoonidhi-download`
(client in [services/ingestion/akasha_ingest/bhoonidhi.py](services/ingestion/akasha_ingest/bhoonidhi.py),
CQL2 `Online=Y` filter), then `scripts/prepare_resourcesat_liss3_boa_cogs.py` +
`worker.py build-composite` / `worker.py ingest-manifest`. Legacy Sentinel-2 and Sentinel-1 helper
scripts remain for regression/migration reference only, not the production ingestion path.

## Frontend rules
- Map renderer is **MapLibre GL JS**; plot drawing uses **Terra Draw + MapLibre adapter**. Do not
  use `@mapbox/mapbox-gl-draw` (it targets Mapbox GL).
- Server state via **TanStack Query**. Derive all layer/date/tile metadata from the BFF; keep
  basemap and satellite overlays as separate sources/layers; use relative same-origin tile URLs only.
- Default map layer is the source's natural display mode (ResourceSat FCC for production) —
  **never** show NDVI/any index as the default layer.

## Source-of-truth docs
[docs/](docs/) is canonical; start at [docs/platform-plan.md](docs/platform-plan.md).
Key files: `architecture-tech-stack.md` (services, BFF API contracts), `data-ingestion-and-satellite-rules.md`
(imagery/COG/STAC/mask/index rules), `engineering-dos-donts.md` (guardrail checklist),
`auth-team-admin-plan.md` (auth/RBAC design), `india-specific-productization-plan.md`
(ISRO/Bhoonidhi product layer), `emergent-context.md` (per-phase handoff notes),
and [infra/selfhosted/README.md](infra/selfhosted/README.md) (Coolify/Azure deployment).
Pinned image/dependency versions matter (GDAL/rasterio/rio-tiler/TiTiler) — do not float to `latest`.
