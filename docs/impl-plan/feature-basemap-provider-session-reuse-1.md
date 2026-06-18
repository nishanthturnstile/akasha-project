---
goal: Basemap Provider Switch and Esri Session Reuse
version: 1.0
date_created: 2026-06-17
last_updated: 2026-06-17
owner: Akasha Engineering
tags: [feature, frontend, maps, cost-optimization, arcgis]
---

# Introduction

This plan implements a development-safe basemap strategy for Akasha. The frontend will support `VITE_BASEMAP_PROVIDER=esri | osm | empty`, default local development to `osm`, preserve ArcGIS session mode for staging/production, and reuse one Esri basemap session across map screens within a browser runtime. The goal is to avoid exhausting ArcGIS Location Platform basemap session free-tier usage during development without changing Akasha satellite overlay behavior.

## 1. Requirements & Constraints

- **REQ-001**: The frontend must support exactly three basemap providers: `esri`, `osm`, and `empty`.
- **REQ-002**: `VITE_BASEMAP_PROVIDER` must override `/api/config.basemap.provider` when it is set to a valid provider.
- **REQ-003**: If `VITE_BASEMAP_PROVIDER` is unset, the frontend must use `/api/config.basemap.provider`.
- **REQ-004**: Local development documentation must show `VITE_BASEMAP_PROVIDER=osm` as the recommended default.
- **REQ-005**: `esri` must keep the current ArcGIS Location Platform basemap session behavior and require `VITE_ESRI_API_KEY`.
- **REQ-006**: `osm` must render a MapLibre raster basemap without calling `BasemapSession.start` or `BasemapStyle.loadStyle`.
- **REQ-007**: `empty` must render a blank MapLibre style without calling any external basemap service.
- **REQ-008**: Akasha satellite overlays, comparison overlays, field-clipped index overlays, opacity, visibility, and scene-fit behavior must remain provider-independent.
- **REQ-009**: Esri sessions must be reused across `MapLayerManager` mounts in the same browser runtime when session options are equivalent.
- **REQ-010**: Map previews must not be introduced on non-map routes; the existing lazy route behavior must be preserved.
- **SEC-001**: ArcGIS API keys must remain frontend build-time public keys and must be referrer-restricted outside local development.
- **SEC-002**: No ArcGIS key must be required for `osm` or `empty` providers.
- **CON-001**: The frontend must continue using MapLibre GL JS.
- **CON-002**: The browser must not call MinIO, STAC, PostGIS, or TiTiler directly except through existing same-origin Akasha tile routes.
- **CON-003**: ResourceSat FCC satellite overlay behavior must not be changed.
- **PAT-001**: Preserve existing `resolveBasemapConfig` and `MapLayerManager` seams instead of introducing unrelated routing or map architecture rewrites.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Extend basemap configuration types and resolver behavior using test-first changes.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Modify `apps/frontend/src/types/api.ts` so `BasemapProvider` is `'esri' | 'osm' | 'empty'` while keeping `BasemapUsageModel` as `'session'` for Esri config compatibility. | ✅ | 2026-06-17 |
| TASK-002 | Modify `apps/frontend/src/vite-env.d.ts` to add `readonly VITE_BASEMAP_PROVIDER?: string;`. | ✅ | 2026-06-17 |
| TASK-003 | Modify `apps/frontend/src/map/basemap.test.ts` to add failing coverage for `osm`, `empty`, Esri override precedence, and missing Esri key behavior only under `esri`. | ✅ | 2026-06-17 |
| TASK-004 | Modify `apps/frontend/src/map/basemap.ts` to return a discriminated union config for `esri`, `osm`, and `empty`, with `VITE_BASEMAP_PROVIDER` taking precedence over server config. | ✅ | 2026-06-17 |
| TASK-005 | Run `npx vitest run src/map/basemap.test.ts` from `apps/frontend` and verify all basemap resolver tests pass. | ✅ | 2026-06-17 |

### Implementation Phase 2

- GOAL-002: Add shared Esri basemap session reuse.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | Create `apps/frontend/src/map/esriBasemapSession.ts` exporting `getSharedEsriBasemapSession(config)` and `resetSharedEsriBasemapSessionForTests()`; cache by token, style family, duration, and safety margin. | ✅ | 2026-06-17 |
| TASK-007 | Add unit coverage in `apps/frontend/src/components/map/MapLayerManager.test.tsx` proving equivalent Esri map mounts call `BasemapSession.start` once and reuse the returned promise. | ✅ | 2026-06-17 |
| TASK-008 | Update `MapLayerManager.tsx` to call `getSharedEsriBasemapSession` instead of `BasemapSession.start` directly. | ✅ | 2026-06-17 |

### Implementation Phase 3

- GOAL-003: Make MapLibre basemap initialization provider-aware without changing overlay behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-009 | Modify `apps/frontend/src/components/map/MapLayerManager.test.tsx` to add coverage that `osm` and `empty` providers never call Esri session/style APIs and still apply Akasha overlays after style readiness. | ✅ | 2026-06-17 |
| TASK-010 | Modify `apps/frontend/src/components/map/MapLayerManager.tsx` so `esri` uses Esri style loading, `osm` uses a MapLibre raster OSM style, and `empty` uses `EMPTY_MAP_STYLE`; all branches call the existing overlay application path after style readiness. | ✅ | 2026-06-17 |
| TASK-011 | Verify route-level map mounting remains unchanged by confirming `apps/frontend/src/routes/ProductRoutes.tsx` still lazy-loads map screens and no non-map preview mount is added. | ✅ | 2026-06-17 |

### Implementation Phase 4

- GOAL-004: Update environment docs and validate the frontend.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Modify `apps/frontend/.env.example` to include `VITE_BASEMAP_PROVIDER=osm` and document that `esri` requires `VITE_ESRI_API_KEY`. | ✅ | 2026-06-17 |
| TASK-013 | Modify `docs/developer-setup-guide.md` to recommend `VITE_BASEMAP_PROVIDER=osm` for local development and `esri` for staging/production validation. | ✅ | 2026-06-17 |
| TASK-014 | Run targeted frontend tests: `npx vitest run src/map/basemap.test.ts src/components/map/MapLayerManager.test.tsx`. | ✅ | 2026-06-17 |
| TASK-015 | Run frontend typecheck with `npx tsc --noEmit`. | ✅ | 2026-06-17 |

## 3. Alternatives

- **ALT-001**: Frontend-only provider override without changing `/api/config` usage. Rejected because it creates two sources of truth and makes staging/prod behavior harder to audit.
- **ALT-002**: Split `MapLayerManager` into separate Esri, OSM, and empty components. Rejected because the current manager already centralizes overlay behavior and splitting now would duplicate satellite overlay logic.
- **ALT-003**: Use `empty` as the local default. Rejected because developers still need real geographic context for drawing fields; `osm` avoids ArcGIS sessions while preserving useful map context.

## 4. Dependencies

- **DEP-001**: Existing `maplibre-gl` dependency provides raster and empty style support.
- **DEP-002**: Existing `@esri/maplibre-arcgis` dependency remains required only for the `esri` provider.
- **DEP-003**: Existing Vite environment variable mechanism exposes `VITE_*` values to frontend code.
- **DEP-004**: Existing `/api/config` endpoint provides the backend basemap provider fallback.

## 5. Files

- **FILE-001**: `apps/frontend/src/types/api.ts` extends `BasemapProvider`.
- **FILE-002**: `apps/frontend/src/vite-env.d.ts` adds `VITE_BASEMAP_PROVIDER` typing.
- **FILE-003**: `apps/frontend/src/map/basemap.ts` resolves provider-specific basemap config.
- **FILE-004**: `apps/frontend/src/map/basemap.test.ts` validates provider resolution.
- **FILE-005**: `apps/frontend/src/map/esriBasemapSession.ts` caches equivalent Esri session promises.
- **FILE-006**: `apps/frontend/src/components/map/MapLayerManager.tsx` initializes provider-specific MapLibre styles.
- **FILE-007**: `apps/frontend/src/components/map/MapLayerManager.test.tsx` validates provider-specific lifecycle and Esri session reuse.
- **FILE-008**: `apps/frontend/.env.example` documents local development provider defaults.
- **FILE-009**: `docs/developer-setup-guide.md` documents local/staging/prod basemap recommendations.

## 6. Testing

- **TEST-001**: `resolveBasemapConfig` returns an Esri config and rejects missing keys only when provider is `esri`.
- **TEST-002**: `resolveBasemapConfig` returns an OSM config when `VITE_BASEMAP_PROVIDER=osm`, even if the backend config says `esri`.
- **TEST-003**: `resolveBasemapConfig` returns an empty config when `VITE_BASEMAP_PROVIDER=empty`, without requiring `VITE_ESRI_API_KEY`.
- **TEST-004**: `MapLayerManager` starts one Esri session for equivalent Esri mounts in the same runtime.
- **TEST-005**: `MapLayerManager` does not call Esri APIs for `osm`.
- **TEST-006**: `MapLayerManager` does not call Esri APIs for `empty`.
- **TEST-007**: Akasha overlays are applied after style readiness for `esri`, `osm`, and `empty` branches.
- **TEST-008**: `npx tsc --noEmit` passes from `apps/frontend`.

## 7. Risks & Assumptions

- **RISK-001**: Public OSM tiles have usage policies and should be limited to local development; staging/prod should use `esri` unless a production-grade OSM tile provider is selected later.
- **RISK-002**: Shared Esri session reuse only reduces route-level remount churn within a browser runtime; full browser reloads can still create new sessions.
- **RISK-003**: MapLibre style readiness events differ slightly by provider; tests must ensure overlays still apply after style setup.
- **ASSUMPTION-001**: Existing lazy routes already avoid mounting map screens on non-map pages.
- **ASSUMPTION-002**: `osm` is acceptable for local developer context and `empty` is acceptable for no-network debug/testing.
- **ASSUMPTION-003**: Staging and production deployments can explicitly set `BASEMAP_PROVIDER=esri` and `VITE_BASEMAP_PROVIDER=esri`.

## 8. Related Specifications / Further Reading

- `AGENTS.md` — Akasha frontend guardrails and one-public-service rule.
- `docs/architecture-tech-stack.md` — service and frontend architecture.
- `docs/developer-setup-guide.md` — local development workflow to update with basemap provider guidance.
- `apps/frontend/src/map/basemap.ts` — existing basemap resolver seam.
- `apps/frontend/src/components/map/MapLayerManager.tsx` — existing MapLibre and overlay lifecycle seam.
