---
goal: Field-Aware Imagery Timeline Availability
version: 1.0
date_created: 2026-07-14
last_updated: 2026-07-14
owner: Akasha Engineering
tags: [feature, satellite, timeline, cloud-filtering, sentinel-2, analytics]
---

# Introduction

Filter field analytics timeline dates using the selected field polygon and the same raster quality policy used by field-index analytics. A displayed date must have an exact-date raster candidate with known provider scene cloud at or below 20 percent, at least one valid field pixel, and field usable pixels at or above the configured 80 percent threshold.

## 1. Requirements & Constraints

- **REQ-001**: The selected-field timeline MUST exclude pipeline dates that cannot produce field analytics for the selected polygon on the exact acquisition date.
- **REQ-002**: Date filtering MUST use `FIELD_MAX_CLOUD_PERCENTAGE` and `FIELD_USABLE_PIXEL_THRESHOLD` from standalone ingestion.
- **REQ-002A**: Missing cloud metadata MUST fail closed; only a known cloud percentage at or below 20 percent may produce an available date.
- **REQ-003**: Date filtering MUST NOT use the field-index plus-or-minus seven-day fallback; each returned date MUST be directly usable.
- **REQ-004**: The filtered date payload MUST preserve the existing `SceneDate` contract and recompute exactly one `isLatestUsable` date.
- **REQ-005**: A global map with no selected field MUST continue to use source-global dates.
- **REQ-006**: Date filtering MUST support Sentinel-2 and every source routed through standalone ingestion.
- **CON-001**: Browser traffic MUST remain same-origin to the product BFF; field geometry and ingestion credentials MUST NOT reach browser responses.
- **CON-002**: Availability evaluation MUST NOT create `field_queries`, tile layers, signed URLs, or other analytics side effects.
- **CON-003**: Each ingestion batch MUST be bounded to at most 64 unique dates; the BFF MUST chunk denser timelines without dropping dates.
- **CON-004**: Raster read failures MUST remain retryable upstream errors and MUST NOT be represented as an empty or unusable timeline.
- **CON-005**: Ingestion readiness and every field-date batch MUST share the BFF request timeout budget; the request MUST return promptly when that budget expires.
- **SEC-002**: The public BFF route MUST use the existing expensive-index per-client rate limit.
- **SEC-001**: Ingestion URLs, MinIO paths, signed query parameters, and API keys MUST remain server-side.
- **PAT-001**: Frontend server state MUST use TanStack Query with a cache key containing field ID, source ID, and index type.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add side-effect-free field-date evaluation to standalone ingestion.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add field-date request/response schemas in `../akasha-ingestion/src/akasha/schemas.py`. | Yes | 2026-07-14 |
| TASK-002 | Add `AnalyticsService.field_dates()` in `../akasha-ingestion/src/akasha/services/analytics.py`, reusing candidate raster statistics with an exact zero-day window and no persistence. | Yes | 2026-07-14 |
| TASK-003 | Add authenticated `POST /api/v1/analytics/field-dates` in `../akasha-ingestion/src/akasha/api/app.py`. | Yes | 2026-07-14 |
| TASK-004 | Add ingestion tests for exact-date filtering, scene-cloud filtering, field-usable filtering, no side effects, typed raster failures, contract invariants, and batch limits. | Yes | 2026-07-14 |

### Implementation Phase 2

- GOAL-002: Adapt field-aware dates through the product BFF.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Add strict ingestion client field-date models and request helper in `apps/api/app/ingestion_client.py`. | Yes | 2026-07-14 |
| TASK-006 | Add rate-limited `GET /api/fields/{field_id}/dates` in `apps/api/app/routers/analytics_router.py`; load field geometry server-side, chunk calls, and filter source-global dates. | Yes | 2026-07-14 |
| TASK-007 | Recompute field usability, preserve true scene-cloud metadata, and recompute the latest usable marker in the BFF response. | Yes | 2026-07-14 |
| TASK-008 | Add BFF contract-drift, authorization, unavailable, chunking, rate-limit, and no-secret-leak tests. | Yes | 2026-07-14 |

### Implementation Phase 3

- GOAL-003: Consume field-aware dates in both field analytics map consumers.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-009 | Extend `getDates`, date query keys, and `useDates` to accept field ID and index type. | Yes | 2026-07-14 |
| TASK-010 | Pass the selected field ID from `MapPage` and `FieldAnalyticsPage`; preserve global dates when no field is selected. | Yes | 2026-07-14 |
| TASK-011 | Add frontend API, query-cache, source-switch, field-switch, and timeline exclusion tests. | Yes | 2026-07-14 |
| TASK-012 | Build, deploy ingestion first, deploy product second, then verify unavailable June dates are absent and a usable May date renders NDVI. | | |

## 3. Alternatives

- **ALT-001**: Call the existing field-index endpoint once per date. Rejected because it creates query records, signed URLs, and tile layers and produces unnecessary network fan-out.
- **ALT-002**: Hide all globally cloudy dates only. Rejected because a globally acceptable date can still be cloudy or outside coverage for the selected field.
- **ALT-003**: Show disabled timeline chips with reasons. Rejected because the requested UX requires unusable dates to be omitted.

## 4. Dependencies

- **DEP-001**: Standalone ingestion readiness must provide the source-global candidate dates.
- **DEP-002**: Precomputed derived index COGs and scene metadata must exist for each date.
- **DEP-003**: Product BFF ingestion bridge configuration and API-key authentication must remain enabled.
- **DEP-004**: TanStack Query remains the frontend server-state layer.

## 5. Files

- **FILE-001**: `../akasha-ingestion/src/akasha/schemas.py` — field-date API models.
- **FILE-002**: `../akasha-ingestion/src/akasha/services/analytics.py` — side-effect-free exact-date evaluation.
- **FILE-003**: `../akasha-ingestion/src/akasha/api/app.py` — authenticated batch endpoint.
- **FILE-004**: `../akasha-ingestion/tests/` — service and API coverage.
- **FILE-005**: `apps/api/app/ingestion_client.py` — server-to-server contract adapter.
- **FILE-006**: `apps/api/app/routers/analytics_router.py` — app-domain field-date route.
- **FILE-007**: `apps/api/tests/` — BFF contract and authorization coverage.
- **FILE-008**: `apps/frontend/src/lib/api.ts` — field-aware date request.
- **FILE-009**: `apps/frontend/src/lib/queries.ts` — field-aware query key/hook.
- **FILE-010**: `apps/frontend/src/pages/MapPage.tsx` — selected-field timeline source.
- **FILE-011**: `apps/frontend/src/pages/monitoring/FieldAnalyticsPage.tsx` — analytics panel date source.
- **FILE-012**: Frontend Vitest files — field-aware timeline behavior.

## 6. Testing

- **TEST-001**: Ingestion returns only exact dates meeting scene-cloud and field-usable thresholds.
- **TEST-002**: Ingestion field-date evaluation creates no field query or tile-layer records.
- **TEST-003**: BFF rejects fields outside the current user and never returns geometry or ingestion internals.
- **TEST-004**: BFF recomputes exactly one latest usable marker after filtering.
- **TEST-005**: TanStack Query cache keys differ by field, source, and index.
- **TEST-006**: Timeline omits June 28 for a field with 58.53 percent usable pixels and retains usable dates.
- **TEST-007**: Global map date behavior remains unchanged when no field is selected.
- **TEST-008**: Full ingestion, BFF, frontend tests, lint, builds, deployed stress, and browser validation pass.

## 7. Risks & Assumptions

- **RISK-001**: Evaluating many dates performs multiple COG range reads; requests are bounded and frontend caching prevents duplicate page-level calls.
- **RISK-002**: Source-global readiness can change while field-date evaluation runs; response consistency is per request and later refetches reconcile changes.
- **RISK-003**: A field may have no usable dates; the existing empty timeline state must render without selecting a stale URL date.
- **ASSUMPTION-001**: All pipeline-backed optical indices share the same valid-pixel mask for a scene.
- **ASSUMPTION-002**: A direct exact-date candidate is required for a displayed chip.

## 8. Related Specifications / Further Reading

[Local remote ingestion bridge](./feature-local-remote-ingestion-bridge-1.md)
[Satellite architecture](../architecture-tech-stack.md)
[Data ingestion and satellite rules](../data-ingestion-and-satellite-rules.md)
