# Data Ingestion and Satellite Rules

## Purpose

This document is the source of truth for imagery sources, COG layout, STAC
metadata, masking, and index calculation rules. Product UX belongs in
`india-specific-productization-plan.md`, `map-screen-redesign.md`, and
`design-system.md`; service architecture belongs in `architecture-tech-stack.md`;
deployment/runtime details belong in `infra/selfhosted/README.md`.

## Production Source Strategy

The production default source is ISRO/NRSC Bhoonidhi ResourceSat-2A LISS-3 BOA
over the Bangalore 60 km AOI. Sentinel source support remains only for legacy
regression and migration checks unless explicitly enabled.

| Source | Provider | Status | Role |
|---|---|---|---|
| ResourceSat-2A LISS-3 BOA | ISRO/NRSC Bhoonidhi | Primary | Field-level optical analytics, FCC display, NDVI/MSAVI/NDMI/NDWI_GREEN_NIR. |
| ResourceSat-2A AWiFS BOA | ISRO/NRSC Bhoonidhi | Gated | Coarser optical context/analytics after validation. |
| ResourceSat-2A LISS-4 | ISRO/NRSC Bhoonidhi | Active: high-resolution field enhancement for NDVI/MSAVI/NDWI_GREEN_NIR with LISS-3 fallback | Verified Jan 30 staging composite for field-level high-resolution enhancement where coverage exists; LISS-3 remains the fallback. |
| EOS-06 OCM NDVI | ISRO/NRSC Bhoonidhi | Gated | Coarse precomputed NDVI context only; not field-level stats. |
| EOS-04 SAR / NISAR | ISRO/NRSC Bhoonidhi | Gated SAR | Radar context; never optical vegetation-index sources. |
| Cartosat-3 | ISRO/NRSC Bhoonidhi | Gated/manual | High-resolution visual context only until access, licensing, and product format are confirmed. |
| Sentinel-2 L2A | ESA / Copernicus | Legacy opt-in | Regression/migration path; not production-selectable by default. |
| Sentinel-1 GRD | ESA / Copernicus | Legacy/gated SAR | SAR context; no optical indices. |

## New Satellite Source Onboarding Rule

Every new satellite source must stay gated until it has all of the following:

- A pipeline registry entry that defines source id, provider, supported roles,
  band/order metadata, default display mode, mask behavior, and index support.
- A source-specific transform/prep script or adapter for native provider
  products; do not reuse ResourceSat/Sentinel assumptions unless the source
  metadata proves they match.
- Validation tests for registry behavior, transform outputs, COG/STAC metadata,
  masks, and source-specific supported/unsupported indices.
- A staging dry-run from the approved staging egress path.
- A capped real staging run, normally with `--max-downloads 1` first.
- Source-appropriate verification before the source is exposed for team use or
  marked selectable in the product. Use `worker.py verify-composite` only for
  optical sources that produce dated composite COGs; use source-aware raster,
  SAR, context, or archive verification for non-composite sources.

## Catalogue-wide Scheduler Rules

The provider-agnostic ingestion scheduler is the architecture layer for scaling beyond
ResourceSat. It must be implemented before onboarding new provider families in bulk.
The Phase 0 contract is [satellite-ingestion-scheduler-contracts.md](reference/satellite-ingestion-scheduler-contracts.md).
The operational guide — how the scheduler works, how to trigger/control it, and the step-by-step
checklist for adding a new satellite — is
[satellite-ingestion-orchestration-and-scheduler.md](satellite-ingestion-orchestration-and-scheduler.md).

- Every scheduler source row must trace to a `docs/reference/satellite-catalog.md` slug through
  `catalogSlug`; one catalogue platform may map to multiple source rows only through explicit
  product variants, such as ResourceSat LISS-3, LISS-4, and AWiFS.
- Scheduler source state must keep lifecycle, schedule, capability, product exposure, commercial,
  AOI, validation, and readiness fields separate. Do not overload `mvp_enabled` or one status
  string to mean all of those things.
- Provider-specific HTTP/auth/search/download/order logic belongs only in provider adapters.
  The scheduler owns due decisions, jobs, locks, redacted artifacts, canonical manifests, and
  dispatch to prepare/validation stages.
- Paid commercial order/task/subscription calls are disabled by default. They require commercial
  readiness, an explicit operator flag, and source/provider-specific approval even if credentials
  are configured.
- AWiFS is allowed to run background search/download/prepare attempts while gated. If coverage
  validation fails, keep product exposure background-only/gated and record the validation failure;
  do not lower the threshold or activate AWiFS without a separate product decision.
- Legacy source-specific timers and the scheduler must not own the same source/AOI at the same
  time. Maintain a source-ownership/cutover matrix and rollback path while migrating timers.
- Best-observation selection and mixed-source timelines are post-scheduler work. Existing
  source-specific timelines stay authoritative until scheduler state and validation history are
  reliable enough for backend-owned ranking.
- Ingestion owns raw scheduler artifacts and the scheduler SQLite ledger under `/srv/akasha`.
  The BFF may read only redacted scheduler snapshots/job summaries through explicit read-only
  configuration; it must not expose raw provider archives, raw server paths, signed URLs,
  credentials, internal hostnames, or full logs.
- Scheduler jobs must calculate `nextDueAt` from scheduler job history and cadence, not from the
  legacy product ledger alone.
- Bhoonidhi non-dry-run scheduler work must pass approved-runtime preflights and run only through
  the staging-safe wrappers or an explicitly approved runtime. Dry-run/local-test modes may not
  download, prepare, upload, or register STAC.
- ResourceSat LISS-3 invariants are release-blocking for scheduler work: four BOA bands in
  `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`, FCC `NIR,RED,GREEN`, Akasha threshold mask
  v1 with `{1,4}` valid by default, reflectance scale `0.0001` and offset `0.0`, separate
  analytic/mask COGs, deterministic keys, STAC metadata preservation, and upsert behavior.

## AOI Rules

- `AOI_CONFIG_PATH` is the authoritative AOI input for the default deployment.
- `AOI_CONFIG_DIR` allows selecting additional AOIs by id for ingestion and
  composite commands.
- The launch AOI is `bangalore-60km`.
- AOI must be configurable; do not hard-code it into frontend or ingestion
  components.
- "Latest usable" means the newest date whose usable-pixel percentage is above
  the configured threshold and whose tile assets are available.

## ResourceSat LISS-3 COG Assets

Keep continuous reflectance and categorical masks as separate COG assets.

For each prepared ResourceSat scene or composite, create/register:

1. **Analytic reflectance COG**
   - Four raw uint16 BOA reflectance bands.
   - Common analysis grid from the AOI/composite configuration.
   - Continuous reflectance overviews use bilinear/cubic resampling.
   - Preserve source values; do not pre-stretch.

2. **Provisional mask COG**
   - One categorical uint8 band.
   - Nearest-neighbour resampling for base data and overviews.
   - Register as STAC asset `mask`.

### ResourceSat LISS-3 Band Order

| Position | Band | Meaning | Used for |
|---:|---|---|---|
| 1 | BAND2 | Green | FCC, NDWI_GREEN_NIR |
| 2 | BAND3 | Red | FCC, NDVI, MSAVI |
| 3 | BAND4 | NIR | FCC, NDVI, MSAVI, NDMI, NDWI_GREEN_NIR |
| 4 | BAND5 | SWIR1 | NDMI |

Default display mode is FCC using role order `NIR, RED, GREEN`, which resolves
to positional `bidx=3,2,1`. Do not reuse Sentinel RGB positions `[1,8,9]`.

### ResourceSat Reflectance

ResourceSat LISS-3 BOA COGs store raw uint16 DN with:

```text
scale  = 0.0001
offset = 0.0
physical_reflectance = raw * scale + offset
```

Do not apply Sentinel-2's `-0.1` offset to ResourceSat.

### ResourceSat Provisional Mask

The validated Bhoonidhi LISS-3 BOA sample did not include a native
quality/cloud/shadow raster. Akasha generates a provisional threshold mask.

| Value | Meaning | Default action |
|---:|---|---|
| 0 | gap/background/nodata | Exclude as nodata |
| 1 | valid optical pixel | Keep |
| 2 | cloud | Exclude |
| 3 | shadow | Exclude |
| 4 | water | Keep |

Default excluded classes are `0,2,3`. Metrics using this mask must expose
`metricsProvisional = true` and a clear `maskMethod`.

## Supported Index Formulas

The formula registry is source-agnostic, but each source advertises only indices
that its band roles support.

| Index id | Formula | ResourceSat LISS-3 roles |
|---|---|---|
| NDVI | (NIR - Red) / (NIR + Red) | BAND4, BAND3 |
| MSAVI | (2*NIR + 1 - sqrt((2*NIR + 1)^2 - 8*(NIR - Red))) / 2 | BAND4, BAND3 |
| NDMI | (NIR - SWIR1) / (NIR + SWIR1) | BAND4, BAND5 |
| NDWI_GREEN_NIR | (Green - NIR) / (Green + NIR) | BAND2, BAND4 |

ResourceSat LISS-3 must not advertise NDRE or RECI because it has no true
red-edge band. SAR sources must advertise no optical vegetation indices.

## Statistics Rules

Cloud/mask-aware index statistics are computed in the BFF with
rasterio/rio-tiler, not by plain TiTiler `/cog/statistics`. The BFF reads the
analytic COG window and the source mask COG window, applies scale/offset,
applies source-specific excluded mask classes, then computes statistics and
pixel percentages.

```text
totalPixels       = pixels intersecting the request geometry at source grid
nodataPixels      = out-of-coverage / nodata / mask class 0 pixels
coveragePixels    = totalPixels - nodataPixels
maskedPixels      = pixels excluded by source mask within coverage
validPixels       = coveragePixels - maskedPixels

validPixelPercent  = validPixels   / totalPixels * 100
cloudMaskedPercent = maskedPixels  / totalPixels * 100
coveragePercent    = coveragePixels / totalPixels * 100
```

For AOI-level latest-usable selection:

```text
usablePixelPercent = validPixels / coveragePixels * 100
```

## STAC Metadata Requirements

Every scene or composite item must include:

- Collection id, source id, acquisition date/datetime, AOI id where applicable.
- `proj` extension fields per asset where available.
- `eo:bands` and `raster:bands` in the exact source band order.
- `akasha:band_role_mapping` for source role lookup.
- `akasha:mask_asset`, `akasha:mask_method`, and excluded mask classes for
  optical mask-aware sources.
- Date-level coverage, usable, cloud/masked, provisional, and latest-usable
  fields when known.
- Asset roles:
  - `data` / `reflectance` for analytic COGs.
  - `metadata` / `data-mask` for mask COGs.
  - `backscatter` for SAR COGs.

## Object Key Rules

ResourceSat scene keys and item ids must be deterministic and idempotent. Use
source, AOI, acquisition date, and scene component in object paths so reruns do
not collide.

```text
s3://akasha-cogs/resourcesat-2a-liss3-boa/scene/{date}/{sceneComponent}/analytic.tif
s3://akasha-cogs/resourcesat-2a-liss3-boa/scene/{date}/{sceneComponent}/mask.tif

s3://akasha-cogs/resourcesat-2a-liss3-boa/composite/{aoiId}/{date}/analytic.tif
s3://akasha-cogs/resourcesat-2a-liss3-boa/composite/{aoiId}/{date}/mask.tif
```

Uploads skip existing keys unless the operator passes an explicit force flag.
STAC registration uses upsert semantics.

## Ingestion Pipeline

1. `worker.py bhoonidhi-search` discovers ResourceSat products for the selected
   AOI and records a coverage manifest.
2. `worker.py bhoonidhi-download` downloads selected products and updates the
   ingestion ledger.
3. `scripts/prepare_resourcesat_liss3_boa_cogs.py` converts native products to
   analytic + provisional mask COGs and writes a prepare manifest.
4. `worker.py ingest-manifest --method upsert` uploads COGs and registers STAC
   items.
5. `worker.py build-composite` builds AOI/date composites from validated scenes.
6. `worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi
  bangalore-60km` verifies the ResourceSat runtime composite COGs and dated STAC item.
  For SAR/context/archive sources, use the source-aware raster verification command
  defined by the ingestion roadmap instead of `verify-composite`.

## Date-Level Serving Rules

The BFF groups STAC items by `akasha:acquisition_date` or item datetime date.

- `/api/sources/{sourceId}/dates` returns date metadata newest first.
- `/api/layers/default` chooses the latest usable date and returns a same-origin
  tile template.
- `/api/tiles/{sourceId}/{acquisitionDate}/FCC/{z}/{x}/{y}.png` serves
  ResourceSat FCC tiles.
- ResourceSat composites are the preferred served item for a date when present.
- Multi-scene, non-composite dates return `MOSAIC_TILES_UNAVAILABLE` until a
  supported mosaic backend is configured.

Do not create one MapLibre raster layer per scene in the browser. The browser
must receive one source/date tile template from the BFF.

## Validation Checklist

- `rio cogeo validate` passes for every COG.
- `gdalinfo` confirms overviews, CRS, band count, dtype, scale/offset, and mask
  classes.
- STAC items validate against required extensions and source metadata.
- TiTiler renders a ResourceSat FCC PNG through the gateway.
- A known small polygon returns ResourceSat NDVI statistics matching an
  independent QGIS/notebook reference within agreed tolerance.
- `/api/sources` hides Sentinel by default and advertises ResourceSat limits.
- `/api/indices/statistics` rejects unsupported ResourceSat NDRE/RECI and all
  optical indices for SAR sources.
- Monitoring exposes latest catalog/composite date, successful search heartbeat,
  source status/reasons, storage usage, and ingestion ledger failures. Stale
  upstream data is a warning only when search is fresh and no newer Online=Y
  product exists; stale/missing searches, unresolved failures, low coverage,
  storage errors, and tile-unavailable active dates remain blockers.

## Legacy Sentinel Notes

Sentinel-2 L2A and Sentinel-1 GRD code may remain for regression or migration
checks. They are not production-selectable unless
`AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES=true`.

Sentinel-2 specifics:

- Analytic band order remains `[B04, B08, B05, B06, B07, B11, B12, B03, B02]`.
- True-colour RGB uses `[1,8,9]`.
- Reflectance offset is `-0.1`.
- SCL excluded classes are `0,1,2,3,7,8,9,10,11`; water class `6` is kept.
- Legacy object paths are under `sentinel-2-l2a/.../analytic.tif|scl.tif`.

SAR specifics:

- SAR sources are context/display sources until radar-specific analytics are
  designed.
- Do not run optical index formulas on SAR COGs.
- Register SAR items with radar-safe metrics and null optical cloud metrics.

## Storage and Retention

- Keep raw Bhoonidhi downloads temporary unless needed for audit/reprocessing.
- Retain the last configurable number of usable scenes/composites per source.
- Purge failed/partial conversion artifacts after review.
- Monitor MinIO volume usage and alert before disk pressure affects writes.
