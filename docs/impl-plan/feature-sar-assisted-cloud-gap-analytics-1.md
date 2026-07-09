---
goal: SAR-assisted cloud-gap analytics for ResourceSat field indices
version: 1.0
date_created: 2026-06-30
last_updated: 2026-06-30
owner: Akasha engineering
tags: [feature, sar, eos-04, analytics, cloud-gap]
---

# Introduction

Implement a first production-safe SAR-assisted cloud-gap analytics slice. ResourceSat optical indices remain the source of truth for NDVI/MSAVI/NDMI/NDWI. EOS-04 SAR-MRS L2B backscatter is used only as backend support metadata when optical field statistics are cloud/mask limited. The feature must not fabricate NDVI values from SAR and must not expose EOS-04 as a directly selectable optical index source.

## 1. Requirements & Constraints

- **REQ-001**: Existing optical statistics values must remain true optical ResourceSat-derived values.
- **REQ-002**: EOS-04 must be queried only as a backend support source for field analytics.
- **REQ-003**: `sarSupport` must be returned separately from `statistics` and `pixelCounts`.
- **REQ-004**: `sarSupport.available=true` requires a same-field EOS-04 item within `AKASHA_SAR_SUPPORT_WINDOW_DAYS` of the optical acquisition date.
- **REQ-005**: `sarSupport` must include source id, acquisition date, day offset, polarizations, coverage percent, per-band dB stats, and confidence.
- **REQ-006**: `sarSupport` must gracefully degrade to `available=false` when no SAR scene exists or raster reading fails.
- **REQ-007**: Field analytics UI must show SAR support as context only; it must not label it as NDVI/cloud removal.
- **CON-001**: Do not add a direct user-selectable EOS-04 source tab for optical analytics.
- **CON-002**: Do not run routine EOS-04 scheduler jobs in this slice; keep manual/backend refresh.
- **CON-003**: Heavy raster dependencies must remain lazy imports.
- **SEC-001**: Do not expose MinIO/S3 object URLs or credentials in API responses.
- **PAT-001**: Follow existing `app.raster.service.compute_statistics` orchestration and `FieldStatisticsResponse` response-model conventions.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add backend SAR support computation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `apps/api/app/raster/sar_support.py` with `compute_sar_support(geometry, optical_source_id, optical_acquisition_date, optical_cloud_masked_percent, optical_masked_pixels, geometry_bounds)` and lazy rasterio/numpy imports. | ✅ | 2026-06-30 |
| TASK-002 | Add settings `AKASHA_SAR_SUPPORT_WINDOW_DAYS` default `7` and `AKASHA_SAR_SUPPORT_CLOUD_THRESHOLD_PERCENT` default `20`. | ✅ | 2026-06-30 |
| TASK-003 | Extend `apps/api/app/raster/models.py` with Pydantic models for `SarBandStatistics` and `SarSupport`. | ✅ | 2026-06-30 |
| TASK-004 | Attach `sarSupport` to `compute_statistics` responses without changing optical `statistics` values. | ✅ | 2026-06-30 |

### Implementation Phase 2

- GOAL-002: Surface SAR support through field analytics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Extend `apps/api/app/schemas/analytics.py` `FieldStatisticsResponse` with `sar_support`. | ✅ | 2026-06-30 |
| TASK-006 | Pass `computed["sarSupport"]` through `apps/api/app/routers/analytics_router.py` field statistics responses. | ✅ | 2026-06-30 |
| TASK-007 | Extend frontend `FieldStatisticsResponse` types with `sarSupport`. | ✅ | 2026-06-30 |
| TASK-008 | Show a small SAR support note in `apps/frontend/src/components/scaffold/IndexPanel.tsx` when support is available or unavailable due cloud gap. | ✅ | 2026-06-30 |

### Implementation Phase 3

- GOAL-003: Validate behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-009 | Add backend tests proving `sarSupport` appears when optical cloud masking is high and a SAR scene is available. | ✅ | 2026-06-30 |
| TASK-010 | Add backend tests proving optical statistics are unchanged when SAR support is unavailable. | ✅ | 2026-06-30 |
| TASK-011 | Add frontend tests for SAR support messaging. | ✅ | 2026-06-30 |
| TASK-012 | Run targeted backend/frontend validation and staging smoke. | ✅ | 2026-06-30 |

## 3. Alternatives

- **ALT-001**: Directly fill cloudy NDVI pixels using SAR-derived values. Rejected because EOS-04 cannot produce true NDVI and this would be scientifically misleading without calibration.
- **ALT-002**: Expose EOS-04 as a selectable map source. Rejected because user workflow is field/index-first and EOS-04 is a support signal, not an optical index source.
- **ALT-003**: Delay all implementation until ML calibration exists. Rejected because useful SAR availability/confidence metadata can be delivered safely now.

## 4. Dependencies

- **DEP-001**: Existing EOS-04 STAC collection/items with explicit `sar:polarizations`.
- **DEP-002**: Existing MinIO COG storage and API-side rasterio/GDAL S3 credentials.
- **DEP-003**: Existing ResourceSat optical statistics pipeline.

## 5. Files

- **FILE-001**: `apps/api/app/raster/sar_support.py` — SAR support resolver/statistics.
- **FILE-002**: `apps/api/app/raster/models.py` — response models.
- **FILE-003**: `apps/api/app/raster/service.py` — attach SAR support to optical statistics.
- **FILE-004**: `apps/api/app/schemas/analytics.py` — field response schema.
- **FILE-005**: `apps/api/app/routers/analytics_router.py` — field response pass-through.
- **FILE-006**: `apps/api/app/config.py` — SAR support settings.
- **FILE-007**: `apps/frontend/src/types/api.ts` — frontend type additions.
- **FILE-008**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` — support note.
- **FILE-009**: `apps/api/tests/test_slice2.py` — API regression tests.
- **FILE-010**: `apps/frontend/src/components/scaffold/IndexPanel.test.tsx` — UI regression tests.

## 6. Testing

- **TEST-001**: `python -m pytest apps/api/tests/test_slice2.py -q` must pass.
- **TEST-002**: `python -m pytest tests/test_satellite_catalog_registry.py tests/test_pipeline_registry.py tests/test_ingestion_scheduler_systemd_artifacts.py tests/test_deploy_workflows.py tests/test_staging_ingestion_job.py tests/test_orchestrator.py -q` must pass.
- **TEST-003**: Frontend targeted test for `IndexPanel` must pass.
- **TEST-004**: Ruff checks on modified Python files must pass.
- **TEST-005**: Staging `/api/config` must report `adminIngestionLiveTriggerEnabled=true` after environment patch.

## 7. Risks & Assumptions

- **RISK-001**: SAR backscatter heuristics can be misinterpreted as NDVI if UI copy is unclear.
- **RISK-002**: A nearby SAR scene may not overlap the field; resolver must verify bbox/window intersection.
- **RISK-003**: Radar incidence angle and crop stage affect backscatter; this slice reports support/confidence only, not calibrated vegetation estimates.
- **ASSUMPTION-001**: EOS-04 STAC items have valid `backscatter` asset hrefs and explicit polarization metadata.
- **ASSUMPTION-002**: API containers include rasterio/GDAL needed to read EOS-04 COGs in deployed environments.

## 8. Related Specifications / Further Reading

- [docs/data-ingestion-and-satellite-rules.md](../data-ingestion-and-satellite-rules.md)
- [docs/satellite-ingestion-orchestration-and-scheduler.md](../satellite-ingestion-orchestration-and-scheduler.md)
- [test_reports/eos04-validation-2026-06-30.md](../../test_reports/eos04-validation-2026-06-30.md)
