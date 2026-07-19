---
goal: Integrate NISAR S-SAR Beta GCOV as bounded radar imagery and field evidence
version: 1.0
date_created: 2026-07-19
last_updated: 2026-07-19
owner: Akasha engineering
tags: [feature, nisar, ssar, gcov, sar, bhoonidhi, ingestion, field-analytics]
---

# NISAR S-SAR Beta GCOV integration

## 1. Purpose and release boundary

This document is the authoritative cross-repository implementation and acceptance plan for
`akasha-ingestion` and `akasha-project`. It supersedes the earlier assumption that scouting or
provider data availability blocks engineering work. Bhoonidhi now advertises
`NISAR_SSAR-Beta_GCOV`; activation is blocked only by the real-product gates in this document.

The first release will:

- acquire one product at a time from Bhoonidhi;
- convert validated S-band L2 GCOV diagonal covariance power to multiband Float32 Gamma0 dB COG;
- publish acquisition dates and a generic `BACKSCATTER` layer;
- return one-date, exact-field HH/HV (or the actual available polarization set) statistics and a
  signed, field-clipped overlay;
- automatically choose the best qualified EOS-04 or NISAR observation without combining sensors;
- remain hidden and manual-only until the complete staging gate is passed, then promote the exact
  staging-validated image to production.

Scheduled preload, multi-scene mosaics, NISAR history, temporal/cross-sensor comparison,
recommendations, scouting decisions, biomass inference, and soil-moisture retrieval are not part of
this release.

## 2. External evidence and fixed identifiers

Provider references:

- [Bhoonidhi NISAR products](https://bhoonidhi.nrsc.gov.in/NISAR/NisarProducts.html)
- [Bhoonidhi API collections](https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/)
- [NISAR Data Product Format Specification v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf)

The implementation uses these versioned identifiers:

| Contract | Value |
|---|---|
| Product source | `nisar-ssar-beta-gcov` |
| Bhoonidhi collection | `NISAR_SSAR-Beta_GCOV` |
| Provider route | `bhoonidhi:NISAR_SSAR-Beta_GCOV` |
| pgSTAC collection | `akasha-nisar-ssar-beta-gcov-backscatter-v1` |
| Processing profile | `nisar-ssar-beta-gcov-gamma0-v1` |
| Selection policy | `radar-support-selection-v1` |
| Output asset key | `backscatter` |
| Output type/scale | Float32 Gamma0 dB |
| Output nodata | `-9999.0` |
| Default display rescale | `-25,5` |
| Display mode | `BACKSCATTER` |

Routine non-beta GCOV products must not silently enter this profile. They require a new provider
collection mapping and a separately validated processing-profile version.

## 3. Current repository implementation

### 3.1 `akasha-ingestion`

- `src/akasha/processing/nisar.py` owns HDF5 discovery, metadata validation, masked windowed
  conversion, COG output, validation, and the bounded manifest.
- `src/akasha/services/nisar_ingestion.py` owns the capped Bhoonidhi pipeline and persistence.
- `src/akasha/jobs/nisar_tasks.py` and the Celery router send NISAR preparation to the heavy worker.
- `nisar_backfill` supports `metadata_only`, `download_only`, `prepare_only`, and `full_pipeline`.
- The source registry and seed catalog define a hidden, manual-only source with no schedule.
- Natural imagery and field-SAR services use per-source radar profiles, preserving EOS-04 temporal
  behavior while rejecting NISAR history.
- pgSTAC registration uses a NISAR-specific collection and radar-safe item metadata.

### 3.2 `akasha-project`

- The BFF has three fail-closed flags: `INGESTION_NISAR_CUTOVER_ENABLED`,
  `NISAR_PRODUCT_ENABLED`, and `NISAR_FIELD_SUPPORT_ENABLED`.
- Natural dates and tiles are proxied server-to-server; the browser receives same-origin URLs.
- The field evidence resolver evaluates each enabled radar source and uses
  `radar-support-selection-v1`.
- The same-origin overlay route accepts `sourceId` and forwards the selected source explicitly.
- NISAR uses `BACKSCATTER`; EOS-04 retains its existing `VV_GRAYSCALE` compatibility token.
- The frontend names NISAR as S-band radar evidence, shows the actual display polarization, and
  states that radar evidence is neither NDVI nor direct soil moisture.

### 3.3 Activation state

Code completion alone does not activate the product. The application defaults remain fail-closed
and scheduling remains disabled. Staging activation is authorized only after the real-product gates
recorded below; production must use the same immutable product image accepted in staging.

## 4. HDF5 processing contract

### 4.1 Science-file selection

Safe ZIP extraction must reuse path-traversal, member-count, and expanded-size protections. Exactly
one HDF5 file may qualify as the main science file. Its metadata must identify:

- mission/platform `NISAR`;
- instrument/platform `SSAR`;
- processing level `L2`;
- product type `GCOV`;
- radar band `S`; and
- a science group at `/science/SSAR/GCOV`.

Ambiguous files, QA/browse-only packages, missing identification, L-band-only files, and
filename/metadata conflicts fail closed.

### 4.2 Required datasets and metadata

Read `/science/SSAR/identification`, `/science/SSAR/GCOV/grids/frequencyA`, and relevant processing,
calibration, RTC, projection, and source-data metadata. `listOfPolarizations` and
`listOfCovarianceTerms` are authoritative. A band must never be inferred from array order.

Only real diagonal terms are accepted:

| Covariance term | Output polarization |
|---|---|
| `HHHH` | `HH` |
| `HVHV` | `HV` |
| `VHVH` | `VH` |
| `VVVV` | `VV` |

Complex off-diagonal terms are ignored in v1. Output bands follow `HH, HV, VH, VV`, limited to
terms actually declared and present.

### 4.3 Numeric and mask rules

- Require radiometric terrain correction and Gamma0 normalization.
- Treat the diagonal covariance values as linear Gamma0 power.
- Convert valid values using `10 * log10(value)`.
- Non-finite, zero, and negative values become nodata; no epsilon clamp is permitted.
- Mask values `1..numberOfSubSwaths` are valid.
- Mask values `0`, `255`, and values outside the sub-swath range are invalid.
- Every selected covariance layer and the mask must have the same shape, grid, and projection.
- Coordinate arrays must be regular and compatible with their declared spacing.
- CRS comes from product projection/EPSG metadata; it must not be guessed from filenames.

Required numeric test vectors are `1.0 -> 0 dB`, `0.1 -> -10 dB`, and `0.01 -> -20 dB`.

### 4.4 COG and manifest

Processing is windowed; complete science arrays must not be loaded into memory. The output is one
multiband `backscatter.tif` with Float32 type, `-9999.0` nodata, 512-pixel tiling where dimensions
allow it, DEFLATE compression, average overviews, band descriptions containing the real
polarization, and strict COG validation.

The manifest retains checksums, valid-pixel counts, bbox/geometry, CRS, resolution, acquisition
interval, polarizations/order, track/frame, pass/look direction, processing/specification versions,
RTC/correction flags, polarization symmetrization, and source normalization. It must not retain
provider credentials, signed URLs, large arrays, or unbounded raw metadata.

## 5. Ingestion and catalog contract

The bounded pipeline is:

`search -> download -> prepare -> validate -> object storage -> scene/asset registration -> pgSTAC`

- Only online AOI-intersecting products are eligible.
- Selection is deterministic and each run may download at most one new product.
- Raw and prepared object keys include the NISAR source and deterministic product identity.
- One accepted scene registers one `backscatter` asset with explicit polarization metadata.
- pgSTAC contains SAR, projection, raster, checksum, orbit, track/frame, processing, and Akasha
  provenance fields.
- Optical cloud metrics, reflectance bands, vegetation indices, optical masks, and optical roles are
  forbidden.
- Idempotency includes source, AOI, date window, provider route, mode, and processing profile.
- Replays must not duplicate an object, scene, asset, or pgSTAC item.

## 6. API contracts

Ingestion routes:

- `GET /api/v1/sources/{sourceId}/dates`
- `GET /api/v1/sources/{sourceId}/dates/{date}/tiles/{z}/{x}/{y}.png`
- `POST /api/v1/analytics/field-sar`
- `GET /api/v1/analytics/field-sar/{queryId}/overlay.png`

NISAR dates report radar semantics, scene count, bounds, and explicit polarizations. Optical quality
fields remain null. A date with more than one scene is typed unavailable until a mosaic policy is
implemented. Natural tiles display HH when present, otherwise the first registered polarization,
and return the actual polarization in metadata.

NISAR field requests require `includeHistory=false`; history returns typed HTTP 422. Exact-field
geometry limits, signed overlays, query retention, cache behavior, 95% coverage, and common-band
validity follow the EOS-04 service. Responses contain all available polarization statistics,
derived cross-polarization features such as `HH_MINUS_HV_DB`, and NISAR provenance.

The product BFF exposes NISAR only when product, cutover, and ingestion configuration gates pass.
No ingestion URL, signed URL, object key, credential, or query ID reaches the browser.

## 7. Automatic radar selection

`radar-support-selection-v1` is deterministic:

1. Request every enabled field-support source independently.
2. Discard unavailable, unqualified, and less-than-95%-coverage observations.
3. Prefer the smallest absolute target-date offset.
4. Break ties with higher exact-field coverage.
5. Break remaining ties in favor of EOS-04 because it is the mature production source.
6. Return only one source. Never merge, average, normalize, or compare C-band and S-band values.
7. Return selected source, platform, displayed polarization, and policy provenance.
8. Put the selected `sourceId` into the same-origin overlay URL so the overlay cannot switch sensor.

## 8. Frontend contract

- Label selected NISAR evidence as “NISAR S-band radar evidence”.
- Use the generic “Backscatter” map layer and identify the actual displayed polarization.
- Show available HH/HV (or actual polarization) field statistics, coverage, confidence, date, and
  provenance.
- Explain that backscatter is structural/moisture-sensitive evidence, not NDVI or direct soil
  moisture.
- Hide optical indices/cloud controls, temporal comparison, and recommendation copy for NISAR.
- Preserve EOS-04 labels and temporal behavior.
- Accept desktop and narrow layout screenshots before staging activation.

## 9. Work tracker

`Completed` records implemented-and-reviewed code or an observed external gate. Blank entries remain
release work; code completion alone does not complete real-product or activation gates.

### Phase 0 — Real-product readiness

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-001 | Metadata-only Bangalore AOI search; record count, dates, footprints, online state, and sanitized IDs. | Yes | 2026-07-19 |
| NISAR-002 | Download at most one intersecting product through the staging wrapper under `/srv/akasha`. | Yes | 2026-07-19 |
| NISAR-003 | Record archive byte size and SHA-256 without committing product data. | Yes | 2026-07-19 |
| NISAR-004 | Inspect with `h5ls`, `h5dump`, `gdalinfo`, and a bounded Python inspector. | Yes | 2026-07-19 |
| NISAR-005 | Prove the science file contains `/science/SSAR/GCOV`, not only QA/browse content. | Yes | 2026-07-19 |
| NISAR-006 | Record identification, polarizations, covariance, masks, grid, CRS, resolution, Gamma0, RTC, versions, orbit, track/frame, and interval. | Yes | 2026-07-19 |

If Bangalore has no scene, a bounded Indian validation AOI may validate the processor. Product
activation still requires a real scene overlapping the configured product AOI and a saved staging
field.

### Phase 1 — Standalone ingestion contracts

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-101 | Add fixed source/provider/catalog/profile/nodata/rescale constants. | Yes | 2026-07-19 |
| NISAR-102 | Seed hidden manual-only source and capabilities. | Yes | 2026-07-19 |
| NISAR-103 | Add validated `nisar_backfill` modes and exact provider route. | Yes | 2026-07-19 |
| NISAR-104 | Add one-download preload cap with scheduling disabled. | Yes | 2026-07-19 |
| NISAR-105 | Route NISAR processing to the heavy worker without optical stages. | Yes | 2026-07-19 |
| NISAR-106 | Add versioned deterministic idempotency. | Yes | 2026-07-19 |

### Phase 2 — HDF5 processor

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-201 | Add source-owned processor and `h5py` worker dependency. | Yes | 2026-07-19 |
| NISAR-202 | Enforce safe extraction and exactly one qualified S-band L2 GCOV science file. | Yes | 2026-07-19 |
| NISAR-203 | Parse authoritative polarizations/covariance terms; diagonal terms only. | Yes | 2026-07-19 |
| NISAR-204 | Enforce RTC/Gamma0 and linear-power-to-dB numeric rules. | Yes | 2026-07-19 |
| NISAR-205 | Enforce native mask, shared grid, validated coordinates, and product CRS. | Yes | 2026-07-19 |
| NISAR-206 | Write windowed multiband COG and bounded audit manifest. | Yes | 2026-07-19 |
| NISAR-207 | Validate processor against a real Bhoonidhi HDF5 product. | Yes | 2026-07-19 |

### Phase 3 — Ingestion, storage, and catalog

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-301 | Implement capped search-to-pgSTAC NISAR service. | Yes | 2026-07-19 |
| NISAR-302 | Add deterministic raw/prepared object keys and registrations. | Yes | 2026-07-19 |
| NISAR-303 | Add SAR-safe NISAR pgSTAC collection and item. | Yes | 2026-07-19 |
| NISAR-304 | Prove no-duplicate replay using a real staging product. | Yes | 2026-07-19 |
| NISAR-305 | Keep schedule manual and source hidden after code completion. | Yes | 2026-07-19 |

### Phase 4 — APIs and field evidence

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-401 | Generalize natural dates/tiles through per-source SAR profiles. | Yes | 2026-07-19 |
| NISAR-402 | Generalize field-SAR source union and reject NISAR history. | Yes | 2026-07-19 |
| NISAR-403 | Return source-specific polarization statistics, features, and provenance. | Yes | 2026-07-19 |
| NISAR-404 | Validate dates, tile, statistics, and overlay with a saved staging field. | Yes | 2026-07-19 |

### Phase 5 — Product BFF and frontend

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-501 | Add three fail-closed deployment flags. | Yes | 2026-07-19 |
| NISAR-502 | Add NISAR natural cutover and `BACKSCATTER`, preserving EOS-04 mode. | Yes | 2026-07-19 |
| NISAR-503 | Add same-origin date/tile/field overlay proxying with source pinning. | Yes | 2026-07-19 |
| NISAR-504 | Implement `radar-support-selection-v1`. | Yes | 2026-07-19 |
| NISAR-505 | Generalize radar UI copy, display polarization, legend, and attribution. | Yes | 2026-07-19 |
| NISAR-506 | Capture accepted desktop and narrow-layout staging screenshots. | Yes | 2026-07-19 |

### Phase 6 — Automated verification

| Task | Description | Completed | Date |
|---|---|---|---|
| NISAR-601 | Synthetic parser, conversion, mask, invalid metadata, grid, and covariance tests. | Yes | 2026-07-19 |
| NISAR-602 | COG type/nodata/bands/CRS/transform/checksum/overview/content tests. | Yes | 2026-07-19 |
| NISAR-603 | Pipeline cap/idempotency/failure/recovery/redaction/catalog tests. | Yes | 2026-07-19 |
| NISAR-604 | Ingestion dates/tiles/field/history/multi-scene/optical-rejection tests. | Yes | 2026-07-19 |
| NISAR-605 | BFF flags/proxy/selection/tie/overlay/non-exposure tests. | Yes | 2026-07-19 |
| NISAR-606 | Frontend copy/polarization/unavailable/disabled-control/EOS regression tests. | Yes | 2026-07-19 |
| NISAR-607 | Full lint, tests, and builds in both repositories. | Yes | 2026-07-19 |

## 10. Required automated cases

The minimum suite includes valid HH/HV, valid single-pol, malformed identification, missing mask,
invalid RTC, wrong band, ambiguous science files, mismatched grids, invalid coordinates,
off-diagonal exclusion, all three numeric conversion vectors, mask 0/255 exclusion, COG structure,
one-download caps, replay idempotency, stage recovery, error redaction, pgSTAC correctness, dates,
BACKSCATTER tiles, exact-field statistics, signed overlays, NISAR-history 422, multi-scene
unavailability, optical-index rejection, all flag combinations, sensor selection/ties, source-pinned
overlay, secret non-exposure, NISAR copy/polarization, unavailable UI, narrow layout, and EOS-04
regressions.

## 11. Operational runbook

1. Run `nisar_backfill` in `metadata_only` for the configured Bangalore AOI.
2. Review sanitized search evidence and choose the deterministic online intersecting candidate.
3. Use `download_only`; verify the one-product cap, byte size, and SHA-256 under `/srv/akasha`.
4. Independently inspect the package and record NISAR-004 through NISAR-006.
5. Use `prepare_only`; compare sampled COG values and mask counts with independent HDF5 reads.
6. Use `full_pipeline`; verify exactly one raw object, prepared object, scene, asset, and STAC item.
7. Replay the identical job and prove all counts are unchanged.
8. Exercise authenticated dates, tile, field statistics, and overlay against a saved field.
9. Exercise automatic selection with both EOS-04 and NISAR enabled.
10. Capture desktop and narrow screenshots.
11. Record all evidence in this document before changing any staging flag.

## 12. Staging activation gates

| Gate | Acceptance evidence | Completed | Date |
|---|---|---|---|
| 1 | Metadata-only provider search succeeds. | Yes | 2026-07-19 |
| 2 | One capped real-product download passes integrity checks. | Yes | 2026-07-19 |
| 3 | Independent inspection confirms HDF5 structure and metadata. | Yes | 2026-07-19 |
| 4 | Prepared COG passes strict validation. | Yes | 2026-07-19 |
| 5 | Sampled dB values match independent raw-HDF calculation. | Yes | 2026-07-19 |
| 6 | Masked pixels and valid-pixel counts match independently. | Yes | 2026-07-19 |
| 7 | Object storage, relational catalog, and pgSTAC each contain exactly one registration. | Yes | 2026-07-19 |
| 8 | Authenticated ingestion dates, tiles, field statistics, and overlay pass. | Yes | 2026-07-19 |
| 9 | Product BFF exposes only same-origin URLs. | Yes | 2026-07-19 |
| 10 | Saved field has at least 95% coverage and a non-empty clipped overlay. | Yes | 2026-07-19 |
| 11 | EOS-04/NISAR automatic selection matches `radar-support-selection-v1`. | Yes | 2026-07-19 |
| 12 | Desktop and narrow screenshots pass. | Yes | 2026-07-19 |
| 13 | Identical replay creates no duplicates. | Yes | 2026-07-19 |
| 14 | Enable all three NISAR flags in staging only after Gates 1–13. | Yes | 2026-07-19 |
| 15 | Promote the exact accepted image to production with all three flags enabled; keep scheduled preload disabled. | Blocked — production service not provisioned | 2026-07-19 |

## 13. Assumptions and non-goals

- Bhoonidhi is the only v1 provider; ASF/Earthdata is a later provider-normalization effort.
- HH is preferred for display when present.
- Existing scene, asset, raster, job, and field-query structures are reused; no schema migration is
  expected.
- NISAR and EOS-04 measurements are sensor-specific and must not share a baseline or comparison.
- No mosaicking, temporal comparison, cross-sensor baseline, soil-moisture retrieval, biomass
  inference, irrigation advice, crop-health claim, scouting recommendation, or production schedule
  is included.
- Existing unrelated worktree changes and the EOS-04 Gate 3F scouting-data deferral must be
  preserved.

## 14. Implementation verification recorded on 2026-07-19

- `akasha-ingestion`: Ruff passed; 311 tests passed; Docker Compose configuration validated.
- Product API: 489 tests passed and 11 were skipped by their existing environment gates.
- Product repository root: 942 tests passed and 1 was skipped.
- Frontend: ESLint completed with four pre-existing warnings and no errors; 402 tests passed;
  TypeScript and the Vite production build passed.
- Slice 1 catalog validation: 227 checks passed and 0 failed.

### 14.1 Real-product acceptance evidence

- Metadata-only job `ab6e6f67-9130-4e13-b2df-e885a6ca2fff` found one online,
  AOI-intersecting scene acquired on 2026-01-03.
- The provider object is a direct HDF5 product of 11,352,015,126 bytes with SHA-256
  `2d9151d1be77e0af99a2a8d75201508daee81ba3697f79a681babcad234eb89f`.
- Independent tools confirmed S-band L2 GCOV, HH/HV diagonal terms, EPSG:32644, 10 m spacing,
  Gamma0 input, RTC, ascending track 84/frame 9, and product specification 1.2.1.
- Full-pipeline job `59786314-393e-4420-94a4-70386c5891f5` completed one search, download,
  preparation, validation, storage, relational registration, and pgSTAC registration.
- The 5,796,290,993-byte BigTIFF COG passes strict validation without warnings. It has Float32
  HH/HV bands, `-9999.0` nodata, 512-pixel DEFLATE tiles, and six average-overview levels.
- Same-pixel raw-to-COG comparisons matched within `2.6e-7 dB`; mask-255 pixels remained nodata.
  Full-grid independent counts matched at 623,274,430 valid pixels per band with zero mismatches.
- Catalog counts are exactly one scene, one backscatter asset, and one NISAR pgSTAC item. An
  identical replay returned the original completed job and left all counts at one.
- The saved staging validation field returned 100% coverage over 496 common valid pixels, high
  confidence, HH/HV statistics, `HH_MINUS_HV_DB`, and a non-empty signed clipped PNG overlay.
- Authenticated dates and BACKSCATTER tile routes passed; NISAR history and optical NDVI requests
  returned typed HTTP 422 responses.

### 14.2 Live product and deployment acceptance evidence

- The final accepted staging image is merge SHA
  `0e4985b52a11adca32e0b8a86c67f511d608de8f`. The API and web containers reported that exact
  immutable image revision and reached healthy state. The three staging NISAR flags are `true`;
  scheduled preload remains disabled.
- The authenticated BFF response exposed a same-origin overlay path only. Response inspection found
  no ingestion origin, object key, signed URL, query ID, credential, or signature leakage.
- With ResourceSat-2A AWiFS on 2026-01-02 as the usable optical observation, the resolver evaluated
  both `eos-04-sar-mrs-l2b` and `nisar-ssar-beta-gcov`, qualified NISAR, and selected its 2026-01-03
  pass under `radar-support-selection-v1`. The selected field had 100% common-band coverage and high
  confidence, and the displayed polarization was HH.
- The source-pinned same-origin overlay returned HTTP 200, `image/png`, a 5,804-byte payload, and a
  valid PNG signature. The browser showed the radar overlay and did not silently switch sensors.
- Accepted screenshot evidence:
  [desktop 1440x1000](./evidence/nisar-ssar-beta-gcov-desktop.png) (SHA-256
  `828db719e08e72120c96fc4df474e74a343afc67142404e2e26241814559da21`) and
  [narrow 390x844](./evidence/nisar-ssar-beta-gcov-narrow.png) (SHA-256
  `dec46f5da0f696016ba30e597dfcf7bb46b69a4d4159642f98f1a2474326022e`). Both show the NISAR
  S-band label, HH display polarization, 100% coverage, high confidence, and non-NDVI/non-soil-
  moisture explanatory copy.
- A staging deployment fault was found and corrected: the workflow issued both an instant service
  deployment and a generic deploy request, causing concurrent Compose recreates to collide on
  PostGIS/MinIO container names. The generic trigger was removed, two stopped transient `Created`
  containers were deleted without touching volumes or running services, deployment contract tests
  passed 15/15, and the corrected single-trigger rollout succeeded.
- The production workflow now supplies all three NISAR activation flags as `true`, while retaining
  its exact approved-image SHA check and protected `production` environment.

### 14.3 Production promotion blocker

Gate 15 cannot be executed safely in the current infrastructure. Coolify contains only the
`akasha-staging-compose` service; no `akasha-production-compose` service exists. The infrastructure
runbook likewise describes `COOLIFY_PRODUCTION_SERVICE_UUID` as the UUID of a future production
stack. The production workflow additionally requires an externally configured
`COOLIFY_PRODUCTION_SERVICE_UUID`, `ESRI_WEB_IMAGE_APPROVED_SHA` equal to the accepted SHA above,
`ESRI_WEB_IMAGE_CREDENTIAL_ID`, production-environment secrets, and environment approval. No
production hostname or isolated production data stack is currently configured. Creating one by
reusing the staging service would overwrite validated staging and is prohibited.
