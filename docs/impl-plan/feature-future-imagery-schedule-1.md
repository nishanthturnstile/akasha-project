---
goal: Future-Only Source-Aware Imagery Projection and Daily Sentinel Discovery
version: 1.0
date_created: 2026-07-14
last_updated: 2026-07-14
owner: Akasha Engineering
tags: [feature, satellite, timeline, scheduler, sentinel-2, cloud-filtering]
---

# Introduction

Replace the timeline's client-side projection from the newest field-usable date with a BFF-owned, source-global, strictly future expected acquisition date. Change the standalone Sentinel-2 periodic discovery trigger from weekly to daily so each complete provider day is checked through the existing bounded seven-day, idempotent, cloud-filtered pipeline. A projected acquisition is informational and is not displayed as an available timeline date until ingestion finds provider data with known scene cloud at or below 20 percent and field availability also passes the existing usable-pixel policy.

## 1. Requirements & Constraints

- **REQ-001**: `timeline-next-image` MUST never display a date on or before the current UTC date.
- **REQ-002**: The next expected acquisition MUST be projected from the selected source's source-global latest acquisition, not the selected field's filtered dates and not the currently selected historical date.
- **REQ-003**: The projection MUST advance by the selected source's declared revisit interval until the result is strictly after the current UTC date.
- **REQ-004**: Source revisit intervals MUST be explicit metadata. Sentinel-2 uses 5 days, ResourceSat LISS-3 uses 24 days, ResourceSat LISS-4 uses 5 days, ResourceSat AWiFS uses 5 days, EOS-06 8-day context uses 8 days, and sources without a validated deterministic cadence MUST return no projection.
- **REQ-005**: Changing the selected source MUST change or remove the projected acquisition according to that source's metadata.
- **REQ-006**: Sentinel-2 ingestion discovery MUST run once daily at the configured UTC hour/minute. With no processed scene it MUST bootstrap from the latest seven complete provider days; otherwise it MUST search from the next outstanding expected pass through the latest complete provider day until a clear scene advances the catalog.
- **REQ-007**: A daily Sentinel run that finds no provider data or only scenes above 20 percent cloud MUST complete without publishing a new date; following daily triggers MUST retain the outstanding expected-pass start date until eligible data arrives.
- **REQ-008**: A date MUST enter the field timeline only through the existing exact-date availability contract: known scene cloud at or below 20 percent, field usable pixels at or above 80 percent, and positive valid pixels.
- **REQ-009**: The UI label MUST say `Next expected pass`, not `Next image`, because provider publication, cloud filtering, coverage, and processing are not guaranteed.
- **REQ-010**: Best-available cross-source mode and archive sources MUST not show a single-source expected pass.
- **CON-001**: Browser traffic MUST remain same-origin through the product BFF; no ingestion URLs, API keys, object paths, provider hrefs, or signed URLs may be exposed.
- **CON-002**: Daily Sentinel checks MUST preserve current heavy-worker routing, late acknowledgements, worker-loss recovery, provider item caps, and same-window idempotency behavior. Overlapping catch-up windows MUST skip already complete scenes before mirror or raster work.
- **CON-003**: Do not derive scheduler execution from a field-specific date because field cloud/coverage varies by polygon while provider discovery is source/AOI-global.
- **CON-004**: ResourceSat provider processing remains owned by the existing ResourceSat scheduler/orchestrator. This change MUST NOT bypass its locks, approved-runtime preflight, disk-headroom checks, or source/AOI planner.
- **PAT-001**: Frontend server state MUST continue using the existing source-scoped `useDefaultLayer(sourceId)` TanStack Query key.
- **SEC-001**: Cloud limits remain fail-closed at 20 percent in standalone ingestion and at the BFF response boundary.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define source-aware expected acquisition metadata in the product BFF.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `revisitDays` to source records in `apps/api/app/raster/catalog_resolver.py` only for validated deterministic cadences. | Yes | 2026-07-14 |
| TASK-002 | Add a pure `_next_expected_acquisition_date(latest_date, revisit_days, today)` helper in `apps/api/app/routers/product_router.py`; return `None` for missing/invalid/non-positive cadence and otherwise advance until strictly after `today`. | Yes | 2026-07-14 |
| TASK-003 | Add `revisitDays` and `nextExpectedAcquisitionDate` to both pipeline-backed and native `GET /api/layers/default?sourceId=...` responses using source-global latest acquisition metadata. | Yes | 2026-07-14 |
| TASK-004 | Add BFF tests for stale-history projection, same-day exclusion, source-specific cadence, null cadence, source-global basis, and response contract preservation. | Yes | 2026-07-14 |

### Implementation Phase 2

- GOAL-002: Render only authoritative future projections in the timeline.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Extend `DefaultLayer` in `apps/frontend/src/types/api.ts` with nullable `revisitDays` and `nextExpectedAcquisitionDate`. | Yes | 2026-07-14 |
| TASK-006 | Replace `TimelineBar`'s hard-coded source-kind cadence calculation with nullable `nextExpectedAcquisitionDate` input; defensively hide values on or before the current UTC date. | Yes | 2026-07-14 |
| TASK-007 | Relabel the status to `Next expected pass`; update the tooltip to explain that ingestion and cloud/field quality gates determine when imagery appears. | Yes | 2026-07-14 |
| TASK-008 | Pass the selected source's default-layer projection from `MapPage`; pass `null` in best-available mode. | Yes | 2026-07-14 |
| TASK-009 | Replace cadence-guess tests in `TimelineBar.test.tsx` with future-only, past-date suppression, null, archive/best-mode, and source-switch contract tests. | Yes | 2026-07-14 |

### Implementation Phase 3

- GOAL-003: Run bounded Sentinel discovery daily.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | Change the Sentinel Celery beat entry in `../akasha-ingestion/src/akasha/jobs/celery_app.py` from weekly to daily by removing `day_of_week` from the cron expression and renaming the schedule key. | Yes | 2026-07-14 |
| TASK-011 | Preserve `AKASHA_SENTINEL2_PRELOAD_SCHEDULE_HOUR_UTC`, `AKASHA_SENTINEL2_PRELOAD_SCHEDULE_MINUTE_UTC`, seven-day bootstrap, full-pipeline mode, provider item cap, and heavy-worker routing. Add catalog-backed outstanding-pass catch-up and keep the old day-of-week setting accepted but deprecated. | Yes | 2026-07-14 |
| TASK-012 | Add ingestion tests proving the beat entry is daily, bootstrap remains bounded, the outstanding pass is retained beyond seven days, current incomplete day is excluded, repeated complete scenes skip expensive work, and provider results are locally capped at 20 percent cloud. | Yes | 2026-07-14 |

### Implementation Phase 4

- GOAL-004: Validate and deploy in dependency order.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Run standalone ingestion pytest and Ruff; run product BFF pytest/Ruff; run complete frontend Vitest, TypeScript/Vite build, and ESLint. | Yes | 2026-07-14 |
| TASK-014 | Perform adversarial review for past-date regressions, field/global confusion, unbounded retries, duplicate heavy jobs, and secret leakage. | Yes | 2026-07-14 |
| TASK-015 | Commit current branches, deploy ingestion first, validate the daily beat entry and private health, then deploy product and validate the future-only label in the authenticated browser. | | |

## 3. Alternatives

- **ALT-001**: Add 5 days to the newest field date and clamp to tomorrow. Rejected because it ignores source cadence and loses orbital phase after long cloud-filtered gaps.
- **ALT-002**: Keep the client calculation but add source-kind constants. Rejected because `optical` includes missions with different revisit intervals and duplicates product metadata in the browser.
- **ALT-003**: Display the scheduler's next run as `Next image`. Rejected because a scheduler run is a discovery attempt, not a guaranteed acquisition or usable product.
- **ALT-004**: Retry Sentinel processing continuously until data appears. Rejected because it is unbounded and can overload provider, network, disk, and heavy-worker capacity. One bounded daily check meets the requirement safely.
- **ALT-005**: Publish cloudy acquisitions as disabled chips. Rejected because the accepted product behavior is to omit dates above 20 percent cloud or below field usability thresholds.

## 4. Dependencies

- **DEP-001**: `GET /api/layers/default` remains source-scoped and backed by source-global readiness/catalog dates.
- **DEP-002**: TanStack Query continues to cache default-layer metadata by source ID.
- **DEP-003**: Celery beat, Redis, and the heavy worker remain healthy on `akasha-staging`.
- **DEP-004**: Earth Search continues to support cloud-filtered Sentinel-2 discovery for complete provider days.
- **DEP-005**: Existing field-date filtering remains deployed before this UI projection change.

## 5. Files

- **FILE-001**: `apps/api/app/raster/catalog_resolver.py` — source revisit metadata.
- **FILE-002**: `apps/api/app/routers/product_router.py` — future expected-acquisition projection and default-layer response.
- **FILE-003**: `apps/api/tests/test_product_sources.py`, `apps/api/tests/test_pipeline_ingestion_bridge.py`, or focused product tests — BFF projection coverage.
- **FILE-004**: `apps/frontend/src/types/api.ts` — typed default-layer projection fields.
- **FILE-005**: `apps/frontend/src/components/timeline/TimelineBar.tsx` — authoritative future-only display.
- **FILE-006**: `apps/frontend/src/components/timeline/TimelineBar.test.tsx` — timeline regression coverage.
- **FILE-007**: `apps/frontend/src/pages/MapPage.tsx` and `MapPage.test.tsx` — selected-source wiring.
- **FILE-008**: `../akasha-ingestion/src/akasha/jobs/celery_app.py` — daily Sentinel beat schedule.
- **FILE-009**: `../akasha-ingestion/tests/test_sentinel2_scheduler.py` — daily schedule and bounded rolling-window tests.
- **FILE-010**: `docs/impl-plan/feature-future-imagery-schedule-1.md` — executable implementation record.

## 6. Testing

- **TEST-001**: Latest source-global date `2026-05-19`, cadence 5, and UTC today `2026-07-14` projects `2026-07-18`, never `2026-05-24`.
- **TEST-002**: A projected date equal to today advances by one revisit interval and is strictly future.
- **TEST-003**: Sentinel, LISS-3, LISS-4, AWiFS, and EOS-06 projections use 5, 24, 5, 5, and 8 days respectively.
- **TEST-004**: Archive, gated nondeterministic, and best-available modes render no expected-pass status.
- **TEST-005**: Changing source updates `nextExpectedAcquisitionDate` through the source-scoped default-layer query.
- **TEST-006**: Celery beat registers Sentinel discovery daily at the configured UTC hour/minute without `day_of_week` restriction.
- **TEST-007**: Daily Sentinel discovery bootstraps with exactly seven complete provider days, excludes the current UTC day, and then retains the outstanding expected-pass start date until eligible data arrives.
- **TEST-008**: A no-result daily run completes without producing dates; later daily catch-up windows remain eligible, while repeated already-complete scenes skip mirror, COG generation, object writes, and pgSTAC registration.
- **TEST-009**: Provider searches continue to cap scene cloud at 20 percent and field dates continue to require at least 80 percent usable pixels.
- **TEST-010**: Deployed browser status says `Next expected pass` with a strictly future date and the selected source's timeline still omits cloudy/unusable acquisitions.

## 7. Risks & Assumptions

- **RISK-001**: Revisit cadence predicts a pass, not provider publication or AOI coverage. Mitigation: use `expected` wording and an explanatory tooltip.
- **RISK-002**: A long provider delay expands the outstanding catch-up date range. Mitigation: run only once daily, retain the provider page/item cap and cloud query, skip complete scenes before expensive work, preserve same-window idempotency, and keep heavy-worker concurrency bounded.
- **RISK-003**: A cloud-filtered source-global readiness date may be older than recent rejected acquisitions. Projection advances by whole source cycles until future, preserving a future orbital-phase estimate without exposing rejected dates.
- **RISK-004**: ResourceSat scheduler semantics differ from Sentinel. Mitigation: do not bypass its existing six-hour orchestrator wake-up, planner cadence, locks, approved-runtime checks, or disk guardrails in this change.
- **ASSUMPTION-001**: The declared revisit intervals are product-level planning values, not guarantees of scene coverage over every field.
- **ASSUMPTION-002**: UTC date boundaries are authoritative for scheduler and projection calculations.
- **ASSUMPTION-003**: Sentinel provider data for an acquisition may arrive after the pass date; daily rolling discovery captures delayed publication on a later run.

## 8. Related Specifications / Further Reading

[Field-aware timeline availability](./feature-field-aware-imagery-timeline-1.md)
[Satellite scheduler architecture](./architecture-satellite-ingestion-scheduler-1.md)
[Satellite ingestion orchestration](../satellite-ingestion-orchestration-and-scheduler.md)
[Akasha platform architecture](../architecture-tech-stack.md)
