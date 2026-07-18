# EOS-04 field-scoped crop-monitoring integration plan

## Status and authority

Implementation status: Phases 0-2 were implemented and locally validated on 2026-07-18 after
explicit user authorization. Staging deployment and real-field acceptance remain the release gate.
Phases 3-5 remain planned work and are not implied by the first engineering slice.

This plan follows the completed EOS-04 ingestion/display work in
`feature-eos04-sar-integration-1.md`. That earlier plan remains the source of truth for provider
download, calibration, COG creation, pgSTAC registration, natural dates/tiles, and the staging
acceptance evidence. This document defines the next product phase: using EOS-04 as a field-scoped
supporting observation when optical crop analytics are limited by cloud or data age.

Repository ownership remains unchanged:

- `akasha-ingestion` owns EOS-04 scenes, calibrated backscatter COGs, field-clipped SAR reads,
  derived field features, query caching, and signed field-clipped SAR overlays.
- `akasha-project` owns users, fields, seasons, vegetation cycles, crop context, the same-origin BFF,
  evidence selection, crop-monitoring summaries, recommendations, and React/MapLibre UX.
- The browser calls only the product origin. It never receives ingestion, MinIO, pgSTAC, TiTiler,
  provider, or signed internal URLs.

## Product decision

EOS-04 is a **supporting crop-monitoring data layer**, not a fifth optical-index source.

For the normal farmer workflow:

1. The user selects a saved field.
2. Akasha evaluates field-specific optical observations and their exact field coverage/quality.
3. If recent optical evidence is usable, measured NDVI/NDMI/etc. remains authoritative.
4. If optical evidence is cloud-limited or stale, Akasha automatically looks for a comparable,
   field-overlapping EOS-04 observation.
5. EOS-04 contributes radar evidence about field structure and moisture-related change. It does
   not produce NDVI and does not silently replace missing optical pixels.
6. The UI explains whether the result is measured optical evidence, radar support, or unavailable.

EOS-04 may remain available to operators and advanced users for diagnostic visualization, but it
should not appear as an equivalent optical/index choice in the default farmer source picker.

## Why this is the correct boundary

The existing product already has most of the required foundations:

- saved field geometry and field-clipped optical overlays;
- field-specific optical date filtering and statistics;
- source-specific coverage, usable-pixel, and cloud/mask metrics;
- a best-observation resolver;
- EOS-04 calibrated HH/HV backscatter and private natural dates/tiles;
- a preliminary `sarSupport` response attached to optical statistics;
- field seasons, vegetation cycles, crops, varieties, sowing/harvest dates, and irrigation data;
- a transparent field-watch/risk response with evidence and limitations.

The current gaps are material:

- EOS-04 is rendered as a full-scene XYZ layer rather than a field-clipped support overlay.
- Standalone ingestion exposes EOS-04 dates/tiles but no field-SAR analytics contract.
- The preliminary `sarSupport` code reads app-native COGs instead of the standalone ingestion API.
- It reports one-date descriptive band statistics but no comparable temporal baseline or anomaly.
- It can trigger on any non-zero masked optical pixel; the production trigger must use the agreed
  field-quality thresholds.
- EOS-04 catalog items do not yet retain every comparability attribute needed for a defensible
  time series, such as orbit/pass, look direction, beam, and incidence-angle information.
- Crop-aware data belongs to `Field` + `VegetationCycle`, while the existing generic risk route
  still depends on legacy `Plot.cropType`/date metadata. The new work must not deepen that split.
- The current UI message says SAR support is available, but it does not show the actual field
  evidence, temporal change, provenance, or an actionable but non-diagnostic explanation.

## Scientific guardrails

### What is allowed in the first release

- Exact-field HH/HV calibrated Gamma0 backscatter statistics in dB.
- Valid-pixel coverage for the exact field geometry.
- Robust per-band distribution statistics: median, mean, standard deviation, p10, p25, p75, p90.
- A polarization contrast feature expressed as a dB difference when both required bands exist,
  with its formula and band order included in provenance.
- Temporal deltas against comparable observations from the same processing profile and compatible
  acquisition geometry.
- Field-relative anomaly detection after a minimum baseline exists.
- Neutral evidence labels such as `stable`, `change_detected`, `insufficient_baseline`, and
  `not_comparable`.
- A recommendation to inspect/scout a field when a material, well-supported change is detected.

### What is forbidden without a separately validated model

- Calling any EOS-04 value NDVI, estimated NDVI, crop health, biomass, soil moisture, disease,
  pest pressure, yield, or irrigation need.
- Treating brighter or darker backscatter as universally better or worse.
- Comparing observations with incompatible polarization, orbit/pass, beam, incidence geometry,
  processing profile, calibration, or terrain-correction state.
- Applying one threshold or interpretation to every crop, region, irrigation system, and growth
  stage.
- Filling the measured NDVI series with SAR-derived values without model validation, provenance,
  confidence, and a visually distinct estimated series.
- Producing chemical, irrigation, insurance, or harvest advice from SAR alone.

### Interpretation tiers

The platform must keep scientific maturity explicit:

| Tier | Output | Initial status |
|---|---|---|
| 0 | Field coverage, HH/HV statistics, acquisition/provenance | Implement now |
| 1 | Comparable temporal change and field-relative anomaly | Implement after repeated scenes exist |
| 2 | Crop/profile-specific interpretation such as rice establishment/flooding context | Gated pilot |
| 3 | SAR-assisted optical-index estimation or learned crop-condition model | Research/validation only |

Tier 0 and Tier 1 can support a generic crop-monitoring UI. Tier 2 and Tier 3 require crop-specific
datasets, ground truth, holdout validation, model cards, and explicit activation gates.

## Field-quality and activation policy

### Optical quality state

Use exact-field metrics, never scene-level cloud metadata alone. Preserve the currently deployed
qualification thresholds:

- field coverage must be at least 95%;
- usable pixels must be at least 80%;
- combined cloud/shadow coverage must be below 20%.

For a requested monitoring date or latest-field view, classify optical evidence as:

- `usable`: all thresholds pass;
- `cloud_limited`: coverage passes, but usable/cloud thresholds fail;
- `partial_coverage`: field coverage is below 95%;
- `stale`: no usable optical observation exists within the configured recency window;
- `unavailable`: no intersecting optical observation exists.

Recommended initial recency window: 10 days. It must be configuration, not a hard-coded UI value.

### When EOS-04 is requested

Request EOS-04 field support only when the selected field exists and one of these is true:

- the latest optical state is `cloud_limited`;
- the latest optical state is `stale`;
- the user explicitly opens the advanced radar-evidence view.

Do not request or compute EOS-04 for global view, before field selection, or merely because a small
number of optical pixels are masked.

### EOS-04 qualification

An EOS-04 observation qualifies only when:

- its footprint intersects the exact field geometry;
- valid calibrated pixels cover at least 95% of the field;
- the COG and item use the accepted EOS-04 processing-profile version;
- explicit polarizations and acquisition-comparability metadata exist;
- the acquisition is within the configured support window;
- exactly one resolved scene or a validated deterministic mosaic covers the date.

Recommended initial support window: latest EOS-04 observation no older than 21 days. For paired
optical/SAR evidence, expose the signed day offset and classify confidence as:

- `high`: absolute offset <= 3 days and coverage >= 95%;
- `medium`: absolute offset <= 7 days and coverage >= 95%;
- `low`: absolute offset <= 12 days and coverage >= 95%;
- otherwise unavailable for paired interpretation, though it may remain visible in history.

These values are defaults for operational behavior, not crop-science claims.

## Target user experience

### Default field analytics

- Keep the selected optical index and last usable field-clipped optical overlay as the primary map.
- Remove EOS-04 from the default optical source tabs once backend-support mode is released.
- Add a small `Observation continuity` status near the date/analytics area.
- When optical evidence is good, show `Optical observation usable`; do not distract the user with
  inactive SAR details.
- When optical evidence is limited, show a plain-language state such as:
  `Clouds limit the latest NDVI observation. Radar evidence from 17 Jul is available for this field.`
- Never imply that the radar observation is NDVI.

### Field-clipped radar evidence

- Provide an optional `Show radar evidence` control only when qualified EOS-04 support exists.
- Render a transparent-outside-the-field image source, following the existing field-index overlay
  pattern. Do not render the full EOS-04 scene in the farmer workflow.
- Label the map `EOS-04 Backscatter`, include the displayed polarization, unit `dB`, acquisition
  date, resolution/pixel spacing, and data-source attribution.
- Preserve the full-scene layer only in admin/advanced diagnostics if operationally useful.

### Timeline

- Keep measured optical index points as the primary series.
- Add radar-pass markers on the same date axis, not on the NDVI value axis.
- A radar marker opens the evidence card; it must not be plotted as an NDVI value.
- Distinguish `usable`, `cloud-limited`, `radar support`, and `no observation` states by icon,
  shape, label, and accessible text rather than color alone.
- A future Tier 3 estimated series must be dashed, independently toggleable, and labelled
  `model-estimated`, with confidence and model version.

### Evidence card

The first release should show:

- why radar was used (`cloud_limited`, `stale`, or `user_requested`);
- optical date/quality that triggered support;
- EOS-04 acquisition date and day offset;
- field coverage and valid pixel count;
- available/displayed polarizations;
- field median and interquartile range for each polarization;
- change from the nearest comparable previous radar pass when available;
- confidence and comparability status;
- a neutral explanation and limitations;
- provenance: satellite, product, processing version, acquisition geometry, and field scope.

### Recommendations

Initial recommendations are evidence-to-action messages, not agronomic diagnoses:

- `No action`: optical evidence is usable and radar has no supporting role.
- `Continue monitoring`: radar support exists but no comparable baseline exists.
- `Review field history`: radar changed materially, but crop context is incomplete.
- `Prioritize scouting`: a comparable field-relative anomaly is detected and evidence quality is
  sufficient.

Every recommendation must include `why`, `evidence`, `confidence`, `limitations`, and
`recommendedNextStep`. Do not recommend treatment or irrigation quantity.

## Crop-profile architecture

One universal crop model is not acceptable. Introduce a versioned crop-monitoring profile contract
owned by the product layer:

```json
{
  "profileId": "generic-field-change-v1",
  "cropIds": [],
  "regions": ["IN"],
  "requiredContext": [],
  "allowedFeatures": ["HH_MEDIAN_DB", "HV_MEDIAN_DB", "HH_MINUS_HV_DB"],
  "minimumComparableRadarObservations": 3,
  "stageModel": "none",
  "interpretationTier": 1,
  "recommendationPolicy": "scout-only",
  "status": "active"
}
```

Resolution order:

1. crop + variety + region profile, when validated;
2. crop + region profile;
3. crop-family profile;
4. generic field-change profile;
5. raw evidence only when no profile qualifies.

The resolver must use the active `VegetationCycle` for the field and date. Crop, variety, sowing,
harvest, maturity, irrigation, and season metadata remain in the product database and are not
copied into the ingestion catalog. Missing crop context must lower interpretation maturity, not
block Tier 0 radar evidence.

Rice should be the first crop-specific pilot because EOS-04 HH/HV multi-temporal agriculture use
is documented for rice monitoring. Its profile still requires local ground truth and validation;
the generic implementation must not embed rice thresholds.

## Target architecture

```text
Saved field + active vegetation cycle
                |
                v
Product BFF computes field-specific optical quality
                |
       +--------+---------+
       | optical usable   | optical cloud-limited/stale
       v                  v
Measured index       Request field-SAR evidence
remains primary            |
                           v
Product BFF sends exact geometry server-to-server
                           |
                           v
Standalone ingestion selects comparable EOS-04 item,
reads field window, computes SAR features, and signs
a transparent field-clipped overlay
                           |
                           v
Product BFF stores/proxies opaque evidence and combines
it with crop/season context and optical history
                           |
                           v
Field monitoring summary + optional radar overlay +
non-diagnostic recommendation
```

## Standalone ingestion changes

### Catalog metadata completeness

Extend EOS-04 preparation/registration to retain and validate, when present in the provider
package:

- orbit direction/pass;
- relative orbit or equivalent track identifier;
- look direction;
- beam/mode identifier;
- center/min/max incidence angle;
- acquisition start/end time;
- polarization order;
- calibration and processing profile versions;
- RTC and mask provenance;
- pixel spacing and nominal ground resolution as separate fields.

Unknown comparability metadata is acceptable for Tier 0 display but must fail closed for temporal
delta/anomaly computation.

### Field-SAR analytics API

Add an authenticated server-to-server endpoint:

`POST /api/v1/analytics/field-sar`

Request:

```json
{
  "geometry": {"type": "Polygon", "coordinates": []},
  "crs": "EPSG:4326",
  "fieldId": "opaque-product-field-id",
  "sourceId": "eos-04-sar-mrs-l2b",
  "targetDate": "2026-07-18",
  "startDate": "2026-06-01",
  "endDate": "2026-07-18",
  "selectionPolicy": "latest_qualified",
  "minimumCoveragePercent": 95,
  "maximumAgeDays": 21,
  "includeComparableHistory": 6
}
```

Response data:

```json
{
  "status": "available",
  "queryId": "opaque-query-id",
  "sourceId": "eos-04-sar-mrs-l2b",
  "acquisitionDate": "2026-07-17",
  "coveragePercent": 100,
  "validPixelCount": 680,
  "polarizations": ["HH", "HV"],
  "bands": [],
  "features": [],
  "comparison": {
    "status": "insufficient_baseline",
    "baselineCount": 0,
    "comparableDates": []
  },
  "quality": {
    "qualified": true,
    "confidence": "medium",
    "warnings": []
  },
  "provenance": {},
  "overlayUrl": "signed-ingestion-url"
}
```

Unavailable responses must be typed and explain `no_scene`, `no_overlap`, `low_coverage`,
`missing_comparability_metadata`, `not_comparable`, or `processing_unavailable` without throwing a
500 for normal data absence.

### Field-clipped overlay

Add a signed query-scoped overlay route analogous to the existing field-index overlay:

`GET /api/v1/analytics/field-sar/{queryId}/overlay.png`

Requirements:

- transparent outside the exact stored query geometry;
- selectable registered polarization, defaulting to the explicitly declared first band;
- stable dB rescale and legend metadata;
- `X-Akasha-Overlay-Corners` for MapLibre image placement;
- no direct object/provider URL in headers or response;
- query TTL, signature validation, and bounded output dimensions;
- cache key includes item ID, geometry hash, polarization, render profile, and processing version.

### Temporal comparison

- Compute temporal deltas only between observations that pass the comparability contract.
- Prefer robust field median over mean for change detection; retain both in evidence.
- Do not define a universal anomaly threshold in ingestion. Return normalized features, baseline
  counts, and robust deviations; product crop profiles decide how they may be interpreted.
- Require at least three comparable observations before returning a field-relative anomaly score.
- Preserve raw evidence and formula/version provenance so results can be reproduced.

## Product BFF changes

### Source roles

Extend source metadata with a product role:

- `primary`: directly selectable optical/index source;
- `support`: automatically or explicitly requested supporting evidence;
- `advanced`: diagnostic/full-scene visualization only.

EOS-04 becomes `support` for the farmer workflow. The existing exposure gate can continue to guard
all EOS functionality, but add separate fail-closed gates for field-SAR analytics and crop-monitoring
recommendations so display validation cannot accidentally activate interpretation.

Recommended flags:

- `EOS04_FIELD_SUPPORT_ENABLED=false`;
- `EOS04_TEMPORAL_CHANGE_ENABLED=false`;
- `EOS04_CROP_PROFILES_ENABLED=false`.

### Same-origin field contracts

Add:

- `GET /api/fields/{fieldId}/monitoring/evidence` - combined optical quality, SAR support, crop
  context, and provenance for a date/range;
- `GET /api/fields/{fieldId}/sar/overlay.png` - same-origin proxy of the signed ingestion overlay;
- `GET /api/fields/{fieldId}/monitoring/timeline` - measured optical points plus radar-event
  markers, with no cross-sensor value conflation;
- later, `GET /api/fields/{fieldId}/monitoring/summary` - versioned crop-profile result and
  recommendation.

The BFF must fetch the field by authenticated user/team scope, obtain the exact geometry, call
ingestion server-to-server, rewrite signed URLs to opaque same-origin proxy references, and attach
the active vegetation-cycle context locally.

### Persistence

Add product-owned records only for product decisions that must be auditable:

- field ID and vegetation-cycle ID;
- optical evidence reference and quality state;
- opaque ingestion SAR query/item reference;
- resolved crop-profile/model version;
- generated recommendation, confidence, limitations, and timestamps;
- user acknowledgement/scouting action when added later.

Do not duplicate raster values, COG locations, provider product URLs, or field geometry in a second
product analytics table unless required for a documented audit or cache use case.

### Resolve the field-domain split first

New crop monitoring must use `Field`, `FieldSeason`, `VegetationCycle`, `Crop`, and `Variety`.
Refactor or replace the existing risk path that still reads `Plot.cropType`, `Plot.sowingDate`, and
`Plot.plantingDate`. Do not introduce another crop metadata copy. Define one adapter that resolves
the active field vegetation cycle for a requested date and use it from monitoring/risk code.

## Frontend changes

- Filter default source selectors to `productRole=primary`.
- Add observation-continuity state to the existing field analytics panel.
- Add radar markers to the timeline without assigning them an optical index value.
- Add a field-clipped radar image source using the existing `IndexOverlay` placement pattern or a
  generalized `FieldImageOverlay` abstraction.
- Add an evidence card with quality, comparison, provenance, and limitations.
- Add accessible loading, unavailable, stale, and low-confidence states.
- Keep optical index controls, cloud-mask controls, point lookup, trend values, and export semantics
  tied to the optical source even when radar evidence is shown.
- Do not enable SAR GeoTIFF/CSV exports in the first product release. Add them only after a stable,
  documented field-SAR export contract exists.

## Implementation phases

### Phase 0 - contract reconciliation and metadata audit

- Inspect multiple real EOS-04 packages/dates for acquisition-comparability metadata.
- Confirm which metadata keys are stable across Bhoonidhi products.
- Decide the exact comparable-acquisition key and fail-closed behavior.
- Reconcile `Field` versus legacy `Plot` usage in monitoring/risk.
- Freeze API schemas, feature names, units, formulas, and processing versions.

Exit: approved contract fixtures from at least two real EOS-04 dates, or Tier 1 explicitly remains
disabled because a second comparable date is unavailable.

### Phase 1 - field-clipped raw radar evidence

- Implement ingestion `field-sar` request/response and signed overlay.
- Add exact-polygon statistics and coverage qualification.
- Add BFF same-origin proxy and source-role filtering.
- Replace the full-scene farmer view with optional field-clipped radar evidence.
- Preserve advanced full-scene diagnostics behind an explicit role/route.

Exit: one real saved field returns a transparent-outside-field EOS-04 overlay and reproducible HH/HV
statistics without exposing internal URLs.

### Phase 2 - optical-gap orchestration

- Introduce the explicit optical quality-state resolver using 95/80/<20 thresholds.
- Trigger EOS support only for cloud-limited/stale evidence or explicit user request.
- Add observation-continuity state and radar timeline markers.
- Remove the current permissive `masked_pixels > 0` trigger.
- Keep measured optical values authoritative.

Exit: automated tests prove usable optical dates do not trigger SAR; cloudy/stale exact-field dates
do; missing SAR fails soft and remains explainable.

### Phase 3 - comparable temporal change

- Persist/register acquisition-comparability metadata.
- Return comparable history and robust temporal features.
- Add field-relative baseline/anomaly results after the minimum sample count.
- Surface neutral change evidence and scout-only recommendations.

Exit: at least three comparable real/synthetic observations validate stable, positive-change,
negative-change, non-comparable, and insufficient-baseline behavior.

### Phase 4 - crop-context integration

- Add the active vegetation-cycle resolver.
- Implement versioned monitoring profiles and generic fallback.
- Add rice as the first gated crop-specific research profile only after local validation data exists.
- Connect results to field-watch/scouting without diagnosing disease, water need, or yield.

Exit: generic behavior works for every crop; crop-specific interpretation activates only for an
explicitly validated profile and otherwise degrades to generic/raw evidence.

### Phase 5 - validation, rollout, and learning loop

- Add operator metrics, audit logs, model/profile cards, and evidence exports for validation.
- Run shadow mode: compute evidence without showing recommendations.
- Compare outputs with field scouting observations and known crop-stage events.
- Activate one tenant/crop/region at a time.
- Keep production flags fail-closed until accuracy, failure, and latency thresholds pass.

## Test strategy

### Ingestion

- geometry validation, area/vertex limits, CRS, and polygon clipping;
- band order/polarization validation and no implicit VV assumptions;
- exact coverage and nodata behavior;
- robust statistics with synthetic HH/HV rasters;
- comparability-key equality and mismatch cases;
- no-baseline, one-baseline, adequate-baseline, and outlier cases;
- signed overlay authentication, expiry, transparency, corners, and URL redaction;
- in-memory/external backend parity;
- bounded reads and cancellation/timeouts.

### BFF

- auth/ownership isolation for every field route;
- exact field geometry forwarded server-to-server;
- optical 95/80/<20 state matrix and recency logic;
- no SAR call for usable optical data;
- fail-soft behavior for ingestion timeout/unavailability;
- no internal URLs/secrets in JSON, headers, logs, or browser requests;
- active vegetation-cycle selection at season boundaries;
- profile resolution and generic fallback;
- recommendation limitations and provenance.

### Frontend

- EOS hidden from the primary optical selector but available through radar evidence;
- no timeline before a saved field is selected;
- field-clipped overlay and transparent exterior;
- radar markers never appear as NDVI values;
- optical controls remain optical while radar evidence is visible;
- keyboard, focus, screen-reader names, non-color status distinctions, and responsive layouts;
- loading, stale, unavailable, low-confidence, and insufficient-baseline states;
- no browser request to ingestion/internal infrastructure.

### Real-data acceptance

- validate at least one field fully inside, partially inside, and outside an EOS-04 footprint;
- validate a small field and a large/complex polygon;
- compare BFF results against an offline rasterio reference calculation;
- inspect screenshots at desktop and narrow responsive widths;
- record package ID, item ID, processing version, acquisition metadata, field geometry hash,
  computed statistics, and checksums without storing user-identifying geometry in the report;
- repeat after a second/third comparable acquisition before enabling temporal interpretation.

## Performance and operational budgets

- Field evidence response target: p95 <= 5 seconds when uncached, <= 750 ms when cached.
- Field overlay target: p95 <= 5 seconds uncached and bounded to configured maximum dimensions.
- One browser request must not cause repeated reads of the 500 MB COG; cache by query/item/geometry.
- Limit history scans and raster reads; default six candidates, hard maximum twelve.
- Heavy preprocessing remains on `akasha-staging`; the product BFF performs orchestration only.
- Add metrics for optical trigger reason, SAR availability, qualification failure, cache hit, read
  duration, coverage, comparison status, profile resolution, and recommendation result.

## Security and privacy

- Enforce field ownership/team scope before every analytics call.
- Treat field geometry and crop-cycle context as user data.
- Send only the required geometry and opaque field ID to ingestion.
- Never send user identity, crop notes, or commercial field metadata to ingestion.
- Give stored ingestion query geometry a documented TTL/retention policy.
- Do not expose provider credentials, API keys, object paths, signed ingestion URLs, or scene
  download URLs to the browser.
- Keep recommendations auditable and reversible; profile/model activation requires explicit flags.

## Rollout gates

1. Metadata gate: comparability attributes verified from real products.
2. Raw-evidence gate: exact-field statistics match offline reference results.
3. Overlay gate: transparent field-clipped rendering passes visual and API tests.
4. Orchestration gate: cloud/stale trigger matrix passes; good optical data stays primary.
5. Privacy gate: same-origin browser traffic and redaction checks pass.
6. Shadow gate: evidence runs without user recommendations and operational budgets hold.
7. Generic-change gate: repeated comparable scenes and scouting review support Tier 1 activation.
8. Crop-profile gate: crop/region ground truth and holdout validation support each Tier 2 profile.
9. Production gate: tenant-scoped activation, rollback tested, monitoring/alerts live.

Each gate is independent. Passing raw display/overlay validation does not authorize change
interpretation, crop advice, or SAR-assisted NDVI estimation.

## Definition of done for the first product release

- EOS-04 is a support role, not a normal optical-index tab.
- No EOS processing occurs until an authenticated saved field is selected.
- Cloud/stale triggering uses exact-field optical quality and the agreed thresholds.
- The farmer map shows only a field-clipped radar overlay with transparent exterior.
- The response contains real field HH/HV evidence, coverage, confidence, and provenance.
- The timeline distinguishes measured optical observations from radar events.
- Missing or poor EOS data degrades cleanly without breaking optical analytics.
- No NDVI is created, estimated, or relabelled from SAR.
- Generic recommendations are scout-only and explain their evidence/limitations.
- Crop-specific behavior is versioned, validated, gated, and falls back safely.
- Unit, integration, contract, security, performance, and screenshot-backed staging validation pass.
- Production remains disabled until the rollout gates above are approved.

## Recommended implementation scope for the next engineering cycle

Implement Phases 0-2 only:

1. metadata/comparability audit;
2. standalone exact-field SAR statistics and signed overlay;
3. same-origin BFF contracts and support-role metadata;
4. exact optical-gap trigger;
5. field-clipped radar evidence UI and timeline marker;
6. tests, staging shadow mode, and real-field validation.

Do not include crop-specific thresholds, anomaly recommendations, soil-moisture retrieval, or
SAR-assisted NDVI in this cycle. Those depend on repeated comparable acquisitions and validation
data that the platform does not yet have.

## Decisions to confirm before implementation

The plan recommends these defaults, but product/science owners should explicitly approve them:

1. Hide EOS-04 from the default source selector and expose it through `Radar evidence`.
2. Use 10 days as optical staleness and 21 days as maximum EOS support age.
3. Require 95% EOS field coverage.
4. Require at least three comparable radar observations for a field anomaly.
5. Use generic, scout-only messaging for all crops initially.
6. Make rice the first separately validated crop-specific pilot.
7. Keep full-scene EOS visualization only for admin/advanced diagnostics.
