---
goal: Integrate Landsat 8 and Landsat 9 Collection 2 Level-2 into Akasha ingestion and field monitoring
version: 1.0
date_created: 2026-07-19
last_updated: 2026-07-19
owner: Akasha engineering
tags: [feature, landsat, oli, collection-2, surface-reflectance, ingestion, field-analytics]
---

# Landsat 8/9 Collection 2 Level-2 integration

## 1. Purpose and release boundary

This is the authoritative cross-repository implementation and acceptance plan for
`akasha-ingestion` and `akasha-project`. It replaces the incomplete Landsat phase in the older
multi-source roadmap with a plan based on the current standalone ingestion API, product BFF, and
frontend contracts.

The first release will expose Landsat 8 and Landsat 9 as one logical user-facing optical source.
Both platforms have the same OLI-family surface-reflectance band roles, Collection 2 scaling, and
QA contract, and together provide an approximately eight-day offset cadence. Keeping one logical
source avoids duplicate UI entries and lets a field timeline naturally contain either platform
while preserving the actual platform in every observation's provenance.

Release 1 will:

- discover Landsat 8/9 Collection 2 Level-2 scenes through a cloud-native STAC provider;
- accept Tier 1 `L2SP` and `L2SR` products from platforms `landsat-8` and `landsat-9` only;
- mirror a bounded set of source COG assets through signed HTTPS;
- apply the official surface-reflectance scale and offset;
- decode `QA_PIXEL` and `QA_RADSAT` into an Akasha categorical quality mask;
- create a multiband analytic COG, a categorical mask COG, and supported field-index COGs;
- publish source dates, true-colour imagery, exact-field quality, statistics, clipped overlays,
  point values, trends, and exports through the existing same-origin product API;
- add Landsat to source-specific and best-available optical workflows without averaging or
  normalizing measurements across sensors; and
- stay hidden, manual-only, and fail-closed until all real-scene staging gates pass.

Surface temperature, thermal stress, evapotranspiration, pan-sharpening, Landsat 4/5/7, full
archive mirroring, crop recommendations, and cross-sensor numeric baselines are not included.

## 2. Research findings and architectural decisions

### 2.1 Authoritative product facts

Primary references:

- [USGS Landsat Collection 2 Level-2 science products](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products)
- [USGS Collection 2 surface reflectance](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-reflectance)
- [USGS Collection 2 quality-assessment bands](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands)
- [USGS scale-factor guidance](https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products)
- [USGS Landsat acquisition cadence](https://landsat.usgs.gov/landsat_acq)
- [Planetary Computer STAC access](https://planetarycomputer.microsoft.com/docs/quickstarts/reading-stac/)
- [Planetary Computer signed data access](https://planetarycomputer.microsoft.com/docs/concepts/sas/)

The fixed scientific contract is:

- surface reflectance is UInt16 with fill value `0`;
- corrected reflectance is `DN * 0.0000275 - 0.2`;
- OLI surface-reflectance pixels are 30 m;
- `QA_PIXEL` is bit-packed and supplies fill, dilated cloud, cirrus, cloud, shadow, snow, clear,
  water, and confidence flags;
- `QA_RADSAT` supplies per-band radiometric saturation and terrain occlusion; and
- each platform revisits every 16 days, with Landsat 8 and 9 offset by eight days.

A live metadata-only query on 2026-07-19 confirmed that both Earth Search and Planetary Computer
advertise collection `landsat-c2-l2`, current Landsat 8/9 items, common-name assets
`blue`, `green`, `red`, `nir08`, `swir16`, `swir22`, `qa_pixel`, `qa_radsat`, and the official
scale/offset metadata.

### 2.2 Provider decision

The primary v1 route is Planetary Computer:

`planetary-computer:landsat-c2-l2`

The catalog search is public. Asset URLs require short-lived SAS signing, which can be obtained
without placing a provider credential in the browser. The signing token is an ingestion-only
secret-like transport value: it must be requested just in time, used only by the worker, redacted
from logs/manifests, and never persisted in scene metadata or returned by an API.

Earth Search remains an inactive fallback route:

`earthsearch:landsat-c2-l2`

Its current Landsat asset HREFs are `s3://usgs-landsat/...` requester-pays objects. The existing
HTTP mirroring service cannot download them, and enabling requester-pays can incur cloud charges.
That route must remain fail-closed unless an operator explicitly enables requester-pays, supplies
approved AWS billing credentials, and validates the byte/cost cap. USGS M2M/EarthExplorer remains
a later official-download fallback, not the v1 implementation path.

### 2.3 Reuse and ownership

The implementation reuses concepts, not source-specific code:

| Existing path | Reused contract | Landsat-specific work |
|---|---|---|
| Sentinel-2 | STAC search, source COG mirroring, derived index COGs, signed field analytics | Platform filtering, signed provider HREFs, Collection 2 scale/offset, QA bit decoding |
| ResourceSat | Source profiles, analytic/mask separation, date-level quality, best-observation UI | Landsat band roles, true colour, WRS path/row, native QA rather than threshold mask |
| EOS-04/NISAR | Fail-closed activation and real-product gates | Optical APIs only; no SAR or polarization contracts |
| Product BFF | Server-to-server ingestion client, same-origin overlays, source/date consistency | Landsat flags, metadata, labels, limitations, best-optical priority |

Operational ownership stays in `akasha-ingestion`. The product application must not execute the
legacy `akasha-project/scripts/prepare_landsat_c2_l2_cogs.py` concept, access provider assets, or
read object storage directly.

## 3. Fixed identifiers and profiles

| Contract | Value |
|---|---|
| Logical source | `landsat-c2-l2` |
| User label | `Landsat 8/9 Collection 2 L2` |
| Provider collection | `landsat-c2-l2` |
| Primary provider route | `planetary-computer:landsat-c2-l2` |
| Inactive fallback | `earthsearch:landsat-c2-l2` |
| pgSTAC collection | `akasha-landsat-c2-l2-derived-v1` |
| Processing profile | `landsat-8-9-c2-l2-sr-qa-v1` |
| Mask profile | `landsat-c2-qa-mask-v1` |
| Selection policy | `field-selection-v2` |
| Source display | `RGB` |
| Analytic bands | `BLUE, GREEN, RED, NIR, SWIR1, SWIR2` |
| Native/processing resolution | 30 m |
| Reflectance formula | `DN * 0.0000275 - 0.2` |
| Derived-index encoding | Int16, scale `10000`, nodata `-32768` |
| Analytic nodata | Float32 `-9999.0` |
| Mask nodata | UInt8 `0` |

User-facing platform provenance must say `Landsat 8` or `Landsat 9`; it must never replace that
with the generic source label in observation metadata.

## 4. User experience and product behavior

### 4.1 Source selection

When enabled, the Layers source list contains one optical card:

**Landsat 8/9 Collection 2 L2 · USGS Landsat via Planetary Computer · 30 m**

The card must explain:

- open, atmospherically corrected surface reflectance;
- nominal combined eight-day cadence, subject to path/row coverage and provider availability;
- 30 m pixels are coarser than Sentinel-2 and LISS-4 and may mix small fields with surroundings;
- no red-edge band, therefore no NDRE/RECI; and
- cloud, cirrus, shadow, snow, fill, saturation, and terrain-occlusion filtering use native QA.

Default map mode is true-colour `RGB`. Index modes are `NDVI`, `MSAVI`, `NDMI`, and
`NDWI_GREEN_NIR`. `NDBI`, `NBR`, surface temperature, and thermal-stress copy remain hidden until
separate product semantics and visualization profiles are accepted.

### 4.2 Field timeline and cloud behavior

Scene-level `eo:cloud_cover` is a discovery/ranking hint, not the final field decision. A scene
that is globally cloudy may still contain a clear saved field. A date is shown as field-usable only
when native QA and analytic pixels prove:

- at least 95% exact-field spatial coverage;
- at least 80% usable common-band pixels; and
- less than 20% field obscuration from cloud, cirrus, shadow, or snow.

The timeline shows date, actual platform, 30 m resolution, field coverage, usable pixels, and field
obscuration. A date failing the field policy is unavailable and explains why. It is not silently
removed from operator/catalog views.

### 4.3 Statistics, overlays, trends, and exports

The existing field-index route remains the browser-facing contract. The BFF sends field geometry,
source, requested date, index, and cloud limit to ingestion. The returned overlay is clipped to the
field and proxied through the app origin. Statistics, point values, chart observations, CSV, and
GeoTIFF exports must preserve selected source, platform, acquisition date, processing profile,
QA-mask version, resolution, WRS path/row, collection category, and product ID.

Landsat values are valid source-specific measurements. They may be selected as the best available
observation but must not be averaged with Sentinel-2 or ResourceSat, and a trend must not switch
sensors without an explicit multi-source mode and visible provenance at every point.

### 4.4 Best-available optical mode

The current backend resolver remains authoritative. A Landsat observation can qualify only when it
supports the requested index and passes exact-field coverage/quality. Ranking is deterministic:

1. smallest absolute target-date offset;
2. higher usable-pixel percentage;
3. higher exact-field coverage;
4. lower field obscuration;
5. finer native resolution;
6. existing production-maturity source priority;
7. stable source ID/product ID tie-break.

The selected source and date must be pinned for tiles, overlays, statistics, points, charts, and
exports. The UI must never describe the selection as “highest accuracy”; it is the best qualified
observation under the recorded policy.

## 5. Provider and ingestion contract

### 5.1 Search and normalization

Create a Planetary Computer provider adapter with pagination, timeout/error categorization, token
refresh, and redaction. Search requests require AOI geometry/bbox, date range, collection, maximum
items, and optional scene-cloud hint. Normalize and validate:

- `platform in {landsat-8, landsat-9}`;
- ID prefix `LC08_` agrees with Landsat 8 and `LC09_` agrees with Landsat 9;
- correction/product token is `L2SP` or `L2SR`;
- collection number is `02`;
- collection category is `T1` for product exposure;
- acquisition datetime, geometry, bbox, WRS path/row, cloud cover, processing date, and instrument;
- required COG media type, scale, offset, nodata, and 30 m grid metadata; and
- required asset roles/common names.

Tier 2 and real-time products may be recorded in metadata-only operator results but must not enter
the product catalog in v1. Search output ordering is deterministic by acquisition date, Tier 1,
field/AOI intersection, lower scene cloud, platform, WRS path/row, and product ID.

### 5.2 Bounded access and storage

Each initial run may accept at most one new scene. Before mirroring, request a SAS token and replace
only the in-memory asset HREF. Persist the unsigned canonical HREF or a redacted asset identity,
never the signed query string. Enforce per-asset and per-run byte caps and required disk headroom.

Store provider metadata/manifests and mirrored COGs beneath deterministic Landsat keys. Bulk data
and scratch files stay under `/srv/akasha` on staging. Reruns reuse objects by checksum and do not
duplicate scenes, assets, outputs, tile layers, or pgSTAC items.

Supported modes are `metadata_only`, `mirror_only`, `prepare_only`, and `full_pipeline`.
`metadata_only` performs no token request and no asset read. Scheduling defaults disabled.

### 5.3 Idempotency

The idempotency key includes source, provider route, AOI, date range, mode, request-parameter
version, processing-profile version, and mask-profile version. A failed job can be retried with the
same identity after the existing job reaches a terminal state.

## 6. Processing contract

### 6.1 Required and optional source assets

Required for v1 processing:

- `blue`, `green`, `red`, `nir08`, `swir16`, `swir22`;
- `qa_pixel`; and
- `qa_radsat`.

`qa_aerosol` is optional evidence. If present, record valid/interpolated/high-aerosol percentages
and warnings; do not silently change the valid-pixel mask until a separately versioned aerosol
policy is accepted.

Every asset must be one-band, north-up, 30 m, and share CRS, transform, dimensions, and bounds after
bounded AOI clipping/reprojection. Continuous reflectance uses bilinear resampling only when a grid
alignment is necessary; QA uses nearest-neighbour.

### 6.2 Reflectance and band order

Treat DN `0` as invalid before applying scale/offset. For valid UInt16 pixels:

`reflectance = DN * 0.0000275 - 0.2`

Do not clamp negative reflectance to zero. Preserve finite physically possible values and let index
formula validation handle denominators. The analytic Float32 COG band order is:

1. `BLUE` / OLI B2
2. `GREEN` / OLI B3
3. `RED` / OLI B4
4. `NIR` / OLI B5
5. `SWIR1` / OLI B6
6. `SWIR2` / OLI B7

Band descriptions and STAC `eo:bands` must state the true OLI band/common name. Platform-specific
metadata must not change this logical order.

### 6.3 QA mask

Decode bits using unsigned integer operations. Mask class priority is deterministic:

| Class | Meaning | Source rule | Default use |
|---:|---|---|---|
| 0 | nodata/invalid | fill bit, missing analytic DN, selected-band saturation, terrain occlusion | exclude |
| 1 | valid land | no higher-priority condition | use |
| 2 | cloud/cirrus | dilated cloud, high cirrus, or high cloud bit | exclude |
| 3 | cloud shadow | high cloud-shadow bit | exclude |
| 4 | water | water bit with no higher-priority condition | use; report separately |
| 5 | snow/ice | snow bit | exclude and count as obscured |

For the six selected OLI bands, the matching `QA_RADSAT` band saturation bits invalidate a pixel;
terrain occlusion bit 11 also invalidates it. `QA_PIXEL` clear bit alone is insufficient because it
does not encode every exclusion and must not override cloud, shadow, snow, fill, or saturation.

### 6.4 Derived products

Write strict COGs with deterministic compression, block size, overviews, nodata, checksums, CRS,
transform, bounds, and tags:

- `analytic.tif`: six-band Float32 reflectance;
- `mask.tif`: one-band UInt8 categorical mask; and
- `ndvi.tif`, `msavi.tif`, `ndmi.tif`, `ndwi_green_nir.tif`: Int16 scaled indices.

All indices use common-band valid pixels plus mask classes `{1,4}`. Required formulas are:

- `NDVI = (NIR - RED) / (NIR + RED)`;
- `MSAVI = (2*NIR + 1 - sqrt((2*NIR + 1)^2 - 8*(NIR - RED))) / 2`;
- `NDMI = (NIR - SWIR1) / (NIR + SWIR1)`; and
- `NDWI_GREEN_NIR = (GREEN - NIR) / (GREEN + NIR)`.

Derived values are clipped to `[-1,1]` only at output encoding where the established profile
requires it. Zero/near-zero denominators become nodata.

### 6.5 Same-date scenes and mosaics

Register every WRS path/row scene independently. Field analytics may select one scene when that
scene alone covers at least 95% of the exact field. A date-level natural layer spanning multiple
scenes requires a deterministic mosaic: highest QA usability first, then lower field/AOI
obscuration, then stable platform/path/row/product ordering. Never average reflectance across
overlaps. Until that mosaic is implemented, a multi-scene natural date is typed unavailable while
single-scene field analytics may still qualify.

## 7. Catalog and API contract

The pgSTAC collection/item includes EO, projection, raster, classification, checksum, and Landsat
properties. Required provenance includes platform, instruments, collection number/category,
correction level, WRS path/row, acquisition/processing time, scene cloud, field quality, source and
provider route, processing/mask/formula versions, source checksums, and Akasha object lineage.

Ingestion APIs reuse:

- `POST /api/v1/ingestion/sync` with `landsat_backfill`;
- `GET /api/v1/readiness`;
- `POST /api/v1/analytics/field-dates`;
- `POST /api/v1/analytics/field-index`;
- signed stats, point, tile, and field-clipped overlay routes; and
- a source/date natural tile route once analytic mosaic support is ready.

Responses never expose Planetary Computer SAS tokens, provider HREFs, MinIO keys, S3 URLs,
internal service hosts, ingestion API keys, or raw query IDs to the browser.

## 8. Product BFF and frontend contract

Add fail-closed flags, default false:

- `INGESTION_LANDSAT_CUTOVER_ENABLED`
- `LANDSAT_PRODUCT_ENABLED`
- `LANDSAT_BEST_OPTICAL_ENABLED`

The source appears in `/api/sources` only when product/cutover flags are true and ingestion is
configured. Dates, field dates, statistics, overlays, points, trends, and exports use the existing
ingestion bridge. Natural tiles are proxied server-to-server and same-origin.

Frontend work is metadata-driven: add no Landsat-specific provider URLs or band math. Required UI
acceptance covers source card, RGB/index controls, 30 m badge, platform badge per date, native-QA
quality explanation, field-clipped overlay, statistics, chart, export, best-mode provenance,
unavailable/multi-scene states, and desktop/narrow layouts. NDRE/RECI and thermal controls must not
appear. Existing Sentinel-2, ResourceSat, EOS-04, and NISAR behavior must remain unchanged.

## 9. Work tracker

`Completed` means implemented and verified. External validation gates cannot be completed by unit
tests or synthetic fixtures.

### Phase 0 — Provider and real-scene readiness

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-001 | Record authoritative SR scale/offset, QA bits, product levels, platform IDs, and cadence. | Yes | 2026-07-19 |
| LANDSAT-002 | Run metadata-only Bangalore searches against Earth Search and Planetary Computer; record sanitized candidates and asset contracts. | Yes | 2026-07-19 |
| LANDSAT-003 | Select Planetary Computer signed HTTPS primary and document requester-pays fallback risk. | Yes | 2026-07-19 |
| LANDSAT-004 | Through the staging wrapper, mirror at most one qualified Tier 1 scene under `/srv/akasha`. | Yes | 2026-07-19 |
| LANDSAT-005 | Record source sizes/checksums and independently inspect all mirrored COG grids/metadata. | Yes | 2026-07-19 |

### Phase 1 — Standalone contracts

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-101 | Add source/provider/catalog/profile/mask constants and typed output profiles. | Yes | 2026-07-19 |
| LANDSAT-102 | Add hidden, manual-only source and primary/fallback provider routes. | Yes | 2026-07-19 |
| LANDSAT-103 | Add `landsat_backfill` request validation, modes, caps, and versioned idempotency. | Yes | 2026-07-19 |
| LANDSAT-104 | Add fail-closed settings, deployment env contracts, queues, and schedule-disabled task. | Yes | 2026-07-19 |
| LANDSAT-105 | Add Planetary Computer search/signing adapter with URL redaction and token refresh. | Yes | 2026-07-19 |

### Phase 2 — Processor

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-201 | Validate Landsat 8/9 identity, Tier 1 L2 product, required assets, scale/offset, and grid. | Yes | 2026-07-19 |
| LANDSAT-202 | Implement SR conversion without invalid zero scaling or negative-reflectance clamping. | Yes | 2026-07-19 |
| LANDSAT-203 | Implement `QA_PIXEL`/`QA_RADSAT` mask decoding and class-priority tests. | Yes | 2026-07-19 |
| LANDSAT-204 | Write and strictly validate analytic, mask, and four index COGs. | Yes | 2026-07-19 |
| LANDSAT-205 | Produce bounded manifest with checksums, QA counts, WRS/platform, versions, and redaction. | Yes | 2026-07-19 |
| LANDSAT-206 | Independently validate output pixels and QA counts against one real scene. | Yes | 2026-07-19 |

### Phase 3 — Ingestion, storage, and pgSTAC

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-301 | Implement search -> sign/mirror -> prepare -> validate -> register -> pgSTAC pipeline. | Yes | 2026-07-19 |
| LANDSAT-302 | Add deterministic object keys and scene/asset/raster/tile registrations. | Yes | 2026-07-19 |
| LANDSAT-303 | Add Landsat-specific EO/projection/raster/classification/checksum pgSTAC collection/item. | Yes | 2026-07-19 |
| LANDSAT-304 | Implement single-scene field resolution and typed multi-scene natural unavailability. | Yes | 2026-07-19 |
| LANDSAT-305 | Prove replay and worker-recovery idempotency with real staging data. | Yes | 2026-07-19 |

### Phase 4 — Ingestion analytics APIs

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-401 | Generalize source-aware index validation, mask policies, native resolution, versions, and provider provenance. | Yes | 2026-07-19 |
| LANDSAT-402 | Return field dates using 95% coverage, 80% usability, and <20% obscuration. | Yes | 2026-07-19 |
| LANDSAT-403 | Validate statistics, clipped overlay, point, trend, and signed URL behavior. | Yes | 2026-07-19 |
| LANDSAT-404 | Add RGB natural date/tile service for a qualified single-scene date. | Yes | 2026-07-19 |

### Phase 5 — Product BFF and frontend

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-501 | Add three fail-closed flags and same-origin ingestion cutover. | Yes | 2026-07-19 |
| LANDSAT-502 | Add source registry metadata, supported modes/indices, limitations, and attribution. | Yes | 2026-07-19 |
| LANDSAT-503 | Proxy dates, RGB, field analytics, points, trends, and exports without internal URL exposure. | Yes | 2026-07-19 |
| LANDSAT-504 | Add qualified Landsat candidates to best-optical selection and pin source/date downstream. | Yes | 2026-07-19 |
| LANDSAT-505 | Add source/date/platform/30 m/QA UI copy and disabled NDRE/thermal behavior. | Yes | 2026-07-19 |
| LANDSAT-506 | Capture desktop and narrow-layout staging acceptance screenshots. | Yes | 2026-07-19 |

### Phase 6 — Verification and activation

| Task | Description | Completed | Date |
|---|---|---|---|
| LANDSAT-601 | Run provider, processor, QA, COG, pipeline, API, BFF, frontend, security, and regression suites. | Yes | 2026-07-19 |
| LANDSAT-602 | Run full lint/tests/builds in both repositories. | Yes | 2026-07-19 |
| LANDSAT-603 | Pass staging Gates 1-13 and enable all three flags in staging. | Yes | 2026-07-19 |
| LANDSAT-604 | Promote the accepted image to production only after production is provisioned. | Blocked - production not provisioned | 2026-07-19 |

## 10. Required automated cases

Tests must cover platform/ID conflicts, Landsat 4/5/7 rejection, Tier 2/RT rejection, L2 identity,
missing assets, wrong scale/offset/nodata/resolution, signed URL expiry/redaction, pagination,
rate-limit/timeouts, reflectance vectors, DN zero exclusion, negative reflectance preservation,
every QA bit and class-priority combination, per-band saturation, terrain occlusion, grid mismatch,
nearest QA resampling, formula vectors, zero denominators, COG structure/overviews/descriptions,
byte/download caps, idempotency, partial failure/recovery, pgSTAC metadata, 95% field coverage,
80% usability, 20% obscuration, single/multi-scene dates, overlays/points/trends/exports, same-origin
proxying, flag combinations, best-source ranking, source/date pinning, unsupported NDRE/thermal,
small-field resolution warning, desktop/narrow UI, and regressions for all existing sources.

## 11. Staging activation gates

| Gate | Acceptance evidence | Completed | Date |
|---:|---|---|---|
| 1 | Planetary Computer metadata-only Bangalore search succeeds and returns Landsat 8/9 Tier 1 candidates. | Yes | 2026-07-19 |
| 2 | One capped real scene is mirrored through the approved staging wrapper with no signed URL persisted. | Yes | 2026-07-19 |
| 3 | Independent inspection confirms required bands, scale/offset, QA, CRS, 30 m grid, WRS, and platform. | Yes | 2026-07-19 |
| 4 | Analytic, mask, and index COGs pass strict validation. | Yes | 2026-07-19 |
| 5 | Sampled reflectance and index values match an independent calculation. | Yes | 2026-07-19 |
| 6 | QA class and valid-pixel counts match an independent bit-decoding check. | Yes | 2026-07-19 |
| 7 | Object storage, relational catalog, and pgSTAC contain exactly the expected registrations. | Yes | 2026-07-19 |
| 8 | Authenticated dates, field dates, RGB, statistics, overlay, point, trend, and export routes pass. | Yes | 2026-07-19 |
| 9 | Product BFF returns same-origin URLs and exposes no provider/internal storage details. | Yes | 2026-07-19 |
| 10 | A saved staging field passes 95% coverage and produces non-empty clipped output. | Yes | 2026-07-19 |
| 11 | Best-optical selection and downstream source/date pinning match `field-selection-v2`. | Yes | 2026-07-19 |
| 12 | Desktop and narrow screenshots pass, including 30 m/no-red-edge limitations. | Yes | 2026-07-19 |
| 13 | Identical replay creates no duplicate job outputs, objects, records, layers, or STAC items. | Yes | 2026-07-19 |
| 14 | Enable all three Landsat flags in staging only after Gates 1-13. | Yes | 2026-07-19 |
| 15 | Promote the accepted images and configure production scheduling after production is provisioned. | Blocked - production not provisioned | 2026-07-19 |

### 2026-07-19 staging acceptance evidence

- Accepted ingestion image: `6f37219f2981ae33e9bb4676e981d2e6ad007edd`.
- Accepted product web/API image: `0518fe6894de19a70283007352100aca01677121`.
- Real capped validation job `c8d90b89-d54c-4238-bc97-c7e6a646bfd2` searched 82
  candidates, mirrored one new Tier 1 scene (8 assets, 563,989,516 bytes), produced six
  prepared outputs, skipped 81 candidates under the one-download cap, and completed with zero
  failures.
- The catalog contains a typed multi-scene RGB-unavailable date (`2026-02-12`, two scenes) and a
  single-scene RGB-available date (`2026-02-04`, one scene). The product defaults to the latter.
- Live authenticated BFF checks returned `200` for source dates, field dates, RGB PNG, field
  statistics, clipped overlay PNG, point lookup, trend, index CSV, report CSV, and best-observation
  selection. The saved acceptance field returned 100% exact-field coverage.
- Browser-facing payload inspection found no ingestion hostname, private address, object-storage
  path, or signed-query fields. Temporary acceptance fields, users, teams, and sessions were
  removed after validation.
- Desktop and 390-pixel narrow browser passes selected Landsat, `2026-02-04`, and true colour;
  both visibly showed 30 m pixels, the mixed-pixel warning, and the lack of OLI red-edge support,
  with no browser page errors. Evidence artifacts: `landsat-live-desktop-final.png` and
  `landsat-live-narrow-final.png`.
- The Landsat scheduler is registered at `03:00 UTC` daily in `full_pipeline` mode, is capped at
  one new scene per run, retains the configured 20 GiB free-space guard, and reports lifecycle
  `scheduled`, product exposure `public`, and validation state `accepted`.

## 12. Rollout, rollback, and operations

Rollout order is ingestion code with source hidden, metadata-only validation, one-scene mirror,
processor validation, catalog/API validation, BFF code with flags false, frontend validation, Gates
1-13, then staging flags. Rollback is all three product flags false; cataloged data may remain for
forensics and reactivation. Never delete bulk staging data during rollback unless an operator
explicitly approves the exact recoverable targets.

Staging routine scheduling was approved on 2026-07-19 after bounded real-scene runs established
bandwidth, storage, token, and processing behavior. It remains capped at one new scene per run with
the storage headroom guard active. Production scheduling must be configured when the production
instance is provisioned. Archive requests must remain date-bounded and quota-aware; the UI must not
trigger an unbounded historical backfill.

## 13. Explicit assumptions and non-goals

- `landsat-c2-l2` is one logical source containing Landsat 8 and 9 observations.
- USGS Collection 2 is the scientific product; Planetary Computer is the cloud access route.
- Tier 1 is required for product exposure in v1.
- No database schema migration is expected; existing source, route, scene, asset, raster, job,
  field-query, tile-layer, and pgSTAC structures are reused.
- No NDRE/RECI is possible because OLI has no red-edge band.
- No thermal product, land-surface-temperature claim, evapotranspiration, irrigation advice,
  pan-sharpening, NBR/fire product, NDBI/urban product, or scouting recommendation is included.
- No cross-sensor averaging or claim that one optical sensor is universally more accurate.
- Existing unrelated worktree changes and all EOS-04/NISAR acceptance evidence must be preserved.
