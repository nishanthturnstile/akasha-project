# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

Akasha is a Railway-first geospatial MVP: browse true-colour Sentinel-2 L2A imagery over an
Area of Interest (Bangalore) and compute **cloud-masked vegetation-index statistics**
(NDVI/NDRE/NDMI/NDWI) for user-drawn plots. It is a Dockerized **multi-service** application
(not one collapsed service), portable between Railway and local Docker Compose / on-prem.

Development is **slice-by-slice**: Slice 0 (skeleton) and Slice 1 (storage/catalog) are done,
Slice 2 (raster de-risk) is implemented. Build only the requested slice; preserve API/data
contracts from earlier slices. The slice roadmap and per-slice doc scope live in
[docs/platform-plan.md](docs/platform-plan.md).

## Canonical application tree

This is the most important thing to understand before editing.

- [apps/api/](apps/api/) — FastAPI BFF (the backend, package `app`)
- [apps/frontend/](apps/frontend/) — React 18 + Vite + TypeScript SPA
- [services/ingestion/](services/ingestion/), [services/ingestion-sar/](services/ingestion-sar/), [services/titiler/](services/titiler/), [services/stac-api/](services/stac-api/), [services/minio/](services/minio/)
- [infra/gateway/](infra/gateway/) (Caddy reverse proxy), [infra/docker/](infra/docker/), [infra/railway/](infra/railway/)

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
make up          # docker compose -f infra/docker/docker-compose.yml up --build -d (copies .env.example -> .env)
make down        # stop;  make reset = down -v (delete volumes);  make logs
```

### Operational CLIs (run inside the api / ingestion containers)
```bash
# api service — app schema (plots) migrations; NOT product endpoints
python -m app.cli migrate            # apply apps/api/migrations/*.sql (idempotent)
python -m app.cli check              # postgis_version() + akasha.plots + MinIO liveness

# ingestion worker — catalog (pgSTAC) + object storage
python worker.py seed                # pgSTAC migrate -> load collection/item -> create MinIO bucket/keys
python worker.py ingest-manifest     # upload prepared COGs + load STAC items from prepare_manifest.json
python worker.py verify              # Slice 1 exit criteria
python worker.py verify-cogs         # Phase 2: also require non-empty real COGs
```

## Architecture

### Service topology & the one-public-service rule
```
Browser ─> web (Caddy + React SPA)  ──/api/*──> api (FastAPI BFF)
                 │                   ──/tiles/*─> titiler (rio-tiler/GDAL)
   api ─> stac-api (pgSTAC) ─> postgis (PostgreSQL + PostGIS)
   api ─> titiler ─> minio (S3-compatible COG storage)
   ingestion-worker ─> minio / stac-api / postgis
```
**Only the `web` gateway is publicly reachable.** The browser calls `/api/*` and `/tiles/*` on
that same origin; the gateway proxies to internal `api`/`titiler`. `api`, `titiler`, `stac-api`,
`postgis`, `minio` never get a public domain. The frontend must never talk directly to MinIO,
PostGIS, STAC, or TiTiler, and must never hard-code COG/object URLs.

### BFF (`apps/api/app`) — the core
- [main.py](apps/api/app/main.py) wires routers: `/health`, `/api/_skeleton/*` (ops visibility),
  product API ([product.py](apps/api/app/product.py)), and plot CRUD ([plots.py](apps/api/app/plots.py)).
- Heavy geospatial deps (rasterio/shapely/pyproj/rio-tiler) are **imported lazily** inside
  `app.raster.*` so importing `app.main` never requires them (keeps the Emergent preview healthy).
- [app/raster/](apps/api/app/raster/) is the masked-statistics engine, decomposed for testability:
  `service.py` orchestrates → `catalog_resolver.py` (STAC API + seed-JSON fallback) +
  `geo_validate.py` (polygon area/vertex limits) + `raster_reader.py` (rasterio dual-COG windows,
  GDAL/S3) + `indices.py` (band registry, name→position) + `statistics_core.py` (pure-numpy math).
- Standard error shape everywhere: `{ "error": { code, message, details } }`.

### Statistics are computed in the BFF, not TiTiler
**TiTiler serves RGB display tiles only.** Cloud-masked index statistics are computed in the BFF
with rasterio/rio-tiler, because vanilla TiTiler `/cog/statistics` takes a single `url` and cannot
apply a categorical mask from a second (SCL) COG. The BFF reads the analytic COG window **and** the
SCL COG window for the request polygon, applies per-band scale/offset, applies the SCL mask, then
computes stats + pixel-percentage fields.

### Catalog & storage ownership
STAC/pgSTAC owns collections, items, asset URLs, acquisition timestamps, cloud metrics, projection
and band metadata — the BFF **reads** this and does not duplicate it into app tables. App tables
(`akasha.plots`, optional `index_requests`/`app_settings`) are owned by the api and migrated via
`app.cli`. Catalog (pgSTAC) migrations are owned by the ingestion worker.

## Domain rules (hard guardrails — see [docs/engineering-dos-donts.md](docs/engineering-dos-donts.md) and [docs/data-ingestion-and-satellite-rules.md](docs/data-ingestion-and-satellite-rules.md))

These are easy to get wrong and are enforced across the raster/catalog code:

- **Frozen analytic band order** (9 bands): `[B04, B08, B05, B06, B07, B11, B12, B03, B02]`.
  STAC `eo:bands`/`raster:bands` must match exactly. TiTiler expressions are **positional**
  (`b1`,`b2`,…), so band NAME→POSITION translation happens only in [indices.py](apps/api/app/raster/indices.py); never hard-code positions elsewhere.
- **True-colour RGB uses bands `[1, 8, 9]`** (B04 Red, B03 Green, B02 Blue) — **not** `[1,2,3]`.
- **Reflectance correction:** raw uint16 DN is stored; apply `corrected = dn * 0.0001 + (-0.1)`.
  The STAC `offset` is `-0.1`, **not** the raw-DN `BOA_ADD_OFFSET=-1000`. Offsets may be band-specific.
- **Cloud/validity mask:** exclude SCL classes `{0,1,2,3,7,8,9,10,11}` plus nodata; **keep class 6
  (water)** by default. Never blindly set `nodata=0` (valid reflectance can be 0).
- **Resampling:** nearest-neighbour for categorical SCL (and its overviews); bilinear/cubic for
  continuous reflectance. Analytic COG and SCL COG stay as **separate** assets.
- **Indices** are normalized-difference `(a-b)/(a+b)`: NDVI=(B08-B04), NDRE=(B08-B05),
  NDMI=(B08-B11), NDWI_GREEN_NIR=(B03-B08). SAR sources are never optical-index sources.
- **Determinism/idempotency:** scene key =
  `{satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}`.
  Object keys: `s3://akasha-cogs/{source}/{date}/{mgrsTile}/{sceneComponent}/analytic.tif|scl.tif`
  (date-only keys are legacy/sample). `upsert` is the normal STAC load mode; uploads skip existing
  keys unless `--force`. Multi-scene dates return `MOSAIC_TILES_UNAVAILABLE` until a mosaic backend exists.

## Data & ingestion pipeline

Real COGs are large and **not committed** (`data/raw/`, `data/work/` are gitignored). The flow:
1. `scripts/download_sentinel2_l2a_product.py` — discover/download CDSE L2A SAFE ZIPs (dry-run by default).
2. `scripts/prepare_sentinel2_l2a_cogs.py` — SAFE ZIP → `analytic.tif` + `scl.tif` COGs +
   `prepare_manifest.json` under `data/seed/rasters/{date}/{mgrsTile}/`. Run inside the ingestion
   Docker image to avoid local GDAL setup (esp. on Windows).
3. `worker.py ingest-manifest` then `worker.py verify-manifest-cogs`.

Sentinel-1 GRD SAR has a parallel path (`download_sentinel1_grd_product.py`,
`prepare_sentinel1_grd_cogs.py`, SNAP GPT graph in `services/ingestion/snap/`). Runbooks:
[docs/sentinel-2-l2a-cog-prep-runbook.md](docs/sentinel-2-l2a-cog-prep-runbook.md),
[docs/sentinel-1-grd-cog-prep-runbook.md](docs/sentinel-1-grd-cog-prep-runbook.md).

## Frontend rules
- Map renderer is **MapLibre GL JS**; plot drawing uses **Terra Draw + MapLibre adapter**. Do not
  use `@mapbox/mapbox-gl-draw` (it targets Mapbox GL).
- Server state via **TanStack Query**. Derive all layer/date/tile metadata from the BFF; keep
  basemap and satellite overlays as separate sources/layers; use relative same-origin tile URLs only.
- Default map layer is true-colour imagery — **never** show NDVI/any index as the default layer.

## Source-of-truth docs
[docs/](docs/) is canonical; start at [docs/platform-plan.md](docs/platform-plan.md).
Key files: `architecture-tech-stack.md` (services, BFF API contracts), `data-ingestion-and-satellite-rules.md`
(imagery/COG/STAC/mask/index rules), `engineering-dos-donts.md` (guardrail checklist),
`emergent-context.md` (per-phase handoff notes), `railway-deployment-guide.md`.
Pinned image/dependency versions matter (GDAL/rasterio/rio-tiler/TiTiler) — do not float to `latest`.
