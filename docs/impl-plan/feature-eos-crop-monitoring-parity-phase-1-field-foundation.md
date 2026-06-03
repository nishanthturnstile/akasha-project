---
goal: EOS Crop Monitoring Parity Phase 1 Field Foundation Plan
version: 1.0
date_created: 2026-06-03
last_updated: 2026-06-03
owner: Akasha Engineering
tags: feature, eos, crop-monitoring, field-management, plots, frontend, fastapi, postgis, terra-draw, tanstack-query
---

# Introduction

This document is the standalone execution plan for Phase 1 of
`docs/impl-plan/feature-eos-crop-monitoring-parity-1.md`.

Phase 1 goal: make field creation and selection real by wiring the existing plot API into the
canonical frontend and extending field metadata/provider-link storage without duplicating geometry.

Phase 0 is complete. The product decisions already locked for the first demo are:

- First demo includes Monitoring, Analytics, Weather, VRA, and export.
- UI and product branding use Akasha branding, not EOS branding.
- EOS access is server-side only; the operator places `EOS_API_KEY` in ignored `.env` or deployment
  secrets.
- Better Auth username/password authentication is deferred to Phase 12 and is not a blocker for
  Phase 1.

## 1. Planning scope

Phase 1 covers `TASK-005` through `TASK-016` in the main implementation plan:

| Task | Scope |
|------|-------|
| `TASK-005` | Add frontend plot/field DTOs in `apps/frontend/src/types/api.ts`. |
| `TASK-006` | Add plot CRUD/import/export API client functions and method/body support in `apps/frontend/src/lib/api.ts`. |
| `TASK-007` | Add TanStack Query plot keys, queries, and mutations in `apps/frontend/src/lib/queries.ts`. |
| `TASK-008` | Replace disabled `PlotToolbar` placeholder controls with real field actions. |
| `TASK-009` | Add Terra Draw polygon creation/editing workflow. |
| `TASK-010` | Add selected-field client state to `mapViewContext.tsx`. |
| `TASK-011` | Create `AllFieldsPanel`. |
| `TASK-012` | Render selected field geometry on MapLibre. |
| `TASK-013` | Add database migration for field metadata/provider links. |
| `TASK-014` | Extend backend plot DTOs and repository read/write paths. |
| `TASK-015` | Add backend metadata tests. |
| `TASK-016` | Add frontend API/query/field UI tests. |

## 2. Source documents and inspected code

Use these docs as source of truth:

- `docs/impl-plan/feature-eos-crop-monitoring-parity-1.md`
- `docs/eos-parity-acceptance-matrix.md`
- `docs/eos-crop-monitoring-replication-research.md`
- `docs/architecture-tech-stack.md`
- `docs/engineering-dos-donts.md`
- `docs/data-ingestion-and-satellite-rules.md`

Inspected implementation surfaces:

| Area | Files |
|------|-------|
| Backend plot API | `apps/api/app/plots.py`, `apps/api/app/plots_repo.py` |
| Backend migrations | `apps/api/migrations/001_app_schema.sql`, `apps/api/migrations/002_plots_polygon_multipolygon.sql` |
| Backend tests | `apps/api/tests/test_slice3.py` |
| Frontend toolbar | `apps/frontend/src/components/scaffold/PlotToolbar.tsx` |
| Frontend API/query/types | `apps/frontend/src/lib/api.ts`, `apps/frontend/src/lib/queries.ts`, `apps/frontend/src/types/api.ts` |
| Frontend map state/page | `apps/frontend/src/state/mapViewContext.tsx`, `apps/frontend/src/pages/MapPage.tsx` |
| Frontend map layer manager | `apps/frontend/src/components/map/MapLayerManager.tsx` |
| Existing draw pattern | `apps/frontend/src/components/map/MeasureTool.tsx` |
| Frontend dependencies | `apps/frontend/package.json` |

## 3. Existing implementation inventory

### 3.1 Backend inventory

`apps/api/app/plots.py` already provides the field-shaped backend surface under plot terminology:

- `GET /api/plots`
- `POST /api/plots`
- `GET /api/plots/{plot_id}`
- `PATCH /api/plots/{plot_id}`
- `DELETE /api/plots/{plot_id}`
- `POST /api/plots/import/geojson`
- `GET /api/plots/export.geojson`
- `GET /api/plots/{plot_id}/export.geojson`

Existing DTOs:

- `PlotCreate`
- `PlotUpdate`
- `PlotResponse`
- `RejectedFeature`
- `ImportResponse`

Existing backend behavior to preserve:

- Server validates `Polygon` and `MultiPolygon` geometries.
- Server computes area; client-provided area is not trusted.
- Blocking database work runs off the event loop.
- PostGIS/backend failures are returned as sanitized API errors.
- Standard BFF error shape is preserved: `{ "error": { "code", "message", "details" } }`.

`apps/api/app/plots_repo.py` is the single persistence boundary for saved plots:

- Current shared projection: `id`, `name`, `geometry`, `area_ha`, `created_at`, `updated_at`.
- Current normalized response keys: `id`, `name`, `geometry`, `areaHa`, `createdAt`, `updatedAt`.
- Current repository functions: `list_plots`, `get_plot`, `create_plot`, `update_plot`,
  `delete_plot`, `create_plots_bulk`.

Current schema:

- `akasha.plots.id`
- `akasha.plots.name`
- `akasha.plots.geometry`
- `akasha.plots.area_ha`
- `akasha.plots.created_at`
- `akasha.plots.updated_at`

Important migration convention:

- Migrations are split by `--;;`.
- Idempotent DDL is expected.
- Existing migrations use patterns such as `DROP CONSTRAINT IF EXISTS` before adding constraints and
  `CREATE INDEX IF NOT EXISTS`.

Existing backend tests:

- `apps/api/tests/test_slice3.py` already covers CRUD, import/export, geometry validation, standard
  errors, and secret-leak regression behavior through an in-memory fake store.

### 3.2 Frontend inventory

`apps/frontend/src/types/api.ts` currently has typed BFF DTOs for config, sources, dates, default
layer, and API errors. It has no plot/field DTOs.

`apps/frontend/src/lib/api.ts` currently has:

- `ApiError`
- JSON GET-only `request<T>(path)`
- `getConfig`
- `getSources`
- `getDates`
- `getDefaultLayer`
- `composeTileTemplate`

It needs method/body support, `204 No Content` handling, and GeoJSON export handling.

`apps/frontend/src/lib/queries.ts` currently has:

- `queryKeys.config`
- `queryKeys.sources`
- `queryKeys.dates(sourceId)`
- `queryKeys.defaultLayer`
- `useConfig`
- `useSources`
- `useDates`
- `useDefaultLayer`

It needs plot/field query and mutation hooks.

`apps/frontend/src/state/mapViewContext.tsx` currently owns map UI state:

- active source
- selected date
- display mode
- opacity
- visibility
- layer panel state
- compare mode state

It needs selected-field state.

`apps/frontend/src/pages/MapPage.tsx` currently:

- loads config/sources/default layer/date queries,
- owns the MapLibre map instance from `MapLayerManager`,
- mounts `PlotToolbar`,
- mounts `MeasureTool`,
- mounts layer, timeline, compare, legend, and map controls.

`apps/frontend/src/components/scaffold/PlotToolbar.tsx` is a disabled placeholder. It must be
replaced with real field actions.

`apps/frontend/src/components/map/MapLayerManager.tsx` owns MapLibre lifecycle and satellite raster
layer swapping. It is the correct boundary for, or host near, selected field geometry rendering.

`apps/frontend/src/components/map/MeasureTool.tsx` already uses Terra Draw through dynamic imports:

- `terra-draw`
- `terra-draw-maplibre-gl-adapter`

Those dependencies are already present in `apps/frontend/package.json`. Phase 1 must reuse this
approved draw stack and must not add Mapbox Draw.

## 4. Terminology decision

Keep internal backend and existing API terminology as `plot` for Phase 1, while using `field` in
user-facing UI copy and component labels.

Rationale:

- The existing `/api/plots` backend already satisfies the core field geometry contract.
- Renaming backend routes/models would add churn and risk without improving the first demo.
- EOS parity is field-centric, so the UI should present "Field" to users.
- A small frontend mapping boundary is cheaper and safer than a backend domain rename.

## 5. Reuse, replace, and remove

### 5.1 Reuse

- Reuse `/api/plots` CRUD/import/export for field management.
- Reuse `akasha.plots.geometry` and `akasha.plots.area_ha` as the only geometry and area storage.
- Reuse `plots_repo.py` as the only plot/field persistence layer.
- Reuse server-side geometry validation and area computation.
- Reuse same-origin `/api/*` browser calls.
- Reuse `ApiError` and sanitized error parsing in the frontend API client.
- Reuse TanStack Query patterns already established in `lib/queries.ts`.
- Reuse `MapViewProvider` for client-only selected-field state.
- Reuse MapLibre and `MapLayerManager` for field boundary display.
- Reuse Terra Draw dynamic imports from `MeasureTool`.

### 5.2 Replace

- Replace disabled `PlotToolbar` placeholder controls with real field actions:
  - draw,
  - edit,
  - import GeoJSON,
  - export GeoJSON,
  - delete selected field.
- Replace placeholder tooltip/copy that says plot tools arrive later.
- Add a real fields list/search/selection surface with `AllFieldsPanel`.
- Add selected field geometry overlay rather than baking field geometry into satellite tile logic.

### 5.3 Avoid

- Do not rename backend routes/models from plot to field in Phase 1.
- Do not create a second field geometry table.
- Do not store EOS/provider geometry copies in Phase 1.
- Do not expose `EOS_API_KEY`, provider internals, signed URLs, MinIO/STAC/TiTiler paths, raw SQL,
  stack traces, or private hostnames to the browser.
- Do not hard-code EOS-specific assumptions into frontend DTOs or state.
- Do not use `window.prompt` for field naming; use a testable inline or modal form.
- Do not change the default map layer away from true-colour imagery.

## 6. Data model change plan

Create:

`apps/api/migrations/003_field_metadata_provider_links.sql`

Preferred strategy: add nullable metadata/provider-link columns directly to `akasha.plots`.

Reason:

- Geometry is already stored exactly once in `akasha.plots.geometry`.
- Field metadata is one-to-one with the Akasha field/plot row for Phase 1.
- A separate metadata table adds joins and drift risk without solving a current requirement.

### 6.1 Columns

User-editable field metadata:

| Column | Type | Notes |
|--------|------|-------|
| `group_name` | `text` | Optional field group/farm grouping label. |
| `crop_type` | `text` | Optional crop type. |
| `variety` | `text` | Optional crop variety. |
| `season_label` | `text` | Optional season/campaign label. |
| `sowing_date` | `date` | Optional sowing date. |
| `planting_date` | `date` | Optional planting/transplanting date. |
| `status` | `text` | Optional lifecycle status. |

Provider/adapter-owned links:

| Column | Type | Notes |
|--------|------|-------|
| `external_provider` | `text` | Example future value: `eos`; not exposed as a secret. |
| `external_field_id` | `text` | Provider field ID; must not replace Akasha plot ID. |
| `provider_sync_status` | `text` | Generic sync state for provider mirror status. |
| `provider_synced_at` | `timestamptz` | Last successful provider sync timestamp. |
| `provider_metadata` | `jsonb NOT NULL DEFAULT '{}'::jsonb` | Server-side opaque metadata; do not expose raw to browser. |

### 6.2 Enumerations

Use the same value sets in database checks, Pydantic validation, and frontend TypeScript types.

Field `status` values:

- `planned`
- `active`
- `inactive`
- `archived`

Provider sync status values:

- `not_synced`
- `pending`
- `synced`
- `failed`

### 6.3 Migration requirements

The migration must be re-run safe:

- Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for every column.
- Use `DROP CONSTRAINT IF EXISTS` before each `ADD CONSTRAINT`.
- Use `CREATE INDEX IF NOT EXISTS` for normal indexes.
- Use `CREATE UNIQUE INDEX IF NOT EXISTS` for partial unique indexes.
- Use the repository migration separator `--;;` between statements.
- Preserve all existing rows.
- Do not change or rewrite `geometry`.
- Do not rename existing columns.

Recommended constraints and indexes:

- `plots_status_chk` allowing null or one of the pinned field status values.
- `plots_provider_sync_status_chk` allowing null or one of the pinned provider sync values.
- `plots_provider_metadata_object_chk` requiring `jsonb_typeof(provider_metadata) = 'object'`.
- Partial unique index on `(external_provider, external_field_id)` when both are non-null.
- Optional indexes on `status` and `provider_sync_status`.

### 6.4 Backend DTO/repository updates

Update these as one coupled change set:

- `PlotCreate`
- `PlotUpdate`
- `PlotResponse`
- `plots_repo._COLUMNS`
- `plots_repo._row_to_plot`
- `plots_repo.create_plot`
- `plots_repo.update_plot`
- `plots_repo.create_plots_bulk`
- import/export helpers in `plots.py`
- in-memory fake store used by backend tests

Contract rules:

- Preserve existing fields: `id`, `name`, `geometry`, `areaHa`, `createdAt`, `updatedAt`.
- Add optional camelCase response fields:
  - `groupName`
  - `cropType`
  - `variety`
  - `seasonLabel`
  - `sowingDate`
  - `plantingDate`
  - `status`
  - `externalProvider`
  - `externalFieldId`
  - `providerSyncStatus`
  - `providerSyncedAt`
- Do not expose raw `provider_metadata` unless a sanitized whitelist is deliberately defined.
- Keep provider-specific IDs separate from Akasha plot IDs.
- Keep provider-link writes adapter-owned where possible.

Export/import rules:

- Extend GeoJSON export feature properties with user-facing field metadata.
- Do not include raw provider metadata in GeoJSON exports.
- Extend GeoJSON import to read supported field metadata properties when present.
- Preserve current import behavior for `name`, `Name`, `title`, raw geometries, partial success, and
  rejected feature reporting.

## 7. Frontend state, API, and query plan

### 7.1 TypeScript DTOs

Update:

`apps/frontend/src/types/api.ts`

Add:

```ts
export type PlotStatus = 'planned' | 'active' | 'inactive' | 'archived';
export type ProviderSyncStatus = 'not_synced' | 'pending' | 'synced' | 'failed';
export interface Plot { ... }
export interface PlotCreatePayload { ... }
export interface PlotUpdatePayload { ... }
export interface RejectedFeature { ... }
export interface PlotImportResponse { ... }
```

`Plot` should keep existing BFF field names and add optional metadata:

- `id`
- `name`
- `geometry`
- `areaHa`
- `createdAt`
- `updatedAt`
- `groupName`
- `cropType`
- `variety`
- `seasonLabel`
- `sowingDate`
- `plantingDate`
- `status`
- `externalProvider`
- `externalFieldId`
- `providerSyncStatus`
- `providerSyncedAt`

Use a local GeoJSON geometry type compatible with `Polygon` and `MultiPolygon`.

### 7.2 API client

Update:

`apps/frontend/src/lib/api.ts`

Extend `request<T>` to accept request options while preserving existing GET behavior:

- `method`
- `body`
- `headers`
- JSON body encoding
- `Content-Type: application/json` for JSON writes
- `Accept: application/json` defaults
- sanitized `ApiError` behavior
- `204 No Content` handling

Add functions:

- `getPlots`
- `createPlot`
- `updatePlot`
- `deletePlot`
- `importPlotsGeoJson`
- `exportAllPlotsGeoJson`
- `exportPlotGeoJson`

Export behavior:

- Backend currently returns inline `application/geo+json`.
- Frontend should fetch the GeoJSON, create a `Blob`, create an object URL, and trigger a download.
- Use deterministic filenames:
  - all fields: `fields.geojson`
  - selected field: derived sanitized field name plus `.geojson`
- Do not require backend `Content-Disposition` in Phase 1.

### 7.3 TanStack Query

Update:

`apps/frontend/src/lib/queries.ts`

Add:

- `queryKeys.plots`
- `usePlots`
- `useCreatePlot`
- `useUpdatePlot`
- `useDeletePlot`
- `useImportPlotsGeoJson`

Mutation behavior:

- Create invalidates `queryKeys.plots`.
- Update invalidates `queryKeys.plots`.
- Delete invalidates `queryKeys.plots`.
- Import invalidates `queryKeys.plots`.
- Delete clears `selectedPlotId` when the deleted field is selected.

Selected field design:

- For Phase 1, derive `selectedPlot` from the `usePlots` list.
- Do not add a separate `usePlot(id)` detail query unless implementation exposes a concrete need.
- Add a defensive reconciliation effect in the page or panel to clear selection if the selected ID is
  not present after the list refreshes.

### 7.4 Client state

Update:

`apps/frontend/src/state/mapViewContext.tsx`

Add:

- `selectedPlotId: string | null`
- `setSelectedPlotId(plotId: string | null)`
- optional `clearSelectedPlot()`

Keep server field data in TanStack Query. Keep only selection and tool state in React client state.

## 8. Terra Draw integration plan

### 8.1 Components to add or update

Add:

- `apps/frontend/src/components/fields/FieldDrawController.tsx`
- `apps/frontend/src/components/fields/AllFieldsPanel.tsx`
- `apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`

Update:

- `apps/frontend/src/pages/MapPage.tsx`
- `apps/frontend/src/components/scaffold/PlotToolbar.tsx`
- `apps/frontend/src/components/map/MeasureTool.tsx` or a shared draw coordinator wrapper
- `apps/frontend/src/components/map/MapLayerManager.tsx` if `FieldBoundaryLayer` is not fully
  separate

### 8.2 Toolbar behavior

`PlotToolbar` becomes the field toolbar. It should expose:

- Draw field
- Edit selected field
- Import GeoJSON
- Export GeoJSON
- Delete selected field

Disabled states:

- Edit disabled when no field is selected.
- Delete disabled when no field is selected.
- Export selected field disabled when no field is selected, but export all can remain available if
  fields exist.
- Draw disabled only when map is unavailable or another mutually exclusive tool is active.
- Every disabled action needs an explanatory tooltip.

### 8.3 Draw flow

`FieldDrawController` receives:

- MapLibre `map`
- active field tool mode
- selected plot/field
- create/update mutation callbacks
- selection setter

Draw mode:

1. Activate Terra Draw polygon mode.
2. Capture finished polygon geometry.
3. Show a testable inline or modal form for field name and optional metadata.
4. Persist through `useCreatePlot`.
5. Select the newly created field.
6. Invalidate the plots list through mutation behavior.

Do not use `window.prompt`.

### 8.4 Edit flow

Edit mode:

1. Require a selected field.
2. Seed the selected field geometry into Terra Draw.
3. Use a select/edit-capable Terra Draw mode, not only the create-only polygon mode used by
   `MeasureTool`.
4. Persist changed geometry through `useUpdatePlot`.
5. Keep the same selected field after save.

### 8.5 Import/export/delete flow

Import:

- Read a local GeoJSON file in the browser.
- Submit it to `importPlotsGeoJson`.
- Surface imported and rejected counts.
- Select the first imported field when appropriate.

Export:

- Export selected field when selected.
- Export all fields when no field is selected or when user explicitly chooses all-fields export.
- Use frontend Blob download.

Delete:

- Confirm delete.
- Call `useDeletePlot`.
- Clear selected field when selected field is deleted.

### 8.6 Terra Draw mutual exclusion

`MeasureTool` already creates a Terra Draw instance on the same MapLibre map. Phase 1 must prevent
two draw workflows from owning map pointer events at the same time.

Required coordination:

- Track an active map tool owner:
  - `measure`
  - `field-draw`
  - `field-edit`
  - `null`
- Activating field draw/edit must stop and clear the measure workflow first.
- Activating measure must stop and clear field draw/edit first.
- If Terra Draw adapter source/layer IDs cannot safely coexist even when stopped, refactor to one
  shared Terra Draw instance before shipping Phase 1.

This is a required implementation guardrail, not an optional cleanup.

## 9. Field list and selected geometry plan

### 9.1 AllFieldsPanel

Create:

`apps/frontend/src/components/fields/AllFieldsPanel.tsx`

Required behavior:

- Load fields from `usePlots`.
- Show loading state.
- Show error state with retry.
- Show empty state with draw/import entry points.
- Search by field name and useful metadata such as crop/group/season.
- Render field cards with:
  - name,
  - area,
  - crop/season when present,
  - status when present,
  - provider sync status if safely exposed.
- Select field on click.
- Focus map on selected field geometry.
- Provide add/import actions.

### 9.2 Field boundary layer

Create:

`apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`

or extend:

`apps/frontend/src/components/map/MapLayerManager.tsx`

Required visual behavior:

- Render selected field geometry as a subtle fill.
- Render selected field outline as a thick white outline.
- Add/update/remove GeoJSON source and layers without disrupting satellite raster layers.
- Keep source/layer IDs stable and namespaced.
- Remove field layers when selection is cleared.

## 10. Tests to add or update

### 10.1 Backend tests

Add or update tests in:

- `apps/api/tests/test_slice3.py`
- or `apps/api/tests/test_plots_metadata.py`

Coverage:

- Create plot with metadata and verify response.
- Patch metadata without changing geometry.
- Patch geometry without losing metadata.
- List and get preserve metadata.
- GeoJSON export includes safe field metadata in feature properties.
- GeoJSON export does not include raw provider metadata.
- GeoJSON import reads supported metadata properties.
- Import partial success behavior remains unchanged.
- Invalid `status` returns standard error envelope.
- Invalid `provider_sync_status` returns standard error envelope.
- Malformed date values return standard error envelope.
- Provider-link fields default to safe null or `not_synced` values.
- Existing CRUD/import/export/geometry tests still pass.
- `FakeStore` signatures match the new route/repo contracts.

Important test limitation:

- Existing backend tests monkeypatch repository functions and do not run real PostGIS migrations.
- SQL/migration validation must be done with `app.cli migrate` and `app.cli check` in an environment
  with PostGIS.

### 10.2 Frontend tests

Add or update tests near changed modules.

Coverage:

- API client:
  - GET behavior unchanged.
  - POST sends JSON body.
  - PATCH sends JSON body.
  - DELETE handles `204`.
  - import returns typed imported/rejected counts.
  - export returns downloadable GeoJSON Blob or equivalent download helper behavior.
  - error envelope parsing unchanged.
- Query hooks:
  - `usePlots` fetches fields.
  - create/update/delete/import invalidate `queryKeys.plots`.
  - delete clears selected field.
- Map view context:
  - `selectedPlotId` set/clear behavior.
  - reconciliation clears deleted/invalid selected field.
- `PlotToolbar`:
  - draw action enabled when map/tool state allows it.
  - edit/delete disabled when no field is selected.
  - disabled tooltips explain why.
  - import/export actions are wired.
- `AllFieldsPanel`:
  - loading state.
  - empty state.
  - error state.
  - search filtering.
  - card selection.
  - add/import actions.
- `FieldDrawController`:
  - create flow calls create mutation with geometry and name.
  - edit flow requires selected field.
  - seeded edit geometry is used.
  - draw sessions clean up on unmount.
  - active draw tool mutual exclusion is respected.
- `FieldBoundaryLayer` or `MapLayerManager`:
  - adds selected field source/layers.
  - updates selected geometry.
  - removes layers when selection clears.
  - does not remove or corrupt satellite layers.
- Regression:
  - true-colour remains the default map layer.
  - browser only calls Akasha same-origin `/api/*`.

## 11. Validation commands

Run after implementation:

```powershell
Set-Location "C:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\apps\api"
python -m pytest -q
python -m pytest tests\test_slice3.py -q
```

Run migration checks in the API container or another environment with PostGIS available:

```powershell
python -m app.cli migrate
python -m app.cli check
```

Frontend validation:

```powershell
Set-Location "C:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\apps\frontend"
yarn test
yarn lint
yarn build
```

Documentation-only edits do not require these commands, but Phase 1 implementation does.

## 12. Risks and rollback notes

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Migration/repository drift | Keep DDL idempotent; run real `migrate` and `check`; update fake store signatures. | Additive columns can remain unused; disable UI wiring first. |
| FastAPI response model drops new fields | Update DTOs, repo mapping, fake store, and export helpers together. | Revert DTO/repo metadata additions while preserving existing plot fields. |
| Provider schema evolves in Phase 2+ | Keep provider fields generic, nullable, and adapter-owned. | Leave nullable provider fields unused. |
| Provider metadata exposure | Do not expose raw `provider_metadata`; whitelist only safe UI fields. | Remove field from responses/exports. |
| Terra Draw conflicts with MeasureTool | Add active tool ownership and hard mutual exclusion. | Disable field draw/edit while preserving list/import/export. |
| Export UX mismatch | Use frontend Blob download instead of requiring backend attachment headers. | Fall back to opening same-origin export route. |
| Plot vs field terminology confusion | Keep backend/API as plot, UI copy as field, and document the boundary. | UI-only copy changes are reversible. |
| First-demo default layer regression | Add frontend regression coverage that true-colour remains default. | Revert layer-related UI changes without affecting field backend. |

## 13. Execution order and dependencies

Recommended order:

1. `TASK-005` - frontend types.
2. `TASK-013` - idempotent backend metadata migration.
3. `TASK-014` - backend DTO/repo/import/export metadata support.
4. `TASK-015` - backend metadata tests.
5. `TASK-006` - frontend API client functions.
6. `TASK-007` - frontend query hooks and mutations.
7. `TASK-010` - selected-field state.
8. `TASK-011` - all-fields panel.
9. `TASK-012` - selected field boundary layer.
10. `TASK-008` - real field toolbar.
11. `TASK-009` - Terra Draw create/edit controller and draw-tool mutual exclusion.
12. `TASK-016` - frontend field tests.
13. Validation commands.

Parallelization notes:

- Backend migration/metadata/tests can proceed mostly in parallel with frontend type/API/query work
  once the DTO shape is agreed.
- Field list, selected boundary, toolbar, and draw controller share state and should be coordinated
  to avoid prop/API churn.
- Terra Draw mutual exclusion should be designed before finalizing toolbar and draw controller
  behavior.

## 14. Files expected to change during implementation

Backend:

- `apps/api/migrations/003_field_metadata_provider_links.sql`
- `apps/api/app/plots.py`
- `apps/api/app/plots_repo.py`
- `apps/api/tests/test_slice3.py`
- optionally `apps/api/tests/test_plots_metadata.py`

Frontend:

- `apps/frontend/src/types/api.ts`
- `apps/frontend/src/lib/api.ts`
- `apps/frontend/src/lib/queries.ts`
- `apps/frontend/src/state/mapViewContext.tsx`
- `apps/frontend/src/pages/MapPage.tsx`
- `apps/frontend/src/components/scaffold/PlotToolbar.tsx`
- `apps/frontend/src/components/map/MeasureTool.tsx`
- `apps/frontend/src/components/map/MapLayerManager.tsx`
- `apps/frontend/src/components/fields/FieldDrawController.tsx`
- `apps/frontend/src/components/fields/AllFieldsPanel.tsx`
- `apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`
- relevant frontend test files near changed modules

## 15. Explicit non-goals for Phase 1

- No EOS API calls from the browser.
- No EOS provider adapter implementation; that begins in Phase 2.
- No authentication or ownership enforcement; Better Auth is deferred to Phase 12.
- No analytics trend chart implementation.
- No weather implementation.
- No VRA zoning implementation.
- No reports implementation.
- No disease/pest/yield/scouting/activity/machinery modules.
- No backend route rename from `/api/plots` to `/api/fields`.
- No duplicate geometry storage.
- No change to default true-colour imagery behavior.

## 16. Acceptance checks for Phase 1

Phase 1 is complete when:

- Frontend has typed plot/field DTOs matching backend responses.
- Frontend can list, create, update, delete, import, and export fields through same-origin `/api/*`.
- Disabled plot toolbar is replaced with real field actions.
- Field selection is stored in map view state.
- Selected field appears in a fields panel and on the map.
- Terra Draw can create a field polygon and persist it through the BFF.
- Edit mode can update selected field geometry or is explicitly guarded until complete within the
  task.
- Measure tool and field draw/edit cannot be active at the same time.
- Backend stores field metadata/provider-link fields without duplicating geometry.
- Backend metadata is returned/imported/exported only through safe, normalized fields.
- Backend and frontend tests cover the new behavior.
- Validation commands pass, with migration/check run in a PostGIS-capable environment.
