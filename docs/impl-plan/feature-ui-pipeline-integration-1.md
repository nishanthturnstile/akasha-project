---
goal: Integrate Akasha Product UI With Standalone Akasha Ingestion Pipeline
version: 1.1
date_created: 2026-07-03
last_updated: 2026-07-03
owner: Akasha Engineering
tags: feature, integration, ui, bff, ingestion, sentinel-2, titiler, pgstac, minio, private-network
---

# Introduction

This implementation plan integrates the Akasha product application in `akasha-em-git` with the standalone ingestion/catalog/processing platform in `../akasha-ingestion` before ResourceSat Phase 3 work. The browser stays on the product app domain; the product FastAPI BFF remains the auth/team/contract adapter; ingestion is called only server-to-server over private networking with an ingestion API key.

First supported source: Sentinel-2 L2A from `../akasha-ingestion` (`sentinel-2-l2a`, provider route `earthsearch:sentinel-2-l2a`). ResourceSat remains on the current product-app native path until standalone ingestion supports ResourceSat. Bangalore 60 km must be preloaded by scheduled ingestion refresh jobs; field-draw requests must query precomputed outputs, not trigger full ingestion.

```text
Browser -> akasha-em-git web/app domain -> akasha-em-git BFF
        -> private HTTP + X-API-Key -> akasha-ingestion API
        -> private TiTiler-PgSTAC / pgSTAC / Postgres / MinIO
```

## 1. Requirements & Constraints

- **REQ-001**: Frontend calls only the `akasha-em-git` app domain. Browser must never call ingestion, MinIO, pgSTAC, or TiTiler directly.
- **REQ-002**: App BFF proxies/adapts ingestion analytics server-to-server with `X-API-Key`; `INGESTION_API_KEY` never reaches browser bundles, payloads, logs, or errors.
- **REQ-003**: Initial pipeline route is Sentinel-2 NDVI only: app `sourceId=sentinel-2-l2a`, ingestion provider route `earthsearch:sentinel-2-l2a`.
- **REQ-004**: Preserve current frontend field analytics UX and endpoint `POST /api/fields/{plot_id}/indices/statistics`.
- **REQ-005**: App BFF adapts ingestion envelope `{"success": bool, "data": T, "error": ...}` to app standard `{ "error": { "code", "message", "details" } }`.
- **REQ-006**: MVP geometry support: app storage/import and adapter validate `Polygon` and `MultiPolygon` in `EPSG:4326`; drawing remains `Polygon` only unless fixing a serialization bug.
- **REQ-007**: Pipeline stats require precomputed Bangalore 60 km outputs. No synchronous full-pipeline work from user draw/stat requests.
- **REQ-008**: Readiness/freshness and source/date catalog bridging must be complete before frontend stats flag enablement.
- **REQ-009**: Uncovered field/date/index requests return clear unavailable/stale reasons.
- **REQ-010**: Phase 1 tile bridge is a hard blocker for UI tile work because ingestion currently returns `_TRANSPARENT_PNG`.
- **REQ-011**: Browser-visible stats/tile URLs are app-domain only. No ingestion hostname, MinIO/S3 URL, pgSTAC URL, TiTiler URL, `sig`, `kid`, `exp`, or API key may leak.
- **REQ-012**: Production keeps ingestion private; only the app VM can reach ingestion Caddy/API.
- **REQ-013**: Support local two-stack development and separate app/ingestion VM production deployment.
- **REQ-014**: App cookie-session auth, team context, and field ownership checks remain authoritative before any ingestion call.
- **REQ-015**: Preserve legacy ResourceSat/Bhoonidhi/native behavior until ResourceSat ingestion parity exists.
- **REQ-016**: Add tests for `AVAILABLE`, `UNAVAILABLE`, timeout, API-key failure, malformed envelope, signed stats/tile proxy, readiness gating, browser leak checks, and shared/golden contract fixtures.
- **REQ-017**: Keep top-level app response compatibility: `provider: "native"`, `scope: "field"`. Add optional pipeline fields under `metadata.pipeline`; do not widen top-level provider/scope in this MVP.
- **REQ-018**: Pipeline `tileUrl` is an additive XYZ layer option. It does not replace the current clipped overlay endpoint or point endpoint unless parity is implemented and tested.
- **REQ-019**: Service-to-service auth is separate from signed result access: app BFF -> ingestion API uses `X-API-Key`; ingestion `statsUrl`/`tileUrl` remain signed URLs hidden behind app-domain proxies.
- **REQ-020**: Ingestion currently hardcodes/selects `sentinel-2-l2a`; app `INGESTION_FIELD_INDEX_SOURCE_ID` is only a routing gate until ingestion adds source selection.
- **SEC-001**: App proxy records are auth/team/field-bound, expire no later than upstream signed URLs, and work across app workers without process-local state.
- **CON-001**: Do not merge/collapse the two repos or runtime models.
- **CON-002**: Scheduled preload must not rely on one-item local smoke caps.
- **CON-003**: `NDVI` is first; other ingestion indices are enabled only after contract verification.
- **GUD-001**: Keep TanStack Query and app BFF adaptation; avoid frontend rewrites.
- **GUD-002**: Add structured logs/metrics without secrets or signed URLs.
- **PAT-001**: Follow `apps/api/app/routers/analytics_router.py`, `apps/frontend/src/lib/api.ts`, and ingestion schemas in `../akasha-ingestion/src/akasha/schemas.py`.

## 2. Implementation Steps

### Implementation Phase 1 — Ingestion tile bridge prerequisite

- GOAL-001: Replace the signed tile placeholder with real TiTiler-PgSTAC PNG proxying while keeping TiTiler private.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | In `../akasha-ingestion/src/akasha/api/app.py`, replace `_TRANSPARENT_PNG` in `tile(layer_id, z, x, y, op, exp, kid, sig)` after signature verification. Look up `layer_id`; missing layer returns 404. | No | |
| TASK-002 | Ensure `TileLayerRecord`/repository can resolve `raster_output_id`; add `get_with_raster(layer_id: str)` if needed. | No | |
| TASK-003 | Ensure raster lookup provides `object_path`, `index_name`, pgSTAC collection, asset key, and scene/item id. | No | |
| TASK-004 | Add ingestion settings `titiler_internal_url="http://titiler:8000"` and `titiler_timeout_seconds=30.0`; wire Docker env. | No | |
| TASK-005 | Call internal TiTiler-PgSTAC `/collections/{collection_id}/items/{item_id}/tiles/WebMercatorQuad/{z}/{x}/{y}.png` with derived assets/rescale/colormap and return bytes/content type. | No | |
| TASK-006 | Sanitize TiTiler 404/422/500 errors; never expose internal URLs. Verify signature/expiry before layer lookup or any TiTiler call. | No | |
| TASK-007 | Add ingestion tests for invalid signature, unknown layer, sanitized TiTiler error, and mocked PNG proxy. | No | |
| TASK-008 | Run `cd ../akasha-ingestion && ruff check . && python -m pytest -q`. | No | |
| TASK-009 | Live smoke: `POST /api/v1/analytics/field-index`, fetch returned `tileUrl`, verify non-placeholder PNG > 1 KB. | No | |

### Implementation Phase 2 — Ingestion readiness endpoint and preload

- GOAL-002: Make ingestion expose a precise readiness/freshness contract for preloaded Sentinel-2 outputs. App-domain source/date bridging happens only after the app ingestion client exists in Phase 3.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | Define Bangalore 60 km Sentinel-2 preload policy in `../akasha-ingestion`; search all required items and avoid smoke caps like `AKASHA_BACKFILL_SEARCH_ITEM_CAP=1`. | No | |
| TASK-011 | Configure scheduled refresh, weekly by default until cost/runtime is measured. | No | |
| TASK-012 | Add ingestion readiness endpoint `GET /api/v1/analytics/readiness?sourceId=sentinel-2-l2a&aoiId=bangalore_60km_geodesic_aoi` returning the Appendix A readiness envelope. | No | |
| TASK-013 | Add readiness tests for fresh, stale, missing jobs, missing index coverage, and source mismatch. | No | |
| TASK-014 | Add readiness shared/golden fixtures for fresh, stale, unavailable, malformed, and auth-failed responses. | No | |
| TASK-015 | Document readiness stale calculation in ingestion: compare `latestProcessedSceneDate`/last successful job time against configured freshness threshold and include deterministic reason codes. | No | |
| TASK-016 | Ensure readiness reports `availableDates` and `indexCoverage.NDVI` from precomputed outputs only; it must not trigger search/mirror/process work. | No | |
| TASK-017 | Run readiness/preload smoke and confirm stale or missing preload returns a clear non-AVAILABLE readiness state. | No | |
| TASK-018 | Run local multi-item preload smoke and verify an official Bangalore test field returns `AVAILABLE`. | No | |

### Implementation Phase 3 — App BFF ingestion client and configuration

- GOAL-003: Add a typed, tested server-to-server ingestion client without exposing ingestion details.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Add app settings `INGESTION_API_URL`, `INGESTION_API_KEY`, `INGESTION_REQUEST_TIMEOUT_SECONDS=30`, `INGESTION_FIELD_INDEX_ENABLED=false`, `INGESTION_FIELD_INDEX_SOURCE_ID=sentinel-2-l2a`, `INGESTION_READINESS_ENABLED=false`, `INGESTION_FRESHNESS_MAX_AGE_HOURS`, and `INGESTION_AOI_ID`. | No | |
| TASK-020 | Wire settings in `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml`, and `infra/selfhosted/env.example`; no real key in source. | No | |
| TASK-021 | Create `apps/api/app/ingestion_client.py` with typed models for field-index request, available/unavailable responses, Appendix A readiness response, API envelope, and client errors; preserve camelCase aliases. | No | |
| TASK-022 | Implement `IngestionClient.field_index(...)` and `IngestionClient.readiness(...)` with `httpx.Client`, `X-API-Key`, timeout, and explicit handling for timeout, connection failure, non-2xx, invalid JSON, `success=false`, and missing `data`. | No | |
| TASK-023 | Redact API key, signed URL query strings, and ingestion hostnames from errors, logs, and metrics labels. | No | |
| TASK-024 | Normalize non-2xx/error envelopes to Appendix A by HTTP status. Accept ingestion numeric-string `error.code` values as advisory, and defensively sanitize any raw FastAPI `{"detail": ...}` body from unhandled failures. | No | |
| TASK-025 | Add client tests for field-index available/unavailable, readiness fresh/stale/unavailable, 401/403, 429, 500, timeout, invalid envelope, and URL/key not configured. | No | |
| TASK-026 | Run `cd apps/api && python -m pytest tests -q`. | No | |

### Implementation Phase 4 — App BFF field statistics adapter

- GOAL-004: Preserve the current field-statistics endpoint while allowing Sentinel-2 NDVI to be served by ingestion.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-027 | Bridge readiness into app product/source/date endpoints before stats enablement: show/enable `sentinel-2-l2a` dates only when readiness is fresh; stale/missing readiness returns app-domain freshness metadata and no ingestion URLs. | No | |
| TASK-028 | In `apps/api/app/routers/analytics_router.py`, keep `POST /api/fields/{plot_id}/indices/statistics` unchanged as the frontend entry point. Add a feature-gated branch before legacy stats: if flag enabled, `sourceId=sentinel-2-l2a`, and `indexType=NDVI`, require fresh readiness and call ingestion. If readiness is stale/missing, return `PIPELINE_STALE` or `PIPELINE_OUTPUT_UNAVAILABLE`; do not silently fall back to native Sentinel-2. Native fallback is allowed only when the pipeline flag is disabled or the request is intentionally non-Sentinel/non-NDVI. | No | |
| TASK-029 | Re-check `_get_field_or_404`, current team, and field ownership before ingestion. Send geometry, `crs="EPSG:4326"`, `index="NDVI"`, requested date, `fallbackPolicy="nearest_valid_scene"`, `maxCloudPercentage`, and `fieldId`; do not send source until ingestion supports it. | No | |
| TASK-030 | Validate both `Polygon` and `MultiPolygon` from stored/imported fields; keep frontend draw controller Polygon-only except bug fixes. | No | |
| TASK-031 | Create pure adapter `apps/api/app/ingestion_field_index_adapter.py` implementing Appendix B mapping. Preserve `provider:"native"`, `scope:"field"`, camelCase JSON, and optional `metadata.pipeline`. | No | |
| TASK-032 | Map ingestion `UNAVAILABLE` to app HTTP 404 code `PIPELINE_OUTPUT_UNAVAILABLE` by default; only return success-with-null-statistics if UI support is explicitly implemented and tested. | No | |
| TASK-033 | Preserve native ResourceSat, non-Sentinel stats, field exports, reports, risk, trend, clipped overlay, point, and rollback behavior. | No | |
| TASK-034 | Add adapter tests for available, unavailable, missing optional fields, derived pixel counts, URL rewrite placeholders, provider/scope preservation, and MultiPolygon passthrough. | No | |
| TASK-035 | Add route tests proving Sentinel-2 NDVI calls ingestion only when flag/readiness are enabled, stale/missing readiness returns pipeline errors, flag-disabled requests use native fallback, and non-NDVI/non-Sentinel cases remain native. | No | |
| TASK-036 | Run `cd apps/api && python -m pytest -q`. | No | |

### Implementation Phase 5 — App-domain stats and tile proxy endpoints

- GOAL-005: Rewrite signed ingestion URLs to app-domain URLs and proxy browser stats/tile requests without topology leakage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-037 | Add `apps/api/app/routers/pipeline_proxy.py` with opaque proxy routes `GET /api/pipeline/field-index/stats?proxyId=...` and `GET /api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=...`; register in `main.py`. | Yes | 2026-07-03 |
| TASK-038 | Use DB-backed proxy records, not stateless browser HMAC. Add SQLAlchemy model/Alembic table `akasha.pipeline_proxy_records`: id/proxy_id, operation, ingestion path/query/signature stored server-side, user_id, team_id, field_id, source_id, index_type, query_id/layer_id, expires_at, created_at, last_accessed_at. | Yes | 2026-07-03 |
| TASK-039 | Browser receives only opaque `proxyId` plus XYZ coordinates for tiles. No ingestion `queryId`/`layerId`, host, `sig`, `kid`, `exp`, `op`, MinIO, S3, pgSTAC, or TiTiler values in browser payloads. `queryId`/`layerId` may be stored only in DB proxy records and server-side logs/metrics after redaction review; do not return them in browser-visible JSON. | Yes | 2026-07-03 |
| TASK-040 | Store records in Postgres for multi-worker behavior; reject expired records with `PIPELINE_PROXY_EXPIRED`; add TTL cleanup. For tile records, add a re-mint path or enforce an upstream signed TTL long enough for interactive map sessions before enabling `INGESTION_PIPELINE_TILE_LAYER_ENABLED`. | Yes | 2026-07-03 |
| TASK-041 | Enforce `get_current_user` and current team, validate record user/team/field binding, and re-check field access where practical before proxying. | Yes | 2026-07-03 |
| TASK-042 | Proxy via `IngestionClient` or shared internal method; preserve PNG/JSON content type; do not log/return ingestion URLs. | Yes | 2026-07-03 |
| TASK-043 | Rewrite ingestion `statsUrl`/`tileUrl` to opaque app proxy URLs under optional `metadata.pipeline.statsUrl`/`tileUrl`; do not include ingestion query/layer identifiers in URL paths. | Yes | 2026-07-03 |
| TASK-044 | Add tests for no URL/secret leakage, expired/invalid proxy IDs, unauthorized user/team/field mismatch, upstream failures, and DB multi-worker lookup. | Yes | 2026-07-03 |
| TASK-045 | Run `cd apps/api && python -m pytest -q`. | Yes | 2026-07-03 |

### Implementation Phase 6 — Frontend integration with minimal changes

- GOAL-006: Keep TanStack Query hooks and field analytics UI working while displaying optional pipeline provenance.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-046 | Review `getFieldStatistics`, `getFieldTrend`, `getFieldIndexOverlayImage`, and `getFieldIndexPoint`; keep all frontend calls app-domain only. | No | |
| TASK-047 | Extend `apps/frontend/src/types/api.ts` with optional `metadata.pipeline`, `tileUrl`, `statsUrl`, freshness, quality, and providerRoute only if read by UI; keep top-level `provider:'native'`, `scope:'field'`. | No | |
| TASK-048 | Update `IndexPanel.tsx` to display optional Sentinel-2 pipeline provenance: provider route, selected scene date, freshness/staleness, quality reason/warnings. | No | |
| TASK-049 | Do not replace clipped overlay/point behavior. If XYZ is enabled, add a separate MapLibre source/layer from app-domain `tileUrl` and reject non-`/api/`/same-origin URLs. | No | |
| TASK-050 | Defer clipped overlay and point parity unless explicitly added: current `/overlay/{index}.png` and point routes stay native. If parity is needed, add backend clipping/corner-header/point-sampling tasks first. | No | |
| TASK-051 | Keep `FieldDrawController.tsx` unchanged except serialization bug fixes. Imported/stored `MultiPolygon` support is adapter/backend validation work. | No | |
| TASK-052 | Add frontend tests for pipeline stats rendering, optional metadata, provider compatibility, app-domain URL validation, and no ingestion hostnames in UI state. | No | |
| TASK-053 | Run `cd apps/frontend && yarn lint && yarn test && yarn build`. | No | |

### Implementation Phase 7 — Separate-VM private networking and deployment wiring

- GOAL-007: Validate separate app VM and ingestion VM connected privately.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-054 | Choose private connectivity: same Azure VNet/subnet, VNet peering, WireGuard, or Tailscale; record in self-hosted runbook. | No | |
| TASK-055 | Restrict ingestion API firewall/NSG to app VM private IP. Do not expose ingestion Postgres, MinIO, Redis, or TiTiler. | No | |
| TASK-056 | Configure app VM `INGESTION_API_URL` to private IP/DNS and `INGESTION_API_KEY` as a deployment secret. | No | |
| TASK-057 | Confirm TLS strategy: private DNS + TLS preferred; minimum private network + API key + IP allowlist. | No | |
| TASK-058 | Add deployment smoke from app VM: ingestion `/health`, authenticated `/api/v1/sources`, readiness, and known-field field-index. | No | |
| TASK-059 | Confirm from browser/client machine that ingestion private URL is not reachable directly. | No | |

### Implementation Phase 8 — Rollout, observability, and end-to-end acceptance

- GOAL-008: Prove UI flow, real tiles, safe rollback, and no browser leakage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-060 | Add flags: `INGESTION_FIELD_INDEX_ENABLED`, `INGESTION_READINESS_ENABLED`, optional `INGESTION_PIPELINE_TILE_LAYER_ENABLED`; default off until smoke passes. | No | |
| TASK-061 | Add correlation IDs and pass redacted `X-Request-ID` to ingestion. Log request id, field/team/source/index, readiness, upstream status, duration, retry count, and app error code only. | No | |
| TASK-062 | Add metrics/counters for ingestion calls, latency, timeout, circuit state, unavailable reason, stale readiness, proxy hits/rejects, tile status, and tile size buckets. | No | |
| TASK-063 | Implement bounded retries/backoff for timeouts/502/503/504. Retry 429 only when `Retry-After` is present and within a small bounded delay; otherwise return `PIPELINE_RATE_LIMITED`. Never retry validation/auth/contract errors. Add short circuit breaker returning `PIPELINE_UPSTREAM_UNAVAILABLE`. | No | |
| TASK-064 | Define rollback: disable stats flag for legacy native behavior; disable tile flag if only XYZ tiles fail. No DB rollback required for proxy records. | No | |
| TASK-065 | Local two-stack smoke: preloaded ingestion + local app; verify app BFF statistics match direct ingestion for same field/date/index. | No | |
| TASK-066 | Browser smoke: trigger NDVI stats; browser calls only app-domain endpoints; optional tile URL returns real PNG, not placeholder. | No | |
| TASK-067 | Browser leak test: no ingestion hostnames, MinIO/S3/pgSTAC/TiTiler URLs, API key, `sig`, `kid`, or `exp` in network payloads, logs, or local storage. | No | |
| TASK-068 | Separate-VM smoke: app VM reaches private ingestion health/sources/readiness/field-index; browser cannot reach ingestion directly. | No | |
| TASK-069 | Regression smoke ResourceSat/native stats, trend, overlay, point, field exports, reports, and risk with flags disabled and with non-Sentinel sources. | No | |
| TASK-070 | Run final app checks: `cd apps/api && python -m pytest -q`; `cd apps/frontend && yarn lint && yarn test && yarn build`. | No | |
| TASK-071 | Run final ingestion checks: `cd ../akasha-ingestion && ruff check . && python -m pytest -q`; live field-index smoke. | No | |

## 3. Alternatives

- **ALT-001**: Frontend calls ingestion directly. Rejected: exposes topology, requires CORS/public ingress, bypasses app auth, risks secret leakage.
- **ALT-002**: App BFF directly reads ingestion Postgres/pgSTAC/MinIO. Rejected: couples app to ingestion internals and duplicates query logic.
- **ALT-003**: Keep only legacy product-app raster path. Rejected: standalone ingestion owns preloading, mirroring, derived COGs, pgSTAC, and future source evolution.
- **ALT-004**: Synchronously trigger full ingestion from field draw. Rejected: long-running pipeline work must be precomputed.
- **ALT-005**: Share filesystem inbox between VMs. Rejected: less reliable than private HTTP API.
- **ALT-006**: Expose TiTiler directly to browser. Rejected: violates private-service model.
- **ALT-007**: Widen top-level app `provider` to `ingestion`. Deferred: current backend/frontend hard-code `native`; MVP uses optional `metadata.pipeline`.
- **ALT-008**: Stateless HMAC proxy token containing signed ingestion URL. Rejected: risks carrying sensitive URL/signature material in browser; DB records are safer and multi-worker friendly.

## 4. Dependencies

- **DEP-001**: `apps/api/app` FastAPI BFF and current auth/team/field ownership dependencies.
- **DEP-002**: `apps/frontend` React/Vite/TanStack Query frontend.
- **DEP-003**: `../akasha-ingestion/src/akasha/api/app.py`, schemas, analytics service, private TiTiler-PgSTAC, pgSTAC/Postgres, and MinIO.
- **DEP-004**: App deployment secrets for `INGESTION_API_URL` and `INGESTION_API_KEY`.
- **DEP-005**: Private networking between app VM and ingestion VM.
- **DEP-006**: Scheduled Bangalore 60 km Sentinel-2 preload/backfill.
- **DEP-007**: App Postgres/Alembic for DB-backed proxy records.
- **DEP-008**: Shared/golden fixtures generated from ingestion OpenAPI or checked into both repos.

## 5. Files

- **FILE-001**: `apps/api/app/config.py` — ingestion URL/key/timeout/feature/readiness settings.
- **FILE-002**: `apps/api/app/ingestion_client.py` — typed server-to-server ingestion client.
- **FILE-003**: `apps/api/app/ingestion_field_index_adapter.py` — pure adapter to app `FieldStatisticsResponse`.
- **FILE-004**: `apps/api/app/routers/analytics_router.py` — feature-gated Sentinel-2 NDVI branch.
- **FILE-005**: `apps/api/app/routers/pipeline_proxy.py` — app-domain stats/tile proxy routes.
- **FILE-006**: `apps/api/app/models.py`, `apps/api/alembic/` — proxy record model/migration.
- **FILE-007**: `apps/api/app/main.py` — router registration.
- **FILE-008**: `apps/api/app/schemas/analytics.py` — optional metadata only; keep provider/scope literals.
- **FILE-009**: `apps/api/tests/` — client, adapter, proxy, readiness, flag, contract tests.
- **FILE-010**: `apps/frontend/src/lib/api.ts`, `queries.ts`, `types/api.ts`, `IndexPanel.tsx`, `FieldDrawController.tsx` — minimal optional-field/UI changes.
- **FILE-011**: `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml`, `infra/selfhosted/env.example` — deployment env wiring.
- **FILE-012**: `../akasha-ingestion/src/akasha/api/app.py`, `config.py`, catalog repositories, `deploy/docker-compose.yml`, tests — tile bridge, readiness, contracts.
- **FILE-013**: `docs/impl-plan/feature-ui-pipeline-integration-1.md` — this plan.

## 6. Testing

- **TEST-001**: Ingestion signed tile tests: valid PNG proxy, invalid signature 401, missing layer 404, sanitized TiTiler errors.
- **TEST-002**: Ingestion readiness tests: fresh, stale, missing preload, source mismatch.
- **TEST-003**: Ingestion live smoke: direct field-index `AVAILABLE`; returned tile URL real PNG > 1 KB.
- **TEST-004**: Shared/golden contract tests for Appendix A field-index request, available response, unavailable response, readiness responses, error envelope, and adapted app response.
- **TEST-005**: App client tests: available, unavailable, readiness, 401/403, 429, 500, timeout, invalid envelope, missing config.
- **TEST-006**: App adapter tests: Appendix B mapping, derived pixel counts, provider/scope preservation, URL rewriting, unavailable mapping, MultiPolygon passthrough.
- **TEST-007**: App route tests: flag/readiness behavior, pipeline errors for stale Sentinel-2 readiness, and native fallback only for flag-disabled/non-NDVI/non-Sentinel paths.
- **TEST-008**: App proxy tests: no URL/secret leakage, auth/team/field binding, expiry, invalid proxy id, multi-worker DB lookup.
- **TEST-009**: Frontend tests: optional pipeline metadata renders; top-level provider remains native; non-app-domain tile URLs are rejected.
- **TEST-010**: End-to-end local and separate-VM smokes plus browser leak tests.
- **TEST-011**: Regression tests for ResourceSat/native stats, trend, overlay, point, exports, reports, and risk.
- **TEST-012**: Final commands: `cd apps/api && python -m pytest -q`; `cd apps/frontend && yarn lint && yarn test && yarn build`; `cd ../akasha-ingestion && ruff check . && python -m pytest -q`.

## 7. Risks & Assumptions

- **RISK-001**: Tile layer may lack pgSTAC metadata; fetch `RasterOutputRecord` by `raster_output_id`.
- **RISK-002**: Multi-tile/mosaic gaps may make some Bangalore fields unavailable; preload all intersecting tiles and return clear unavailable until mosaicking exists.
- **RISK-003**: Current ingestion response lacks explicit total/nodata pixel counts; Appendix B defines provisional derivation and metadata basis, or ingestion can add exact counts before flag enablement.
- **RISK-004**: Separate private networking may lag; temporary TLS + IP allowlist + API key is acceptable only for validation.
- **RISK-005**: Signed URL TTLs can expire; proxy record expiry must not exceed upstream expiry.
- **RISK-006**: Ingestion outage impacts Sentinel-2 stats; mitigate with readiness gate, circuit breaker, unavailable messages, and native fallback where applicable.
- **ASSUMPTION-001**: MVP users draw fields inside Bangalore 60 km AOI.
- **ASSUMPTION-002**: Sentinel-2 outputs are preloaded for UI date windows.
- **ASSUMPTION-003**: Product app remains the only browser-facing app service.
- **ASSUMPTION-004**: Existing app auth/team model remains authoritative; ingestion receives no end-user identity.

## 8. Related Specifications / Further Reading

- `AGENTS.md`
- `docs/platform-plan.md`
- `docs/architecture-tech-stack.md`
- `docs/data-ingestion-and-satellite-rules.md`
- `docs/engineering-dos-donts.md`
- `docs/impl-plan/process-staging-ingestion-workflow-1.md`
- `../akasha-ingestion/AGENTS.md`
- `../akasha-ingestion/docs/implementation-roadmap.md`
- `../akasha-ingestion/docs/phase-2-sentinel-2-vertical-slice-implementation-plan.md`
- `../akasha-ingestion/src/akasha/schemas.py`
- `../akasha-ingestion/src/akasha/api/app.py`

## Appendix A — Pinned Cross-App Contract

Pinned field-index/readiness JSON in this appendix is camelCase. Existing ingestion source/job endpoints may remain snake_case; the app source/date bridge must adapt them into app-domain camelCase responses. Both repos must validate these examples with contract/golden tests, preferably generated from ingestion OpenAPI plus shared fixtures.

### A.1 App BFF -> ingestion field-index request

`POST {INGESTION_API_URL}/api/v1/analytics/field-index`

```http
X-API-Key: <server-side-secret>
Content-Type: application/json
X-Request-ID: <app-correlation-id>
```

```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [77.5901, 12.9716],
      [77.5911, 12.9716],
      [77.5911, 12.9726],
      [77.5901, 12.9726],
      [77.5901, 12.9716]
    ]]
  },
  "crs": "EPSG:4326",
  "index": "NDVI",
  "date": "2026-01-15",
  "fallbackPolicy": "nearest_valid_scene",
  "maxCloudPercentage": 20,
  "fieldId": "field_123"
}
```

- `geometry.type` may be `Polygon` or `MultiPolygon`; coordinates are lon/lat.
- `sourceId` is intentionally absent for MVP because ingestion currently selects `sentinel-2-l2a`; the app source setting only gates routing.

### A.2 Ingestion `AVAILABLE` response envelope

HTTP `200`:

```json
{
  "success": true,
  "data": {
    "status": "AVAILABLE",
    "queryId": "q_01JZ8H7P5ZNDVI",
    "fieldId": "field_123",
    "index": "NDVI",
    "requestedDate": "2026-01-15",
    "selectedSceneDate": "2026-01-13",
    "source": "sentinel-2-l2a",
    "providerRoute": "earthsearch:sentinel-2-l2a",
    "resolution": { "nativeMeters": 10, "processingMeters": 10, "displayMeters": 10 },
    "layerId": "layer_01JZ8H7P5Z",
    "tileUrl": "https://ingestion.internal/tiles/layer_01JZ8H7P5Z/{z}/{x}/{y}.png?op=tile&exp=1783071196&kid=default&sig=REDACTED",
    "statsUrl": "https://ingestion.internal/api/v1/analytics/field-index/q_01JZ8H7P5ZNDVI?op=stats&exp=1783071196&kid=default&sig=REDACTED",
    "selection": { "windowDays": 7, "rule": "quality_first", "validPixelCount": 3456 },
    "statistics": {
      "min": 0.12,
      "max": 0.86,
      "mean": 0.54,
      "median": 0.55,
      "stdDev": 0.08,
      "usablePixelPercentage": 92.5,
      "cloudPercentage": 4.2
    },
    "classStatistics": [
      { "class": "healthy", "valueRange": [0.4, 1.0], "areaSqM": 28100.0, "areaPercentage": 81.3 }
    ],
    "visualization": {
      "displayProfile": "ndvi-v1",
      "thresholdProfile": "ndvi-thresholds-v1",
      "legend": [{ "label": "healthy", "color": "#2f7d32", "min": 0.4, "max": 1.0 }]
    },
    "versions": { "analytics": "phase2-sentinel2-v1", "processor": "sentinel2-index-v1" },
    "quality": { "status": "GOOD", "reason": "Field cloud cover within threshold", "warnings": [] }
  },
  "error": null
}
```

### A.3 Ingestion `UNAVAILABLE` response envelope

HTTP `200`:

```json
{
  "success": true,
  "data": {
    "status": "UNAVAILABLE",
    "index": "NDVI",
    "requestedDate": "2026-01-15",
    "reason": "No optical scene with field usable-pixels >= 80% within +/- 7 days",
    "searchedSources": ["sentinel-2-l2a"]
  },
  "error": null
}
```

### A.4 Ingestion error envelope / non-2xx

Current ingestion wraps handled HTTP errors in the same envelope but uses numeric-string `error.code` values derived from the HTTP status. The app client maps primarily by HTTP status and treats ingestion `error.code` as advisory.

```json
{
  "success": false,
  "data": null,
  "error": { "code": "401", "message": "Invalid API key" }
}
```

| HTTP | Ingestion code | App BFF mapped code | Retry? |
|------|----------------|---------------------|--------|
| 400/422 | `"400"` / `"422"` | `PIPELINE_BAD_REQUEST` | No |
| 401/403 | `"401"` / `"403"` | `PIPELINE_AUTH_FAILED` | No |
| 404 | `"404"` | `PIPELINE_OUTPUT_UNAVAILABLE` | No |
| 429 | `"429"` | `PIPELINE_RATE_LIMITED` | Conditional: only with bounded `Retry-After` |
| 500 | `"500"` or raw `detail` | `PIPELINE_UPSTREAM_ERROR` | Maybe |
| 502/503/504 | `"502"` / `"503"` / `"504"` | `PIPELINE_UPSTREAM_UNAVAILABLE` | Yes |

If ingestion emits raw FastAPI `{"detail": "..."}` for an unhandled failure, the app client must sanitize/map it defensively by HTTP status without exposing internals.

### A.5 Ingestion readiness response envelope

`GET {INGESTION_API_URL}/api/v1/analytics/readiness?sourceId=sentinel-2-l2a&aoiId=bangalore_60km_geodesic_aoi`

```http
X-API-Key: <server-side-secret>
X-Request-ID: <app-correlation-id>
```

Fresh HTTP `200`:

```json
{
  "success": true,
  "data": {
    "status": "AVAILABLE",
    "sourceId": "sentinel-2-l2a",
    "aoiId": "bangalore_60km_geodesic_aoi",
    "latestProcessedSceneDate": "2026-01-13",
    "latestSuccessfulJobCompletedAt": "2026-01-14T02:30:00Z",
    "staleAfter": "2026-01-21T02:30:00Z",
    "availableDates": ["2026-01-13", "2026-01-06"],
    "indexCoverage": {
      "NDVI": { "available": true, "dateCount": 2, "coveragePercent": 100.0 },
      "NDMI": { "available": false, "dateCount": 0, "coveragePercent": 0.0 }
    },
    "lastSuccessfulJob": {
      "jobId": "job_01JZ8H",
      "status": "SUCCEEDED",
      "completedAt": "2026-01-14T02:30:00Z"
    },
    "unavailableReasons": []
  },
  "error": null
}
```

Stale HTTP `200`:

```json
{
  "success": true,
  "data": {
    "status": "STALE",
    "sourceId": "sentinel-2-l2a",
    "aoiId": "bangalore_60km_geodesic_aoi",
    "latestProcessedSceneDate": "2026-01-01",
    "latestSuccessfulJobCompletedAt": "2026-01-02T02:30:00Z",
    "staleAfter": "2026-01-09T02:30:00Z",
    "availableDates": ["2026-01-01"],
    "indexCoverage": {
      "NDVI": { "available": true, "dateCount": 1, "coveragePercent": 100.0 }
    },
    "lastSuccessfulJob": {
      "jobId": "job_01JYOLD",
      "status": "SUCCEEDED",
      "completedAt": "2026-01-02T02:30:00Z"
    },
    "unavailableReasons": [
      { "code": "PRELOAD_STALE", "message": "Latest successful preload is older than the freshness threshold." }
    ]
  },
  "error": null
}
```

Unavailable HTTP `200`:

```json
{
  "success": true,
  "data": {
    "status": "UNAVAILABLE",
    "sourceId": "sentinel-2-l2a",
    "aoiId": "bangalore_60km_geodesic_aoi",
    "latestProcessedSceneDate": null,
    "latestSuccessfulJobCompletedAt": null,
    "staleAfter": null,
    "availableDates": [],
    "indexCoverage": {
      "NDVI": { "available": false, "dateCount": 0, "coveragePercent": 0.0 }
    },
    "lastSuccessfulJob": null,
    "unavailableReasons": [
      { "code": "NO_PRELOAD_OUTPUTS", "message": "No precomputed NDVI outputs are registered for this AOI." }
    ]
  },
  "error": null
}
```

Rules:

- `status` enum is `AVAILABLE | STALE | UNAVAILABLE`.
- Dates use `YYYY-MM-DD`; timestamps use UTC ISO 8601 with `Z`.
- `indexCoverage` keys are uppercase index names; MVP requires `NDVI`.
- The app may expose `sentinel-2-l2a` dates and call field-index only when readiness is `AVAILABLE`, `indexCoverage.NDVI.available=true`, and `availableDates` is non-empty.
- `STALE` maps to app `PIPELINE_STALE`; `UNAVAILABLE` maps to app `PIPELINE_OUTPUT_UNAVAILABLE`.
- Readiness is read-only and must not trigger search, mirror, processing, or TiTiler calls.

### A.6 App BFF adapted `FieldStatisticsResponse`

HTTP `200` from `POST /api/fields/{plotId}/indices/statistics`:

```json
{
  "plotId": "field_123",
  "provider": "native",
  "scope": "field",
  "indexType": "NDVI",
  "sourceId": "sentinel-2-l2a",
  "acquisitionDate": "2026-01-15",
  "cloudMask": { "clouds": true, "cloudShadows": true, "cirrus": true },
  "statistics": {
    "min": 0.12,
    "max": 0.86,
    "mean": 0.54,
    "stddev": 0.08,
    "validPixelPercent": 92.5,
    "cloudMaskedPercent": 4.2,
    "coveragePercent": 100.0
  },
  "pixelCounts": {
    "totalPixels": 3736,
    "nodataPixels": 0,
    "coveragePixels": 3736,
    "maskedPixels": 280,
    "validPixels": 3456
  },
  "metadata": {
    "provider": "native",
    "scope": "field",
    "formula": "(NIR-RED)/(NIR+RED)",
    "bands": ["NIR", "RED"],
    "maskMethod": "sentinel2-pipeline-scl",
    "warnings": [],
    "pipeline": {
      "enabled": true,
      "status": "AVAILABLE",
      "source": "sentinel-2-l2a",
      "providerRoute": "earthsearch:sentinel-2-l2a",
      "requestedDate": "2026-01-15",
      "selectedSceneDate": "2026-01-13",
      "selection": { "windowDays": 7, "rule": "quality_first", "validPixelCount": 3456 },
      "resolution": { "nativeMeters": 10, "processingMeters": 10, "displayMeters": 10 },
      "quality": { "status": "GOOD", "reason": "Field cloud cover within threshold", "warnings": [] },
      "versions": { "analytics": "phase2-sentinel2-v1", "processor": "sentinel2-index-v1" },
      "classStatistics": [
        { "class": "healthy", "valueRange": [0.4, 1.0], "areaSqM": 28100.0, "areaPercentage": 81.3 }
      ],
      "tileUrl": "/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_01JZ8H7",
      "statsUrl": "/api/pipeline/field-index/stats?proxyId=px_01JZ8H8",
      "pixelCountsBasis": "derivedFromValidPixelCountAndUsablePixelPercentage",
      "cloudMaskedPercentBasis": "sceneCloudPercentage",
      "coveragePercentBasis": "availableOutputAssumedFullCoverage",
      "cloudMaskOptionsNote": "Request cloudMask flags are echoed for compatibility; Sentinel-2 pipeline MVP applies its precomputed mask and maxCloudPercentage policy."
    }
  },
  "resolvedSourceId": "sentinel-2-l2a",
  "resolutionMeters": 10,
  "enhanced": false,
  "basisDate": "2026-01-13",
  "provenanceNote": "Pipeline Sentinel-2 scene selected by quality_first within +/- 7 days."
}
```

### A.7 App BFF error mapping

Unavailable precomputed output:

```json
{
  "error": {
    "code": "PIPELINE_OUTPUT_UNAVAILABLE",
    "message": "No precomputed Sentinel-2 NDVI output is available for this field and date.",
    "details": {
      "sourceId": "sentinel-2-l2a",
      "indexType": "NDVI",
      "requestedDate": "2026-01-15",
      "reason": "No optical scene with field usable-pixels >= 80% within +/- 7 days",
      "searchedSources": ["sentinel-2-l2a"],
      "retryable": false
    }
  }
}
```

Stale readiness gate:

```json
{
  "error": {
    "code": "PIPELINE_STALE",
    "message": "Sentinel-2 pipeline preload is stale for Bangalore 60 km.",
    "details": {
      "sourceId": "sentinel-2-l2a",
      "aoiId": "bangalore_60km_geodesic_aoi",
      "latestProcessedSceneDate": "2026-01-01",
      "staleAfter": "2026-01-08T00:00:00Z",
      "retryable": true
    }
  }
}
```

Upstream timeout/auth errors use A.4 app codes and must never include ingestion hostnames, signed URLs, or API keys.

## Appendix B — Statistics and Metadata Mapping

| App `FieldStatisticsResponse` field | Source from ingestion | Exact rule |
|--------------------------------------|-----------------------|------------|
| `plotId` | route `{plot_id}` / app field id | Preserve app id, not ingestion `fieldId` if they differ. |
| `provider` | compatibility decision | Always `"native"` for MVP. |
| `scope` | compatibility decision | Always `"field"` for statistics. |
| `indexType` | `data.index` | Uppercase; MVP only `NDVI`. |
| `sourceId` | `data.source` | Expect `sentinel-2-l2a`; reject mismatch with `PIPELINE_CONTRACT_MISMATCH`. |
| `acquisitionDate` | app request date / `data.requestedDate` | Use requested date so UI date labels remain stable. |
| `basisDate` | `data.selectedSceneDate` | Scene actually used by ingestion. |
| `statistics.min/max/mean` | `data.statistics.min/max/mean` | Copy as nullable numbers. |
| `statistics.stddev` | `data.statistics.stdDev` | Rename to app `stddev`. |
| `statistics.validPixelPercent` | `data.statistics.usablePixelPercentage` | Copy, clamp to `[0, 100]`. |
| `statistics.cloudMaskedPercent` | `data.classStatistics` or `data.statistics.cloudPercentage` | Prefer sum of cloud/shadow/cirrus class percentages if ingestion exposes them; otherwise use `cloudPercentage` and set `cloudMaskedPercentBasis`. |
| `statistics.coveragePercent` | ingestion explicit coverage if added, else derived | Copy explicit coverage; otherwise `100.0` for available outputs and set `coveragePercentBasis=availableOutputAssumedFullCoverage`. |
| `pixelCounts.validPixels` | `data.selection.validPixelCount` | Copy integer. |
| `pixelCounts.coveragePixels` | derived | Copy explicit ingestion count if added; else `round(validPixels * 100 / usablePixelPercentage)` when usable > 0, else `0`. |
| `pixelCounts.maskedPixels` | derived | `max(coveragePixels - validPixels, 0)`. |
| `pixelCounts.totalPixels` | derived | Copy explicit ingestion total if added; else `coveragePixels`. |
| `pixelCounts.nodataPixels` | derived | Copy explicit ingestion nodata if added; else `max(totalPixels - coveragePixels, 0)`, normally `0`. |
| `cloudMask` | app request | Echo request mask options for compatibility. Because ingestion receives only `maxCloudPercentage` in MVP, add `metadata.pipeline.cloudMaskOptionsNote` warning that per-class toggles were not applied by ingestion. |
| `resolvedSourceId` | `data.source` | Copy. |
| `resolutionMeters` | `data.resolution.processingMeters` | Copy. |
| `enhanced` | compatibility | `false` for Sentinel-2 pipeline MVP; keep native LISS-4 meaning unchanged. |
| `provenanceNote` | `data.selection`, `data.providerRoute`, `data.quality.reason` | Human-readable pipeline/provider/scene/selection sentence. |
| `metadata.maskMethod` | pipeline metadata | Set to a Sentinel-2 pipeline mask label such as `sentinel2-pipeline-scl`; do not fall back to the native ResourceSat mask method. |
| Internal query/layer IDs | `data.queryId`, `data.layerId` | Store only in DB-backed proxy records; do not return to browser-visible JSON. |
| `metadata.pipeline.tileUrl/statsUrl` | ingestion URLs via proxy records | Rewrite to opaque app-domain proxy URLs only. |
| `metadata.pipeline.quality/versions/selection/resolution/classStatistics` | same ingestion fields | Copy. |
| `metadata.pipeline.freshness` | readiness endpoint | Include latest processed date, stale status, and AOI id when available. |

Unavailable behavior: ingestion `status:"UNAVAILABLE"` is not converted into fake numeric statistics. App returns `PIPELINE_OUTPUT_UNAVAILABLE` unless success-with-null-statistics is explicitly implemented and tested. Pipeline field stats use requested date in `acquisitionDate` for UI stability and selected scene date in `basisDate`; downstream exports/reports/risk remain native until separately planned, and any future pipeline consumer that needs scene-accurate dating must use `basisDate`.

## Appendix C — Current-vs-New Route Matrix

| Capability | Current app route/UI | New ingestion-backed MVP behavior | Notes |
|------------|----------------------|-----------------------------------|-------|
| Product sources | `/api/sources` and product config routes | Add Sentinel-2 pipeline availability only when readiness is fresh | Required before stats flag. |
| Product dates | App-domain date endpoints | Merge/annotate ingestion `availableDates` for `sentinel-2-l2a` | No ingestion URLs. |
| Field statistics | `POST /api/fields/{plot_id}/indices/statistics` | Same route; feature-gated Sentinel-2 NDVI branch calls ingestion | Preserve response compatibility. |
| Trend | `GET /api/fields/{plot_id}/analytics/trend` | Native path remains | Pipeline trend deferred. |
| Clipped overlay image | `GET /api/fields/{plot_id}/overlay/{index}.png` / `getFieldIndexOverlayImage` | Native path remains | Pipeline `tileUrl` is separate XYZ. |
| Point value | App point query / `getFieldIndexPoint` | Native path remains | Pipeline point parity deferred. |
| Pipeline stats proxy | None | `GET /api/pipeline/field-index/stats?proxyId=...` | Auth/team/field-bound DB proxy. |
| Pipeline XYZ tile proxy | None | `GET /api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=...` | Requires Phase 1 tile bridge. |
| `/api/indices/statistics` | Legacy/general stats route if present | No deletion in MVP | Audit consumers before deprecation. |
| Field exports | Native trend/statistics backing | Native path remains | Do not break exports. |
| Reports | Native app analytics/risk inputs | Native path remains | Pipeline reports deferred. |
| Risk | Native app risk routes | Native path remains | Pipeline risk deferred. |

## Appendix D — Deletion / Deprecation Matrix

| Area | Delete now? | Deprecate now? | Required action |
|------|-------------|----------------|-----------------|
| ResourceSat native statistics | No | No | Preserve until ResourceSat exists in ingestion and parity is proven. |
| Sentinel-2 native fallback | No | No | Keep for flag-off rollback/tests. |
| `FieldStatisticsResponse.provider='native'` | No | No | Preserve; add optional metadata only. |
| Native trend route/types/tests | No | No | Keep unchanged; future pipeline trend needs its own plan. |
| Native clipped overlay route | No | No | Keep; pipeline XYZ tile is additive. |
| Native point route | No | No | Keep; point parity deferred. |
| `/api/indices/statistics` | No | No | Audit consumers before any future deprecation. |
| Field exports/reports/risk | No | No | Must keep native path because they depend on existing analytics. |
| Frontend hooks/types | No wholesale deletion | No | Extend optional fields; keep existing query functions. |
| Docs/tests for native path | No | No | Add pipeline tests beside native tests. |
| Ingestion `_TRANSPARENT_PNG` placeholder | Yes, in ingestion repo Phase 1 | N/A | Replace with real TiTiler bridge before UI tile work. |

## Appendix E — Rollout and Observability Runbook

1. **Preflight**: tile bridge complete; readiness fresh; source/date bridge shows `sentinel-2-l2a`; contract/golden tests pass in both repos.
2. **Flags-off deploy**: deploy app config, client, proxy tables, and optional frontend metadata rendering with `INGESTION_FIELD_INDEX_ENABLED=false`.
3. **Private smoke**: from app VM, call ingestion `/health`, `/api/v1/sources`, readiness, and field-index using private URL/API key.
4. **Enable stats in staging**: set `INGESTION_READINESS_ENABLED=true` and `INGESTION_FIELD_INDEX_ENABLED=true`; keep tile flag off until PNG smoke passes.
5. **Enable tiles**: set `INGESTION_PIPELINE_TILE_LAYER_ENABLED=true` only after app-domain PNG and browser leak tests pass.
6. **Monitor**: latency, error codes, stale readiness, unavailable reasons, proxy rejects, tile size/status, circuit breaker state.
7. **Rollback**: disable stats flag to restore native behavior; disable tile flag if only XYZ tiles fail. Proxy records can expire naturally.
8. **Browser leak tests**: verify no ingestion hostnames, MinIO/S3/pgSTAC/TiTiler URLs, API key, `sig`, `kid`, or `exp` in network payloads, logs, or local storage.
9. **Retry policy**: retry transient 502/503/504/timeouts with bounded exponential backoff and correlation ID. Retry 429 only when `Retry-After` is present and within a small bounded delay; never retry validation/auth/contract errors.
10. **Circuit breaker**: after repeated transient failures, open for a short TTL and return `PIPELINE_UPSTREAM_UNAVAILABLE` with `retryable:true`.
