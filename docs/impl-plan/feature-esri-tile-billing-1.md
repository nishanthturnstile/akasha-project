---
goal: Esri Imagery Tile-Based Billing for Staging
version: 1.1
date_created: 2026-07-14
last_updated: 2026-07-14
owner: Akasha Engineering
tags: [feature, frontend, maps, cost-optimization, arcgis, staging, billing]
---

# Introduction

This plan updates the Akasha product application to support both ArcGIS Location Platform basemap usage models and activates the **tile usage model** for the staging environment. Akasha will continue to render the `arcgis/imagery` basemap through MapLibre GL JS and `@esri/maplibre-arcgis`; tile-based billing will be selected by passing the ArcGIS API-key access token directly to `BasemapStyle` and by not creating an ArcGIS basemap session.

The current implementation is session-only: `/api/config.basemap.usageModel` defaults to `session`, the frontend type accepts only `session`, `resolveBasemapConfig()` rejects every other value, and every Esri map mount calls `BasemapSession.start()`. The target implementation is dual-mode so staging can use `tile` while production and rollback paths retain `session`. This is an application/product change under `akasha-em-git`; the standalone `akasha-ingestion` repository is outside scope and must not be modified.

Payment-method and pay-as-you-go activation occur in the ArcGIS Location Platform portal and are external prerequisites for staging activation. Code implementation and test validation may proceed while the payment method is pending, but the tile-mode staging cutover must not occur until pay-as-you-go is shown as enabled.

## 1. Requirements & Constraints

### Current state

- **CUR-001**: Hosted builds already default `VITE_BASEMAP_PROVIDER` to `esri` and `VITE_ESRI_BASEMAP_STYLE` to `arcgis/imagery` in `.github/workflows/deploy-staging.yml` and `infra/gateway/Dockerfile`.
- **CUR-002**: `apps/frontend/src/types/api.ts` defines `BasemapUsageModel` as only `'session'`.
- **CUR-003**: `apps/frontend/src/map/basemap.ts` rejects any usage model other than `session`.
- **CUR-004**: `apps/frontend/src/components/map/MapLayerManager.tsx` always calls `getSharedEsriBasemapSession()` for the Esri provider.
- **CUR-005**: `apps/frontend/src/map/esriBasemapSession.ts` reuses one equivalent Esri session promise within a browser runtime.
- **CUR-006**: `@esri/maplibre-arcgis` version `1.3.0` already accepts either `token` or `session` in `BasemapStyle`; no dependency upgrade is required.
- **CUR-007**: `apps/api/app/routers/product_router.py::_basemap_config()` already returns the configured usage-model string and requires no behavior change.
- **CUR-008**: `infra/selfhosted/coolify-compose.yml` does not currently pass the BFF basemap environment variables, causing hosted API deployments to use code defaults.
- **CUR-009**: Map creation is isolated in a mount-only effect. Scene/date, compare scene, index image, opacity, and visibility updates do not recreate the MapLibre map or reapply the Esri basemap.
- **CUR-010**: Pitch and rotation are disabled, `places=none` is the hosted default, and the application starts maps at known AOI or field locations. These behaviors already reduce unnecessary basemap tile requests.
- **CUR-011**: The working tree contains unrelated in-progress edits to `apps/api/app/routers/product_router.py` and `apps/frontend/src/types/api.ts`; implementation must preserve and rebase around those edits rather than overwrite them.
- **CUR-012**: `EditFieldDialog` currently converts every basemap configuration error to `null` and displays an indefinite loading state, while `FieldCreatePage` and `OnboardingFieldCreate` pass no-op runtime error callbacks. Tile-mode key/referrer failures can therefore be hidden on secondary map surfaces.

### Target state

- **REQ-001**: Akasha must support exactly two Esri basemap usage models: `session` and `tile`.
- **REQ-002**: In tile mode, the frontend must construct `BasemapStyle` with `token: apiKey` and must not call `BasemapSession.start()`, `/sessions/start`, or `getSharedEsriBasemapSession()`.
- **REQ-003**: In session mode, the existing shared-session behavior, 12-hour maximum duration handling, automatic refresh, and error handling must remain unchanged.
- **REQ-004**: `/api/config.basemap.usageModel` must remain the single usage-model source of truth. Do not add a `VITE_ESRI_BASEMAP_USAGE_MODEL` override.
- **REQ-005**: Defaults in code, Compose, and example environment files must remain `session` so deploying dual-mode code alone cannot silently change production billing.
- **REQ-006**: Staging must explicitly set `ESRI_BASEMAP_USAGE_MODEL=tile` in its Coolify runtime environment only after the compatible web and API images are deployed and verified in session mode.
- **REQ-007**: `arcgis/imagery`, style family `arcgis`, and `places=none` must remain the staging defaults.
- **REQ-008**: Tile mode must use the ArcGIS Basemap Styles service. It must not migrate to the ArcGIS Static Basemap Tiles service or access underlying ArcGIS map/vector tile sources directly.
- **REQ-009**: The MapLibre ArcGIS plugin must continue managing Esri and dynamic data-provider attribution. Attribution must remain visible and unobstructed on every map surface.
- **REQ-010**: The following independent Akasha layers and interactions must remain unchanged in both usage modes: source-native satellite tiles, compare tiles, field-clipped index image overlays, field boundaries, Terra Draw, measurement, opacity, visibility, scene fitting, point lookup, and map controls.
- **REQ-011**: Changing acquisition date, source-native scene, compare date, index overlay, opacity, or visibility must not recreate `BasemapStyle`, restart an Esri session, or reload the base style.
- **REQ-012**: Local `osm` and `empty` providers must remain independent of the Esri key and must never call Esri APIs.
- **REQ-013**: All current map consumers must work without caller-specific billing logic: `MapPage`, `FieldCreatePage`, `OnboardingFieldCreate`, and `EditFieldDialog`.
- **REQ-014**: The application must fail closed with a clear `BasemapConfigurationError` for an unsupported usage model; it must not silently substitute another billing model or leave a map consumer in an indefinite loading state.
- **REQ-015**: The API process must reject an unsupported `ESRI_BASEMAP_USAGE_MODEL` during startup/configuration rather than serving an invalid public contract.
- **REQ-016**: Session-only fields (`sessionDurationSeconds` and refresh safety margin) must only be used in the resolved session variant. Tile mode must not use or emulate session duration.
- **REQ-017**: Switching staging from `tile` back to `session` must require only a Coolify runtime configuration change and API/stack redeploy after dual-mode code is installed; rebuilding the web image must not be required for billing-model rollback.
- **REQ-018**: No database migration, raster change, ingestion change, public route, or new server-side Esri proxy is permitted.
- **REQ-019**: Payment-method completion is not equivalent to PAYG activation. Staging activation requires the ArcGIS portal to explicitly show pay-as-you-go as enabled.
- **REQ-020**: PAYG activation does not select the billing model. Runtime code behavior defined in REQ-002 selects tile usage.
- **REQ-021**: Shared-session error listeners must be attached only while a session-mode `MapLayerManager` is mounted and must be removed on unmount. A session promise that resolves after unmount must not retain a stale callback.
- **REQ-022**: `MapPage`, `FieldCreatePage`, `OnboardingFieldCreate`, and `EditFieldDialog` must surface Esri runtime failures in their existing full-screen or inline map regions without exposing token values or replacing unaffected form state.

### Security requirements

- **SEC-001**: Use a public-application ArcGIS API key credential with only the Basemaps privilege (`premium:user:basemaps`) and no item access.
- **SEC-002**: Restrict the key to the exact staging origin `https://staging.gis.cidsaglobal.com`; do not use an unrestricted key or a path-specific referrer.
- **SEC-003**: Do not commit the real key. Continue injecting it through the existing `VITE_ESRI_API_KEY`/`VITE_ESRI_PUBLIC_ACCESS` build path.
- **SEC-004**: Treat the compiled key as browser-visible by design. Referrer restriction, least privilege, expiry, rotation, Akasha sign-in, and usage monitoring are the controls against abuse.
- **SEC-005**: Do not log the key, copy it into error messages, place it in source maps intentionally, or include it in screenshots/test artifacts.
- **SEC-006**: Add a staging build preflight that fails when `VITE_BASEMAP_PROVIDER=esri` and the key is empty or still a placeholder.
- **SEC-007**: Rotate with ArcGIS secondary keys: generate the secondary key, deploy and validate it, then invalidate the old key.
- **SEC-008**: The current deployment promotes the same immutable web image from staging to production. `.github/workflows/deploy-production.yml` must fail closed unless protected production variables `ESRI_WEB_IMAGE_APPROVED_SHA` and `ESRI_WEB_IMAGE_CREDENTIAL_ID` are non-empty and `ESRI_WEB_IMAGE_APPROVED_SHA` exactly equals the requested immutable `image_tag`. An authorized operator may set those variables only after confirming that the credential item identified by `ESRI_WEB_IMAGE_CREDENTIAL_ID` permits the exact production referrer. The workflow must never print the key.

### Performance and cost requirements

- **PERF-001**: Preserve the one-MapLibre-instance-per-`MapLayerManager`-mount lifecycle.
- **PERF-002**: Preserve MapLibre/browser/CDN caching; do not add cache-busting query parameters or replace plugin-managed tile URLs.
- **PERF-003**: Preserve disabled pitch/rotation and the current AOI/field-focused start center and zoom.
- **PERF-004**: Do not add global `maxBounds` in this change. A default-AOI bound can break multi-AOI, imported-field, onboarding, and edit-field workflows outside that bound.
- **PERF-005**: Do not introduce basemap prefetching, hidden map mounts, basemap selectors, or extra style loads.
- **PERF-006**: Keep `places=none` unless a separately approved product requirement enables places.
- **PERF-007**: Preserve style-layer separation: Esri remains the basemap; Akasha source-native imagery and field analytics remain independent overlays.
- **PERF-008**: Tile usage must be measured in the ArcGIS dashboard after cutover. Do not estimate production suitability from staging traffic alone.

### Constraints and patterns

- **CON-001**: Continue using React 18, TypeScript, Vite, MapLibre GL JS, and `@esri/maplibre-arcgis`.
- **CON-002**: Only the Akasha `web` gateway is public. The browser may call ArcGIS basemap services directly with the referrer-restricted public key, but must continue using same-origin Akasha routes for Akasha API and raster data.
- **CON-003**: Preserve existing public DTO field names and error presentation.
- **CON-004**: Production is not switched to tile billing by this plan.
- **CON-005**: Real payment-card data and API-key values must be entered by an authorized operator and must never be provided through chat or committed files.
- **PAT-001**: Use a TypeScript discriminated union keyed by `usageModel` to make session-only behavior statically inaccessible from the tile branch.
- **PAT-002**: Keep shared overlay application in one `applyOverlays()` path; do not duplicate overlay logic between session and tile branches.
- **PAT-003**: Keep `resolveBasemapConfig()` as the boundary between the server DTO and rendering configuration.
- **PAT-004**: Keep session caching in `esriBasemapSession.ts` for the session variant and production rollback.
- **PAT-005**: Deploy compatibility before activation: dual-mode code first with `session`, then switch only staging runtime to `tile`.

### Context map

#### Files to modify

| File | Purpose | Required change |
|------|---------|-----------------|
| `apps/frontend/src/types/api.ts` | Public frontend API DTOs | Expand `BasemapUsageModel` to `'session' | 'tile'`; preserve unrelated `revisitDays` work. |
| `apps/frontend/src/map/basemap.ts` | Server DTO to renderer config boundary | Return discriminated Esri session/tile configs; validate both modes; omit session-only resolved fields in tile mode. |
| `apps/frontend/src/map/basemap.test.ts` | Resolver contract tests | Add tile resolution, invalid mode, and session regression coverage. |
| `apps/frontend/src/map/esriBasemapSession.ts` | Shared session lifecycle | Accept only `EsriSessionBasemapResolvedConfig`; do not add tile handling. |
| `apps/frontend/src/components/map/MapLayerManager.tsx` | MapLibre and Esri style lifecycle | Branch authentication by `usageModel`; direct token for tile, shared session for session; preserve one overlay-ready path. |
| `apps/frontend/src/components/map/MapLayerManager.test.tsx` | Map lifecycle regression tests | Prove tile mode does not start a session and does not reload the basemap on overlay/state updates. |
| `apps/frontend/src/components/onboarding/OnboardingFieldCreate.tsx` | Onboarding map consumer | Surface configuration and runtime Esri failures without discarding the field draft. |
| `apps/frontend/src/components/onboarding/OnboardingFieldCreate.test.tsx` | New onboarding map test | Verify session/tile config forwarding and runtime failure presentation. |
| `apps/frontend/src/pages/monitoring/FieldCreatePage.tsx` | Field-create map consumer | Surface configuration and runtime Esri failures without discarding pending fields. |
| `apps/frontend/src/pages/monitoring/FieldCreatePage.test.tsx` | New field-create map test | Verify session/tile config forwarding and runtime failure presentation. |
| `apps/frontend/src/components/seasons/EditFieldDialog.tsx` | Edit-field mini-map consumer | Preserve typed configuration/runtime errors and render an inline failure instead of indefinite loading. |
| `apps/frontend/src/components/seasons/EditFieldDialog.test.tsx` | New edit-field mini-map test | Verify session/tile config forwarding and inline failure presentation. |
| `apps/frontend/src/pages/MapPage.test.tsx` | Primary map-consumer regression tests | Add direct Esri session/tile config forwarding and `onBasemapError` full-screen error coverage. |
| `apps/api/app/config.py` | Typed runtime settings | Validate/normalize `ESRI_BASEMAP_USAGE_MODEL` against `session` and `tile`, retaining `session` default. |
| `apps/api/tests/test_basemap_config.py` | Focused BFF basemap tests | Add default, tile, and invalid runtime configuration tests without expanding the large slice test file. |
| `apps/api/.env.example` | API environment example | Document both modes and retain safe `session` default. |
| `apps/api/app/skeleton.py` | Documented environment matrix | Document `session | tile` support while retaining `session` default. |
| `infra/selfhosted/coolify-compose.yml` | Hosted product runtime | Pass BFF basemap variables explicitly to the API service with safe defaults. |
| `infra/selfhosted/env.example` | Coolify environment template | Add the complete basemap runtime section and staging `tile` override instructions. |
| `infra/selfhosted/README.md` | Deployment runbook | Document code-first activation, PAYG gate, key restrictions, verification, monitoring, and rollback. |
| `.github/workflows/deploy-staging.yml` | Staging image build/deploy | Fail the web build preflight for missing Esri key when provider is Esri; do not add a build-time usage-model variable. |
| `.github/workflows/deploy-production.yml` | Production immutable-image promotion | Enforce the protected SHA-bound Esri web-image approval gate before image verification or Coolify patching. |
| `tests/test_deploy_workflows.py` | Deployment workflow validation | Prove staging preflight presence and reject production deployment without an exact approved SHA/credential item. |
| `docs/architecture-tech-stack.md` | Canonical architecture/API contract | Change `usageModel` documentation from session-only to dual-mode and describe environment selection. |
| `docs/developer-setup-guide.md` | Developer operations | Preserve local OSM guidance and document targeted Esri session/tile validation. |

#### Dependencies and files to inspect but not modify unless implementation reveals a defect

| File | Relationship |
|------|--------------|
| `apps/api/app/routers/product_router.py` | `_basemap_config()` already forwards the setting; avoid touching unrelated in-progress acquisition-schedule changes. |
| `apps/frontend/src/types/esri-maplibre-arcgis.d.ts` | Already declares both `token` and `session` options; no change expected. |
| `apps/frontend/src/pages/MapPage.tsx` | Primary map consumer and all overlay modes; should require no billing-specific code. |
| `apps/frontend/src/lib/satelliteLayer.ts` | Independent Akasha satellite source/layer swap logic; behavior must remain unchanged. |
| `apps/frontend/src/components/fields/FieldBoundaryLayer.tsx` | Adds field layers after map readiness; behavior must remain unchanged. |
| `infra/gateway/Dockerfile` | Existing build-time public key path; no usage-model build argument should be added. |
| `apps/frontend/package.json` and `yarn.lock` | Installed plugin already supports token mode; no dependency changes expected. |

#### Existing and new tests

| Test file | Coverage |
|-----------|----------|
| `apps/frontend/src/map/basemap.test.ts` | Config resolution, key requirement, usage-model discrimination, provider precedence. |
| `apps/frontend/src/components/map/MapLayerManager.test.tsx` | Session reuse, tile direct-token behavior, style readiness, overlays, OSM/empty isolation. |
| `apps/frontend/src/lib/satelliteLayer.test.ts` | Scene/source swapping without disturbing basemap. |
| `apps/frontend/src/pages/MapPage.test.tsx` | Primary map-page configuration and state regression. |
| `apps/frontend/src/routes/ProductRoutes.test.tsx` | Lazy route behavior and map-screen routing. |
| `apps/api/tests/test_basemap_config.py` | New focused BFF runtime/config contract coverage. |
| `apps/api/tests/test_slice2.py::test_config_endpoint_contract` | Existing default-session contract remains valid. |
| `apps/frontend/src/components/onboarding/OnboardingFieldCreate.test.tsx` | New direct onboarding map-consumer coverage. |
| `apps/frontend/src/pages/monitoring/FieldCreatePage.test.tsx` | New direct field-create map-consumer coverage. |
| `apps/frontend/src/components/seasons/EditFieldDialog.test.tsx` | New direct edit-field mini-map coverage. |
| `tests/test_deploy_workflows.py` | Existing YAML workflow harness for fail-closed staging/production deployment checks. |

### Execution dependency rules

- **EXEC-001**: Execute tasks in ascending numeric order. `TASK-001` has no dependency; every `TASK-N` for `N > 1` depends on successful completion of `TASK-(N-1)`. This global dependency applies to every task table below and intentionally serializes the migration so contract deployment, PAYG activation, and billing cutover cannot race.
- **EXEC-002**: A task may perform its internal read-only checks in parallel, but no two tasks may edit the same file concurrently.
- **EXEC-003**: Every phase completion criterion is a blocking gate for the next phase. Phase 7 cannot begin until Phase 6 is complete, and Phase 8 cannot begin until Phase 7 is complete.
- **EXEC-004**: Any failed verification task blocks all higher-numbered tasks until the root cause is fixed and the failed verification is rerun successfully.

## 2. Implementation Steps

### Implementation Phase 0

- GOAL-001: Protect existing work and establish a reproducible baseline before modifying billing behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Verify the branch is `dev-akasha-core`; stop if it is not. Record `git status --short` and preserve all unrelated changes. | | |
| TASK-002 | Inspect and preserve the current diffs in `apps/frontend/src/types/api.ts` and `apps/api/app/routers/product_router.py`. Do not reset, stash, or overwrite user changes. | | |
| TASK-003 | Run the current targeted frontend tests for `src/map/basemap.test.ts`, `src/components/map/MapLayerManager.test.tsx`, and `src/lib/satelliteLayer.test.ts`; record the baseline result. | | |
| TASK-004 | Run `python -m pytest tests/test_slice2.py::test_config_endpoint_contract -q` from `apps/api`; record the baseline result. | | |
| TASK-005 | Confirm the installed `@esri/maplibre-arcgis` `IBasemapStyleOptions` supports `token` and `session`, and confirm no package upgrade is required. | | |

**Completion criteria:** Baseline behavior is recorded, unrelated changes are preserved, and no source files have been modified before the baseline is known.

### Implementation Phase 1

- GOAL-002: Extend and validate the BFF and TypeScript billing-model contract without activating tile mode.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | In `apps/frontend/src/types/api.ts`, change `BasemapUsageModel` from `'session'` to `'session' | 'tile'`. Make no changes to unrelated source/default-layer DTO work. | | |
| TASK-007 | In `apps/api/app/config.py`, add an allowed-choice parser or equivalent startup validation that trims/lowercases `ESRI_BASEMAP_USAGE_MODEL`, accepts only `session` and `tile`, and raises a non-secret configuration error for every other value. Keep the default `session`. | | |
| TASK-008 | Add `apps/api/tests/test_basemap_config.py` with tests that instantiate settings under `session`, `tile`, mixed-case/whitespace normalization if normalization is implemented, and an invalid value. | | |
| TASK-009 | Add a BFF route contract test that temporarily sets `settings.esri_basemap_usage_model` to `tile`, calls `/api/config`, verifies `usageModel == "tile"`, and restores state through `monkeypatch`. | | |
| TASK-010 | Update `apps/api/.env.example` and `apps/api/app/skeleton.py` to document `session | tile`, retaining `session` as the example/default and retaining `ESRI_BASEMAP_SESSION_SECONDS=43200` for session mode. | | |
| TASK-011 | Run the new BFF tests plus `tests/test_slice2.py::test_config_endpoint_contract`; do not proceed until both the tile contract and default-session regression pass. | | |

**Completion criteria:** The BFF can emit a validated `tile` contract, defaults remain `session`, and no staging environment has been switched.

### Implementation Phase 2

- GOAL-003: Implement a statically separated frontend tile-authentication path while preserving the session path.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | In `apps/frontend/src/map/basemap.ts`, introduce shared Esri base fields plus `EsriSessionBasemapResolvedConfig` (`usageModel: 'session'`, duration, safety margin) and `EsriTileBasemapResolvedConfig` (`usageModel: 'tile'`, no session-only fields). Export their union as `EsriBasemapResolvedConfig`. | | |
| TASK-013 | Update `resolveBasemapConfig()` to validate `serverConfig.usageModel`, require the API key for both Esri modes, preserve style/style-family/places resolution, and return the correct discriminated variant. Unknown values must raise `BasemapConfigurationError`. | | |
| TASK-014 | In `apps/frontend/src/map/esriBasemapSession.ts`, change `sessionKeyOf()` and `getSharedEsriBasemapSession()` to accept only `EsriSessionBasemapResolvedConfig`. Preserve the current cache key and behavior. | | |
| TASK-015 | Add resolver tests proving tile mode resolves with `usageModel: 'tile'`, does not contain session-only fields, still requires the key, and rejects unsupported usage-model strings received at runtime. Preserve all provider/session tests. | | |
| TASK-016 | Run `src/map/basemap.test.ts` and TypeScript compilation before changing the map component. | | |

**Completion criteria:** TypeScript narrows tile and session configs correctly, tile configs cannot be passed to the session helper, and all resolver tests pass.

### Implementation Phase 3

- GOAL-004: Apply Esri imagery in tile mode without changing MapLibre or Akasha layer behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Refactor only the Esri initialization branch in `MapLayerManager.tsx`: build common `BasemapStyle` options (`style`, `preferences`), attach `session` and its error listener only when `usageModel === 'session'`, and attach `token: basemap.apiKey` when `usageModel === 'tile'`. | | |
| TASK-018 | Preserve the existing `BasemapStyleLoad` → `map.once('styledata', applyOverlays)` sequence and the shared `applyOverlays()` implementation for both modes. | | |
| TASK-019 | Preserve the mount-only map effect, `attributionControl: false` plugin handoff, metric scale control, disabled rotation/pitch, and all subsequent independent layer effects. Do not add `basemap` or scene state to the map-creation effect dependencies. | | |
| TASK-020 | Extend `MapLayerManager.test.tsx` with a tile config and assert: `BasemapSession.start` is never called; `BasemapStyle` receives `token` and not `session`; imagery style and `places=none` are preserved; overlays wait for style readiness. | | |
| TASK-021 | Add a tile-mode rerender regression that changes scene, compare scene, index overlay, opacity, and visibility and proves the MapLibre map and `BasemapStyle` are created once while independent Akasha layers update through their existing effects. Expand the mock host only as needed for existing source/layer calls. | | |
| TASK-022 | In the session branch, retain a stable `BasemapSessionError` handler, attach it only if the session resolves before disposal, retain the resolved session reference, and call `session.off('BasemapSessionError', handler)` during cleanup. Add tests for unmount-before-resolution, sequential mounts, no stale callback, and no active-listener growth. Preserve the existing shared-session and scene-change tests. | | |
| TASK-023 | Preserve OSM/empty isolation tests. Update `OnboardingFieldCreate`, `FieldCreatePage`, and `EditFieldDialog` to retain and display typed configuration/runtime errors in their current map regions. Update `MapPage.test.tsx` so its `MapLayerManager` mock captures the `basemap` and `onBasemapError` props instead of forcing OSM-only coverage. Add direct tests for all four consumers proving both session and tile resolved configs reach `MapLayerManager`, invoking `onBasemapError` produces the existing full-screen or new inline error state, local form/draft state remains mounted where applicable, and no caller contains billing-branch logic. | | |
| TASK-024 | Run `MapLayerManager.test.tsx`, `basemap.test.ts`, `satelliteLayer.test.ts`, `OnboardingFieldCreate.test.tsx`, `FieldCreatePage.test.tsx`, and `EditFieldDialog.test.tsx`; then run TypeScript compilation. | | |

**Completion criteria:** Tile mode produces direct-token style requests with zero session starts, all overlay/state regressions pass, and session/OSM/empty behavior remains intact.

### Implementation Phase 4

- GOAL-005: Make hosted configuration explicit and safe without changing production billing.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | Add `BASEMAP_PROVIDER`, `ESRI_BASEMAP_STYLE`, `ESRI_BASEMAP_STYLE_FAMILY`, `ESRI_BASEMAP_USAGE_MODEL`, `ESRI_BASEMAP_PLACES`, and `ESRI_BASEMAP_SESSION_SECONDS` to the `api.environment` block in `infra/selfhosted/coolify-compose.yml`. Use `session` as the Compose default. | | |
| TASK-026 | Add the same variables to `infra/selfhosted/env.example`, documenting `ESRI_BASEMAP_USAGE_MODEL=session` as the safe shared default and `tile` as the explicit staging override after compatibility deployment. | | |
| TASK-027 | Add a dedicated `validate-web-basemap-config` job to `.github/workflows/deploy-staging.yml` and make `build-images` depend on it. Map repository variable `VITE_ESRI_API_KEY` to a masked step environment value before Docker build arguments are constructed; when provider is `esri`, reject empty values and placeholder prefixes/forms (`CHANGE_ME`, `<...>`, or whitespace-only), reject empty style, and reject a style family other than `arcgis`. Never echo the value. Do not add a build argument for usage model; verify the dual-mode frontend reads it only from `/api/config`. | | |
| TASK-028 | Update `.github/workflows/deploy-production.yml` to load protected production variables `ESRI_WEB_IMAGE_APPROVED_SHA` and `ESRI_WEB_IMAGE_CREDENTIAL_ID`, fail before manifest verification unless both are non-empty and the approved SHA exactly equals `inputs.image_tag`, and keep production billing activation out of the workflow. Extend `tests/test_deploy_workflows.py` to assert staging preflight ordering, production gate ordering, exact-SHA comparison, non-empty credential item ID, and absence of key logging; include a negative fixture/assertion showing an unapproved SHA cannot satisfy the gate. | | |
| TASK-029 | Update `infra/selfhosted/README.md` with two-stage deployment, exact staging runtime values, PAYG prerequisite, key referrer requirements, browser checks, dashboard monitoring, and session rollback. | | |
| TASK-030 | Update `docs/architecture-tech-stack.md` so the basemap contract documents both `session` and `tile`, the direct-token/session-token distinction, and staging-only activation. | | |
| TASK-031 | Update `docs/developer-setup-guide.md` to retain OSM for normal local development and describe deliberate local validation for each Esri usage model without committing a key. | | |
| TASK-032 | Run `docker compose -f infra/selfhosted/coolify-compose.yml config` with safe placeholder environment values and verify the rendered API service includes all basemap variables without exposing the frontend key. | | |

**Completion criteria:** Hosted API configuration is explicit, missing-key builds fail safely, documentation matches runtime behavior, and production still defaults to sessions.

### Implementation Phase 5

- GOAL-006: Perform complete automated validation before any staging billing change.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-033 | Run focused frontend tests: `yarn test src/map/basemap.test.ts src/components/map/MapLayerManager.test.tsx src/lib/satelliteLayer.test.ts src/pages/MapPage.test.tsx src/routes/ProductRoutes.test.tsx src/components/onboarding/OnboardingFieldCreate.test.tsx src/pages/monitoring/FieldCreatePage.test.tsx src/components/seasons/EditFieldDialog.test.tsx`. | | |
| TASK-034 | Run the full frontend suite with `yarn test`. | | |
| TASK-035 | Run `yarn lint` and `yarn build` from `apps/frontend`. The build must pass both TypeScript projects and Vite. | | |
| TASK-036 | Run the new BFF basemap tests and `tests/test_slice2.py::test_config_endpoint_contract`, then run the repository-root `tests/test_deploy_workflows.py` workflow contract suite. | | |
| TASK-037 | Run the full BFF suite with `python -m pytest -q` from `apps/api`. | | |
| TASK-038 | Run `ruff check apps/api` from the repository root. | | |
| TASK-039 | Run editor diagnostics for every modified source file and resolve all introduced errors. | | |
| TASK-040 | Review the final diff for accidental changes to satellite formulas, raster routes, ingestion integration, field geometry, or unrelated in-progress schedule work. | | |

**Completion criteria:** All focused/full tests, lint, build, Compose validation, and diagnostics pass with no unrelated behavioral changes.

### Implementation Phase 6

- GOAL-007: Deploy dual-mode compatibility to staging while staging still uses session billing.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-041 | Confirm ArcGIS payment setup status separately; code deployment may continue if payment is pending, but TASK-049 must remain blocked. | | |
| TASK-042 | Create or verify the public-application ArcGIS credential has only `premium:user:basemaps`, no item access, a defined expiry/rotation owner, and exact referrer `https://staging.gis.cidsaglobal.com`. | | |
| TASK-043 | Set the repository `VITE_BASEMAP_PROVIDER=esri`, `VITE_ESRI_API_KEY`, `VITE_ESRI_BASEMAP_STYLE=arcgis/imagery`, `VITE_ESRI_BASEMAP_STYLE_FAMILY=arcgis`, and `VITE_ESRI_BASEMAP_PLACES=none` values used by the staging web build. | | |
| TASK-044 | Before building, classify the key as staging-only or staging-plus-production. If it is staging-only, leave production `ESRI_WEB_IMAGE_APPROVED_SHA` unset so the workflow-enforced SEC-008 gate blocks promotion. If it includes an approved exact production referrer, an authorized operator must record the credential item ID and approved immutable SHA in the protected production variables before promotion. | | |
| TASK-045 | Keep Coolify staging `ESRI_BASEMAP_USAGE_MODEL=session`, deploy the new immutable web/API SHA, and verify both containers report the same expected image revision and healthy status. | | |
| TASK-046 | Verify authenticated `/api/config` reports `provider=esri`, `style=arcgis/imagery`, and `usageModel=session`. | | |
| TASK-047 | Smoke all map consumers in session mode: primary field analytics map, field creation, onboarding field creation, and edit-field mini-map. Verify source/date changes, field-clipped overlay, compare mode, field boundary, drawing, opacity, visibility, and attribution. | | |
| TASK-048 | In browser network tools, verify the compatibility deployment still creates a session and no functional regression exists before changing billing mode. | | |

**Completion criteria:** The dual-mode build is proven in the existing session configuration on staging, all map surfaces work, and rollback code is known-good.

### Implementation Phase 7

- GOAL-008: Activate tile billing in staging and prove the effective usage model end to end.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-049 | Confirm the ArcGIS Billing page explicitly shows pay-as-you-go enabled. Do not activate tile mode while payment/PAYG remains pending or disabled. | | |
| TASK-050 | Set only the staging Coolify runtime variable `ESRI_BASEMAP_USAGE_MODEL=tile` and redeploy the product stack/API using the already validated dual-mode SHA. Leave production configuration unchanged. | | |
| TASK-051 | Verify authenticated `/api/config` reports `usageModel=tile` and all other basemap fields remain correct. | | |
| TASK-052 | Hard-refresh staging to eliminate an old browser bundle/config cache before acceptance testing. Notify active staging testers to refresh; an old session-only bundle cannot interpret the new contract. | | |
| TASK-053 | Open the primary field analytics map and verify the browser sends a direct-token Basemap Styles request and sends no request whose path contains `/sessions/start`. Do not capture or publish the token value. | | |
| TASK-054 | Verify imagery tiles return successfully, no 401/403/referrer errors occur, and the console has no Esri, MapLibre, style, glyph, sprite, or attribution errors. | | |
| TASK-055 | Repeat the complete map-consumer smoke from TASK-047 in tile mode, including a Sentinel-2 field-clipped index overlay and a ResourceSat/native scene path. | | |
| TASK-056 | Verify `Powered by Esri` and dynamic imagery-provider attribution are visible, accessible, and not covered by Akasha controls at desktop and narrow viewport sizes. | | |
| TASK-057 | Verify the staging key fails from a non-allowed origin using an approved non-secret test method; do not paste the key into tickets, chat, or command history. | | |
| TASK-058 | After the prior UTC usage day is complete and the ArcGIS dashboard has updated, verify both views: (a) `Usage > Developer credentials` shows Basemap tiles increasing for the staging credential with no new sessions in the tile-mode window, and (b) `Usage > All services` plus the Billing summary show account-wide Basemap tile/session totals and remaining free-tier context. | | |
| TASK-059 | Download/store the first approved usage CSV in the operations-controlled evidence location, not the Git repository, and record the cutover date, deployed SHA, credential item ID, and usage model without recording the key. | | |

**Completion criteria:** Runtime/API/browser behavior proves tile mode, sessions are absent, all map surfaces and layers pass, attribution is compliant, and ArcGIS usage reporting records basemap tiles.

### Implementation Phase 8

- GOAL-009: Establish cost monitoring, rollback thresholds, and production isolation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-060 | Assign the Akasha deployment owner to review both account-wide Basemap usage and the staging credential after the completed UTC day for the first seven days, then weekly for the remainder of the first billing cycle. Record each review date, account total, credential total, trend, and action in the operations-controlled evidence location outside Git. | | |
| TASK-061 | Reconfirm current pricing/free-tier values from the official pricing page at activation time, then apply account-wide thresholds: at 50% investigate and record the trend/source; at 75% freeze nonessential staging map testing; at 90% set staging back to `session` unless an authorized billing owner records explicit approval to continue. Credential-level thresholds are diagnostic and do not replace account-wide thresholds. | | |
| TASK-062 | Treat unexpected daily spikes, referrer failures, attribution failures, or any `/sessions/start` request as rollout incidents. Investigate before continuing validation traffic. | | |
| TASK-063 | If functional or cost acceptance fails, set staging `ESRI_BASEMAP_USAGE_MODEL=session`, redeploy the API/stack, hard-refresh, verify `/api/config`, and verify session-mode map smoke. No database rollback is required. | | |
| TASK-064 | If key abuse is suspected, generate/deploy a secondary key with the same least privilege/referrer settings, validate it, then invalidate the compromised key. | | |
| TASK-065 | Keep production `ESRI_BASEMAP_USAGE_MODEL=session`. Do not promote a staging-only-key web image or switch production to tile as part of this plan. | | |
| TASK-066 | After the first complete staging billing cycle, compare measured tiles per active staging map visit and total cost against session usage. Create a separate production decision plan using measured data before any production billing-model change. | | |

**Completion criteria:** Staging has an owned monitoring process, an immediate functional rollback, a key-compromise response, and no implicit production cutover.

## 3. Alternatives

- **ALT-001**: Replace `@esri/maplibre-arcgis` with a hand-built style URL containing the API key. Rejected because the installed plugin already implements direct-token tile mode, style rewriting, errors, and compliant dynamic attribution.
- **ALT-002**: Switch to the ArcGIS Static Basemap Tiles service. Rejected because Akasha is a modern WebGL client, `arcgis/imagery` is already supported by the Basemap Styles service, and the requested billing change does not require a service migration.
- **ALT-003**: Remove session support entirely. Rejected because production currently depends on session behavior and a runtime session rollback is the safest recovery path.
- **ALT-004**: Add `VITE_ESRI_BASEMAP_USAGE_MODEL`. Rejected because it would create a second source of truth, require a web rebuild for rollback, and permit the BFF and browser to report/use different billing models.
- **ALT-005**: Proxy ArcGIS styles and tiles through the Akasha BFF. Rejected because the public browser API key is designed for client use, while proxying adds bandwidth, cache, token, attribution, latency, and abuse-control responsibilities without improving the requested behavior.
- **ALT-006**: Add global AOI `maxBounds` as part of tile optimization. Rejected because Akasha supports multiple AOIs, imported fields, and field editing; a default bound can make valid fields unreachable. This requires a separate product decision and contract.
- **ALT-007**: Reuse one MapLibre instance globally across all routes/dialogs. Rejected because it is a high-risk architecture change that can break Terra Draw, controls, lifecycle cleanup, and independent mini-map behavior. The current one-instance-per-mounted-map pattern is retained.
- **ALT-008**: Upgrade MapLibre or `@esri/maplibre-arcgis` during this migration. Rejected because version `1.3.0` already supports direct tokens; combining a dependency upgrade with a billing cutover adds unrelated risk.
- **ALT-009**: Use an OSM/public raster service for staging. Rejected because the requested staging basemap is Esri satellite imagery and public OSM raster servers are not a production/staging substitute.
- **ALT-010**: Put the Esri key in the API `/api/config` response to support per-environment immutable promotion. Rejected for this scope because it changes the established key-delivery architecture. The immutable-image/referrer conflict is handled by SEC-008 and a production promotion block.

## 4. Dependencies

- **DEP-001**: `@esri/maplibre-arcgis@1.3.0` direct-token and session support.
- **DEP-002**: `maplibre-gl@5.24.0` style/source/layer lifecycle and browser tile caching.
- **DEP-003**: ArcGIS Location Platform account with payment method and PAYG explicitly enabled before Phase 7.
- **DEP-004**: ArcGIS public-application API key with `premium:user:basemaps`, exact referrer, expiry owner, and rotation procedure.
- **DEP-005**: GitHub repository variables used by `.github/workflows/deploy-staging.yml` for the public frontend key and Esri style settings.
- **DEP-006**: Coolify staging runtime configuration for `ESRI_BASEMAP_USAGE_MODEL=tile`.
- **DEP-007**: Existing `/api/config` TanStack Query path, which provides the runtime usage model to every map consumer.
- **DEP-008**: Existing same-SHA staging web/API deployment verification and rollback workflow.
- **DEP-009**: Browser developer tools or approved browser automation for runtime request and attribution validation.
- **DEP-010**: ArcGIS Location Platform Usage dashboard/CSV reporting for post-cutover billing verification.
- **DEP-011**: No database, PostGIS, MinIO, TiTiler, STAC, or ingestion dependency change.

## 5. Files

- **FILE-001**: `docs/impl-plan/feature-esri-tile-billing-1.md` — this implementation and operational rollout plan.
- **FILE-002**: `apps/frontend/src/types/api.ts` — dual-mode public DTO type.
- **FILE-003**: `apps/frontend/src/map/basemap.ts` — discriminated resolved config and usage-model validation.
- **FILE-004**: `apps/frontend/src/map/basemap.test.ts` — resolver tests.
- **FILE-005**: `apps/frontend/src/map/esriBasemapSession.ts` — session-only helper typing.
- **FILE-006**: `apps/frontend/src/components/map/MapLayerManager.tsx` — direct-token tile branch and preserved session branch.
- **FILE-007**: `apps/frontend/src/components/map/MapLayerManager.test.tsx` — billing/layer lifecycle regression tests.
- **FILE-008**: `apps/frontend/src/components/onboarding/OnboardingFieldCreate.tsx` — onboarding basemap error presentation.
- **FILE-009**: `apps/frontend/src/components/onboarding/OnboardingFieldCreate.test.tsx` — onboarding map-consumer regression tests.
- **FILE-010**: `apps/frontend/src/pages/monitoring/FieldCreatePage.tsx` — field-create basemap error presentation.
- **FILE-011**: `apps/frontend/src/pages/monitoring/FieldCreatePage.test.tsx` — field-create map-consumer regression tests.
- **FILE-012**: `apps/frontend/src/components/seasons/EditFieldDialog.tsx` — edit-field mini-map error preservation/presentation.
- **FILE-013**: `apps/frontend/src/components/seasons/EditFieldDialog.test.tsx` — edit-field map-consumer regression tests.
- **FILE-014**: `apps/api/app/config.py` — validated runtime usage model.
- **FILE-015**: `apps/api/tests/test_basemap_config.py` — focused BFF configuration tests.
- **FILE-016**: `apps/api/.env.example` — API configuration examples.
- **FILE-017**: `apps/api/app/skeleton.py` — canonical environment matrix documentation.
- **FILE-018**: `infra/selfhosted/coolify-compose.yml` — explicit API basemap runtime variables.
- **FILE-019**: `infra/selfhosted/env.example` — Coolify basemap runtime template.
- **FILE-020**: `infra/selfhosted/README.md` — staging activation, acceptance, monitoring, and rollback runbook.
- **FILE-021**: `.github/workflows/deploy-staging.yml` — Esri web-build preflight.
- **FILE-022**: `.github/workflows/deploy-production.yml` — protected exact-SHA Esri web-image promotion gate.
- **FILE-023**: `tests/test_deploy_workflows.py` — staging and production workflow gate tests.
- **FILE-024**: `docs/architecture-tech-stack.md` — dual-mode architecture and API contract.
- **FILE-025**: `docs/developer-setup-guide.md` — local and hosted validation guidance.
- **FILE-026**: `apps/frontend/src/pages/MapPage.test.tsx` — primary map session/tile config forwarding and runtime-error tests.

## 6. Testing

- **TEST-001**: Default BFF configuration remains `usageModel=session`.
- **TEST-002**: BFF configuration accepts and reports `usageModel=tile`.
- **TEST-003**: Invalid BFF usage model fails during settings construction/startup with no secret values in the error.
- **TEST-004**: `resolveBasemapConfig()` returns a session discriminant with duration/safety fields.
- **TEST-005**: `resolveBasemapConfig()` returns a tile discriminant without duration/safety fields.
- **TEST-006**: Both Esri variants require a non-placeholder API key.
- **TEST-007**: Unsupported runtime usage values produce `BasemapConfigurationError`.
- **TEST-008**: Tile mode passes `token` and never `session` to `BasemapStyle`.
- **TEST-009**: Tile mode never invokes `BasemapSession.start()` or the shared session helper.
- **TEST-010**: Session mode continues reusing one equivalent session promise and attaches session error handling.
- **TEST-010A**: Session error listeners are removed on unmount, are not attached after disposal, and do not accumulate across sequential mounts.
- **TEST-011**: Tile and session modes use the same `arcgis/imagery`, `places=none`, style-load, and attribution paths.
- **TEST-012**: Scene/date changes do not recreate the basemap style in tile or session mode.
- **TEST-013**: Compare layer changes do not recreate the basemap style.
- **TEST-014**: Field-clipped index image changes do not recreate the basemap style.
- **TEST-015**: Opacity/visibility changes update only Akasha layer paint/visibility.
- **TEST-016**: OSM/empty providers never call Esri APIs.
- **TEST-017**: Direct render tests prove `MapPage`, `FieldCreatePage`, `OnboardingFieldCreate`, and `EditFieldDialog` accept session and tile configs and visibly report runtime/configuration failures without losing local form/draft state.
- **TEST-018**: Full frontend unit suite, lint, and production build pass.
- **TEST-019**: Full BFF unit suite and Ruff pass.
- **TEST-020**: Rendered self-hosted Compose includes validated API basemap environment variables and no frontend API key in the API environment.
- **TEST-020A**: Staging workflow cannot build Esri mode with an empty/placeholder public key, and production workflow cannot deploy a SHA that does not exactly match `ESRI_WEB_IMAGE_APPROVED_SHA` or lacks `ESRI_WEB_IMAGE_CREDENTIAL_ID`.
- **TEST-021**: Staging session compatibility smoke passes before activation.
- **TEST-022**: Staging tile smoke observes no `/sessions/start` request.
- **TEST-023**: Esri/data attribution is visible on desktop and narrow staging viewports.
- **TEST-024**: Staging tile mode preserves Source-native, Sentinel-2 clipped overlay, compare, field boundary, drawing/editing, opacity, visibility, and map controls.
- **TEST-025**: ArcGIS dashboard records tile usage and no new session usage for the tile test window.
- **TEST-026**: Runtime rollback to session restores the previously validated session path without a web rebuild.

### Acceptance commands

Run from the repository root unless a task states otherwise:

1. `cd apps/frontend && yarn test`
2. `cd apps/frontend && yarn lint`
3. `cd apps/frontend && yarn build`
4. `cd apps/api && python -m pytest -q`
5. `ruff check apps/api`
6. `python -m pytest tests/test_deploy_workflows.py -q`
7. Render and validate `infra/selfhosted/coolify-compose.yml` with non-secret placeholder values.

### Staging acceptance evidence

- Deployed immutable Git SHA for both `web` and `api`.
- Redacted `/api/config.basemap` showing `provider=esri`, `style=arcgis/imagery`, and `usageModel=tile`.
- Browser network review confirming no `/sessions/start` request; evidence must not reveal the token.
- Browser/automation screenshots showing imagery plus unobstructed attribution on primary and mini-map surfaces.
- Functional smoke results for Akasha source-native and field-clipped overlays.
- ArcGIS usage report/CSV retained outside Git, with credential item ID but without the key.

## 7. Risks & Assumptions

### Risk matrix

| ID | Risk / breakage scenario | Likelihood | Impact | Affected area | Prevention / mitigation | Detection and recovery |
|----|--------------------------|------------|--------|---------------|-------------------------|------------------------|
| RISK-001 | New API emits `tile` while an old session-only frontend is loaded, causing a full-screen configuration error. | Medium | High | All map screens | Deploy dual-mode web/API with `session` first; switch runtime only after compatibility smoke; notify testers to hard-refresh. | `/api/config` and browser error; rollback to `session`, then refresh. |
| RISK-002 | Tile branch accidentally starts a basemap session, causing session charges instead of tile usage. | Low | High | Billing and map startup | Discriminated union; session helper accepts only session config; explicit negative unit assertion. | Browser network path and ArcGIS session usage; fix code and return to `session` until redeployed. |
| RISK-003 | API key referrer or privilege is incorrect, returning 401/403 and blank maps. | Medium | High | Every Esri map | Exact HTTPS staging origin; only Basemaps privilege; preflight and session compatibility smoke. | Browser network/console; correct credential, rebuild web image, or temporarily use validated session key. |
| RISK-004 | API key is abused and drives PAYG charges. | Medium | High | Account billing | Least privilege, exact referrer, expiry, rotation, authenticated Akasha access, daily initial monitoring. | Unexpected dashboard spike; rotate key and investigate origin/referrer traffic. |
| RISK-005 | Esri or imagery-provider attribution disappears or is obscured. | Low | High | Legal/compliance and all maps | Preserve plugin attribution path; do not replace style loading; viewport acceptance checks. | Visual/browser automation smoke; block rollout or rollback to session until fixed. |
| RISK-006 | Esri style readiness timing changes and Akasha overlays are applied before the style exists. | Medium | High | Satellite, compare, index, field layers | Preserve `BasemapStyleLoad` and one-time `styledata` gate with one shared `applyOverlays()`. | Unit tests and blank/missing overlay smoke; rollback and fix lifecycle ordering. |
| RISK-007 | Date/source/opacity state causes repeated base-style loads and excessive tile use. | Medium | Medium | Cost/performance | Preserve mount-only effect and independent layer effects; add rerender creation-count tests. | Mock counts/browser network; fix dependencies before cutover. |
| RISK-008 | Session rollback breaks because session-specific fields were removed globally. | Low | High | Production and staging rollback | Use discriminated variants; retain duration/safety parsing and shared session helper/tests. | Session compatibility Phase 6; rollback code before tile activation. |
| RISK-009 | Production silently changes to tile billing. | Low | High | Production cost model | Keep code/Compose/env defaults `session`; staging runtime override only; no production task. | Production `/api/config` release gate; set production back to `session`. |
| RISK-010 | A staging-only API key is promoted in the immutable web image to production and fails its referrer. | Medium | High | Future production deployment | Workflow-enforced SEC-008 gate requires an exact protected approved SHA plus credential item ID; approve the exact production referrer before setting those values. | Production workflow fails before image verification/Coolify patch; leave approval unset and build an approved artifact. |
| RISK-011 | Broad map optimization such as `maxBounds` blocks legitimate fields or future AOIs. | Medium | High | Drawing/editing/multi-AOI | Exclude bounds changes from this scope; retain current start centers and zoom. | Field workflow smoke; revert any unapproved constraints. |
| RISK-012 | OSM/empty local development begins requiring an Esri key. | Low | Medium | Developer workflow/tests | Keep provider branch before Esri validation and preserve negative tests. | Resolver and MapLayerManager tests; restore provider isolation. |
| RISK-013 | Tile model is confused with Static Basemap Tiles and changes visual quality/style behavior. | Low | High | Basemap rendering | Use existing Basemap Styles service/plugin with direct token; explicitly reject service migration. | URL/style review and visual smoke; revert service endpoint change. |
| RISK-014 | Dynamic imagery attribution changes over time but Akasha displays a copied static string. | Low | High | Compliance | Continue plugin-managed dynamic attribution; do not hard-code provider list. | Visual comparison/service metadata; restore plugin attribution. |
| RISK-015 | Tile use exceeds expectations because PAYG has no assumed hard application cap or another credential consumes the shared account free tier. | Medium | Medium | Staging cost | Monitor account-wide and staging-credential usage; enforce 50/75/90% actions; no hidden maps/prefetch; session rollback. | ArcGIS All services, Billing summary, credential dashboard/CSV; switch to session through the approved rollback. |
| RISK-016 | Existing unrelated edits are lost or conflicted during implementation. | Medium | High | Current feature work | Diff overlapping files before edits; use small patches; never reset/stash user work without approval. | Final diff review and tests; recover from Git only with user approval. |
| RISK-017 | The public key leaks through logs or test output beyond normal browser visibility. | Low | High | Security/billing | Never print key; use placeholders in tests; redact network evidence. | Secret scan/diff review; rotate immediately if exposed. |
| RISK-018 | PAYG remains pending/disabled when tile mode is activated, causing service interruption after free-tier exhaustion. | Medium | High | Staging availability | Hard Phase 7 gate requiring portal status `enabled`. | Billing page and service errors; return to session/OSM only as approved and complete PAYG. |
| RISK-019 | Browser cache makes operators think tile mode is active while an old bundle still runs. | Medium | Medium | Acceptance accuracy | Same-SHA verification, hard refresh, inspect `/api/config` and actual network paths. | Network behavior mismatch; clear cache/reload and repeat tests. |
| RISK-020 | Existing map consumers swallow basemap errors differently, masking failures in mini-maps. | Medium | Medium | Onboarding/edit-field maps | Preserve typed errors, add visible full-screen/inline states, and direct-test every map consumer without duplicating billing logic. | Consumer tests and smoke; return to session if a secondary map surface cannot report failure safely. |
| RISK-021 | Prices/free tiers change after this plan date. | Medium | Medium | Cost decision | Treat official pricing as runtime operational input; reconfirm at activation and each production decision. | Pricing-page review; adjust thresholds/decision plan. |
| RISK-022 | Esri usage data is delayed, leading to premature acceptance. | High | Low | Billing verification | Allow documented reporting delay and review the next completed UTC usage day. | Dashboard/CSV after delay; keep acceptance pending until recorded. |
| RISK-023 | Shared session error callbacks accumulate across map-route/dialog mounts and invoke disposed components. | Medium | Medium | Session rollback/production maps | Attach only after pre-disposal resolution, retain a stable handler, unregister with `off()` on cleanup, and test sequential mounts. | Listener-count tests and duplicate-error logs; fix cleanup before compatibility deployment. |

### Assumptions

- **ASSUMPTION-001**: The ArcGIS Location Platform payment method is currently pending and will be completed by an authorized account operator.
- **ASSUMPTION-002**: The staging public origin remains `https://staging.gis.cidsaglobal.com` during rollout.
- **ASSUMPTION-003**: The installed MapLibre ArcGIS plugin behavior reviewed on 2026-07-14 remains pinned by the lockfile during implementation.
- **ASSUMPTION-004**: `arcgis/imagery` remains an available ArcGIS Basemap Styles service identifier.
- **ASSUMPTION-005**: ArcGIS API keys are expected to be browser-visible and protected by scope/referrer controls.
- **ASSUMPTION-006**: Staging traffic is focused and materially below production traffic; production suitability will use measured data, not this assumption.
- **ASSUMPTION-007**: Existing TanStack Query config caching does not mutate `usageModel` during a map mount. A runtime model change is applied through deployment and page refresh, not hot switching an existing map.
- **ASSUMPTION-008**: No schema/data migration is required and rollback is configuration-only after dual-mode code is deployed.

## 8. Related Specifications / Further Reading

- [ArcGIS Location Platform pricing](https://location.arcgis.com/pricing/)
- [ArcGIS Location Platform billing and PAYG](https://location.arcgis.com/help/billing/)
- [ArcGIS basemap tile and session usage models](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/basemap-usage-styles/)
- [ArcGIS Basemap Styles service](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/introduction-basemap-styles-service/)
- [ArcGIS Basemap styles and imagery identifiers](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/arcgis-styles/)
- [ArcGIS basemap service best practices](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/types-of-basemap-services/#best-practices)
- [ArcGIS API key creation](https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/tutorials/create-an-api-key/)
- [ArcGIS API key credentials, referrers, rotation, and usage](https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/api-key-credentials/)
- [ArcGIS security best practices](https://developers.arcgis.com/documentation/security-and-authentication/security-best-practices/)
- [Esri and data attribution](https://developers.arcgis.com/documentation/esri-and-data-attribution/)
- [ArcGIS Location Platform usage monitoring](https://location.arcgis.com/help/usage/)
- `AGENTS.md`
- `docs/architecture-tech-stack.md`
- `docs/developer-setup-guide.md`
- `docs/impl-plan/archive/feature-basemap-provider-session-reuse-1.md`
- `infra/selfhosted/README.md`
- `apps/frontend/src/map/basemap.ts`
- `apps/frontend/src/components/map/MapLayerManager.tsx`
