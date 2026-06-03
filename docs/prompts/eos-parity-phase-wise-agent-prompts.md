# EOS Parity Phase-wise Agent Prompts

Use this prompt pack when running Copilot CLI or another coding agent phase-by-phase against `docs/impl-plan/feature-eos-crop-monitoring-parity-1.md`.

The workflow is intentionally two-step for every phase:

1. **Planning prompt** — the agent performs research, inspects existing code, identifies what is already implemented, resolves conflicts with the new EOS-parity direction, and writes a phase execution plan.
2. **Implementation prompt** — the agent implements only the approved phase plan, validates it, and updates the plan/checklist.

Do not skip the planning prompt. The repo already has partial implementations in a different shape. Each phase must first discover what exists, decide what to reuse, what to replace, and what must become provider-adapter-ready for future Akasha-native production.

## Model routing recommendation

Use different model families for planning, implementation, and review when your CLI supports it. The goal is not brand loyalty; it is adversarial cross-checking.

| Activity | Default model choice | Why |
|---|---|---|
| Phase planning / architecture | Claude Opus-class model if available | Best for long-context architecture, dependency analysis, and identifying hidden coupling. |
| Backend implementation | GPT-5-class or Claude Sonnet-class model | Strong code generation and debugging; choose the one that is most reliable in your CLI. |
| Frontend implementation | GPT-5-class or Claude Sonnet-class model | Strong React/TypeScript edits; validate with Vitest/build. |
| Review / adversarial audit | Different family than implementer; prefer Opus if implementation used GPT, or GPT if implementation used Claude | Avoid same-model blind spots. |
| Test failure debugging | GPT-5-class model, then cross-check with Opus if failures are architectural | Good at iterative error repair. |
| Documentation cleanup | Any strong general model | Lower risk; still validate links and front matter. |

Recommended default loop:

1. Planning: `Opus`.
2. Plan review: `GPT`.
3. Implementation: `GPT` or `Sonnet`.
4. Implementation review: model family not used for implementation.
5. Final validation: same implementation model may fix issues, but review model must approve before moving to the next phase.

## Non-negotiable global instructions for every phase

Paste these instructions at the top of every planning and implementation prompt.

```text
You are working in the Akasha repository.

Primary source of truth:
- docs/impl-plan/feature-eos-crop-monitoring-parity-1.md
- docs/eos-crop-monitoring-replication-research.md
- docs/architecture-tech-stack.md
- docs/engineering-dos-donts.md
- docs/data-ingestion-and-satellite-rules.md

Critical architecture rules:
- The browser must never call EOSDA API Connect directly.
- EOS is a temporary trial provider only.
- All provider access must go through an Akasha BFF/provider adapter layer.
- The adapter must be swappable later for Akasha-native STAC/COG/weather/zoning services.
- Do not hard-code EOS assumptions into frontend DTOs or UI state.
- Keep true-colour imagery as the default map layer; never default to NDVI.
- Do not expose EOS keys, MinIO URLs, PostGIS/STAC/TiTiler internals, raw COG paths, stack traces, SQL, or private hostnames to the browser.
- Existing code may already implement part of the requested behavior in a different way. You must inspect it before changing it.
- Backward compatibility is not required unless the old behavior is still needed for the final production architecture.
- Prefer replacing incorrect or temporary logic with clean provider-ready architecture instead of preserving legacy shape.
- Preserve production-relevant native Akasha logic: STAC/COG catalog, BFF masked statistics, PostGIS fields/plots, MapLibre/Terra Draw, same-origin tile routes.

Required workflow:
1. Read the phase tasks in docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.
2. Inspect current implementation before editing.
3. Identify what already exists, what should be reused, what should be removed/replaced, and what must be made adapter-ready.
4. Use official docs or current repository docs when uncertain.
5. Use multi-model review if available. Ask a second model to challenge the plan or implementation before finalizing.
6. Do not move to the next phase until this phase passes tests and review.
7. Update relevant docs/checklists after implementation.
8. Never print or request secrets. If EOS_API_KEY is needed, instruct the operator to place it in ignored .env or deployment secrets.
```

## Required review gate for every phase

After the planning prompt and before implementation, run this review prompt with a different model:

```text
Review the proposed phase plan as an adversarial reviewer.

Check specifically:
1. Did the plan inspect existing code rather than assuming blank-slate implementation?
2. Does it avoid direct frontend calls to EOS?
3. Does it preserve a provider adapter that can swap EOS for Akasha-native services later?
4. Does it remove or replace old logic only when that logic is not production-relevant?
5. Are all tests, migrations, docs, and validation commands explicit?
6. Are there hidden dependencies on later phases?
7. Is the plan small enough to implement safely in one phase?
8. Are there any security leaks, secret-handling mistakes, or internal URL exposure risks?

Return:
- APPROVED or BLOCKED.
- Blocking issues.
- Required corrections.
- Optional improvements.
```

After implementation, run this review prompt with a different model:

```text
Review the completed implementation as an adversarial reviewer.

Check specifically:
1. Does the diff implement only the approved phase scope?
2. Does the implementation follow the provider-adapter architecture?
3. Does any frontend code call EOS or expose provider details directly?
4. Are old incompatible patterns removed or updated cleanly?
5. Are tests meaningful and sufficient?
6. Were validation commands actually run, and do they pass?
7. Are docs/checklists updated?
8. Are there security leaks, secret exposures, raw provider URLs, internal URLs, or stack traces?
9. Is the phase safe to build on for the next phase?

Return:
- APPROVED or BLOCKED.
- Blocking issues.
- Required corrections.
- Follow-up tasks that belong to later phases.
```

## Phase 0 prompts — Scope, acceptance matrix, demo definition

### Phase 0 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 0 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Create a concrete EOS parity acceptance matrix and demo definition before implementation starts.

Required research and inspection:
- Read docs/eos-crop-monitoring-replication-research.md.
- Read docs/impl-plan/feature-eos-crop-monitoring-parity-1.md, Phase 0.
- Inspect docs/README.md and docs/platform-plan.md for documentation conventions.
- Identify any already-existing matrix/checklist/doc that should be reused instead of duplicated.

Planning output required:
1. Exact files to create/update.
2. Proposed acceptance matrix columns.
3. Exact module list to include.
4. How to classify each module: reuse-existing-akasha, wire-existing-backend, eos-backed-trial, akasha-native-first-party, defer.
5. First-demo acceptance path.
6. Non-goals for first demo.
7. Validation checks.
8. Risks or clarifications.

Do not edit files in this planning step.
```

### Phase 0 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 0 plan only.

Required tasks:
- Create or update docs/eos-parity-acceptance-matrix.md.
- Classify all EOS modules from docs/eos-crop-monitoring-replication-research.md.
- Define the first-demo acceptance path exactly.
- Add non-goals for first demo.
- Link the acceptance matrix from docs/README.md.
- Do not modify application code.

Validation required:
- Check Markdown diagnostics for changed docs.
- Verify docs links are valid relative links.
- Run git status and summarize changed files.

Final response required:
- Files changed.
- Acceptance matrix sections created.
- Any assumptions or follow-ups.
- Validation results.
```

## Phase 1 prompts — Field foundation and existing plot API wiring

### Phase 1 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 1 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Make field creation/selection real by wiring the existing plot API into the frontend and extending metadata without duplicating geometry storage.

Required research and inspection:
- Read Phase 1 tasks in docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.
- Inspect apps/api/app/plots.py, plots_repo.py, migrations, and tests.
- Inspect apps/frontend/src/components/scaffold/PlotToolbar.tsx.
- Inspect apps/frontend/src/lib/api.ts, lib/queries.ts, types/api.ts, state/mapViewContext.tsx, MapPage.tsx, MapLayerManager.tsx.
- Identify existing plot/field logic that can be reused.
- Identify old placeholder logic that should be replaced.
- Decide whether existing plot terminology should remain internally while UI uses field terminology.

Planning output required:
1. Existing implementation inventory.
2. What to reuse, replace, and remove.
3. Data model change plan for field metadata/provider links.
4. Frontend state/API/query plan.
5. Terra Draw integration plan.
6. Tests to add/update.
7. Validation commands.
8. Risks and rollback notes.

Do not edit files in this planning step.
```

### Phase 1 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 1 plan only.

Required scope:
- Wire existing /api/plots into frontend typed API functions and TanStack Query hooks.
- Replace PlotToolbar placeholder with real field actions.
- Add selected field state.
- Add All Fields panel.
- Add selected field boundary rendering.
- Add field metadata/provider-link migration only as approved.
- Extend backend plot metadata only as approved.
- Add backend and frontend tests.

Constraints:
- Do not implement EOS API calls in Phase 1.
- Do not add navigation shell yet unless explicitly approved as a small dependency.
- Do not preserve backward compatibility unless it is production-relevant.
- Do not duplicate geometry storage.

Validation required:
- Backend tests for changed API code.
- Frontend tests for changed UI/hooks.
- Run lint/build if frontend structure changes.
- Confirm no direct EOS logic was added.

Final response required:
- Files changed.
- Existing logic reused/replaced.
- Tests run and results.
- Known follow-ups for Phase 2.
```

## Phase 2 prompts — EOS provider adapter foundation

### Phase 2 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 2 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add secure server-side EOS provider plumbing without exposing EOS keys or raw EOS contracts to the frontend.

Required research and inspection:
- Read Phase 2 tasks in the implementation plan.
- Inspect apps/api/app/config.py, main.py, raster/errors.py, plots.py, plots_repo.py.
- Inspect existing dependency style in apps/api/requirements.txt.
- Inspect .gitignore and .env.example patterns if present.
- Review EOS official docs for Field Management, Search/Scene Search, Render/Imagery, Statistics/Field Analytics, Weather, and Zoning if endpoint details are needed.
- Identify where provider interfaces should live.
- Identify what should be mocked for tests.

Planning output required:
1. Provider package structure.
2. EOS config/secrets plan.
3. HTTP client dependency plan.
4. Provider DTO plan.
5. FieldProvider/SceneProvider/TileProvider/AnalyticsProvider/WeatherProvider/ZoningProvider interface plan.
6. Provider status route plan.
7. Mock testing plan.
8. Secret-leak prevention checklist.

Do not edit files in this planning step.
```

### Phase 2 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 2 plan only.

Required scope:
- Add EOS/provider settings server-side only.
- Add pinned backend HTTP client if approved.
- Add provider interface modules and normalized provider DTOs.
- Add EOS client with x-api-key, timeouts, sanitized errors, and secret-safe logging.
- Add initial EOS provider modules as approved.
- Add /api/providers/eos/status with no key leakage.
- Register provider router.
- Add mocked backend tests.

Constraints:
- No frontend direct EOS calls.
- No real EOS calls required in CI.
- No raw EOS response as public API contract.
- No hard dependency on having EOS_API_KEY for local app startup.

Validation required:
- Run backend tests.
- Confirm provider status does not expose EOS_API_KEY.
- Confirm app imports without geospatial/provider secrets.
- Run git diff/grep for accidental secret prints.

Final response required:
- Files changed.
- Provider interfaces created.
- Tests run and results.
- Security checks performed.
- Follow-ups for Phase 4/5/7/8.
```

## Phase 3 prompts — Product shell and navigation

### Phase 3 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 3 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add EOS-like product navigation and routes while preserving the current map workspace.

Required research and inspection:
- Inspect current App.tsx, MapPage.tsx, main.tsx, components, tests, package.json.
- Inspect EOS UI findings in docs/eos-crop-monitoring-replication-research.md.
- Decide routing library and lazy-loading approach.
- Identify how existing MapPage should move into Monitoring / Field Analytics without breaking current root URL.
- Identify placeholder shells that should be created now.

Planning output required:
1. Route map.
2. Shell component structure.
3. Dependency addition plan.
4. Existing MapPage preservation plan.
5. Placeholder module policy.
6. Tests to add/update.
7. Validation commands.

Do not edit files in this planning step.
```

### Phase 3 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 3 plan only.

Required scope:
- Add approved routing dependency.
- Add product shell/navigation.
- Add routes for EOS-like modules.
- Keep root URL working.
- Move or wrap MapPage as approved.
- Add clear placeholders for modules not implemented yet.
- Add route/shell tests.

Constraints:
- Do not implement field analytics/weather/VRA logic in this phase.
- Do not break existing map load.
- Do not introduce direct EOS frontend calls.

Validation required:
- yarn test.
- yarn lint.
- yarn build.
- Browser smoke if available: root route loads and navigation links render.

Final response required:
- Files changed.
- Routes added.
- Tests run and results.
- Any route limitations.
```

## Phase 4 prompts — Monitoring map parity

### Phase 4 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 4 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Make the map field-aware and EOS-like: selected field drives scene timeline, true-colour imagery, index layers, cloud controls, and download affordances.

Required research and inspection:
- Inspect existing source/date/tile flow in product.py, catalog_resolver.py, tiles.py, api.ts, queries.ts, MapPage.tsx, DisplayModeToggle, TimelineBar, Legend, MapControls.
- Inspect Phase 1 field selection implementation and Phase 2 provider interfaces.
- Review EOS official docs for scene search/render if needed.
- Identify existing native map/timeline behavior to preserve for no-field mode.
- Identify provider-specific details that must stay server-side.

Planning output required:
1. Field scene API plan.
2. Tile proxy/template plan.
3. Frontend selected-field scene flow.
4. Display mode expansion plan.
5. Cloud mask control plan.
6. Existing global scene fallback plan.
7. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 4 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 4 plan only.

Required scope:
- Add field provider sync route if not already present.
- Add field scene list route.
- Add same-origin EOS-backed tile proxy/template route.
- Add frontend field scene hooks.
- Make MapPage use field scenes when a selected synced field exists.
- Expand display modes for EOS-backed scenes.
- Add cloud mask controls and missing map controls approved for this phase.
- Preserve global source/date behavior when no field is selected.

Constraints:
- Keep default display mode RGB.
- Do not expose direct EOS URLs or IDs beyond normalized safe scene IDs/metadata.
- Do not implement analytics chart/weather/VRA in this phase.

Validation required:
- Backend tests for scene route and tile proxy using mocks.
- Frontend tests for field scene timeline/display mode/cloud toggles.
- Existing map tests must pass.
- Build/lint if frontend changed.

Final response required:
- Files changed.
- New API contracts.
- Existing logic reused/replaced.
- Tests run and results.
- Follow-ups for Phase 5/6.
```

## Phase 5 prompts — Field analytics and trends

### Phase 5 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 5 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Replace IndexPanel placeholder with real selected-field single-date statistics and multi-temporal analytics trends.

Required research and inspection:
- Inspect current native /api/indices/statistics flow and raster indices.
- Inspect IndexPanel placeholder and map selected-field state.
- Inspect Phase 2 analytics provider and Phase 4 field scenes.
- Review EOS Field Analytics/Statistics docs if needed.
- Decide chart library with bundle/test considerations.
- Identify native MSAVI/RECI feasibility versus EOS-only support.

Planning output required:
1. Native field statistics route plan.
2. EOS trend route plan.
3. DTO shape for trend points.
4. Chart dependency recommendation.
5. Analytics panel structure.
6. Placeholder policy for crop info/growth/risk sections.
7. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 5 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 5 plan only.

Required scope:
- Add or extend native index support only as approved.
- Add selected-field statistics route.
- Add field analytics trend route using provider adapter.
- Add chart dependency if approved.
- Replace IndexPanel with real analytics UI.
- Add analytics sections/placeholders approved in the plan.
- Add backend/frontend tests.

Constraints:
- Do not overclaim NDVI as diagnosis.
- Always display cloud/valid/coverage metadata.
- Keep provider responses normalized.
- No direct EOS frontend calls.

Validation required:
- Backend tests.
- Frontend tests.
- yarn lint/build.
- Manual smoke if browser available: selected field shows stats/trend states.

Final response required:
- Files changed.
- Analytics API contract.
- Chart dependency added, if any.
- Tests run and results.
- Remaining analytics limitations.
```

## Phase 6 prompts — Cloud masking, legends, exports

### Phase 6 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 6 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add EOS-like cloud-mask controls, legend behavior, and selected field/date/index exports.

Required research and inspection:
- Inspect current cloud usability logic, Legend, DisplayModeToggle, IndexPanel/analytics state.
- Inspect provider analytics/tile routes from previous phases.
- Review EOS cloud masking and imagery/download docs if needed.
- Identify native SCL mask options and EOS cloud_masking_level mapping.
- Decide first export formats and what should be provider-backed versus native.

Planning output required:
1. CloudMaskOptions DTO plan.
2. EOS/native cloud mapping plan.
3. Legend/color-ramp plan.
4. Export route plan.
5. Frontend download menu plan.
6. Security constraints for downloads.
7. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 6 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 6 plan only.

Required scope:
- Add CloudMaskOptions DTO and propagation.
- Map cloud options to EOS/native behavior.
- Update legends for RGB/index display.
- Add selected field/date/index export routes.
- Add frontend download menu actions.
- Add tests.

Constraints:
- Downloads must go through BFF.
- No provider-signed secret URLs to the browser.
- Safe default masking must remain enabled for statistics.

Validation required:
- Backend export/cloud tests.
- Frontend menu/legend tests.
- Secret exposure grep for EOS key/internal URLs.

Final response required:
- Files changed.
- Export formats supported.
- Tests run and results.
- Unsupported export formats and planned follow-ups.
```

## Phase 7 prompts — Weather analytics and forecast

### Phase 7 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 7 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add EOS-like field weather forecast and historical weather analytics with provider-normalized contracts.

Required research and inspection:
- Inspect Phase 2 weather provider foundation.
- Inspect product shell weather routes.
- Review EOS Weather API official docs if needed.
- Identify future native replacement fields for IMD/GFS/ECMWF/Open-Meteo/SMAP.
- Decide caching/stale-time policy.

Planning output required:
1. Weather DTO plan.
2. BFF weather route plan.
3. Frontend forecast page plan.
4. Frontend weather analytics chart plan.
5. Cache/rate-limit plan.
6. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 7 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 7 plan only.

Required scope:
- Add provider-backed weather routes.
- Add frontend weather hooks.
- Implement Weather Forecast page.
- Implement Weather Analytics page.
- Add caching/stale-time rules.
- Add tests.

Constraints:
- Field is required for weather routes.
- Do not hard-code EOS response shapes into frontend.
- Show provider-unavailable states cleanly.

Validation required:
- Backend mocked weather tests.
- Frontend weather page tests.
- Build/lint.

Final response required:
- Files changed.
- Weather metrics supported.
- Tests run and results.
- Provider limitations.
```

## Phase 8 prompts — VRA vegetation zoning

### Phase 8 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 8 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Implement the first EOS-compatible VRA workflow: vegetation-based zoning map creation, retrieval, display, and export.

Required research and inspection:
- Inspect Phase 2 zoning provider foundation.
- Inspect Phase 4 field scenes and Phase 6 exports.
- Review EOS Zoning API docs if needed.
- Identify async job/polling behavior and durable metadata requirements.
- Identify native replacement path using Akasha k-means/quantile zoning.

Planning output required:
1. Zoning request/response DTOs.
2. Job tracking schema plan if needed.
3. BFF route plan.
4. Frontend VRA Vegetation page plan.
5. Zone overlay rendering plan.
6. Export plan.
7. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 8 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 8 plan only.

Required scope:
- Add vegetation zoning create/list/get/export routes.
- Add job tracking if approved.
- Implement VRA Vegetation page.
- Add shells for Sowing, P&K, Map Builder, and Soil Sampling if not already present.
- Render zone polygons over existing map/layer context.
- Add tests.

Constraints:
- Do not block frontend while zoning job runs.
- Normalize provider status.
- No direct EOS frontend calls.

Validation required:
- Backend zoning tests using mocked EOS responses.
- Frontend VRA tests.
- Manual smoke if browser available.

Final response required:
- Files changed.
- Zoning lifecycle implemented.
- Tests run and results.
- Remaining VRA limitations.
```

## Phase 9 prompts — Reports and leaderboard

### Phase 9 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 9 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Build Akasha-native field leaderboard and reporting using normalized field, analytics, weather, and activity data.

Required research and inspection:
- Inspect analytics/weather outputs from prior phases.
- Inspect field metadata and operations data if implemented.
- Review EOS leaderboard/reporting UI findings.
- Decide scoring formula and report template persistence.
- Decide CSV first, XLSX/PDF later unless required.

Planning output required:
1. Leaderboard DTO and scoring plan.
2. Report template schema plan.
3. Export plan.
4. Frontend leaderboard page plan.
5. Frontend report-template page plan.
6. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 9 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 9 plan only.

Required scope:
- Add leaderboard route and scoring.
- Add report template routes/schema.
- Add CSV export.
- Implement Field Leaderboard page.
- Implement Reporting page.
- Add tests.

Constraints:
- Do not depend on a non-existent EOS reporting API.
- Keep score formula transparent.
- Use placeholders for unavailable values like actual yield.

Validation required:
- Backend report tests.
- Frontend report tests.
- Export smoke.

Final response required:
- Files changed.
- Score formula.
- Exports supported.
- Tests run and results.
```

## Phase 10 prompts — Operations, scout tasks, data manager, field groups

### Phase 10 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 10 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add EOS-like operational modules as Akasha-native workflows: field activity log, scout tasks, data manager, connections placeholder, and field groups.

Required research and inspection:
- Inspect current field/plot schema and frontend shell routes.
- Review EOS UI findings for Field Activity Log, Scout Tasks, Data Manager, Connections, and Field Groups.
- Decide schema boundaries for activities, tasks, field groups, uploaded datasets, and attachments metadata.
- Decide which imports are parsed now versus stored as metadata.

Planning output required:
1. Schema plan.
2. API route plan.
3. Frontend page plan.
4. Upload/security constraints.
5. John Deere placeholder policy.
6. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 10 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 10 plan only.

Required scope:
- Add operations/tasks/data-manager/field-groups migration.
- Add backend CRUD/routes.
- Implement Field Activity Log page.
- Implement Scout Tasks page.
- Implement Data Manager page.
- Implement Connections placeholder.
- Implement Field Groups page.
- Add tests.

Constraints:
- Do not implement John Deere OAuth unless explicitly approved.
- Do not parse ISO-XML beyond approved scope.
- Validate uploaded files and avoid storing secrets in metadata.

Validation required:
- Backend CRUD/upload tests.
- Frontend page tests.
- Build/lint.

Final response required:
- Files changed.
- Data model added.
- Tests run and results.
- Deferred import/integration details.
```

## Phase 11 prompts — Risk, crop stages, diseases/pests, India path

### Phase 11 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 11 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add transparent decision-support foundations: risk summary, crop-stage timeline, diseases/pests shell, and India-specific productization path.

Required research and inspection:
- Inspect analytics, weather, scout task, and field metadata outputs.
- Review EOS disease/pest/risk UI findings.
- Identify what can be rule-based versus what needs future agronomic validation.
- Identify India localization docs to create/update.

Planning output required:
1. Risk scoring inputs and formula.
2. Crop-stage model plan.
3. Disease/pest UI state plan.
4. India-specific productization doc outline.
5. Safety/claim limitations.
6. Tests and validation commands.

Do not edit files in this planning step.
```

### Phase 11 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 11 plan only.

Required scope:
- Add risk summary route/service.
- Add transparent rule-based risk scoring.
- Add crop-stage timeline calculation.
- Implement Diseases & Pests page shell.
- Add India-specific productization plan doc.
- Add tests.

Constraints:
- Do not present NDVI as disease diagnosis.
- Show confidence, inputs, and limitations.
- Keep India-specific work as planned divergence after EOS-like parity.

Validation required:
- Backend risk/stage tests.
- Frontend disease/pest state tests.
- Markdown diagnostics for new docs.

Final response required:
- Files changed.
- Risk formula.
- Tests run and results.
- India-specific follow-ups.
```

## Phase 12 prompts — Auth, teams, API/admin, notifications

### Phase 12 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 12 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Add ownership, collaboration, account/admin, API settings, and notification foundations required before customer pilot data is used.

Required research and inspection:
- Inspect all user-owned data introduced in prior phases.
- Inspect Railway/deployment constraints if relevant.
- Decide authentication provider and local dev behavior.
- Identify ownership columns and authorization checks.
- Identify notification sources and delivery scope.

Planning output required:
1. Auth provider recommendation.
2. User/team schema plan.
3. Ownership enforcement plan.
4. API/admin/settings page plan.
5. Notification schema and UI plan.
6. Tests and validation commands.
7. Migration risks.

Do not edit files in this planning step.
```

### Phase 12 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 12 plan only.

Required scope:
- Add auth/team/admin decision doc.
- Add approved migrations.
- Add auth dependencies/middleware.
- Add ownership checks.
- Implement account/team/settings/API pages.
- Add notification routes and panel.
- Add AI assistant shell only if approved and only using evidence from Akasha APIs.
- Add security tests.

Constraints:
- Do not introduce insecure demo auth into production path.
- Do not expose provider keys in API settings.
- Do not invent agronomic advice in AI assistant.

Validation required:
- Backend auth/ownership tests.
- Frontend auth/settings/notifications tests.
- Secret exposure checks.

Final response required:
- Files changed.
- Auth/ownership model.
- Tests run and results.
- Pilot-readiness limitations.
```

## Phase 13 prompts — End-to-end verification and native replacement readiness

### Phase 13 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 13 from docs/impl-plan/feature-eos-crop-monitoring-parity-1.md.

Phase goal:
Verify full EOS-like workflow, update acceptance matrix, and prove EOS remains replaceable by native Akasha providers.

Required research and inspection:
- Inspect all changed docs and code from Phases 0-12.
- Inspect docs/eos-parity-acceptance-matrix.md.
- Inspect provider interfaces and frontend DTOs for EOS leakage.
- Identify all validation commands and manual browser QA steps.
- Identify native replacement map for every EOS-backed feature.

Planning output required:
1. Full validation plan.
2. Mocked E2E plan.
3. Optional real-EOS smoke plan guarded by EOS_API_KEY.
4. Acceptance matrix update plan.
5. Native replacement documentation plan.
6. Release/demo readiness checklist.

Do not edit files in this planning step.
```

### Phase 13 implementation prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved Phase 13 verification plan only.

Required scope:
- Run mocked E2E workflow.
- Run real-EOS smoke only if EOS_API_KEY is configured locally and never print the key.
- Update docs/eos-parity-acceptance-matrix.md with pass/fail status.
- Update docs/architecture-tech-stack.md with provider replacement map.
- Run full backend/frontend validation commands.
- Perform manual browser QA if browser tools are available.
- Check for secrets/internal URL leakage.

Constraints:
- Do not add new product scope in verification phase.
- Do not skip failed tests.
- Do not mark a feature complete without evidence.

Final response required:
- Validation commands and results.
- Acceptance matrix status summary.
- Native replacement readiness summary.
- Blockers remaining before client demo.
```

## How to run the phase loop

For each phase:

1. Paste the global instructions plus the phase planning prompt.
2. Run the planning model, preferably Opus-class.
3. Run the review gate with a different model.
4. If blocked, ask the planning model to revise.
5. Once approved, paste the global instructions plus the phase implementation prompt.
6. Run implementation with GPT/Sonnet-class model.
7. Run implementation review with a different model.
8. Fix blockers.
9. Run tests and diagnostics.
10. Commit or checkpoint only after the phase is approved.
11. Move to the next phase.

Do not merge phases unless the phase plan explicitly proves the merged scope is smaller and safer than running them separately.
