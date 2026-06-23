---
goal: Productionise ResourceSat-2A LISS-4 and fully onboard ResourceSat-2A AWiFS through the Akasha Bhoonidhi ingestion-to-serving pipeline
version: 1.0
date_created: 2026-06-23
last_updated: 2026-06-23
owner: Akasha Engineering (ingestion + raster + BFF + frontend)
tags: [data, feature, ingestion, raster, isro, bhoonidhi, resourcesat, liss4, awifs, productionization]
---

# Introduction

This plan productionises **ResourceSat-2A LISS-4 MX70 L2** to the same operational standard as the existing **ResourceSat-2A LISS-3 BOA** source, then fully onboards **ResourceSat-2A AWiFS BOA** as an active, source-aware regional optical source. It assumes the current codebase already has structural support for all three ResourceSat-2A source IDs, and focuses on closing the remaining production gaps: gate-state consistency, real staging verification, manifest-derived STAC registration, source-aware COG validation, scheduling, monitoring, documentation, and regression tests.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking where detailed substeps are needed.

**Goal:** Make LISS-4 production-consumable first, then make AWiFS production-consumable, without regressing LISS-3.

**Architecture:** Reuse the proven Bhoonidhi → prepare COG → composite → STAC → MinIO → BFF source registry → frontend data-driven display architecture. Keep LISS-3, LISS-4, and AWiFS as separate source IDs, separate STAC collections, separate composite COGs, and separate scheduled ingestion jobs. Do not blend pixels across instruments into one COG.

**Tech Stack:** Python 3.11, FastAPI BFF, pgSTAC, PostgreSQL/PostGIS, MinIO/S3-compatible object storage, rasterio/GDAL/rio-cogeo, TiTiler display tiles, React 18 + Vite + TypeScript frontend, MapLibre GL JS, TanStack Query, systemd on the IP-whitelisted `akasha-staging` VM.

## 1. Requirements & Constraints

### Functional requirements

- **REQ-001**: LISS-3 remains the production baseline source `resourcesat-2a-liss3-boa`. No task in this plan may break LISS-3 search, download, prepare, composite, STAC registration, BFF date/tile/statistics serving, or frontend display.
- **REQ-002**: LISS-4 source ID is `resourcesat-2a-liss4-mx70-l2`; Bhoonidhi collection ID is `ResourceSat-2A_LISS4-MX70_L2`; analytic band order is `[BAND2 Green, BAND3 Red, BAND4 NIR]`; there is no SWIR band.
- **REQ-003**: LISS-4 must become production-consumable only after a real staging composite is verified and registered in pgSTAC. Production-consumable means `/api/sources`, `/api/sources/{sourceId}/dates`, display tiles, field statistics, index overlays, and monitoring all work from manifest-ingested STAC items and COGs.
- **REQ-004**: LISS-4 supports `NDVI`, `MSAVI`, and `NDWI_GREEN_NIR`. LISS-4 does not support `NDMI`, `NDRE`, or `RECI` because it has no SWIR or red-edge band.
- **REQ-005**: LISS-4 may be used as a high-resolution field-level source where a verified composite covers the field. The existing best-resolution resolver may prefer LISS-4 for supported indices and must fall back to LISS-3 for unsupported indices and uncovered fields.
- **REQ-006**: AWiFS source ID is `resourcesat-2a-awifs-boa`; Bhoonidhi collection ID is `ResourceSat-2A_AWIFS_BOA`; analytic band order is `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`.
- **REQ-007**: AWiFS must be onboarded as an active `analysisLevel="regional"` optical source. It can expose FCC display and supported indices, but UI copy and metadata must not imply LISS-3/LISS-4-level field precision.
- **REQ-008**: AWiFS supports `NDVI`, `MSAVI`, `NDMI`, and `NDWI_GREEN_NIR` after real product validation confirms its BOA band files and scale/offset match the ResourceSat BOA assumptions.
- **REQ-009**: Each active ResourceSat source must produce separate COG assets: `analytic.tif` for continuous reflectance and `mask.tif` for the categorical Akasha mask.
- **REQ-010**: Each active ResourceSat source must register manifest-derived STAC items in pgSTAC using the source-specific object key scheme `s3://akasha-cogs/{sourceId}/composite/{aoiId}/{date}/analytic.tif|mask.tif`.
- **REQ-011**: `worker.py seed-stac` must not rely on placeholder sample items for production availability. Production availability is proven by `worker.py ingest-manifest` + `worker.py verify-composite` against pgSTAC and MinIO.
- **REQ-012**: The frontend must remain data-driven from `/api/sources`; no hard-coded MinIO, STAC, TiTiler, or COG URLs may be added.
- **REQ-013**: The default imagery display for LISS-4 and AWiFS is FCC (`NIR, RED, GREEN`), not an index ramp.
- **REQ-014**: Every source registry row must include truthful `attribution`, `maskMethod`, `metricsProvisional`, `resolutionMeters`, `analysisLevel`, `supportedIndices`, `displayModes`, `defaultDisplayMode`, and `limitations` fields.

### Security and operations requirements

- **SEC-001**: All Bhoonidhi search and download commands for LISS-4 and AWiFS must run only from the IP-whitelisted `akasha-staging` VM with egress IP `20.219.3.35`.
- **SEC-002**: Bhoonidhi credentials (`BHOONIDHI_USER_ID`, `BHOONIDHI_PASSWORD`) must remain deployment secrets. Do not commit credentials, tokens, downloaded ZIPs, or raw product files.
- **SEC-003**: The browser must call only same-origin `/api/*` and `/tiles/*` routes. It must never call Bhoonidhi, MinIO, pgSTAC, PostGIS, or TiTiler directly.
- **OPS-001**: LISS-4 and AWiFS must have separate systemd unit names, lock files, logs, and environment files so failures do not block LISS-3.
- **OPS-002**: Scheduled jobs must respect Bhoonidhi token TTL, session limits, daily download limits, and worker lock files.
- **OPS-003**: Verification commands must run after each staging ingest. A source cannot be marked active unless the command exits with code 0 and the output contains `composite verification passed`.

### Geospatial and raster constraints

- **CON-001**: LISS-4 has no SWIR band. Any LISS-4 code path that attempts NDMI must fail closed or fall back to LISS-3 through the existing resolver.
- **CON-002**: AWiFS has the same four broad spectral roles as LISS-3 but different spatial resolution and swath. AWiFS STAC metadata must use source-appropriate `gsd`, `resolutionMeters`, and `analysisLevel`.
- **CON-003**: ResourceSat BOA reflectance correction is assumed as `corrected = dn * 0.0001 + 0.0` until real staging validation confirms otherwise. If staging validation finds different scale/offset, update source profiles and STAC metadata before activation.
- **CON-004**: ResourceSat has no native Sentinel-style SCL. Use the Akasha threshold mask v1 class scheme `0=nodata/gap`, `1=valid`, `2=cloud`, `3=shadow`, `4=water`; exclude `{0,2,3}` and keep `{1,4}` by default.
- **CON-005**: Continuous reflectance must use bilinear or cubic resampling. Categorical masks must use nearest-neighbour resampling for base data and overviews.
- **CON-006**: LISS-4 narrow swath can produce partial AOI coverage. LISS-4 production acceptance uses a lower coverage threshold than LISS-3 and relies on field-level fallback to LISS-3 outside LISS-4 coverage.
- **CON-007**: AWiFS 56 m pixels are coarse for small fields. AWiFS activation must keep `analysisLevel="regional"` and source limitations visible.
- **CON-008**: Band NAME-to-position translation must remain centralized in `apps/api/app/raster/indices.py`. Do not hard-code ResourceSat band positions in route handlers, frontend code, or TiTiler URL builders.

### Implementation guidelines

- **GUD-001**: Follow the canonical app tree: backend changes under `apps/api`, frontend changes under `apps/frontend`, ingestion changes under `services/ingestion` and `scripts`, deployment artifacts under `infra/selfhosted`.
- **GUD-002**: Keep the worker orchestration source-parameterized. Do not fork a LISS-4-only or AWiFS-only copy of the full LISS-3 pipeline unless a real product structure forces a narrow adapter.
- **GUD-003**: Preserve pinned geospatial dependency versions. Do not float GDAL, rasterio, rio-cogeo, rio-tiler, TiTiler, or Docker images to `latest`.
- **GUD-004**: Prefer test-first changes for every code modification. Each source activation must have unit tests, static registry tests, and staging verification evidence.
- **PAT-001**: Use manifest-derived STAC items for production availability. Checked-in sample STAC items are contract scaffolds and do not prove operational readiness.
- **PAT-002**: Use `availabilityStatus="gated"` only when a source is visible for roadmap/context but not ready for user consumption. Active sources must have verified COGs and pgSTAC items.
- **PAT-003**: Use `metricsProvisional=true` for ResourceSat threshold-mask-derived metrics until a validated native quality layer exists.

## 2. Implementation Steps

### Implementation Phase 0 — Baseline audit and acceptance gate lock

- GOAL-001: Capture the current source-state reality before changing behavior: LISS-3 active, LISS-4 structurally wired with local prepared COGs but incomplete production gate, AWiFS scaffolded and gated.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Record the current ResourceSat source-state matrix in `docs/impl-plan/data-resourcesat-liss4-awifs-productionization-1.md`: LISS-3 active baseline; LISS-4 productionization target; AWiFS onboarding target. Use the source IDs `resourcesat-2a-liss3-boa`, `resourcesat-2a-liss4-mx70-l2`, and `resourcesat-2a-awifs-boa`. | ✅ | 2026-06-23 |
| TASK-002 | Verify the current code locations before editing: `services/ingestion/akasha_ingest/pipeline_registry.py`, `services/ingestion/akasha_ingest/bhoonidhi.py`, `scripts/prepare_resourcesat_liss3_boa_cogs.py`, `services/ingestion/akasha_ingest/composite.py`, `services/ingestion/akasha_ingest/catalog.py`, `apps/api/app/raster/catalog_resolver.py`, and `data/seed/stac/`. | ✅ | 2026-06-23 |
| TASK-003 | Run the static registry tests before changing implementation: from repo root run `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py -q`. Expected result before edits: tests pass or fail only because local Python dependencies are missing. If dependencies are missing, install with the repo-documented dev requirements before continuing. | ✅ | 2026-06-23 |
| TASK-004 | Confirm LISS-3 remains the benchmark by running, on the target deployment, `python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item`. Acceptance output must include `composite verification passed`; failure blocks LISS-4/AWiFS activation because the baseline path must be healthy first. | ✅ | 2026-06-23 |

Phase 0 validation notes (2026-06-23):

- TASK-002 evidence: all seven referenced code locations exist. `data/seed/stac/` contains LISS-3 and LISS-4 collection/sample-item seeds plus the AWiFS collection seed; no checked-in AWiFS sample item exists, which matches later plan guidance to avoid production seed loading from a placeholder AWiFS item.
- TASK-002 state findings: LISS-3 remains the active baseline; AWiFS is explicitly gated in `apps/api/app/raster/catalog_resolver.py`; LISS-4 is structurally wired but still lacks an explicit `availabilityStatus`, so the source serializer defaults it to active. Phase 1 TASK-007 must correct this before activation work continues.
- TASK-002 follow-up finding: LISS-4 resolution is `5.8` m in `services/ingestion/akasha_ingest/composite.py` and `apps/api/app/raster/catalog_resolver.py`, but `scripts/prepare_resourcesat_liss3_boa_cogs.py` currently declares `resolution_meters=5.0` for the LISS-4 source profile. Phase 1/2 cleanup should reconcile this to the plan value before production verification.
- TASK-003 evidence: `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py -q` completed locally with `53 passed in 4.54s`.
- TASK-004 evidence: SSH access to `akasha-staging` works via the configured alias (`ssh akasha-staging "hostname && whoami"` returned `akasha-staging` / `akashaadmin`), and the VM egress IP is `20.219.3.35`. Core staging validation passed: web/api/stac-api/titiler/postgis/minio containers are healthy; `python -m app.cli check` inside the API container reported PostGIS, Alembic version table, and MinIO reachable; `/health` inside the API container returned HTTP 200. After deploying the latest ingestion worker image, the staging worker command `python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item` completed with 23 passing checks and output `composite verification passed (23 checks)`. The verified LISS-3 composite is `resourcesat-2a-liss3-boa_composite_bangalore-60km_2026-03-19` with 14 contributing scenes, EPSG:32643, 4 analytic bands, 1 mask band, aligned 5061x5030 shape, valid mask classes `[1, 2, 3, 4]`, 100.0% coverage, and catalog item present.

### Implementation Phase 1 — LISS-4 production-state cleanup

- GOAL-002: Make LISS-4 source-state explicit and consistent across docs, ingestion registry, BFF registry, STAC seed metadata, and frontend behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | In `apps/api/app/raster/catalog_resolver.py`, inspect the `resourcesat-2a-liss4-mx70-l2` entry in `_SOURCE_REGISTRY`. Ensure it has `kind="optical"`, `analysisLevel="field"`, `resolutionMeters=5.8`, `expectedAssets=["analytic","mask"]`, `maskAsset="mask"`, `excludedMaskClasses=[0,2,3]`, `nodataPolicy="mask_only"`, `tileRouteMode="fcc"`, `defaultDisplayMode="FCC"`, and `metricsProvisional=true`. | ✅ | 2026-06-23 |
| TASK-006 | In `apps/api/app/raster/catalog_resolver.py`, set LISS-4 supported indices exactly to `["NDVI", "MSAVI", "NDWI_GREEN_NIR"]`. Ensure `NDMI`, `NDRE`, and `RECI` are absent from `supportedIndices`, `displayModes`, `mapDisplayModes`, and `layerGroups`. | ✅ | 2026-06-23 |
| TASK-007 | In `apps/api/app/raster/catalog_resolver.py`, set the pre-verification LISS-4 production state explicitly to `availabilityStatus="gated"` and `gatedReason="LISS-4 awaits staging composite verification."`. TASK-030 is the only task allowed to change LISS-4 to `availabilityStatus="active"` and `gatedReason=None`. Do not leave LISS-4 active in code while docs describe it as gated. | ✅ | 2026-06-23 |
| TASK-008 | Update `docs/data-ingestion-and-satellite-rules.md` production source table. Before TASK-030 passes, label LISS-4 as `Gated: staging validation in progress`. After TASK-030 passes, label it as `Active: high-resolution field enhancement for NDVI/MSAVI/NDWI_GREEN_NIR with LISS-3 fallback`. | ✅ | 2026-06-23 |
| TASK-009 | Update `docs/reference/satellite-ingestion-onboarding-matrix.md` so the ResourceSat row distinguishes the three variants: LISS-3 `active baseline`, LISS-4 `productionization in progress until TASK-030`, AWiFS `gated until TASK-049`. Do not use one blanket `Done` verdict for all three variants until each has verification evidence. | ✅ | 2026-06-23 |
| TASK-010 | Add or update a BFF test in `apps/api/tests/test_product_sources.py` or `apps/api/tests/test_best_resolution_resolver.py` asserting the LISS-4 source payload has `supportedIndices == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]`, `analysisLevel == "field"`, `resolutionMeters == 5.8`, and no `NDMI`. | ✅ | 2026-06-23 |
| TASK-011 | Run the BFF source registry tests from `apps/api`: `python -m pytest tests/test_best_resolution_resolver.py tests/test_product_sources.py -q`. Expected result: source registry tests pass and LISS-3 tests remain unchanged. | ✅ | 2026-06-23 |

Phase 1 validation notes (2026-06-23):

- TDD red evidence: `python -m pytest tests/test_slice2.py::test_sources_endpoint_contract -q` failed before the registry change because LISS-4 returned `availabilityStatus == "active"` instead of the required `"gated"`.
- Implementation evidence: `apps/api/app/raster/catalog_resolver.py` now explicitly sets LISS-4 `availabilityStatus="gated"` and `gatedReason="LISS-4 awaits staging composite verification."`; supported indices remain exactly `NDVI`, `MSAVI`, and `NDWI_GREEN_NIR`, with no `NDMI`, `NDRE`, or `RECI` in supported/display/map modes.
- Documentation evidence: `docs/data-ingestion-and-satellite-rules.md` labels LISS-4 as `Gated: staging validation in progress`; `docs/reference/satellite-ingestion-onboarding-matrix.md` now splits ResourceSat variants into LISS-3 active baseline, LISS-4 productionization in progress until TASK-030, and AWiFS gated until TASK-049.
- Test evidence: `python -m pytest tests/test_best_resolution_resolver.py tests/test_product_sources.py -q` completed with `24 passed, 15 warnings in 3.14s`; `python -m pytest tests/test_best_resolution_resolver.py tests/test_product_sources.py tests/test_slice2.py::test_sources_endpoint_contract -q` completed with `25 passed, 15 warnings in 2.90s`. The warnings are existing Pydantic `UnsupportedFieldAttributeWarning` warnings from `test_best_resolution_resolver.py`.

### Implementation Phase 2 — LISS-4 manifest-derived STAC and COG verification

- GOAL-003: Ensure LISS-4 is consumed from real prepared manifests and COGs, not only checked-in placeholder sample STAC items.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Inspect the local LISS-4 prepared manifest at `data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json`. Confirm it declares `source_id="resourcesat-2a-liss4-mx70-l2"`, `collection="ResourceSat-2A_LISS4-MX70_L2"`, `composite=true`, `aoi_id="bangalore-60km"`, `composite_resolution_meters=5.8`, `analytic_band_order=["BAND2","BAND3","BAND4"]`, and `band_role_mapping={"GREEN":"BAND2","RED":"BAND3","NIR":"BAND4"}`. | ✅ | 2026-06-23 |
| TASK-013 | In `services/ingestion/akasha_ingest/catalog.py`, verify `_build_resourcesat_boa_stac_item()` builds the LISS-4 composite item ID as `resourcesat-2a-liss4-mx70-l2_composite_bangalore-60km_2026-01-30` when given the local manifest. If the resulting ID differs, update `SceneIdentity.item_id` in `services/ingestion/akasha_ingest/scene.py` only for ResourceSat BOA composite manifests while preserving LISS-3 behavior. | ✅ | 2026-06-23 |
| TASK-014 | Update or add a test in `tests/test_bhoonidhi_ingestion.py` named `test_catalog_emits_manifest_derived_liss4_composite_item`. Use a manifest with `composite=true`, `aoi_id="bangalore-60km"`, and `composite_date="2026-01-30"`; assert item collection, ID, instruments `["liss-4"]`, 3 analytic EO bands, 3 raster bands, `akasha:composite is True`, and asset hrefs under `s3://akasha-cogs/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/`. | ✅ | 2026-06-23 |
| TASK-015 | Run `python -m pytest tests/test_bhoonidhi_ingestion.py::test_catalog_emits_manifest_derived_liss4_composite_item -q`. Expected result after implementation: one test passes. | ✅ | 2026-06-23 |
| TASK-016 | In `services/ingestion/akasha_ingest/config.py`, verify `item_files(collection_id)` does not load ResourceSat sample items as production seed items. Production LISS-4 items must come from `worker.py ingest-manifest`, not `data/seed/stac/resourcesat-2a-liss4-mx70-l2-sample-item.json`. Add a regression test if this behavior is not covered. | ✅ | 2026-06-23 |
| TASK-017 | On the target deployment, run `python worker.py ingest-manifest --manifest-glob '/app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json' --method upsert`. Expected output includes `loaded 1 manifest item(s)` or the repo's equivalent success text from `catalog.load_manifest_items`. | ✅ | 2026-06-23 |
| TASK-018 | On the target deployment, run `python worker.py verify-composite --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --manifest /app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json --min-coverage-percent 10`. Expected output includes passes for 3 analytic bands, 1 mask band, EPSG:32643, aligned shape, overviews, valid mask classes, coverage above 10%, and catalog item existence. | ✅ | 2026-06-23 |

Phase 2 validation notes (2026-06-23):

- TASK-012 evidence: the LISS-4 composite manifest exists on staging at `/srv/akasha/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json` and declares `source_id='resourcesat-2a-liss4-mx70-l2'`, `collection='ResourceSat-2A_LISS4-MX70_L2'`, `composite=True`, `aoi_id='bangalore-60km'`, `composite_resolution_meters=5.8`, `analytic_band_order=['BAND2','BAND3','BAND4']`, and `band_role_mapping={'GREEN':'BAND2','RED':'BAND3','NIR':'BAND4'}`. The manifest is deployed on staging storage and is not checked into the local workspace, which remains consistent with large-raster gitignore rules.
- TASK-013/TASK-014 evidence: `tests/test_bhoonidhi_ingestion.py::test_catalog_emits_manifest_derived_liss4_composite_item` asserts the manifest-derived item ID `resourcesat-2a-liss4-mx70-l2_composite_bangalore-60km_2026-01-30`, instrument `liss-4`, 3 analytic EO/raster bands, `akasha:composite is True`, and source-specific S3 asset hrefs under `s3://akasha-cogs/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/`.
- TASK-015/TASK-016 evidence: `python -m pytest tests/test_bhoonidhi_ingestion.py::test_catalog_emits_manifest_derived_liss4_composite_item -q` completed with `1 passed in 2.78s`; `python -m pytest tests/test_bhoonidhi_ingestion.py::test_resourcesat_sample_items_are_not_loaded_as_production_seed_items tests/test_bhoonidhi_ingestion.py -q` completed with `51 passed in 10.16s`.
- TASK-017 evidence: on `akasha-staging`, `python worker.py ingest-manifest --manifest-glob '/app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json' --method upsert` found 1 prepared manifest, skipped existing analytic/mask objects, and reported `loaded 1 manifest item(s) (method=upsert)`.
- TASK-018 evidence: on `akasha-staging`, `python worker.py verify-composite --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --manifest /app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/composite/bangalore-60km/2026-01-30/prepare_manifest.json --min-coverage-percent 10` completed with 23 passing checks and output `composite verification passed (23 checks)`. Verified details include 2 contributing scenes, 3 analytic bands, 1 mask band, EPSG:32643, aligned 20937x20809 shape, resolution near 5.8 m, analytic/mask overviews, valid mask classes `[0, 3, 4]`, coverage `17.7699% >= 10.0%`, buildable dated item `resourcesat-2a-liss4-mx70-l2_composite_bangalore-60km_2026-01-30`, and catalog item present.

### Implementation Phase 3 — LISS-4 staging production run and scheduler

- GOAL-004: Run LISS-4 from the real Bhoonidhi staging path, validate radiometry, build a production composite, register it, and schedule repeat runs separately from LISS-3.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | On `akasha-staging`, run `python worker.py bhoonidhi-search --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --lookback-days 90 --limit 100`. Acceptance: command exits 0, writes `coverage_manifest.json`, and selected candidates include products from `ResourceSat-2A_LISS4-MX70_L2`. | ✅ | 2026-06-23 |
| TASK-020 | On `akasha-staging`, run `python worker.py bhoonidhi-download --source resourcesat-2a-liss4-mx70-l2 --manifest /srv/akasha/data/work/bhoonidhi/resourcesat-2a-liss4-mx70-l2/coverage_manifest.json --max-downloads 1`. Acceptance: one non-zero-byte ZIP is written under `/srv/akasha/data/raw/bhoonidhi/resourcesat-2a-liss4-mx70-l2/`. | ✅ | 2026-06-23 |
| TASK-021 | Inspect the downloaded LISS-4 product with `gdalinfo` or rasterio from the ingestion container. Record band filenames, CRS, dtype, dimensions, nodata/background behavior, and any scale/offset metadata in `test_reports/pytest/` or a dated markdown report under `test_reports/`. Acceptance: product has `BAND2`, `BAND3`, and `BAND4` files and no required `BAND5` dependency. | ✅ | 2026-06-23 |
| TASK-022 | If TASK-021 confirms scale/offset different from `0.0001/0.0`, update `SOURCE_PROFILES["resourcesat-2a-liss4-mx70-l2"]` in `scripts/prepare_resourcesat_liss3_boa_cogs.py`, update LISS-4 STAC reflectance metadata in `data/seed/stac/resourcesat-2a-liss4-mx70-l2-collection.json`, and update BFF assumptions if any are source-specific. If TASK-021 confirms `0.0001/0.0`, record that result in the validation report and make no code change for scale/offset. | ✅ | 2026-06-23 |
| TASK-023 | On `akasha-staging`, run `python worker.py bhoonidhi-sync --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --max-downloads 3 --min-coverage-percent 10 --method upsert`. Acceptance: search, download, prepare, composite, upload, STAC registration, and post-ingest `verify-composite` complete with exit code 0. | ✅ | 2026-06-23 |
| TASK-024 | Add or verify LISS-4 systemd artifacts under `infra/selfhosted/systemd/`: `akasha-bhoonidhi-liss4-sync.timer`, `akasha-bhoonidhi-liss4-sync.service`, `akasha-bhoonidhi-liss4-sync.sh`, and `bhoonidhi-liss4-sync.env.example`. The timer uses a LISS-4 cadence, the service uses its own environment file, and the wrapper passes `--source resourcesat-2a-liss4-mx70-l2`. | ✅ | 2026-06-23 |
| TASK-025 | Extend `tests/test_bhoonidhi_systemd_artifacts.py` to assert LISS-4 systemd artifacts exist, use source ID `resourcesat-2a-liss4-mx70-l2`, and use lock names containing `liss4` so they cannot collide with LISS-3 locks. | ✅ | 2026-06-23 |
| TASK-026 | Run `python -m pytest tests/test_bhoonidhi_systemd_artifacts.py -q`. Expected result: all systemd artifact tests pass. | ✅ | 2026-06-23 |
| TASK-027 | On `akasha-staging`, install and enable the LISS-4 timer with the repo's install script. Then run `systemctl list-timers | grep akasha-bhoonidhi-liss4-sync` and `journalctl -u akasha-bhoonidhi-liss4-sync.service -n 100 --no-pager`. Acceptance: timer is listed, service can run, and logs show the LISS-4 source ID. | ✅ | 2026-06-23 |
| TASK-028 | Query the deployed BFF after TASK-023: `GET /api/sources/resourcesat-2a-liss4-mx70-l2/dates`. Acceptance: response contains at least one date with `tileAvailable=true`, `coveragePercent` greater than or equal to 10, and `metricsProvisional=true`. | ✅ | 2026-06-23 |
| TASK-029 | Query field statistics or overlay for a field inside LISS-4 coverage with `sourceId=resourcesat-2a-liss3-boa`, `indexType=NDVI`, and high-resolution preference enabled. Acceptance: response provenance has `resolvedSourceId="resourcesat-2a-liss4-mx70-l2"`, `enhanced=true`, and `resolutionMeters=5.8`. | ✅ | 2026-06-23 |
| TASK-030 | Flip LISS-4 to active only after TASK-018, TASK-023, TASK-028, and TASK-029 pass. Update `apps/api/app/raster/catalog_resolver.py` LISS-4 `availabilityStatus` to active, update docs statuses, and record the verification commands and outputs in `test_reports/`. | ✅ | 2026-06-23 |

Phase 3 validation notes (2026-06-23):

- TASK-019 evidence: on `akasha-staging`, `python worker.py bhoonidhi-search --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --lookback-days 90 --limit 100` completed with `found 1 Bhoonidhi item(s)`, `selected 1 candidate(s)`, and wrote `/srv/akasha/data/work/bhoonidhi/resourcesat-2a-liss4-mx70-l2/coverage_manifest.json`. The manifest declares `source_id='resourcesat-2a-liss4-mx70-l2'` and `collection='ResourceSat-2A_LISS4-MX70_L2'`.
- TASK-020 evidence: on `akasha-staging`, `python worker.py bhoonidhi-download --source resourcesat-2a-liss4-mx70-l2 --manifest /srv/akasha/data/work/bhoonidhi/resourcesat-2a-liss4-mx70-l2/coverage_manifest.json --max-downloads 1` completed with `downloaded 1 product(s)` and wrote `/srv/akasha/data/work/bhoonidhi/resourcesat-2a-liss4-mx70-l2/download_manifest.json`. The downloaded ZIP `/srv/akasha/data/raw/bhoonidhi/resourcesat-2a-liss4-mx70-l2/RAF06MAY2026048841009900063SSANSTUC00GTDD.zip` is non-zero at `650898903` bytes.
- TASK-021/TASK-022 evidence: product inspection is recorded in `test_reports/liss4-validation-2026-06-23.md`. The inspected ZIP contains `BAND2.tif`, `BAND3.tif`, `BAND4.tif`, `BAND_META.txt`, and product `.meta`; no `BAND5.tif` exists. Rasterio opened all three bands as EPSG:32643 uint16 rasters, size `17761x16588`, one band each, no native nodata tag, 5.0 m output resolution, and raster tags `scales=(1.0,)`, `offsets=(0.0,)`. Metadata lists `InputResolutionAlong/Across=5.80`, `OutputResolutionAlong/Across=5.00`, and no explicit alternate reflectance multiplier/offset. No code change was made for scale/offset; Akasha continues applying the source-profile correction `dn * 0.0001 + 0.0`.
- TASK-023 failed-attempt evidence: before the safe-wrapper rule was enforced, a default LISS-4 sync for the current 45-day window completed without new candidates and skipped composite rebuild. A May 2026 window found one candidate and ran through search/download/prepare but failed verification because coverage was `1.5147%`, below the required `10.0%`. A broader `2026-01-01..2026-02-28` window found 8 candidates, downloaded 3 new products, and prepared scene COGs, but the session was terminated after no final composite/ingest/verify output appeared. After termination, SSH to `akasha-staging` timed out during banner exchange.
- TASK-023 heavy-build incident evidence: SSH recovered after VM restart (`akasha-staging`, egress `20.219.3.35`, low load, all core containers healthy). Inspection showed no running ingestion worker, a stale `/srv/akasha/ingestion/ledger.sqlite.lock` from `2026-06-23T05:15:37Z`, prepared LISS-4 scene manifests for `2026-01-16`, `2026-02-04`, `2026-02-28`, and no Jan/Feb LISS-4 composite manifest. A manual direct `worker.py build-composite --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --manifest-glob "/app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/scene/*/*/prepare_manifest.json" --output-root /app/data/seed/rasters/resourcesat-2a-liss4-mx70-l2 --window-start 2026-01-01 --window-end 2026-02-28 --overwrite` was launched to build from already prepared scene manifests. During the build, SSH again timed out during banner exchange and Azure later reported the VM stopped. This confirms broad/direct high-resolution composite builds are unsafe on staging and must not be repeated; subsequent Phase 3 work used only `scripts/staging_ingestion_job.py trigger --host akasha-staging ...`.
- TASK-023 safe-wrapper completion evidence: after enforcing the safe wrapper-only rule, `python scripts/staging_ingestion_job.py doctor --host akasha-staging` passed and a bounded LISS-4 job was submitted with `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --window-start 2026-01-30 --window-end 2026-01-30 --window-days 1 --limit 100 --max-downloads 3 --min-coverage-percent 10 --overwrite --notes "Phase 3 bounded Jan30 LISS-4 validation via safe wrapper only" --wait --wait-interval 15 --wait-timeout 1800`. Job `ingest-20260623T102407Z-cfe24deb` completed with state `succeeded`, `exit_code=0`, and message `worker completed`. The job log shows `found 2 Bhoonidhi item(s)`, `selected 2 candidate(s)`, `skipped existing 2 product(s)`, `new products 0`, `sync window: 2026-01-30..2026-01-30`, rebuilt the Jan 30 analytic/mask composite, reported `composite verification passed (22 checks)`, ensured bucket `akasha-cogs`, skipped existing uploaded analytic/mask objects, loaded `1 manifest item(s) (method=upsert)`, and completed post-ingest validation with `composite verification passed (23 checks)`. The wrapper `validate <job_id>` subcommand printed `no composite produced; nothing to validate` because its result discovery currently looks under the work/temp tree while this source writes final composites under `/app/data/seed/rasters`; the authoritative job log and exit code prove the worker completed the full sync/ingest/post-ingest verification path.
- TASK-024/TASK-025/TASK-026 evidence: LISS-4 systemd artifacts already exist under `infra/selfhosted/systemd/` and are covered by `tests/test_bhoonidhi_systemd_artifacts.py`; `python -m pytest tests/test_bhoonidhi_systemd_artifacts.py -q` completed with `4 passed in 2.77s`.
- TASK-027 evidence: because the deployed repo copy on staging did not contain the LISS-4 installer, the LISS-4 systemd package was copied from the local workspace to `/tmp/akasha-liss4-systemd`, normalized to LF line endings, dry-run installed successfully, then installed and enabled on `akasha-staging`. A safe one-shot service run was executed with `AKASHA_SYNC_DRY_RUN=true`; journal output showed `Akasha Bhoonidhi LISS-4 sync: source=resourcesat-2a-liss4-mx70-l2 aoi=bangalore-60km ...`, found 0 candidates for the current 30-day window, and exited successfully with `dry-run: stopping before download/prepare/composite/ingest`. The timer is enabled and active with next trigger `Fri 2026-06-26 03:40:08 UTC`; `/etc/akasha/bhoonidhi-liss4-sync.env` was set back to `AKASHA_SYNC_DRY_RUN=false` after the validation run so future scheduled runs are not disabled.
- TASK-028 partial evidence: direct HTTP inside the production API container returned `401 Unauthorized`, as expected for the protected deployed API route without a browser/session. The deployed BFF catalog resolver was validated inside the API container and returned the LISS-4 date `2026-01-30` with `tileAvailable=true`, `coveragePercent=17.77`, `metricsProvisional=true`, and bounds covering the Jan 30 composite. Keep the formal TASK-028 route smoke open until an authenticated gateway/API check is run after TASK-023 completes.
- TASK-029 partial evidence: the deployed best-resolution resolver was validated inside the API container for an NDVI field geometry inside LISS-4 coverage with `primary_source_id=resourcesat-2a-liss3-boa`, `acquisition_date=2026-01-30`, `prefer_high_res=True`, and `window_days=60`; it returned `ResolutionResult(source_id='resourcesat-2a-liss4-mx70-l2', resolution_meters=5.8, enhanced=True, basis_date='2026-01-30', provenance_note=None)`. Keep the formal TASK-029 statistics/overlay smoke open until an authenticated deployed route check is run after TASK-023 completes.
- TASK-028 evidence: authenticated deployed BFF dates smoke used a temporary staging smoke user created inside the API container with a random password that was not printed, then cleaned up after the test. `GET /api/sources/resourcesat-2a-liss4-mx70-l2/dates` returned HTTP 200 and included `acquisitionDate=2026-01-30`, `tileAvailable=True`, `coveragePercent=17.77`, and `metricsProvisional=True`.
- TASK-029 evidence: authenticated deployed BFF field analytics smoke created a temporary field inside the LISS-4 coverage footprint, then cleaned it up after the test. `POST /api/fields/{fieldId}/indices/statistics` with `sourceId=resourcesat-2a-liss3-boa`, `acquisitionDate=2026-01-30`, `indexType=NDVI`, and `preferHighRes=True` returned HTTP 200 with `resolvedSourceId=resourcesat-2a-liss4-mx70-l2`, `enhanced=True`, `resolutionMeters=5.8`, and `basisDate=2026-01-30`. `GET /api/fields/{fieldId}/overlay/NDVI.png?sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-01-30&preferHighRes=true` returned HTTP 200 with a non-empty PNG (`365` bytes) and provenance headers `resolvedSourceId=resourcesat-2a-liss4-mx70-l2`, `enhanced=true`, `resolutionMeters=5.8`, and `basisDate=2026-01-30`.
- TASK-030 evidence: after TASK-018, TASK-023, TASK-028, and TASK-029 passed, `apps/api/app/raster/catalog_resolver.py` was updated to set LISS-4 `availabilityStatus="active"` and `gatedReason=None`. `docs/data-ingestion-and-satellite-rules.md` now labels LISS-4 `Active: high-resolution field enhancement for NDVI/MSAVI/NDWI_GREEN_NIR with LISS-3 fallback`, and `docs/reference/satellite-ingestion-onboarding-matrix.md` now identifies LISS-4 as active field enhancement. TDD red evidence: `python -m pytest tests/test_product_sources.py tests/test_slice2.py::test_sources_endpoint_contract -q` failed before the registry change because LISS-4 was still `gated`. Verification evidence after the registry/docs change: `python -m pytest tests/test_product_sources.py tests/test_slice2.py::test_sources_endpoint_contract tests/test_best_resolution_resolver.py -q` completed with `25 passed, 15 warnings in 3.11s`; warnings are existing Pydantic `UnsupportedFieldAttributeWarning` warnings in `test_best_resolution_resolver.py`.

### Implementation Phase 4 — AWiFS source-profile completion

- GOAL-005: Move AWiFS from registry scaffold to fully source-aware prepare/composite/STAC support with clear regional semantics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-031 | In `services/ingestion/akasha_ingest/pipeline_registry.py`, verify `resourcesat-2a-awifs-boa` has `provider="bhoonidhi"`, `collection_id="ResourceSat-2A_AWIFS_BOA"`, `prepare_script="prepare_resourcesat_liss3_boa_cogs.py"`, `supports_search=True`, `supports_download=True`, `supports_composite=True`, `mvp_enabled=True`, `default_min_coverage_percent=95.0`, and `output_profile="resourcesat-awifs-boa"`. | | |
| TASK-032 | In `services/ingestion/akasha_ingest/bhoonidhi.py`, verify `SOURCE_COLLECTIONS["resourcesat-2a-awifs-boa"] == "ResourceSat-2A_AWIFS_BOA"`. Add a test if this mapping is not already asserted. | | |
| TASK-033 | In `scripts/prepare_resourcesat_liss3_boa_cogs.py`, verify `SOURCE_PROFILES["resourcesat-2a-awifs-boa"]` has `label="AWiFS"`, `resolution_meters=56`, `analytic_bands=LISS3_ANALYTIC_BANDS`, `reflectance_scale=0.0001`, `reflectance_offset=0.0`, `mask_builder="4band"`, and an AWiFS-specific `mask_method` string. | | |
| TASK-034 | Add `tests/test_prepare_resourcesat_awifs_boa_cogs.py`. Build synthetic four-band AWiFS inputs named `BAND2.tif`, `BAND3.tif`, `BAND4.tif`, `BAND5.tif`; run the prepare script with `--source resourcesat-2a-awifs-boa`; assert the output manifest has 4 bands, `resolution_meters=56`, source ID `resourcesat-2a-awifs-boa`, collection `ResourceSat-2A_AWIFS_BOA`, and mask classes `{0,1,2,3,4}`. | | |
| TASK-035 | Run `python -m pytest tests/test_prepare_resourcesat_awifs_boa_cogs.py -q`. Expected result: AWiFS synthetic prepare test passes. If raster dependencies are unavailable on the host, run the test inside the ingestion container and record the command in the plan execution notes. | | |
| TASK-036 | In `services/ingestion/akasha_ingest/composite.py`, verify `SOURCE_PROFILES["resourcesat-2a-awifs-boa"]` uses `resolution=56.0`, `analytic_band_order=["BAND2","BAND3","BAND4","BAND5"]`, and the four-band ResourceSat role mapping. Add a composite unit test that AWiFS produces a 56 m composite grid and preserves 4 analytic bands. | | |
| TASK-037 | In `services/ingestion/akasha_ingest/catalog.py`, verify `RESOURCESAT_BOA_SOURCE_META[config.RESOURCESAT_AWIFS_COLLECTION_ID]` has `instrument="awifs"`, `label="AWiFS"`, and `default_gsd=56`. If AWiFS-specific center wavelengths are known from NRSC metadata, replace the current LISS-3 EO-band alias with AWiFS-specific EO-band metadata; if not known, keep LISS-3 EO-band metadata and document the assumption in `limitations`. | | |
| TASK-038 | Add `tests/test_bhoonidhi_ingestion.py::test_catalog_emits_awifs_resourcesat_item`. Use an AWiFS composite manifest and assert collection `resourcesat-2a-awifs-boa`, instruments `["awifs"]`, 4 analytic EO bands, 4 raster bands, asset hrefs under `s3://akasha-cogs/resourcesat-2a-awifs-boa/composite/bangalore-60km/{date}/`, `akasha:band_role_mapping` includes SWIR1, and `gsd == 56`. | | |

### Implementation Phase 5 — AWiFS BFF, STAC seed, and frontend visibility

- GOAL-006: Make AWiFS visible as a properly described regional source while keeping it gated until staging verification succeeds.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-039 | In `apps/api/app/raster/catalog_resolver.py`, verify the AWiFS `_SOURCE_REGISTRY` entry has `availabilityStatus="gated"` and `gatedReason="No validated AWiFS BOA composite has been ingested."` until TASK-049 passes. Set `analysisLevel="regional"`, `resolutionMeters=56`, `supportedIndices=["NDVI","MSAVI","NDMI","NDWI_GREEN_NIR"]`, `displayModes=["FCC","NDVI","MSAVI","NDMI","NDWI_GREEN_NIR"]`, `mapDisplayModes=["NDVI","MSAVI","NDMI","NDWI_GREEN_NIR"]`, and `defaultDisplayMode="FCC"`. Add source limitations from TASK-040 so the UI exposes AWiFS as regional/coarse even though index display modes are available. | | |
| TASK-040 | In `apps/api/app/raster/catalog_resolver.py`, set AWiFS `limitations` to include exactly these meanings: `Coarse 56 m pixels; use for regional context and large-field analytics.`, `Mask is Akasha threshold-derived and provisional until a native quality layer exists.`, and `Not a replacement for LISS-3/LISS-4 field-level monitoring.` | | |
| TASK-041 | Update `data/seed/stac/resourcesat-2a-awifs-boa-collection.json` to match the BFF registry: `id="resourcesat-2a-awifs-boa"`, `akasha:bhoonidhi_collection_id="ResourceSat-2A_AWIFS_BOA"`, `akasha:analysis_level="regional"`, `akasha:display_modes`, `akasha:default_display_mode="FCC"`, `akasha:supported_indices`, 4-band EO metadata, reflectance scale/offset, and mask class metadata. | | |
| TASK-042 | Do not add a checked-in AWiFS sample item for production seed loading. If API tests require an AWiFS sample item, define the sample STAC item as an in-test Python dictionary fixture inside the relevant test file and assert `config.item_files("resourcesat-2a-awifs-boa") == []` until manifest-derived items exist under `data/seed/stac/items/resourcesat-2a-awifs-boa/`. | | |
| TASK-043 | Add or update BFF source tests asserting `/api/sources` returns AWiFS as `availabilityStatus="gated"`, `analysisLevel="regional"`, `resolutionMeters=56`, and the exact gated reason `No validated AWiFS BOA composite has been ingested.` before TASK-049 passes. In TASK-053, update the same test to assert `availabilityStatus="active"` and `gatedReason is None` after AWiFS activation. | | |
| TASK-044 | In `apps/frontend/src/components/layers/SourceCard.tsx` and `SourceMetadata.tsx`, verify gated regional sources render the gated badge, regional analysis label, limitations, and gated reason. Add a Vitest test if AWiFS-specific regional copy is not covered by existing EOS-06/Cartosat gated tests. | | |
| TASK-045 | Run frontend source card tests from `apps/frontend`: `yarn test SourceCard SourceMetadata`. Expected result: gated AWiFS/regional source UI behavior passes. If the repo uses `corepack yarn`, run `corepack yarn test SourceCard SourceMetadata`. | | |

### Implementation Phase 6 — AWiFS staging dry-run, capped real run, and activation

- GOAL-007: Execute the AWiFS pipeline from Bhoonidhi on `akasha-staging`, verify product structure and COG outputs, ingest manifest-derived STAC items, and activate AWiFS only after verification succeeds.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-046 | On `akasha-staging`, run `python worker.py bhoonidhi-search --source resourcesat-2a-awifs-boa --aoi bangalore-60km --lookback-days 120 --limit 100`. Acceptance: command exits 0, writes a coverage manifest, and selected candidates come from `ResourceSat-2A_AWIFS_BOA`. | | |
| TASK-047 | On `akasha-staging`, run `python worker.py bhoonidhi-download --source resourcesat-2a-awifs-boa --manifest /srv/akasha/data/work/bhoonidhi/resourcesat-2a-awifs-boa/coverage_manifest.json --max-downloads 1`. Acceptance: one non-zero-byte AWiFS ZIP is downloaded under `/srv/akasha/data/raw/bhoonidhi/resourcesat-2a-awifs-boa/`. | | |
| TASK-048 | Inspect the downloaded AWiFS product with `gdalinfo` or rasterio. Acceptance: product has `BAND2`, `BAND3`, `BAND4`, `BAND5`; dtype is uint16 or documented equivalent; CRS and dimensions are recorded; scale/offset/background are recorded; no native quality mask is required for pipeline success. Store findings in `test_reports/awifs-validation-YYYY-MM-DD.md`. | | |
| TASK-049 | On `akasha-staging`, run `python worker.py bhoonidhi-sync --source resourcesat-2a-awifs-boa --aoi bangalore-60km --max-downloads 3 --min-coverage-percent 95 --method upsert`. Acceptance: search, download, prepare, composite, upload, STAC registration, and post-ingest `verify-composite` complete with exit code 0. If the first run has insufficient cloud-free coverage, keep AWiFS gated and run another window; do not reduce the threshold below 95 without documenting why the regional source still meets launch needs. | | |
| TASK-050 | Run `GET /api/sources/resourcesat-2a-awifs-boa/dates` against the deployed BFF. Acceptance: after TASK-049 passes, the response contains at least one date with `tileAvailable=true`, `coveragePercent >= 95`, and `metricsProvisional=true`. | | |
| TASK-051 | Run tile smoke for AWiFS FCC through the gateway using a same-origin route: `/api/tiles/resourcesat-2a-awifs-boa/{acquisitionDate}/FCC/{z}/{x}/{y}.png`. Acceptance: HTTP 200 for a tile inside AOI coverage and no direct MinIO/TiTiler URL exposed to the browser. | | |
| TASK-052 | Run a statistics smoke test for a large field or AOI-sized polygon using `sourceId=resourcesat-2a-awifs-boa` and `indexType=NDVI`. Acceptance: response includes valid statistics, source ID AWiFS, regional limitations remain visible in `/api/sources`, and no NDRE/RECI support is advertised. | | |
| TASK-053 | Flip AWiFS to active only after TASK-049, TASK-050, TASK-051, and TASK-052 pass. In `apps/api/app/raster/catalog_resolver.py`, set `availabilityStatus="active"`, `gatedReason=None`, keep `analysisLevel="regional"`, keep limitations, and keep `metricsProvisional=true`. Update `docs/data-ingestion-and-satellite-rules.md` and `docs/reference/satellite-ingestion-onboarding-matrix.md` with the validation date and acceptance evidence. | | |

### Implementation Phase 7 — AWiFS scheduler and monitoring

- GOAL-008: Give AWiFS its own operational cadence, verification checks, and monitoring visibility.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-054 | Add `infra/selfhosted/systemd/akasha-bhoonidhi-awifs-sync.timer`, `akasha-bhoonidhi-awifs-sync.service`, `akasha-bhoonidhi-awifs-sync.sh`, and `bhoonidhi-awifs-sync.env.example`. The wrapper must pass `--source resourcesat-2a-awifs-boa`, use lock names containing `awifs`, and set default `AKASHA_SYNC_WINDOW_DAYS=45` unless staging evidence supports a shorter regional composite window. | | |
| TASK-055 | Extend `tests/test_bhoonidhi_systemd_artifacts.py` to assert AWiFS systemd artifacts exist, reference `resourcesat-2a-awifs-boa`, use AWiFS-specific locks, and do not modify LISS-3 or LISS-4 service names. | | |
| TASK-056 | Run `python -m pytest tests/test_bhoonidhi_systemd_artifacts.py -q`. Expected result: LISS-3, LISS-4, and AWiFS systemd artifact tests pass. | | |
| TASK-057 | Extend monitoring source health so AWiFS appears in the monitoring view with `analysisLevel="regional"`, latest successful composite date, tile availability reasons, and last failure reason. Use existing monitoring API patterns rather than a new endpoint. | | |
| TASK-058 | Add a monitoring test in `apps/frontend/src/pages/monitoring/MonitoringGlobalView.test.tsx` or the corresponding backend monitoring test to assert active AWiFS contributes to source health after activation and gated AWiFS is excluded from active-source rollups before activation. | | |

### Implementation Phase 8 — Regression suite and release gate

- GOAL-009: Prove LISS-3 still works, LISS-4 is productionized, and AWiFS is complete before moving to the next satellite integration.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-059 | Run Python static/unit tests from repo root: `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py tests/test_bhoonidhi_systemd_artifacts.py -q`. Expected result: all selected ingestion tests pass. | | |
| TASK-060 | Run BFF tests from `apps/api`: `python -m pytest tests/test_best_resolution_resolver.py tests/test_field_analytics.py tests/test_field_exports.py -q`. Expected result: LISS-4 provenance, LISS-3 fallback, and field analytics tests pass. | | |
| TASK-061 | Run frontend tests from `apps/frontend`: `corepack yarn test` or `yarn test` depending on the environment. Expected result: source card, monitoring, map legend, and index panel tests pass. | | |
| TASK-062 | Run lint/type checks where available: `ruff check apps/api services/ingestion scripts`, `cd apps/frontend && corepack yarn lint`, and `cd apps/frontend && corepack yarn build`. Expected result: zero new lint/type/build failures caused by this plan. | | |
| TASK-063 | On `akasha-staging`, run source-specific verification commands for all three ResourceSat variants: LISS-3 `verify-composite --min-coverage-percent 95`, LISS-4 `verify-composite --min-coverage-percent 10`, AWiFS `verify-composite --min-coverage-percent 95`. Expected result: each active source returns `composite verification passed`; any failing source remains gated. | | |
| TASK-064 | Update `test_reports/` with a dated ResourceSat productionization report listing commands, exit codes, source IDs, composite dates, coverage percentages, usable pixel percentages, and known limitations. | | |
| TASK-065 | Only after TASK-063 passes for active sources, proceed to the next satellite integration plan. The recommended next plan is CDSE Sentinel-2 because the repo already has Sentinel-2 prepare scripts and registry scaffolding; the missing piece is the `cdse` provider client and generic non-ISRO orchestration. | | |

## 3. Alternatives

- **ALT-001**: Activate AWiFS immediately because registry rows already exist. Rejected because no validated AWiFS composite, COG manifest, or pgSTAC item was found during audit, and `catalog_resolver.py` explicitly marks AWiFS gated.
- **ALT-002**: Treat LISS-4 as already productionised because local `analytic.tif`, `mask.tif`, and `prepare_manifest.json` exist. Rejected because docs still classify LISS-4 as gated, the seed sample item date differs from the local prepared composite date, and production readiness must be proven against pgSTAC and MinIO on the target environment.
- **ALT-003**: Merge LISS-3, LISS-4, and AWiFS into one ResourceSat source ID. Rejected because each instrument has different resolution, band availability, coverage, index support, and user-facing limitations. Separate STAC collections and source IDs preserve provenance and prevent invalid index requests.
- **ALT-004**: Use one systemd timer to sync all ResourceSat variants. Rejected because LISS-3, LISS-4, and AWiFS have different cadence, coverage, thresholds, and failure modes. Separate timers make operations safer.
- **ALT-005**: Make AWiFS field-level by default to match LISS-3/LISS-4 UI. Rejected because 56 m pixels are coarse for many farm fields. The source can compute indices, but the product must label it regional.
- **ALT-006**: Wait to start AWiFS until the next satellite integration is complete. Rejected because the user explicitly requested finishing AWiFS after LISS-4 productionization before proceeding further.

## 4. Dependencies

- **DEP-001**: `akasha-staging` VM with egress IP `20.219.3.35`, Bhoonidhi IP allow-list approval, Docker stack access, `/srv/akasha` storage, and running web/api/stac-api/titiler/postgis/minio services.
- **DEP-002**: Bhoonidhi credentials configured as deployment secrets on `akasha-staging`: `BHOONIDHI_USER_ID` and `BHOONIDHI_PASSWORD`.
- **DEP-003**: Object storage settings available to the ingestion worker: `AKASHA_COG_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_REGION` when required by the S3 client.
- **DEP-004**: Catalog settings available to the ingestion worker: `DATABASE_URL` and `STAC_API_URL`.
- **DEP-005**: AOI configuration available on staging: `AOI_CONFIG_PATH=/app/data/seed/bangalore-60km-aoi.geojson`. If `AOI_CONFIG_DIR` is used in addition to `AOI_CONFIG_PATH`, it must contain a selectable `bangalore-60km` AOI file.
- **DEP-006**: Raster dependencies available in the ingestion runtime: GDAL, rasterio, rio-cogeo, numpy, and pyproj-compatible CRS transformation support.
- **DEP-007**: Existing LISS-3 production composite remains available and verified as the fallback source for field analytics.
- **DEP-008**: Existing frontend data-driven source components continue to consume `/api/sources` without source-specific hard-coded COG URLs.

## 5. Files

- **FILE-001**: `docs/impl-plan/data-resourcesat-liss4-awifs-productionization-1.md` — This plan; source-state, tasks, gates, tests, risks, and acceptance criteria.
- **FILE-002**: `docs/data-ingestion-and-satellite-rules.md` — Source-of-truth source statuses, ResourceSat band/mask rules, production activation evidence.
- **FILE-003**: `docs/reference/satellite-ingestion-onboarding-matrix.md` — Updated ResourceSat variant verdicts and onboarding status.
- **FILE-004**: `services/ingestion/akasha_ingest/pipeline_registry.py` — LISS-4/AWiFS pipeline metadata and thresholds.
- **FILE-005**: `services/ingestion/akasha_ingest/bhoonidhi.py` — Bhoonidhi source-to-collection mappings.
- **FILE-006**: `services/ingestion/akasha_ingest/config.py` — ResourceSat BOA source IDs, manifest discovery, seed item loading behavior.
- **FILE-007**: `scripts/prepare_resourcesat_liss3_boa_cogs.py` — Source profiles for LISS-3, LISS-4, AWiFS; band order; scale/offset; mask builders; output manifests.
- **FILE-008**: `services/ingestion/akasha_ingest/composite.py` — Source-specific composite profiles, resolution, band count, mask validation, `verify_composite_manifest()`.
- **FILE-009**: `services/ingestion/akasha_ingest/catalog.py` — ResourceSat STAC item generation, EO bands, raster bands, mask classes, source metadata.
- **FILE-010**: `services/ingestion/akasha_ingest/scene.py` — ResourceSat scene/composite item IDs and S3 object key prefixes.
- **FILE-011**: `services/ingestion/worker.py` — Source-aware search/download/sync/build/verify commands and thresholds.
- **FILE-012**: `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.timer` — LISS-4 scheduled ingestion timer.
- **FILE-013**: `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.service` — LISS-4 scheduled ingestion service.
- **FILE-014**: `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.sh` — LISS-4 scheduled ingestion wrapper.
- **FILE-015**: `infra/selfhosted/systemd/bhoonidhi-liss4-sync.env.example` — LISS-4 scheduled ingestion environment template.
- **FILE-016**: `infra/selfhosted/systemd/akasha-bhoonidhi-awifs-sync.timer` — AWiFS scheduled ingestion timer.
- **FILE-017**: `infra/selfhosted/systemd/akasha-bhoonidhi-awifs-sync.service` — AWiFS scheduled ingestion service.
- **FILE-018**: `infra/selfhosted/systemd/akasha-bhoonidhi-awifs-sync.sh` — AWiFS scheduled ingestion wrapper.
- **FILE-019**: `infra/selfhosted/systemd/bhoonidhi-awifs-sync.env.example` — AWiFS scheduled ingestion environment template.
- **FILE-020**: `data/seed/stac/resourcesat-2a-liss4-mx70-l2-collection.json` — LISS-4 STAC collection metadata.
- **FILE-021**: `data/seed/stac/resourcesat-2a-liss4-mx70-l2-sample-item.json` — LISS-4 contract scaffold only; production comes from manifest ingestion.
- **FILE-022**: `data/seed/stac/resourcesat-2a-awifs-boa-collection.json` — AWiFS STAC collection metadata.
- **FILE-023**: `data/seed/stac/items/resourcesat-2a-awifs-boa/` — Manifest-derived AWiFS STAC items may be generated or loaded here by explicit ingest workflows; do not create a production seed sample item for AWiFS.
- **FILE-024**: `apps/api/app/raster/catalog_resolver.py` — BFF source registry, source payload, date listing, supported indices, best-resolution resolver.
- **FILE-025**: `apps/api/app/raster/indices.py` — Centralized band role to position and index expression logic; no new hard-coded positions elsewhere.
- **FILE-026**: `apps/api/app/raster/service.py` — Verify and update source-aware statistics service behavior for AWiFS activation and LISS-4 fallback semantics.
- **FILE-027**: `apps/api/app/routers/product_router.py` or current product router path — Verify and update source/dates/tile route behavior for LISS-4 and AWiFS activation fields.
- **FILE-028**: `apps/api/app/routers/analytics_router.py` — Verify and update field statistics, overlay, and point responses for LISS-4 provenance and AWiFS regional behavior.
- **FILE-029**: `apps/frontend/src/types/api.ts` — Source availability, analysis level, provenance, and regional-source types.
- **FILE-030**: `apps/frontend/src/components/layers/SourceCard.tsx` — Gated/active source rendering and limitations display.
- **FILE-031**: `apps/frontend/src/components/layers/SourceMetadata.tsx` — Field/regional/gated source labels.
- **FILE-032**: `apps/frontend/src/pages/monitoring/MonitoringGlobalView.tsx` — Active/gated source health rollups.
- **FILE-033**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` — LISS-4 enhancement badge and NDMI fallback copy if route provenance changes are needed.
- **FILE-034**: `apps/frontend/src/components/map/Legend.tsx` — Resolved source/resolution display for LISS-4-enhanced overlays.
- **FILE-035**: `tests/test_pipeline_registry.py` — Pipeline registry assertions for ResourceSat source metadata.
- **FILE-036**: `tests/test_bhoonidhi_ingestion.py` — Bhoonidhi source mapping and STAC item-generation tests.
- **FILE-037**: `tests/test_bhoonidhi_systemd_artifacts.py` — Systemd artifact tests for LISS-3, LISS-4, AWiFS.
- **FILE-038**: `tests/test_prepare_resourcesat_awifs_boa_cogs.py` — New AWiFS prepare synthetic raster test.
- **FILE-039**: `tests/test_prepare_resourcesat_liss4_mx70_l2_cogs.py` — New or updated LISS-4 prepare synthetic raster test covering the 3-band path.
- **FILE-040**: `apps/api/tests/test_best_resolution_resolver.py` — LISS-4 high-resolution resolver tests.
- **FILE-041**: `apps/api/tests/test_product_sources.py` — Source payload status and metadata tests.
- **FILE-042**: `apps/frontend/src/components/layers/SourceCard.test.tsx` — Frontend source status/limitations tests.
- **FILE-043**: `apps/frontend/src/pages/monitoring/MonitoringGlobalView.test.tsx` — Frontend monitoring source health tests.
- **FILE-044**: `test_reports/` — Dated staging validation reports for LISS-4 and AWiFS.

## 6. Testing

- **TEST-001**: Static ingestion registry test: `python -m pytest tests/test_pipeline_registry.py -q`. Verifies LISS-3, LISS-4, AWiFS source IDs, provider, collection IDs, prepare script names, and enabled flags.
- **TEST-002**: Bhoonidhi source mapping test: `python -m pytest tests/test_bhoonidhi_ingestion.py::test_source_collection_supports_liss4_phase_a_source tests/test_bhoonidhi_ingestion.py::test_source_collection_supports_awifs_phase5_source -q`. Verifies source IDs map to Bhoonidhi collection IDs.
- **TEST-003**: LISS-4 STAC generation test: `python -m pytest tests/test_bhoonidhi_ingestion.py::test_catalog_emits_manifest_derived_liss4_composite_item -q`. Verifies manifest-derived composite item ID, 3 bands, instrument, role mapping, and S3 asset hrefs.
- **TEST-004**: AWiFS STAC generation test: `python -m pytest tests/test_bhoonidhi_ingestion.py::test_catalog_emits_awifs_resourcesat_item -q`. Verifies AWiFS item metadata, 4 bands, SWIR1 role, regional resolution, and S3 asset hrefs.
- **TEST-005**: LISS-4 synthetic prepare test: `python -m pytest tests/test_prepare_resourcesat_liss4_mx70_l2_cogs.py -q`. Verifies 3-band COG + mask output and manifest metadata.
- **TEST-006**: AWiFS synthetic prepare test: `python -m pytest tests/test_prepare_resourcesat_awifs_boa_cogs.py -q`. Verifies 4-band COG + mask output and manifest metadata.
- **TEST-007**: Composite profile test: extend existing ResourceSat composite tests to cover LISS-3 24 m, LISS-4 5.8 m, and AWiFS 56 m output grids with correct band counts and mask classes.
- **TEST-008**: Systemd artifact test: `python -m pytest tests/test_bhoonidhi_systemd_artifacts.py -q`. Verifies LISS-4 and AWiFS unit files, source IDs, lock names, and env examples.
- **TEST-009**: BFF source payload test: from `apps/api`, run `python -m pytest tests/test_product_sources.py -q`. Verifies active/gated states, analysis levels, supported indices, limitations, and source labels.
- **TEST-010**: Best-resolution resolver test: from `apps/api`, run `python -m pytest tests/test_best_resolution_resolver.py -q`. Verifies LISS-4 preference for supported indices, LISS-3 fallback, and NDMI fallback.
- **TEST-011**: Field analytics regression test: from `apps/api`, run `python -m pytest tests/test_field_analytics.py tests/test_field_exports.py -q`. Verifies source-aware stats/export paths do not regress.
- **TEST-012**: Frontend source UI test: from `apps/frontend`, run `corepack yarn test SourceCard SourceMetadata`. Verifies active LISS-4, gated/active AWiFS, regional labels, limitations, and gated reasons.
- **TEST-013**: Frontend monitoring test: from `apps/frontend`, run `corepack yarn test MonitoringGlobalView`. Verifies active/gated source rollups.
- **TEST-014**: Frontend build: from `apps/frontend`, run `corepack yarn build`. Verifies TypeScript and Vite build remain healthy.
- **TEST-015**: Python lint: from repo root, run `ruff check apps/api services/ingestion scripts`. Verifies no new lint failures.
- **TEST-016**: LISS-3 deployment verification: on staging, run `python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --min-coverage-percent 95 --require-catalog-item`.
- **TEST-017**: LISS-4 deployment verification: on staging, run `python worker.py verify-composite --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --min-coverage-percent 10 --require-catalog-item`.
- **TEST-018**: AWiFS deployment verification: on staging, run `python worker.py verify-composite --source resourcesat-2a-awifs-boa --aoi bangalore-60km --min-coverage-percent 95 --require-catalog-item`.
- **TEST-019**: BFF smoke after activation: call `/api/sources`, `/api/sources/resourcesat-2a-liss4-mx70-l2/dates`, `/api/sources/resourcesat-2a-awifs-boa/dates`, one FCC tile route per active source, and one statistics route per active source through the gateway.
- **TEST-020**: Regression smoke: run `python scripts/smoke-test.py http://localhost:8080` for the local Docker gateway. For authenticated staging, the operator must export `AKASHA_SMOKE_LOGIN=1`, `AKASHA_SMOKE_USERNAME`, and `AKASHA_SMOKE_PASSWORD` in the deployment shell, then run `python scripts/smoke-test.py http://localhost:8080 --login`; do not commit those values. Acceptance: existing LISS-3 product checks still pass and active LISS-4/AWiFS routes do not return unexpected 5xx responses.

## 7. Risks & Assumptions

- **RISK-001**: LISS-4 is currently structurally active in code while docs classify it as gated. This can confuse users and operators. Mitigation: TASK-007 and TASK-030 force a single explicit state.
- **RISK-002**: The checked-in LISS-4 sample item date and local prepared LISS-4 manifest date may differ. Mitigation: TASK-013 through TASK-018 require manifest-derived STAC registration and verification.
- **RISK-003**: LISS-4 narrow swath can produce partial coverage and low usable pixels. Mitigation: keep LISS-3 fallback, use min coverage threshold 10 for LISS-4 composite verification, and require field-level coverage checks before high-resolution enhancement.
- **RISK-004**: AWiFS has no validated local composite at the start of this plan. Mitigation: keep AWiFS gated until TASK-049 through TASK-053 pass.
- **RISK-005**: AWiFS-specific spectral metadata may differ slightly from LISS-3 despite shared band names. Mitigation: TASK-037 requires replacing EO metadata if NRSC metadata is available; otherwise limitations document the assumption.
- **RISK-006**: ResourceSat threshold masks are provisional and can misclassify cloud/shadow/water. Mitigation: keep `metricsProvisional=true`, expose `maskMethod`, and preserve mask class statistics for user transparency.
- **RISK-007**: Staging Bhoonidhi downloads may fail due to token/session limits, daily limits, IP allow-list changes, or product offline status. Mitigation: capped downloads, separate locks, retry logic already in the client, and explicit staging validation reports.
- **RISK-008**: Generalizing prepare/composite code for AWiFS could regress LISS-3. Mitigation: run LISS-3 tests and LISS-3 deployment verification before activation.
- **RISK-009**: AWiFS 56 m regional pixels may be misunderstood as field-level precision. Mitigation: keep `analysisLevel="regional"`, source limitations, SourceCard metadata, and monitoring labels.
- **RISK-010**: Adding multiple systemd timers may create operational noise. Mitigation: source-specific env files, logs, lock names, and monitoring rollups make failures attributable.
- **ASSUMPTION-001**: Bhoonidhi collections `ResourceSat-2A_LISS4-MX70_L2` and `ResourceSat-2A_AWIFS_BOA` remain searchable and downloadable from the whitelisted staging VM.
- **ASSUMPTION-002**: LISS-4 and AWiFS raw products use per-band GeoTIFF files compatible with the shared ResourceSat prepare script.
- **ASSUMPTION-003**: Reflectance scale/offset remain `0.0001/0.0` unless staging product metadata proves otherwise.
- **ASSUMPTION-004**: `bangalore-60km` remains the launch AOI and UTM zone 43N remains the operational composite CRS for the AOI.
- **ASSUMPTION-005**: The existing BFF and frontend are sufficiently data-driven that AWiFS activation requires only source metadata, tests, and regional copy unless smoke tests reveal a source-specific gap.

## 8. Related Specifications / Further Reading

- `AGENTS.md` — Repository guardrails, canonical tree, one-public-service rule, ResourceSat band/mask/index rules.
- `docs/data-ingestion-and-satellite-rules.md` — Source-of-truth for imagery, COG layout, STAC metadata, mask classes, index support, and onboarding gates.
- `docs/reference/satellite-ingestion-onboarding-matrix.md` — Source/provider feasibility matrix and ResourceSat variant status.
- `docs/impl-plan/feature-resourcesat-liss4-best-resolution-1.md` — Existing LISS-4 implementation plan; this plan productionises and closes the remaining gate.
- `docs/impl-plan/data-multi-source-ingestion-roadmap-1.md` — Cross-source onboarding roadmap and generic provider orchestration context.
- `docs/impl-plan/isro-bhoonidhi-ingestion-phase-plan.md` — Bhoonidhi ingestion phase plan, staging VM constraints, ResourceSat composite model.
- `docs/staging-ingestion-developer-guide.md` — Bhoonidhi staging execution constraints and whitelisted egress context.
- `infra/selfhosted/README.md` — Self-hosted deployment, staging/Coolify operational commands, and ingestion worker execution patterns.
- `services/ingestion/akasha_ingest/bhoonidhi.py` — Bhoonidhi API client and source collection mappings.
- `scripts/prepare_resourcesat_liss3_boa_cogs.py` — Current shared ResourceSat BOA COG preparation script.
- `services/ingestion/akasha_ingest/composite.py` — ResourceSat composite builder and verifier.
- `services/ingestion/akasha_ingest/catalog.py` — STAC collection/item generation for prepared manifests.
- `apps/api/app/raster/catalog_resolver.py` — BFF source registry, date listing, source payloads, and best-resolution resolver.
- `apps/api/app/raster/indices.py` — Central index registry and band role-to-position translation.
