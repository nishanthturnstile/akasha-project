---
goal: EOSDA Crop Monitoring Functional Parity Implementation Plan
version: 1.0
date_created: 2026-06-03
last_updated: 2026-06-03
owner: Akasha Engineering
tags: feature, eos, crop-monitoring, provider-adapter, frontend, fastapi, field-management, analytics, weather, vra, reports
---

# Introduction

This implementation plan defines the sequence for upgrading Akasha from the current map-and-raster MVP into an EOSDA Crop Monitoring functional-parity product. Akasha must first replicate EOS-like crop monitoring workflows using EOSDA API Connect as a temporary trial provider, while preserving Akasha's long-term architecture: the browser calls only Akasha same-origin APIs, and paid/external providers are replaceable behind the FastAPI BFF.

The current Akasha application already has a working map shell, Sentinel-2/Sentinel-1 source discovery, date timeline, same-origin tile templates, plot CRUD backend endpoints, and single-date index statistics. The missing core is product workflow depth: field drawing/selection, field-aware EOS provider integration, multi-temporal analytics, weather, VRA zoning, reports, operations/scouting, data imports, account/team modules, notifications, and India-specific advisory intelligence.

This plan is ordered so each phase unlocks the next phase. Field creation and selection must be completed first because every EOS workflow is field-centric. EOS integration must remain behind the BFF because the EOS API key is secret and because production must later replace EOS with Akasha-native STAC/COG/weather/zoning services.

## 1. Requirements & Constraints

- **REQ-001**: The product must replicate EOSDA Crop Monitoring functionality at workflow level before India-specific divergence.
- **REQ-002**: The first parity milestone must support this user path: create or import field, select field, mirror field to EOS, load field scene timeline, render true-colour imagery, render vegetation index imagery, compute/view index analytics, load weather forecast/history, create a vegetation VRA map, and export basic outputs.
- **REQ-003**: The frontend must call only Akasha-owned `/api/*` or same-origin tile/download routes. It must never call EOSDA API Connect directly.
- **REQ-004**: The BFF must expose normalized Akasha DTOs for fields, scenes, tiles, analytics, weather, zoning, reports, tasks, and activities. Raw EOS responses must not be passed through as public contracts.
- **REQ-005**: EOSDA API Connect must be implemented as a temporary provider adapter. Provider-specific IDs must be stored separately from Akasha domain IDs.
- **REQ-006**: Preserve existing native endpoints: `/api/config`, `/api/sources`, `/api/sources/{sourceId}/dates`, `/api/layers/default`, `/api/tiles/...`, `/api/indices/statistics`, and `/api/plots`.
- **REQ-007**: The default map layer must remain true-colour imagery. NDVI or any other index must not become the default map layer.
- **REQ-008**: Field/plot geometry must be validated server-side and field area must be computed server-side. Client-provided area values must not be trusted.
- **REQ-009**: Field management must support draw, edit, delete, list, focus, GeoJSON import, GeoJSON export, field name, area, group, crop, variety, season, sowing/planting date, and status.
- **REQ-010**: The EOS trial provider must support field mirroring, scene search, true-colour tile rendering, index tile rendering, field analytics/trend, weather forecast/history, and vegetation zoning where EOS API access allows it.
- **REQ-011**: The UI must expose an EOS-like navigation structure even when some advanced modules initially contain documented placeholders.
- **REQ-012**: The analytics UI must support at least `NDVI`, `NDRE`, `NDMI`, `MSAVI`, and `RECI` for EOS-parity workflows. Native Akasha support may initially cover fewer indices and must be extended deliberately.
- **REQ-013**: Cloud quality and masked-pixel limitations must be visible to the user for every scene/statistics result.
- **REQ-014**: Weather and zoning data must be normalized behind provider interfaces so EOS can be replaced later by IMD/GFS/ECMWF/Open-Meteo/SMAP/Akasha-native services.
- **REQ-015**: Reports, leaderboard, activity log, scout tasks, data manager, account/team/admin, AI assistant, and notifications must be treated as Akasha-native modules unless a verified public EOS endpoint exists.
- **REQ-016**: All provider secrets must be loaded from ignored local environment variables or deployment secret variables. Secrets must not be committed, logged, shown in frontend code, or returned by APIs.
- **REQ-017**: Add automated tests for every new backend route/provider adapter and every new frontend query/mutation/critical component.
- **SEC-001**: `EOS_API_KEY` must be read only server-side by the FastAPI BFF.
- **SEC-002**: BFF error responses must use Akasha's standard sanitized error envelope `{ "error": { "code", "message", "details" } }`.
- **SEC-003**: Download/export endpoints must proxy or generate files server-side and must not expose provider-signed URLs unless explicitly sanitized and time-limited behind Akasha access checks.
- **SEC-004**: Before customer pilot use, auth and ownership must protect fields, provider links, activities, tasks, reports, uploaded data, and exports.
- **PER-001**: EOS trial request volume must be minimized through caching and explicit user-triggered operations because trial accounts and weather/statistics endpoints have request limits.
- **PER-002**: Scene search, analytics, weather, zoning status/results, and provider readiness responses must use TTL caches where safe.
- **PER-003**: The browser must continue rendering one selected raster layer/date contract rather than managing provider-specific scene composition.
- **CON-001**: The current frontend is a single `MapPage` and has no routing library.
- **CON-002**: `apps/frontend/src/components/scaffold/PlotToolbar.tsx` is currently a disabled placeholder.
- **CON-003**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` is currently a disabled placeholder.
- **CON-004**: `apps/frontend/src/lib/api.ts` currently supports only GET requests for config, sources, dates, and default layer.
- **CON-005**: `apps/frontend/src/lib/queries.ts` currently exposes only `useConfig`, `useSources`, `useDates`, and `useDefaultLayer`.
- **CON-006**: `apps/api/app/plots.py` already provides plot CRUD/import/export and must be reused before creating new geometry storage.
- **CON-007**: `apps/api/app/product.py` already provides single-date index statistics and tile routes; new field-aware/product-provider routes must avoid breaking these contracts.
- **CON-008**: The current frontend has no chart dependency; analytics charts require an explicit dependency decision.
- **CON-009**: The current API requirements do not include an async HTTP client for EOS. Add one deliberately with pinned dependency.
- **CON-010**: The local `.env` file is ignored by git and may contain `EOS_API_KEY=replace-with-eosda-api-connect-key`; a real key must be provided locally/deployment-side before real EOS calls can be verified.
- **GUD-001**: Implement the smallest vertical slice first: field create/select, EOS sync, scene list, true-colour tile, one index layer, one trend chart, one weather response, and one vegetation zoning map.
- **GUD-002**: Preserve Akasha branding and UX quality. Replicate EOS workflow/functionality; do not copy EOS visual assets or proprietary content.
- **GUD-003**: Prefer typed Pydantic models for BFF requests/responses and typed TypeScript interfaces for frontend DTOs.
- **GUD-004**: Use TanStack Query for all frontend server state, including mutations and cache invalidation.
- **GUD-005**: Keep provider adapters modular: `FieldProvider`, `SceneProvider`, `TileProvider`, `AnalyticsProvider`, `WeatherProvider`, and `ZoningProvider`.
- **PAT-001**: Store external provider links in separate tables or explicit provider-link fields: `external_provider`, `external_field_id`, `external_request_id`, `external_zmap_id`, `sync_status`, and `synced_at`.
- **PAT-002**: Keep native Akasha raster/index math centralized in the BFF raster modules and provider-independent DTOs.
- **PAT-003**: Every phase must keep the application runnable with no real EOS key by returning configured/unconfigured provider status and using mocked tests.

### Phase dependency graph

| Phase | Depends on | Unlocks |
|-------|------------|---------|
| Phase 0 — Scope and acceptance matrix | Existing research doc | Shared implementation checklist |
| Phase 1 — Field foundation | Phase 0 | EOS field mirroring, analytics, weather, VRA, reports |
| Phase 2 — Provider adapter foundation | Phase 1 schema decisions | Secure EOS integration |
| Phase 3 — Navigation shell | Phase 0 | EOS-like product workflow surface |
| Phase 4 — Monitoring map parity | Phase 1, Phase 2 | Field-aware imagery and timeline |
| Phase 5 — Analytics panel | Phase 1, Phase 4 | Crop monitoring analytics demo |
| Phase 6 — Cloud controls and exports | Phase 4, Phase 5 | Download/export parity |
| Phase 7 — Weather | Phase 1, Phase 2, Phase 3 | Weather analytics/forecast parity |
| Phase 8 — VRA zoning | Phase 1, Phase 2, Phase 4 | Vegetation zoning demo |
| Phase 9 — Reports/leaderboard | Phase 1, Phase 5, Phase 7 | Multi-field decision UI |
| Phase 10 — Operations/scouting/data | Phase 1, Phase 3 | Field management parity beyond imagery |
| Phase 11 — Risk/crop intelligence | Phase 5, Phase 7, Phase 10 | Advisory layer and India-specific model path |
| Phase 12 — Auth/team/admin/notifications | Phase 1, Phase 10 | Customer-pilot readiness |
| Phase 13 — EOS parity verification | Phases 0-12 | Client demo readiness and native replacement roadmap |

## 2. Implementation Steps

### Implementation Phase 0 — Scope, Acceptance Matrix, and Demo Definition

- GOAL-000: Convert the EOS research findings into an executable acceptance matrix and define the first parity demo slice.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-000 | Create `docs/eos-parity-acceptance-matrix.md` from `docs/eos-crop-monitoring-replication-research.md`. Include one row per EOS module and columns: `Module`, `EOS capability`, `Akasha status`, `Implementation owner`, `Provider strategy`, `First-demo required`, `Acceptance check`, and `Dependencies`. Depends on: none. | ✅ | 2026-06-03 |
| TASK-001 | In `docs/eos-parity-acceptance-matrix.md`, classify every feature as one of `reuse-existing-akasha`, `wire-existing-backend`, `eos-backed-trial`, `akasha-native-first-party`, or `defer`. Depends on: TASK-000. | ✅ | 2026-06-03 |
| TASK-002 | Define first-demo acceptance as this exact path: create/import field, select field, sync to EOS, load scene timeline, display true-colour layer, switch to NDVI, show NDVI trend, show weather forecast/history, create vegetation VRA zones, export one result. Depends on: TASK-001. | ✅ | 2026-06-03 |
| TASK-003 | Add a short section to `docs/eos-parity-acceptance-matrix.md` named `Non-goals for first demo` listing full disease models, yield estimation, AI assistant, marketplace, John Deere integration, full team roles, and paid high-resolution imagery. Depends on: TASK-002. | ✅ | 2026-06-03 |
| TASK-004 | Add a cross-reference from `docs/README.md` to this implementation plan and the acceptance matrix. Depends on: TASK-000. | ✅ | 2026-06-03 |

### Implementation Phase 1 — Field Foundation and Existing Plot API Wiring

- GOAL-001: Make field creation/selection real by wiring the existing plot API into the frontend and extending metadata without duplicating geometry storage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | In `apps/frontend/src/types/api.ts`, add `Plot`, `PlotCreatePayload`, `PlotUpdatePayload`, `PlotImportResponse`, and `RejectedFeature` interfaces matching `apps/api/app/plots.py` response models. Depends on: TASK-002. | ✅ | 2026-06-03 |
| TASK-006 | In `apps/frontend/src/lib/api.ts`, add typed functions `getPlots`, `createPlot`, `updatePlot`, `deletePlot`, `importPlotsGeoJson`, `exportAllPlotsGeoJson`, and `exportPlotGeoJson`. Add POST/PATCH/DELETE support in the shared request helper without breaking existing GET behavior. Depends on: TASK-005. | ✅ | 2026-06-03 |
| TASK-007 | In `apps/frontend/src/lib/queries.ts`, add query keys and TanStack Query hooks/mutations: `usePlots`, `useCreatePlot`, `useUpdatePlot`, `useDeletePlot`, and `useImportPlotsGeoJson`. Each mutation must invalidate the plots list and selected plot where applicable. Depends on: TASK-006. | ✅ | 2026-06-03 |
| TASK-008 | Replace the disabled controls in `apps/frontend/src/components/scaffold/PlotToolbar.tsx` with real actions for draw, edit, import GeoJSON, export GeoJSON, and delete selected field. Keep inaccessible actions disabled with explanatory tooltips when no field is selected. Depends on: TASK-007. | ✅ | 2026-06-03 |
| TASK-009 | Add Terra Draw polygon creation/editing support to the map workflow. Preferred location: new component `apps/frontend/src/components/fields/FieldDrawController.tsx` used by `apps/frontend/src/pages/MapPage.tsx`. Persist created polygons via `useCreatePlot`. Depends on: TASK-008. | ✅ | 2026-06-03 |
| TASK-010 | Add selected-field client state to `apps/frontend/src/state/mapViewContext.tsx`: `selectedPlotId`, `setSelectedPlotId`, and a reset rule when a deleted field is selected. Depends on: TASK-007. | ✅ | 2026-06-03 |
| TASK-011 | Create `apps/frontend/src/components/fields/AllFieldsPanel.tsx` with search, field cards, area display, selected-field focus action, add/import action, and empty/error/loading states. Depends on: TASK-010. | ✅ | 2026-06-03 |
| TASK-012 | Render selected field geometry on MapLibre with a thick white outline and subtle fill. Preferred location: extend `apps/frontend/src/components/map/MapLayerManager.tsx` or create `apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`. Depends on: TASK-010. | ✅ | 2026-06-03 |
| TASK-013 | Add database migration `apps/api/migrations/003_field_metadata_provider_links.sql` with tables or columns for field metadata and provider links. Required fields: group name, crop type, variety, season label, sowing date, planting date, status, external provider, external field id, provider sync status, provider synced at, provider metadata JSON. Depends on: TASK-005. | ✅ | 2026-06-03 |
| TASK-014 | Extend `apps/api/app/plots.py` and `apps/api/app/plots_repo.py` to read/write optional field metadata without breaking existing plot CRUD clients. Depends on: TASK-013. | ✅ | 2026-06-03 |
| TASK-015 | Add backend tests for metadata create/update/list/export behavior in `apps/api/tests/`. Depends on: TASK-014. | ✅ | 2026-06-03 |
| TASK-016 | Add frontend tests for plot API functions, plot query hooks, field toolbar states, field import behavior, and field selection behavior. Depends on: TASK-007, TASK-008, TASK-011. | ✅ | 2026-06-03 |

### Implementation Phase 2 — EOS Provider Adapter Foundation Behind the BFF

- GOAL-002: Add secure server-side EOS provider plumbing without exposing EOS keys or raw contracts to the frontend.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Add EOS/provider settings to `apps/api/app/config.py`: `eos_api_key`, `eos_base_url`, `provider_mode`, `eos_timeout_seconds`, `eos_cache_ttl_seconds`, `eos_rate_limit_per_minute`, and `eos_enabled`. Use safe defaults and never expose `eos_api_key`. Depends on: TASK-013. | | |
| TASK-018 | Add a pinned HTTP client dependency to `apps/api/requirements.txt`. Preferred: `httpx` with an explicit version range compatible with FastAPI. Depends on: TASK-017. | | |
| TASK-019 | Create `apps/api/app/providers/models.py` containing Pydantic DTOs for provider status, field mirror result, scene metadata, tile template metadata, analytics trend points, weather responses, zoning map status, and normalized provider errors. Depends on: TASK-017. | | |
| TASK-020 | Create `apps/api/app/providers/base.py` defining protocol-style interfaces: `FieldProvider`, `SceneProvider`, `TileProvider`, `AnalyticsProvider`, `WeatherProvider`, and `ZoningProvider`. Depends on: TASK-019. | | |
| TASK-021 | Create `apps/api/app/providers/eos/client.py` implementing EOS API Connect requests with `x-api-key`, timeout handling, sanitized error mapping, request logging without secrets, and dependency-injected base URL. Depends on: TASK-018, TASK-019. | | |
| TASK-022 | Create `apps/api/app/providers/eos/field_provider.py` with `mirror_field`, `update_mirror`, `delete_mirror`, and `get_mirror` methods using EOS Field Management API. Store provider link fields via repository functions. Depends on: TASK-021, TASK-014. | | |
| TASK-023 | Create `apps/api/app/providers/eos/scene_provider.py` with field-based scene search methods and normalized scene DTO output containing acquisition date, sensor, cloud percent, usable percent when available, coverage, EOS scene/request/view IDs, and bounds. Depends on: TASK-021, TASK-022. | | |
| TASK-024 | Create `apps/api/app/providers/eos/tile_provider.py` returning Akasha same-origin tile metadata for EOS-backed true-colour and index routes. It must not return direct EOS URLs to the browser. Depends on: TASK-023. | | |
| TASK-025 | Create `apps/api/app/providers/eos/analytics_provider.py` for EOS Field Analytics or Statistics `mt_stats`, normalized to Akasha trend-point DTOs. Depends on: TASK-021, TASK-022. | | |
| TASK-026 | Create `apps/api/app/providers/eos/weather_provider.py` for field forecast, high-accuracy forecast where enabled, historical, accumulated precipitation/temperature, and soil moisture where enabled. Depends on: TASK-021, TASK-022. | | |
| TASK-027 | Create `apps/api/app/providers/eos/zoning_provider.py` for vegetation-map create, retrieve, list, delete, and SHP export operations. Depends on: TASK-021, TASK-022. | | |
| TASK-028 | Add `apps/api/app/providers/router.py` with `GET /api/providers/eos/status`. Response must show configured/enabled/unconfigured state without returning the API key. Depends on: TASK-017, TASK-021. | | |
| TASK-029 | Include provider router in `apps/api/app/main.py`. Depends on: TASK-028. | | |
| TASK-030 | Add provider unit tests using mocked HTTP responses. Cover missing key, sanitized errors, timeout, successful field mirror, successful scene search, and request header behavior without exposing secrets. Depends on: TASK-021, TASK-028. | | |

### Implementation Phase 3 — EOS-Like Product Shell and Navigation

- GOAL-003: Add a product navigation structure that matches EOS workflow coverage while allowing modules to mature incrementally.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-031 | Add a routing dependency to `apps/frontend/package.json`. Preferred: `react-router-dom` pinned to a stable compatible version for React 18. Depends on: TASK-002. | | |
| TASK-032 | Update `apps/frontend/src/App.tsx` to use the router and render a persistent product shell around the map workspace. Depends on: TASK-031. | | |
| TASK-033 | Create `apps/frontend/src/components/shell/AppShell.tsx` with module navigation groups: Monitoring, Weather, Field activity log, VRA maps, Scout tasks, Data manager, Field manager, AI assistant, Notifications, Help, Marketplace, and Account/API/settings. Depends on: TASK-032. | | |
| TASK-034 | Create route components for `MonitoringGlobalView`, `FieldAnalyticsPage`, `FieldLeaderboardPage`, `ReportingPage`, `DiseasesPestsPage`, `WeatherAnalyticsPage`, `WeatherForecastPage`, `FieldActivityLogPage`, `VraSowingPage`, `VraVegetationPage`, `VraPkPage`, `VraMapBuilderPage`, `VraSoilSamplingPage`, `ScoutTasksPage`, `DataManagerPage`, `ConnectionsPage`, `FieldGroupsPage`, `AiAssistantPage`, `NotificationsPage`, `AccountSettingsPage`, and `ApiSettingsPage`. Initial routes may be functional shells with clear status. Depends on: TASK-033. | | |
| TASK-035 | Move the current `MapPage` into the Monitoring/Field Analytics context without breaking direct `/` loading. Redirect `/` to the main monitoring route. Depends on: TASK-032, TASK-034. | | |
| TASK-036 | Add shell tests for navigation rendering, route transitions, selected module highlighting, and map route compatibility. Depends on: TASK-033, TASK-034, TASK-035. | | |

### Implementation Phase 4 — Monitoring Map Parity with Field-Aware EOS Scenes and Tiles

- GOAL-004: Make the map field-aware and EOS-like: selected field drives scene timeline, true-colour layer, index layers, cloud controls, and download affordances.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-037 | Add `POST /api/fields/{plot_id}/providers/eos/sync` in a new field/provider router or existing plot router. It must mirror the selected Akasha field to EOS and persist provider link metadata. Depends on: TASK-022. | ✅ | 2026-06-03 |
| TASK-038 | Add `GET /api/fields/{plot_id}/scenes` returning normalized field-specific scene metadata. It must use EOS scene provider when provider mode is `eos` or `hybrid`, and native STAC fallback where supported. Depends on: TASK-023, TASK-037. | ✅ | 2026-06-03 |
| TASK-039 | Add EOS-backed tile proxy route `GET /api/fields/{plot_id}/tiles/{provider_scene_id}/{display_mode}/{z}/{x}/{y}.png` or equivalent same-origin route. It must proxy/fetch EOS render output server-side and return image content. Depends on: TASK-024, TASK-038. | ✅ | 2026-06-03 |
| TASK-040 | Extend frontend types with `FieldScene`, `FieldLayer`, `ProviderSyncStatus`, and field-aware tile template DTOs. Depends on: TASK-038. | ✅ | 2026-06-03 |
| TASK-041 | Add API functions and TanStack Query hooks for field provider sync and field scene list in `apps/frontend/src/lib/api.ts` and `apps/frontend/src/lib/queries.ts`. Depends on: TASK-040. | ✅ | 2026-06-03 |
| TASK-042 | Update `apps/frontend/src/pages/MapPage.tsx` so selected field scene timeline supersedes global source dates when a field is selected and synced. Preserve existing global date behavior when no field is selected. Depends on: TASK-041, TASK-010. | ✅ | 2026-06-03 |
| TASK-043 | Expand display modes for EOS-backed optical field scenes: `RGB`, `NDVI`, `NDRE`, `NDMI`, `MSAVI`, `RECI`, and optional `FALSE_COLOR`. Keep default `RGB`. Depends on: TASK-039, TASK-042. | ✅ | 2026-06-03 |
| TASK-044 | Add cloud mask control UI with cirrus, cloud, and cloud-shadow toggles. Store the selected mask settings in map view state and pass them to field scene/tile/stat requests. Depends on: TASK-042. | ✅ | 2026-06-03 |
| TASK-045 | Add EOS-like map controls missing from the current shell: find selected field, legend toggle, download menu, and true split/swipe comparison. Existing measure/fullscreen/zoom controls may be reused. Depends on: TASK-042. | ✅ | 2026-06-03 |
| TASK-046 | Add frontend tests for field sync button behavior, field-aware scene timeline, display mode switching, cloud mask toggles, and same-origin tile URL usage. Depends on: TASK-041, TASK-042, TASK-043, TASK-044. | ✅ | 2026-06-03 |
| TASK-047 | Add backend tests for field scene route and EOS tile proxy route using mocked provider responses and image bytes. Depends on: TASK-038, TASK-039. | ✅ | 2026-06-03 |

### Implementation Phase 5 — Field Analytics Panel and Multi-Temporal Trends

- GOAL-005: Replace the placeholder index panel with real single-date and multi-date analytics for selected fields.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-048 | Extend `apps/api/app/raster/indices.py` to support MSAVI and RECI for native calculations where band metadata permits. Preserve existing NDVI, NDRE, NDMI, and NDWI_GREEN_NIR behavior. Depends on: TASK-002. | ✅ | 2026-06-03 |
| TASK-049 | Add `POST /api/fields/{plot_id}/indices/statistics` that can compute statistics for the selected field geometry and selected source/date/index without requiring the frontend to send geometry manually. Depends on: TASK-014, TASK-048. | ✅ | 2026-06-03 |
| TASK-050 | Add `GET /api/fields/{plot_id}/analytics/trend` with query params `indexType`, `startDate`, `endDate`, `provider`, and `cloudMask`. It must use EOS analytics provider during trial and return normalized trend points. Depends on: TASK-025, TASK-037. | ✅ | 2026-06-03 |
| TASK-051 | Add backend tests for field statistics route, invalid index handling, missing field handling, and trend normalization from mocked EOS responses. Depends on: TASK-049, TASK-050. | ✅ | 2026-06-03 |
| TASK-052 | Choose and add a chart dependency in `apps/frontend/package.json`. The selected dependency must support accessible line charts, tooltips, responsive layout, and deterministic tests. Depends on: TASK-050. | ✅ | 2026-06-03 |
| TASK-053 | Replace `apps/frontend/src/components/scaffold/IndexPanel.tsx` with a real `FieldAnalyticsPanel` that displays selected index, latest statistics, valid/cloud/coverage percentages, trend chart, loading/error/empty states, and provider metadata. Depends on: TASK-052, TASK-049, TASK-050. | ✅ | 2026-06-03 |
| TASK-054 | Add analytics tabs or sections for Crop info, Chart, Activities, Crop rotation, Growth stages, Current risks, and NDVI value split. Sections without implemented data must show explicit planned-state copy, not silent empty UI. Depends on: TASK-053. | ✅ | 2026-06-03 |
| TASK-055 | Add frontend API functions/hooks for field statistics and field trend queries. Depends on: TASK-049, TASK-050. | ✅ | 2026-06-03 |
| TASK-056 | Add tests for analytics panel rendering, chart empty state, cloud warning display, index switch, selected-field required state, and failed request state. Depends on: TASK-053, TASK-055. | ✅ | 2026-06-03 |

Phase 5 chart decision: no package was added for TASK-052. The selected implementation is a deterministic accessible SVG chart to avoid dependency churn.

### Implementation Phase 6 — Cloud Masking, Legends, and Exports

- GOAL-006: Match EOS operational controls for cloud filtering, legends, and selected index/date exports.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-057 | Define `CloudMaskOptions` in backend and frontend DTOs with booleans for `clouds`, `cloudShadows`, `cirrus`, and a provider/native mapping field. Depends on: TASK-044. | ✅ | 2026-06-03 |
| TASK-058 | Map `CloudMaskOptions` to EOS `cloud_masking_level` conservatively for statistics and imagery requests. Document exact mapping in provider code comments and tests. Depends on: TASK-057, TASK-021. | ✅ | 2026-06-03 |
| TASK-059 | Add `GET /api/fields/{plot_id}/exports/index` supporting export type `geotiff`, `geojson`, `shp`, and `csv` where available. It must call EOS imagery/zoning/export APIs or native Akasha exporters and return a file response. Depends on: TASK-039, TASK-049. | ✅ | 2026-06-03 |
| TASK-060 | Add `GET /api/fields/{plot_id}/exports/report.csv` for basic selected-field analytics export. Depends on: TASK-050. | ✅ | 2026-06-03 |
| TASK-061 | Update frontend legend behavior so RGB hides index ramps, index layers show matching color ramp/thresholds, and EOS-backed index layers can use EOS-compatible labels. Depends on: TASK-043. | ✅ | 2026-06-03 |
| TASK-062 | Implement download menu actions for `NDVI.tiff`, `NDVI.shp`, `Contours.shp`, and analytics CSV where available. Depends on: TASK-059, TASK-060. | ✅ | 2026-06-03 |
| TASK-063 | Add backend and frontend tests for cloud mask option mapping and export download actions. Depends on: TASK-058, TASK-059, TASK-062. | ✅ | 2026-06-03 |

### Implementation Phase 7 — Weather Analytics and Forecast

- GOAL-007: Add EOS-like field weather forecast/history UI backed by normalized provider APIs.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-064 | Add `GET /api/fields/{plot_id}/weather/forecast` returning normalized forecast cards for temperature, precipitation, relative humidity, clouds, and wind. Depends on: TASK-026, TASK-037. | Yes | 2026-06-03 |
| TASK-065 | Add `GET /api/fields/{plot_id}/weather/history` returning time series for accumulated precipitation, daily precipitation, daily temperature, sum active temperatures, evapotranspiration, relative humidity, and global radiation. Depends on: TASK-026, TASK-037. | Yes | 2026-06-03 |
| TASK-066 | Add `GET /api/fields/{plot_id}/weather/soil-moisture` where EOS trial access supports it. If unsupported, return a clear provider-unavailable response. Depends on: TASK-026. | Yes | 2026-06-03 |
| TASK-067 | Implement `apps/frontend/src/pages/weather/WeatherForecastPage.tsx` with current cards, forecast timeline, field-required empty state, loading state, and provider-unavailable state. Depends on: TASK-064, TASK-034. | Yes | 2026-06-03 |
| TASK-068 | Implement `apps/frontend/src/pages/weather/WeatherAnalyticsPage.tsx` with parameter selectors, date range controls, comparison mode placeholder, and charts for all supported weather series. Depends on: TASK-065, TASK-052, TASK-034. | Yes | 2026-06-03 |
| TASK-069 | Add weather API functions/hooks in `apps/frontend/src/lib/api.ts` and `apps/frontend/src/lib/queries.ts`. Depends on: TASK-064, TASK-065, TASK-066. | Yes | 2026-06-03 |
| TASK-070 | Add backend provider tests and frontend page tests for forecast/history success, rate-limit/provider errors, and no selected field. Depends on: TASK-064, TASK-065, TASK-067, TASK-068. | Yes | 2026-06-03 |

### Implementation Phase 8 — VRA Vegetation Zoning and Zoning Module Shells

- GOAL-008: Implement the first EOS-compatible VRA workflow: vegetation-based zone creation, retrieval, display, and export.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-071 | Add `POST /api/fields/{plot_id}/zoning/vegetation` with request body `indexType`, `imageDate`, `zoneCount`, `minZoneArea`, and optional provider callback/async flags. Depends on: TASK-027, TASK-037, TASK-043. | Yes | 2026-06-03 |
| TASK-072 | Add `GET /api/fields/{plot_id}/zoning/maps` and `GET /api/fields/{plot_id}/zoning/maps/{zmap_id}` returning normalized zone geometry, area, percentage, cluster values, status, and provider metadata. Depends on: TASK-071. | Yes | 2026-06-03 |
| TASK-073 | Add `GET /api/fields/{plot_id}/zoning/maps/{zmap_id}/export.shp` and optional `export.geojson`. Depends on: TASK-072. | Yes | 2026-06-03 |
| TASK-074 | Implement `VraVegetationPage` with form controls for selected field, date, index, zone count, minimum zone area, create action, processing state, zone map overlay, zone table, and export actions. Depends on: TASK-071, TASK-072, TASK-073, TASK-034. | Yes | 2026-06-03 |
| TASK-075 | Implement clear shells for `VraSowingPage`, `VraPkPage`, `VraMapBuilderPage`, and `VraSoilSamplingPage` with descriptions and dependency notes. Depends on: TASK-034. | Yes | 2026-06-03 |
| TASK-076 | Add tests for zoning create/retrieve/export backend flows and VRA Vegetation UI form/processing/result states. Depends on: TASK-071, TASK-072, TASK-074. | Yes | 2026-06-03 |

### Implementation Phase 9 — Field Leaderboard, Reporting, and Report Templates

- GOAL-009: Build Akasha-native reporting and leaderboard features from normalized field analytics/weather/activity data.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-077 | Add `GET /api/reports/field-leaderboard` returning fields ranked by latest index value, index delta, cloud-free recency, weather risk summary, crop, group, season, area, and image date. Depends on: TASK-050, TASK-064, TASK-014. | Yes | 2026-06-04 |
| TASK-078 | Add `POST /api/reports/templates`, `GET /api/reports/templates`, and `PATCH /api/reports/templates/{template_id}` for custom report column templates. Store templates in a new migration `005_report_templates.sql`. Depends on: TASK-077. | Yes | 2026-06-04 |
| TASK-079 | Add `GET /api/reports/field-leaderboard/export.csv` and optional `export.xlsx` after choosing an XLSX library. CSV is required first. Depends on: TASK-077. | Yes | 2026-06-04 |
| TASK-080 | Implement `FieldLeaderboardPage` with filters/columns matching EOS: index, group, crop, variety, report date, field, location, coordinates, area, sowing/planting, index value, value change, actual yield, image date, and preview/open. Depends on: TASK-077, TASK-034. | Yes | 2026-06-04 |
| TASK-081 | Implement `ReportingPage` with create-template workflow and selectable columns. Depends on: TASK-078, TASK-034. | Yes | 2026-06-04 |
| TASK-082 | Add backend and frontend tests for leaderboard sorting, report template CRUD, CSV export, and UI filters. Depends on: TASK-077, TASK-078, TASK-080, TASK-081. | Yes | 2026-06-04 |

### Implementation Phase 10 — Field Activity Log, Scout Tasks, Data Manager, and Field Groups

- GOAL-010: Add EOS-like operational modules as Akasha-native first-party data workflows.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-083 | Add migration `006_operations_tasks_data_manager.sql` with tables for field activities, scout tasks, field groups, uploaded datasets, and attachments metadata. Depends on: TASK-013. | Yes | 2026-06-04 |
| TASK-084 | Add `apps/api/app/operations.py` with CRUD endpoints for field activities: type, date, field, assignee, status, input/product, cost, notes, and attachment references. Depends on: TASK-083. | Yes | 2026-06-04 |
| TASK-085 | Add `apps/api/app/scout_tasks.py` with CRUD endpoints for map-pin tasks, status `new|closed`, assignee, priority, notes, photos/attachments, and field linkage. Depends on: TASK-083. | Yes | 2026-06-04 |
| TASK-086 | Add `apps/api/app/data_manager.py` with dataset upload metadata endpoints for GeoJSON/SHP ZIP first. ISO-XML may be stored as uploaded metadata until parsing rules are implemented. Depends on: TASK-083. | Yes | 2026-06-04 |
| TASK-087 | Add `apps/api/app/field_groups.py` with CRUD endpoints for field groups and field assignment. Depends on: TASK-083. | Yes | 2026-06-04 |
| TASK-088 | Implement `FieldActivityLogPage` with filters for group/crop/variety/activity/assignee, yearly calendar timeline, add activity, and download report action. Depends on: TASK-084, TASK-034. | Yes | 2026-06-04 |
| TASK-089 | Implement `ScoutTasksPage` with map task pins, task list, search/filter, New/Closed tabs, and add-new-task-by-pin workflow. Depends on: TASK-085, TASK-034. | Yes | 2026-06-04 |
| TASK-090 | Implement `DataManagerPage` with upload/drop zone for GeoJSON/SHP ZIP and ISO-XML ZIP, max upload copy, upload status, and dataset list. Depends on: TASK-086, TASK-034. | Yes | 2026-06-04 |
| TASK-091 | Implement `ConnectionsPage` with John Deere placeholder and clear `not connected` state. Do not implement OAuth until client confirms need. Depends on: TASK-034. | Yes | 2026-06-04 |
| TASK-092 | Implement `FieldGroupsPage` with add group, edit group, delete group, and assign fields. Depends on: TASK-087, TASK-034. | Yes | 2026-06-04 |
| TASK-093 | Add backend/frontend tests for activities, scout tasks, dataset metadata upload, field groups, and corresponding pages. Depends on: TASK-084, TASK-085, TASK-086, TASK-087, TASK-088, TASK-089, TASK-090, TASK-092. | Yes | 2026-06-04 |

### Implementation Phase 11 — Risk Map, Crop Stages, Diseases/Pests Shell, and India-Specific Intelligence Path

- GOAL-011: Add decision-support features after monitoring, analytics, weather, and operations data exist.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-094 | Add `apps/api/app/risk.py` with `GET /api/fields/{plot_id}/risk/summary`. Initial risk inputs: latest index value, index delta between latest two clean scenes, weather stress flags, cloud-data gap, crop/season metadata, and open scout tasks. Depends on: TASK-050, TASK-064, TASK-085, TASK-014. | Yes | 2026-06-04 |
| TASK-095 | Implement a transparent rule-based risk scoring model with output levels `low`, `medium`, `high`, and `unknown`. Do not claim disease diagnosis from NDVI alone. Depends on: TASK-094. | Yes | 2026-06-04 |
| TASK-096 | Add crop-stage timeline calculation from crop type and sowing/planting date. Start with generic stages and explicit `modelVersion`. Depends on: TASK-014. | Yes | 2026-06-04 |
| TASK-097 | Implement `DiseasesPestsPage` with manage-disease-list placeholder, low/medium/high risk legend, crop/growth-stage context, and clear statement when no validated model is available. Depends on: TASK-095, TASK-096, TASK-034. | Yes | 2026-06-04 |
| TASK-098 | Add `docs/india-specific-productization-plan.md` covering Kharif/Rabi/Zaid seasons, Indian crop catalog, IMD weather warnings, regional languages, smallholder workflows, WhatsApp/SMS advisory path, and government/insurance workflows. Depends on: TASK-095, TASK-096. | Yes | 2026-06-04 |
| TASK-099 | Add tests for risk summary levels, crop-stage calculation, and disease/pest page states. Depends on: TASK-094, TASK-096, TASK-097. | Yes | 2026-06-04 |

### Implementation Phase 12 — Auth, Teams, API/Admin, Notifications, and Pilot Readiness

- GOAL-012: Add ownership, collaboration, and admin surfaces required before real customer pilot data is used.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-100 | Decide authentication provider and document decision in `docs/auth-team-admin-plan.md`. Minimum decision fields: provider, local dev mode, Railway deployment mode, session storage, user table, team table, and migration approach. Depends on: TASK-010, TASK-083. | | |
| TASK-101 | Add migrations for users, teams, memberships, roles, API keys, and ownership columns on fields/activities/tasks/reports/uploads/provider links. Depends on: TASK-100. | | |
| TASK-102 | Add authentication middleware/dependencies in FastAPI and ownership checks for field, activity, task, report, data manager, and provider routes. Depends on: TASK-101. | | |
| TASK-103 | Implement account/team/settings/API pages and team switching UI. Depends on: TASK-102, TASK-034. | | |
| TASK-104 | Add notification tables and routes for field changes, risk alerts, task assignment, report availability, and provider sync failures. Depends on: TASK-102, TASK-094, TASK-085. | | |
| TASK-105 | Implement Notifications page/panel with empty state, unread count, and notification detail actions. Depends on: TASK-104, TASK-034. | | |
| TASK-106 | Implement AI assistant shell only after analytics/weather/risk endpoints exist. It may summarize field data from Akasha APIs but must not invent agronomic advice beyond available evidence. Depends on: TASK-050, TASK-065, TASK-094. | | |
| TASK-107 | Add security and authorization tests for every protected route and frontend tests for team/settings/notifications states. Depends on: TASK-102, TASK-103, TASK-104, TASK-105. | | |

### Implementation Phase 13 — End-to-End EOS Parity Verification and Native Replacement Readiness

- GOAL-013: Verify the full EOS-like workflow and ensure the EOS provider remains replaceable.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-108 | Run a mocked-provider E2E workflow: create field, sync provider, load scenes, render tile template, view trend, view weather, create VRA map, export report. Depends on: TASK-076, TASK-082, TASK-093. | | |
| TASK-109 | Run a real-EOS smoke test only with local/deployment `EOS_API_KEY`: field mirror, scene search, true-colour tile, NDVI trend, weather forecast/history, and vegetation zoning map. Do not print the key. Depends on: TASK-030, TASK-047, TASK-070, TASK-076. | | |
| TASK-110 | Update `docs/eos-parity-acceptance-matrix.md` with pass/fail status for every first-demo required feature. Depends on: TASK-108, TASK-109. | | |
| TASK-111 | Add provider-replacement notes to `docs/architecture-tech-stack.md`: map each EOS-backed feature to Akasha-native STAC/COG/weather/zoning/reporting replacement. Depends on: TASK-110. | | |
| TASK-112 | Run complete validation: `cd apps/api && python -m pytest -q`, `cd apps/frontend && yarn test`, `cd apps/frontend && yarn lint`, `cd apps/frontend && yarn build`, and relevant raster validators. Depends on: all implementation phases touched. | | |

## 3. Alternatives

- **ALT-001**: Call EOS directly from the frontend. Rejected because it exposes `EOS_API_KEY`, couples UI to paid-provider contracts, and violates Akasha's BFF guardrail.
- **ALT-002**: Build Akasha-native replacements for every EOS feature before integrating EOS. Rejected for the current client goal because EOS trial integration can validate functional parity faster and clarify exact workflows.
- **ALT-003**: Implement navigation shells first and defer field drawing. Rejected because field selection is the dependency for scenes, analytics, weather, VRA, reports, activities, scout tasks, and data imports.
- **ALT-004**: Store EOS field IDs directly inside `akasha.plots` as hard-coded columns only. Rejected because multiple providers and future native replacement require a provider-link abstraction.
- **ALT-005**: Make NDVI the default view to match crop-health emphasis. Rejected because Akasha guardrails require true-colour imagery by default and NDVI is not a complete crop-health diagnosis.
- **ALT-006**: Build reports/leaderboard from a non-existent EOS report API. Rejected because reviewed EOS public APIs do not expose complete reporting/leaderboard endpoints; Akasha should compose these from fields, analytics, weather, and operations.
- **ALT-007**: Implement full auth/team management before imagery parity. Deferred for internal demo speed, but required before customer pilot or shared data workflows.
- **ALT-008**: Copy EOS visual design exactly. Rejected because the target is functional parity with Akasha branding, not copying proprietary UI assets.

## 4. Dependencies

- **DEP-001**: Existing Akasha FastAPI BFF under `apps/api/app`.
- **DEP-002**: Existing Akasha React/Vite frontend under `apps/frontend`.
- **DEP-003**: Existing plot CRUD API in `apps/api/app/plots.py` and `apps/api/app/plots_repo.py`.
- **DEP-004**: Existing product/tile/statistics API in `apps/api/app/product.py`.
- **DEP-005**: Existing PostGIS app schema in `apps/api/migrations/001_app_schema.sql` and `002_plots_polygon_multipolygon.sql`.
- **DEP-006**: EOSDA API Connect key supplied as server-side `EOS_API_KEY` in ignored `.env` or deployment variables.
- **DEP-007**: EOSDA API Connect endpoints for Field Management, Scene Search/Search, Render, Imagery, Field Analytics/Statistics, Weather, Soil Moisture, Zoning, Colorization, Terrain, and Point Value where available.
- **DEP-008**: TanStack Query already installed in `apps/frontend` for server-state management.
- **DEP-009**: Terra Draw and Terra Draw MapLibre adapter already installed for map drawing workflows.
- **DEP-010**: Phase 5 selected a no-dependency accessible SVG chart for the initial analytics trend view.
- **DEP-011**: A routing library to be selected in Phase 3, preferably `react-router-dom` for React 18 compatibility.
- **DEP-012**: A backend HTTP client dependency to be selected in Phase 2, preferably `httpx`.
- **DEP-013**: Optional export dependencies for SHP/XLSX/PDF after CSV/GeoJSON exports are working.
- **DEP-014**: Native Akasha STAC/COG/weather/zoning services for long-term provider replacement after EOS trial parity.

## 5. Files

- **FILE-001**: `docs/eos-crop-monitoring-replication-research.md` — Current EOS feature/API inventory and UI findings.
- **FILE-002**: `docs/eos-parity-acceptance-matrix.md` — New execution checklist generated in Phase 0.
- **FILE-003**: `docs/impl-plan/feature-eos-crop-monitoring-parity-1.md` — This implementation plan.
- **FILE-004**: `docs/README.md` — Documentation index link target.
- **FILE-005**: `apps/api/app/config.py` — Provider settings including EOS configuration.
- **FILE-006**: `apps/api/requirements.txt` — Add backend HTTP client dependency.
- **FILE-007**: `apps/api/app/providers/base.py` — New provider interface definitions.
- **FILE-008**: `apps/api/app/providers/models.py` — New normalized provider DTOs.
- **FILE-009**: `apps/api/app/providers/eos/client.py` — New EOS HTTP client.
- **FILE-010**: `apps/api/app/providers/eos/field_provider.py` — New EOS field provider.
- **FILE-011**: `apps/api/app/providers/eos/scene_provider.py` — New EOS scene provider.
- **FILE-012**: `apps/api/app/providers/eos/tile_provider.py` — New EOS tile provider/proxy support.
- **FILE-013**: `apps/api/app/providers/eos/analytics_provider.py` — New EOS analytics provider.
- **FILE-014**: `apps/api/app/providers/eos/weather_provider.py` — New EOS weather provider.
- **FILE-015**: `apps/api/app/providers/eos/zoning_provider.py` — New EOS zoning provider.
- **FILE-016**: `apps/api/app/providers/router.py` — New provider status and sync routes.
- **FILE-017**: `apps/api/app/main.py` — Include new provider/domain routers.
- **FILE-018**: `apps/api/app/plots.py` — Extend plot/field metadata and optionally provider sync surface.
- **FILE-019**: `apps/api/app/plots_repo.py` — Extend plot/field persistence.
- **FILE-020**: `apps/api/app/product.py` — Preserve existing product routes; add or coordinate field-aware routes.
- **FILE-021**: `apps/api/app/raster/indices.py` — Add MSAVI and RECI native support where possible.
- **FILE-022**: `apps/api/migrations/003_field_metadata_provider_links.sql` — New field metadata/provider link migration.
- **FILE-023**: `apps/api/migrations/004_zoning_maps.sql` — New zoning map public-ID/job-handle migration.
- **FILE-024**: `apps/api/migrations/005_report_templates.sql` — New report template migration.
- **FILE-025**: `apps/api/migrations/006_operations_tasks_data_manager.sql` — New operations/scouting/data manager migration.
- **FILE-026**: `apps/api/app/operations.py` — New field activity routes.
- **FILE-027**: `apps/api/app/scout_tasks.py` — New scout task routes.
- **FILE-028**: `apps/api/app/data_manager.py` — New dataset upload/metadata routes.
- **FILE-029**: `apps/api/app/field_groups.py` — New field group routes.
- **FILE-030**: `apps/api/app/risk.py` — New risk summary routes.
- **FILE-031**: `apps/frontend/package.json` — Add routing/chart/export dependencies as phases require.
- **FILE-032**: `apps/frontend/src/App.tsx` — Add routing and shell.
- **FILE-033**: `apps/frontend/src/pages/MapPage.tsx` — Make current map field-aware and route-aware.
- **FILE-034**: `apps/frontend/src/components/scaffold/PlotToolbar.tsx` — Replace placeholder with real field tools.
- **FILE-035**: `apps/frontend/src/components/scaffold/IndexPanel.tsx` — Replace placeholder with analytics panel or delegate to new analytics component.
- **FILE-036**: `apps/frontend/src/state/mapViewContext.tsx` — Add selected field, cloud-mask, and field-aware view state.
- **FILE-037**: `apps/frontend/src/lib/api.ts` — Add typed API functions for fields, provider sync, scenes, stats, weather, zoning, reports, operations, tasks, data manager, groups, risk, notifications.
- **FILE-038**: `apps/frontend/src/lib/queries.ts` — Add TanStack Query hooks/mutations and invalidation rules.
- **FILE-039**: `apps/frontend/src/types/api.ts` — Add normalized frontend DTOs.
- **FILE-040**: `apps/frontend/src/components/fields/FieldDrawController.tsx` — New field drawing/editing controller.
- **FILE-041**: `apps/frontend/src/components/fields/AllFieldsPanel.tsx` — New All Fields panel.
- **FILE-042**: `apps/frontend/src/components/fields/FieldBoundaryLayer.tsx` — New selected field boundary layer if not handled in `MapLayerManager`.
- **FILE-043**: `apps/frontend/src/components/shell/AppShell.tsx` — New product shell.
- **FILE-044**: `apps/frontend/src/pages/weather/WeatherForecastPage.tsx` — New forecast page.
- **FILE-045**: `apps/frontend/src/pages/weather/WeatherAnalyticsPage.tsx` — New weather analytics page.
- **FILE-046**: `apps/frontend/src/pages/vra/VraVegetationPage.tsx` — New VRA vegetation page.
- **FILE-047**: `apps/frontend/src/pages/reports/FieldLeaderboardPage.tsx` — New field leaderboard page.
- **FILE-048**: `apps/frontend/src/pages/reports/ReportingPage.tsx` — New reporting/template page.
- **FILE-049**: `apps/frontend/src/pages/operations/FieldActivityLogPage.tsx` — New activity log page.
- **FILE-050**: `apps/frontend/src/pages/scout/ScoutTasksPage.tsx` — New scout tasks page.
- **FILE-051**: `apps/frontend/src/pages/data/DataManagerPage.tsx` — New data manager page.
- **FILE-052**: `apps/frontend/src/pages/fields/FieldGroupsPage.tsx` — New field groups page.
- **FILE-053**: `apps/frontend/src/pages/risk/DiseasesPestsPage.tsx` — New diseases/pests page.
- **FILE-054**: `docs/architecture-tech-stack.md` — Update provider adapter and replacement path after parity verification.
- **FILE-055**: `docs/india-specific-productization-plan.md` — New India-specific plan after baseline parity.
- **FILE-056**: `docs/auth-team-admin-plan.md` — New auth/team/admin decision doc before pilot.

## 6. Testing

- **TEST-001**: Backend unit tests for plot metadata and provider-link persistence.
- **TEST-002**: Backend unit tests for EOS client configuration, missing API key, sanitized provider errors, timeouts, and mocked successful responses.
- **TEST-003**: Backend route tests for provider status, field sync, field scene list, field tile proxy, field statistics, field trend, weather forecast/history, zoning create/retrieve/export, leaderboard, reports, activities, scout tasks, data manager, field groups, risk, and notifications.
- **TEST-004**: Frontend unit tests for typed API functions and TanStack Query hooks/mutations, including cache invalidation.
- **TEST-005**: Frontend component tests for `PlotToolbar`, `AllFieldsPanel`, field boundary rendering, field sync controls, field-aware timeline, display mode switching, cloud mask menu, download menu, and analytics panel.
- **TEST-006**: Frontend route tests for product shell navigation and all module shells/pages.
- **TEST-007**: Frontend chart tests for trend empty/loading/error/success states.
- **TEST-008**: Weather page tests for no selected field, successful forecast/history, provider unavailable, and rate-limit error states.
- **TEST-009**: VRA page tests for create form validation, processing state, retrieved zone display, and export actions.
- **TEST-010**: Report/leaderboard tests for sorting, filtering, selected columns, and CSV export.
- **TEST-011**: Operations/scout/data manager tests for CRUD, filters, map-pin task creation, dataset upload metadata, and field group assignment.
- **TEST-012**: Risk tests for low/medium/high/unknown levels and crop-stage timeline calculation.
- **TEST-013**: Security tests verifying EOS key is never returned by `/api/providers/eos/status` or errors.
- **TEST-014**: Authorization tests after auth phase for field ownership, task ownership, report ownership, upload ownership, and provider link access.
- **TEST-015**: Mocked end-to-end test for the first demo path with no real EOS key.
- **TEST-016**: Optional real-EOS smoke test guarded by local `EOS_API_KEY` and skipped automatically when no key is configured.
- **TEST-017**: Regression tests proving existing `/api/config`, `/api/sources`, `/api/sources/{sourceId}/dates`, `/api/layers/default`, `/api/tiles/...`, `/api/indices/statistics`, and `/api/plots` still work.
- **TEST-018**: Manual browser QA checklist: load app, open shell navigation, create/import field, sync field, switch dates, switch true-colour/index layers, compute stats, view trend, view weather, create VRA map, export output, view report/leaderboard, add activity, add scout task.
- **TEST-019**: Required commands after touched phases: `cd apps/api && python -m pytest -q`, `cd apps/frontend && yarn test`, `cd apps/frontend && yarn lint`, `cd apps/frontend && yarn build`.

## 7. Risks & Assumptions

- **RISK-001**: EOS trial limits may block frequent testing if caching and mocked tests are not implemented early.
- **RISK-002**: EOS API response schemas may differ from docs or be gated by account plan. Every provider route must handle unavailable features gracefully.
- **RISK-003**: EOS zoning workflows may be asynchronous and take 30-300 seconds, requiring polling and durable request metadata.
- **RISK-004**: Exact EOS visual parity may require color ramps/thresholds not fully documented. Functional parity with Akasha styling is the default unless client demands exact colors.
- **RISK-005**: Adding routing and many module shells can destabilize the current single-page map if done without tests.
- **RISK-006**: Field metadata schema may evolve quickly. Use additive migrations and avoid irreversible assumptions.
- **RISK-007**: Chart/export dependencies can increase frontend bundle size. Add only when required and measure after build.
- **RISK-008**: Auth/team work can become large. It is intentionally later for internal demo speed but mandatory before real customer pilot data.
- **RISK-009**: Disease/pest and yield estimates require agronomic validation. Do not present rule-based outputs as definitive diagnosis.
- **RISK-010**: Native replacement work may be delayed if provider-specific assumptions leak into frontend DTOs.
- **ASSUMPTION-001**: A valid EOSDA API Connect key will be available locally/deployment-side for real provider smoke tests.
- **ASSUMPTION-002**: First demo scope is Monitoring + Field Analytics + Weather + Vegetation VRA, with advanced modules present as shells or placeholders.
- **ASSUMPTION-003**: Akasha may use single-tenant/no-auth mode for internal demo only.
- **ASSUMPTION-004**: The client wants functional parity first, then India-specific localization and paid-provider replacement.
- **ASSUMPTION-005**: Existing Sentinel-2 native functionality must remain usable throughout EOS trial integration.
- **ASSUMPTION-006**: Provider-normalized DTOs are allowed to omit fields not available from a given provider as long as the response documents availability and reason.

## 8. Related Specifications / Further Reading

- `docs/eos-crop-monitoring-replication-research.md`
- `docs/platform-plan.md`
- `docs/architecture-tech-stack.md`
- `docs/engineering-dos-donts.md`
- `docs/data-ingestion-and-satellite-rules.md`
- `docs/product-plan.md`
- `apps/api/app/product.py`
- `apps/api/app/plots.py`
- `apps/api/app/plots_repo.py`
- `apps/api/app/config.py`
- `apps/frontend/src/pages/MapPage.tsx`
- `apps/frontend/src/components/scaffold/PlotToolbar.tsx`
- `apps/frontend/src/components/scaffold/IndexPanel.tsx`
- `apps/frontend/src/lib/api.ts`
- `apps/frontend/src/lib/queries.ts`
- `apps/frontend/src/types/api.ts`
- EOSDA API Connect quickstart: `https://doc.eos.com/docs/quickstart/`
- EOSDA Crop Monitoring product page: `https://eos.com/products/crop-monitoring/`
