---
goal: Sentinel-1 GRD SAR Layer Ingestion and Display Pipeline
version: 1.1
date_created: 2026-06-01
last_updated: 2026-06-01
owner: Akasha Engineering
tags: data, ingestion, satellite, sentinel-1, sar, grd, cog, stac, minio, titiler, frontend
---

# Introduction

This implementation plan adds a free/open Sentinel-1 GRD SAR radar layer to Akasha alongside the existing Sentinel-2 L2A optical layer. The first target is the same South India bounding box used for Sentinel-2 production coverage and the current Sentinel-2 acquisition date `2026-04-27`. Because Sentinel-1 pass timing may not exactly match Sentinel-2 acquisition dates, this plan uses the nearest available Sentinel-1 GRD pass within a configurable search window around `2026-04-27`.

The first visual Sentinel-1 layer will be `VV grayscale`: a calibrated, terrain-corrected radar backscatter layer rendered as grayscale. Sentinel-1 is not true-colour optical imagery, has no SCL cloud mask, and must not be used for Sentinel-2 optical indices such as NDVI, NDRE, NDMI, or NDWI_GREEN_NIR.

The first implementation scope is **one selected Sentinel-1 scene validated end-to-end**. The South India bbox remains the discovery target, but full date-level regional coverage may require multiple Sentinel-1 scenes, a mosaic backend, or a pre-mosaicked display COG. Browser rendering must remain one source/date/display-mode tile template; the browser must not manage one raster layer per SAR scene.

The target bounding box is:

| Field | Value |
|-------|-------|
| West | `74.168701` |
| South | `8.085101` |
| East | `81.013184` |
| North | `14.434701` |
| Sentinel-2 reference date | `2026-04-27` |
| Sentinel-1 date policy | nearest available pass within `±7 days` of `2026-04-27` |
| First display mode | `VV_GRAYSCALE` |

## 1. Requirements & Constraints

- **REQ-001**: Add a new source/collection id `sentinel-1-grd` for Sentinel-1 Ground Range Detected SAR products.
- **REQ-002**: Use Copernicus Data Space Ecosystem as the free/open Sentinel-1 data source.
- **REQ-003**: Query CDSE STAC collection `sentinel-1-grd` for products intersecting the target bbox.
- **REQ-004**: Prefer CDSE Sentinel-1 products where `properties.sar:instrument_mode = "IW"`, `properties.product:type = "IW_GRDH_1S"` or another documented `GRDH` product type, and `properties.sar:polarizations` includes `VV`; prefer candidates that also include `VH`.
- **REQ-005**: Search for the nearest available Sentinel-1 pass within `±7 days` around `2026-04-27` by default. Exact-date-only matching is not required for the first implementation.
- **REQ-006**: The downloader must default to dry-run manifest generation and must not download SAFE ZIPs unless an explicit download flag is provided.
- **REQ-007**: The Sentinel-1 downloader manifest must include product id, acquisition datetime, platform, relative orbit, orbit direction, polarization list, bbox overlap, selected product(s), and estimated download size.
- **REQ-008**: Sentinel-1 preprocessing must produce display-ready COGs from GRD products before upload/registration.
- **REQ-009**: The first Sentinel-1 display product must be `VV_GRAYSCALE` using calibrated terrain-corrected backscatter in dB.
- **REQ-010**: Sentinel-1 COG storage must be source-specific and collision-safe. It must not reuse Sentinel-2 `analytic.tif` + `scl.tif` assumptions.
- **REQ-011**: Sentinel-1 STAC metadata must use SAR-specific fields and must not rely on Sentinel-2 `eo:bands` or SCL metadata.
- **REQ-012**: `/api/sources` must return both `sentinel-2-l2a` and `sentinel-1-grd` after Sentinel-1 registration.
- **REQ-013**: Sentinel-1 source metadata must indicate that the source is SAR/radar and has no optical vegetation indices.
- **REQ-014**: The frontend must show Sentinel-1 as a separate source option and must not treat it as true-colour RGB imagery.
- **REQ-015**: The UI must show source-specific explanatory copy for Sentinel-1: `Radar layer · cloud-penetrating · not true colour` or equivalent.
- **REQ-016**: Optical index UI/actions must be hidden or disabled when Sentinel-1 is selected unless SAR-specific metrics are explicitly implemented later.
- **REQ-017**: Sentinel-1 tile serving must remain behind same-origin `/api/*` routes. The browser must never receive MinIO object URLs or credentials.
- **REQ-018**: Source metadata and default layer responses must include display-mode metadata: `displayModes`, `defaultDisplayMode`, and a source/date/display-mode tile URL template. Sentinel-1 must not be routed through a semantically RGB-only API contract.
- **REQ-019**: If a STAC collection explicitly advertises `akasha:supported_indices: []`, the BFF must return an empty list and must not fall back to Sentinel-2 optical indices.
- **REQ-020**: Sentinel-1 date metadata must use SAR-safe semantics: `usablePixelPercent = null`, `cloudMaskedPercent = null`, `coveragePercent` only when computed from footprint/AOI coverage, and `isLatestUsable` meaning latest selectable radar pass rather than cloud-screened optical usability.
- **REQ-021**: The downloader must verify that the selected Sentinel-1 product has an accessible download URL before preprocessing. If a native SAFE ZIP is unavailable, it must record a sanitized manifest warning and stop before SNAP processing unless an explicit fallback mode is implemented.
- **REQ-022**: Local seed STAC fallback and prepared-manifest discovery must be source-aware, not hardcoded to `sentinel-2-l2a` collection/sample item paths.
- **SEC-001**: CDSE credentials must be read only from environment variables, ignored `.env`, or terminal prompt. Credentials must not be written to source, manifests, docs, logs, or chat output.
- **SEC-002**: Internal MinIO, TiTiler, STAC, PostGIS, and API service URLs must remain private and must not be exposed in frontend code.
- **SEC-003**: Error responses for Sentinel-1 processing/rendering failures must use the standard sanitized BFF error envelope.
- **CON-001**: Sentinel-1 is SAR/radar, not optical imagery. It cannot provide true-colour RGB.
- **CON-002**: Sentinel-1 has no SCL cloud classification layer. Cloud masking and usable-pixel logic from Sentinel-2 must not be copied directly.
- **CON-003**: Sentinel-1 products use a different naming pattern, metadata model, and preprocessing chain than Sentinel-2 L2A.
- **CON-004**: Sentinel-1 preprocessing is heavier than Sentinel-2 COG conversion and likely requires ESA SNAP GPT or an equivalent SAR processing stack.
- **CON-005**: Adding SNAP GPT to the existing ingestion image may significantly increase image size; a separate SAR ingestion image may be preferable.
- **CON-006**: Exact Sentinel-1 acquisition on `2026-04-27` may not exist for the target bbox. The implementation must support nearest-pass behavior.
- **CON-007**: CDSE Sentinel-1 STAC uses `product:type` values such as `IW_GRDH_1S`; `sar:product_type` must not be assumed to exist in CDSE STAC responses.
- **CON-008**: CDSE native/compressed Sentinel-1 SAFE ZIP download availability may vary by product age and storage form. The pipeline must validate download availability before promising preprocessing.
- **CON-009**: The South India target bbox is larger than a single Sentinel-1 scene footprint. Full regional display requires multi-scene selection plus mosaic/pre-mosaic support and is not guaranteed by one-scene validation.
- **GUD-001**: Keep Sentinel-1 source-specific quirks behind ingestion/catalog/BFF metadata rather than frontend conditionals where possible.
- **GUD-002**: Preserve the existing Sentinel-2 L2A pipeline and tests while adding Sentinel-1.
- **GUD-003**: Prefer a dry-run manifest and one-scene validation before attempting large regional Sentinel-1 batch ingestion.
- **PAT-001**: Use one STAC collection per satellite/product family: `sentinel-2-l2a` and `sentinel-1-grd`.
- **PAT-002**: Keep frontend layer rendering date/source-based with one raster source/layer per selected date.
- **PAT-003**: Store large generated SAFE ZIPs and COGs outside git; keep them under ignored `data/raw/` and `data/seed/rasters/` paths.
- **PAT-004**: Use source-scoped prepared raster paths for new dynamic products: `data/seed/rasters/{sourceId}/{acquisitionDate}/{orbitOrTileOrUnknown}/{sceneComponent}/...`.

## 2. Implementation Steps

### Implementation Phase 0 — Pre-Implementation Data Contract Validation

- GOAL-000: Validate CDSE Sentinel-1 contracts and choose the exact first-display scope before writing production code.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-079 | Query `https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/queryables` and record that CDSE filtering must use `product:type`, `sar:instrument_mode`, `sar:polarizations`, `sat:relative_orbit`, and `sat:orbit_state`; do not use `sar:product_type` for CDSE STAC search. | | |
| TASK-080 | Run a dry-run STAC search for bbox `[74.168701, 8.085101, 81.013184, 14.434701]` and datetime `2026-04-20T00:00:00Z/2026-05-04T23:59:59Z`; save a sanitized fixture of one candidate STAC item under `data/raw/sentinel-1-grd/stac_candidate_sample.redacted.json` if manual validation is performed. | | |
| TASK-081 | Verify the selected candidate exposes a `Product` asset, an OData product UUID, or a documented CDSE download URL using `https://download.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/$value` or `$zip`; record download URL mode in the dry-run manifest without credentials. | | |
| TASK-082 | Decide and document the first rollout scope as `one-scene-validation`. Full South India date-level display requires a later `mosaic-backend` or `pre-mosaic-display-cog` task and must not be implied by one selected scene. | | |
| TASK-083 | Evaluate whether CDSE `vv`/`vh` STAC assets can provide a temporary display-only fallback. If they are not calibrated terrain-corrected dB outputs suitable for Akasha, record why SNAP-derived `backscatter.tif` remains required. | | |
| TASK-084 | Finalize the BFF tile route contract as `/api/tiles/{sourceId}/{acquisitionDate}/{displayMode}/{z}/{x}/{y}.png`, where Sentinel-2 uses `RGB` and Sentinel-1 uses `VV_GRAYSCALE`. | | |
| TASK-085 | Define the source registry schema fields: `id`, `label`, `provider`, `kind`, `collectionId`, `expectedAssets`, `supportedIndices`, `displayModes`, `defaultDisplayMode`, `description`, `attribution`, `dateMetricsKind`, `defaultRescale`, and `tileRouteMode`. | | |
| TASK-086 | Add an explicit implementation guard: do not start Phase 3 SNAP preprocessing until TASK-081 confirms that a selected SAFE ZIP or equivalent source product is accessible. | | |

### Implementation Phase 1 — Sentinel-1 Source Semantics and Product Decisions

- GOAL-001: Define Sentinel-1 as a separate SAR source with clear product, date, display, and non-index rules.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Confirm collection id `sentinel-1-grd` and display label `Sentinel-1 GRD` in documentation and source registry design. | | |
| TASK-002 | Define first CDSE STAC product filter as `sar:instrument_mode = "IW"`, `product:type = "IW_GRDH_1S"` or a documented `GRDH` equivalent, and `sar:polarizations` containing `VV`; prefer `VV+VH` candidates when available. | | |
| TASK-003 | Define default search window as `2026-04-20T00:00:00Z/2026-05-04T23:59:59Z`, representing `2026-04-27 ± 7 days`. | | |
| TASK-004 | Define first display mode as `VV_GRAYSCALE`, using band 1 `VV` backscatter in dB and grayscale rendering. | | |
| TASK-005 | Define future display modes as deferred: `VH_GRAYSCALE`, `VV_VH_RATIO`, and `SAR_FALSE_COLOR`. | | |
| TASK-006 | Document that Sentinel-1 has no optical indices and must return `supportedIndices: []` until SAR-specific metrics are implemented; explicitly require the BFF not to fall back to global Sentinel-2 indices when the collection advertises an empty list. | | |

### Implementation Phase 2 — Sentinel-1 GRD Downloader

- GOAL-002: Create a dry-run-first downloader for free/open Sentinel-1 GRD products from CDSE.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Create `scripts/download_sentinel1_grd_product.py` by reusing safe patterns from `scripts/download_sentinel2_l2a_product.py`: `.env` loading, CDSE credential handling, STAC search, OData product detail lookup, manifest writing, and opt-in download. | | |
| TASK-008 | Set `COLLECTION_ID = "sentinel-1-grd"` in `scripts/download_sentinel1_grd_product.py`. | | |
| TASK-009 | Add `BBOX_PRESETS["south-india-target"] = [74.168701, 8.085101, 81.013184, 14.434701]` to the Sentinel-1 downloader. | | |
| TASK-010 | Implement `default_datetime_range(reference_date: date = date(2026, 4, 27), window_days: int = 7) -> str` returning `2026-04-20T00:00:00Z/2026-05-04T23:59:59Z` by default. | | |
| TASK-011 | Implement STAC search payload that requests fields: `id`, `collection`, `bbox`, `assets`, `properties.datetime`, `properties.platform`, `properties.product:type`, `properties.sar:instrument_mode`, `properties.sar:polarizations`, `properties.sat:relative_orbit`, and `properties.sat:orbit_state`; treat `sat:absolute_orbit` as optional if absent. | | |
| TASK-012 | Implement candidate filtering for `sar:instrument_mode == "IW"`, `product:type` in the accepted GRDH set such as `IW_GRDH_1S`, and `VV` polarization. Prefer candidates that also include `VH`. | | |
| TASK-013 | Implement `bbox_intersection`, `bbox_area_degrees`, and `overlap_percent` helpers equivalent to the Sentinel-2 downloader. | | |
| TASK-014 | Implement nearest-pass ranking for the one-scene validation candidate: positive overlap first, dual polarization first, absolute time delta from `2026-04-27T00:00:00Z` ascending, overlap percentage descending, product id ascending. Preserve all candidates in the manifest for later coverage-set/mosaic work. | | |
| TASK-015 | Write dry-run manifest to `data/raw/sentinel-1-grd/coverage_manifest.json`. | | |
| TASK-016 | Add `--download`, `--download-selected`, `--yes`, `--force`, `--prompt-credentials`, `--item-id`, `--candidate-index`, `--bbox`, `--bbox-preset`, `--datetime`, `--max-items`, and `--out-dir` flags. | | |
| TASK-017 | Ensure dry-run mode never prompts for credentials and never downloads ZIP files. | | |
| TASK-087 | Add download URL resolution that supports STAC `Product` asset hrefs and CDSE OData download URLs under `https://download.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/$value` or `$zip`; record the chosen mode and sanitized availability status in the manifest. | | |
| TASK-088 | If a selected product has no accessible native SAFE ZIP/download URL, fail before preprocessing with a clear sanitized message and a manifest warning; do not attempt SNAP processing from incomplete metadata. | | |

### Implementation Phase 3 — Sentinel-1 GRD SAFE ZIP Preprocessing and COG Creation

- GOAL-003: Create display-ready Sentinel-1 COGs from GRD SAFE products using a reproducible SAR preprocessing workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Create `scripts/prepare_sentinel1_grd_cogs.py` with single-product and manifest-driven modes analogous to `scripts/prepare_sentinel2_l2a_cogs.py`. | | |
| TASK-019 | Use ESA SNAP GPT in the separate SAR Docker image as the first preprocessing implementation. If SNAP is not available, script must fail with a clear message and link to `docs/sentinel-1-grd-cog-prep-runbook.md`. | | |
| TASK-020 | Define a SNAP GPT graph file path, for example `services/ingestion/snap/sentinel1_grd_to_backscatter.xml`, or generate the graph from Python with explicit steps. | | |
| TASK-021 | The SNAP graph must perform Apply-Orbit-File, ThermalNoiseRemoval, optional Remove-GRD-Border-Noise where available, Calibration to sigma0, optional Speckle-Filter disabled by default for first validation, Terrain-Correction, and GeoTIFF output with deterministic target CRS, pixel spacing, band names, and nodata settings recorded in the manifest. | | |
| TASK-022 | Use a DEM source suitable for Linux/Docker execution. Recommended default: Copernicus DEM 30m when available through SNAP; fallback: SRTM 30m. Document DEM caching path. | | |
| TASK-023 | Convert calibrated terrain-corrected linear sigma0 to dB using `10 * log10(max(sigma0, epsilon))`, where `epsilon` is a small positive value such as `1e-8`. | | |
| TASK-024 | Write a Float32 COG `backscatter.tif` with band 1 `VV_dB` and band 2 `VH_dB` when both polarizations exist. If only VV exists, write one band and record `polarizations = ["VV"]` in the manifest. | | |
| TASK-025 | Use Float32 nodata `-9999.0` by default for TiTiler/rasterio compatibility. Treat `NaN` nodata as a future optimization only after downstream rendering and statistics tests prove it safe. | | |
| TASK-026 | Build internal overviews for `backscatter.tif` with average resampling. | | |
| TASK-027 | Write prepared outputs under `data/seed/rasters/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif` and `prepare_manifest.json`. | | |
| TASK-028 | Include in `prepare_manifest.json`: product id, platform, acquisition datetime/date, relative orbit, orbit direction, polarizations, processing graph version, DEM source, output COG path, WGS84 bbox/geometry, CRS, transform, dimensions, nodata, and display rescale defaults. | | |
| TASK-029 | Add a batch summary manifest for manifest-driven mode, analogous to Sentinel-2 batch preparation. | | |

### Implementation Phase 4 — Ingestion Image and Runtime Dependencies

- GOAL-004: Provide a Linux/Docker-compatible runtime for Sentinel-1 SAR preprocessing without breaking the existing Sentinel-2 ingestion worker.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-030 | Create a separate SAR image at `services/ingestion-sar/Dockerfile` instead of extending `services/ingestion/Dockerfile`, to avoid bloating or destabilizing the existing Sentinel-2 ingestion worker. | | |
| TASK-031 | If using SNAP GPT, install Java runtime, SNAP command-line tooling, required SNAP toolboxes, and Python dependencies needed for post-processing and COG creation. | | |
| TASK-032 | Ensure the SAR image can access mounted `data/` paths exactly like the existing `ingestion-worker`. | | |
| TASK-033 | Add documentation for expected memory and disk usage. Minimum recommendation: 16 GiB RAM and large attached disk for batch runs. | | |
| TASK-034 | Add a healthcheck or smoke command that prints SNAP GPT version and verifies that `prepare_sentinel1_grd_cogs.py --help` runs inside the container. | | |
| TASK-089 | Add `ingestion-sar` service wiring to `infra/docker/docker-compose.yml`, including `../../data:/app/data`, `../../scripts:/app/scripts:ro`, and a persistent SNAP DEM/orbit cache volume or documented host path. | | |
| TASK-090 | Add SAR image environment examples and deployment/on-prem notes for SNAP cache paths, memory, disk, and `AKASHA_S1_VV_RESCALE`. | | |

### Implementation Phase 5 — STAC Collection, Scene Identity, and MinIO Upload

- GOAL-005: Register Sentinel-1 prepared scenes as SAR STAC items and upload COGs to source-specific MinIO keys.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-035 | Create `data/seed/stac/sentinel-1-grd-collection.json` with STAC extensions `sar`, `sat`, `raster`, and `projection`; also create a local seed item fixture or source-aware item glob strategy for offline BFF fallback. | | |
| TASK-036 | In the Sentinel-1 collection, define `akasha:supported_indices: []`, `akasha:kind: "sar"`, `akasha:display_modes: ["VV_GRAYSCALE"]`, `akasha:default_display_mode: "VV_GRAYSCALE"`, `akasha:date_metrics_kind: "radar"`, and item asset metadata for `backscatter`. | | |
| TASK-037 | Update `services/ingestion/akasha_ingest/config.py` so collection file lookup and prepared manifest discovery are parameterized by collection/source id and support source-scoped layouts such as `data/seed/rasters/sentinel-1-grd/*/*/*/prepare_manifest.json`. | | |
| TASK-038 | Update `services/ingestion/akasha_ingest/scene.py` with Sentinel-1 product parsing for product ids such as `S1A_IW_GRDH_...` and `S1C_IW_GRDH_...`; product-name parsing must not be the only source for `sat:relative_orbit` or `sat:orbit_state`. | | |
| TASK-039 | Add Sentinel-1 scene identity fields: `source_id`, `platform`, `instrument_mode`, `product_type`, `relative_orbit_or_unknown`, `orbit_state_or_unknown`, `acquisition_datetime`, `product_id_hash`, and `scene_component`. | | |
| TASK-040 | Use MinIO keys such as `sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif`; include `product_id_hash` or an equivalent sanitized product component in `sceneComponent` to avoid collisions. | | |
| TASK-041 | Update `services/ingestion/akasha_ingest/storage.py` so manifest upload and verification are collection-aware: Sentinel-2 expects `analytic` + `scl`, Sentinel-1 expects `backscatter`. | | |
| TASK-042 | Update `services/ingestion/akasha_ingest/catalog.py` with a Sentinel-1 STAC item builder that emits SAR metadata and `backscatter` asset hrefs. | | |
| TASK-043 | Update `services/ingestion/worker.py ingest-manifest`, `verify-manifest-cogs`, `services/ingestion/akasha_ingest/seed.py`, and `services/ingestion/akasha_ingest/verify.py` so they can ingest/verify Sentinel-1 prepared manifests without breaking Sentinel-2 manifests. | | |

### Implementation Phase 6 — BFF Source Registry and Sentinel-1 Tiles

- GOAL-006: Expose Sentinel-1 as a source and serve the first VV grayscale display tiles through the BFF.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-044 | Refactor `apps/api/app/raster/catalog_resolver.py` from Sentinel-2 singleton constants to a source registry containing `sentinel-2-l2a` and `sentinel-1-grd`, using the schema finalized in TASK-085. | | |
| TASK-045 | Update `/api/sources` in `apps/api/app/product.py` so it returns all registered source collections and includes `kind`, `displayModes`, `defaultDisplayMode`, `description`, `attribution`, and source-specific `supportedIndices`. | | |
| TASK-046 | Ensure Sentinel-1 source response includes `supportedIndices: []`, `provider: "Copernicus"`, and `label: "Sentinel-1 GRD"`. | | |
| TASK-047 | Update `/api/sources/{sourceId}/dates` so Sentinel-1 dates are listed with `sceneCount`, merged bounds, `tileAvailable`, `metricsProvisional`, `usablePixelPercent: null`, `cloudMaskedPercent: null`, optional `coveragePercent`, and `isLatestUsable` meaning latest selectable radar pass. | | |
| TASK-048 | Update default layer selection so selecting `sentinel-1-grd` resolves the nearest/latest Sentinel-1 date independently from Sentinel-2 and returns Sentinel-1 attribution/display mode. | | |
| TASK-049 | Add Sentinel-1 asset resolution for `backscatter` COGs. Do not require `analytic`, `scl`, `eo:bands`, or optical band positions for Sentinel-1. | | |
| TASK-050 | Add `build_sentinel1_vv_tile_url()` in `apps/api/app/raster/tiles.py` using TiTiler COG tile route with `bidx=1`, configurable `rescale=-25,5`, and grayscale rendering behind `/api/tiles/{sourceId}/{acquisitionDate}/VV_GRAYSCALE/{z}/{x}/{y}.png`. | | |
| TASK-051 | Add environment variable `AKASHA_S1_VV_RESCALE` with default `-25,5` to API settings, `.env.example`, Docker Compose, and deployment documentation. | | |
| TASK-052 | Return a transparent PNG for out-of-footprint Sentinel-1 tile misses just like Sentinel-2 edge tiles. | | |
| TASK-053 | Ensure `POST /api/indices/statistics` rejects Sentinel-1 optical index requests with a sanitized unsupported-source/index error. | | |
| TASK-091 | Fix `catalog_resolver.supported_indices()` so an explicitly empty `akasha:supported_indices: []` remains empty and does not fall back to global Sentinel-2 `SUPPORTED_INDICES`. | | |
| TASK-092 | Add source-aware default layer support via `GET /api/layers/default?sourceId=sentinel-1-grd` or an equivalent source-aware contract; response must include `displayMode` and a matching tile URL template. | | |
| TASK-093 | Clarify `/api/config` index fields as legacy/global optical defaults or migrate frontend index availability to selected-source metadata so Sentinel-1 never inherits optical index controls from global config. | | |

### Implementation Phase 7 — Frontend Source Switching and SAR UX

- GOAL-007: Allow users to select Sentinel-1 in the layer panel while clearly communicating it is a radar layer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-054 | Update `apps/frontend/src/types/api.ts` to allow source/default-layer metadata fields: `kind?: "optical" | "sar"`, `displayModes?: string[]`, `defaultDisplayMode?: string`, `displayMode?: string`, `description?: string`, and source-specific attribution. | | |
| TASK-055 | Ensure `apps/frontend/src/components/layers/SourceSelector.tsx` works with multiple source tabs without layout overflow. | | |
| TASK-056 | Update `apps/frontend/src/pages/MapPage.tsx` to use source metadata for attribution and source-specific notes instead of hardcoded Sentinel-2 fallback text. | | |
| TASK-057 | Update `apps/frontend/src/components/layers/LayerPanel.tsx` to show the note `Radar layer · cloud-penetrating · not true colour` when source kind is `sar`. | | |
| TASK-058 | Hide or disable optical index UI/actions, including `apps/frontend/src/components/scaffold/IndexPanel.tsx`, when selected source has `supportedIndices.length === 0` or `kind === "sar"`. | | |
| TASK-059 | Keep `apps/frontend/src/lib/satelliteLayer.ts` as one raster source/layer per selected source/date. Do not add one browser layer per scene. | | |
| TASK-060 | If Sentinel-1 selected date is not `2026-04-27`, show nearest-pass wording such as `Nearest radar pass: YYYY-MM-DD`. | | |
| TASK-094 | Update `apps/frontend/src/components/layers/DateList.tsx` and `CloudUsabilityChip.tsx` so SAR dates do not show cloud/usability chip wording; show radar-pass or coverage-safe metadata instead. | | |
| TASK-095 | Update `apps/frontend/src/lib/api.ts` `composeTileTemplate()` to accept `displayMode` and generate `/api/tiles/{sourceId}/{date}/{displayMode}/{z}/{x}/{y}.png`. | | |
| TASK-096 | Update `apps/frontend/src/lib/selectDefaultDate.ts` to support SAR source selection where `usablePixelPercent` is `null` and latest selectable radar pass should be chosen. | | |

### Implementation Phase 8 — Sentinel-1 Runbook and Documentation

- GOAL-008: Document the full Sentinel-1 operator workflow before or alongside implementation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-061 | Create `docs/sentinel-1-grd-cog-prep-runbook.md`. | | |
| TASK-062 | In the runbook, document Sentinel-1 source products: CDSE `sentinel-1-grd`, `sar:instrument_mode = IW`, `product:type = IW_GRDH_1S` or accepted GRDH equivalents, `VV/VH`, SAFE ZIP contents, and free/open access through Copernicus. | | |
| TASK-063 | In the runbook, document dry-run discovery for the same bbox and nearest-pass search around `2026-04-27`. | | |
| TASK-064 | In the runbook, document explicit download commands, credential handling, and CDSE OData download URL modes (`$value`/`$zip`) plus the failure behavior when native ZIP access is unavailable. | | |
| TASK-065 | In the runbook, document SNAP GPT preprocessing steps and VM/container requirements. | | |
| TASK-066 | In the runbook, document output COG layout, MinIO keys, STAC registration, BFF serving, UI behavior, and the one-scene-validation scope versus later mosaic/pre-mosaic regional coverage. | | |
| TASK-067 | Update `docs/data-ingestion-and-satellite-rules.md` with Sentinel-1 SAR COG layout, STAC metadata, no-SCL rules, dB display rescale, and no-optical-index constraints. | | |
| TASK-068 | Update `docs/product-plan.md` to clarify Sentinel-1 is a Wave 2 radar fallback layer, not a true-colour optical source. | | |
| TASK-100 | Update `docs/architecture-tech-stack.md` and `apps/api/README.md` to document display-mode-aware tile routes and source-specific index availability. | | |

### Implementation Phase 9 — Validation and Rollout

- GOAL-009: Validate one Sentinel-1 scene end-to-end before large-area or multi-date ingestion.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-069 | Run Sentinel-1 downloader dry-run for `2026-04-27 ± 7 days` and confirm whether exact-date or nearest-pass candidates exist. | | |
| TASK-070 | Download exactly one selected Sentinel-1 GRD product first. | | |
| TASK-071 | Verify SAFE ZIP contents include measurement files for expected polarizations and annotation/calibration metadata. | | |
| TASK-072 | Run Sentinel-1 preprocessing and COG creation for that one product. | | |
| TASK-073 | Validate `backscatter.tif` with `rio-cogeo`, `gdalinfo`, and TiTiler tile rendering. | | |
| TASK-074 | Upload/register the Sentinel-1 scene and verify STAC item metadata includes SAR fields. | | |
| TASK-075 | Query `/api/sources` and confirm both Sentinel-2 L2A and Sentinel-1 GRD appear. | | |
| TASK-076 | Query `/api/sources/sentinel-1-grd/dates` and confirm Sentinel-1 date metadata is returned. | | |
| TASK-077 | Request a Sentinel-1 VV grayscale tile and confirm `200 image/png`. | | |
| TASK-078 | Open the UI, switch to Sentinel-1 GRD, and confirm radar note, date, layer toggle, opacity, and no optical index options. | | |
| TASK-097 | Validate that `/api/sources` returns Sentinel-1 with `supportedIndices: []` and that no fallback optical indices appear. | | |
| TASK-098 | Validate that Sentinel-1 tile requests use `/api/tiles/sentinel-1-grd/{date}/VV_GRAYSCALE/{z}/{x}/{y}.png`, not an RGB route. | | |
| TASK-099 | Validate that a Sentinel-1 multi-scene date returns a sanitized `MOSAIC_TILES_UNAVAILABLE` or equivalent until a supported mosaic/pre-mosaic path is implemented. | | |

## 3. Alternatives

- **ALT-001**: Require exact Sentinel-1 date `2026-04-27`. Rejected for the first implementation because Sentinel-1 pass timing may not align exactly with Sentinel-2 acquisition dates.
- **ALT-002**: Use Sentinel-1 SLC products. Rejected because SLC is complex-valued and intended for InSAR/coherence workflows; GRD is simpler and sufficient for first display layers.
- **ALT-003**: Implement false-colour SAR first. Deferred because VV grayscale is easier to validate and explain. False-colour SAR needs stronger legends and product interpretation.
- **ALT-004**: Add SNAP GPT directly to the existing ingestion-worker image. Deferred as a default because SNAP may significantly increase image size; a separate SAR worker image is safer.
- **ALT-005**: Treat Sentinel-1 as another RGB source. Rejected because SAR is not optical imagery and has no red/green/blue bands.
- **ALT-006**: Allow NDVI/NDRE/NDMI/NDWI on Sentinel-1. Rejected because those are optical spectral indices and are not meaningful for SAR.
- **ALT-007**: Use CDSE STAC `vv`/`vh` polarization assets directly as the first display layer. Deferred until TASK-083 verifies calibration, terrain-correction, units, and display suitability; may become a temporary display-only fallback if native SAFE ZIP download is unavailable.
- **ALT-008**: Promise full South India Sentinel-1 visual coverage in the first implementation. Rejected because the target bbox may require multiple scenes and current date-level multi-COG tile rendering intentionally fails until a supported mosaic/pre-mosaic backend is implemented.

## 4. Dependencies

- **DEP-001**: Copernicus Data Space STAC API collection `sentinel-1-grd` for discovery.
- **DEP-002**: Copernicus Data Space OData catalogue metadata plus CDSE download-service URLs such as `https://download.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/$value` or `$zip` for downloading complete Sentinel-1 SAFE ZIPs when available.
- **DEP-003**: CDSE credentials supplied through ignored `.env`, `CDSE_ACCESS_TOKEN`, or `CDSE_USERNAME`/`CDSE_PASSWORD` for downloads.
- **DEP-004**: ESA SNAP GPT or an equivalent SAR preprocessing stack for orbit, calibration, noise removal, terrain correction, and dB conversion.
- **DEP-005**: DEM access for terrain correction, preferably Copernicus DEM 30m or SRTM 30m.
- **DEP-006**: Existing Docker Compose services: MinIO, PostGIS, STAC API, TiTiler, FastAPI BFF, web gateway.
- **DEP-007**: rio-cogeo/rasterio/GDAL for COG creation and validation after SAR preprocessing.
- **DEP-008**: TiTiler COG tile rendering for display tiles.
- **DEP-009**: CDSE Sentinel-1 GRD queryables must expose the fields used for filtering/ranking: `product:type`, `sar:instrument_mode`, `sar:polarizations`, `sat:relative_orbit`, `sat:orbit_state`, `platform`, and `datetime`.
- **DEP-010**: A supported mosaic/pre-mosaic backend is required before multi-scene Sentinel-1 dates can be rendered as one complete regional date layer.

## 5. Files

- **FILE-001**: `scripts/download_sentinel1_grd_product.py` — New Sentinel-1 GRD discovery/download script.
- **FILE-002**: `scripts/prepare_sentinel1_grd_cogs.py` — New Sentinel-1 preprocessing and COG preparation script.
- **FILE-003**: `services/ingestion/snap/sentinel1_grd_to_backscatter.xml` — Optional SNAP GPT graph file if graph is not generated from Python.
- **FILE-004**: `services/ingestion-sar/Dockerfile` — Separate SNAP/SAR preprocessing runtime.
- **FILE-005**: `data/seed/stac/sentinel-1-grd-collection.json` — New Sentinel-1 STAC collection.
- **FILE-006**: `services/ingestion/akasha_ingest/config.py` — Source/collection-aware config helpers.
- **FILE-007**: `services/ingestion/akasha_ingest/scene.py` — Sentinel-1 product parsing and scene identity.
- **FILE-008**: `services/ingestion/akasha_ingest/storage.py` — Collection-aware upload and verification for Sentinel-1 `backscatter` assets.
- **FILE-009**: `services/ingestion/akasha_ingest/catalog.py` — Sentinel-1 SAR STAC item builder.
- **FILE-010**: `services/ingestion/worker.py` — Source-aware manifest ingest and verification commands.
- **FILE-011**: `apps/api/app/raster/catalog_resolver.py` — Multi-source registry and Sentinel-1 asset resolution.
- **FILE-012**: `apps/api/app/raster/tiles.py` — Sentinel-1 VV grayscale tile builder and SAR rescale config.
- **FILE-013**: `apps/api/app/product.py` — Multi-source source list and default layer behavior.
- **FILE-014**: `apps/api/app/raster/service.py` — Guard optical statistics for SAR sources.
- **FILE-015**: `apps/frontend/src/types/api.ts` — Add source metadata fields such as `kind` and `displayModes`.
- **FILE-016**: `apps/frontend/src/pages/MapPage.tsx` — Source-specific attribution, note, and index availability behavior.
- **FILE-017**: `apps/frontend/src/components/layers/LayerPanel.tsx` — SAR explanatory note and optional nearest-pass label.
- **FILE-018**: `docs/sentinel-1-grd-cog-prep-runbook.md` — New Sentinel-1 runbook.
- **FILE-019**: `docs/data-ingestion-and-satellite-rules.md` — Add Sentinel-1 SAR rules.
- **FILE-020**: `docs/product-plan.md` — Clarify Sentinel-1 Wave 2 SAR product behavior.
- **FILE-021**: `docs/impl-plan/data-sentinel1-grd-layer-1.md` — This implementation plan.
- **FILE-022**: `services/ingestion/akasha_ingest/seed.py` — Source-aware seed loading if existing helpers assume Sentinel-2 sample assets.
- **FILE-023**: `services/ingestion/akasha_ingest/verify.py` — Source-aware verification if existing helpers assume Sentinel-2 sample assets.
- **FILE-024**: `infra/docker/docker-compose.yml` — Optional `ingestion-sar` service and Sentinel-1 API environment variables.
- **FILE-025**: `apps/api/.env.example` — Document `AKASHA_S1_VV_RESCALE` and any source/default-display variables.
- **FILE-026**: `apps/frontend/src/lib/api.ts` — Display-mode-aware tile template composition.
- **FILE-027**: `apps/frontend/src/lib/selectDefaultDate.ts` — SAR-safe default date selection.
- **FILE-028**: `apps/frontend/src/components/layers/DateList.tsx` — Source-aware date metric wording.
- **FILE-029**: `apps/frontend/src/components/layers/CloudUsabilityChip.tsx` — Hide or generalize cloud/usable copy for SAR sources.
- **FILE-030**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` — Hide or replace optical index messaging for SAR sources.
- **FILE-031**: `docs/architecture-tech-stack.md` — Document display-mode-aware tile routes and source-specific indices.
- **FILE-032**: `apps/api/README.md` — Document source metadata and display-mode tile route updates.
- **FILE-033**: `data/seed/stac/sentinel-1-grd-sample-item.json` or `data/seed/stac/items/sentinel-1-grd/*.json` — Offline/static Sentinel-1 STAC item fixture if local fallback is used.

## 6. Testing

- **TEST-001**: Unit test Sentinel-1 downloader default date window returns `2026-04-20T00:00:00Z/2026-05-04T23:59:59Z` for reference date `2026-04-27` and `window_days=7`.
- **TEST-002**: Unit test Sentinel-1 candidate filtering includes `sar:instrument_mode = "IW"`, `product:type = "IW_GRDH_1S"` or an allowed `*_GRDH_1S` value, and `VV`; prefer `VV+VH`.
- **TEST-003**: Unit test nearest-pass ranking selects the candidate with smallest absolute time delta to `2026-04-27` after overlap and polarization filters.
- **TEST-004**: Unit test Sentinel-1 product id parser extracts platform, instrument mode, product type, acquisition datetime, and relative orbit/scene component where available.
- **TEST-005**: Unit test prepared Sentinel-1 manifest path generation writes under `data/seed/rasters/sentinel-1-grd/{date}/{relativeOrbitOrUnknown}/{sceneComponent}/` and includes a product id component/hash in `sceneComponent`.
- **TEST-006**: Unit test Sentinel-1 STAC collection includes SAR extension and `supportedIndices: []`.
- **TEST-007**: Unit test Sentinel-1 STAC item builder emits `sar:*`, `sat:*`, `raster:*`, and `projection` metadata and one `backscatter` asset.
- **TEST-008**: Unit test storage verification accepts Sentinel-1 `backscatter` COGs and does not require Sentinel-2 `analytic` or `scl` assets.
- **TEST-009**: API test `/api/sources` returns both Sentinel-2 and Sentinel-1 when both collections are registered.
- **TEST-010**: API test `/api/sources/sentinel-1-grd/dates` returns date metadata without optical index claims.
- **TEST-011**: API test Sentinel-1 tile builder uses `bidx=1` and source-specific rescale, default `-25,5`.
- **TEST-012**: API test optical index/statistics request for `sentinel-1-grd` returns a sanitized unsupported index/source error.
- **TEST-013**: Frontend test source selector renders Sentinel-1 source tab.
- **TEST-014**: Frontend test Sentinel-1 selection shows radar note and hides/disables optical index controls.
- **TEST-015**: Manual validation dry-runs CDSE Sentinel-1 discovery for the target bbox around `2026-04-27`.
- **TEST-016**: Manual validation downloads one Sentinel-1 GRD product and verifies SAFE contents.
- **TEST-017**: Manual validation runs preprocessing and confirms `backscatter.tif` is COG-valid.
- **TEST-018**: Manual validation registers one Sentinel-1 item and renders one VV grayscale tile via BFF/TiTiler.
- **TEST-019**: Unit test `catalog_resolver.supported_indices()` returns `[]` when collection metadata explicitly contains `akasha:supported_indices: []`.
- **TEST-020**: API test `/api/sources` returns Sentinel-1 with `kind: "sar"`, `displayModes: ["VV_GRAYSCALE"]`, `defaultDisplayMode: "VV_GRAYSCALE"`, `dateMetricsKind: "radar"`, and `supportedIndices: []`.
- **TEST-021**: API test source-aware default-layer response for Sentinel-1 returns a `VV_GRAYSCALE` tile template rather than an RGB template.
- **TEST-022**: API test display-mode tile route accepts `/api/tiles/sentinel-1-grd/{date}/VV_GRAYSCALE/{z}/{x}/{y}.png` and rejects unsupported Sentinel-1 display modes with a sanitized error payload.
- **TEST-023**: Unit test source-scoped prepared manifest discovery finds `data/seed/rasters/sentinel-1-grd/{date}/{relativeOrbitOrUnknown}/{sceneComponent}/prepare_manifest.json`.
- **TEST-024**: Frontend test `composeTileTemplate()` supports display mode and does not hardcode `/rgb/` for Sentinel-1.
- **TEST-025**: Frontend test SAR date rows do not display cloud/usable-pixel terminology or cloud-chip copy.
- **TEST-026**: Frontend test SAR default-date selection does not require `usablePixelPercent`.
- **TEST-027**: Unit test downloader manifest records CDSE download availability and exits safely before preprocessing when SAFE ZIP download is unavailable.

## 7. Risks & Assumptions

- **RISK-001**: Exact Sentinel-1 acquisition on `2026-04-27` may not exist for the target bbox.
- **RISK-002**: SNAP GPT dependency can make Docker images large and slow to build.
- **RISK-003**: Sentinel-1 preprocessing requires orbit files and DEM access; network or cache failures can block processing.
- **RISK-004**: Terrain correction and speckle filtering can be memory- and CPU-intensive for large scenes.
- **RISK-005**: SAR imagery is visually unfamiliar and can be misinterpreted without UI explanation.
- **RISK-006**: Float32 `-9999.0` nodata may still require adjustment if TiTiler/rasterio masking behavior differs between local validation and deployed runtime.
- **RISK-007**: Sentinel-1 source semantics may require broader API changes because current raster code contains many Sentinel-2 optical assumptions.
- **RISK-008**: Multi-source support must not regress the working Sentinel-2 2026-04-27 pipeline.
- **RISK-009**: CDSE compressed/native Sentinel-1 SAFE ZIP download may be unavailable for selected products; fallback or operator intervention may be required.
- **RISK-010**: Full target-bbox Sentinel-1 display may require multiple scenes and a mosaic/pre-mosaic backend that is not part of one-scene validation.
- **RISK-011**: Existing frontend copy and date metrics are optical/cloud-centric and could mislead users if not made source-aware.
- **ASSUMPTION-001**: Sentinel-1 GRD IW products are available from CDSE for the target bbox within `±7 days` of `2026-04-27`.
- **ASSUMPTION-002**: VV grayscale is acceptable as the first Sentinel-1 visualization.
- **ASSUMPTION-003**: Sentinel-1 is used as a display/fallback layer first; SAR analytics are future work.
- **ASSUMPTION-004**: Operators will validate one Sentinel-1 scene end-to-end before batch ingestion.
- **ASSUMPTION-005**: The frontend remains source-agnostic and should not own SAR preprocessing or per-scene composition logic.
- **ASSUMPTION-006**: Phase 0 validation will confirm at least one candidate can be discovered in CDSE STAC for the configured bbox/date window.
- **ASSUMPTION-007**: Full regional Sentinel-1 rendering is not considered complete until multi-scene mosaic/pre-mosaic behavior is implemented and verified.

## 8. Related Specifications / Further Reading

- `docs/data-ingestion-and-satellite-rules.md`
- `docs/sentinel-2-l2a-cog-prep-runbook.md`
- `docs/product-plan.md`
- `docs/architecture-tech-stack.md`
- `docs/engineering-dos-donts.md`
- `docs/impl-plan/data-sentinel2-production-coverage-1.md`
- `scripts/download_sentinel2_l2a_product.py`
- `scripts/prepare_sentinel2_l2a_cogs.py`
- `services/ingestion/akasha_ingest/catalog.py`
- `services/ingestion/akasha_ingest/storage.py`
- `apps/api/app/raster/catalog_resolver.py`
- `apps/api/app/raster/tiles.py`
- Copernicus Data Space STAC API: `https://stac.dataspace.copernicus.eu/v1`
- Copernicus Data Space Sentinel-1 GRD queryables: `https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/queryables`
- Copernicus Data Space OData API: `https://catalogue.dataspace.copernicus.eu/odata/v1`
- Copernicus Data Space OData documentation: `https://documentation.dataspace.copernicus.eu/APIs/OData.html`
- STAC SAR extension: `https://stac-extensions.github.io/sar/`
- ESA SNAP toolbox documentation: `https://step.esa.int/main/doc/`
