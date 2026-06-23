---
goal: Bhoonidhi ResourceSat BOA Diagnostic Download Endpoint
version: 1.0
date_created: 2026-06-14
last_updated: 2026-06-14
owner: Akasha Engineering
tags: feature, diagnostic, bhoonidhi, resourcesat, boa, fastapi, staging, ingestion
---

# Introduction

This plan implements a temporary, admin-only diagnostic endpoint that can be deployed to the Akasha staging VM and used to validate Bhoonidhi ResourceSat-2A LISS-3 BOA product downloads from the whitelisted egress IP. The endpoint starts a background diagnostic job, downloads one Bhoonidhi product using server-side credentials, inspects the archive and raster metadata, and returns a sanitized report identifying available bands, quality/mask candidates, missing data, and implementation recommendations for the full ingestion pipeline.

## 1. Requirements & Constraints

- **REQ-001**: Add a protected BFF endpoint that starts one Bhoonidhi ResourceSat BOA diagnostic job from the API container.
- **REQ-002**: Add a status endpoint that returns job state and sanitized diagnostic output by `jobId`.
- **REQ-003**: Support direct product diagnostics using `collectionId` and `itemId`.
- **REQ-004**: Optionally support search-first diagnostics using `collectionId`, `datetime`, and either `intersects` or `bbox`, but direct `itemId` is the required first implementation path.
- **REQ-005**: Downloaded raw products must remain server-side under `BHOONIDHI_DOWNLOAD_ROOT` and must never be returned to the browser.
- **REQ-006**: Diagnostic output must include archive entry summary, band file candidates, quality/mask candidates, raster metadata where readable, missing expected roles, and next-step recommendations.
- **SEC-001**: Endpoint must require owner/admin role via existing `require_role("owner", "admin")`.
- **SEC-002**: Endpoint must be disabled unless `BHOONIDHI_DIAGNOSTICS_ENABLED=true`.
- **SEC-003**: Endpoint must never include Bhoonidhi credentials, JWTs, refresh tokens, internal paths, or raw download URLs in API responses.
- **SEC-004**: Secrets must come only from server-side env: `BHOONIDHI_USER_ID`, `BHOONIDHI_PASSWORD`, `BHOONIDHI_API_BASE`.
- **CON-001**: Runtime dependencies should remain lean; use stdlib `urllib` for HTTP to match existing BFF patterns unless a later phase intentionally adds `httpx` to runtime requirements.
- **CON-002**: The diagnostic job is temporary and in-memory; it is acceptable to lose status on API restart for this staging-smoke slice.
- **CON-003**: The endpoint must not upload to MinIO, register STAC, or perform COG conversion in this slice.
- **CON-004**: Heavy raster libraries must be imported lazily inside diagnostic inspection functions.
- **PAT-001**: Follow existing BFF router style under `apps/api/app/*.py`, standard Akasha error shape, and FastAPI `TestClient` tests.
- **PAT-002**: Follow TDD: add failing tests before implementation code.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add configuration, models, and test coverage for disabled/secured diagnostic endpoints.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add settings fields in `apps/api/app/config.py`: `bhoonidhi_diagnostics_enabled`, `bhoonidhi_user_id`, `bhoonidhi_password`, `bhoonidhi_api_base`, `bhoonidhi_download_root`, `bhoonidhi_download_timeout_seconds`, `bhoonidhi_max_download_bytes`. | ✅ | 2026-06-14 |
| TASK-002 | Add env placeholders to `apps/api/.env.example`, `infra/selfhosted/env.example`, and staging compose env (`infra/selfhosted/coolify-compose.yml`) without real secrets; bind-mount `/srv/akasha/bhoonidhi-diagnostics` into the staging API container. | ✅ | 2026-06-14 |
| TASK-003 | Create `apps/api/tests/test_bhoonidhi_diagnostics.py` with RED tests for disabled endpoint, owner/admin access, job creation, status lookup, and sanitized result shape. | ✅ | 2026-06-14 |

### Implementation Phase 2

- GOAL-002: Implement the diagnostic job manager, Bhoonidhi client, and product inspector.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Create `apps/api/app/bhoonidhi_diagnostics.py` with Pydantic request/response models, in-memory job store, and router endpoints: `POST /api/admin/bhoonidhi/diagnostics/resourcesat-boa` and `GET /api/admin/bhoonidhi/diagnostics/{job_id}`. | ✅ | 2026-06-14 |
| TASK-005 | Implement stdlib `urllib` Bhoonidhi auth and download helpers inside the diagnostic module: password grant, bearer download, sanitized HTTP errors, file streaming with byte limit. | ✅ | 2026-06-14 |
| TASK-006 | Implement archive/raster inspection helpers: detect zip/tar/plain files, summarize entries, identify `BAND2/BAND3/BAND4/BAND5` candidates, identify quality/cloud/mask candidates, and lazily read raster metadata with rasterio when possible. | ✅ | 2026-06-14 |
| TASK-007 | Include `bhoonidhi_diagnostics.router` in `apps/api/app/main.py`. | ✅ | 2026-06-14 |

### Implementation Phase 3

- GOAL-003: Verify locally without real Bhoonidhi credentials and document staging usage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Mock network calls and create a tiny local zip fixture in tests so tests do not hit Bhoonidhi. | ✅ | 2026-06-14 |
| TASK-009 | Run `cd apps/api && python -m pytest tests/test_bhoonidhi_diagnostics.py -q`. | ✅ | 2026-06-14 |
| TASK-010 | Update `docs/impl-plan/isro-bhoonidhi-ingestion-phase-plan.md` or the diagnostic plan with the manual staging smoke sequence and expected output fields. | ✅ | 2026-06-14 |

### Manual Staging Smoke Sequence

1. Deploy the API image to the Akasha staging VM through the existing Coolify/GHCR flow.
2. In Coolify, set these API env values only on staging: `BHOONIDHI_DIAGNOSTICS_ENABLED=true`, `BHOONIDHI_USER_ID`, `BHOONIDHI_PASSWORD`, `BHOONIDHI_API_BASE=https://bhoonidhi-api.nrsc.gov.in`, `BHOONIDHI_DOWNLOAD_ROOT=/srv/akasha/bhoonidhi-diagnostics`.
3. Confirm the API service has the bind mount `/srv/akasha/bhoonidhi-diagnostics:/srv/akasha/bhoonidhi-diagnostics` and that the host path is on the 512 GiB data disk.
4. Sign in as an owner/admin user through the web app so the browser has the `akasha_session` cookie.
5. Trigger the diagnostic endpoint with `collectionId=ResourceSat-2A_LISS3_BOA` and a known `itemId` from a prior Bhoonidhi search.
6. Poll the returned `statusUrl` until `status` is `succeeded` or `failed`.
7. Inspect `result.bandCandidates`, `result.qualityCandidates`, `result.rasterMetadata`, `result.missing`, and `result.recommendations`.
8. After the diagnostic is captured, set `BHOONIDHI_DIAGNOSTICS_ENABLED=false` and redeploy unless another staging test is needed.

Expected successful result fields:

- `result.download.fileName`, `result.download.bytes`, `result.download.sha256`.
- `result.archive.kind`, `result.archive.entryCount`, `result.archive.entriesByExtension`, `result.archive.sampleEntries`.
- `result.bandCandidates[]` with roles `GREEN`, `RED`, `NIR`, `SWIR1` and matched entries.
- `result.qualityCandidates[]` listing any quality/cloud/shadow/mask candidate files.
- `result.rasterMetadata[]` with readable GeoTIFF metadata where rasterio/GDAL can open the entries.
- `result.missing.roles` and `result.missing.qualityLayer`.
- `result.recommendations[]` with concrete next steps for the ResourceSat prep/composite implementation.

### Live Staging Validation Result — 2026-06-14

The diagnostic was run from the `api` container in the Akasha staging Coolify stack after setting
`BHOONIDHI_DIAGNOSTICS_ENABLED=true` and deploying image tag
`962f8e598699d2573f2019522a2ca4ac89e49b9c`.

Validated runtime facts:

- Container egress IP: `20.219.3.35`.
- Bhoonidhi auth succeeded with `expires_in=1200`.
- `POST /data/search` for `ResourceSat-2A_LISS3_BOA`, `Online=Y`, Bangalore 60 km AOI, 120 day
	lookback returned 5 products.
- Downloaded/inspected product: `RA319MAR2026048153009900065PSANSTUCSRHTDF`.

Observed product facts:

| Field | Result |
| --- | --- |
| `GREEN` | `BAND2.tif` present |
| `RED` | `BAND3.tif` present |
| `NIR` | `BAND4.tif` present |
| `SWIR1` | `BAND5.tif` present |
| Metadata sidecar | `BAND_META.txt` present |
| Native quality/cloud/shadow/mask raster | Not found |
| Raster metadata | 4/4 sampled rasters readable |
| Raster size | `7657 x 7230` |
| CRS | `EPSG:32643` |
| Data type | `uint16` |
| Native GeoTIFF nodata tag | `None` |

Conclusion: the diagnostic endpoint and Bhoonidhi access path are validated. The full ingestion
pipeline must proceed with an Akasha-generated provisional `mask.tif` fallback unless later samples
or NRSC documentation expose a separate native quality layer.

## 3. Alternatives

- **ALT-001**: Synchronous one-shot endpoint. Rejected because real Bhoonidhi downloads can be large and would risk request timeouts.
- **ALT-002**: Ingestion-worker CLI only. Rejected for this slice because the user needs a staging-deployed endpoint to confirm image deployment and whitelisted egress behavior through the running stack.
- **ALT-003**: Full durable job queue with database persistence. Rejected for this temporary diagnostic slice; in-memory status is enough for a staging smoke test and avoids schema churn.
- **ALT-004**: Add runtime `httpx`. Rejected for this slice because the repo already uses stdlib `urllib` in runtime BFF HTTP paths and keeps `httpx` test-only.

## 4. Dependencies

- **DEP-001**: Existing FastAPI BFF in `apps/api/app/main.py`.
- **DEP-002**: Existing auth dependencies in `apps/api/app/auth.py`, especially `require_role`.
- **DEP-003**: Existing standard error payload helpers in `apps/api/app/raster/errors.py`.
- **DEP-004**: Runtime `rasterio` is already present in `apps/api/requirements.txt`, but must be imported lazily.
- **DEP-005**: Bhoonidhi credentials and whitelisted staging egress IP must be configured outside git.

## 5. Files

- **FILE-001**: `apps/api/app/config.py` — add diagnostic env settings.
- **FILE-002**: `apps/api/app/bhoonidhi_diagnostics.py` — new diagnostic router, job manager, client, and inspector.
- **FILE-003**: `apps/api/app/main.py` — include diagnostic router.
- **FILE-004**: `apps/api/tests/test_bhoonidhi_diagnostics.py` — new API/unit tests with mocked network and local archive fixture.
- **FILE-005**: `apps/api/.env.example` — add server-side Bhoonidhi diagnostic placeholders.
- **FILE-006**: `infra/selfhosted/coolify-compose.yml` — add disabled-by-default diagnostic env placeholders for staging/Coolify.
- **FILE-007**: `docs/impl-plan/feature-bhoonidhi-diagnostic-download-1.md` — this implementation plan and smoke instructions.

## 6. Testing

- **TEST-001**: Disabled endpoint returns standard error `BHOONIDHI_DIAGNOSTICS_DISABLED` when feature flag is false.
- **TEST-002**: Missing credentials returns standard error `BHOONIDHI_NOT_CONFIGURED` before any network call.
- **TEST-003**: POST endpoint returns `202` with `jobId`, `status=queued`, and status URL when enabled and configured.
- **TEST-004**: GET unknown job returns `404` with `BHOONIDHI_DIAGNOSTIC_JOB_NOT_FOUND`.
- **TEST-005**: Job runner downloads a mocked zip file and reports expected band candidates (`BAND2`, `BAND3`, `BAND4`, `BAND5`) and quality candidates.
- **TEST-006**: Diagnostic result sanitizes tokens, credentials, and local filesystem paths.
- **TEST-007**: API imports succeed without requiring Bhoonidhi credentials or real network access.

## 7. Risks & Assumptions

- **RISK-001**: Bhoonidhi products may not be zip archives; inspector must support zip, tar, and plain file fallback.
- **RISK-002**: Bhoonidhi downloads may be very large; stream with a configured byte limit and save under `/srv/akasha` on staging.
- **RISK-003**: In-memory jobs disappear on API restart; acceptable for this diagnostic slice.
- **RISK-004**: FastAPI background tasks are not a production queue; full ingestion must move to worker/systemd/cron later.
- **ASSUMPTION-001**: Staging API container has network egress from whitelisted IP `20.219.3.35` when deployed on the Akasha staging VM.
- **ASSUMPTION-002**: `rasterio` can inspect GeoTIFF metadata either directly from extracted candidate files or via GDAL virtual filesystems on staging.

## 8. Related Specifications / Further Reading

- `docs/impl-plan/isro-bhoonidhi-ingestion-phase-plan.md`
- Bhoonidhi API SIS: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/
- Bhoonidhi EULA: https://bhoonidhi.nrsc.gov.in/bhoonidhi/htmls/TnC.html
