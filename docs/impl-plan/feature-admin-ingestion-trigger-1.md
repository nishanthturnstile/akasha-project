---
goal: Admin UI Bounded Ingestion Trigger (Option B — inbox + host dispatcher bridge)
version: 1.0
date_created: 2026-06-26
last_updated: 2026-06-26
owner: Akasha ingestion / platform
tags: [feature, infrastructure, ingestion, admin, scheduler]
---

# Introduction

This plan adds an owner/admin-only UI control to trigger a single satellite/source ingestion
run from the existing admin ingestion console, primarily for development, maintenance,
validation, and testing. The browser submits a bounded, validated request to the BFF; the BFF
writes a request file to a writable staging **inbox**; a host-side **dispatcher** picks it up and
launches the existing bounded wrapper (`/opt/akasha/bin/akasha-ingestion-job.sh start`). Job status,
counts, verdict, failure detail, and next-due context are read back through the **already-working**
`/api/monitoring/ingestion-*` endpoints and the existing admin jobs/schedules/detail pages.

The design deliberately keeps Docker, systemd, and SSH **out** of the BFF/API container. The API only
gains write access to a dedicated inbox directory. All existing staging guardrails (single-flight
locks, `ionice`/`nice`, redaction, canonical scheduler ledger, dry-run-first) are preserved by reusing
the existing wrapper/runner chain rather than bypassing it.

## 1. Requirements & Constraints

- **REQ-001**: Provide an admin-only UI action to trigger one source/AOI ingestion run at a time from `/admin/ingestion/*`.
- **REQ-002**: Default every UI-triggered run to `dryRun=true`; a live (non-dry-run) run requires explicit operator confirmation.
- **REQ-003**: Support at least the scheduler-owned ResourceSat sources: `resourcesat-2a-liss3-boa`, `resourcesat-2a-liss4-mx70-l2`, `resourcesat-2a-awifs-boa`, AOI `bangalore-60km`.
- **REQ-004**: After submit, surface the basic operator answers via existing pages: when it ran, source/AOI/window, state, failure kind/message, found/selected/downloaded counts, verdict (`no_new_candidates` vs validation failure vs succeeded), and next due.
- **REQ-005**: The BFF trigger response must link the operator to the relevant job view (filtered jobs list) and must not depend on a BFF-minted job id matching the scheduler job id.
- **REQ-006**: The BFF must validate the requested source/AOI against current scheduler schedule state and reject unknown or non-scheduler-enabled rows.
- **REQ-007**: All numeric inputs (`windowDays`, `limit`, `maxDownloads`, `minCoveragePercent`) must be bounded server-side before a request is written.
- **SEC-001**: The trigger endpoint must be gated by `require_role("owner", "admin")` (same as existing monitoring endpoints).
- **SEC-002**: Responses must never include raw host paths, inbox paths, compose paths, internal hostnames, credentials, signed URLs, or raw logs; reuse existing redaction helpers in `apps/api/app/ingestion_jobs.py`.
- **SEC-003**: The API/BFF container must not receive a Docker socket, systemd access, or SSH keys. Its only new write capability is the dedicated inbox directory.
- **SEC-004**: `sourceId`, `aoiId`, and generated `jobId` must match the safe identifier pattern `^[A-Za-z0-9._-]+$`; `notes` must be length-bounded and sanitized.
- **CON-001**: The BFF/API container currently mounts `/srv/akasha/ingestion:ro`; the inbox must be a **separate** writable path (`/srv/akasha/ingestion-inbox`), not a child of the read-only mount, to avoid nested RO/RW mount conflicts.
- **CON-002**: The manual wrapper (`akasha-ingestion-job.sh`) writes a placeholder under `/srv/akasha/ingestion/jobs` with a `ingest-*` id and a different status schema, while the scheduler runner (`schedule-source --manual`) writes the canonical scheduler job (`job_<ts>_<hex>`) under `/srv/akasha/ingestion/scheduler/jobs` + the SQLite ledger that the BFF reads. The two ids differ, so the UI must correlate by source/AOI + recency, not by the submitted id.
- **CON-002a**: Heavy/direct ingestion has previously wedged the staging VM; all execution must remain on the bounded wrapper/runner path (`ionice`/`nice`, `flock`, single-flight), never direct `docker run`/`docker compose run` from the trigger path.
- **CON-003**: Timer enable/disable and "run all due sources" must remain out of the UI in v1.
- **GUD-001**: Reuse existing patterns: FastAPI `ApiModel` (camelCase aliases), `require_role`, `_validate_job_id_or_raise`, `_redact_*`/`_sanitize_monitoring_value`, TanStack Query hooks, and shadcn UI primitives already used in monitoring pages.
- **GUD-002**: Keep new files small and single-responsibility; prefer a focused trigger router/component over enlarging existing large files.
- **PAT-001**: Follow the existing monitoring router pattern in `apps/api/app/ingestion_jobs.py` (router prefix `/api/monitoring`, role dependency, redaction).
- **PAT-002**: Follow the existing host-script safety pattern in `infra/selfhosted/systemd/akasha-ingestion-job*.sh` (env file source, `flock`, `ionice`/`nice`, `redact_stream`, canonical `/srv/akasha` paths).

## 2. Implementation Steps

### Implementation Phase 1 — Backend trigger contract

- GOAL-001: Add a bounded, validated, admin-only trigger endpoint that writes a normalized request file to the inbox and returns a safe, link-bearing acknowledgment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add config field `ingestion_job_inbox_dir` (env `INGESTION_JOB_INBOX_DIR`, default `/srv/akasha/ingestion-inbox`) to `apps/api/app/config.py`, mirroring the docstring style of `scheduler_jobs_dir`/`scheduler_job_ledger_path`. | | |
| TASK-002 | Add `TriggerIngestionJobRequest` Pydantic model (extends `ApiModel`) in `apps/api/app/ingestion_jobs.py` with fields: `source_id: str`, `aoi_id: str = "bangalore-60km"`, `window_days: int = Field(12, ge=1, le=90)`, `window_start: str | None = None`, `window_end: str | None = None`, `dry_run: bool = True`, `confirm_live: bool = False`, `limit: int = Field(100, ge=1, le=500)`, `max_downloads: int = Field(1, ge=1, le=20)`, `min_coverage_percent: float = Field(95.0, ge=0, le=100)`, `notes: str = Field("", max_length=500)`. | | |
| TASK-003 | Add `TriggerIngestionJobResponse` model (extends `ApiModel`) with `status: str`, `job_request_id: str | None`, `dry_run: bool`, `jobs_url: str`, `message: str`. `status` values: `submitted`, `rejected`, `unavailable`. | | |
| TASK-004 | Add a private helper `_allowed_trigger_sources()` in `apps/api/app/ingestion_jobs.py` that returns the set of `(source_id, aoi_id)` from `get_ingestion_schedules()` where `schedule_enabled is True`; reject any request whose pair is not in that set with an Akasha error (`code="SOURCE_NOT_SCHEDULABLE"`). | | |
| TASK-005 | Add a private helper `_resolve_inbox_dir()` returning `Path` or `None` when `ingestion_job_inbox_dir` is unset/absent, mirroring `_resolve_jobs_dir()`. | | |
| TASK-006 | Add `POST /ingestion-jobs/trigger` handler on the existing `router` in `apps/api/app/ingestion_jobs.py` (inherits `Depends(require_role("owner", "admin"))`). Steps: validate source/AOI via TASK-004; if `dry_run is False` require `confirm_live is True` else reject (`code="LIVE_CONFIRMATION_REQUIRED"`); if inbox dir missing return `TriggerIngestionJobResponse(status="unavailable", ...)`; generate `job_request_id = f"ingest-ui-{utc}-{uuid4().hex[:8]}"`; validate it with `_validate_job_id_or_raise`; write request file (TASK-007); return `status="submitted"` with `jobs_url=f"/admin/ingestion/jobs?sourceId={source_id}"`. | | |
| TASK-007 | Implement atomic inbox write: create `inbox/<job_request_id>/`, write `request.json.tmp` then `os.replace` to `request.json`. Payload keys must match the wrapper contract (snake_case): `job_id`, `source_id`, `provider="bhoonidhi"`, `aoi_id`, `window_days`, `window_start` (`""` if None), `window_end` (`""` if None), `limit`, `max_downloads`, `min_coverage_percent`, `dry_run`, `overwrite=False`, `force_upload=False`, `retain_raw_downloads=False`, `keep_intermediate=False`, `requested_by=f"{user.email}@bff"`, `notes`. `job_id` in the payload = `job_request_id`. | | |
| TASK-008 | Add an optional deploy gate: read `admin_ingestion_live_trigger_enabled` (env `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED`, default `False`) in `config.py`; when false, force `dry_run=True` server-side regardless of request and ignore `confirm_live`. | | |

### Implementation Phase 2 — Host-side inbox dispatcher

- GOAL-002: Add a host-side dispatcher that converts inbox requests into bounded wrapper jobs, without the API touching Docker/systemd.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-009 | Create `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.sh`: source `/etc/akasha/ingestion-jobs.env`; `INBOX_DIR=${AKASHA_INGESTION_INBOX_DIR:-/srv/akasha/ingestion-inbox}`; for each `<id>/request.json`, acquire a per-id `flock`, call `/opt/akasha/bin/akasha-ingestion-job.sh start "<id>/request.json"`, then move the folder to `${INBOX_DIR}/submitted/<id>/`; reuse a `redact_stream` block for logs; never call `docker`/`systemctl` directly. | | |
| TASK-010 | Create `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.service` (Type=oneshot, runs the dispatcher script, `WorkingDirectory=/srv/akasha`, no network needs) following the existing scheduler service unit's hardening style. | | |
| TASK-011 | Create `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.path` watching `PathExistsGlob=/srv/akasha/ingestion-inbox/*/request.json` (plus a low-frequency safety timer fallback `akasha-ingestion-inbox-dispatcher.timer` at e.g. every 2 minutes for missed events). | | |
| TASK-012 | Add stale/failed handling: requests that fail to dispatch are moved to `${INBOX_DIR}/failed/<id>/` with a redacted `dispatch_error.txt`; a prune step deletes `submitted/`+`failed/` entries older than a configurable retention (default 14 days). | | |
| TASK-013 | Extend `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh` to install the dispatcher script (`0755`) to `/opt/akasha/bin/`, the `.service`/`.path`/`.timer` units to `/etc/systemd/system/`, create `/srv/akasha/ingestion-inbox` (mode `0770`, group `akasha-ingesters`), run `systemctl daemon-reload`, and print enable/rollback guidance. Do not enable the scheduler timer. | | |

### Implementation Phase 3 — Deployment wiring

- GOAL-003: Give the API write-only inbox access while preserving read-only scheduler monitoring and host execution boundaries.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-014 | In `infra/selfhosted/coolify-compose.yml`, add to the `api` service: env `INGESTION_JOB_INBOX_DIR: "/srv/akasha/ingestion-inbox"`, optional env `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED: "${ADMIN_INGESTION_LIVE_TRIGGER_ENABLED:-false}"`, and a writable volume `- /srv/akasha/ingestion-inbox:/srv/akasha/ingestion-inbox`. Keep the existing `- /srv/akasha/ingestion:/srv/akasha/ingestion:ro` monitoring mount unchanged. | | |
| TASK-015 | Mirror the same env in `infra/docker/docker-compose.yml` / `docker-compose.dev.yml` for local dev (default inbox under a repo-local bind path, e.g. `./data/work/ingestion-inbox`), so the endpoint is testable locally even if no dispatcher runs. | | |
| TASK-016 | Ensure host directory ownership/permissions allow the API container UID to write and the dispatcher (root/host) to read+move; document in `infra/selfhosted/README.md`. | | |

### Implementation Phase 4 — Frontend trigger UI

- GOAL-004: Add an admin-only trigger panel to the schedules page with dry-run default and explicit live confirmation, plus post-submit links.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Add `TriggerIngestionJobRequest` and `TriggerIngestionJobResponse` types to `apps/frontend/src/types/api.ts` (camelCase, matching the BFF response). | | |
| TASK-018 | Add `triggerIngestionJob(payload: TriggerIngestionJobRequest): Promise<TriggerIngestionJobResponse>` to `apps/frontend/src/lib/api.ts` (POST `/api/monitoring/ingestion-jobs/trigger`). | | |
| TASK-019 | Add `useTriggerIngestionJob()` mutation hook to `apps/frontend/src/lib/queries.ts`; on success invalidate `queryKeys.ingestionJobs()` (all variants), `queryKeys.ingestionSchedules`, and the imagery-source monitoring key. | | |
| TASK-020 | Add a reusable component `apps/frontend/src/components/admin/ingestion/AdminIngestionRunPanel.tsx`: source select (from schedules), AOI select, mode toggle (`Dry run` default / `Live canary`), window-days select (12/30/45), max-downloads input, notes input. | | |
| TASK-021 | For live mode, render an explicit confirmation control (checkbox + typed acknowledgment) that sets `confirmLive=true`; disable the submit button until acknowledged. Hide live mode entirely when a `liveTriggerEnabled` prop is false (driven by config/feature flag echoed from the BFF or a build-time env). | | |
| TASK-022 | Mount `AdminIngestionRunPanel` at the top of `apps/frontend/src/pages/monitoring/IngestionSchedules.tsx`; add a per-row "Run this source" button that pre-fills the panel's source/AOI. | | |
| TASK-023 | On submit success, show a status note ("Submitted — waiting for staging runner pickup") with a link to `response.jobsUrl` (`/admin/ingestion/jobs?sourceId=...`) and a link to `/admin/ingestion/jobs`. On error, render the Akasha error message safely (no raw details). | | |
| TASK-024 | Add `sourceId` URL-param support to `apps/frontend/src/pages/monitoring/IngestionJobsList.tsx` so the post-submit link pre-filters the jobs list by source. | | |

### Implementation Phase 5 — Operator answerability polish (optional, low-risk)

- GOAL-005: Make the basic answers obvious on the job detail/list without exposing raw artifacts.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | In `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx`, ensure a top summary clearly states the verdict (e.g. "Provider returned no candidates" for `no_new_candidates`, "Downloaded N products", "Validation failed: …"), reusing existing fields only. | | |
| TASK-026 | Ensure the jobs list "Counts" and "Message" columns render `0` vs `—` distinctly so "found 0" reads clearly (already present in `IngestionJobsList.tsx`; verify and add a unit assertion). | | |

### Implementation Phase 6 — Tests

- GOAL-006: Cover backend validation/security, host-artifact safety, and frontend trigger UX.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-027 | In `apps/api/tests/test_ingestion_jobs.py`, add tests: owner/admin can POST trigger; member/viewer rejected; `dry_run` defaults true; live without `confirmLive` rejected (`LIVE_CONFIRMATION_REQUIRED`); unknown/non-schedulable source rejected (`SOURCE_NOT_SCHEDULABLE`); inbox missing → `status="unavailable"`; bounded fields reject out-of-range; request file written with correct snake_case keys and `dry_run`; response contains no raw paths/secrets (reuse `_assert_no_raw_paths`). | | |
| TASK-028 | Add a test that `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false` forces `dry_run=True` even when `dry_run=False, confirmLive=True` is sent. | | |
| TASK-029 | In `tests/test_ingestion_scheduler_systemd_artifacts.py`, add the dispatcher artifacts to `EXPECTED_FILES` and assert: dispatcher calls `/opt/akasha/bin/akasha-ingestion-job.sh start`; does not call `docker`/`systemctl`; uses `flock`; uses `/srv/akasha/ingestion-inbox`; installer installs the dispatcher units and creates the inbox dir; no `/tmp`/`/var/tmp` data paths. | | |
| TASK-030 | In `apps/frontend/src/pages/monitoring/IngestionSchedules.test.tsx`, add: panel renders for admin; ResourceSat sources selectable; dry-run default; live confirmation gates submit; submit calls mutation; success shows jobs link; error renders safely. | | |
| TASK-031 | Add a hook/client test for `useTriggerIngestionJob` verifying it invalidates `ingestionJobs` and `ingestionSchedules` on success. | | |

### Implementation Phase 7 — Docs & staging validation

- GOAL-007: Document the workflow and validate end-to-end on staging without enabling the timer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | Update `docs/staging-ingestion-developer-guide.md` with the admin UI trigger flow, dry-run/live expectations, inbox/dispatcher overview, and rollback (disable the dispatcher `.path`/`.timer`). | | |
| TASK-033 | Update `docs/architecture-tech-stack.md` BFF API contracts with `POST /api/monitoring/ingestion-jobs/trigger` (request/response, role gating, redaction). | | |
| TASK-034 | Add a guardrail bullet to `docs/engineering-dos-donts.md`: UI ingestion triggers must be bounded, dry-run-first, wrapper-backed, and must never run Docker/systemd from the API container. | | |
| TASK-035 | Note the new env vars (`INGESTION_JOB_INBOX_DIR`, `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED`) and inbox convention in `AGENTS.md` and `CLAUDE.md` operational sections. | | |
| TASK-036 | Staging validation: deploy; confirm the API can write the inbox but cannot write `/srv/akasha/ingestion/scheduler`; trigger a UI dry-run for LISS-3, LISS-4, AWiFS; verify each scheduler job appears in the jobs list/detail and shows source/AOI/window/state/verdict/counts with no raw paths; trigger one explicit live canary; verify terminal state; confirm `akasha-ingestion-scheduler.timer` remains `disabled`/`inactive`. | | |

## 3. Alternatives

- **ALT-001**: BFF SSHes to localhost using the existing forced-command key. Rejected for v1 — requires SSH key + key management inside the API container, increasing blast radius (SEC-003).
- **ALT-002**: BFF calls `docker compose run`/`systemctl` directly. Rejected — violates CON-002a and the one-public-service/least-privilege boundary; previously wedged the staging VM.
- **ALT-003**: BFF mints a job id and deep-links to `/admin/ingestion/jobs/{id}`. Rejected — the scheduler runner generates its own `job_<ts>_<hex>` id (CON-002); a BFF id would never resolve. Replaced by filtered-jobs-list linking (REQ-005).
- **ALT-004**: Command-generation-only UI (UI prints the CLI command for an operator to run). Kept as a fallback if the dispatcher is deferred, but less useful; the trigger contract/types are designed so the UI can switch to the inbox path without rework.
- **ALT-005**: New API-owned SQLite/ORM job-request table. Rejected for v1 — unnecessary; the inbox file + existing scheduler ledger already provide the request/record path (Phase 0 contract keeps raw job state ingestion-owned).

## 4. Dependencies

- **DEP-001**: Existing BFF monitoring router and redaction helpers in `apps/api/app/ingestion_jobs.py`.
- **DEP-002**: Existing host wrapper `/opt/akasha/bin/akasha-ingestion-job.sh` and runner `akasha-ingestion-job-runner.sh` (write canonical scheduler jobs + `job_ledger.db`).
- **DEP-003**: Existing scheduler monitoring read paths `SCHEDULER_JOBS_DIR=/srv/akasha/ingestion/scheduler/jobs` and `SCHEDULER_JOB_LEDGER_PATH=/srv/akasha/ingestion/scheduler/job_ledger.db`.
- **DEP-004**: Existing auth/RBAC `require_role("owner","admin")` and `get_current_user` in `apps/api/app/auth.py`.
- **DEP-005**: Existing TanStack Query hooks/keys in `apps/frontend/src/lib/queries.ts` and admin route gating in `apps/frontend/src/routes/`.
- **DEP-006**: Bhoonidhi credentials present in the ingestion-worker environment for non-dry-run runs (already configured on staging).

## 5. Files

- **FILE-001**: `apps/api/app/config.py` — add `ingestion_job_inbox_dir` and `admin_ingestion_live_trigger_enabled`.
- **FILE-002**: `apps/api/app/ingestion_jobs.py` — add trigger DTOs, validation helpers, inbox writer, and `POST /ingestion-jobs/trigger`.
- **FILE-003**: `apps/api/tests/test_ingestion_jobs.py` — backend trigger tests (validation, auth, safety, file write).
- **FILE-004**: `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.sh` — new host dispatcher.
- **FILE-005**: `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.service` — new oneshot unit.
- **FILE-006**: `infra/selfhosted/systemd/akasha-ingestion-inbox-dispatcher.path` (+ `.timer`) — inbox watch + safety fallback.
- **FILE-007**: `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh` — install dispatcher artifacts + inbox dir.
- **FILE-008**: `infra/selfhosted/coolify-compose.yml` — API inbox mount + env; keep scheduler RO mount.
- **FILE-009**: `infra/docker/docker-compose.yml` / `docker-compose.dev.yml` — local inbox env/mount.
- **FILE-010**: `apps/frontend/src/types/api.ts` — trigger request/response types.
- **FILE-011**: `apps/frontend/src/lib/api.ts` — `triggerIngestionJob` client.
- **FILE-012**: `apps/frontend/src/lib/queries.ts` — `useTriggerIngestionJob` + invalidation.
- **FILE-013**: `apps/frontend/src/components/admin/ingestion/AdminIngestionRunPanel.tsx` — trigger panel.
- **FILE-014**: `apps/frontend/src/pages/monitoring/IngestionSchedules.tsx` (+ `.test.tsx`) — mount panel + per-row run action.
- **FILE-015**: `apps/frontend/src/pages/monitoring/IngestionJobsList.tsx` — `sourceId` URL-param prefilter.
- **FILE-016**: `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx` — verdict summary polish (optional).
- **FILE-017**: `tests/test_ingestion_scheduler_systemd_artifacts.py` — dispatcher artifact assertions.
- **FILE-018**: `docs/staging-ingestion-developer-guide.md`, `docs/architecture-tech-stack.md`, `docs/engineering-dos-donts.md`, `AGENTS.md`, `CLAUDE.md` — docs/guardrails/env.

## 6. Testing

- **TEST-001**: Backend — owner/admin allowed; member/viewer rejected (403).
- **TEST-002**: Backend — `dryRun` defaults true; live without `confirmLive` rejected.
- **TEST-003**: Backend — unknown/non-schedulable source/AOI rejected with `SOURCE_NOT_SCHEDULABLE`.
- **TEST-004**: Backend — out-of-range `windowDays`/`limit`/`maxDownloads`/`minCoveragePercent` rejected by validation.
- **TEST-005**: Backend — inbox missing → `status="unavailable"`; inbox present → request file written with correct snake_case keys and `dry_run`.
- **TEST-006**: Backend — `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false` forces dry-run.
- **TEST-007**: Backend — trigger response and any echoed values contain no raw paths/secrets (`_assert_no_raw_paths`).
- **TEST-008**: Infra — dispatcher artifacts exist; call the wrapper `start`; no `docker`/`systemctl`; `flock`; inbox under `/srv/akasha/ingestion-inbox`; installer creates dir + installs units.
- **TEST-009**: Frontend — panel renders for admin; dry-run default; live confirmation gating; submit calls mutation; success links to jobs list; error renders safely.
- **TEST-010**: Frontend — `useTriggerIngestionJob` invalidates `ingestionJobs` + `ingestionSchedules`.
- **Verification commands**:
  - `cd apps/api && python -m pytest tests/test_ingestion_jobs.py -q`
  - `python -m pytest tests/test_ingestion_scheduler_systemd_artifacts.py tests/test_scheduler_phase0_contracts.py -q`
  - `ruff check apps/api services/ingestion scripts tests`
  - `cd apps/frontend && yarn test --run IngestionSchedules IngestionJobsList IngestionJobDetail`
  - `cd apps/frontend && yarn build`

## 7. Risks & Assumptions

- **RISK-001**: Unbounded/abusive runs wedge the VM. Mitigation: dry-run default, server-side hard caps (REQ-007), reuse of `flock`/`ionice`/`nice` runner, single-flight per source/AOI (`blocked_by_lock`).
- **RISK-002**: Submitted id ≠ scheduler job id confuses operators. Mitigation: link to filtered jobs list, not a per-id page (REQ-005, CON-002).
- **RISK-003**: Inbox RO/RW mount conflict on the API container. Mitigation: inbox is a sibling path `/srv/akasha/ingestion-inbox`, not under the RO mount (CON-001).
- **RISK-004**: Dispatcher double-dispatches a request. Mitigation: per-id `flock` + move to `submitted/` after handoff (TASK-009/012).
- **RISK-005**: Live UI runs cause real downloads before the team is ready. Mitigation: `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED` deploy flag (default false) + explicit UI confirmation (TASK-008/021).
- **RISK-006**: Secret/path leakage via the new endpoint. Mitigation: reuse existing redaction; response has no raw fields; tests assert it (TEST-007).
- **ASSUMPTION-001**: The host dispatcher runs as a privileged host unit (root/host user in `akasha-ingesters`), separate from the API container.
- **ASSUMPTION-002**: ResourceSat sources remain `schedule_enabled` in `schedule_state.json`; non-scheduler sources stay rejected by validation.
- **ASSUMPTION-003**: The existing runner continues to write the canonical scheduler ledger that the BFF monitoring reads.

## 8. Related Specifications / Further Reading

- docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md
- docs/impl-plan/feature-admin-ingestion-orchestration-console-1.md
- docs/impl-plan/process-staging-ingestion-workflow-1.md
- docs/reference/satellite-ingestion-scheduler-contracts.md
- docs/satellite-ingestion-orchestration-and-scheduler.md
- docs/staging-ingestion-developer-guide.md
- infra/selfhosted/README.md
