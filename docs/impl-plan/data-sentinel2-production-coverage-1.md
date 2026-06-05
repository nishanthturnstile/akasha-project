---
goal: Production Sentinel-2 L2A Multi-Scene Coverage Pipeline
version: 1.0
date_created: 2026-05-31
last_updated: 2026-05-31
owner: Akasha Engineering
tags: data, ingestion, satellite, sentinel-2, cog, stac, minio, titiler, frontend
---

# Introduction

This implementation plan upgrades Akasha from a single Sentinel-2 L2A proof scene to a production-like multi-scene satellite imagery pipeline for the requested South India polygon. The pipeline must discover latest 2026 Sentinel-2 L2A products over the target polygon, create a dry-run coverage manifest before downloading large SAFE ZIPs, prepare optimized analytic and SCL Cloud Optimized GeoTIFFs, upload/register multiple scenes in MinIO and STAC, and serve the selected date to the UI through one backend-managed mosaic tile contract.

The requested polygon is represented by this bounding box for Sentinel-2 STAC search and candidate scoring:

| Field | Value |
|-------|-------|
| West | `74.168701` |
| South | `8.085101` |
| East | `81.013184` |
| North | `14.434701` |
| GeoJSON polygon | `{"type":"Polygon","coordinates":[[[81.013184,14.434701],[74.168701,14.434701],[74.168701,8.085101],[81.013184,8.085101],[81.013184,14.434701]]]}` |

The first production-like milestone will select latest available coverage from the last 90 days within 2026, grouped by intersecting MGRS tile, and will remain dry-run by default to prevent accidental multi-GB downloads.

## 1. Requirements & Constraints

- **REQ-001**: `scripts/download_sentinel2_l2a_product.py` must support the requested polygon bounding box as an explicit preset without removing existing presets.
- **REQ-002**: The downloader must prefer 2026 data and default to a last-90-days search window ending at runtime date, constrained to the year 2026, unless `--datetime` is explicitly provided.
- **REQ-003**: The downloader must produce a dry-run coverage manifest by default and must not download any SAFE ZIP unless an explicit download flag is supplied.
- **REQ-004**: The downloader must rank products using MGRS tile grouping, required asset completeness, positive target-bbox overlap, overlap score, cloud cover, and acquisition recency.
- **REQ-005**: The downloader manifest must include target bbox, date window, inspected products, selected products, MGRS tile metadata, overlap metadata, estimated download size, and coverage warnings.
- **REQ-006**: The ingestion pipeline must support multiple Sentinel-2 L2A products/scenes instead of relying only on the hardcoded `SAMPLE_SCENE`.
- **REQ-007**: The COG preparation pipeline must support both the existing single-ZIP workflow and a new manifest-driven batch workflow.
- **REQ-008**: Prepared COG output paths must include the MGRS tile to avoid same-date storage collisions.
- **REQ-009**: MinIO object keys must include the MGRS tile to avoid same-date storage collisions.
- **REQ-010**: STAC registration must support loading multiple generated STAC items in one operation.
- **REQ-011**: The BFF must aggregate multiple STAC items for a selected acquisition date and expose a single date-level layer contract to the frontend.
- **REQ-012**: The UI must continue consuming one `SatelliteScene` object per selected date: one tile URL template, one merged bounds value, one attribution value, and one visibility/opacity control.
- **REQ-013**: Backend tile serving must retain the existing single-COG route behavior as a fallback when only one scene exists for a date.
- **REQ-014**: Documentation must be updated to explain that one complete Sentinel-2 SAFE ZIP represents one MGRS tile/granule, not complete coverage for a large AOI.
- **SEC-001**: Copernicus credentials must continue to be read only from environment variables or terminal prompt; credentials must not be written to manifests, logs, docs, or source files.
- **SEC-002**: MinIO/S3 credentials and internal object URLs must remain server-side and must not be exposed to the browser.
- **SEC-003**: API error responses must not leak secrets, internal service hostnames, stack traces, SQL text, or raw S3 credentials.
- **PER-001**: The default downloader mode must be dry-run to avoid accidental large downloads over the wide target polygon.
- **PER-002**: Batch downloads must be serial by default to reduce CDSE throttling risk; concurrency may be added later behind an explicit option.
- **PER-003**: The frontend must not stack many raster sources/layers for the initial production-like implementation; mosaic or date-level composition must be handled behind the backend contract.
- **CON-001**: The current running system has only one registered STAC item and two COG objects in the legacy date-only sample layout: `sentinel-2-l2a/2025-09-14/analytic.tif` and `sentinel-2-l2a/2025-09-14/scl.tif`.
- **CON-002**: The legacy storage key layout `sentinel-2-l2a/{date}/analytic.tif` cannot support more than one MGRS tile for the same acquisition date.
- **CON-003**: The current BFF resolver `get_item_for_date` returns one item for a date and therefore cannot serve same-date multi-tile coverage without refactoring.
- **CON-004**: The target polygon is large and may require many Sentinel-2 MGRS tiles, resulting in tens of GB of SAFE ZIPs and COG outputs.
- **GUD-001**: Preserve backward compatibility for the Slice 2 single-scene proof path until the multi-scene path is verified.
- **GUD-002**: Prefer manifest-driven workflows for repeatability, auditability, and resumability.
- **GUD-003**: Prefer backend mosaic serving over frontend multi-layer rendering for initial production-like serving.
- **PAT-001**: Keep the same same-origin browser contract: `/api/tiles/...` must be the browser-facing tile path.
- **PAT-002**: Keep large generated rasters ignored by git.
- **PAT-003**: Continue using the frozen Akasha analytic band order: `B04, B08, B05, B06, B07, B11, B12, B03, B02`.

## 2. Implementation Steps

### Implementation Phase 1 — Downloader Target Preset, 2026 Date Window, and Coverage Manifest

- GOAL-001: Update the downloader so operators can discover 2026 Sentinel-2 L2A products for the requested polygon and inspect selected coverage before any download occurs.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | In `scripts/download_sentinel2_l2a_product.py`, add `BBOX_PRESETS["south-india-target"] = [74.168701, 8.085101, 81.013184, 14.434701]`. Do not remove `south-india` or `bengaluru-install`. | | |
| TASK-002 | In `scripts/download_sentinel2_l2a_product.py`, replace `DEFAULT_DATETIME = "2025-07-01T00:00:00Z/2025-09-30T23:59:59Z"` with a function named `default_datetime_range(now: datetime | None = None) -> str` that returns a last-90-days interval constrained to 2026. If current date is after 2026-12-31, cap end date to `2026-12-31T23:59:59Z`. If current date is before 2026-01-01, use `2026-01-01T00:00:00Z/2026-03-31T23:59:59Z`. | | |
| TASK-003 | In `scripts/download_sentinel2_l2a_product.py`, update argparse so `--datetime` defaults to `None`; after parsing, set `datetime_range = args.datetime or default_datetime_range()`. | | |
| TASK-004 | In `scripts/download_sentinel2_l2a_product.py`, add a pure helper `bbox_intersection(a: list[float], b: list[float]) -> list[float] | None` that returns `[west, south, east, north]` only when the boxes overlap with positive area. | | |
| TASK-005 | In `scripts/download_sentinel2_l2a_product.py`, add a pure helper `bbox_area_degrees(bbox: list[float]) -> float` for deterministic candidate scoring. Use degree-space area only for ranking; do not represent it as a geodesic area. | | |
| TASK-006 | In `scripts/download_sentinel2_l2a_product.py`, extend `CandidateProduct` with `mgrs_tile: str | None`, `grid_code: str | None`, `overlap_bbox: list[float] | None`, `overlap_area: float`, and `overlap_percent: float`. | | |
| TASK-007 | In `scripts/download_sentinel2_l2a_product.py`, update `collect_candidates` to accept `target_bbox: list[float]`, compute overlap metadata for every candidate, and preserve candidates with `overlap_area > 0` for selection. | | |
| TASK-008 | In `scripts/download_sentinel2_l2a_product.py`, add `select_coverage_candidates(candidates: list[CandidateProduct]) -> list[CandidateProduct]` that groups by `mgrs_tile` when available and selects one best candidate per tile. Sort candidates by `(missing_required_assets != (), overlap_area <= 0, -overlap_percent, cloud_cover or 9999, datetime descending)`. | | |
| TASK-009 | In `scripts/download_sentinel2_l2a_product.py`, update `candidate_to_manifest` to include `mgrs_tile`, `grid_code`, `overlap_bbox`, `overlap_area`, and `overlap_percent`. | | |
| TASK-010 | In `scripts/download_sentinel2_l2a_product.py`, update `write_manifest` to include a top-level `selection` object with selected product IDs, selected MGRS tiles, estimated total download bytes, estimated total download human value, and warnings. | | |
| TASK-011 | In `scripts/download_sentinel2_l2a_product.py`, update `print_candidates` to show MGRS tile and overlap percentage. | | |
| TASK-012 | Add unit tests for `default_datetime_range`, `bbox_intersection`, `bbox_area_degrees`, and `select_coverage_candidates`. Preferred path: create `tests/test_download_sentinel2_l2a_product.py` or an equivalent existing test location. | | |

### Implementation Phase 2 — Explicit Batch Download From Selected Manifest

- GOAL-002: Add a controlled batch download mode that downloads only selected manifest products and skips already-complete ZIPs.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | In `scripts/download_sentinel2_l2a_product.py`, add an explicit CLI flag named `--download-selected` or update existing `--download` semantics so it downloads the coverage-selected candidates instead of only `--candidate-index` when a new `--coverage-mode` flag is enabled. The default behavior must remain dry-run. | | |
| TASK-014 | In `scripts/download_sentinel2_l2a_product.py`, implement serial iteration over selected candidates using existing `download_product`. | | |
| TASK-015 | In `scripts/download_sentinel2_l2a_product.py`, write per-product download status into the manifest: `pending`, `downloaded`, `skipped_existing`, or `failed`. | | |
| TASK-016 | In `scripts/download_sentinel2_l2a_product.py`, preserve the existing single-product `--candidate-index` path for backwards compatibility. | | |
| TASK-017 | Add tests or a no-network dry-run fixture verifying that default execution writes a manifest and does not call `download_product`. | | |

### Implementation Phase 3 — Manifest-Driven Multi-Product COG Preparation

- GOAL-003: Prepare COGs for multiple downloaded SAFE products while preserving the existing single-ZIP workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | In `scripts/prepare_sentinel2_l2a_cogs.py`, add CLI argument `--selection-manifest` that points to the downloader manifest. | | |
| TASK-019 | In `scripts/prepare_sentinel2_l2a_cogs.py`, implement manifest parsing that extracts selected products with local ZIP paths under `data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip`. | | |
| TASK-020 | In `scripts/prepare_sentinel2_l2a_cogs.py`, preserve current `--zip-path` behavior when `--selection-manifest` is not supplied. | | |
| TASK-021 | In `scripts/prepare_sentinel2_l2a_cogs.py`, update output path generation for manifest-driven mode to `data/seed/rasters/{acquisitionDate}/{mgrsTile}/analytic.tif`, `data/seed/rasters/{acquisitionDate}/{mgrsTile}/scl.tif`, and `data/seed/rasters/{acquisitionDate}/{mgrsTile}/prepare_manifest.json`. | | |
| TASK-022 | In `scripts/prepare_sentinel2_l2a_cogs.py`, include product ID, MGRS tile, acquisition datetime, acquisition date, processing baseline, source ZIP, raster bounds, CRS, dimensions, dtype, nodata, and band descriptions in each `prepare_manifest.json`. | | |
| TASK-023 | In `scripts/prepare_sentinel2_l2a_cogs.py`, add a batch summary manifest at `data/seed/rasters/batch_prepare_manifest.json` or a path derived from `--selection-manifest`. | | |
| TASK-024 | Add tests for path generation to ensure two products with the same acquisition date and different MGRS tiles produce distinct output directories. | | |

### Implementation Phase 4 — Dynamic Scene Identity, MinIO Upload, and STAC Registration

- GOAL-004: Replace singleton-only ingestion with manifest-driven multi-scene upload and catalog registration while retaining demo compatibility.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | In `services/ingestion/akasha_ingest/scene.py`, add a constructor or helper `SceneIdentity.from_prepare_manifest(manifest: dict) -> SceneIdentity`. | | |
| TASK-026 | In `services/ingestion/akasha_ingest/scene.py`, update `SceneIdentity.analytic_key` to return `f"{satellite}/{acquisition_date}/{mgrs_tile}/analytic.tif"` for dynamic scenes. Preserve `SAMPLE_SCENE` compatibility through either a legacy property or migration note. | | |
| TASK-027 | In `services/ingestion/akasha_ingest/scene.py`, update `SceneIdentity.scl_key` to return `f"{satellite}/{acquisition_date}/{mgrs_tile}/scl.tif"` for dynamic scenes. | | |
| TASK-028 | In `services/ingestion/akasha_ingest/config.py`, add `prepared_manifest_glob()` or equivalent helper to discover `data/seed/rasters/*/*/prepare_manifest.json`. | | |
| TASK-029 | In `services/ingestion/akasha_ingest/storage.py`, add `seed_manifest_cogs(manifest_paths: list[Path], force: bool = False) -> list[str]` that uploads every prepared `analytic.tif` and `scl.tif` to the collision-safe MinIO keys. | | |
| TASK-030 | In `services/ingestion/akasha_ingest/storage.py`, add `verify_manifest_cogs(manifest_paths: list[Path]) -> tuple[bool, str]` that validates every manifest scene has non-empty COG objects and raster metadata. | | |
| TASK-031 | In `services/ingestion/akasha_ingest/catalog.py`, add `build_stac_item_from_prepare_manifest(manifest: dict) -> dict` or equivalent generator that creates STAC items using dynamic MinIO object keys and raster metadata. | | |
| TASK-032 | In `services/ingestion/akasha_ingest/catalog.py`, update `load_items` or add `load_manifest_items` to load multiple generated STAC items through NDJSON. | | |
| TASK-033 | In `services/ingestion/worker.py`, add command `ingest-manifest` with arguments `--manifest-glob`, `--force`, and `--method upsert|insert_ignore`. It must upload COGs and load generated STAC items. | | |
| TASK-034 | In `services/ingestion/worker.py`, add command `verify-manifest-cogs` that verifies all manifest scenes in MinIO. | | |
| TASK-035 | Add tests for dynamic key generation and multi-item NDJSON loading helpers without requiring live MinIO/PostGIS. | | |

### Implementation Phase 5 — BFF Date Aggregation and Mosaic Tile Contract

- GOAL-005: Serve many same-date scenes to the UI as one date-level satellite layer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-036 | In `apps/api/app/raster/catalog_resolver.py`, add `items_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]` that returns all matching STAC items for the date. | | |
| TASK-037 | In `apps/api/app/raster/catalog_resolver.py`, update `list_dates` to deduplicate by acquisition date and include aggregate fields: `sceneCount`, `bounds`, `tileAvailable`, `usablePixelPercent`, `cloudMaskedPercent`, `coveragePercent`, and `metricsProvisional`. Initial metric aggregation may use simple average or best available scene-level provisional values, documented as provisional. | | |
| TASK-038 | In `apps/api/app/raster/catalog_resolver.py`, add `merged_bbox(items: list[dict[str, Any]]) -> list[float] | None`. | | |
| TASK-039 | In `apps/api/app/raster/catalog_resolver.py`, add `resolve_assets_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]` that returns analytic/SCL hrefs and band metadata for all items on that date. | | |
| TASK-040 | In `apps/api/app/raster/tiles.py`, add mosaic tile URL construction. Preferred implementation: use TiTiler mosaic support if available in the deployed image; fallback implementation must keep single-COG behavior when the date has exactly one item. | | |
| TASK-041 | In `apps/api/app/product.py`, update `/api/layers/default` to use all latest-date items and return merged bounds. | | |
| TASK-042 | In `apps/api/app/product.py`, update `/api/tiles/{source_id}/{acquisition_date}/rgb/{z}/{x}/{y}.png` to route to single-COG fallback for one item and mosaic serving for multiple items. | | |
| TASK-043 | Add BFF tests where two STAC items share one acquisition date. Verify `/api/sources/{sourceId}/dates` returns one date with `sceneCount = 2` and merged bounds. | | |
| TASK-044 | Add BFF tests verifying `/api/layers/default` returns merged bounds when multiple items exist. | | |
| TASK-045 | Add BFF tests verifying tile route preserves existing single-COG URL behavior for one item. | | |

### Implementation Phase 6 — Frontend Date-Level Layer Compatibility

- GOAL-006: Keep the frontend simple by consuming the BFF date-level mosaic contract without adding one layer per scene.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-046 | In `apps/frontend/src/types/api.ts`, add optional fields to `SceneDate` and `DefaultLayer` types: `sceneCount?: number` and `bounds?: [number, number, number, number]` if not already present. | | |
| TASK-047 | In `apps/frontend/src/pages/MapPage.tsx`, ensure the `SatelliteScene` uses merged bounds from `/api/layers/default` or date metadata when available. | | |
| TASK-048 | In `apps/frontend/src/components/layers/LayerPanel.tsx`, optionally display `sceneCount` for the selected date as non-blocking metadata. If this increases scope, defer to a later enhancement. | | |
| TASK-049 | Keep `apps/frontend/src/lib/satelliteLayer.ts` using one MapLibre raster source with one tile template. Do not add one raster source per MGRS tile in this phase. | | |
| TASK-050 | Run frontend tests and add a small unit test only if type changes require it. | | |

### Implementation Phase 7 — Documentation and Operator Runbook Updates

- GOAL-007: Document the production-like workflow, warnings, and updated path conventions.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-051 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` to state that one complete SAFE ZIP is one Sentinel-2 MGRS tile/granule, not full coverage for a large polygon. | | |
| TASK-052 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` with dry-run coverage manifest command examples using the new target bbox preset and 2026 last-90-days default. | | |
| TASK-053 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` with batch download examples that require explicit download flags. | | |
| TASK-054 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` with manifest-driven batch COG preparation examples. | | |
| TASK-055 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` with new output paths containing `{acquisitionDate}/{mgrsTile}`. | | |
| TASK-056 | Update `docs/sentinel-2-l2a-cog-prep-runbook.md` with upload/register commands for manifest-driven ingestion. | | |
| TASK-057 | Update `docs/data-ingestion-and-satellite-rules.md` with dynamic scene identity, collision-safe object keys, STAC item idempotency, and date-level mosaic serving rules. | | |
| TASK-058 | Update any README or operator docs that reference `sentinel-2-l2a/{date}/analytic.tif` as the only storage key convention. | | |

### Implementation Phase 8 — End-to-End Verification and Rollout

- GOAL-008: Verify the production-like pipeline incrementally before attempting full-region downloads.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-059 | Run the downloader dry-run for the new target preset and confirm the manifest contains 2026 products, selected MGRS tiles, overlap scores, warnings, and total estimated download size. | | |
| TASK-060 | Run a capped batch download for one or two selected MGRS tiles before full-region download. | | |
| TASK-061 | Run single-product COG preparation and confirm existing behavior still works. | | |
| TASK-062 | Run manifest-driven COG preparation for at least two products sharing one date and confirm distinct output directories. | | |
| TASK-063 | Run manifest-driven upload/register and confirm internal STAC API returns multiple items. | | |
| TASK-064 | Query `/api/sources/sentinel-2-l2a/dates` and confirm the multi-scene date appears once with aggregate metadata. | | |
| TASK-065 | Query `/api/layers/default` and confirm merged bounds cover all registered scenes for the selected date. | | |
| TASK-066 | Request one tile inside each registered scene footprint and confirm `200 image/png`. | | |
| TASK-067 | Open the UI and confirm the satellite toggle renders the selected date through one raster layer and one tile template. | | |
| TASK-068 | Run backend tests. | | |
| TASK-069 | Run frontend tests. | | |
| TASK-070 | Run ingestion verification for all manifest scenes in MinIO. | | |

## 3. Alternatives

- **ALT-001**: Keep downloading a single best scene only. This was rejected because the requested polygon spans a wide region and one Sentinel-2 MGRS tile cannot provide production-like coverage.
- **ALT-002**: Render one frontend raster layer per selected MGRS tile. This was rejected for the first production-like implementation because it complicates UI state, increases MapLibre layer/source churn, and pushes composition complexity to the browser.
- **ALT-003**: Pre-mosaic all COGs into one very large COG per date. This was deferred because it increases preprocessing time, storage use, and operational complexity before the multi-scene catalog path is proven.
- **ALT-004**: Continue using date-only object keys. This was rejected because same-date multi-tile scenes would overwrite or collide at `sentinel-2-l2a/{date}/analytic.tif` and `sentinel-2-l2a/{date}/scl.tif`.
- **ALT-005**: Load all available 2026 time series immediately. This was deferred because it multiplies data volume and complexity. The first milestone is latest complete-ish coverage.
- **ALT-006**: Use only scene-level cloud cover for final production usability metrics. This is acceptable only as a provisional metric. Final AOI usability should be computed from SCL pixels across selected scenes.

## 4. Dependencies

- **DEP-001**: Copernicus Data Space STAC API at `https://stac.dataspace.copernicus.eu/v1` for product discovery.
- **DEP-002**: Copernicus Data Space OData API at `https://catalogue.dataspace.copernicus.eu/odata/v1` for product download hrefs and content length.
- **DEP-003**: Copernicus credentials supplied through `CDSE_ACCESS_TOKEN` or `CDSE_USERNAME` and `CDSE_PASSWORD`, or terminal prompt.
- **DEP-004**: Docker Compose service `ingestion-worker` for reliable rasterio/GDAL/JP2 COG preparation on Windows.
- **DEP-005**: MinIO bucket `akasha-cogs` for COG object storage.
- **DEP-006**: pgSTAC via `stac-fastapi-pgstac` for catalog registration and item discovery.
- **DEP-007**: TiTiler service for tile rendering from COGs and future mosaic tile serving.
- **DEP-008**: FastAPI BFF in `apps/api` for same-origin tile proxying and product metadata APIs.
- **DEP-009**: MapLibre frontend in `apps/frontend` for raster source display.
- **DEP-010**: Existing runbook `docs/sentinel-2-l2a-cog-prep-runbook.md` and data rules `docs/data-ingestion-and-satellite-rules.md`.

## 5. Files

- **FILE-001**: `scripts/download_sentinel2_l2a_product.py` — Add target bbox preset, 2026 last-90-days default, overlap scoring, MGRS grouping, dry-run coverage manifest, and explicit batch download mode.
- **FILE-002**: `scripts/prepare_sentinel2_l2a_cogs.py` — Add manifest-driven batch processing and scene-disambiguated `{date}/{mgrsTile}` output paths.
- **FILE-003**: `services/ingestion/akasha_ingest/scene.py` — Add dynamic scene identity support and collision-safe object key generation.
- **FILE-004**: `services/ingestion/akasha_ingest/config.py` — Add prepared manifest discovery helpers and preserve existing sample item helpers.
- **FILE-005**: `services/ingestion/akasha_ingest/storage.py` — Add manifest-driven multi-scene COG upload and verification.
- **FILE-006**: `services/ingestion/akasha_ingest/catalog.py` — Add generated multi-item STAC registration through NDJSON.
- **FILE-007**: `services/ingestion/akasha_ingest/seed.py` — Keep sample seed compatibility and optionally delegate to manifest-driven paths where appropriate.
- **FILE-008**: `services/ingestion/worker.py` — Add manifest-driven ingest and verify commands.
- **FILE-009**: `apps/api/app/raster/catalog_resolver.py` — Aggregate STAC items by date and resolve all assets for a selected date.
- **FILE-010**: `apps/api/app/raster/tiles.py` — Add mosaic tile URL/proxy support and keep single-COG fallback.
- **FILE-011**: `apps/api/app/product.py` — Return merged default layer metadata and serve mosaic tiles under the same-origin API contract.
- **FILE-012**: `apps/frontend/src/types/api.ts` — Add optional scene count and merged bounds fields if missing.
- **FILE-013**: `apps/frontend/src/pages/MapPage.tsx` — Ensure selected scene uses merged bounds and same tile template contract.
- **FILE-014**: `apps/frontend/src/components/layers/LayerPanel.tsx` — Optional scene count display.
- **FILE-015**: `apps/frontend/src/lib/satelliteLayer.ts` — Keep one raster source per selected date and use merged bounds.
- **FILE-016**: `docs/sentinel-2-l2a-cog-prep-runbook.md` — Update operator workflow for multi-scene production-like coverage.
- **FILE-017**: `docs/data-ingestion-and-satellite-rules.md` — Update ingestion identity, storage key, and mosaic serving rules.
- **FILE-018**: `docs/impl-plan/data-sentinel2-production-coverage-1.md` — This implementation plan.
- **FILE-019**: `tests/test_download_sentinel2_l2a_product.py` — New or updated tests for downloader pure helpers and selection behavior.
- **FILE-020**: `apps/api/tests/test_slice2.py` or new API test file — Tests for multi-item date aggregation and default layer merged bounds.
- **FILE-021**: `apps/frontend/src/lib/satelliteLayer.test.ts` and related frontend tests — Update only if frontend type/contract changes require it.

## 6. Testing

- **TEST-001**: Unit test `default_datetime_range` for current dates before 2026, during 2026, and after 2026.
- **TEST-002**: Unit test `bbox_intersection` returns expected overlap for overlapping boxes and `None` for disjoint boxes.
- **TEST-003**: Unit test `bbox_area_degrees` returns deterministic positive area for valid boxes.
- **TEST-004**: Unit test candidate grouping selects one best candidate per MGRS tile.
- **TEST-005**: Unit test candidate selection rejects or warns on zero-overlap products.
- **TEST-006**: Unit test dry-run manifest generation contains target bbox, selected candidates, overlap metadata, MGRS metadata, warnings, and total estimated bytes.
- **TEST-007**: Unit test default downloader execution does not call `download_product` unless explicit download flag is present.
- **TEST-008**: Unit test COG prep path generation avoids collisions for same-date products with different MGRS tiles.
- **TEST-009**: Unit test `SceneIdentity` dynamic object keys include acquisition date and MGRS tile.
- **TEST-010**: Unit test generated STAC item assets point to collision-safe S3 keys.
- **TEST-011**: API test where two STAC items share the same date and `/api/sources/{sourceId}/dates` returns a single aggregated date.
- **TEST-012**: API test where `/api/layers/default` returns merged bounds for multiple scenes.
- **TEST-013**: API test where single-scene tile route remains backward compatible.
- **TEST-014**: API test for missing scene returns sanitized standard error shape.
- **TEST-015**: Frontend test ensuring one `SatelliteScene` can consume merged bounds and one tile template.
- **TEST-016**: Integration test or manual validation: dry-run manifest with the requested polygon returns 2026 selected products and no downloads.
- **TEST-017**: Integration test or manual validation: manifest-driven upload/register creates multiple STAC items visible through internal STAC API.
- **TEST-018**: Integration test or manual validation: tile request inside each registered scene footprint returns `200 image/png`.
- **TEST-019**: UI validation: satellite layer toggle displays imagery through one raster layer and one date-level tile template.
- **TEST-020**: Regression validation: existing 2025 single-scene sample can still be verified and served.

## 7. Risks & Assumptions

- **RISK-001**: The requested polygon is large and may require many MGRS tiles, causing large CDSE downloads and large local COG outputs.
- **RISK-002**: Last 90 days of 2026 may not contain cloud-acceptable data for every intersecting MGRS tile.
- **RISK-003**: Simple bbox overlap scoring may not guarantee full polygon coverage because Sentinel tile footprints are not perfect rectangles. It is acceptable for the first dry-run milestone but should be improved with geometry intersection later.
- **RISK-004**: TiTiler mosaic support must be verified in the current `ghcr.io/developmentseed/titiler:1.0.0` image. If unavailable, an additional TiTiler mosaic/pgSTAC service or BFF-side mosaicjson flow may be required.
- **RISK-005**: Same-date scenes can have different acquisition times/orbits. Selecting one date-level mosaic may require deterministic ordering and possible seam handling.
- **RISK-006**: Scene-level cloud cover is not the same as AOI-level usable-pixel percentage. Metrics must remain marked provisional until SCL-derived AOI metrics are implemented.
- **RISK-007**: Changing storage keys requires migration or compatibility handling for the existing sample objects.
- **RISK-008**: Batch STAC registration may need robust idempotency to avoid duplicate items on repeated ingest attempts.
- **RISK-009**: Wide-region COG preparation can be slow and disk-heavy on local machines.
- **ASSUMPTION-001**: Operators will run dry-run discovery before any large download.
- **ASSUMPTION-002**: Operators will provide Copernicus credentials outside source control.
- **ASSUMPTION-003**: Large generated rasters remain ignored by git and are stored in MinIO for runtime serving.
- **ASSUMPTION-004**: Initial production-like coverage means latest available coverage, not historical time series.
- **ASSUMPTION-005**: The frontend should remain a consumer of date-level layer metadata and should not own MGRS composition logic.
- **ASSUMPTION-006**: Backward compatibility with the existing single-scene sample is required until the new manifest-driven flow is verified.

## 8. Related Specifications / Further Reading

- `docs/sentinel-2-l2a-cog-prep-runbook.md`
- `docs/data-ingestion-and-satellite-rules.md`
- `docs/architecture-tech-stack.md`
- `docs/platform-plan.md`
- `scripts/download_sentinel2_l2a_product.py`
- `scripts/prepare_sentinel2_l2a_cogs.py`
- `services/ingestion/akasha_ingest/scene.py`
- `services/ingestion/akasha_ingest/storage.py`
- `services/ingestion/akasha_ingest/catalog.py`
- `apps/api/app/raster/catalog_resolver.py`
- `apps/api/app/raster/tiles.py`
- `apps/api/app/product.py`
- Copernicus Data Space STAC API: `https://stac.dataspace.copernicus.eu/v1`
- Copernicus Data Space OData API: `https://catalogue.dataspace.copernicus.eu/odata/v1`
- STAC specification: `https://stacspec.org/`
- TiTiler documentation: `https://developmentseed.org/titiler/`
