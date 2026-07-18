# EOS-04 SAR-MRS L2B display integration plan

## Status and authority

This plan was reconciled with the current two-repository implementation on 2026-07-18. It
supersedes the earlier single-repository EOS-04 plan.

Implementation status: phases 1–5 and local validation are complete in the working trees. A real
approved-runtime EOS-04 product has also passed catalog search, capped download, package inspection,
calibration, mask application, and strict COG validation. The operational ingest/catalog/API run
is also complete. Staging product exposure is approved through the two fail-closed deployment
gates; production exposure remains unchanged. A screenshot-backed staging smoke test is the
remaining release-evidence step.

- `akasha-ingestion` owns provider access, raw downloads, preparation, validation, object storage,
  pgSTAC registration, scheduler jobs, and private raster-serving APIs.
- `akasha-project` owns the product BFF and React/MapLibre UI. The browser talks only to the product
  origin; the BFF calls ingestion server-to-server.
- `akasha-project/services/ingestion` and its EOS-04 preparation script are reference/legacy code.
  New operational ingestion work belongs in `akasha-ingestion`.

## Pre-implementation audit used to reconcile the plan

### Standalone ingestion (`akasha-ingestion`)

Sentinel-2 and the three ResourceSat instrument sources are implemented end to end. The current
runtime provides source catalog rows, provider routes, bounded backfill jobs, prepared COG/object
storage, pgSTAC registration, readiness, field-quality analytics, signed field overlays, Celery
tasks, and deployment preflight checks.

Before this change EOS-04 was not a runtime source in this repository. The implementation adds its
source row, settings, scheduler state, ingestion service, Celery task, SAR preparation module, SAR
STAC collection/item builder, natural-source date endpoint, and natural-source tile endpoint.

### Product API and frontend (`akasha-project`)

EOS-04 already has useful gated scaffolding:

- rich source metadata with `kind="sar"`, no optical indices, no mask, and Backscatter display;
- legacy app-native date/tile resolution and SAR-assisted optical support;
- frontend source selection, radar timeline semantics, Backscatter legend, disabled optical
  analytics/export controls, and tests;
- admin monitoring visibility while the product source remains gated.

The production source list intentionally contains only Sentinel-2, LISS-3, LISS-4, and AWiFS.
ResourceSat/Sentinel pipeline bridging currently assumes field-index optical sources and cannot be
reused unchanged for a display-only SAR source.

## Target state

EOS-04 SAR-MRS L2B becomes the fifth product source through the current ownership boundary:

1. Standalone ingestion searches and downloads one bounded Bhoonidhi EOS-04 product.
2. A source-specific processor produces a validated Float32 dB `backscatter.tif` COG and manifest.
3. Ingestion stores the COG, registers a SAR pgSTAC item with explicit polarizations, and exposes
   private API-key-protected acquisition-date and natural-tile endpoints.
4. The product BFF obtains dates and tile bytes server-to-server and exposes only same-origin
   `/api/*` responses to the browser.
5. The existing frontend renders the radar date timeline and Backscatter layer while keeping all
   optical index, cloud-mask, field-index, point, trend, and export workflows disabled.

Product activation remains controlled by explicit deployment flags. Code completion does not
authorize enabling EOS-04 until a real staging product passes every activation gate below.

## Scientific and product contract

- Source ID: `eos-04-sar-mrs-l2b`.
- Provider route: `bhoonidhi:EOS-04_SAR-MRS_L2B`.
- Processing family: SAR backscatter, never optical reflectance.
- Output: one `backscatter.tif` COG per provider scene; no optical composite and no index COGs.
- Accepted polarization names: `HH`, `HV`, `VH`, `VV`, `RH`, `RV`; at least one explicit value is
  required. Unknown/missing polarization metadata fails closed.
- Input must be EOS-04 SAR-MRS `L2B-ARD-PRODUCT` with `RTC_Apply_Flag=1`, no missing frames,
  explicit polarization declarations, matching `imagery_<POL>.tif` rasters, and a data mask.
- Each uint16 Gamma0 DN band is calibrated with its package metadata using
  `10*log10(DN² - IMAGE_NOISE_BIAS) - Calibration_Constant_Beta0`. Only mask value `128` is valid;
  layover, shadow, and outside-product values are nodata. Output is Float32 dB with overviews.
- The validated MRS L2B ARD grid uses 18 m pixel spacing (nominal MRS ground resolution is about
  33 m).
- UI display token remains `VV_GRAYSCALE` for compatibility, but all user-facing text says
  “Backscatter”. The renderer selects the first explicitly registered polarization; it never
  fabricates VV metadata.
- No NDVI, MSAVI, NDMI, NDWI, NDRE, RECI, optical cloud percentage, SCL, or ResourceSat mask.
- One scene per acquisition date is renderable. Multiple same-date scenes are reported as
  unavailable until a SAR mosaic strategy exists.

## Implementation phases

### Phase 1 — contracts and gated source registration

- Add EOS-04 constants, settings, static/database source metadata, provider route, and a manual,
  hidden scheduler state in `akasha-ingestion`.
- Add `eos04_backfill` to the validated sync request contract.
- Keep routine scheduling and product exposure disabled by default.
- Extend deployment configuration with opt-in EOS-04 flags without changing the four-source
  production preflight invariant.

### Phase 2 — SAR preparation and validation

- Port the validated concepts from the legacy preparation script into a package module owned by
  `akasha-ingestion`; do not execute or import code across repositories.
- Extract TIFF candidates safely, parse `BAND_META`, resolve explicit band polarizations, apply the
  per-polarization Gamma0 calibration/noise constants and mask, write a deterministic COG, and emit
  a typed manifest.
- Reject path traversal, non-L2B/non-ARD products, missing RTC, missing frames, missing/ambiguous
  polarizations, mismatched grids, invalid CRS/transform, empty rasters, missing overviews, and
  non-finite output.
- Add synthetic HH/HV and RH/RV tests plus fail-closed tests.

### Phase 3 — bounded ingestion service and worker

- Implement search -> bounded download -> prepare -> validate -> store -> scene/asset registration
  -> pgSTAC registration.
- Reuse the current approved-runtime, storage-root, idempotency, redaction, stage tracking, and
  worker-loss conventions.
- Add a dedicated Celery task routed to the heavy/preprocess worker. EOS-04 must never call the
  ResourceSat composite/index stages.

### Phase 4 — SAR catalog, dates, and private tiles

- Register a SAR-specific pgSTAC collection/item with `sar:polarizations`, C-band metadata,
  projection/raster metadata, and a `backscatter` asset.
- Add API-key-protected `GET /api/v1/sources/{sourceId}/dates` and natural-source tile endpoints.
- Dates return radar semantics: null optical quality metrics, scene count, footprint/bounds, and a
  clear unavailable reason for same-date multi-scene cases.
- Tile serving resolves only registered EOS-04 items/assets and proxies private TiTiler bytes.

### Phase 5 — product BFF cutover and UI activation path

- Add EOS-04-specific ingestion client models/methods for dates and tile bytes.
- Add an explicit `INGESTION_EOS04_CUTOVER_ENABLED` gate and an independent
  `EOS04_PRODUCT_ENABLED` exposure gate.
- When cut over, source dates/default-layer metadata come from ingestion and `/api/tiles/...`
  proxies ingestion; app-native object/STAC URLs are not used.
- Add EOS-04 to the product source list only when both exposure and cutover prerequisites are met.
- Preserve the existing React SAR UX and add integration tests proving Backscatter display,
  radar timeline, disabled optical controls, and absence of ingestion URLs/secrets in browser data.

### Phase 6 — validation and activation

Local completion requires lint, unit/integration tests, API contract tests, frontend tests, and
frontend build in both repositories.

Staging activation requires, in order:

1. Inspect one real EOS-04 MRS L2B archive with `gdalinfo` and record band order, polarizations,
   calibration/noise metadata, mask classes, RTC flag, CRS, resolution, and file layout. **Passed:**
   2026-07-17 Bangalore scene, HH/HV, EPSG:32643, 18 m, mask value 128.
2. Run an approved-runtime dry run. **Passed.**
3. Run one capped download (`max_downloads=1`). **Passed:** 1,232,901,939-byte ZIP; integrity and
   SHA-256 recorded in the staging validation evidence.
4. Pass SAR preparation/COG validation before upload. **Passed:** strict-valid 478,982,354-byte
   HH/HV Float32 dB COG with five overview levels and expected sampled backscatter distributions.
5. Confirm object storage and pgSTAC contain exactly the expected backscatter scene/item. **Passed:**
   one accepted scene, one 509 MB prepared COG, and one SAR pgSTAC item with HH/HV metadata.
6. Confirm ingestion dates and tile endpoints through API-key authentication. **Passed:** private
   dates returned one tile-available acquisition and an authenticated tile returned PNG 200.
7. Confirm the product BFF returns same-origin dates/tiles and leaks no internal URLs or secrets.
8. Enable both EOS-04 gates in staging only after steps 1–7 pass; keep production unchanged.
9. Complete a screenshot-backed frontend smoke test on the activated staging source. Routine
   scheduling and production exposure remain separate operational decisions.

## Validation commands

From `akasha-ingestion`:

```bash
ruff check .
python -m pytest
```

From `akasha-project`:

```bash
ruff check apps/api
cd apps/api && python -m pytest -q
cd apps/frontend && yarn test && yarn build
```

## Explicit non-goals

- Deriving optical vegetation indices from SAR.
- Filling cloudy NDVI pixels with SAR values.
- SAR field statistics, soil-moisture models, flood classification, or crop classification.
- Date mosaicking of multiple EOS-04 scenes.
- Direct browser access to ingestion, TiTiler, MinIO, pgSTAC, or signed storage URLs.
- Automatic production activation without real-product staging evidence.
