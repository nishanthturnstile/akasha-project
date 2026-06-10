# Akasha — Project Overview & Structure

This document summarizes the repository layout, architecture, local development workflow, build and run commands, and troubleshooting tips. It is intended for developers who need to run or contribute to Akasha locally or in CI.

## High-level summary

- Purpose: Browser-based geospatial MVP for viewing Sentinel imagery and computing cloud-masked vegetation-index statistics (NDVI, NDRE, NDMI, NDWI) over user-drawn plots.
- Top-level approach: Multi-service Docker Compose stack for local development. The canonical code lives under `apps/` (the BFF and frontend). Supporting services live under `services/` and `infra/` contains Docker and gateway configuration.

## Architecture overview

Services and responsibilities:

- `apps/api` — FastAPI BFF (backend-for-frontend). Implements plot CRUD, raster index/statistics endpoints, and orchestration of raster reading, STAC catalog resolving, and statistics computation.
- `apps/frontend` — React + Vite SPA. Map UI, plot drawing, requests to the BFF, and UI for index/time-series visualization.
- `services/titiler` — Tile service for RGB display tiles (TiTiler). The BFF computes cloud-masked index statistics; TiTiler only serves tiles.
- `services/minio`, `services/stac-api`, `services/postgis` — Storage and catalog services used by stack (MinIO S3-compatible storage, pgSTAC/PostGIS catalog).
- `services/ingestion`, `services/ingestion-sar` — Ingestion workers and tooling for preparing and uploading COGs and SAR processing.

Network and access: Browser → `web` gateway (Caddy) → proxied `/api/*` to `apps/api` and `/tiles/*` to `titiler`. Internal services are not publicly reachable.

## Key design principles & guardrails

- Frozen analytic band order: `[B04, B08, B05, B06, B07, B11, B12, B03, B02]`. Band name→position mapping is centralized in `apps/api/app/raster/indices.py`.
- True-colour RGB uses bands `[1, 8, 9]` (B04 red, B03 green, B02 blue).
- Reflectance correction: apply `corrected = dn * 0.0001 + (-0.1)` using STAC band offsets.
- Cloud mask rules: exclude SCL classes `{0,1,2,3,7,8,9,10,11}` and nodata; keep class 6 (water) by default.
- Resampling: nearest for categorical SCL, bilinear/cubic for continuous reflectance.
- Index formulas: normalized difference `(a-b)/(a+b)` (NDVI: B08-B04, NDRE: B08-B05, NDMI: B08-B11, NDWI (green): B03-B08).

## Repository layout (important paths)

- `apps/api/` — FastAPI BFF source, migrations, tests. Main entry: `apps/api/app/main.py`.
- `apps/frontend/` — React/Vite SPA. Run/build scripts live in this folder. Key files: `src/pages/MapPage.tsx`, `src/components/*`, `src/types/api.ts`.
- `services/` — multi-service helpers and Dockerfiles for ingestion, titiler, stac-api, minio, etc.
- `infra/docker/` — Docker Compose configuration used for local full-stack development. `docker-compose.yml` is the single command used by the `Makefile`.
- `scripts/` — download/prepare COG helper scripts used by the ingestion pipeline.
- `docs/` — developer docs (this file belongs here).

## Local development — prerequisites

- macOS (arm64) or Linux (amd64). Note: Apple Silicon requires attention for some images (SNAP installer and native Linux binaries). Use `--platform linux/amd64` or Docker Buildx emulation when necessary.
- Docker Desktop (with Buildx / QEMU enabled for cross-platform builds).
- Make (repository `Makefile` wraps common commands).
- Node.js & corepack (local frontend dev only): `corepack` is used within Docker builds; locally run via `corepack yarn`.

## Common local workflows

1. Build and run full stack (Docker Compose):

```bash
cd <repo-root>
make up
```

This copies `.env.example` to `infra/docker/.env` (if missing), builds images, and starts containers.

2. Stop the stack:

```bash
make down
# or
docker compose -f infra/docker/docker-compose.yml down
```

3. Build frontend locally (fast verify without Docker):

```bash
cd apps/frontend
corepack yarn install
corepack yarn build
```

4. Run backend tests (BFF):

```bash
cd apps/api
python -m pytest -q
```

5. Validators & smoke tests (no Docker required):

```bash
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
python scripts/smoke-test.py http://localhost:8080
```

## Docker & Apple Silicon notes

- Some services (notably `ingestion-sar` which installs ESA SNAP) are x86-only. On Apple Silicon, builds may need `platform: linux/amd64` or `docker buildx` with QEMU enabled. Example:

```bash
docker buildx build --platform linux/amd64 -t akasha-ingestion-sar:local services/ingestion-sar
```

- If builds fail with overlayfs, I/O, or permission errors, free disk space and prune Docker resources:

```bash
docker system prune -af
docker builder prune -af
```

## Tests and static checks

- Frontend build runs `tsc -p tsconfig.json && tsc -p tsconfig.node.json && vite build` (see `apps/frontend/package.json`). Fix TypeScript errors before CI.
- Backend uses `ruff` and `black` for formatting; tests live under `apps/api/tests`.

## Troubleshooting common failures

- Permission denied on `git push` to upstream: fork the repo or switch to SSH auth.
- Docker build failure on Apple Silicon: enable QEMU, run buildx with `--platform`, or build those images on an amd64 runner.
- Frontend `vite` chunk warnings: chunk size >500k — consider manual chunking or dynamic imports.

## Useful commands (quick reference)

- Build frontend locally:
  - `cd apps/frontend && corepack yarn install && corepack yarn build`
- Run full stack:
  - `make up` (from repo root)
- Rebuild specific service (example: ingestion-sar):
  - `docker compose -f infra/docker/docker-compose.yml build --no-cache ingestion-sar`
- View logs:
  - `docker compose -f infra/docker/docker-compose.yml logs -f` or `logs -f <service>`
- List running containers:
  - `docker compose -f infra/docker/docker-compose.yml ps`

## Contributing notes

- Keep API contracts stable: BFF reads STAC catalog and exposes product endpoints; breaking changes require coordination.
- Use feature branches and open PRs against `main`.
- Update `docs/` for any architectural or workflow changes.

## Contact / Next steps

If you need a developer handoff or a trimmed quickstart README for onboarding, I can generate a short `docs/QUICKSTART.md` containing the minimal commands to get started on macOS or Linux.

---

## End-to-end data flow (detailed)

1. Data acquisition (ingestion):
   - Input sources: Sentinel-2 L2A SAFE products (optical), Sentinel-1 GRD (SAR) where applicable.
   - `scripts/download_sentinel2_l2a_product.py` discovers and optionally downloads SAFE ZIPs.
   - `scripts/prepare_sentinel2_l2a_cogs.py` converts SAFE ZIPs to two Cloud-Optimized GeoTIFFs (COGs) per scene:
     - `analytic.tif` — stacked reflectance bands (uint16 DN + STAC reflectance offsets/scaling stored in metadata).
     - `scl.tif` — Scene Classification Layer (SCL) categorical mask.
   - Prepared COGs and a `prepare_manifest.json` are stored under `data/seed/rasters/{date}/{mgrsTile}/` for ingestion.

2. Ingestion & cataloging (worker):
   - `worker.py ingest-manifest` uploads COGs to object storage (MinIO) and inserts STAC items into pgSTAC.
   - Scene metadata in pgSTAC includes band order, offsets, asset URLs, acquisition timestamps, processing baseline.

3. BFF request handling (apps/api):
   - Browser sends a request to the BFF: e.g., `POST /api/plots/{plot_id}/indices?start=YYYY-MM-DD&end=YYYY-MM-DD&index=NDVI`.
   - The BFF resolves candidate scenes from the STAC catalog (pgSTAC), selects assets for each date, and computes per-scene windows.
   - BFF uses `raster_reader` to load matching windows from both the analytic COG and its SCL COG (separate assets) applying correct resampling per-raster.

4. Masking & reflectance correction:
   - Apply per-band scale & offset from STAC metadata: `corrected_reflectance = dn * scale + offset`.
   - Apply SCL mask: exclude SCL classes `{0,1,2,3,7,8,9,10,11}` and nodata. Keep class `6` (water) by default.

5. Index calculation & statistics:
   - For each valid pixel compute requested index (normalized difference): e.g., `NDVI = (B08 - B04) / (B08 + B04)`.
   - Statistics computed per-scene and aggregated for the plot: `count`, `mean`, `median`, `stddev`, `min`, `max`, and `valid_pixel_percentage`.
   - Time-series: BFF aggregates per-scene statistic across requested date range and returns a list of date→stat pairs (for trend charts).

6. Output formats & storage:
   - JSON API responses containing per-date summary statistics and per-scene details.
   - CSV export for time-series and per-scene metrics (frontend may request/trigger export).
   - STAC items and COGs remain in MinIO and pgSTAC for reproducibility and re-query.

## What this project produces

- User-facing outputs:
  - Interactive map (true-colour tiles served via `titiler` and proxied by the `web` gateway).
  - Plot-level index statistics and time-series for selected indices (NDVI, NDRE, NDMI, NDWI).
  - Trend charts and downloadable CSVs of index values per acquisition date for a plot.
  - Compare-mode visual overlays for two dates (difference visualization) and date slider for temporal browsing.

- Backend outputs / artifacts:
  - MinIO-hosted COGs (`analytic.tif` and `scl.tif`) representing processed scenes.
  - STAC catalog entries in pgSTAC with asset URLs and metadata.
  - API responses (JSON) with masks applied and aggregated statistics.

## Features (user-facing, developer-facing)

- Map & drawing
  - True-colour basemap toggle and visualization layers.
  - Draw polygon plots with Terra Draw adapter.
  - Save/load plot geometries via plot CRUD endpoints.

- Temporal analysis
  - Request per-plot index statistics across a date-range.
  - Time-series charts with hover values and date stacking.
  - Compare two dates side-by-side (or blended) for visual change detection.

- Index computations
  - Supported indices: NDVI, NDRE, NDMI, NDWI (green NIR), extendable via `indices.py` registry.
  - Cloud-masked computations using SCL COGs to exclude invalid pixels.

- Exporting & reporting
  - Download CSV of time-series statistics.
  - Basic summary report in JSON for integrations.

- Developer tools
  - Ingestion scripts to prepare COGs and manifests.
  - `worker.py` ingestion and verification commands to seed catalog and verify COG accessibility.
  - Validators & smoke tests under `scripts/` and `apps/api/tests`.

## Sequence of interactions (request example)

Example: compute NDVI time-series for a plot

1. Frontend POSTs geometry & request: `POST /api/plots` (create plot with GeoJSON geometry) → returns `plot_id`.
2. Frontend requests index statistics:

   POST /api/plots/{plot_id}/indices
   Body: { "index": "NDVI", "start": "2025-01-01", "end": "2025-06-01", "cloud_threshold": 0.2 }

3. BFF resolves STAC scenes in that date window, for each scene:
   - Reads analytic window + SCL window (via rio-tiler/rasterio), applies scale/offset, masks SCL classes, computes NDVI and statistics.
4. BFF aggregates per-scene stats into a time-series array and returns JSON:

```json
{
	"plot_id": "...",
	"index": "NDVI",
	"time_series": [ { "date": "2025-01-01", "mean": 0.45, "median": 0.43, "valid_pct": 0.92 }, ... ]
}
```

## API summary (selected endpoints)

- `POST /api/plots` — Create plot (GeoJSON). Returns `plot_id`.
- `GET /api/plots/{plot_id}` — Fetch saved plot details.
- `POST /api/plots/{plot_id}/indices` — Compute indices/time-series for the plot.
- `GET /api/tiles/{scene}/{z}/{x}/{y}.png` — Tile server (via TiTiler) for RGB display.

## Operational considerations

- Reproducibility: COGs and STAC metadata are treated as source-of-truth. Recomputeable results are produced on-demand by the BFF using those assets.
- Performance: For large AOIs or long date ranges, results are computed per-scene windows and aggregated; consider batching, caching, or precomputing per-plot statistics for production workloads.
- Storage: MinIO holds large COGs and should be sized accordingly; pgSTAC catalog needs disk and PostGIS indexing capacity for spatial/time queries.

---

If you'd like, I can also:

- Add a `docs/QUICKSTART.md` with copy-paste commands for macOS and Linux.
- Add sequence diagrams (Mermaid) for the ingestion → BFF → frontend request flow.

Next, I'll mark the docs review task as complete if you're happy with this addition.

Last updated: 2026-06-09
