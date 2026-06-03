# EOS Parity Phase-wise Agent Prompts

Use this prompt pack when running Copilot CLI or another coding agent phase-by-phase against `docs/impl-plan/feature-eos-crop-monitoring-parity-1.md`.

The workflow is intentionally two-step for every phase:

1. **Planning prompt** — the agent researches the phase, inspects existing code, identifies what is already implemented, resolves conflicts with the EOS-parity direction, and writes an execution plan detailed enough to implement from.
2. **Common implementation prompt** — the agent implements only the approved phase plan, validates it, updates docs/checklists, and does not require another phase-specific implementation prompt.

Do not skip the planning prompt. The repo already has partial implementations in a different shape. Each phase must first discover what exists, decide what to reuse, what to replace, and what must become provider-adapter-ready for future Akasha-native production.

## Model routing recommendation

Use different model families for planning, implementation, and review when your CLI supports it. The goal is not brand loyalty; it is adversarial cross-checking.

| Activity | Default model choice | Why |
|---|---|---|
| Phase planning / architecture | Claude Opus-class model if available | Best for long-context architecture, dependency analysis, and identifying hidden coupling. |
| Backend/frontend implementation | GPT-5-class or Claude Sonnet-class model | Strong code generation and debugging; implement from the approved plan, not from a second phase-specific prompt. |
| Review / adversarial audit | Different family than implementer; prefer Opus if implementation used GPT, or GPT if implementation used Claude | Avoid same-model blind spots. |
| Test failure debugging | GPT-5-class model, then cross-check with Opus if failures are architectural | Good at iterative error repair. |
| Documentation cleanup | Any strong general model | Lower risk; still validate links and front matter. |

Recommended default loop:

1. Planning: `Opus`.
2. Plan review: `GPT`.
3. Implementation: `GPT` or `Sonnet` using the approved plan plus the common implementation prompt.
4. Implementation review: model family not used for implementation.
5. Final validation: same implementation model may fix issues, but review model must approve before moving to the next phase.

## Non-negotiable global instructions for every phase

Paste these instructions at the top of every planning, implementation, and review prompt.

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

## Common implementation prompt for approved phase plans

Use this prompt for implementation of any phase after the phase plan has passed review. Do not add a separate phase-specific implementation prompt; the approved phase plan is the implementation specification.

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Implement the approved execution plan for Phase <N> only.

Inputs:
- The approved Phase <N> execution plan.
- The adversarial plan review result and any required corrections.
- The phase source-of-truth docs referenced by the plan.

Implementation rules:
1. Re-read the approved plan before editing and treat it as the scope boundary.
2. Inspect each target file before changing it; do not assume blank-slate code.
3. Reuse production-relevant Akasha logic and replace only logic the plan explicitly marks as incorrect, temporary, or out of scope.
4. Keep provider access server-side and adapter-based; never add frontend direct EOS calls or raw provider DTO coupling.
5. Do not introduce extra product scope, routes, dependencies, migrations, or UI beyond the approved plan.
6. Add/update tests, docs, migrations, and checklists exactly where the plan requires them.
7. If implementation evidence proves the approved plan is wrong, stop and revise the plan before continuing.

Validation rules:
- Run every validation command listed in the approved plan.
- Run security/secret-leak checks when the phase touches providers, exports, tile URLs, auth, settings, or logs.
- If a validation command cannot run in the environment, explain why and provide the closest completed check.
- Do not mark the phase complete while tests or review blockers remain unresolved.

Final response required:
- Files changed.
- Approved-plan scope implemented.
- Existing logic reused/replaced.
- Tests and validation commands run, with results.
- Security/doc/checklist checks performed.
- Follow-ups that belong to later phases only.
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

## Phase 3 prompts — Product shell and navigation

### Phase 3 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 3 only: add EOS-like product navigation/routes while preserving the current map workspace.

Inspect:
- docs/impl-plan/feature-eos-crop-monitoring-parity-1.md Phase 3.
- Current App.tsx, main.tsx, MapPage.tsx, frontend components/tests/package.json.
- EOS UI findings in docs/eos-crop-monitoring-replication-research.md.

Decide in the plan:
1. Route map, shell layout, and lazy-loading approach.
2. Routing dependency decision and install/test impact.
3. How root URL and existing MapPage stay working.
4. Placeholder policy for future modules.
5. Exact files to create/update, tests, lint/build/browser-smoke commands.
6. Risks, rollback notes, and later-phase dependencies.

Do not edit files in this planning step.
```

## Phase 4 prompts — Monitoring map parity

### Phase 4 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 4 only: make Monitoring field-aware with scenes, RGB/index layers, cloud controls, and download affordances.

Inspect:
- Phase 4 tasks, Phase 1 selected-field state, and Phase 2 provider interfaces.
- Existing source/date/tile flow: product.py, catalog_resolver.py, tiles.py, api.ts, queries.ts, MapPage.tsx, DisplayModeToggle, TimelineBar, Legend, MapControls.
- EOS scene/render docs only if endpoint details are needed.

Decide in the plan:
1. Field scene API and normalized DTOs.
2. Same-origin tile proxy/template behavior with provider details kept server-side.
3. Frontend selected-field scene flow, display modes, timeline, cloud controls, and RGB default.
4. Native/global scene fallback when no field is selected.
5. Exact files, tests, lint/build/browser checks, and security leak checks.
6. Risks, rollback notes, and Phase 5/6 follow-ups.

Do not edit files in this planning step.
```

## Phase 5 prompts — Field analytics and trends

### Phase 5 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 5 only: replace IndexPanel placeholder with selected-field statistics and multi-temporal analytics trends.

Inspect:
- Native /api/indices/statistics flow, raster indices, and cloud/coverage metadata.
- Current IndexPanel, selected-field state, Phase 2 analytics provider, and Phase 4 field scenes.
- EOS Field Analytics/Statistics docs only if provider endpoint details are needed.

Decide in the plan:
1. Native single-date field statistics route and any approved index additions.
2. Provider-backed trend route and normalized trend-point DTO.
3. Chart dependency recommendation or no-dependency alternative.
4. Analytics panel states, metadata display, and safe wording/limitations.
5. Exact files, backend/frontend tests, lint/build/manual smoke commands.
6. Risks, rollback notes, and deferred analytics sections.

Do not edit files in this planning step.
```

## Phase 6 prompts — Cloud masking, legends, exports

### Phase 6 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 6 only: add cloud-mask options, legend behavior, and selected field/date/index exports.

Inspect:
- Current cloud usability logic, Legend, DisplayModeToggle, analytics state, provider tile/analytics routes.
- Native SCL masking rules and EOS cloud/download docs only if mapping details are needed.

Decide in the plan:
1. CloudMaskOptions DTO and EOS/native mapping.
2. Legend/color-ramp behavior for RGB and index displays.
3. Export route contracts, first export formats, and provider-vs-native ownership.
4. Frontend download menu/actions and unavailable-state policy.
5. Exact files, tests, lint/build/export smoke, and secret/internal URL checks.
6. Risks, rollback notes, and unsupported export follow-ups.

Do not edit files in this planning step.
```

## Phase 7 prompts — Weather analytics and forecast

### Phase 7 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 7 only: add field weather forecast and historical weather analytics via normalized provider contracts.

Inspect:
- Phase 2 weather provider foundation and product-shell weather routes/placeholders.
- EOS Weather docs only if endpoint details are needed.
- Future native replacement candidates: IMD/GFS/ECMWF/Open-Meteo/SMAP.

Decide in the plan:
1. Forecast/history DTOs and required field context.
2. BFF weather routes, cache/stale-time/rate-limit behavior, and provider-unavailable handling.
3. Frontend forecast and weather analytics pages/charts.
4. Exact files, mocked backend tests, frontend tests, lint/build commands.
5. Risks, rollback notes, and native replacement follow-ups.

Do not edit files in this planning step.
```

## Phase 8 prompts — VRA vegetation zoning

### Phase 8 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 8 only: implement vegetation-based VRA zoning creation, retrieval, display, polling, and export.

Inspect:
- Phase 2 zoning provider foundation, Phase 4 field scenes, and Phase 6 export patterns.
- EOS Zoning docs only if async/job details are needed.
- Native replacement path using Akasha k-means/quantile zoning.

Decide in the plan:
1. Zoning request/response/status DTOs and normalized lifecycle.
2. Job tracking schema needs, migrations, and polling behavior.
3. BFF create/list/get/export route contracts.
4. VRA Vegetation page, zone overlay rendering, and related VRA placeholders.
5. Exact files, backend/frontend tests, manual smoke, and security checks.
6. Risks, rollback notes, and native zoning follow-ups.

Do not edit files in this planning step.
```

## Phase 9 prompts — Reports and leaderboard

### Phase 9 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 9 only: build Akasha-native field leaderboard and reporting from normalized field, analytics, weather, and activity data.

Inspect:
- Implemented analytics/weather/field metadata/operations outputs.
- EOS leaderboard/reporting UI findings.

Decide in the plan:
1. Leaderboard DTO, transparent scoring formula, and missing-value policy.
2. Report template persistence/schema and CSV-first export plan.
3. BFF routes and frontend leaderboard/reporting pages.
4. Exact files, tests, export smoke, lint/build commands.
5. Risks, rollback notes, and XLSX/PDF/later reporting follow-ups.

Do not edit files in this planning step.
```

## Phase 10 prompts — Operations, scout tasks, data manager, field groups

### Phase 10 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 10 only: add Akasha-native operations modules for activity log, scout tasks, data manager, connections placeholder, and field groups.

Inspect:
- Current field/plot schema, frontend shell routes, and EOS UI findings for operations/data modules.

Decide in the plan:
1. Schema boundaries for activities, tasks, field groups, uploaded datasets, and attachment metadata.
2. CRUD/upload API routes and validation/security constraints.
3. Frontend page structure for Activity Log, Scout Tasks, Data Manager, Connections, and Field Groups.
4. Import parsing scope versus metadata-only storage; John Deere placeholder policy.
5. Exact files, migrations, backend/frontend tests, upload tests, lint/build commands.
6. Risks, rollback notes, and deferred integrations.

Do not edit files in this planning step.
```

## Phase 11 prompts — Risk, crop stages, diseases/pests, India path

### Phase 11 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 11 only: add transparent decision-support foundations and India-specific productization path.

Inspect:
- Implemented analytics, weather, scout task, field metadata outputs, and EOS disease/pest/risk UI findings.

Decide in the plan:
1. Risk scoring inputs, formula, confidence, and limitations.
2. Crop-stage timeline model and required field/crop metadata.
3. Diseases & Pests page shell and safe non-diagnostic wording.
4. India-specific productization doc outline.
5. Exact files, backend/frontend tests, Markdown diagnostics.
6. Risks, rollback notes, and agronomic validation follow-ups.

Do not edit files in this planning step.
```

## Phase 12 prompts — Auth, teams, API/admin, notifications

### Phase 12 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 12 only: add ownership, collaboration, account/admin, API settings, and notification foundations for pilot readiness.

Inspect:
- All user-owned data introduced so far and Railway/deployment constraints if relevant.

Decide in the plan:
1. Auth provider recommendation and safe local-dev behavior.
2. User/team schema, ownership columns, migrations, and authorization checks.
3. Account/team/settings/API pages without exposing provider keys.
4. Notification schema, routes, and UI panel.
5. AI assistant shell policy, if any, using only evidence from Akasha APIs.
6. Exact files, security tests, frontend tests, secret checks, lint/build commands.
7. Risks, rollback notes, and migration/pilot-readiness limitations.

Do not edit files in this planning step.
```

## Phase 13 prompts — End-to-end verification and native replacement readiness

### Phase 13 planning prompt

```text
Use the global instructions from docs/prompts/eos-parity-phase-wise-agent-prompts.md.

Plan Phase 13 only: verify the full EOS-like workflow, update acceptance evidence, and prove EOS remains replaceable.

Inspect:
- All changed docs/code from Phases 0-12.
- docs/eos-parity-acceptance-matrix.md.
- Provider interfaces and frontend DTOs for EOS leakage.

Decide in the plan:
1. Full validation command sequence and failure policy.
2. Mocked E2E workflow and optional real-EOS smoke guarded by configured EOS_API_KEY.
3. Manual browser QA steps if browser tools are available.
4. Acceptance matrix update/evidence plan.
5. Native replacement map updates for architecture docs.
6. Secret/internal URL leakage checks and release/demo readiness checklist.

Do not edit files in this planning step.
```

## How to run the phase loop

For each phase:

1. Paste the global instructions plus the phase planning prompt.
2. Run the planning model, preferably Opus-class.
3. Run the plan review gate with a different model.
4. If blocked, ask the planning model to revise the plan.
5. Once approved, paste the global instructions plus the common implementation prompt and attach the approved phase plan.
6. Run implementation with GPT/Sonnet-class model.
7. Run the implementation review gate with a different model.
8. Fix blockers by updating implementation only if still within the approved plan; otherwise revise the plan first.
9. Run tests and diagnostics from the approved plan.
10. Commit or checkpoint only after the phase is approved.
11. Move to the next phase.

Do not merge phases unless the phase plan explicitly proves the merged scope is smaller and safer than running them separately.
