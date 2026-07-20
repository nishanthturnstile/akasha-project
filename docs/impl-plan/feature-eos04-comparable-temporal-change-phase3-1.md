---
goal: EOS-04 comparable temporal change for field monitoring
version: 1.0
date_created: 2026-07-18
last_updated: 2026-07-18
owner: Akasha engineering
tags: [feature, eos-04, sar, field-analytics, temporal-change, phase-3]
---

# EOS-04 Phase 3: comparable temporal change

## 1. Decision and scope

Phase 3 turns the deployed single-date EOS-04 field evidence into a defensible, field-relative
time series. It does not create NDVI from SAR and it does not diagnose crop health, water need,
disease, yield, or treatment.

The implementation will:

1. retain and normalize acquisition geometry and processing metadata from EOS-04 products;
2. decide whether two observations are comparable using a versioned, fail-closed policy;
3. return exact-field history, previous-pass deltas, and a robust field-relative baseline;
4. expose neutral change evidence in the existing monitoring contract and UI; and
5. keep scouting recommendations disabled until shadow validation passes.

Phase 3 is intentionally split into release gates. Metadata capture and shadow computation may ship
before any anomaly label is visible to users.

## 2. What is already implemented

The plan is based on the repositories and staging deployment as they exist on 18 July 2026, not on
the older proposed architecture.

### 2.1 Standalone ingestion (`akasha-ingestion`)

- EOS-04 Bhoonidhi search, download, safe extraction, calibration, masking, COG creation, checksum,
  catalog registration, pgSTAC registration, and natural imagery are implemented.
- The accepted processing profile is `eos04-sar-mrs-l2b-gamma0-v2`.
- L2B Gamma0 DN is calibrated to dB with the versioned formula
  `10*log10(DN^2-IMAGE_NOISE_BIAS)-KCAL_BETA0_DB`.
- The preparation path validates EOS-04, SAR, MRS, L2B ARD, RTC enabled, no missing frames,
  declared polarization assets, mask value, grids, and non-empty calibrated pixels.
- `POST /api/v1/analytics/field-sar` selects one qualified observation within a configurable
  target window, computes exact-polygon HH/HV statistics and contrast, and returns a signed overlay.
- `GET /api/v1/analytics/field-sar/{queryId}/overlay.png` returns a transparent-outside-field image.
- Field-SAR queries currently use the generic `akasha.field_queries` table.

### 2.2 Product API/BFF (`akasha-project/apps/api`)

- `GET /api/fields/{fieldId}/monitoring/evidence` computes the optical state using exact-field
  thresholds: at least 95% coverage, at least 80% usable pixels, and below 20% combined
  cloud/shadow.
- EOS-04 is requested only for an optical gap or an explicit radar request.
- The product API owns field authorization and geometry lookup and calls ingestion server-to-server.
- The browser receives only same-origin URLs; ingestion query IDs and signed/internal URLs are not
  exposed.
- `GET /api/fields/{fieldId}/sar/overlay.png` proxies the field-clipped overlay.
- EOS-04 is represented as a `support` source, while optical sources remain `primary`.

### 2.3 Frontend

- The field analytics panel explains that EOS-04 is structural/moisture-sensitive radar evidence,
  not NDVI.
- A user can toggle the qualified field-clipped radar overlay and return to optical imagery.
- The timeline has a nearest-radar-pass note, but not a multi-date radar event series.
- There is no temporal comparison, baseline, anomaly, or user-facing recommendation yet.

### 2.4 Validated baseline

- Ingestion tests: 279 passed.
- Product API tests: 481 passed, 11 skipped.
- Frontend tests: 397 passed.
- The deployed field `fe5a652b-4d33-4ff1-8801-a361f71c40b9` returned a 17 July 2026 HH/HV
  observation with 100% field coverage and high pairing confidence.
- Deployed immutable revisions are `7c23ab8f5a8b81d4c273bc060115146220832b4d` for ingestion and
  `e90066c65e80e9489387a57aa72d3839cc298c94` for product API/web.

These behaviors are regression requirements for Phase 3.

## 3. Audit findings that change the old plan

### 3.1 Only one real scene is available

Staging initially contained one accepted EOS-04 scene, acquired on 17 July 2026. A Phase 3 provider
search found 90 online intersecting products in the preceding year, and the 13 June 2026 repeat
scene was downloaded for metadata validation. Additional scenes still need full-pipeline
registration before the temporal API can validate the saved field.

The EOS-04 scheduled preload exists but is disabled by default. Historical backfill and then a
controlled recurring preload are Phase 3 prerequisites, not optional operational follow-up.

### 3.2 Comparison metadata is read but discarded

The real `BAND_META.txt` includes the following useful fields:

- `SceneStartTime`, `SceneCenterTime`, and `SceneEndTime`;
- `ImagingOrbitNo`, `Cycle_Number`, `StripNumber`, and headings;
- `PassType`, `ImagingDirection`, and `SensorOrientation`;
- `IncidenceAngle`, look angles, and pointing angles;
- `DEMCorrection`, `DEMSource`, and `DEMSource_Grid`;
- `RTC_Apply_Flag`, `ProcessingLevel`, and `SOFTWARE_VERSION`;
- output pixel/line spacing, polarizations, and calibration/noise constants.

The current scene record retains only collection, polarizations, processing family, input
representation, calibration formula, output scale, and bounding box. The asset record retains
polarizations, unit, geometry, CRS, and resolution. pgSTAC also omits the comparison-critical
geometry fields.

### 3.3 Some provider fields cannot be trusted as-is

In the first real package, `PassType=NA`, `Path=0`, `Row=0`, and beam-number fields are sentinel
values, while heading, strip number, incidence angle, sensor orientation, and times are populated.
The implementation must normalize verified fields, preserve raw values for audit, and fail closed
when the normalized comparison contract is incomplete. It must not assume that a field name is
usable merely because it exists.

### 3.4 Three observations are not a production-quality anomaly baseline

The parent plan proposed three comparable observations. Three observations are sufficient for
contract and synthetic-path acceptance, but median/MAD behavior is too fragile for a user-facing
anomaly score. Phase 3 will use:

- two observations for a previous-pass delta;
- at least three observations to exercise the baseline contract in tests and shadow telemetry;
- at least five **prior** comparable observations for a user-facing robust anomaly score; and
- no anomaly score when the baseline MAD is degenerate.

The default can be raised after operational review without changing the response shape.

## 4. Scientific and product invariants

- Optical NDVI/NDMI/etc. remains measured optical evidence and remains authoritative.
- SAR values and changes always use dB and never share an optical-index value axis.
- A change sign means only `backscatter_increased` or `backscatter_decreased`.
- No generic wet/dry, healthy/unhealthy, biomass, crop-stage, or irrigation interpretation is
  produced.
- Every observation must satisfy exact-field coverage independently.
- An observation may be displayed as raw evidence even when it cannot be compared.
- Missing or ambiguous comparison metadata produces a typed state, never a guessed comparison.
- No universal crop threshold is implemented in ingestion or the generic UI.
- Crop and vegetation-cycle context stays in the product service; ingestion remains crop-agnostic.
- Existing full-scene/admin imagery and field-clipped overlay behavior remain separate from the
  temporal analytics contract.

## 5. Versioned comparability contract

Create `eos04-comparability-v1`. A normalized object is persisted on every newly prepared scene and
registered in pgSTAC.

```json
{
  "policyVersion": "eos04-comparability-v1",
  "platform": "EOS-04",
  "sensor": "SAR",
  "frequencyBand": "C",
  "instrumentMode": "MRS",
  "productType": "L2B-ARD-PRODUCT",
  "processingProfileVersion": "eos04-sar-mrs-l2b-gamma0-v2",
  "providerSoftwareVersion": "1.2.00",
  "outputScale": "dB",
  "rtcApplied": true,
  "demCorrection": true,
  "demSource": "COPERNICUS30",
  "polarizations": ["HH", "HV"],
  "sensorOrientation": "RIGHT",
  "orbitState": "DESCENDING",
  "orbitStateSource": "satellite_heading",
  "trackKey": "scene:22",
  "incidenceAngleDegrees": 37.86202,
  "pixelSpacingMeters": 18.0,
  "acquisitionStart": "2026-07-17T00:40:49.740Z",
  "acquisitionEnd": "2026-07-17T00:41:12.370Z",
  "complete": true,
  "missing": []
}
```

### 5.1 Equality requirements

Two observations are comparable only when all of these match:

- platform, sensor, frequency band, instrument mode, and product type;
- processing profile, calibration formula, output scale/unit, RTC state, and DEM-correction state;
- ordered polarization set required by the metric;
- sensor orientation and normalized orbit state;
- normalized track key, after it has been verified from at least two real products; and
- pixel spacing within 0.5 m.

Center incidence angles must differ by no more than 1.0 degree initially. This is a configurable
comparison tolerance, not part of an opaque hash equality test.

Provider software-version differences are recorded and rejected by default. They may be allowed
only after processing-equivalence validation and a new comparability-policy version.

### 5.2 Normalization rules

- Parse provider date/time values into UTC-aware instants and retain the original strings in a
  bounded `rawComparisonMetadata` object.
- Prefer a valid provider pass/orbit-state value. If it is absent or `NA`, derive northbound versus
  southbound from satellite heading using a documented, tested rule and record the derivation
  source. Do not derive when heading is missing or ambiguous.
- Treat provider sentinel values such as `NA`, `-9999`, and zero-valued path/row identifiers as
  missing.
- Use the positive `SceneNumber` as the normalized within-strip track key. The 17 July and 13 June
  repeat products both use scene 22 with matching geometry, orientation, incidence, polarization,
  RTC/DEM, and processing software.
- Normalize polarizations with the existing canonical order.
- Do not include absolute orbit number, cycle number, or strip number in equality: they change
  between verified repeat acquisitions and remain observation provenance.
- Store a canonical JSON hash for cache/audit use, but return individual fields and mismatch reasons
  in the API.

### 5.3 Typed comparison failures

The service returns one of:

- `COMPARABLE`;
- `METADATA_INCOMPLETE`;
- `POLARIZATION_MISMATCH`;
- `TRACK_MISMATCH`;
- `ORBIT_STATE_MISMATCH`;
- `INCIDENCE_ANGLE_MISMATCH`;
- `PROCESSING_PROFILE_MISMATCH`;
- `PROCESSING_SOFTWARE_MISMATCH`;
- `RTC_OR_DEM_MISMATCH`; or
- `RESOLUTION_MISMATCH`.

Multiple mismatches may be returned. User copy remains concise; detailed reasons remain available
for operators and provenance.

## 6. Temporal analytics contract

### 6.1 Ingestion request

Extend the existing endpoint rather than adding a parallel field-SAR implementation:

`POST /api/v1/analytics/field-sar`

Add optional fields:

```json
{
  "includeHistory": true,
  "historyLookbackDays": 180,
  "maximumHistoryObservations": 12,
  "comparisonPolicyVersion": "eos04-comparability-v1",
  "minimumBaselineObservations": 5
}
```

Bounds:

- lookback default 180 days, maximum 365;
- history default 8 observations, maximum 12;
- coverage remains at least 95%; and
- only observations on or before the selected acquisition are eligible for history.

The existing request without `includeHistory` must remain backward compatible and retain its
single-observation performance.

### 6.2 Ingestion response

Keep the current raw evidence fields and add:

```json
{
  "comparison": {
    "status": "INSUFFICIENT_BASELINE",
    "policyVersion": "eos04-comparability-v1",
    "currentKeyHash": "opaque-hash",
    "previousComparableDate": "2026-07-05",
    "comparableObservationCount": 2,
    "excludedObservationCount": 1,
    "exclusions": [
      {"acquisitionDate": "2026-06-23", "reasonCodes": ["TRACK_MISMATCH"]}
    ]
  },
  "history": [
    {
      "acquisitionDate": "2026-07-05",
      "coveragePercent": 99.8,
      "bands": [],
      "features": {},
      "quality": {},
      "comparableToCurrent": true
    }
  ],
  "change": {
    "status": "AVAILABLE",
    "referenceDate": "2026-07-05",
    "bands": [
      {"polarization": "HH", "medianDeltaDb": 1.25}
    ],
    "features": {"hhMinusHvMedianDeltaDb": 0.32}
  },
  "baseline": {
    "status": "INSUFFICIENT_OBSERVATIONS",
    "requiredPriorObservations": 5,
    "priorObservationCount": 1,
    "windowStart": "2026-01-18",
    "windowEnd": "2026-07-16",
    "bands": []
  }
}
```

`history` returns bounded field statistics and provenance, never raster URLs for every date. The
existing overlay URL continues to represent only the selected/current observation.

### 6.3 Temporal features

For each shared polarization:

- current and prior field median in dB;
- `medianDeltaDb = currentMedianDb - previousMedianDb`;
- current and prior IQR, for context;
- optional mean delta for diagnostics, not primary UI interpretation.

For the existing ordered polarization contrast:

- current and prior contrast in dB;
- contrast delta in dB; and
- formula/band order in provenance.

Do not compute pixel-to-pixel change in Phase 3. The current exact-field distribution approach is
less sensitive to sub-pixel registration and avoids pretending that independently acquired 18 m
pixels are perfectly aligned.

### 6.4 Robust field-relative baseline

For each feature, build the baseline from **prior** comparable observations only. Do not include the
current observation in its own baseline.

- baseline center: median of prior per-observation field medians;
- baseline spread: MAD of prior per-observation field medians;
- robust deviation: `0.67448975 * (current - baselineMedian) / MAD`;
- default required prior observations: 5;
- maximum prior observations: 12; and
- use the most recent observations in the configured window.

Return the numeric robust deviation but no crop-health meaning. When MAD is zero or below a tested
numeric tolerance, return `DEGENERATE_BASELINE` and omit the score. Never inject an epsilon merely
to manufacture a large anomaly.

The product layer may initially label only:

- `INSUFFICIENT_HISTORY`;
- `NO_COMPARABLE_HISTORY`;
- `COMPARABLE_CHANGE_AVAILABLE`;
- `BASELINE_AVAILABLE`; or
- `BASELINE_DEGENERATE`.

Do not ship `stable` or `change_detected` thresholds until shadow distributions and scouting review
approve a versioned generic policy.

## 7. Persistence and privacy

### 7.1 Scene/catalog records

Use existing JSON metadata columns rather than adding fixed database columns for provider-specific
fields:

- persist `comparisonMetadata`, `comparisonKeyHash`, and bounded `rawComparisonMetadata` in
  `provider_scenes.provider_metadata`;
- persist processing profile, RTC/DEM provenance, spacing, unit, and polarizations in the
  backscatter asset metadata; and
- register applicable standard SAR properties plus `akasha:comparison_*` properties in pgSTAC.

Reprocessing an existing product must deterministically update the same scene and STAC item.

### 7.2 Exact-field statistics cache

Do not reread up to 12 COG windows on every panel refresh. Extend `akasha.field_queries` with:

- nullable `geometry_hash`;
- nullable `analysis_version`;
- a lookup index over scene, geometry hash, index name, analysis version, and expiry; and
- repository methods to find a non-expired cached observation and delete expired queries.

Cache one scene/field/analysis-version statistics result. Create a fresh signed current-overlay
query only when an overlay is requested or its query has expired.

The cache key includes scene ID, canonical geometry hash, polarization set, minimum coverage,
statistics version, and processing profile. It must not include the product-layer field ID.

### 7.3 Geometry retention

The existing field-SAR path stores exact geometry without setting `expires_at`, and repository reads
do not enforce expiry. Phase 3 must close this gap before expanding history usage:

- set a configurable query TTL, initially 24 hours;
- reject expired query IDs in the overlay route;
- delete expired field queries with a bounded scheduled cleanup; and
- do not log geometry coordinates or return geometry in analytics responses.

Historical numeric results may be cached only for the same TTL in Phase 3. Longer-lived audit data,
if needed later, belongs in a separately reviewed product decision record without duplicated field
geometry.

## 8. Repository implementation plan

### 8.1 Workstream A — metadata and catalog foundation (`akasha-ingestion`)

1. Add typed EOS-04 comparison metadata parsing and normalization in
   `src/akasha/processing/eos04.py`.
2. Persist normalized and bounded raw values from `PreparedEos04Scene.manifest` in
   `src/akasha/services/eos04_ingestion.py`.
3. Add standard/custom properties in `src/akasha/catalog/pgstac_repository.py`.
4. Add a pure comparison-policy module, recommended path
   `src/akasha/processing/sar_comparability.py`.
5. Add fixtures for real metadata shapes, including `NA`, `-9999`, missing headings, different
   software versions, polarization mismatch, and incidence-angle boundaries.
6. Reprocess the accepted 17 July product and verify the scene, asset, COG, and STAC item remain
   idempotent.

No product/UI work starts until this contract is test-frozen.

### 8.2 Workstream B — acquisition history prerequisite (`akasha-ingestion`)

1. Run a dry-run provider search for the Bangalore AOI across the existing 365-day window.
2. Record candidate dates, footprints, product types, polarization sets, and normalized comparison
   metadata without downloading more than operational limits permit.
3. Backfill every qualified, non-duplicate EOS-04 scene needed to produce at least two comparable
   dates for previous-pass validation and preferably six comparable dates for a real baseline.
4. If provider history cannot supply those dates, keep the user-facing baseline disabled and use
   synthetic fixtures only for engineering acceptance.
5. After one successful manual refresh and idempotent rerun, enable the existing scheduled preload
   in staging with its 12-day refresh cadence. Production activation is a separate rollout gate.
6. Add freshness/accepted-scene-count monitoring by source, without treating provider no-result as
   a pipeline failure.

### 8.3 Workstream C — history and statistics (`akasha-ingestion`)

1. Add a repository range query ordered newest-first, filtered to accepted EOS-04 scenes and
   spatially intersecting the field envelope before raster reads.
2. Extend Pydantic request/response schemas in `src/akasha/schemas.py`.
3. Refactor the current single-scene field statistics path so one function computes or retrieves a
   cached observation for one scene.
4. Compare candidates to the selected/current scene using `eos04-comparability-v1`.
5. Return bounded comparable history, typed exclusions, previous-pass delta, and baseline results.
6. Add the field-query cache/expiry migration and repository methods.
7. Preserve current unavailable responses and add normal-data reason codes for missing/incompatible
   history; do not convert them to HTTP 500.
8. Keep `includeHistory=false` as the default until performance and correctness gates pass.

Likely files:

- `src/akasha/processing/eos04.py`;
- `src/akasha/processing/sar_comparability.py` (new);
- `src/akasha/processing/raster_stats.py`;
- `src/akasha/services/eos04_ingestion.py`;
- `src/akasha/services/analytics.py`;
- `src/akasha/catalog/scene_repository.py`;
- `src/akasha/catalog/field_query_repository.py`;
- `src/akasha/catalog/pgstac_repository.py`;
- `src/akasha/schemas.py`;
- `src/akasha/api/app.py`;
- `src/akasha/config.py`;
- one new Alembic migration; and
- focused processing, repository, API, cache, and migration tests.

### 8.4 Workstream D — same-origin product contract (`akasha-project/apps/api`)

1. Extend the existing ingestion client field-SAR models; do not introduce untyped dictionary
   pass-through for temporal results.
2. Extend `GET /api/fields/{fieldId}/monitoring/evidence` with a bounded `radar.temporal` summary
   when radar is triggered.
3. Add `GET /api/fields/{fieldId}/monitoring/radar-history` only for the expandable detail/timeline
   payload. It repeats field authorization, calls ingestion server-to-server, and exposes no signed
   URLs or query IDs.
4. Keep the overlay endpoint current-date only.
5. Attach crop/vegetation-cycle identifiers only as context for future profile resolution; do not
   send them to ingestion and do not interpret change in Phase 3.
6. Add fail-closed flags and configuration:
   - `EOS04_TEMPORAL_CHANGE_ENABLED=false`;
   - `EOS04_TEMPORAL_SHADOW_ENABLED=false`;
   - `EOS04_TEMPORAL_RECOMMENDATIONS_ENABLED=false`;
   - `EOS04_TEMPORAL_LOOKBACK_DAYS=180`;
   - `EOS04_TEMPORAL_MAX_OBSERVATIONS=12`; and
   - `EOS04_TEMPORAL_MIN_BASELINE_OBSERVATIONS=5`.
7. When shadow is enabled and visible change is disabled, compute and log only bounded status,
   counts, policy version, latency, and reason codes. Do not log field geometry or raw field values.

Likely files:

- `apps/api/app/ingestion_client.py`;
- `apps/api/app/routers/analytics_router.py`;
- `apps/api/app/config.py`;
- deployment environment examples/workflows; and
- ingestion-client and pipeline-bridge tests.

### 8.5 Workstream E — frontend evidence UX (`akasha-project/apps/frontend`)

1. Extend `FieldMonitoringEvidence` with typed temporal states.
2. Upgrade the existing radar evidence card rather than creating a competing analytics panel.
3. Show the current pass, previous comparable pass, and per-band median dB delta when available.
4. Show explicit states for insufficient history, missing comparison metadata, no comparable pass,
   and degenerate baseline.
5. Add radar event markers to the date axis as events, never as NDVI values. If the current timeline
   data model cannot represent non-valued events, introduce a separate `observationEvents` array
   rather than manufacturing numeric points.
6. Keep any radar sparkline or trend in a separate dB-labelled view. Do not overlay it on the
   optical trend chart.
7. Keep copy neutral, for example:
   - `HH backscatter increased by 1.3 dB since 5 Jul.`
   - `Only 2 comparable radar observations are available; 5 prior observations are required for a baseline.`
   - `Radar change can reflect crop structure, surface condition, or acquisition effects. It is not NDVI or a diagnosis.`
8. Keep recommendations hidden while `EOS04_TEMPORAL_RECOMMENDATIONS_ENABLED=false`.
9. Add accessible text, keyboard behavior, and non-color-only event distinctions.

Likely files:

- `apps/frontend/src/types/api.ts`;
- `apps/frontend/src/lib/api.ts`;
- `apps/frontend/src/lib/queries.ts`;
- `apps/frontend/src/components/scaffold/IndexPanel.tsx`;
- timeline event components/types; and
- corresponding component/integration tests.

## 9. Recommendation policy

Phase 3 engineering computes evidence; it does not immediately activate a recommendation.

After shadow validation, a separate generic policy version may map a sufficiently large robust
deviation to `Review field conditions` or `Prioritize scouting`. Activation requires:

- at least five prior comparable observations;
- non-degenerate baseline;
- current exact-field coverage at least 95%;
- no comparison warnings;
- an approved two-sided robust-deviation threshold derived from reviewed field distributions;
- an explanation containing date, metric, direction, confidence, and limitations; and
- `EOS04_TEMPORAL_RECOMMENDATIONS_ENABLED=true`.

Even after activation, the recommendation must never specify disease, treatment, irrigation
quantity, or yield impact. Crop-specific interpretation remains Phase 4.

## 10. Test plan

### 10.1 Ingestion unit/contract tests

- parse and normalize the real 17 July metadata fixture;
- treat `NA`, zero path/row, and `-9999` as missing;
- derive orbit state from unambiguous heading and preserve derivation source;
- reject ambiguous/missing orbit state for comparison;
- exact comparability equality and each mismatch reason;
- incidence difference at, below, and above 1.0 degree;
- absolute orbit/cycle changes do not break an otherwise verified repeating track;
- provider software-version mismatch fails closed;
- current plus one comparable observation returns a delta;
- baseline excludes the current observation;
- fewer than five prior observations returns `INSUFFICIENT_OBSERVATIONS`;
- five or more prior observations returns reproducible median, MAD, and robust deviation;
- zero/near-zero MAD returns `DEGENERATE_BASELINE` without a score;
- outlier robustness and positive/negative delta sign;
- excluded observations never influence baseline metrics;
- cache hit avoids a second raster read;
- cache key changes for geometry, analysis version, coverage threshold, or scene;
- expired query cannot render an overlay and cleanup is bounded;
- history bounds and geometry complexity limits are enforced; and
- old single-date requests/responses remain compatible.

### 10.2 Product API tests

- usable optical evidence still avoids an automatic radar request;
- optical gap requests history only when the temporal flag is enabled;
- shadow mode does not expose temporal values;
- radar-history endpoint enforces field ownership/team scope;
- ingestion reason codes map to stable same-origin response states;
- no ingestion URL, query ID, object path, or field geometry leaks;
- overlay proxy behavior remains unchanged; and
- disabled/unavailable temporal service fails soft while optical analytics remain usable.

### 10.3 Frontend tests

- delta and reference date render with dB units;
- insufficient, non-comparable, metadata-incomplete, and degenerate states render correctly;
- radar events have no optical index value;
- no SAR value appears on an NDVI axis or in optical export semantics;
- overlay toggle remains current-pass only;
- recommendation is absent while its flag is false; and
- accessible labels communicate event type and state without color dependence.

### 10.4 Performance and security tests

- cold request with 12 candidates stays within an agreed staging budget; target p95 <= 5 seconds;
- warm cached request target p95 <= 750 ms inside ingestion;
- candidate spatial prefilter prevents non-overlapping raster reads;
- maximum geometry vertices/area and history bounds prevent abusive work;
- logs contain no coordinates, provider URLs, signatures, or credentials; and
- signed overlays expire and expired database query rows are cleaned.

## 11. Rollout and validation gates

### Gate 3A — metadata foundation

- deploy normalized metadata and pgSTAC properties with temporal output disabled;
- reprocess the existing scene idempotently;
- verify the real catalog record is complete; and
- preserve the 17 July and 13 June metadata shapes as contract fixtures for scene-22 recurrence.

### Gate 3B — history ingestion

- dry-run and then backfill the Bangalore AOI;
- verify at least two real comparable dates for the saved test field;
- rerun backfill and prove no duplicate scenes/assets/items;
- enable scheduled preload in staging only after the manual run is healthy; and
- alert on job failure, not on a legitimate no-result search.

### Gate 3C — shadow temporal computation

- enable `EOS04_TEMPORAL_SHADOW_ENABLED=true` in staging;
- compare cold/warm latency, cache behavior, exclusion reasons, and numeric reproducibility;
- manually recompute at least one real field/date outside the API path; and
- keep UI temporal values and recommendations disabled.

### Gate 3D — neutral UI

- requires at least two real comparable observations for previous-pass display;
- enable temporal evidence for internal users;
- visually validate desktop and narrow/mobile layouts in a real browser;
- confirm no optical/radar axis conflation and no internal URL exposure; and
- validate all empty/error states with the real saved field.

### Gate 3E — baseline evidence

- requires at least six real comparable observations total: current plus five prior;
- compare API baseline calculations with an independent notebook/script;
- review distributions for several fields and acquisition dates; and
- expose numeric field-relative deviation only after review.

### Gate 3F — scouting recommendation

- explicitly outside the initial Phase 3 release;
- requires field observations/scouting feedback, an approved generic policy version, false-alert
  review, and separate flag activation.

**Deferred — 19 July 2026:** field scouting observations and feedback are not currently available.
Gate 3F is therefore intentionally deferred, not failed or completed. EOS-04 neutral temporal
evidence may remain available under the completed Gates 3A–3E, but scouting recommendations must
remain disabled. Reopen Gate 3F when sufficiently dated, field-linked ground observations are
available for false-alert and policy validation.

Production rollout repeats the staging gates. A synthetic passing test never substitutes for a
real-data gate.

### Staging acceptance record — 18 July 2026

- Gates 3A through 3E passed for saved field `fe5a652b-4d33-4ff1-8801-a361f71c40b9`.
- Six real, metadata-complete, descending scene-22 observations were prepared and registered:
  17 July, 13 June, 27 May, 10 May, 23 April, and 6 April 2026.
- All six observations returned 100% exact-field coverage and 100% valid pixels for the saved
  field; the previous comparable date was 13 June 2026.
- The current-versus-previous median deltas were -1.719 dB for HH and -2.189 dB for HV.
- The five-prior median/MAD baseline returned `AVAILABLE`; robust deviations were -1.000 for HH,
  -1.127 for HV, and 2.374 for the HH-minus-HV feature.
- A cold real-field request completed in 0.599 seconds. A warm request completed in 0.123 seconds
  and reused the five cached historical statistics records while retaining a distinct audit query.
- Staging may therefore enable neutral temporal evidence (Gate 3D/3E). Scouting recommendations
  remain disabled pending the separate Gate 3F review.

## 12. Exit criteria

Phase 3 engineering is complete when:

1. comparison-critical metadata is normalized, persisted, registered, and versioned;
2. at least two real packages validate the chosen repeating-track/comparability semantics;
3. exact-field history and previous-pass deltas work for real and synthetic observations;
4. synthetic tests cover adequate/insufficient/degenerate baselines and every mismatch state;
5. real user-facing baseline output remains gated until current plus five prior comparable
   observations exist;
6. the existing optical-gap and field-overlay behavior has no regression;
7. query retention, expiry enforcement, and cleanup are active;
8. same-origin BFF and frontend show neutral, accessible, non-NDVI temporal evidence;
9. full repository test suites, builds, lint, migrations, staging health, and visual browser checks
   pass; and
10. recommendations remain off unless Gate 3F receives separate approval.

## 13. Recommended implementation order

1. Metadata parser, normalization policy, real fixtures, and pgSTAC registration.
2. Reprocess current scene; dry-run/backfill second and subsequent real acquisitions.
3. Field-query TTL/cache migration and repository range/spatial queries.
4. Ingestion history/delta/baseline contracts behind `includeHistory`.
5. Product typed client, shadow flag, and telemetry.
6. Independent numerical and performance validation.
7. Same-origin radar-history route and neutral frontend evidence.
8. Staging visual acceptance, then production rollout.
9. Baseline UI only when the six-real-observation gate is met.
10. Scouting policy as a separately approved activation.

Gate 3F was deferred on 19 July 2026 because field observations and scouting feedback are not yet
available. It remains a separate approval and must not be inferred from the completed engineering
gates. Satellite integration work may proceed independently while the project waits for suitable
ground observations.
