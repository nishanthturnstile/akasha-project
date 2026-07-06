---
goal: Local Development Remote Ingestion Bridge for Sentinel-2 Field Analytics
version: 1.2
date_created: 2026-07-06
last_updated: 2026-07-06
owner: Akasha Engineering
tags: [feature, infrastructure, local-development, ingestion, sentinel-2, field-analytics]
---

> **Implementation status (v1.2):** Phases 1–8 are IMPLEMENTED and validated with automated
> tests. Backend (`apps/api`): 409 passed / 2 skipped, ruff + black clean. Ingestion
> (`akasha-ingestion`): 88 passed, ruff clean (adds the signed `field-index/{query_id}/point`
> endpoint). Frontend (`apps/frontend`): `yarn build` + 346 vitest tests pass, lint clean. Compose
> env resolves (`docker compose config`). A post-implementation code review by Claude Opus 4.8
> (verdict: SHIP) and GPT-5.5 (verdict: SHIP-WITH-FIXES) produced two hardening fixes, both applied:
> (1) the Sentinel pipeline source is only advertised / date-resolved when readiness AND field-index
> AND config are all present (`product_router._pipeline_bridge_enabled`), preventing a half-enabled
> state that advertises `pipelineBacked` while analytics silently go native (REQ-009/REQ-012);
> (2) `ingestion-check` now flags a missing EXPLICIT `INGESTION_SIGNED_URL_ALLOWED_PREFIX` as
> misconfiguration instead of accepting the `INGESTION_API_URL` fallback (TASK-001/TASK-010).
> REMAINING MANUAL (require the live SSH tunnel + deployed ingestion, not runnable in an automated
> pass): TASK-009, TASK-041a (deploy ingestion point endpoint to `akasha-staging` before enabling
> the frontend point UI — currently gated off), TASK-053, and TEST-010/011/015 (browser leak check +
> end-to-end smoke).

> **Review status (v1.1):** Reviewed against the live codebase and independently by two
> models (Claude Opus 4.8 and GPT-5.5). Findings below have been folded back into the tasks,
> requirements, security constraints, and risks. Blockers resolved in-plan: statistics adapter
> completeness + signed-URL leak (TASK-024/026, SEC-006); `DEFAULT_SOURCE_ID` compose hardcoding
> (TASK-004a); config `default_factory` sibling-reference limitation (TASK-001); Sentinel default
> requires three flags together (TASK-018/050); dates/statistics/trend must not silently fall back
> when the bridge is enabled (TASK-018a, REQ-009); trend fan-out timeout/side-effects (TASK-029/030);
> point-lookup caching/throttle to avoid per-mousemove ingestion flooding (TASK-046, TASK-038);
> Phase 6 cross-VM deploy/cutover before enabling point UI (TASK-041a). The plan is
> **ready to implement** with these tasks applied.

# Introduction

This implementation plan defines how the Akasha product application can run locally while using
the deployed standalone ingestion pipeline for Sentinel-2 NDVI field analytics. The local browser
must continue to call only the local product app origin (`/api/*`). The local FastAPI BFF will call
the deployed ingestion API server-to-server through an SSH tunnel, fetch signed ingestion resources
server-side, and return app-domain responses to the frontend.

The target workflow is: a developer starts the local product app, selects or defaults to
`sentinel-2-l2a`, draws or selects a field, and sees Sentinel-2 NDVI overlays, statistics, trends,
and point samples computed from the deployed ingestion pipeline data rather than from local
ResourceSat TIFF/COG files.

## 1. Requirements & Constraints

- **REQ-001**: The local browser must call only the local product app origin through `/api/*` and
  `/tiles/*`; it must never call the deployed ingestion API directly.
- **REQ-002**: When the local remote-ingestion bridge is enabled, `sentinel-2-l2a` must be visible
  in `/api/sources` and available in the frontend source picker.
- **REQ-003**: When the local remote-ingestion bridge is enabled, a fresh local UI session must be
  able to default to `sentinel-2-l2a` without requiring local ResourceSat COGs.
- **REQ-004**: Sentinel-2 source dates in the local UI must come from the deployed ingestion
  readiness endpoint through the local BFF endpoint `/api/sources/sentinel-2-l2a/dates`. When the
  readiness bridge is enabled, a readiness transport/config failure for Sentinel-2 must NOT silently
  fall back to the local catalog; it must surface a typed ingestion-unavailable error (see REQ-009).
- **REQ-005**: Sentinel-2 field NDVI overlays must use the field-clipped image-source path:
  `/api/fields/{fieldId}/overlay/NDVI.png?sourceId=sentinel-2-l2a&acquisitionDate=YYYY-MM-DD`.
- **REQ-006**: Sentinel-2 field statistics must use the deployed ingestion `field-index` result
  through the local BFF, not local ResourceSat/native raster statistics.
- **REQ-007**: Sentinel-2 trend data must be derived from deployed ingestion pipeline dates and
  field-index responses through the local BFF, with a bounded maximum number of dates.
- **REQ-008**: Sentinel-2 point hover/click lookup must use a same-origin local BFF endpoint and a
  deployed ingestion point endpoint once that endpoint exists.
- **REQ-009**: If the SSH tunnel or ingestion API is unavailable, the BFF must return a typed
  ingestion-unavailable error for Sentinel-2 requests (dates, statistics, trend, overlay, point); it
  must not silently fall back to ResourceSat or to local-catalog dates/native rasters.
- **REQ-010**: ResourceSat native behavior must remain available when a user explicitly selects a
  ResourceSat source and local COGs are present.
- **REQ-011**: The local implementation must be opt-in through local environment variables and must
  not change hosted production defaults unless the hosted deployment explicitly sets the same flags.
- **REQ-012**: The local Sentinel-2-first workflow requires these flags set *together*:
  `DEFAULT_SOURCE_ID=sentinel-2-l2a`, `INGESTION_READINESS_ENABLED=true`,
  `INGESTION_FIELD_INDEX_ENABLED=true`, plus a configured `INGESTION_API_URL`/`INGESTION_API_KEY` and
  signed-URL prefixes. If readiness is off, Sentinel-2 does not appear in `/api/sources`
  (`product_router._pipeline_source_payload`) and the frontend `effectiveSourceId` silently falls
  back; if field-index is off, statistics/trend/overlay silently use native ResourceSat (which fails
  on a fresh checkout with no local COGs). Docs must state the flags are required as a set.
- **SEC-001**: `INGESTION_API_KEY` must remain server-side only. It must not be committed, printed,
  added to frontend environment files, exposed in `/api/config`, or returned in any browser payload.
- **SEC-002**: Ingestion signed URLs and query parameters (`sig`, `kid`, `exp`, `op`) must never be
  returned to browser JavaScript by the product app.
- **SEC-003**: The BFF must validate every signed ingestion URL against an explicit allowed prefix
  before fetching it server-side.
- **SEC-004**: The BFF may rewrite only the allowed URL prefix to the local SSH tunnel fetch prefix;
  it must preserve path and query exactly.
- **SEC-005**: The deployed ingestion API must stay private/server-to-server. SSH tunnel access is
  a developer/operator path, not a browser-facing public API.
- **SEC-006**: Response adapters must never copy ingestion signed URLs or signing params into any
  browser-visible payload. The ingestion `FieldIndexAvailableResponse` contains `tileUrl`,
  `statsUrl`, `overlayUrl`, (future) `pointUrl`, and `layerId` with `sig/kid/exp/op` query params.
  Adapters (TASK-024, trend/point) must build `metadata` from an explicit allow-list
  (e.g. `provider`, `scope`, `queryId`, `providerRoute`, `versions`) and must never include those
  URL/param fields or spread the raw ingestion dict into the response.
- **CON-001**: The local frontend remains a Vite dev server that proxies `/api` and `/tiles` to the
  local web gateway.
- **CON-002**: Local Docker Compose keeps only the `web` gateway published. The API, PostGIS,
  MinIO, STAC API, and TiTiler stay private to the compose network except documented dev-only
  loopback database inspection.
- **CON-003**: The ingestion service signs URLs using its configured `AKASHA_PUBLIC_BASE_URL`. In
  SSH-tunnel local development this value may differ from the local tunnel URL used by the BFF.
- **CON-004**: The current deployed ingestion pipeline has Sentinel-2 data only for the configured
  AOI and dates already processed in ingestion readiness.
- **CON-005**: Current ingestion `field-index` supports field overlay/statistics through signed
  URLs, but point lookup support requires an additive ingestion API extension.
- **PAT-001**: Follow the existing BFF pattern: frontend calls app endpoints; BFF resolves app-owned
  field geometry and calls ingestion server-to-server.
- **PAT-002**: Follow the existing MapLibre pattern: field index heatmaps render as field-clipped
  `image` sources, not full-scene XYZ tiles.
- **PAT-003**: Keep heavy geospatial imports lazy in the BFF and avoid requiring rasterio/shapely
  at `app.main` import time.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add safe local SSH-tunnel ingestion bridge configuration and signed URL rewrite support.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Modify `apps/api/app/config.py`. Add `ingestion_signed_url_allowed_prefix: str`, `ingestion_signed_url_fetch_prefix: str`, and `ingestion_trend_max_dates: int`. NOTE: `Settings` uses `field(default_factory=lambda: _get(ENV))` and a `default_factory` CANNOT reference a sibling field. Implement the fallbacks inside each factory by reading env directly: allowed-prefix factory reads `INGESTION_SIGNED_URL_ALLOWED_PREFIX` and, if empty, `INGESTION_API_URL`; fetch-prefix factory reads `INGESTION_SIGNED_URL_FETCH_PREFIX` and, if empty, the same allowed-prefix env resolution (NOT the sibling attribute). Normalize both with `.rstrip('/')`. `ingestion_trend_max_dates` defaults to `12`. When the bridge is enabled, treat an empty allowed prefix as a misconfiguration in `ingestion-check` (TASK-010). | | |
| TASK-002 | Modify `apps/api/app/ingestion_client.py`. Replace the current single-prefix validation in `fetch_signed_ingestion_binary()` with a helper `_validate_and_rewrite_signed_url(settings, url)` that requires `url.startswith(allowed_prefix + "/")` (raise `INGESTION_UPSTREAM_FORBIDDEN` otherwise), then rebuilds the URL as `fetch_prefix + url[len(allowed_prefix):]` (prefix-slice replacement, NOT `str.replace`, so mid-URL occurrences are never rewritten). Preserve the path and query string byte-for-byte. Open the rewritten URL server-side. | | |
| TASK-003 | Modify `apps/api/app/ingestion_client.py`. Add `fetch_signed_ingestion_json()` using the same validate-and-rewrite helper as binary fetches. NOTE: this is only exercised by Phase 6 point lookup — Phase 4/5 statistics/trend read the inline nested `statistics` object already returned by `field-index` and do NOT need a signed JSON fetch. | | |
| TASK-004 | Modify `infra/docker/docker-compose.yml`. Pass `INGESTION_API_URL`, `INGESTION_API_KEY`, `INGESTION_REQUEST_TIMEOUT_SECONDS`, `INGESTION_FIELD_INDEX_ENABLED`, `INGESTION_READINESS_ENABLED`, `INGESTION_AOI_ID`, `INGESTION_SIGNED_URL_ALLOWED_PREFIX`, `INGESTION_SIGNED_URL_FETCH_PREFIX`, and `INGESTION_TREND_MAX_DATES` into the `api` service environment using `${VAR:-}` defaults so hosted/Coolify behavior is unchanged when unset. Note the base compose already defines a local `ingestion` service (`akasha-ingestion:slice1`) — these vars point at the *deployed* ingestion over the tunnel, not that local service. | | |
| TASK-004a | Modify `infra/docker/docker-compose.yml`. The `api` service currently HARDCODES `DEFAULT_SOURCE_ID: "resourcesat-2a-liss3-boa"` (~line 80), so a local `.env` value would be ignored. Change it to `DEFAULT_SOURCE_ID: "${DEFAULT_SOURCE_ID:-resourcesat-2a-liss3-boa}"` so the local opt-in in TASK-018 takes effect while the production default stays ResourceSat. Verify the substitution reaches the container with `docker compose -f infra/docker/docker-compose.yml config`. | | |
| TASK-005 | Modify `infra/docker/docker-compose.dev.yml`. Add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `api` service for Linux Docker Engine compatibility. Keep Windows Docker Desktop behavior unchanged. | | |
| TASK-006 | Modify `infra/docker/.env.example`. Add commented local remote-ingestion placeholders with no real secret values. Include `INGESTION_API_URL=http://host.docker.internal:18081`, `INGESTION_API_KEY=CHANGE_ME`, `INGESTION_READINESS_ENABLED=false`, `INGESTION_FIELD_INDEX_ENABLED=false`, `INGESTION_AOI_ID=bangalore_60km_geodesic_aoi`, `INGESTION_SIGNED_URL_ALLOWED_PREFIX=http://10.10.2.4:18080`, `INGESTION_SIGNED_URL_FETCH_PREFIX=http://host.docker.internal:18081`, `INGESTION_TREND_MAX_DATES=12`, and `DEFAULT_SOURCE_ID=resourcesat-2a-liss3-boa` (documented as the local Sentinel opt-in override to `sentinel-2-l2a`). | | |
| TASK-007 | Modify `scripts/dev-local.sh`. When creating `infra/docker/.env`, generate disabled bridge placeholders only (reuse the existing `upsert_env_value`/`read_env_value`/`is_placeholder_or_empty` helpers). When updating an existing `.env`, add missing keys (`INGESTION_*`, `DEFAULT_SOURCE_ID`) with disabled/empty values but do not overwrite user-provided values. | | |
| TASK-008 | Create `scripts/local-ingestion-tunnel.sh`. Implement a helper that opens `127.0.0.1:18081 -> 10.10.2.4:18080` through the configured SSH host. It must print the matching `.env` values and must not print `INGESTION_API_KEY`. | | |
| TASK-009 | Verify Phase 1 AFTER Phase 2 lands (the `ingestion-check` command is added in TASK-010). Start the SSH tunnel and run from the API container: `python -m app.cli ingestion-check`. (Ordering note: TASK-009 is deferred verification; do not attempt before TASK-010.) | | |

### Implementation Phase 2

- GOAL-002: Add developer-visible ingestion bridge preflight and diagnostics without leaking secrets.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | Modify `apps/api/app/cli.py`. Add command `python -m app.cli ingestion-check`. It must verify bridge config presence, `INGESTION_API_URL/health`, and authenticated readiness for `sourceId=sentinel-2-l2a&aoiId=<INGESTION_AOI_ID>`. It must redact the API key and all signed URLs. | | |
| TASK-011 | Modify `apps/api/app/main.py`. Extend `/health` and `/api/health` only with non-sensitive booleans: `ingestionConfigured`, `ingestionReadinessEnabled`, and `ingestionFieldIndexEnabled`. Do not include URLs or keys. | | |
| TASK-012 | Add tests in `apps/api/tests/test_ingestion_client.py`. Cover configured/unconfigured state, allowed-prefix validation, fetch-prefix rewrite, forbidden signed URL rejection, and HTTP error redaction. | | |
| TASK-013 | Add tests in `apps/api/tests/test_cli_ingestion_check.py`. Mock HTTP calls and verify success/failure output does not include API keys. | | |
| TASK-014 | Verify Phase 2 with `cd apps/api && python -m pytest tests/test_ingestion_client.py tests/test_cli_ingestion_check.py -q`. | | |

### Implementation Phase 3

- GOAL-003: Make Sentinel-2 the configured local default source while preserving hosted ResourceSat defaults.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Modify `apps/api/app/routers/product_router.py`. Add `defaultSourceId: settings.default_source_id` to `/api/config`. This value must be non-secret and must default to `resourcesat-2a-liss3-boa` unless local `.env` overrides it. | | |
| TASK-016 | Modify `apps/frontend/src/types/api.ts`. Add `defaultSourceId: string` to `AppConfig`. | | |
| TASK-017 | Modify `apps/frontend/src/pages/MapPage.tsx`. Update `effectiveSourceId` selection priority: valid `activeSourceId`, then valid `configQ.data.defaultSourceId`, then first source from `/api/sources`. | | |
| TASK-018 | Modify `infra/docker/.env.example` and `docs/developer-setup-guide.md`. Document that the local Sentinel-2-first workflow requires, TOGETHER: `DEFAULT_SOURCE_ID=sentinel-2-l2a`, `INGESTION_READINESS_ENABLED=true`, `INGESTION_FIELD_INDEX_ENABLED=true`, and a configured `INGESTION_API_URL`/`INGESTION_API_KEY`/prefixes (see REQ-012). State that omitting readiness hides Sentinel-2 from `/api/sources`, and omitting field-index causes silent native ResourceSat fallback that fails without local COGs. Depends on TASK-004a so the `.env` `DEFAULT_SOURCE_ID` actually reaches the container. Keep production default as ResourceSat. | | |
| TASK-018a | Modify `apps/api/app/routers/product_router.py`. When `settings.ingestion_readiness_enabled` is true for a pipeline source, `_pipeline_dates()` must NOT swallow readiness transport/config failures and return `None` (which currently causes `get_source_dates()` to fall back to `catalog.list_dates`). Instead raise a typed `INGESTION_API_UNREACHABLE`/`INGESTION_READINESS_UNAVAILABLE` error, and treat `get_readiness()` returning `None`/empty `availableDates` as a typed unavailable error too (REQ-004/REQ-009). Preserve the existing local-catalog path only for non-pipeline sources and when readiness is disabled. | | |
| TASK-019 | Add frontend tests in `apps/frontend/src/pages/MapPage.test.tsx`. Verify `config.defaultSourceId=sentinel-2-l2a` makes Sentinel the first effective source when no persisted active source exists. Verify persisted active source still wins. | | |
| TASK-020 | Verify Phase 3 with `cd apps/frontend && yarn test src/pages/MapPage.test.tsx src/state/mapViewContext.test.tsx`. | | |

### Implementation Phase 4

- GOAL-004: Route Sentinel-2 field statistics through deployed ingestion and adapt ingestion responses into app-owned response contracts.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-021 | Modify `apps/api/app/api_models.py`. Widen `FieldTrendResponse.provider` from literal `"native"` to `"native" | "pipeline"`. Widen `FieldTrendResponse.scope` from `"native_fallback"` to `"native_fallback" | "pipeline"`. | | |
| TASK-022 | Modify `apps/api/app/schemas/analytics.py`. Widen `FieldStatisticsResponse.provider` from `"native"` to `"native" | "pipeline"`. Keep `scope="field"`. | | |
| TASK-023 | Modify `apps/frontend/src/types/api.ts`. Widen `FieldStatisticsResponse.provider` and `FieldTrendResponse.provider` to include `"pipeline"`. Widen `FieldTrendResponse.scope` to include `"pipeline"`. | | |
| TASK-024 | Create `apps/api/app/ingestion_adapters.py`. Implement `field_index_to_statistics_response(result, *, plot_id, source_id, index_type, cloud_mask)` where `result` is the RAW dict returned by `request_field_index()` (NOT a parsed model). (1) If `result.get("status") != "AVAILABLE"` raise `INGESTION_OVERLAY_UNAVAILABLE` (ingestion returns `success=True` even for UNAVAILABLE, so this guard is required). (2) Read stats from the NESTED `result["statistics"]`: `min`, `max`, `mean`, `stdDev -> stddev`, `usablePixelPercentage -> validPixelPercent`, `cloudPercentage -> cloudMaskedPercent`; `coveragePercent` is not provided by ingestion — default `0.0`. (3) Build required fields with no defaults: `cloud_mask=<passed request cloud_mask>`, `pixel_counts=PixelCounts()` (optionally set `validPixels`/`coveragePixels` from `result["selection"]["validPixelCount"]`), `acquisition_date=result["selectedSceneDate"]`, `provider="pipeline"`, `scope="field"`, `resolution_meters=result["resolution"]["displayMeters"]`, `resolved_source_id=source_id`. (4) Build `metadata` from an explicit ALLOW-LIST only (`provider`, `scope`, `queryId`, `providerRoute`, `versions`) — never spread the raw result or include `tileUrl`/`statsUrl`/`overlayUrl`/`layerId` (SEC-006). | | |
| TASK-025 | Modify `apps/api/app/routers/analytics_router.py`. In `post_field_index_statistics()`, if `payload.source_id == catalog.SENTINEL_2_SOURCE_ID` and `settings.ingestion_field_index_enabled` is true, call `request_field_index()` (inside `_run_blocking`, wrapped by the existing `asyncio.wait_for(index_request_timeout_seconds)`) and adapt the raw dict through `field_index_to_statistics_response()`. Pass the request `cloud_mask`, `source_id`, `index_type`, and `plot_id`. Use `max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent)` for parity with the overlay path. | | |
| TASK-026 | Ensure `post_field_index_statistics()` returns `INGESTION_FIELD_INDEX_ERROR` or `INGESTION_OVERLAY_UNAVAILABLE` typed errors for unavailable ingestion responses (via the adapter's status guard). It must not call native `compute_statistics()` for Sentinel-2 when the pipeline flag is enabled — even on ingestion failure it must raise, never silently fall back (REQ-009). | | |
| TASK-027 | Add BFF tests in `apps/api/tests/test_pipeline_ingestion_bridge.py`. Mock `request_field_index()` and verify: (a) an AVAILABLE fixture yields `provider="pipeline"`, `resolutionMeters=10`, correct nested-stats mapping, and a valid `FieldStatisticsResponse` (no Pydantic error); (b) an UNAVAILABLE fixture yields a typed error and does NOT invoke native `compute_statistics`; (c) the serialized response body contains NO `tileUrl`/`statsUrl`/`overlayUrl`/`sig`/`kid`/`exp` (SEC-006 leak check). | | |
| TASK-028 | Verify Phase 4 with `cd apps/api && python -m pytest tests/test_pipeline_ingestion_bridge.py -q`. | | |

### Implementation Phase 5

- GOAL-005: Route Sentinel-2 trend data through deployed ingestion with bounded date fan-out.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-029 | Modify `apps/api/app/ingestion_adapters.py` and `apps/api/app/routers/analytics_router.py`. Add `field_index_to_trend_point(result)` mapping the NESTED `result["statistics"]` -> `mean/min/max/stddev/valid_pixel_percent/cloud_masked_percent` and using `result["selectedSceneDate"]` (NOT the requested date) for `acquisition_date`. Add `_pipeline_trend_response()` that calls `get_readiness()`; if readiness is `None`/config-failed or `availableDates` is empty, raise a typed unavailable error (REQ-009). Otherwise filter `availableDates` by `startDate`/`endDate`, cap to the NEWEST `settings.ingestion_trend_max_dates` dates, call `request_field_index()` per date with `max_cloud_percentage=float(settings.sar_support_cloud_threshold_percent)`, de-duplicate points by resulting `selectedSceneDate`, and return points sorted ASCENDING (matching the native contract). | | |
| TASK-029a | In `get_field_analytics_trend()`, wrap `_pipeline_trend_response()` in an overall `asyncio.wait_for()` budget (the native trend has none; the pipeline path does sequential blocking `urllib` calls of up to `ingestion_request_timeout_seconds` each, so N dates could exceed the gateway timeout). Use a bounded per-date timeout and an overall cap so a 12-date fan-out cannot block for minutes. Document that each `request_field_index()` call persists an ingestion query record + tile layer server-side (side-effect noted in RISK-008). | | |
| TASK-030 | Implement partial failure behavior in `_pipeline_trend_response()`: individual UNAVAILABLE field-index results (status != "AVAILABLE") produce `FieldTrendPoint(acquisition_date=<requested date>, metrics_provisional=True, unavailable_reason=<reason>)`; transport failures for a single date also produce a provisional point. Only raise a typed endpoint error when readiness itself is unavailable or NO points can be produced at all. | | |
| TASK-031 | Modify `get_field_analytics_trend()`. If `sourceId == catalog.SENTINEL_2_SOURCE_ID` and `settings.ingestion_field_index_enabled` is true, return `_pipeline_trend_response()` (with the TASK-029a timeout budget) instead of `_native_trend_response()`. Set `provider="pipeline"`, `scope="pipeline"` on the response. | | |
| TASK-032 | Add BFF tests in `apps/api/tests/test_pipeline_ingestion_bridge.py`. Verify: date filtering by window, newest-N cap, ascending output ordering, de-dup by `selectedSceneDate`, successful trend points (`provider="pipeline"`), unavailable trend points (`metrics_provisional=True`), empty/None readiness -> typed error, no native trend path invoked for Sentinel-2 pipeline requests, and no signed-URL leakage in the serialized body. | | |
| TASK-033 | Verify Phase 5 with `cd apps/api && python -m pytest tests/test_pipeline_ingestion_bridge.py -q`. | | |

### Implementation Phase 6

- GOAL-006: Add ingestion and BFF support for Sentinel-2 point lookup.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-034 | Modify `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\schemas.py`. Add optional `pointUrl: str | None = None` to `FieldIndexAvailableResponse`. Add `FieldIndexPointResponse` schema with `queryId`, `index`, `lng`, `lat`, `value`, `masked`, `maskClass`, and `source`. | | |
| TASK-035 | Modify `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\services\analytics.py`. When field-index is available, sign a point route with operation `point` (query hash `f"{query_id}:point"`, mirroring the existing `stats`/`overlay` signing) and include `pointUrl` in the response. NOTE: `SigningService.sign/verify` accept `operation` as a free string, so no signing-core change is needed. The signed `pointUrl` intentionally does NOT include `lng/lat`; those are appended per-lookup by the BFF (see TASK-038/SEC note). | | |
| TASK-036 | Modify `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\api\app.py`. Add `GET /api/v1/analytics/field-index/{query_id}/point` guarded by `op == "point"`, HMAC verification (query hash `f"{query_id}:point"`), stored-query lookup via a new `AnalyticsService.point_for_query(query_id, lng, lat)` (follow the `overlay_for_query` pattern: load `field_query_repository` record -> raster output -> object store -> sample the pixel with scale/nodata handling), returning value/masked/maskClass. Accept `lng`/`lat` as unsigned query params. | | |
| TASK-037 | Add ingestion tests in `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\tests\test_field_point.py`. Verify signed point URL generation, signature/op rejection, query not found (404), masked response, and valid pixel response. | | |
| TASK-038 | Modify `apps/api/app/ingestion_client.py`. Add `request_field_index_point()` that reuses a cached `(fieldId, sourceId, date, index) -> (queryId, pointUrl)` mapping so a full `request_field_index()` is NOT re-run on every lookup; it appends unsigned `lng`/`lat` to the cached `pointUrl` and fetches the signed point JSON through the allowlist/rewrite helper (`fetch_signed_ingestion_json`). SEC note: appending `lng`/`lat` is an explicit, documented exception to TASK-002's "preserve query exactly" rule — the signature does not cover them, and they carry no secret. Add a short-TTL in-process cache to bound ingestion load. | | |
| TASK-039 | Modify `apps/api/app/routers/analytics_router.py`. In `get_field_index_point()`, if `sourceId == catalog.SENTINEL_2_SOURCE_ID` and `settings.ingestion_field_index_enabled` is true, route to `request_field_index_point()` and return the existing app `FieldIndexPointResponse` shape (never native for Sentinel). | | |
| TASK-040 | Add app BFF tests for pipeline point lookup in `apps/api/tests/test_pipeline_ingestion_bridge.py`. Verify same-origin app endpoint returns value/masked metadata, no ResourceSat/native point path is used for Sentinel-2, cached-query reuse avoids re-calling `request_field_index()`, and no signed URL leaks into the response. | | |
| TASK-041 | Verify Phase 6 with ingestion tests and app tests: `python -m pytest tests/test_analytics_api.py tests/test_field_point.py tests/test_field_overlay.py tests/test_signing.py -q` in `akasha-ingestion`, then `cd apps/api && python -m pytest tests/test_pipeline_ingestion_bridge.py -q` in `akasha-em-git`. | | |
| TASK-041a | DEPLOY/CUTOVER (blocks Phase 7 point UI). The local product app calls the DEPLOYED ingestion behind the tunnel, so the ingestion point changes (TASK-035/036) must be deployed to `akasha-staging` before BFF/frontend point lookup is enabled. Deploy `akasha-ingestion`, verify `pointUrl` appears in the deployed `field-index` response, and verify a signed point fetch succeeds over the SSH tunnel through the BFF. Until then keep frontend Sentinel point lookup gated (TASK-046). | | |

### Implementation Phase 7

- GOAL-007: Replace placeholder field analytics chart with pipeline-aware statistics and trend UI.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-042 | Modify `apps/frontend/src/components/analytics/FieldAnalyticsPanel.tsx`. Pass `sourceId`, selected date, active index type, `cloudMask`, `periodFrom`, and `periodTo` into the chart section. | | |
| TASK-043 | Extract reusable statistics/trend UI from `apps/frontend/src/components/scaffold/IndexPanel.tsx` into a shared component, or move the required query/render logic into `components/analytics/ChartTab.tsx`. | | |
| TASK-044 | Modify `apps/frontend/src/components/analytics/ChartTab.tsx`. Use `useFieldStatistics()` and `useFieldTrend()` for the selected field/source/date/index and render loading, error, unavailable, stats, and trend states. | | |
| TASK-045 | Modify `apps/frontend/src/pages/monitoring/FieldAnalyticsPage.tsx` and `apps/frontend/src/pages/MapPage.tsx` to pass selected date/display mode to `FieldAnalyticsPanel`. IMPORTANT: `FieldAnalyticsPage` currently sets `effectiveSourceId = activeSourceId ?? undefined` (line ~40), which does NOT apply the `defaultSourceId` fallback that `MapPage` uses, so a fresh Sentinel-default session would pass `sourceId=undefined` and the stats/trend queries would not fire. Apply the same source-selection priority (valid `activeSourceId` -> `config.defaultSourceId` -> first `/api/sources`) in `FieldAnalyticsPage`, or centralize it in shared map-view state so both pages agree. | | |
| TASK-046 | Update `CoordinateReadout` integration in `MapPage.tsx`. `CoordinateReadout` invokes `indexLookup` on every `mousemove` (coalesced to one per animation frame), so a pipeline point lookup MUST NOT trigger a fresh `request_field_index()` per cursor move. Gate pipeline-backed Sentinel point lookup so it is (a) disabled entirely until Phase 6 point support is deployed (TASK-041a) — showing no sample or a typed unavailable state, never native ResourceSat COGs for Sentinel-2 — and (b) once enabled, click-only or heavily throttled/debounced and backed by the BFF `(field,source,date,index)` cache from TASK-038. Use the source `pipelineBacked` flag to detect pipeline sources. | | |
| TASK-047 | Add frontend tests for Sentinel-2 pipeline statistics/trend UI and point lookup gating. Use mocked `/api/fields/{id}/indices/statistics`, `/analytics/trend`, and `/indices/point` responses. | | |
| TASK-048 | Verify Phase 7 with `cd apps/frontend && yarn test src/components/analytics src/pages/MapPage.test.tsx src/lib/api.test.ts`. | | |

### Implementation Phase 8

- GOAL-008: Document local setup and provide end-to-end local smoke validation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-049 | Modify `README.md`. Add a short “Local Sentinel-2 remote ingestion mode” section that links to `docs/developer-setup-guide.md`. | | |
| TASK-050 | Modify `docs/developer-setup-guide.md`. Add exact SSH tunnel steps, local `.env` values, local startup steps, and smoke checks. Include Windows Git Bash guidance. | | |
| TASK-051 | Add a smoke payload file under `docs/reference/` or document an approved non-secret test field geometry. Do not include production customer geometry or secrets. | | |
| TASK-052 | Add leak-check instructions: browser network panel must show local app `/api/*` only; no ingestion host/IP, no `host.docker.internal`, no signed `sig/kid/exp`, no API keys, no MinIO/STAC/TiTiler URLs. | | |
| TASK-053 | Verify end-to-end locally: SSH tunnel up, local API configured, `/api/sources/sentinel-2-l2a/dates` returns remote dates, Sentinel-2 overlay returns `200 image/png`, statistics/trend return provider `pipeline`, and UI displays Sentinel-2 10 m NDVI. | | |

## 3. Alternatives

- **ALT-001**: Expose the ingestion API publicly to local browsers. Rejected because it violates the
  one-public-service rule and would expose ingestion endpoints/signed URLs outside the BFF.
- **ALT-002**: Copy deployed Sentinel-2 COGs from ingestion VM into each developer laptop. Rejected
  because it duplicates large raster data, makes fresh checkouts heavy, and bypasses the new
  standalone ingestion architecture.
- **ALT-003**: Keep ResourceSat as the only local default and require developers to manually select
  Sentinel-2. Rejected for this scenario because a fresh checkout without ResourceSat COGs should be
  able to validate the new pipeline-first Sentinel workflow.
- **ALT-004**: Use full-scene Sentinel XYZ tiles for the field heatmap. Rejected because the field
  analytics requirement is a field-clipped overlay image, transparent outside the polygon.
- **ALT-005**: Use VPN/direct private IP only. Accepted as a future option, but not selected for this
  implementation because the requested local workflow uses SSH tunneling.

## 4. Dependencies

- **DEP-001**: Deployed `akasha-ingestion` API reachable from the SSH tunnel target.
- **DEP-002**: Valid ingestion API key configured as local server-side `INGESTION_API_KEY`.
- **DEP-003**: Deployed ingestion `AKASHA_PUBLIC_BASE_URL` known exactly so the local BFF can set
  `INGESTION_SIGNED_URL_ALLOWED_PREFIX`.
- **DEP-004**: Sentinel-2 readiness data exists in ingestion for `sourceId=sentinel-2-l2a` and
  `aoiId=bangalore_60km_geodesic_aoi`.
- **DEP-005**: At least one processed Sentinel-2 date intersects the local test field with sufficient
  usable pixels. Current known validated date is `2026-03-20` for the existing Bangalore test field.
- **DEP-006**: Docker supports API container access to the host tunnel through `host.docker.internal`.
- **DEP-007**: Phase 6 point lookup depends on additive changes in `akasha-ingestion` that must be
  BOTH implemented AND deployed to the tunnel-reachable ingestion VM (TASK-041a) before the frontend
  can enable Sentinel-2 point sampling.
- **DEP-008**: Local developer has SSH access to the tunnel host (`akasha-control` or equivalent).

## 5. Files

- **FILE-001**: `apps/api/app/config.py` — BFF settings for signed URL allowlist/fetch rewrite,
  trend max dates, and default source behavior.
- **FILE-002**: `apps/api/app/ingestion_client.py` — ingestion request helpers and signed URL
  validation/rewrite logic.
- **FILE-003**: `apps/api/app/ingestion_adapters.py` — new adapter module for ingestion field-index
  responses to app statistics/trend/point responses.
- **FILE-004**: `apps/api/app/routers/product_router.py` — expose `defaultSourceId`, pipeline source,
  and ingestion readiness dates.
- **FILE-005**: `apps/api/app/routers/analytics_router.py` — route Sentinel-2 statistics, trend,
  overlay, and point lookup through ingestion.
- **FILE-006**: `apps/api/app/api_models.py` — pipeline provider/scope response literals.
- **FILE-007**: `apps/api/app/schemas/analytics.py` — pipeline provider support for field statistics.
- **FILE-008**: `apps/api/app/cli.py` — local ingestion bridge preflight command.
- **FILE-009**: `infra/docker/docker-compose.yml` — pass ingestion bridge environment into local API
  container.
- **FILE-010**: `infra/docker/docker-compose.dev.yml` — add `host.docker.internal` compatibility for
  local API container.
- **FILE-011**: `infra/docker/.env.example` — safe local remote-ingestion placeholders.
- **FILE-012**: `scripts/dev-local.sh` — generate/update local placeholders without overwriting user
  values.
- **FILE-013**: `scripts/local-ingestion-tunnel.sh` — helper to start the SSH tunnel.
- **FILE-014**: `README.md` — short local Sentinel-2 remote ingestion setup note.
- **FILE-015**: `docs/developer-setup-guide.md` — detailed local tunnel/config/smoke procedure.
- **FILE-016**: `apps/frontend/src/types/api.ts` — `defaultSourceId` and pipeline provider/scope
  types.
- **FILE-017**: `apps/frontend/src/pages/MapPage.tsx` — default-source selection and pipeline point
  lookup gating.
- **FILE-018**: `apps/frontend/src/pages/monitoring/FieldAnalyticsPage.tsx` — pass selected source,
  date, index, mask, and period state to field analytics panel.
- **FILE-019**: `apps/frontend/src/components/analytics/FieldAnalyticsPanel.tsx` — render real
  pipeline-capable chart/statistics section.
- **FILE-020**: `apps/frontend/src/components/analytics/ChartTab.tsx` — implement stats/trend UI.
- **FILE-021**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` — source for extraction or
  reuse of existing analytics UI behavior.
- **FILE-022**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\schemas.py`
  — add point URL and point response schemas.
- **FILE-023**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\api\app.py`
  — add signed point endpoint.
- **FILE-024**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\src\akasha\services\analytics.py`
  — sign point URL and implement point lookup.

## 6. Testing

- **TEST-001**: Add `apps/api/tests/test_ingestion_client.py` for signed URL allowlist validation,
  fetch-prefix rewrite, unconfigured state, upstream HTTP errors, and redaction.
- **TEST-002**: Add `apps/api/tests/test_cli_ingestion_check.py` for `python -m app.cli
  ingestion-check` success/failure output without secret leakage.
- **TEST-003**: Add `apps/api/tests/test_pipeline_ingestion_bridge.py` for Sentinel-2 source/date
  exposure, statistics adapter, trend adapter, overlay unavailable handling, and point lookup
  behavior.
- **TEST-004**: Update `apps/api/tests/test_slice2.py` if needed to preserve legacy native Sentinel
  tests with bridge flags disabled.
- **TEST-005**: Add ingestion tests in `akasha-ingestion/tests/test_field_point.py` or extend
  `test_analytics_api.py` for signed point URL generation, validation, query not found, masked
  point, and valid point response.
- **TEST-006**: Update `akasha-ingestion/tests/test_signing.py` for `op=point` signature behavior.
- **TEST-007**: Update `apps/frontend/src/types/api.ts` compile coverage through `yarn build` after
  adding `defaultSourceId` and pipeline provider/scope types.
- **TEST-008**: Update `apps/frontend/src/pages/MapPage.test.tsx` for `config.defaultSourceId`
  priority and persisted active source priority.
- **TEST-009**: Add frontend tests for `FieldAnalyticsPanel` / `ChartTab` rendering pipeline
  statistics, trend points, loading, unavailable, and error states.
- **TEST-010**: Manual local smoke: SSH tunnel up, local API configured, `/api/sources/sentinel-2-l2a/dates`
  returns remote dates, overlay returns `200 image/png`, stats/trend return provider `pipeline`, and
  UI shows Sentinel-2 10 m NDVI.
- **TEST-011**: Browser leak test: DevTools/network shows only local `/api/*` requests and no
  ingestion host/IP, `host.docker.internal`, signed query params, MinIO, pgSTAC, TiTiler, or API key.
- **TEST-012**: Automated no-leak assertions in `test_pipeline_ingestion_bridge.py`: serialized
  statistics/trend/point response bodies must not contain `tileUrl`, `statsUrl`, `overlayUrl`,
  `pointUrl`, `layerId`, `sig`, `kid`, or `exp` (SEC-006).
- **TEST-013**: Config smoke check: `docker compose -f infra/docker/docker-compose.yml config`
  confirms `DEFAULT_SOURCE_ID` and every `INGESTION_*` var resolve into the `api` service env with the
  `.env` overrides applied (validates TASK-004/004a).
- **TEST-014**: Adapter unit tests (`ingestion_adapters`): AVAILABLE fixture (full valid response),
  UNAVAILABLE fixture (typed error, no native call), missing `statistics` key, nested-stats reads,
  all required app fields populated, and metadata allow-list excludes signed URLs.
- **TEST-015**: Deploy verification (Phase 6, TASK-041a): after deploying `akasha-ingestion`, the
  deployed `field-index` response includes `pointUrl`, and a BFF point lookup over the SSH tunnel
  returns a value/masked result before enabling the frontend point UI.

## 7. Risks & Assumptions

- **RISK-001**: Signed URL prefix mismatch can break local overlay/stat/point fetches over SSH
  tunnel. Mitigation: implement explicit allowed-prefix and fetch-prefix settings with unit tests.
- **RISK-002**: A down SSH tunnel can appear as a UI analytics failure. Mitigation: add
  `ingestion-check` and typed errors that identify remote ingestion as unavailable without exposing
  the private URL or key.
- **RISK-003**: Trend fan-out can be slow or expensive. Mitigation: cap date count using
  `INGESTION_TREND_MAX_DATES` and return partial unavailable points.
- **RISK-004**: Sentinel-2 point lookup requires ingestion changes not yet deployed. Mitigation:
  keep frontend point lookup gated until the ingestion point endpoint is available.
- **RISK-005**: Fresh local default to Sentinel-2 could accidentally affect staging/production.
  Mitigation: use `DEFAULT_SOURCE_ID=sentinel-2-l2a` only in local `.env`; keep production default
  as ResourceSat unless explicitly changed.
- **RISK-006**: Local field geometry may not intersect currently processed Sentinel-2 data or may
  fail usable-pixel thresholds. Mitigation: document known-good test field/date and surface
  unavailable reasons clearly.
- **RISK-007**: Browser leak of signed ingestion URL or API key would violate architecture. Mitigation:
  never return ingestion URLs to the frontend, build adapter `metadata` from an explicit allow-list
  that excludes `tileUrl`/`statsUrl`/`overlayUrl`/`pointUrl`/`layerId`/`sig`/`kid`/`exp` (SEC-006), and
  add automated no-leak assertions (TASK-027/032/040) plus manual network leak checks.
- **RISK-008**: Trend fan-out and repeated stats calls persist a new ingestion query record + tile
  layer per `request_field_index()` invocation (`akasha-ingestion` `services/analytics.py` upserts a
  tile layer and saves a field-query row on every AVAILABLE result), so repeated trend loads grow the
  ingestion DB unboundedly. Mitigation: cap the date fan-out (`INGESTION_TREND_MAX_DATES`), read the
  inline nested `statistics` already returned rather than re-fetching, and track a follow-up for an
  ingestion stats-only/no-overlay-layer path and/or ephemeral-query GC.
- **RISK-009**: Point lookup fires on `mousemove` (per animation frame). A naive pipeline point path
  would call `request_field_index()` per cursor move, flooding the tunnel/ingestion and creating many
  query records. Mitigation: gate until Phase 6 is deployed (TASK-041a), then make point lookup
  click-only or heavily throttled and backed by a BFF `(field,source,date,index)` query/pointUrl cache
  (TASK-038/046).
- **RISK-010**: A down tunnel/ingestion could appear as empty/local Sentinel dates or a native stats
  fallback instead of a clear error. Mitigation: when the bridge is enabled, dates (TASK-018a),
  statistics (TASK-026), trend (TASK-029/030), overlay, and point paths raise typed
  ingestion-unavailable errors and never fall back to local catalog/native rasters (REQ-009).
- **RISK-011**: The "local" workflow depends on DEPLOYING ingestion changes (Phase 6 point endpoint)
  to `akasha-staging` behind the tunnel. Mitigation: keep the deploy/cutover on its own task
  (TASK-041a) off the critical path for Phases 1–5, and gate the frontend point UI until it lands.
- **ASSUMPTION-001**: Developers can SSH to the tunnel host and can obtain the ingestion API key
  through an approved secret channel.
- **ASSUMPTION-002**: Deployed ingestion `AKASHA_PUBLIC_BASE_URL` remains stable and known for the
  local signed URL allowlist.
- **ASSUMPTION-003**: Current ingestion readiness for Bangalore AOI includes Sentinel-2 processed
  dates such as `2026-03-20`.
- **ASSUMPTION-004**: The local product app still owns users, teams, seasons, and field geometry;
  ingestion receives geometry only through server-to-server requests.

## 8. Related Specifications / Further Reading

- [Akasha app agent guide](../../AGENTS.md)
- [Akasha ingestion developer guide](../staging-ingestion-developer-guide.md)
- [Two-VM CI/CD migration plan](./infrastructure-two-vm-cicd-migration-1.md)
- [Self-hosted deployment guide](../../infra/selfhosted/README.md)
- [Developer setup guide](../developer-setup-guide.md)
- [Data ingestion and satellite rules](../data-ingestion-and-satellite-rules.md)
- [Engineering do/don't guardrails](../engineering-dos-donts.md)