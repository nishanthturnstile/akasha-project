---
goal: Build an internal admin-only ingestion orchestration console for scheduler jobs, schedules, and pipeline timelines
version: 1.0
date_created: 2026-06-25
last_updated: 2026-06-25
owner: Akasha Engineering (BFF + frontend + ingestion operations)
tags: [feature, admin, ingestion, scheduler, orchestration, observability, security, frontend]
---

# Introduction

This plan moves all ingestion/satellite orchestration monitoring out of the product-facing monitoring surface and into an **internal admin-only console**. The console may live in the same React/FastAPI application for development and operations convenience, but it must not be exposed as a public/customer feature and must not be visible to non-admin users.

The current codebase already supports role-based access control. Backend memberships use the roles `owner`, `admin`, `member`, and `viewer` in `apps/api/app/models.py`, and `apps/api/app/auth.py` exposes `require_role("owner", "admin")`. Frontend `/api/account/me` data already includes `currentTeam.role` in `apps/frontend/src/types/api.ts`. Therefore this plan uses existing owner/admin RBAC and does **not** introduce a static email allowlist.

Current ingestion monitoring pages and APIs exist, but they are under `/monitoring/*` and are not strictly admin-only. This plan makes `/admin/ingestion/*` the canonical operator surface, keeps any old `/monitoring/ingestion-jobs` route only as a temporary admin-gated compatibility alias during migration, and adds a visual pipeline/timeline view for scheduler jobs.

## 1. Requirements & Constraints

### Functional requirements

- **REQ-001**: The orchestration console must be internal/admin-only and must not appear in normal product navigation for `member` or `viewer` users.
- **REQ-002**: The canonical route namespace must be `/admin/ingestion/*`.
- **REQ-003**: Existing `/monitoring/ingestion-jobs` and `/monitoring/ingestion-jobs/:jobId` routes may remain temporarily, but they must be owner/admin gated and redirect or alias to the admin routes.
- **REQ-004**: Product-facing monitoring remains focused on crop/field monitoring. Ingestion scheduler health, source freshness, job queues, and pipeline events belong to the admin console.
- **REQ-005**: Owner/admin users can view admin ingestion routes and APIs. Member/viewer users cannot view admin nav, cannot open admin routes, and cannot call admin ingestion monitoring APIs.
- **REQ-006**: The admin console must show what is scheduled, what ran, current state, job output, validation outcome, and failure reason.
- **REQ-007**: The admin job detail page must visualize a stage pipeline: planned → approved runtime → lock → search → select → download → prepare → composite → verify → upload → STAC → ledger.
- **REQ-008**: The admin schedules view must show source/AOI schedule state, last run, last success, last failure, next due, cadence, due/overdue, product exposure, and validation state.
- **REQ-009**: Admin UI must be read-only in the first implementation. Retry/rerun/live actions are out of scope for this plan because they can trigger provider calls and require a separate safety design.
- **REQ-010**: If local development uses `AUTH_MODE=disabled`, the dev user may keep owner role through the existing development auth behavior. Deployed environments must rely on real auth and roles.

### Security requirements

- **SEC-001**: Backend APIs for ingestion schedules, ingestion jobs, ingestion job details, ingestion job events, and admin source scheduler health must require `require_role("owner", "admin")`.
- **SEC-002**: Frontend route gating is required for UX, but backend role gating is the source of truth.
- **SEC-003**: Static email allowlists must not be used because RBAC already exists. If a future emergency allowlist is needed, it requires a separate plan and must live in backend configuration only.
- **SEC-004**: The frontend must never receive raw server filesystem paths, `/srv/akasha` paths, `/tmp` paths, Windows local paths, signed provider URLs, bearer tokens, provider credentials, object-store credentials, internal hostnames, or full unredacted logs.
- **SEC-005**: Job event payloads read from `events.jsonl` must be recursively sanitized before returning to the browser.
- **SEC-006**: Admin route visibility must not be treated as security. Hidden nav is required, but APIs must still reject non-admin requests.
- **SEC-007**: The admin console must stay same-origin under the app/gateway. Do not create a public service/domain for scheduler artifacts.

### UI/UX requirements

- **UI-001**: Admin ingestion navigation must be visually and structurally separate from product monitoring navigation.
- **UI-002**: Product nav label `Monitoring` must remain field/crop/product-oriented. It must not contain ingestion job queue links.
- **UI-003**: Admin pages must show an internal-operations label such as `Admin · Internal operations`.
- **UI-004**: Job status colors must be consistent: green for succeeded, blue for running, amber for skipped/gated/deferred, red for failed/validation failed, gray for not reached.
- **UI-005**: Pipeline stages must be understandable without reading logs. Each stage must show state, timestamp when available, and a short message or metric.
- **UI-006**: Clicking a pipeline stage should focus or link to the relevant existing detail section where practical: search/select → Candidates, download → Downloads, verify → Verification, ledger → Ledger, failure → Logs.

### Data requirements

- **DATA-001**: Use existing scheduler artifacts as the source of truth: `request.json`, `status.json`, `result.json`, `observability.json`, `events.jsonl`, `scheduler_ledger.json`, and SQLite `scheduler_jobs` ledger.
- **DATA-002**: The first timeline implementation may derive stages from existing job detail fields when `events.jsonl` is missing.
- **DATA-003**: The event endpoint must cap returned events to a deterministic safe limit, initially 200 events.
- **DATA-004**: Malformed `events.jsonl` lines must not crash the endpoint. They should be skipped or returned as sanitized parse-error events with no raw line content.

### Constraints

- **CON-001**: Do not introduce Better Auth or another auth framework. Akasha uses existing hand-rolled cookie-session auth and team RBAC.
- **CON-002**: Do not add public access to MinIO, pgSTAC, TiTiler, Bhoonidhi, or scheduler artifact directories.
- **CON-003**: Do not add live retry/rerun actions in this plan.
- **CON-004**: Do not mix field/crop monitoring UX with ingestion/operator monitoring UX.
- **CON-005**: Preserve the one-public-service rule: browser calls only same-origin `/api/*` and `/tiles/*` through the gateway.
- **CON-006**: Keep existing monitoring pages functional during migration, but make admin routes canonical.

### Existing code facts verified on 2026-06-25

- **FACT-001**: `apps/api/app/models.py` defines membership roles with DB constraint `role IN ('owner', 'admin', 'member', 'viewer')`.
- **FACT-002**: `apps/api/app/auth.py` defines `require_role(*roles)` and returns HTTP 403 via `forbidden()` for insufficient roles.
- **FACT-003**: `apps/api/app/routers/account_router.py` returns `current_team={id, name, role}` from `/api/account/me`.
- **FACT-004**: `apps/frontend/src/types/api.ts` defines `AccountMe.currentTeam.role`.
- **FACT-005**: `apps/frontend/src/components/auth/AuthGate.tsx` currently gates login/onboarding but does not gate roles.
- **FACT-006**: `apps/frontend/src/routes/ProductRoutes.tsx` currently mounts ingestion job pages under `/monitoring/ingestion-jobs`.
- **FACT-007**: `apps/frontend/src/routes/productNavigation.ts` currently keeps product monitoring and utility navigation in one list and has no role-aware item model.

## 2. Implementation Steps

### Implementation Phase 1 — Backend admin role gate

- GOAL-001: Make the backend APIs authoritative for admin-only access before adding or moving UI routes.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Modify `apps/api/app/ingestion_jobs.py` so the router dependencies use `Depends(require_role("owner", "admin"))` instead of `Depends(get_current_team)`. Import `require_role` from `app.auth`. All existing `/api/monitoring/ingestion-schedules`, `/api/monitoring/ingestion-jobs`, and `/api/monitoring/ingestion-jobs/{job_id}` endpoints must reject `member` and `viewer` roles with 403. | | |
| TASK-002 | Add BFF tests in `apps/api/tests/test_ingestion_jobs.py` that monkeypatch auth dependencies or use existing auth test helpers to prove owner/admin can access ingestion job endpoints and member/viewer receive 403. Cover list, detail, and schedules. | | |
| TASK-003 | Decide the source-monitoring admin boundary in code: operational ingestion fields (`latestSchedulerJobId`, `latestSchedulerJobState`, `schedulerNextDueAt`, `schedulerIsDue`, `schedulerIsOverdue`, scheduler failure summaries) must be moved to an admin-only endpoint or guarded behind owner/admin role. Implement the simpler first version by adding owner/admin role gating to `apps/api/app/source_monitoring.py` if the page remains an operator page. | | |
| TASK-004 | Add or update tests in `apps/api/tests/test_source_monitoring.py` proving non-admin roles cannot access scheduler/source operational monitoring when it is admin-only. | | |

### Implementation Phase 2 — Canonical admin route namespace

- GOAL-002: Move ingestion/scheduler pages to `/admin/ingestion/*` while keeping temporary admin-gated aliases for current development routes.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Modify `apps/frontend/src/components/auth/AuthGate.tsx` to accept `requiredRoles?: string[]`. If `account.data.currentTeam.role` is not in `requiredRoles`, render a redirect to `MAIN_MONITORING_ROUTE` or a small `Forbidden` panel. The redirect/panel must not reveal admin page data. | | |
| TASK-006 | Add a focused frontend test for `AuthGate` or route behavior proving a `member` role cannot render admin children and an `owner` role can. Use existing `/api/account/me` mock patterns from `apps/frontend/src/routes/ProductRoutes.test.tsx`. | | |
| TASK-007 | Modify `apps/frontend/src/routes/ProductRoutes.tsx` to add canonical admin routes: `/admin/ingestion`, `/admin/ingestion/jobs`, `/admin/ingestion/jobs/:jobId`, and `/admin/ingestion/schedules`. Wrap these routes with `AuthGate requireOnboardingComplete requiredRoles={["owner", "admin"]}`. | | |
| TASK-008 | Keep `/monitoring/ingestion-jobs` and `/monitoring/ingestion-jobs/:jobId` only as temporary owner/admin-gated aliases. Implement them as redirects to `/admin/ingestion/jobs` and `/admin/ingestion/jobs/:jobId`, or keep rendering the same components behind the admin gate for one development cycle. | | |
| TASK-009 | Add `apps/frontend/src/routes/ProductRoutes.test.tsx` tests proving `/admin/ingestion/jobs` renders for owner/admin and redirects/blocks for member/viewer. Add tests proving `/monitoring/ingestion-jobs` does not expose content to member/viewer. | | |

### Implementation Phase 3 — Admin-only navigation model

- GOAL-003: Separate operator/admin navigation from product monitoring navigation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | Extend `apps/frontend/src/routes/productNavigation.ts` item types with optional `requiredRoles?: string[]` and optional `surface?: "product" | "admin"`. Do not show admin items to non-admin roles. | | |
| TASK-011 | Add an admin navigation group named `Admin` or `Operations Admin` with items: `Ingestion overview` at `/admin/ingestion`, `Ingestion jobs` at `/admin/ingestion/jobs`, and `Schedules` at `/admin/ingestion/schedules`. Each item must use `requiredRoles: ["owner", "admin"]` and `surface: "admin"`. | | |
| TASK-012 | Modify `apps/frontend/src/components/shell/AppShell.tsx` to filter navigation groups and mobile nav items using `account.data.currentTeam.role`. The `Monitoring` product group must keep field/crop/product pages only and must not include ingestion job queue links. | | |
| TASK-013 | Add `AppShell` or `ProductRoutes` tests proving admin nav appears for owner/admin and is hidden for member/viewer. | | |

### Implementation Phase 4 — Backend job events endpoint

- GOAL-004: Expose a safe, bounded, redacted event stream for pipeline/timeline visualization.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-014 | Add response models in `apps/api/app/ingestion_jobs.py`: `IngestionJobEvent` and `IngestionJobEventsResponse`. Required fields: `timestamp`, `eventType`, `stage`, `status`, `message`, and `payload`. `payload` must be sanitized using the existing recursive monitoring sanitizer. | | |
| TASK-015 | Add `GET /api/monitoring/ingestion-jobs/{job_id}/events` in `apps/api/app/ingestion_jobs.py`. It must validate `job_id` using the same traversal checks as job detail, read `<jobs_dir>/<job_id>/events.jsonl`, cap to 200 events, skip malformed JSON lines, and return `status="ok"` with an empty list if no events file exists. | | |
| TASK-016 | Map raw scheduler event types to normalized pipeline stages. Initial mapping: `job_created -> planned`, `status_change -> running|terminal`, `dry_run_plan -> planned`, `search_done -> search`, `download_progress -> download`, `validation_result -> verify`, `error -> failed`. Unknown event types use `stage="unknown"` and `status="unknown"`. | | |
| TASK-017 | Add tests in `apps/api/tests/test_ingestion_jobs.py` for the events endpoint: owner/admin access, member/viewer 403, missing events file, malformed line skip, path traversal rejection, and redaction of `/srv/akasha`, `/tmp`, `C:\\Users`, bearer token, password, signed URL, and internal host values. | | |

### Implementation Phase 5 — Pipeline/timeline visualization in job detail

- GOAL-005: Make one job understandable at a glance with a visual stage timeline.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Add frontend types in `apps/frontend/src/types/api.ts`: `IngestionJobEvent`, `IngestionJobEventsResponse`, `PipelineStageId`, and `PipelineStageState`. | | |
| TASK-019 | Add `getIngestionJobEvents(jobId: string)` in `apps/frontend/src/lib/api.ts` and `useIngestionJobEvents(jobId)` in `apps/frontend/src/lib/queries.ts`. | | |
| TASK-020 | Create `apps/frontend/src/pages/monitoring/components/OrchestrationPipeline.tsx`. It must accept `job: IngestionJobDetail` and `events?: IngestionJobEvent[]`. It must render ordered stages: planned, approved_runtime, lock, search, select, download, prepare, composite, verify, upload, stac, ledger. | | |
| TASK-021 | Implement event-first stage derivation in `OrchestrationPipeline.tsx`. If no events exist, derive fallback stages from job fields: `state`, `foundCount`, `selectedCount`, `downloadedCount`, `verificationSummary`, `artifactHandles`, `ledgerRows`, and `failureKind`. | | |
| TASK-022 | Modify `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx` to add a `Pipeline` tab before `Summary`. The tab must render `OrchestrationPipeline` and show an admin-only/internal label. | | |
| TASK-023 | Add tests in `apps/frontend/src/pages/monitoring/IngestionJobDetail.test.tsx` proving the Pipeline tab renders success, running, failed, skipped-gated, and missing-events fallback states without showing raw paths. | | |

### Implementation Phase 6 — Admin schedule/cadence overview

- GOAL-006: Provide a clear view of what is scheduled next and what is overdue.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-024 | Create or adapt `apps/frontend/src/pages/monitoring/IngestionSchedules.tsx` for `/admin/ingestion/schedules`. It must call the existing `useIngestionSchedules` query and render source/AOI schedule rows. | | |
| TASK-025 | The schedules page must display: source ID, provider, AOI, lifecycle state, schedule state, product exposure, validation state, last run, last success, last failure, next due, next window, cadence days, due reason, due/overdue status. | | |
| TASK-026 | Add filters for source ID, provider, schedule state, product exposure, due/overdue, and validation state. Keep filters client-side initially. | | |
| TASK-027 | Add frontend tests for schedule rendering, unconfigured state, empty state, due/overdue badge rendering, and admin-only route access. | | |

### Implementation Phase 7 — Admin overview landing page

- GOAL-007: Provide `/admin/ingestion` as the console entry point and avoid mixing it with crop/field monitoring.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-028 | Create `apps/frontend/src/pages/monitoring/AdminIngestionOverview.tsx` or rename/reuse `MonitoringGlobalView.tsx` as the admin ingestion overview. Recommendation: create a thin `AdminIngestionOverview.tsx` wrapper first to avoid a large rename. | | |
| TASK-029 | The admin overview must show high-level cards: scheduler status, due/overdue count, failed job count, latest successful job, latest failed job, and source health summary. | | |
| TASK-030 | Link overview cards to `/admin/ingestion/jobs`, `/admin/ingestion/schedules`, and latest job details. | | |
| TASK-031 | Add tests proving the overview renders for owner/admin only and does not appear under product `Monitoring` navigation for member/viewer users. | | |

### Implementation Phase 8 — Documentation and route migration cleanup

- GOAL-008: Document the admin-only boundary and prepare removal of old monitoring aliases.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | Update `docs/satellite-ingestion-orchestration-and-scheduler.md` to state that visual orchestration is an internal owner/admin console under `/admin/ingestion/*`, not a public product feature. | | |
| TASK-033 | Update `docs/staging-ingestion-developer-guide.md` with operator/admin access steps and clarify that normal product users do not see ingestion orchestration. | | |
| TASK-034 | Update `docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md` to replace old public/product monitoring ambiguity with admin-only console requirements. | | |
| TASK-035 | Add a deprecation note for `/monitoring/ingestion-jobs` aliases in docs and tests. The final target is to remove ingestion job routes from the `/monitoring/*` product namespace after the admin routes are stable. | | |

### Implementation Phase 9 — Verification and release gates

- GOAL-009: Prove the admin console is secure, useful, and non-public before deployment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-036 | Run backend focused tests: `cd apps/api && python -m pytest tests/test_ingestion_jobs.py tests/test_source_monitoring.py -q`. Expected: all pass, including owner/admin allow and member/viewer deny tests. | | |
| TASK-037 | Run backend full tests: `cd apps/api && python -m pytest -q`. Expected: all pass. | | |
| TASK-038 | Run root scheduler tests: `python -m pytest tests/ -q`. Expected: all pass except known skips. | | |
| TASK-039 | Run lint: `python -m ruff check apps/api services/ingestion scripts tests`. Expected: all checks pass. | | |
| TASK-040 | Run frontend focused tests: `cd apps/frontend && corepack yarn vitest run src/pages/monitoring/IngestionJobDetail.test.tsx src/pages/monitoring/IngestionJobsList.test.tsx src/pages/monitoring/MonitoringGlobalView.test.tsx src/routes/ProductRoutes.test.tsx src/components/shell/AppShell.test.tsx`. Expected: all pass. | | |
| TASK-041 | Run frontend full verification: `cd apps/frontend && corepack yarn test && corepack yarn build`. Expected: tests pass and production build succeeds. | | |
| TASK-042 | Run slice validators: `python scripts/validate_slice0.py`, `python scripts/validate_slice1.py`, `python scripts/validate_slice2.py`. Expected: all pass. | | |
| TASK-043 | Manual verification with an owner/admin user: admin nav is visible, `/admin/ingestion/*` routes open, pipeline tab renders, and API calls return 200. | | |
| TASK-044 | Manual verification with a member/viewer user: admin nav is hidden, `/admin/ingestion/*` routes are blocked, old `/monitoring/ingestion-jobs` aliases are blocked, and API calls return 403. | | |

## 3. Alternatives

- **ALT-001**: Use a static backend email allowlist. Rejected because the application already supports team roles, membership role constraints, `require_role()`, and frontend account role data. Static email lists would duplicate RBAC and create drift.
- **ALT-002**: Keep ingestion job UI under `/monitoring/*`. Rejected because product monitoring is for crop/field health and must not be mixed with internal ingestion operations.
- **ALT-003**: Build a separate admin service/domain for orchestration. Rejected for now because same-origin authenticated admin routes are simpler and preserve the one-public-service rule.
- **ALT-004**: Add retry/rerun buttons in the first admin console release. Rejected because live actions can trigger provider calls and need separate approved-runtime, lock, and audit safety design.
- **ALT-005**: Expose raw job artifacts directly to the browser. Rejected because scheduler artifacts can include internal paths and operational details; the BFF must return redacted summaries and opaque handles only.

## 4. Dependencies

- **DEP-001**: Existing auth/team RBAC in `apps/api/app/auth.py`, `apps/api/app/models.py`, and account APIs.
- **DEP-002**: Existing `/api/account/me` response with `currentTeam.role` consumed by frontend.
- **DEP-003**: Existing scheduler job artifacts under configured `scheduler_jobs_dir`.
- **DEP-004**: Existing `events.jsonl` writer behavior in `services/ingestion/akasha_ingest/jobs.py`.
- **DEP-005**: Existing frontend route structure in `apps/frontend/src/routes/ProductRoutes.tsx` and shell navigation in `apps/frontend/src/components/shell/AppShell.tsx`.
- **DEP-006**: Existing monitoring pages `MonitoringGlobalView`, `IngestionJobsList`, and `IngestionJobDetail`.
- **DEP-007**: Existing BFF redaction and sanitization helpers in `apps/api/app/ingestion_jobs.py`.
- **DEP-008**: Existing TanStack Query setup in `apps/frontend/src/lib/queries.ts`.

## 5. Files

- **FILE-001**: `docs/impl-plan/feature-admin-ingestion-orchestration-console-1.md` — this implementation plan.
- **FILE-002**: `apps/api/app/auth.py` — existing RBAC dependency `require_role`; no new auth framework required.
- **FILE-003**: `apps/api/app/ingestion_jobs.py` — add owner/admin router dependency and events endpoint.
- **FILE-004**: `apps/api/app/source_monitoring.py` — gate or move operational scheduler fields to admin-only access.
- **FILE-005**: `apps/api/tests/test_ingestion_jobs.py` — add admin role, events, and redaction tests.
- **FILE-006**: `apps/api/tests/test_source_monitoring.py` — add admin-only source scheduler monitoring tests.
- **FILE-007**: `apps/frontend/src/components/auth/AuthGate.tsx` — add optional role-gating support.
- **FILE-008**: `apps/frontend/src/routes/ProductRoutes.tsx` — add `/admin/ingestion/*` routes and temporary admin-gated aliases.
- **FILE-009**: `apps/frontend/src/routes/productNavigation.ts` — add admin navigation metadata and separate admin ingestion items.
- **FILE-010**: `apps/frontend/src/components/shell/AppShell.tsx` — filter admin navigation by `currentTeam.role`.
- **FILE-011**: `apps/frontend/src/types/api.ts` — add ingestion event and pipeline types.
- **FILE-012**: `apps/frontend/src/lib/api.ts` — add events endpoint client.
- **FILE-013**: `apps/frontend/src/lib/queries.ts` — add events query hook.
- **FILE-014**: `apps/frontend/src/pages/monitoring/IngestionJobsList.tsx` — reuse as admin job queue page.
- **FILE-015**: `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx` — add Pipeline tab.
- **FILE-016**: `apps/frontend/src/pages/monitoring/MonitoringGlobalView.tsx` — reuse or wrap as admin ingestion overview.
- **FILE-017**: `apps/frontend/src/pages/monitoring/IngestionSchedules.tsx` — create schedules/cadence page.
- **FILE-018**: `apps/frontend/src/pages/monitoring/AdminIngestionOverview.tsx` — create admin landing page wrapper if needed.
- **FILE-019**: `apps/frontend/src/pages/monitoring/components/OrchestrationPipeline.tsx` — create visual stage timeline.
- **FILE-020**: `apps/frontend/src/pages/monitoring/components/PipelineStagePill.tsx` — create reusable stage status component if useful.
- **FILE-021**: `apps/frontend/src/pages/monitoring/components/ScheduleDueBadge.tsx` — create due/overdue badge if useful.
- **FILE-022**: `apps/frontend/src/pages/monitoring/IngestionJobDetail.test.tsx` — add Pipeline tab tests.
- **FILE-023**: `apps/frontend/src/pages/monitoring/IngestionJobsList.test.tsx` — update route expectations to admin namespace.
- **FILE-024**: `apps/frontend/src/pages/monitoring/MonitoringGlobalView.test.tsx` — update admin-only source-health expectations.
- **FILE-025**: `apps/frontend/src/routes/ProductRoutes.test.tsx` — add admin route allow/deny tests.
- **FILE-026**: `apps/frontend/src/components/shell/AppShell.test.tsx` — add admin nav visibility tests.
- **FILE-027**: `docs/satellite-ingestion-orchestration-and-scheduler.md` — document admin-only route model.
- **FILE-028**: `docs/staging-ingestion-developer-guide.md` — document operator/admin console usage.
- **FILE-029**: `docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md` — update scheduler plan status and admin-only UI boundary.

## 6. Testing

- **TEST-001**: `cd apps/api && python -m pytest tests/test_ingestion_jobs.py -q` must prove owner/admin can access ingestion job APIs and member/viewer cannot.
- **TEST-002**: `cd apps/api && python -m pytest tests/test_source_monitoring.py -q` must prove scheduler operational source monitoring is admin-only or does not leak scheduler fields to non-admin users.
- **TEST-003**: `cd apps/api && python -m pytest tests/test_ingestion_jobs.py::test_job_events_redacts_paths_and_secrets -q` must prove the events endpoint redacts `/srv/akasha`, `/tmp`, `C:\\Users`, bearer tokens, passwords, signed URLs, and internal hosts.
- **TEST-004**: `cd apps/api && python -m pytest -q` must pass.
- **TEST-005**: `python -m pytest tests/ -q` must pass the root scheduler/ingestion tests.
- **TEST-006**: `python -m ruff check apps/api services/ingestion scripts tests` must pass.
- **TEST-007**: `cd apps/frontend && corepack yarn vitest run src/routes/ProductRoutes.test.tsx src/components/shell/AppShell.test.tsx` must prove admin routes/nav are visible only to owner/admin.
- **TEST-008**: `cd apps/frontend && corepack yarn vitest run src/pages/monitoring/IngestionJobDetail.test.tsx` must prove the Pipeline tab renders stage states and does not show raw paths.
- **TEST-009**: `cd apps/frontend && corepack yarn vitest run src/pages/monitoring/IngestionJobsList.test.tsx src/pages/monitoring/MonitoringGlobalView.test.tsx` must pass after route migration.
- **TEST-010**: `cd apps/frontend && corepack yarn test && corepack yarn build` must pass.
- **TEST-011**: `python scripts/validate_slice0.py && python scripts/validate_slice1.py && python scripts/validate_slice2.py` must pass.
- **TEST-012**: Manual owner/admin verification must confirm `/admin/ingestion`, `/admin/ingestion/jobs`, `/admin/ingestion/jobs/:jobId`, and `/admin/ingestion/schedules` open and show expected data.
- **TEST-013**: Manual member/viewer verification must confirm admin nav is hidden, admin routes are blocked, compatibility aliases are blocked, and admin APIs return 403.

## 7. Risks & Assumptions

- **RISK-001**: Frontend-only role gating could be bypassed. Mitigation: backend `require_role("owner", "admin")` is mandatory and tested.
- **RISK-002**: Existing product monitoring and admin ingestion monitoring can remain visually mixed if routes are not renamed. Mitigation: canonical `/admin/ingestion/*` namespace and admin navigation group.
- **RISK-003**: Event payloads can leak raw paths or secrets. Mitigation: recursive sanitizer, capped events endpoint, and redaction tests.
- **RISK-004**: Renaming routes can break existing test links or development bookmarks. Mitigation: temporary owner/admin-gated aliases from `/monitoring/ingestion-jobs` to `/admin/ingestion/jobs`.
- **RISK-005**: Adding retry actions too early can trigger live provider work accidentally. Mitigation: first admin console release is read-only.
- **RISK-006**: Source monitoring may contain both product-safe and admin-only fields. Mitigation: gate operational source monitoring or split product-safe and admin endpoints.
- **ASSUMPTION-001**: Owner/admin roles are sufficient for the first internal admin console release.
- **ASSUMPTION-002**: A dedicated `operator` role is not required for the first release.
- **ASSUMPTION-003**: Local development may use `AUTH_MODE=disabled`, which returns a dev owner user; this is acceptable for local-only workflows.
- **ASSUMPTION-004**: The same app/gateway remains the only public entry point; admin pages are protected routes, not a separate exposed service.

## 8. Related Specifications / Further Reading

- [Architecture Satellite Ingestion Scheduler Plan](architecture-satellite-ingestion-scheduler-1.md)
- [Satellite Ingestion Orchestration and Scheduler Guide](../satellite-ingestion-orchestration-and-scheduler.md)
- [Staging Ingestion Developer Guide](../staging-ingestion-developer-guide.md)
- [Auth and Team Admin Plan](../auth-team-admin-plan.md)
- [Engineering Do's and Don'ts](../engineering-dos-donts.md)
- [Data Ingestion and Satellite Rules](../data-ingestion-and-satellite-rules.md)
