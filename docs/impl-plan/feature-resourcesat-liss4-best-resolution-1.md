---
goal: Wire ResourceSat-2A LISS-4 (5.0 m native scenes, 5.8 m composite grid) as an automatic per-field best-resolution enhancement layer on top of LISS-3 (24 m)
version: 1.0
date_created: 2026-06-18
last_updated: 2026-06-18
owner: Akasha Engineering (ingestion + raster + frontend)
tags: [feature, data, infrastructure, ingestion, raster, isro, bhoonidhi]
---

# Introduction

This plan adds **ResourceSat-2A LISS-4 MX70 L2 (5.0 m native scenes, composited to the 5.8 m operational grid)** as a second ISRO/NRSC Bhoonidhi optical source
that **automatically enhances per-field vegetation-index accuracy** (NDVI / MSAVI / NDWI_GREEN_NIR) wherever a
LISS-4 composite covers a field for the selected date, while **falling back to the existing LISS-3 (24 m)
source** elsewhere. LISS-3 remains the wide-coverage baseline and the only source for NDMI (LISS-4 has no
SWIR band). The two sources stay as **separate STAC collections / composites** — there is no pixel-level
radiometric blending into a single COG.

The work mirrors the proven LISS-3 ingestion pipeline (Bhoonidhi search/download → COG prepare → AOI
composite → STAC load → source registry → frontend), adds a **new per-field best-resolution resolver** in the
BFF, a **separate scheduled systemd job** on the IP-whitelisted staging VM (`akasha-staging`), and **ungates**
the LISS-4 source. Real download, radiometric validation, composite build, ingest, and the final gate flip are
executed on `akasha-staging` over SSH because Bhoonidhi access is IP-whitelisted to that VM.

## 1. Requirements & Constraints

- **REQ-001**: LISS-4 enhances NDVI / MSAVI / NDWI_GREEN_NIR on a **per-field** basis; when a LISS-4 composite
  covers the field for the requested date (within a configurable date window), the BFF computes the index from
  LISS-4 (5.8 m composite grid). Otherwise it falls back to LISS-3 (24 m).
- **REQ-002**: LISS-3 is never replaced. It remains the wide-coverage baseline and the sole NDMI source.
- **REQ-003**: NDMI requested while LISS-4 is the resolved source MUST auto-resolve to LISS-3 and carry a
  provenance note (LISS-4 has no SWIR band).
- **REQ-004**: A **separate** systemd timer/service/wrapper runs the LISS-4 Bhoonidhi sync at an independent
  cadence (~5 days, matching LISS-4 MX revisit). The existing LISS-3 timer is untouched.
- **REQ-005**: The single-date overlay, single-date statistics, and hover point endpoints all use the resolved
  (best-resolution) source. Index response payloads expose provenance:
  `resolvedSourceId`, `resolutionMeters`, `enhanced` (bool), `basisDate`.
- **REQ-006**: The historical **trend** time series stays on a single consistent source (LISS-3) for radiometric
  continuity; LISS-4-enhanced points are not mixed into the trend series (see ALT-002).
- **REQ-007**: LISS-4 supported indices = `["NDVI", "MSAVI", "NDWI_GREEN_NIR"]` only. NDMI / NDRE excluded.
- **SEC-001**: All Bhoonidhi search/download for LISS-4 MUST run from the IP-whitelisted `akasha-staging` VM
  (egress `20.219.3.35`). No Bhoonidhi calls from dev or `akasha-control`.
- **SEC-002**: ISRO/NRSC/Bhoonidhi attribution MUST be wired into the LISS-4 source registry `attribution`
  field and surfaced on served layers.
- **CON-001**: LISS-4 MX70 has **3 analytic bands** — Green (BAND2), Red (BAND3), NIR (BAND4). **No SWIR.** All
  4-band assumptions (analytic band count, mask logic, STAC `eo:bands`/`raster:bands`) must be generalized.
- **CON-002**: LISS-4 MX swath ≈ 70 km < 120 km AOI → multi-scene compositing is mandatory (same as LISS-3).
- **CON-003**: LISS-4 L2 reflectance scale/offset/background and red/NIR calibration are **UNVALIDATED**. They
  MUST be confirmed from a real `akasha-staging` download before the gate is flipped to active.
- **CON-004**: There is no native cloud/quality layer; a SWIR-free **provisional Akasha threshold mask v1
  (LISS-4)** is generated. Metrics remain `metricsProvisional: true`.
- **CON-005**: Object/scene/composite key schemes and idempotency rules must match existing conventions
  (`s3://akasha-cogs/{sourceId}/composite/{aoiId}/{date}/analytic.tif|mask.tif`).
- **GUD-001**: Pin container/dependency versions (GDAL / rasterio / rio-tiler / TiTiler). Do not float to latest.
- **GUD-002**: Band NAME→POSITION translation happens only in `indices.py` via `bandRoleMapping`; never
  hard-code band positions in new code.
- **PAT-001**: Resampling — **nearest** for categorical mask (+ overviews); **bilinear/cubic** for continuous
  reflectance. Analytic COG and mask COG remain **separate** assets.
- **PAT-002**: Reuse the source-parameterized worker/composite/catalog code paths; add LISS-4 by configuration
  (source id, collection id, profile) rather than forking the LISS-3 logic.

## 2. Implementation Steps

### Implementation Phase A — LISS-4 ingestion adapter (COG prepare + composite + STAC)

- GOAL-A01: Make the existing source-parameterized ingestion pipeline accept and correctly process the 3-band
  LISS-4 MX70 product end-to-end (search → download → prepare → composite → STAC item) without disturbing
  LISS-3. Local/synthetic-COG correctness only; real radiometry confirmed in Phase F.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-A01 | In `services/ingestion/akasha_ingest/bhoonidhi.py`, add constants `RESOURCESAT_LISS4_SOURCE_ID = "resourcesat-2a-liss4-mx70-l2"` and `RESOURCESAT_LISS4_BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS4-MX70_L2"`, and add the pair to the `SOURCE_COLLECTIONS` dict. | | |
| TASK-A02 | In `services/ingestion/akasha_ingest/config.py`, add a `RESOURCESAT_LISS4_COLLECTION_ID` constant and include the LISS-4 source id in `RESOURCESAT_BOA_COLLECTION_IDS` (this unblocks `bhoonidhi-sync` / `build-composite` / `verify-composite` source guards in `worker.py#L540`). Keep all worker `--source` defaults = LISS-3. | | |
| TASK-A03 | In `scripts/prepare_resourcesat_liss3_boa_cogs.py`, make band order and mask builder **profile-driven**. Add a `resourcesat-2a-liss4-mx70-l2` entry to `SOURCE_PROFILES` with `collection="ResourceSat-2A_LISS4-MX70_L2"`, `label="LISS-4"`, `resolution_meters=5.0` (confirmed from the first Jan 30 staging download), a 3-band `analytic_bands = (("BAND2","GREEN","Green"),("BAND3","RED","Red"),("BAND4","NIR","Near infrared"))`, and reflectance `scale=0.0001`, `offset=0.0` (placeholder — confirm in Phase F). | | |
| TASK-A04 | Add a SWIR-free mask builder `build_mask_array_3band()` (selected via profile) implementing the LISS-4 provisional Akasha threshold mask v1: class 0 gap (all bands background/out-of-range); class 4 water (`NDWI_GREEN_NIR >= 0.20 AND NIR <= 0.20`); class 2 cloud (`brightness((G+R+NIR)/3) >= 0.32 AND NDVI <= 0.20`); class 3 shadow (`GREEN <= 0.08 AND RED <= 0.08 AND NIR <= 0.08`); class 1 valid otherwise. Same `MASK_CLASSES` value scheme {0,1,2,3,4}. | | |
| TASK-A05 | In `services/ingestion/akasha_ingest/composite.py`, generalize the analytic **band count** (read from the scene `prepare_manifest.json` / source profile instead of assuming 4). Confirm the most-recent-valid-pixel rule (`RESOURCE_SAT_VALID_MASK_CLASSES = {1,4}`), grid (`grid_from_aoi`, UTM 43N), analytic=bilinear / mask=nearest reprojection, and COG overview resampling all work for 3-band input. | | |
| TASK-A06 | In `services/ingestion/akasha_ingest/catalog.py`, add a `resourcesat-2a-liss4-mx70-l2` entry to `RESOURCESAT_BOA_SOURCE_META` (`instrument="liss-4"`, `label="LISS-4"`, `default_gsd=5.8`) and make `_build_resourcesat_boa_stac_item()` emit **3-band** `eo:bands` (green/red/nir) and `raster:bands` using the manifest's resolution (5.0 for native scene manifests, 5.8 for composites). | | |
| TASK-A07 | Confirm `worker.py` subcommands `bhoonidhi-search`, `bhoonidhi-download`, `bhoonidhi-sync`, `build-composite`, `verify-composite` accept `--source resourcesat-2a-liss4-mx70-l2` (via the guard now including the id). Do **not** change defaults. | | |

### Implementation Phase B — Separate scheduled LISS-4 sync job (staging VM)

- GOAL-B01: Add an independent systemd timer/service/wrapper to run the LISS-4 Bhoonidhi sync at a ~5-day
  cadence on `akasha-staging`, with its own lock, env, and logs, leaving the LISS-3 units unchanged.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-B01 | Add `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.timer` with `OnCalendar` ~ every 5 days (e.g. `*-*-1/5 03:30:00`), `RandomizedDelaySec=30m`, `Persistent=true`, `Unit=akasha-bhoonidhi-liss4-sync.service`. | | |
| TASK-B02 | Add `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.service` (`Type=oneshot`, `EnvironmentFile=-/etc/akasha/bhoonidhi-liss4-sync.env`, `WorkingDirectory=/srv/akasha`, dedicated `flock` lock `/srv/akasha/ingestion/bhoonidhi-liss4-sync.systemd.lock`, `TimeoutStartSec=6h`). | | |
| TASK-B03 | Add `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.sh` wrapper (modeled on `akasha-bhoonidhi-sync.sh`) with `source_id="${AKASHA_SYNC_SOURCE:-resourcesat-2a-liss4-mx70-l2}"`, AOI loop, per-AOI worker lock `bhoonidhi-liss4-sync.${aoi_id}.worker.lock`, and `docker compose run --rm ingestion-worker python worker.py bhoonidhi-sync --source "${source_id}" ...`. | | |
| TASK-B04 | Add `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.env.example` with `AKASHA_SYNC_SOURCE=resourcesat-2a-liss4-mx70-l2`, `AKASHA_SYNC_AOI=bangalore-60km`, `AKASHA_SYNC_WINDOW_DAYS=30`, `AKASHA_SYNC_MAX_DOWNLOADS=3`. | | |
| TASK-B05 | Parameterize `infra/selfhosted/systemd/install-akasha-bhoonidhi-sync.sh` (or add `install-akasha-bhoonidhi-liss4-sync.sh`) to install the LISS-4 unit set to `/opt/akasha/bin/`, `/etc/systemd/system/`, `/etc/akasha/bhoonidhi-liss4-sync.env` without overwriting the LISS-3 units. | | |

### Implementation Phase C — Source registry ungate + STAC seed

- GOAL-C01: Promote the gated LISS-4 registry stub to an active field-analytics source and finalize the STAC
  collection + sample composite item.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-C01 | In `apps/api/app/raster/catalog_resolver.py`, edit the `resourcesat-2a-liss4-mx70-l2` registry entry: remove `availabilityStatus="gated"` and `gatedReason`; set `supportedIndices=["NDVI","MSAVI","NDWI_GREEN_NIR"]`; add `"GREEN":"BAND2"` to `bandRoleMapping`; set `analysisLevel="field"`; set `displayModes=["FCC","NDVI","MSAVI","NDWI_GREEN_NIR"]`, `mapDisplayModes=["NDVI","MSAVI","NDWI_GREEN_NIR"]`, `defaultMapDisplayMode="NDVI"`; add LISS-3-style `layerGroups`; set real `maskMethod="Akasha threshold mask v1 (LISS-4, no SWIR; provisional)"`; set `refreshPolicy` to the ~5-day cadence; keep `resolutionMeters=5.8`, `metricsProvisional=true`. | | |
| TASK-C02 | Finalize `data/seed/stac/resourcesat-2a-liss4-mx70-l2-collection.json`: `instruments=["liss-4"]`, `gsd=[5.8]`, `akasha:supported_indices`, `akasha:display_modes=["FCC",...]`, `akasha:fcc_role_order=["NIR","RED","GREEN"]`, `akasha:band_role_mapping={"GREEN":"BAND2","RED":"BAND3","NIR":"BAND4"}`, `akasha:reflectance={scale:0.0001,offset:0}`, 3-band `item_assets.analytic.eo:bands`/`raster:bands`, and `mask` `classification:classes` {0..4}. | | |
| TASK-C03 | Add a sample composite item `data/seed/stac/resourcesat-2a-liss4-mx70-l2-sample-item.json` mirroring the LISS-3 sample (composite=true, aoi_id=bangalore-60km, grid CRS EPSG:32643, resolution 5.8, analytic/mask asset hrefs under the LISS-4 composite key prefix). | | |

### Implementation Phase D — Per-field best-resolution resolver (the "on top of" core)

- GOAL-D01: Add a BFF resolver that selects the best-resolution source per field+index+date and wire it into the
  overlay, single-date statistics, and hover point endpoints, with provenance in responses. Trend stays LISS-3.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-D01 | Add `resolve_best_resolution_source(*, primary_source_id, index_type, field_geometry, acquisition_date, prefer_high_res=True, window_days=<config>)` in `apps/api/app/raster/catalog_resolver.py` (or a new `resolution_resolver.py`). Logic: if `prefer_high_res` and `index_type ∈ LISS-4 supportedIndices` and a LISS-4 composite exists within `±window_days` of `acquisition_date` whose coverage (non-gap mask) intersects `field_geometry` → return LISS-4 source id + its resolved assets + `basisDate`; else return the primary (LISS-3). NDMI/NDRE always return primary. | | |
| TASK-D02 | Add a config value `AKASHA_BEST_RESOLUTION_WINDOW_DAYS` (default e.g. 12) and a `prefer_high_res` toggle plumbed from the request (query/body param, default true). | | |
| TASK-D03 | Wire the resolver into `apps/api/app/routers/analytics_router.py` `_field_statistics`, `_index_overlay_response`, and `_field_index_point_response` so the resolved source's assets/scale/offset/mask are read instead of the primary's. Keep `compute_statistics()` source-id-driven. | | |
| TASK-D04 | Ensure `_native_trend_response()` (trend) continues to use the **primary** (LISS-3) source only; add a response annotation indicating LISS-4 enhancement is available for single dates but not mixed into the series. | | |
| TASK-D05 | Extend the statistics / overlay / point response models (`apps/api/app/api_models.py` or the relevant Pydantic models) with `resolvedSourceId: str`, `resolutionMeters: float`, `enhanced: bool`, `basisDate: str | None`. Overlay endpoint also returns these via response headers (e.g. `X-Akasha-Resolved-Source`, `X-Akasha-Resolved-Resolution`, `X-Akasha-Enhanced`). | | |
| TASK-D06 | For NDMI specifically, ensure the response provenance note states moisture is served from LISS-3 even when the field is LISS-4-enhanced for vegetation indices. | | |

### Implementation Phase E — Frontend (source, provenance, NDMI note)

- GOAL-E01: Surface the LISS-4 enhancement and NDMI fallback in the UI; clear the gated badge now that the
  source is active.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-E01 | In `apps/frontend/src/types/api.ts`, add `resolvedSourceId`, `resolutionMeters`, `enhanced`, `basisDate` to the field statistics, overlay, and point response types. | | |
| TASK-E02 | In `apps/frontend/src/lib/api.ts`, parse the new overlay response headers (`X-Akasha-Resolved-Source`, `X-Akasha-Resolved-Resolution`, `X-Akasha-Enhanced`) alongside the existing corner/stretch headers. | | |
| TASK-E03 | In `apps/frontend/src/pages/MapPage.tsx` + `apps/frontend/src/components/scaffold/IndexPanel.tsx`, render an "Enhanced 5 m (LISS-4)" badge and the resolved resolution when `enhanced === true`; add an optional "Prefer high-res" toggle (default on) that sets `prefer_high_res`. | | |
| TASK-E04 | In the moisture/NDMI view, render the provenance note "Moisture served from LISS-3 (24 m) — LISS-4 has no SWIR band." | | |
| TASK-E05 | In `apps/frontend/src/components/map/Legend.tsx`, show the resolved resolution next to the index legend. Confirm `apps/frontend/src/components/layers/SourceCard.tsx` no longer shows the gated badge for LISS-4 (now `availabilityStatus` active). | | |

### Implementation Phase F — Staging validation + gate flip (`ssh akasha-staging`)

- GOAL-F01: Confirm LISS-4 radiometry, build a real composite, ingest it, validate the enhancement end-to-end,
  and enable the scheduled job. Executed on `akasha-staging` (IP-whitelisted) over SSH.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-F01 | `ssh akasha-staging`; run `worker.py bhoonidhi-search --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --lookback-days 90` and assess scene/date availability and AOI coverage feasibility. | | |
| TASK-F02 | Download a sample LISS-4 product; validate 3 bands (Green/Red/NIR), CRS (EPSG:32643 expected), and real reflectance `scale`/`offset`/background + calibrated red/NIR. Update the prepare profile (TASK-A03) and STAC `akasha:reflectance` (TASK-C02) with confirmed values. | | |
| TASK-F03 | Run `worker.py bhoonidhi-sync --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km` (search→download→prepare→composite→verify→ingest); confirm native scene prepare accepts 5.0 m inputs and `verify-composite` passes (CRS, 5.8 m composite grid, mask classes, partial-AOI coverage). | | |
| TASK-F04 | Confirm `GET /api/sources/resourcesat-2a-liss4-mx70-l2/dates` returns composite dates, and a field inside LISS-4 coverage returns `enhanced: true` with `resolutionMeters: 5.8` for NDVI overlay + statistics + point. | | |
| TASK-F05 | Cross-check LISS-4 vs LISS-3 NDVI on an overlapping date for a stable field; record any radiometric offset. If material, annotate (do not blend) per ALT-002. | | |
| TASK-F06 | Install + enable the LISS-4 systemd timer (`systemctl enable --now akasha-bhoonidhi-liss4-sync.timer`); verify a dry-run/triggered run logs cleanly and respects the daily download limit. | | |

## 3. Alternatives

- **ALT-001 (rejected)**: True fused composite COG — write one merged COG using LISS-4 where available and LISS-3
  fill. Rejected: mixes two instruments' calibration into one pixel grid (radiometric guardrail violation),
  highest complexity, and breaks the "separate STAC collections" convention.
- **ALT-002 (chosen for trend)**: Keep the historical trend on a single source (LISS-3) and mark only
  single-date overlays/stats as LISS-4-enhanced. Alternative dual-series trend (LISS-3 line + LISS-4 markers)
  is deferred to avoid step artifacts from inter-instrument NDVI offset.
- **ALT-003 (rejected)**: Independent manual-switch LISS-4 source only (no auto per-field selection). Rejected
  because the user explicitly wants LISS-4 to apply automatically "on top of" LISS-3 for higher accuracy.
- **ALT-004 (rejected)**: Extend the existing LISS-3 systemd timer to loop both sources on one schedule.
  Rejected to keep the proven LISS-3 cadence/locking isolated and to honor the ~5-day LISS-4 revisit.
- **ALT-005 (rejected)**: Separate standalone `prepare_resourcesat_liss4_*.py` script. Rejected in favor of a
  profile-driven extension of the existing prepare script to keep one tested COG/manifest path (PAT-002).

## 4. Dependencies

- **DEP-001**: IP-whitelisted `akasha-staging` VM (egress `20.219.3.35`) reachable via `ssh akasha-staging`,
  with the full Akasha stack (MinIO/STAC/PostGIS/TiTiler) running and disk headroom on `/srv/akasha`.
- **DEP-002**: Valid Bhoonidhi credentials (`BHOONIDHI_USER_ID` / `BHOONIDHI_PASSWORD`) on staging; daily
  download limit and 20-min token TTL respected by the existing client.
- **DEP-003**: Confirmed Bhoonidhi collection id `ResourceSat-2A_LISS4-MX70_L2` (validated present in catalog).
- **DEP-004**: Pinned geospatial deps (GDAL / rasterio / rio-cogeo / rio-tiler / TiTiler) unchanged (GUD-001).
- **DEP-005**: Existing source-parameterized worker/composite/catalog code paths (LISS-3) as the template.

## 5. Files

- **FILE-001**: `services/ingestion/akasha_ingest/bhoonidhi.py` — LISS-4 source/collection constants + `SOURCE_COLLECTIONS`.
- **FILE-002**: `services/ingestion/akasha_ingest/config.py` — `RESOURCESAT_LISS4_COLLECTION_ID` + `RESOURCESAT_BOA_COLLECTION_IDS`.
- **FILE-003**: `scripts/prepare_resourcesat_liss3_boa_cogs.py` — LISS-4 `SOURCE_PROFILES` entry, 3-band `analytic_bands`, SWIR-free mask builder.
- **FILE-004**: `services/ingestion/akasha_ingest/composite.py` — generalize analytic band count (3 vs 4).
- **FILE-005**: `services/ingestion/akasha_ingest/catalog.py` — `RESOURCESAT_BOA_SOURCE_META` + 3-band STAC item builder.
- **FILE-006**: `services/ingestion/worker.py` — source guard (no default change).
- **FILE-007**: `infra/selfhosted/systemd/akasha-bhoonidhi-liss4-sync.{timer,service,sh,env.example}` (new).
- **FILE-008**: `infra/selfhosted/systemd/install-akasha-bhoonidhi-sync.sh` (parameterize) or new `install-akasha-bhoonidhi-liss4-sync.sh`.
- **FILE-009**: `apps/api/app/raster/catalog_resolver.py` — ungate LISS-4 stub + `resolve_best_resolution_source`.
- **FILE-010**: `apps/api/app/raster/service.py` — source-id-driven stats / `supported_indices` gate (resolver hook).
- **FILE-011**: `apps/api/app/routers/analytics_router.py` — `_field_statistics`, `_index_overlay_response`, `_field_index_point_response`, `_native_trend_response`.
- **FILE-012**: `apps/api/app/api_models.py` — provenance fields on stats/overlay/point responses.
- **FILE-013**: `data/seed/stac/resourcesat-2a-liss4-mx70-l2-collection.json` + `...-sample-item.json`.
- **FILE-014**: `apps/frontend/src/types/api.ts` — provenance fields.
- **FILE-015**: `apps/frontend/src/lib/api.ts` — parse new overlay headers.
- **FILE-016**: `apps/frontend/src/pages/MapPage.tsx`, `apps/frontend/src/components/scaffold/IndexPanel.tsx`, `apps/frontend/src/components/map/Legend.tsx`, `apps/frontend/src/components/layers/SourceCard.tsx` — badge, toggle, NDMI note.

## 6. Testing

- **TEST-001**: `tests/test_prepare_resourcesat_liss4_mx70_l2_cogs.py` — synthetic 3-band input produces a
  3-band analytic COG + 1-band mask COG with classes {0,1,2,3,4} via the SWIR-free mask builder; manifest valid.
- **TEST-002**: `tests/test_resourcesat_composite.py` (extend) — 3-band scenes composite to a valid AOI mosaic
  (UTM 43N, 5.8 m composite grid, most-recent-valid rule, analytic/mask separate).
- **TEST-003**: `tests/test_bhoonidhi_ingestion.py` (extend) — LISS-4 source id maps to collection
  `ResourceSat-2A_LISS4-MX70_L2`; `bhoonidhi-sync` guard accepts the id.
- **TEST-004**: `tests/test_bhoonidhi_systemd_artifacts.py` (extend) — LISS-4 timer/service/wrapper/env exist,
  reference the LISS-4 source id, separate lock paths, and ~5-day `OnCalendar`.
- **TEST-005**: `apps/api/tests` — `source_payload("resourcesat-2a-liss4-mx70-l2")` returns
  `availabilityStatus="active"`, `supportedIndices=["NDVI","MSAVI","NDWI_GREEN_NIR"]`, `analysisLevel="field"`.
- **TEST-006**: `apps/api/tests` — `resolve_best_resolution_source` prefers LISS-4 when a covering composite is
  within the date window; falls back to LISS-3 otherwise; NDMI always returns LISS-3.
- **TEST-007**: `apps/api/tests` — overlay / statistics / point responses include
  `resolvedSourceId`/`resolutionMeters`/`enhanced`/`basisDate`; trend stays LISS-3.
- **TEST-008**: `apps/frontend` (vitest) — enhancement badge renders when `enhanced=true`; NDMI provenance note
  renders; SourceCard shows no gated badge for active LISS-4.
- **TEST-009**: Staging end-to-end (Phase F) — `/api/sources/{liss4}/dates` non-empty; a covered field returns
  `enhanced: true` NDVI; visual EOS comparison.

## 7. Risks & Assumptions

- **RISK-001**: LISS-4 L2 radiometry (scale/offset/background) differs from the 0.0001/0.0 placeholder →
  wrong reflectance/index. Mitigation: TASK-F02 validates before the gate flip; profile/STAC updated.
- **RISK-002**: SWIR-free provisional mask is weaker (no SWIR cloud/shadow discrimination) → more residual
  cloud. Mitigation: keep `metricsProvisional: true`, honest `maskMethod`, sample multiple scenes on staging.
- **RISK-003**: LISS-4 70 km swath + cloud → sparse/partial AOI coverage and gaps in enhancement. Mitigation:
  per-field fallback to LISS-3 (REQ-001); coverage check in the resolver (TASK-D01).
- **RISK-004**: Inter-instrument NDVI offset (LISS-3 vs LISS-4) creates visible steps if mixed into trends.
  Mitigation: trend stays single-source (REQ-006 / ALT-002); cross-check in TASK-F05.
- **RISK-005**: Daily Bhoonidhi download limit + max-session/token TTL throttle backfill. Mitigation: separate
  cadence + `AKASHA_SYNC_MAX_DOWNLOADS`, spread backfill across runs.
- **RISK-006**: Generalizing composite band count could regress the LISS-3 path. Mitigation: TEST-002 covers
  both 3- and 4-band; run the full LISS-3 ingestion test suite.
- **ASSUMPTION-001**: LISS-4 MX70 product layout matches the per-band `BANDx.tif` + `BAND_META.txt` structure
  used by LISS-3 prep; confirmed/adjusted in TASK-F02.
- **ASSUMPTION-002**: `akasha-staging` egress remains the whitelisted static IP `20.219.3.35`.
- **ASSUMPTION-003**: A configurable date window (default ~12 days) is acceptable for matching a LISS-4 composite
  to a selected LISS-3 date for enhancement.

## 8. Related Specifications / Further Reading

- `docs/impl-plan/isro-bhoonidhi-ingestion-phase-plan.md` (Phase 5 / P5-002 — LISS-4 adapter, AOI, composite/dated-timeline model, §2.1 Bhoonidhi API contract)
- `docs/data-ingestion-and-satellite-rules.md` (band order, reflectance, mask classes, resampling, object keys)
- `docs/engineering-dos-donts.md` (source registration guardrails, version pinning)
- `docs/reference/satellite-catalog.md` (ResourceSat-2A LISS-4: 5.0 m native scenes, 5.8 m operational composite grid, ~70 km swath, ~5-day revisit, 3 bands)
- `docs/architecture-tech-stack.md` (services, BFF API contracts)
- `AGENTS.md` / `CLAUDE.md` (domain guardrails, canonical app tree, ingestion CLIs)
