# Celery Sentinel-2 Ingestion Automation Plan

## Purpose

Automate Akasha's existing manual Sentinel-2 L2A ingestion workflow with Celery while preserving the current service boundaries and data contracts.

The automated workflow must:

- Discover Sentinel-2 L2A scenes for the configured AOI.
- Download complete provider products as native `.SAFE.zip` files.
- Convert each SAFE product into Akasha's required Cloud-Optimized GeoTIFF outputs.
- Upload only validated COG outputs to MinIO.
- Register scene metadata and COG asset hrefs in pgSTAC.
- Keep TiTiler and the frontend using the existing BFF/STAC-driven tile contract.

This document is a plan only. It does not implement Celery or change runtime behavior.

## Current Manual Workflow

The current manual path is already split into three reliable boundaries:

1. Product discovery and download:
   - Script: `scripts/download_sentinel2_l2a_product.py`
   - Provider: Copernicus Data Space Ecosystem.
   - STAC collection: `sentinel-2-l2a`.
   - Download asset: CDSE `Product`.
   - Output: complete native Sentinel-2 L2A `.SAFE.zip`.
   - Local path:
     `data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip`
   - Discovery manifest:
     `data/raw/sentinel-2-l2a/coverage_manifest.json`

2. SAFE ZIP to COG preparation:
   - Script: `scripts/prepare_sentinel2_l2a_cogs.py`
   - Input: one or more complete `.SAFE.zip` products selected by the coverage manifest.
   - Output per selected scene:
     `data/seed/rasters/{acquisitionDate}/{mgrsTile}/analytic.tif`
     `data/seed/rasters/{acquisitionDate}/{mgrsTile}/scl.tif`
     `data/seed/rasters/{acquisitionDate}/{mgrsTile}/prepare_manifest.json`

3. MinIO upload and STAC registration:
   - CLI: `services/ingestion/worker.py ingest-manifest --method upsert`
   - Uploads prepared COGs to MinIO.
   - Builds pgSTAC items from `prepare_manifest.json`.
   - Uses deterministic scene identities and collision-safe object keys.

The Celery implementation should reuse these boundaries instead of creating a second ingestion path.

## Provider Data Format

For Sentinel-2, use Copernicus Data Space Ecosystem current access.

Provider query:

- API: CDSE STAC API.
- Collection: `sentinel-2-l2a`.
- Search filters:
  - AOI bbox or configured AOI geometry.
  - Datetime interval.
  - Maximum cloud cover threshold.
  - Maximum candidate count.

Provider download:

- Download the `Product` asset from the selected STAC item.
- The provider supplies the product as a complete native Sentinel-2 L2A SAFE product ZIP.
- The file should be stored locally during processing as:
  `data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip`

The SAFE ZIP contains JPEG 2000 source assets and metadata. Required source assets for Akasha are:

| Akasha output | SAFE source asset |
|---|---|
| analytic band 1 B04 | `B04_10m.jp2` |
| analytic band 2 B08 | `B08_10m.jp2` |
| analytic band 3 B05 | `B05_20m.jp2` |
| analytic band 4 B06 | `B06_20m.jp2` |
| analytic band 5 B07 | `B07_20m.jp2` |
| analytic band 6 B11 | `B11_20m.jp2` |
| analytic band 7 B12 | `B12_20m.jp2` |
| analytic band 8 B03 | `B03_10m.jp2` |
| analytic band 9 B02 | `B02_10m.jp2` |
| SCL mask | `SCL_20m.jp2` |

Recommended metadata to preserve in manifests:

- `MTD_MSIL2A.xml`
- tile metadata XML
- `manifest.safe`
- product id
- MGRS tile
- acquisition datetime
- processing baseline
- cloud cover
- product bbox and geometry

Do not use Sentinel-2 Global Mosaics for this workflow. The mosaic products do not provide all analytic bands and SCL in the shape Akasha needs for masked statistics.

## Celery Design

### Services

Add background processing without collapsing the existing multi-service topology.

Recommended services:

- `api`
  - Accepts admin/internal ingestion requests.
  - Creates an ingestion run record.
  - Enqueues Celery tasks.
  - Does not perform heavy geospatial processing.

- `ingestion-worker`
  - Runs Celery worker process.
  - Performs discovery, download, conversion, upload, verification, and STAC registration.
  - Reuses current ingestion package code and prep scripts.
  - Needs network access to CDSE and private access to MinIO/Postgres/STAC API.

- `valkey` or `redis`
  - Celery broker.
  - Optional result backend for short-lived task state.
  - Durable ingestion status should still be stored in Postgres, not only in Celery results.

Celery Beat should be deferred. The first release should use an API-triggered run so operators can test bounded ingestion runs safely.

### API Trigger

Add an internal/admin route:

```text
POST /api/ingestion-runs
GET  /api/ingestion-runs
GET  /api/ingestion-runs/{runId}
```

Initial request shape:

```json
{
  "sourceId": "sentinel-2-l2a",
  "bbox": [76.8, 12.5, 77.9, 13.6],
  "datetime": "2026-01-01T00:00:00Z/2026-03-31T23:59:59Z",
  "maxItems": 50,
  "maxCloudCover": 30.0,
  "force": false
}
```

Defaults:

- `sourceId`: `sentinel-2-l2a`
- `bbox`: configured Bangalore AOI when omitted
- `datetime`: use the existing downloader default if omitted
- `maxItems`: `50`
- `maxCloudCover`: `30.0`
- `force`: `false`

The API should return immediately:

```json
{
  "id": "uuid",
  "sourceId": "sentinel-2-l2a",
  "status": "queued",
  "celeryTaskId": "task-id",
  "createdAt": "2026-06-08T00:00:00Z"
}
```

### Run Tracking

Add an app-owned ingestion run table in the `akasha` schema. This table is not a pgSTAC catalog table.

Suggested columns:

- `id uuid primary key`
- `source_id text not null`
- `status text not null`
- `request jsonb not null`
- `celery_task_id text`
- `coverage_manifest_path text`
- `batch_prepare_manifest_path text`
- `selected_scene_count integer`
- `downloaded_scene_count integer`
- `prepared_scene_count integer`
- `uploaded_scene_count integer`
- `registered_scene_count integer`
- `failed_scene_count integer`
- `error_code text`
- `error_message text`
- `error_details jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `started_at timestamptz`
- `finished_at timestamptz`
- `updated_at timestamptz not null default now()`

Allowed statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Optional child table for per-scene status:

- `run_id uuid`
- `product_id text`
- `scene_key text`
- `item_id text`
- `mgrs_tile text`
- `acquisition_datetime timestamptz`
- `status text`
- `raw_zip_path text`
- `analytic_key text`
- `scl_key text`
- `prepare_manifest_path text`
- `error_message text`
- timestamps

Per-scene tracking is recommended because large AOIs may select multiple MGRS tiles and some scenes can fail independently.

### Task Structure

Use one top-level orchestration task and smaller importable functions underneath. Celery subtasks can be added later, but v1 can run sequentially inside one task to keep state handling simple.

Top-level task:

```text
akasha_ingest.tasks.run_sentinel2_l2a_ingestion(run_id)
```

Internal stages:

1. Mark run `running`.
2. Discover CDSE candidate products.
3. Write `coverage_manifest.json`.
4. Download all selected products.
5. Prepare COGs from the selection manifest.
6. Upload COGs to MinIO.
7. Register STAC items with `upsert`.
8. Verify uploaded COG metadata.
9. Mark run `succeeded` or `failed`.

Recommended importable functions:

- `discover_sentinel2_products(request) -> coverage_manifest`
- `download_sentinel2_products(coverage_manifest, force=False) -> download_statuses`
- `prepare_sentinel2_cogs(selection_manifest, overwrite=False) -> batch_prepare_manifest`
- `upload_prepared_cogs(manifest_paths, force=False) -> upload_results`
- `register_prepared_items(manifest_paths, method="upsert") -> registration_result`
- `verify_prepared_cogs(manifest_paths) -> verification_result`

The current script functions can be refactored into these functions while keeping the CLI wrappers.

## Detailed Automated Process

### 1. Discover Candidate Scenes

Input:

- AOI bbox or configured AOI.
- Date range.
- Cloud threshold.
- Max items.

Process:

- Query CDSE STAC collection `sentinel-2-l2a`.
- Collect only items that expose a complete `Product` asset.
- Reject candidates missing required source assets:
  - `B04_10m`
  - `B08_10m`
  - `B05_20m`
  - `B06_20m`
  - `B07_20m`
  - `B11_20m`
  - `B12_20m`
  - `B03_10m`
  - `B02_10m`
  - `SCL_20m`
- Group candidates by MGRS tile.
- Select the best candidate per intersecting MGRS tile.
- Rank by current downloader rules: useful overlap, required asset availability, cloud cover, and recency.

Output:

```text
data/raw/sentinel-2-l2a/coverage_manifest.json
```

The manifest should retain the existing shape:

- `collection`
- `bbox`
- `datetime`
- `required_source_assets`
- `recommended_metadata_assets`
- `selection.selected_product_ids`
- `selection.selected_mgrs_tiles`
- `selection.estimated_total_bytes`
- `selection.warnings`
- `selected_candidates`
- `candidates`

### 2. Download Provider ZIPs

Input:

- `coverage_manifest.json`
- CDSE credentials from environment.

Credentials:

- Prefer `CDSE_ACCESS_TOKEN` if present.
- Otherwise use `CDSE_USERNAME` and `CDSE_PASSWORD`.
- Do not prompt in Celery workers.
- Do not log secrets.

Process:

- For each selected product, download the CDSE `Product` asset.
- Write to a `.part` file first.
- Rename to final `.SAFE.zip` only after the full response is written.
- If `ContentLength` is known, skip existing complete ZIPs unless `force=true`.
- Record per-product status:
  - `downloaded`
  - `skipped_existing`
  - `failed`

Output:

```text
data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip
```

Raw ZIP retention:

- v1 uses raw ZIPs as temporary worker-disk artifacts.
- Do not upload raw ZIPs to MinIO.
- Keep local raw ZIPs only as long as needed for the run, unless a future retention flag is added.

### 3. Convert SAFE ZIPs to COGs

Input:

- `coverage_manifest.json`
- Downloaded `.SAFE.zip` files.

Process per selected product:

1. Extract the SAFE ZIP to:
   `data/work/sentinel-2-l2a/`
2. Use `B04_10m.jp2` as the 10 m reference grid.
3. Build analytic intermediate GeoTIFF:
   - data type: `uint16`
   - band count: `9`
   - nodata: `0`
   - band order: `[B04, B08, B05, B06, B07, B11, B12, B03, B02]`
   - 10 m bands copied directly when aligned.
   - 20 m continuous bands resampled to 10 m with bilinear resampling.
4. Build SCL intermediate GeoTIFF:
   - data type: `uint8`
   - band count: `1`
   - nodata: `0`
   - source: `SCL_20m.jp2`
   - resampled to 10 m with nearest-neighbour.
5. Translate both intermediates to COGs:
   - compression: DEFLATE
   - block size: `512`
   - `BIGTIFF=IF_SAFER`
   - analytic overview resampling: average
   - SCL overview resampling: nearest
6. Validate both COGs using `rio-cogeo`.
7. Write `prepare_manifest.json`.
8. Remove temporary intermediates unless debug mode is enabled.

Output per scene:

```text
data/seed/rasters/{acquisitionDate}/{mgrsTile}/analytic.tif
data/seed/rasters/{acquisitionDate}/{mgrsTile}/scl.tif
data/seed/rasters/{acquisitionDate}/{mgrsTile}/prepare_manifest.json
```

Batch output:

```text
data/seed/rasters/batch_prepare_manifest.json
```

### 4. Upload COGs to MinIO

Input:

- Prepared scene manifests.

Process:

- Ensure bucket exists:
  `akasha-cogs`
- Build scene identity from `prepare_manifest.json`.
- Upload only validated COGs.
- Skip existing keys unless `force=true`.
- Set object metadata:
  - `akasha-asset`
  - `akasha-scene-key`
  - `akasha-placeholder=false`

MinIO object structure:

```text
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/analytic.tif
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/scl.tif
```

Example:

```text
s3://akasha-cogs/sentinel-2-l2a/2026-01-15/43PHQ/20260115T052000Z_0500/analytic.tif
s3://akasha-cogs/sentinel-2-l2a/2026-01-15/43PHQ/20260115T052000Z_0500/scl.tif
```

Do not use date-only keys for dynamic production scenes. Date-only keys cannot represent multiple MGRS tiles or multiple scenes on the same date without collisions.

### 5. Register STAC Items

Input:

- Prepared scene manifests.

Process:

- Build one STAC item per prepared scene.
- Use deterministic item ids from scene identity.
- Load items through pypgstac with `method="upsert"`.
- Register asset hrefs as private MinIO S3 URIs.

Required STAC item properties:

- `datetime`
- `platform`
- `constellation=sentinel-2`
- `instruments=["msi"]`
- `gsd`
- `eo:cloud_cover`
- `s2:product_level`
- `s2:mgrs_tile`
- `s2:processing_baseline`
- `akasha:scene_key`
- `akasha:acquisition_date`
- `akasha:usable_pixel_percent`
- `akasha:cloud_masked_percent`
- `akasha:coverage_percent`
- `akasha:metrics_provisional`
- projection metadata where available

Required STAC assets:

- `analytic`
  - href: `s3://akasha-cogs/.../analytic.tif`
  - type: `image/tiff; application=geotiff; profile=cloud-optimized`
  - roles: `["data", "reflectance"]`
  - `eo:bands` matching frozen analytic order
  - `raster:bands` with scale `0.0001` and offset `-0.1`

- `scl`
  - href: `s3://akasha-cogs/.../scl.tif`
  - type: `image/tiff; application=geotiff; profile=cloud-optimized`
  - roles: `["metadata", "data-mask"]`
  - categorical SCL classification classes

### 6. Verify Outputs

After upload and registration:

- Verify both objects exist in MinIO.
- Verify neither object is a placeholder or empty object.
- Open COGs through rasterio/GDAL `/vsis3/`.
- Confirm:
  - analytic has 9 bands.
  - SCL has 1 band.
  - CRS matches.
  - transform matches.
  - width and height match.
  - both have internal overviews.
- Mark run failed if any selected scene fails verification.

## Final TIFF Output Contract for TiTiler

TiTiler serves display tiles from the analytic COG only. It does not compute cloud-masked statistics.

Analytic COG:

- file name: `analytic.tif`
- format: Cloud-Optimized GeoTIFF
- data type: `uint16`
- band count: `9`
- stored values: raw Sentinel-2 DN
- scale: `0.0001`
- offset: `-0.1`
- internal overviews: required
- continuous overview resampling: average
- common grid: 10 m grid from `B04_10m`
- band order:
  1. `B04`
  2. `B08`
  3. `B05`
  4. `B06`
  5. `B07`
  6. `B11`
  7. `B12`
  8. `B03`
  9. `B02`

SCL COG:

- file name: `scl.tif`
- format: Cloud-Optimized GeoTIFF
- data type: `uint8`
- band count: `1`
- source values: Sentinel-2 SCL classes
- common grid: same 10 m grid as analytic COG
- internal overviews: required
- categorical overview resampling: nearest
- registered as a separate STAC asset

True-colour tile rendering:

- BFF resolves STAC items for the selected source/date.
- BFF extracts the analytic asset href.
- BFF translates band names to TiTiler positions.
- True-colour RGB uses bands `[1, 8, 9]`:
  - red: `B04` at position 1
  - green: `B03` at position 8
  - blue: `B02` at position 9
- BFF calls internal TiTiler `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png`.
- Browser receives only same-origin `/api/tiles/...` URLs.

Statistics path:

- BFF computes masked NDVI/NDRE/NDMI/NDWI statistics.
- BFF reads both analytic COG and SCL COG.
- BFF applies scale/offset.
- BFF excludes SCL classes `{0,1,2,3,7,8,9,10,11}`.
- BFF keeps SCL class `6` water by default.
- TiTiler is not used for cloud-masked statistics.

## Failure Handling and Idempotency

Idempotency key:

```text
{satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}
```

Scene component:

```text
{compactAcquisitionDatetime}_{processingBaselineWithoutDot}
```

Expected behavior:

- Re-running the same scene must not create duplicate STAC items.
- Re-running the same scene must not overwrite existing validated MinIO COGs unless `force=true`.
- Failed COG validation must stop upload and STAC registration for that scene.
- Download failures should mark only affected scenes failed.
- The top-level run should report failed scene counts and error details.
- Partial success policy should be explicit:
  - v1 recommendation: mark the run `failed` if any selected scene fails.
  - Still keep successfully registered scenes because STAC upsert and MinIO uploads are idempotent.

Retries:

- Retry transient CDSE download failures with exponential backoff.
- Retry transient MinIO upload failures.
- Retry transient pgSTAC load failures.
- Do not blindly retry COG validation failures; those indicate bad input, dependency problems, or conversion bugs.

Cleanup:

- Remove `.part` download files on failure.
- Remove temporary conversion intermediates by default.
- Keep `prepare_manifest.json` for successfully prepared scenes.
- Raw SAFE ZIPs are temporary worker artifacts for v1 and may be deleted after successful upload/register/verify if disk pressure requires it.

## Configuration

Required worker environment:

```text
DATABASE_URL
STAC_API_URL
S3_ENDPOINT_URL
S3_ACCESS_KEY
S3_SECRET_KEY
S3_REGION
AKASHA_COG_BUCKET
SEED_DATA_DIR
AOI_CONFIG_PATH
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
CDSE_ACCESS_TOKEN or CDSE_USERNAME/CDSE_PASSWORD
```

Recommended optional environment:

```text
AKASHA_INGEST_RAW_DIR=data/raw/sentinel-2-l2a
AKASHA_INGEST_WORK_DIR=data/work/sentinel-2-l2a
AKASHA_INGEST_OUTPUT_ROOT=data/seed/rasters
AKASHA_INGEST_MAX_ITEMS=50
AKASHA_INGEST_MAX_CLOUD_COVER=30
AKASHA_INGEST_DOWNLOAD_TIMEOUT_SECONDS=180
AKASHA_INGEST_FORCE=false
AKASHA_INGEST_KEEP_RAW=false
AKASHA_INGEST_KEEP_INTERMEDIATE=false
```

Do not expose MinIO, Postgres, STAC API, TiTiler, or Celery broker publicly.

## Read Path After Automation

No frontend contract change is required.

After successful ingestion:

1. MinIO contains validated scene COGs.
2. pgSTAC contains one item per scene with `analytic` and `scl` assets.
3. BFF reads source/date metadata from STAC.
4. `/api/sources/{sourceId}/dates` returns date-level metadata.
5. `/api/layers/default` returns a same-origin tile template.
6. `/api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png` proxies to TiTiler for single-scene dates.
7. Multi-scene dates still return `MOSAIC_TILES_UNAVAILABLE` until a supported mosaic backend is configured.

The browser must never receive MinIO URLs, raw product paths, credentials, or TiTiler internal URLs.

## Testing and Acceptance Criteria

Unit tests:

- Candidate collection and MGRS selection from fixture CDSE STAC items.
- Manifest writing with selected products and download statuses.
- Scene identity generation from prepared manifests.
- Dynamic MinIO key generation.
- STAC item generation from prepared manifests.
- API run creation and Celery enqueue with mocked Celery.

Integration tests:

- Existing ingestion manifest tests continue to pass.
- Mock or fixture end-to-end run:
  - create run
  - discover fixture candidates
  - skip/download fixture ZIP
  - prepare COGs
  - mock MinIO upload
  - build pgSTAC item
  - mark run succeeded

Manual acceptance:

- Run a bounded Bangalore ingestion request.
- Confirm run moves from `queued` to `running` to `succeeded`.
- Confirm `coverage_manifest.json` records selected products.
- Confirm prepared manifests exist.
- Confirm MinIO contains non-empty:
  - `analytic.tif`
  - `scl.tif`
- Confirm `worker.py verify-manifest-cogs` passes.
- Confirm `/api/sources/sentinel-2-l2a/dates` includes the ingested acquisition date.
- Confirm one RGB tile renders through the BFF tile route.
- Confirm one index statistics request returns plausible masked pixel accounting.

Suggested commands after implementation:

```bash
cd apps/api && python -m pytest -q
python -m pytest services/ingestion/tests -q
python scripts/validate_slice2.py
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify-manifest-cogs
```

## Rollout Sequence

1. Refactor existing downloader and prep scripts into importable functions while preserving CLI behavior.
2. Add ingestion run persistence and API enqueue route.
3. Add Celery app and top-level Sentinel-2 task.
4. Add broker and Celery worker runtime configuration for Docker Compose and the deployment stack.
5. Add tests for run tracking, task orchestration, manifests, and idempotency.
6. Run one small bounded Bangalore ingestion manually through the API.
7. Verify MinIO, pgSTAC, BFF date metadata, tile serving, and statistics.
8. Only after API-triggered ingestion is stable, add optional Celery Beat scheduling.

## Open Follow-Ups

- Decide whether failed multi-scene runs should support partial-success status instead of top-level `failed`.
- Decide raw ZIP retention policy for audited production runs; v1 default is temporary only.
- Add a mosaic backend before promising RGB rendering for dates with multiple selected scenes.
- Add operator UI for ingestion runs only after API-triggered workflow is stable.
