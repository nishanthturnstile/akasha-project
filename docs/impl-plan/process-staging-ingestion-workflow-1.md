---
goal: Centralized Aakasha Staging Satellite Ingestion Workflow
version: 1.1
date_created: 2026-06-22
last_updated: 2026-06-22
owner: Akasha Engineering
tags: process, infrastructure, ingestion, bhoonidhi, bhuvan, azure, staging, cli, minio, systemd, debugging
---

# Introduction

This implementation plan creates a repeatable team workflow for satellite data ingestion where developers trigger Bhoonidhi/Bhuvan downloads and transforms from their local machines while the actual network calls and processing run on the whitelisted **Aakasha Staging** Azure VM. The first release is **CLI-first**: a local Python command talks to a restricted staging-side wrapper over SSH, the wrapper runs the existing ingestion worker inside the deployed Docker Compose stack, and final transformed COG/TIFF bundles can be imported into a developer's local MinIO/STAC setup for testing.

> **For agentic workers:** implement this plan task-by-task. Use `superpowers:subagent-driven-development` for independent phases or `superpowers:executing-plans` for inline execution. Use TDD for new scripts and behavior. Do not expose private services publicly. Do not copy Bhoonidhi credentials or raw provider ZIPs to developer machines.

**Goal:** Build a centralized, debuggable, team-safe workflow for satellite download, transform, validation, retry, and local MinIO import without manual VM login.

**Architecture:** The MVP uses a local developer CLI (`scripts/staging_ingestion_job.py`) that invokes a restricted remote command (`/opt/akasha/bin/akasha-ingestion-job.sh`) on Aakasha Staging. The remote command writes per-job artifacts under `/srv/akasha/ingestion/jobs/<job_id>/`, runs `docker compose run --rm --pull never ingestion-worker python worker.py bhoonidhi-sync ...`, and reuses the existing SQLite ingestion ledger at `/srv/akasha/ingestion/ledger.sqlite`. Local MinIO import reuses `scripts/sync_staging_raster_bundle.py` so existing manifest, MinIO, and pgSTAC contracts stay intact.

**Tech Stack:** Python 3.11 scripts, Bash/systemd on the staging VM, Docker Compose/Coolify deployment artifacts, FastAPI/BFF monitoring patterns for future API phase, SQLite ingestion ledger, MinIO, pgSTAC/STAC, SSH, optional Azure CLI for discovery/onboarding.

## 1. Requirements & Constraints

- **REQ-001**: A team member must be able to trigger a satellite ingestion job from a local workstation without manually logging into Aakasha Staging.
- **REQ-002**: All Bhoonidhi/Bhuvan API search and download traffic must originate from the whitelisted Aakasha Staging VM egress IP `20.219.3.35` unless NRSC/Bhoonidhi approves another egress IP.
- **REQ-003**: The MVP trigger surface must be CLI-first. Browser/API/admin UI job submission is a deferred phase after the CLI workflow is stable.
- **REQ-004**: All team members may trigger jobs, but only through a restricted staging-side wrapper and source/AOI/download guardrails, not broad raw Docker Compose access.
- **REQ-005**: The first local testing target must be local MinIO/STAC import of final transformed COG/TIFF artifacts, not raw provider downloads.
- **REQ-006**: Every staging job must write durable job artifacts under `/srv/akasha/ingestion/jobs/<job_id>/` so developers can inspect status, logs, command arguments, results, and failure reasons.
- **REQ-007**: The workflow must support retrying failed jobs with explicit `--overwrite` and `--force-upload` controls for conversion and object-storage retries.
- **REQ-008**: The workflow must support validation of transformed output by running `worker.py verify-composite` against the remote composite manifest or latest source/AOI composite.
- **REQ-009**: The workflow must support source generalization through an ingestion pipeline registry. The MVP supported sources are `resourcesat-2a-liss3-boa`, `resourcesat-2a-liss4-mx70-l2`, and `resourcesat-2a-awifs-boa`.
- **REQ-010**: Unsupported sources must fail before the worker starts, with a clear message that identifies the missing provider/download/transform capability.
- **REQ-011**: The local CLI must be Windows-friendly and must use `subprocess.run([...])` or `subprocess.Popen([...])` without local shell string interpolation.
- **REQ-012**: Azure CLI support must be limited to optional VM discovery/onboarding checks in the MVP. The long-running execution path must remain SSH plus remote systemd/script execution.
- **REQ-013**: Scheduled ingestion through `akasha-bhoonidhi-sync.service` must continue to work unchanged. The ad hoc team workflow must not break the existing timer path.
- **REQ-014**: The local sync/import flow must reuse `scripts/sync_staging_raster_bundle.py --import-local --verify-local` so local MinIO and STAC ingestion remain consistent with current development practices.
- **REQ-015**: The CLI `--wait` flag must poll remote `status` on a bounded interval (default `--wait-interval` 10s) with a `--wait-timeout` (default 1800s). On timeout the CLI must exit non-zero and print the `status`/`logs` commands to resume monitoring. `--wait` must treat every terminal state (including `blocked_by_lock` and `validation_failed`) as a stop condition.
- **SEC-001**: Bhoonidhi credentials, S3 keys, database URLs, tokens, and signed/internal URLs must never be printed in local CLI output, remote status JSON, or logs.
- **SEC-002**: Bhoonidhi/Bhuvan credentials must stay only on Aakasha Staging in Coolify environment variables or root-readable `/etc/akasha` files.
- **SEC-003**: Raw Bhoonidhi provider ZIPs must not be copied to developer machines. Only final prepared COG/TIFF artifacts and manifests are eligible for local sync.
- **SEC-004**: The workflow must preserve Akasha's one-public-service rule: only `web` is public; `api`, `ingestion-worker`, `titiler`, `stac-api`, `postgis`, and `minio` remain private.
- **SEC-005**: Team SSH access to the runner must be least-privilege. Each team key must be restricted with an SSH forced command (`command="/opt/akasha/bin/akasha-ingestion-forced-command.sh"` in `authorized_keys`) or an equivalent sudoers rule so the key can only run the allowed `akasha-ingestion-job.sh` subcommands, never an interactive shell or arbitrary Docker Compose commands.
- **SEC-006**: `job.log` and `command.txt` must be written through a redaction filter that masks credentials, tokens, signed URLs, and `s3://`/internal hostnames, and job artifacts must be created group-only (`chmod 640` files, `2750` directories) owned by the `akasha-ingesters` group — never world-readable.
- **CON-001**: Aakasha Staging stores persistent data under `/srv/akasha`; raw downloads and COG prep scratch must not land on `/` or Docker's OS-disk data root.
- **CON-002**: Bhoonidhi rate and session limits apply. Jobs must keep `max_downloads` bounded and must respect existing worker token/session/backoff behavior.
- **CON-003**: The remote runner must respect existing source/AOI lock behavior from `services/ingestion/akasha_ingest/sync.py::acquire_lock` and the systemd wrapper lock discipline.
- **CON-004**: The ad hoc runner must pass the same per-(source, AOI) worker lock path as the scheduled wrappers — `/srv/akasha/ingestion/bhoonidhi-sync.<aoi_id>.worker.lock` — so an ad hoc job and `akasha-bhoonidhi-sync` / `akasha-bhoonidhi-liss4-sync` are mutually exclusive for the same source/AOI and never double-hit Bhoonidhi.
- **CON-005**: The pipeline registry must contain an entry for every source currently in `services/ingestion/akasha_ingest/sync.py::PREPARE_SCRIPTS` (the three ResourceSat MVP sources plus `sentinel-1-grd`, `eos-04-sar-mrs-l2b`, and `nisar-ssar-beta-gcov`). Delegating `prepare_script_name` to the registry must not change the resolved script for any existing source.
- **CON-006**: At most one ad hoc job may be in flight per (source, AOI). The runner must refuse to start when another job for the same source/AOI is `queued` or `running`, returning `blocked_by_lock`.
- **PAT-001**: Reuse the existing ingestion worker command `worker.py bhoonidhi-sync` for MVP execution instead of creating a second ingestion implementation.
- **PAT-002**: Reuse `infra/selfhosted/systemd/akasha-bhoonidhi-sync.sh` Compose discovery logic in the new ad hoc runner.
- **PAT-003**: Reuse `apps/api/app/source_monitoring.py` failure taxonomy and secret-redaction philosophy for job status and logs.
- **PAT-004**: Reuse `scripts/sync_staging_raster_bundle.py` for final bundle pull and local MinIO/STAC import.
- **GUD-001**: Implement new Python behavior with test-first unit tests using pytest fixtures and monkeypatched subprocess calls.
- **GUD-002**: Keep shell scripts small and deterministic; push parsing and local orchestration into Python where possible.
- **GUD-003**: Add docs and troubleshooting alongside the scripts in the same implementation branch.
- **GUD-004**: Request defaults have a single source of truth: the local CLI fills every field in the canonical request before sending it. The remote wrapper only validates and never silently re-defaults missing fields.
- **GUD-005**: Remote machine-readable output is stable: `status`/`result`/`retry`/`validate` print a single JSON object, and `list` prints NDJSON (one job object per line). The CLI parses exactly these shapes.

### Canonical staging job request

| Field | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `job_id` | string | yes | generated locally as `ingest-YYYYMMDDTHHMMSSZ-<8hex>` | Stable remote job directory and systemd unit suffix. |
| `source_id` | string | yes | `resourcesat-2a-liss3-boa` | Akasha source id. |
| `provider` | string | yes | `bhoonidhi` | Provider implementation. MVP supports `bhoonidhi` only. |
| `aoi_id` | string | yes | `bangalore-60km` | AOI id loaded by worker from AOI config. |
| `window_start` | ISO date string | no | empty | Explicit composite window start. |
| `window_end` | ISO date string | no | current UTC date, filled by local CLI | Explicit composite window end. |
| `window_days` | integer | no | `45` | Rolling composite window size when explicit dates are absent. |
| `backfill_days` | integer | no | `0` | Historical backfill span. |
| `backfill_step_days` | integer | no | empty | Backfill window step; worker default applies when empty. |
| `limit` | integer | no | `100` | Bhoonidhi search limit. |
| `max_downloads` | integer | no | `3` | Per-run cap for new downloads. |
| `min_coverage_percent` | number | no | `95` | Composite acceptance threshold. |
| `dry_run` | boolean | no | `false` | Stop before download/prepare/composite/ingest. |
| `overwrite` | boolean | no | `false` | Rebuild local prepared artifacts if they exist. |
| `force_upload` | boolean | no | `false` | Replace existing MinIO objects. |
| `retain_raw_downloads` | boolean | no | `false` | Keep raw ZIPs after success. |
| `keep_intermediate` | boolean | no | `false` | Keep temporary conversion files. |
| `requested_by` | string | yes | local username plus hostname | Human-readable audit identity. |
| `notes` | string | no | empty | Freeform operator note stored in request JSON. |

> **Defaults & lock path:** Per GUD-004 the local CLI fills every field above (including `window_end`, `requested_by`, and the booleans) before the request is sent; the remote wrapper validates only. The runner derives the worker lock path as `/srv/akasha/ingestion/bhoonidhi-sync.<aoi_id>.worker.lock` (CON-004) — it is not a client-supplied field.

### Remote job artifacts

| Path | Writer | Purpose |
| --- | --- | --- |
| `/srv/akasha/ingestion/jobs/<job_id>/request.json` | local CLI via remote wrapper | Canonical request payload used by `start` and `retry`. |
| `/srv/akasha/ingestion/jobs/<job_id>/status.json` | remote control/runner scripts | Machine-readable lifecycle state, timestamps, exit code, failure kind, and result references. |
| `/srv/akasha/ingestion/jobs/<job_id>/command.txt` | remote runner | Redacted command line executed inside the staging Docker Compose stack. |
| `/srv/akasha/ingestion/jobs/<job_id>/job.log` | remote runner | Redacted combined stdout/stderr (SEC-006) from preflight, Docker Compose worker run, and validation. Group-readable only. |
| `/srv/akasha/ingestion/jobs/<job_id>/result.json` | remote runner | Final manifest paths, composite paths, source/AOI/date, and verification summary. |

### Lifecycle states

| State | Meaning | Terminal |
| --- | --- | --- |
| `queued` | Request accepted and job directory created. | no |
| `running` | Remote runner started and worker command is executing. | no |
| `succeeded` | Worker and post-run validation completed with exit code `0`. | yes |
| `failed` | Worker or runner failed with non-zero exit code. | yes |
| `blocked_by_lock` | Source/AOI lock is active and the job was not started. | yes |
| `validation_failed` | Worker completed but `verify-composite` failed. | yes |
| `cancelled` | Operator cancelled the systemd unit before completion. | yes |

> **Dry-run and "no new data" runs** end as `succeeded` with an empty `result.json.composite_date`. `validate` on such a job reports "no composite produced; nothing to validate" and exits `0` rather than reporting `validation_failed`.

### Team usage flow

1. Developer configures SSH alias `akasha-staging` or sets `AKASHA_STAGING_SSH_HOST`.
2. Developer runs the local CLI `doctor` command to verify SSH, remote runner, local Docker, and local MinIO/STAC prerequisites.
3. Developer runs `trigger --dry-run` for the selected source/AOI/date window.
4. Developer runs `trigger --max-downloads 1 --wait` for a limited real ingestion job.
5. Developer runs `logs <job_id> --follow` and `status <job_id>` to debug progress and failures.
6. Developer runs `validate <job_id>` or `validate --source <source> --aoi <aoi> --date latest`.
7. Developer runs `sync-local <job_id> --import-local --verify-local` to pull final COG/TIFF artifacts into local MinIO/STAC.
8. Developer opens the local app and verifies the source/date appears through existing BFF product endpoints.

## 2. Implementation Steps

### Implementation Phase 1 — Pipeline registry and command contract

- GOAL-001: Add deterministic source capability metadata and a reusable command contract so the remote runner can validate requests before launching expensive work.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `services/ingestion/akasha_ingest/pipeline_registry.py`. Define a frozen dataclass `PipelineSource` with fields `source_id`, `provider`, `collection_id`, `prepare_script`, `supports_search`, `supports_download`, `supports_composite`, `mvp_enabled`, `default_aoi_ids`, `default_max_downloads`, `default_min_coverage_percent`, `output_profile`, and `notes`. Add a constant for **every** source in `sync.py::PREPARE_SCRIPTS`: the three ResourceSat MVP sources (`mvp_enabled=True`, provider `bhoonidhi`) plus `sentinel-1-grd`, `eos-04-sar-mrs-l2b`, and `nisar-ssar-beta-gcov` (`mvp_enabled=False`) so registry delegation is loss-less (CON-005). | | |
| TASK-002 | In `pipeline_registry.py`, add functions `get_pipeline_source(source_id: str) -> PipelineSource`, `supported_source_ids(provider: str | None = None) -> list[str]` (returns only `mvp_enabled` sources, sorted), `prepare_script_name(source_id: str) -> str` (must return the correct script for all six registered sources), and `is_source_allowed(source_id: str, allowed_sources: set[str] | None) -> bool`. Raise `KeyError` with message `unsupported ingestion source: <source_id>` for unknown sources. | | |
| TASK-003 | Modify `services/ingestion/akasha_ingest/sync.py` so `prepare_script_name(source_id)` delegates to `pipeline_registry.prepare_script_name(source_id)`. The registry must reproduce the full `PREPARE_SCRIPTS` mapping (CON-005); keep `DEFAULT_PREPARE_SCRIPT` only as the unknown-source fallback. Preserve the public function name `prepare_script_path(source_id, start)` because `worker.py` already calls it. | | |
| TASK-004 | Add `tests/test_pipeline_registry.py`. Assert each ResourceSat MVP source returns provider `bhoonidhi`, the expected Bhoonidhi collection ID, prepare script `prepare_resourcesat_liss3_boa_cogs.py`, and composite support `True`. Assert the SAR sources still resolve to their own scripts (`prepare_sentinel1_grd_cogs.py`, `prepare_eos04_sar_mrs_l2b_cogs.py`, `prepare_nisar_ssar_beta_gcov_cogs.py`) so delegation does not regress (CON-005). Assert `supported_source_ids("bhoonidhi")` returns the three MVP sources sorted, and that an unknown source raises `KeyError`. | | |
| TASK-005 | Run `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py -q`. Expected result: all tests pass and existing Bhoonidhi sync behavior remains unchanged. | | |

### Implementation Phase 2 — Staging-side restricted job wrapper

- GOAL-002: Add scripts that let a restricted staging user start, inspect, retry, validate, and list ingestion jobs without running arbitrary Docker Compose commands.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | Create `tests/test_staging_ingestion_job_artifacts.py`. Test that `infra/selfhosted/systemd/akasha-ingestion-job.sh`, `akasha-ingestion-job-runner.sh`, `akasha-ingestion-forced-command.sh`, `akasha-ingestion-jobs.env.example`, and `install-akasha-ingestion-jobs.sh` exist under `infra/selfhosted/systemd/`. Test file content for `/srv/akasha/ingestion/jobs`, `docker compose`, `ingestion-worker`, `worker.py`, `bhoonidhi-sync`, `--pull never`, the shared lock path token `bhoonidhi-sync.` (CON-004), a redaction filter applied to `command.txt`/`job.log` (SEC-006), `chmod` of artifacts to group-only, `status.json`, `job.log`, and absence of literal secrets. | | |
| TASK-007 | Create `infra/selfhosted/systemd/akasha-ingestion-jobs.env.example`. Include `AKASHA_INGESTION_JOB_ROOT=/srv/akasha/ingestion/jobs`, `AKASHA_INGESTION_ALLOWED_SOURCES=resourcesat-2a-liss3-boa,resourcesat-2a-liss4-mx70-l2,resourcesat-2a-awifs-boa`, `AKASHA_INGESTION_ALLOWED_AOIS=bangalore-60km`, `AKASHA_INGESTION_DEFAULT_MAX_DOWNLOADS=3`, `AKASHA_INGESTION_DEFAULT_MIN_COVERAGE_PERCENT=95`, `AKASHA_INGESTION_LOG_RETENTION_DAYS=14`, `AKASHA_SYNC_RAW_ROOT=/srv/akasha/data/raw/bhoonidhi`, `AKASHA_SYNC_TEMP_ROOT=/srv/akasha/data/work/bhoonidhi`, `AKASHA_SYNC_LEDGER_PATH=/srv/akasha/ingestion/ledger.sqlite`, and `AKASHA_SYNC_PULL_POLICY=never`. | | |
| TASK-008 | Create `infra/selfhosted/systemd/akasha-ingestion-job.sh`. Implement subcommands `start`, `status`, `logs`, `list`, `retry`, `validate`, `doctor`, and `prune`. Source `/etc/akasha/ingestion-jobs.env` when present. For `start`, accept a request JSON path or stdin, create the job directory, write `request.json` and `status.json` (`queued`), then launch the runner **detached so `start` always returns immediately**: prefer `systemd-run --collect --unit akasha-ingest-job-<job_id>` (clearing any stale unit of that name first); if `systemd-run` is unavailable, fall back to `setsid nohup akasha-ingestion-job-runner.sh ... &` writing `runner.pid`. Never run the runner synchronously inside `start`. | | |
| TASK-009 | In `akasha-ingestion-job.sh`, implement `status <job_id>` (print `status.json`), `logs <job_id> [--tail N] [--follow]` (tail `job.log`; `--follow` stops when `status.json` reaches a terminal state), `list [--limit N]` (print newest jobs as NDJSON, one object per line — GUD-005), `retry <job_id>` (load stored `request.json`, merge optional `--overwrite`/`--force-upload`/`--notes`, clear `dry_run` unless re-supplied, generate a new job id, call `start`), `validate` (call the runner validation mode), `doctor` (check compose discovery, disk paths, and Bhoonidhi env presence), and `prune` (delete job directories older than `AKASHA_INGESTION_LOG_RETENTION_DAYS` **only when terminal**, never `queued`/`running` or the lock-holding job). | | |
| TASK-010 | Create `infra/selfhosted/systemd/akasha-ingestion-job-runner.sh`. Reuse the compose-file discovery logic from `infra/selfhosted/systemd/akasha-bhoonidhi-sync.sh`: prefer `AKASHA_COMPOSE_FILE`, then `/srv/akasha/coolify-compose.yml`, then the first `/data/coolify/services/*/docker-compose.yml`. Resolve `compose_dir`, `compose_args`, and `pull_policy`. | | |
| TASK-011 | In `akasha-ingestion-job-runner.sh`, implement preflight checks before calling Docker: job directory exists, request JSON exists, `/srv/akasha` is writable, raw/work roots exist or can be created, compose file exists and contains `ingestion-worker`, required Bhoonidhi env is available in the Compose environment, requested source is in `AKASHA_INGESTION_ALLOWED_SOURCES`, requested AOI is in `AKASHA_INGESTION_ALLOWED_AOIS`, no other job for the same (source, AOI) is `queued`/`running` (CON-006), and the shared worker lock `/srv/akasha/ingestion/bhoonidhi-sync.<aoi_id>.worker.lock` is not held (CON-004). Set `blocked_by_lock` and stop if either guard fails. | | |
| TASK-012 | In `akasha-ingestion-job-runner.sh`, build the worker command from `request.json` and run `docker compose <compose_args> -f <compose_file> run --rm --pull <pull_policy> ingestion-worker python worker.py bhoonidhi-sync ...`. Always pass `--source`, `--aoi`, `--limit`, `--window-days`, `--raw-root`, `--out-dir`, `--ledger-path`, `--max-downloads`, `--min-coverage-percent`, and `--lock-path /srv/akasha/ingestion/bhoonidhi-sync.<aoi_id>.worker.lock` (CON-004). Conditionally pass explicit `--window-start`, `--window-end`, `--backfill-days`, `--backfill-step-days`, `--dry-run`, `--overwrite`, `--force` (from `force_upload`), `--retain-raw-downloads`, and `--keep-intermediate`. | | |
| TASK-013 | In `akasha-ingestion-job-runner.sh`, write `command.txt` and `job.log` through a shared redaction filter (mask credentials, tokens, signed URLs, `s3://` and internal hostnames — SEC-006) and `chmod 640` them; tee combined stdout/stderr to `job.log`; update `status.json` to `running` at start and to `succeeded`, `failed`, `blocked_by_lock`, or `validation_failed` at exit, including `started_at`, `completed_at`, `exit_code`, `failure_kind`, `message`, and `log_path`. | | |
| TASK-014 | In `akasha-ingestion-job-runner.sh`, write `result.json` after the worker exits. Prefer parsing the worker's emitted manifest/composite paths from its captured stdout; fall back to the deterministic layout `/srv/akasha/data/work/bhoonidhi/<source>/<aoi>/` and `/srv/akasha/data/seed/rasters/<source>/composite/<aoi>/<date>/`. Include `source_id`, `aoi_id`, `window_start`, `window_end`, `ledger_path`, `coverage_manifest`, `download_manifest`, `composite_manifest`, `analytic_cog`, `mask_cog`, `composite_date`, and `verification_status`. Set `composite_date` to empty and use empty JSON arrays when no composite/manifests were produced (dry-run or no new data), not freeform text. | | |
| TASK-015 | Create `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh`. Install `akasha-ingestion-job.sh`, `akasha-ingestion-job-runner.sh`, and `akasha-ingestion-forced-command.sh` to `/opt/akasha/bin`; create `/srv/akasha/ingestion/jobs` with `2750` ownership for the restricted `akasha-ingesters` group; install the env example to `/etc/akasha/ingestion-jobs.env` only when absent; print the `authorized_keys` forced-command line operators must add per team key (SEC-005); and support `--dry-run` (print actions only) and `--uninstall` (remove installed scripts/units, keep `/srv/akasha` data). | | |
| TASK-015A | Create `infra/selfhosted/systemd/akasha-ingestion-forced-command.sh`. Parse `$SSH_ORIGINAL_COMMAND`, allow only the `akasha-ingestion-job.sh` subcommands (`start`, `status`, `logs`, `list`, `retry`, `validate`, `doctor`, `prune`) with validated arguments, reject anything else with a non-zero exit, and `exec` the allowed command. This is the SSH `command="..."` target that enforces SEC-005. | | |
| TASK-016 | Run `python -m pytest tests/test_staging_ingestion_job_artifacts.py -q`. Expected result: all artifact tests pass. | | |

### Implementation Phase 3 — Local developer CLI

- GOAL-003: Add a local Python CLI that developers can use from Windows, macOS, or Linux to submit jobs, inspect logs, retry, validate, and import results into local MinIO.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Create `tests/test_staging_ingestion_job.py`. Use `pytest` and monkeypatch `subprocess.run`, `subprocess.Popen`, `os.environ`, and time/UUID helpers. Test CLI argument parsing for `trigger`, `status`, `logs`, `list`, `retry`, `validate`, `sync-local`, and `doctor`. | | |
| TASK-018 | Create `scripts/staging_ingestion_job.py` with `argparse`. Define constants `DEFAULT_HOST_ENV="AKASHA_STAGING_SSH_HOST"`, `DEFAULT_HOST="akasha-staging"`, `REMOTE_COMMAND="/opt/akasha/bin/akasha-ingestion-job.sh"`, `DEFAULT_SOURCE="resourcesat-2a-liss3-boa"`, and `DEFAULT_AOI="bangalore-60km"`. | | |
| TASK-019 | Implement local helper `run_ssh(host: str, remote_args: list[str], *, input_text: str | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]`. It must invoke `ssh` with a list argument form: `['ssh', host, REMOTE_COMMAND, *remote_args]`. It must never build a local shell string. | | |
| TASK-020 | Implement `trigger`. Build the canonical request JSON from CLI flags, filling **all** defaults locally (GUD-004): `window_end`=today UTC, `requested_by`=`<user>@<host>`, the booleans, and `job_id`=`ingest-YYYYMMDDTHHMMSSZ-<8hex>`. Send it to remote `start` over SSH stdin; print `job_id`, `source_id`, `aoi_id`, and the next `status`/`logs --follow`/`validate`/`sync-local` commands. Support `--wait` by polling remote `status` every `--wait-interval` seconds (default 10) until any terminal state, bounded by `--wait-timeout` seconds (default 1800); on timeout exit non-zero and print resume commands (REQ-015). | | |
| TASK-021 | Implement `status <job_id>`. Call remote `status <job_id>`, parse JSON, and print both raw JSON with `--json` and a human-readable summary by default. The summary must include state, source, AOI, window, exit code, failure kind, message, log path, and composite date when present. | | |
| TASK-022 | Implement `logs <job_id>`. Support `--tail N` by calling remote `logs <job_id> --tail N`. Support `--follow` by starting `ssh <host> /opt/akasha/bin/akasha-ingestion-job.sh logs <job_id> --follow` through `subprocess.Popen([...])` and streaming stdout until the process exits. | | |
| TASK-023 | Implement `list`. Call remote `list --limit <N>`, parse the NDJSON stream (one job object per line — GUD-005), and print newest jobs with columns `job_id`, `state`, `source`, `aoi`, `updated_at`, and `message`. | | |
| TASK-024 | Implement `retry <job_id>`. Call remote `retry <job_id>`, forwarding `--overwrite`, `--force-upload`, and `--notes` so the wrapper merges them into the stored request (TASK-009). Print the new job id returned by the remote wrapper. | | |
| TASK-025 | Implement `validate`. Accept either `<job_id>` or explicit `--source`, `--aoi`, and `--date latest|YYYY-MM-DD`. Call remote `validate`; if the target job produced no composite (dry-run or no new data) print "no composite produced; nothing to validate" and exit `0`; otherwise print pass/fail with manifest path and verification detail. | | |
| TASK-026 | Implement `sync-local`. In job-id mode, delegate to the bundle script's `--job-id` path: `scripts/sync_staging_raster_bundle.py --job-id <job_id> --import-local --verify-local` (no field re-extraction in the CLI — avoids a second job-resolution path, TASK-031). In explicit mode, call it with `--source <source> --aoi <aoi> --date <date> --import-local --verify-local`. Append `--overwrite` and `--force-upload` when requested. | | |
| TASK-027 | Implement `doctor`. Check local `ssh` availability, remote wrapper availability, remote `doctor` success, optional Azure CLI VM identity when `--azure-resource-group` and `--azure-vm` are supplied, local `docker` availability, local `docker compose version`, and write access to local `data/seed/rasters`. Return exit code `1` when any required check fails. | | |
| TASK-028 | Add tests in `tests/test_staging_ingestion_job.py` for no-shell SSH command construction, trigger request JSON fields (all defaults filled locally), wait loop terminal handling and `--wait-timeout` non-zero exit, status summary formatting, logs follow Popen call, retry flag forwarding, validate no-composite exit `0`, sync-local `--job-id` delegation to `sync_staging_raster_bundle.py`, and doctor failure exit code. | | |
| TASK-029 | Run `python -m pytest tests/test_staging_ingestion_job.py -q`. Expected result: all local CLI tests pass. | | |

### Implementation Phase 4 — Local bundle sync enhancements

- GOAL-004: Extend the existing staging bundle pull script so it can consume job outputs while preserving safe tar extraction and local MinIO/STAC import behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-030 | Create or extend `tests/test_sync_staging_raster_bundle.py`. Cover existing behavior before modifying the script: latest remote composite lookup, date-specific lookup, safe tar extraction refusing absolute paths and `..`, local import calling `worker.py seed-stac` and `worker.py ingest-manifest`, and local verification calling `worker.py verify-composite`. | | |
| TASK-031 | Modify `scripts/sync_staging_raster_bundle.py` to accept `--job-id`. When supplied, SSH to the staging host and read `/srv/akasha/ingestion/jobs/<job_id>/result.json`. Extract `source_id`, `aoi_id`, and `composite_date`; then continue through the existing source/AOI/date pull path. | | |
| TASK-032 | Modify `scripts/sync_staging_raster_bundle.py` to accept `--remote-manifest`. When supplied, verify the remote path ends with `/prepare_manifest.json`, resolve its parent directory as the remote composite directory, and refuse paths outside `args.remote_root`. | | |
| TASK-033 | Modify `scripts/sync_staging_raster_bundle.py` output so successful pulls print `local_manifest=<path>`, `source=<source>`, `aoi=<aoi>`, and `date=<date>` on separate lines after `local bundle:`. Keep existing human-readable output. | | |
| TASK-034 | Ensure `--import-local` still runs local Docker Compose `worker.py seed-stac` and `worker.py ingest-manifest`. Ensure `--verify-local` still runs `worker.py verify-composite`. Keep `DEFAULT_MIN_COVERAGE_BY_SOURCE` behavior for LISS-4. | | |
| TASK-035 | Run `python -m pytest tests/test_sync_staging_raster_bundle.py -q`. Expected result: all bundle sync tests pass and safe tar extraction remains enforced. | | |

### Implementation Phase 5 — Documentation and runbooks

- GOAL-005: Document installation, team usage, debugging, retry, validation, and local MinIO import in the canonical docs.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-036 | Update `infra/selfhosted/README.md`. Add section `Centralized ad hoc ingestion jobs` after `Scheduled Bhoonidhi sync`. Document installer path, `/etc/akasha/ingestion-jobs.env`, the restricted `akasha-ingesters` group, the SSH `command="...akasha-ingestion-forced-command.sh"` forced-command setup per team key (SEC-005), SSH alias setup, local CLI examples (dry-run, capped real job, logs, status, retry, validate, sync-local), the shared per-(source, AOI) lock behavior (CON-004), and `--uninstall`/rollback. | | |
| TASK-037 | Update `docs/data-ingestion-and-satellite-rules.md`. Add a rule that every new satellite source must have a pipeline registry entry, source-specific transform/prep script or adapter, validation tests, staging dry-run, capped real run, and composite verification before team use. | | |
| TASK-038 | Update `docs/engineering-dos-donts.md`. Add an operational guardrail that Bhoonidhi/Bhuvan downloads must run from the approved Aakasha Staging egress IP, which must be a **reserved static** Azure IP, unless NRSC/Bhoonidhi whitelisting changes. Add a negative guardrail: do not copy raw Bhoonidhi provider archives to developer laptops. | | |
| TASK-039 | Add developer usage examples to this plan's related docs or `infra/selfhosted/README.md`: `doctor`, `trigger --dry-run`, `trigger --max-downloads 1 --wait`, `logs --follow`, `status`, `validate`, and `sync-local --import-local --verify-local`. Use placeholder host `akasha-staging` and do not include secrets. | | |
| TASK-040 | Run a documentation grep check: `grep -R "BHOONIDHI_PASSWORD\|S3_SECRET_KEY\|access_token" docs infra/selfhosted -n`. Expected result: no committed secret values; only variable names in templates/docs. | | |

### Implementation Phase 6 — Integrated verification and staging pilot

- GOAL-006: Prove the workflow locally with tests and then on Aakasha Staging with a dry run and a capped real run.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-041 | Run targeted tests from the repo root: `python -m pytest tests/test_pipeline_registry.py tests/test_staging_ingestion_job_artifacts.py tests/test_staging_ingestion_job.py tests/test_sync_staging_raster_bundle.py tests/test_bhoonidhi_ingestion.py tests/test_bhoonidhi_systemd_artifacts.py tests/test_validate_selfhosted_staging_bhoonidhi.py -q`. Expected result: all tests pass. | | |
| TASK-042 | Run lint from repo root: `ruff check services/ingestion scripts tests`. Expected result: no lint errors. | | |
| TASK-043 | Deploy the scripts to Aakasha Staging using `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh --dry-run` first, then run the installer without `--dry-run` from the staging VM or through the approved deployment process. Confirm `/opt/akasha/bin/akasha-ingestion-job.sh` exists and `/srv/akasha/ingestion/jobs` is writable by the restricted group. | | |
| TASK-044 | From a developer workstation, run `python scripts/staging_ingestion_job.py doctor --host akasha-staging`. Expected result: SSH, remote wrapper, remote compose discovery, staging disk path, local Docker, and local raster seed directory checks pass. | | |
| TASK-045 | From a developer workstation, run a dry-run job: `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --dry-run --wait`. Expected result: terminal state `succeeded`, `job.log` exists, `status.json` exists, and no raw download occurs. | | |
| TASK-046 | From a developer workstation, run a capped real job: `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --max-downloads 1 --wait`. Expected result: job reaches `succeeded` or a classified provider/data failure; unclassified failures block completion of this task. | | |
| TASK-047 | Validate the remote output: `python scripts/staging_ingestion_job.py validate <job_id> --host akasha-staging`. Expected result: `worker.py verify-composite` passes for the produced composite manifest or latest source/AOI composite. | | |
| TASK-048 | Import locally: `python scripts/staging_ingestion_job.py sync-local <job_id> --host akasha-staging --import-local --verify-local`. Expected result: local `sync_staging_raster_bundle.py` pulls final COG/TIFF artifacts, imports to local MinIO/STAC, and verifies the local composite. | | |
| TASK-049 | Run the existing staging validator after deployment: `python scripts/validate_selfhosted_staging_bhoonidhi.py --expected-sha <deployed-git-sha> --skip-timer-check --public-origin https://staging.gis.cidsaglobal.com`. Expected result: existing staging gates remain compatible with the new ad hoc job workflow. | | |

### Implementation Phase 7 — Deferred BFF/admin dashboard

- GOAL-007: Define the later app-backed job system without blocking the CLI MVP.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-050 | After the CLI workflow is stable, create SQLAlchemy ORM model `IngestionJob` in `apps/api/app/models.py` with `id`, `team_id`, `owner_id`, `source_id`, `aoi_id`, `provider`, `job_type`, `status`, `params` JSONB, `remote_job_id`, `log_path`, `result` JSONB, `error_summary`, `started_at`, `completed_at`, `created_at`, and `updated_at`. Use existing `UuidPkMixin`, `TimestampMixin`, and `OwnerTeamMixin` where compatible. | | |
| TASK-051 | Add an Alembic migration under `apps/api/alembic/versions/` for `akasha.ingestion_jobs`. Add indexes for `(team_id, created_at)`, `(team_id, status)`, `(source_id, aoi_id)`, and `(remote_job_id)`. Use Alembic/PostgreSQL-safe index practices from the repo's existing migration style. | | |
| TASK-052 | Create `apps/api/app/routers/ingestion_jobs_router.py` exposing `POST /api/admin/ingestion/jobs`, `GET /api/admin/ingestion/jobs`, `GET /api/admin/ingestion/jobs/{id}`, `GET /api/admin/ingestion/jobs/{id}/logs`, and `POST /api/admin/ingestion/jobs/{id}/retry`. Gate browser/API job triggers with `require_role("owner", "admin")` for the first dashboard release. | | |
| TASK-053 | Wire the router in `apps/api/app/main.py` and add API tests under `apps/api/tests/test_ingestion_jobs.py`. Use auth-disabled test mode from `apps/api/tests/conftest.py`. Mock remote SSH/job runner calls; do not call staging from unit tests. | | |
| TASK-054 | Extend `apps/api/app/source_monitoring.py` and `apps/frontend/src/pages/monitoring/MonitoringGlobalView.tsx` only after the persistent job API exists. Show recent job status beside the existing ledger/source health view. | | |

## 3. Alternatives

- **ALT-001**: Build API/admin UI first. Rejected for MVP because current production-safe job state is CLI/systemd/ledger based, the existing diagnostics router uses in-memory jobs that are not durable, and browser-triggered ingestion needs stronger RBAC/audit design before broad use.
- **ALT-002**: Use Azure CLI `az vm run-command invoke` as the main execution primitive. Rejected for MVP because long-running downloads need streamable logs, durable files, shell-level least privilege, and simple file transfer; SSH plus remote wrapper handles these better. Azure CLI remains useful for VM discovery and onboarding validation.
- **ALT-003**: Let every developer run Bhoonidhi downloads locally. Rejected because Bhoonidhi access is IP-whitelisted to Aakasha Staging and credentials must not be distributed to developer machines.
- **ALT-004**: Expose ingestion-worker or MinIO publicly for team use. Rejected because it violates the one-public-service rule and increases credential/object-storage exposure.
- **ALT-005**: Introduce Celery/RQ/Redis immediately. Rejected for MVP because the existing worker is an ephemeral Docker Compose job, the team needs a near-term centralized workflow, and file-based job artifacts plus the existing SQLite ledger are enough for the first iteration.

## 4. Dependencies

- **DEP-001**: Aakasha Staging Azure VM `akasha-staging` must keep a **reserved static** egress IP `20.219.3.35` for Bhoonidhi/Bhuvan access; a dynamic IP that can change on dealloc/realloc is not acceptable.
- **DEP-002**: SSH access to Aakasha Staging must exist for the team through alias `akasha-staging`, `AKASHA_STAGING_SSH_HOST`, or an approved Azure-managed SSH setup.
- **DEP-003**: Coolify/Docker Compose stack on Aakasha Staging must include the `ingestion-worker` service and the Bhoonidhi env values required by `worker.py bhoonidhi-sync`.
- **DEP-004**: Staging paths `/srv/akasha/data/raw/bhoonidhi`, `/srv/akasha/data/work/bhoonidhi`, `/srv/akasha/data/seed/rasters`, and `/srv/akasha/ingestion` must exist on the large data disk.
- **DEP-005**: Local developer machines must have Python, SSH, Docker, and Docker Compose for local MinIO/STAC import.
- **DEP-006**: Existing scripts `services/ingestion/worker.py`, `services/ingestion/akasha_ingest/sync.py`, and `scripts/sync_staging_raster_bundle.py` must remain compatible with current ResourceSat ingestion behavior.
- **DEP-007**: Existing local Docker Compose file `infra/docker/docker-compose.yml` must remain the local MinIO/STAC import target for `sync_staging_raster_bundle.py`.
- **DEP-008**: Future API/dashboard phase depends on the app schema Alembic migration path under `apps/api/alembic/` and existing auth/RBAC helpers in `apps/api/app/auth.py`.

## 5. Files

- **FILE-001**: Create `services/ingestion/akasha_ingest/pipeline_registry.py` — source/provider/prepare-script/default capability registry for ingestion jobs.
- **FILE-002**: Modify `services/ingestion/akasha_ingest/sync.py` — delegate prepare script lookup to `pipeline_registry` (mirroring the full `PREPARE_SCRIPTS` mapping, CON-005) while preserving `prepare_script_path()`.
- **FILE-003**: Create `infra/selfhosted/systemd/akasha-ingestion-job.sh` — restricted remote control command for start/status/logs/list/retry/validate/doctor/prune.
- **FILE-004**: Create `infra/selfhosted/systemd/akasha-ingestion-job-runner.sh` — long-running remote runner that discovers Compose, runs `worker.py bhoonidhi-sync`, and writes job artifacts.
- **FILE-005**: Create `infra/selfhosted/systemd/akasha-ingestion-jobs.env.example` — staging env template for allowed sources/AOIs, roots, defaults, and retention.
- **FILE-006**: Create `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh` — installer for staging scripts, env file, job root, and permissions.
- **FILE-007**: Create `scripts/staging_ingestion_job.py` — local developer CLI for trigger/status/logs/list/retry/validate/sync-local/doctor.
- **FILE-008**: Modify `scripts/sync_staging_raster_bundle.py` — add `--job-id`, `--remote-manifest`, and clearer import output while preserving existing safe tar and MinIO import behavior.
- **FILE-009**: Modify `infra/selfhosted/README.md` — add centralized ad hoc ingestion job installation and usage runbook.
- **FILE-010**: Modify `docs/data-ingestion-and-satellite-rules.md` — add source-onboarding validation rule.
- **FILE-011**: Modify `docs/engineering-dos-donts.md` — add staging egress and raw-download guardrails.
- **FILE-012**: Create `tests/test_pipeline_registry.py` — tests for source registry behavior.
- **FILE-013**: Create `tests/test_staging_ingestion_job_artifacts.py` — tests for remote shell artifacts and content contracts.
- **FILE-014**: Create `tests/test_staging_ingestion_job.py` — tests for local CLI command construction and behavior.
- **FILE-015**: Create or modify `tests/test_sync_staging_raster_bundle.py` — tests for job-id/manifest sync additions and existing safe extraction/import behavior.
- **FILE-016**: Optionally modify `apps/api/app/models.py` — deferred `IngestionJob` ORM model after CLI stabilization.
- **FILE-017**: Optionally add `apps/api/alembic/versions/<revision>_add_ingestion_jobs.py` — deferred Postgres job table migration.
- **FILE-018**: Optionally create `apps/api/app/routers/ingestion_jobs_router.py` — deferred API/admin job router.
- **FILE-019**: Optionally modify `apps/api/app/main.py` — deferred router registration.
- **FILE-020**: Optionally modify `apps/frontend/src/pages/monitoring/MonitoringGlobalView.tsx` — deferred dashboard status display.
- **FILE-021**: Create `infra/selfhosted/systemd/akasha-ingestion-forced-command.sh` — SSH forced-command guard restricting team keys to `akasha-ingestion-job.sh` subcommands (SEC-005).

## 6. Testing

- **TEST-001**: Run `python -m pytest tests/test_pipeline_registry.py -q` to verify source registry entries and unsupported-source behavior.
- **TEST-002**: Run `python -m pytest tests/test_staging_ingestion_job_artifacts.py -q` to verify remote shell script artifacts and static content contracts.
- **TEST-003**: Run `python -m pytest tests/test_staging_ingestion_job.py -q` to verify local CLI argument parsing, SSH command construction, retry/status/log/sync-local behavior, and Windows-safe subprocess usage.
- **TEST-004**: Run `python -m pytest tests/test_sync_staging_raster_bundle.py -q` to verify job-id and remote-manifest sync behavior plus safe tar extraction and local MinIO import command shape.
- **TEST-005**: Run `python -m pytest tests/test_bhoonidhi_ingestion.py tests/test_bhoonidhi_systemd_artifacts.py tests/test_validate_selfhosted_staging_bhoonidhi.py -q` to protect existing Bhoonidhi worker, systemd, and staging validator behavior.
- **TEST-006**: Run `ruff check services/ingestion scripts tests` to lint new Python scripts and tests.
- **TEST-007**: Run remote installer dry run on staging: `infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh --dry-run`. Verify printed actions target `/opt/akasha/bin`, `/etc/akasha/ingestion-jobs.env`, and `/srv/akasha/ingestion/jobs`.
- **TEST-008**: Run local doctor from a developer workstation: `python scripts/staging_ingestion_job.py doctor --host akasha-staging`. Verify SSH, remote runner, compose discovery, staging disk, local Docker, and local raster seed checks pass.
- **TEST-009**: Run dry-run ingestion: `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --dry-run --wait`. Verify status `succeeded`, job artifacts exist, and no raw download is created.
- **TEST-010**: Run capped real ingestion: `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --max-downloads 1 --wait`. Verify success or a classified provider/data failure with actionable logs.
- **TEST-011**: Run remote validation: `python scripts/staging_ingestion_job.py validate <job_id> --host akasha-staging`. Verify `worker.py verify-composite` passes for the produced composite.
- **TEST-012**: Run local import: `python scripts/staging_ingestion_job.py sync-local <job_id> --host akasha-staging --import-local --verify-local`. Verify final COG/TIFF artifacts are pulled and ingested into local MinIO/STAC.
- **TEST-013**: Run existing staging validator after deployment: `python scripts/validate_selfhosted_staging_bhoonidhi.py --expected-sha <deployed-git-sha> --skip-timer-check --public-origin https://staging.gis.cidsaglobal.com`.
- **TEST-014**: For the deferred API phase, run `cd apps/api && python -m pytest -q` after adding the ORM, migration, and router. On Windows, use a fresh pytest base temp directory if the known temp cleanup flake appears.

## 7. Risks & Assumptions

- **RISK-001**: Team members could overload Bhoonidhi download limits if too many jobs are triggered. Mitigation: enforce source/AOI locks, default `max_downloads=3`, allowed-source lists, and later add per-requester daily caps.
- **RISK-002**: Broad SSH access could become broad VM shell access. Mitigation: use a restricted `akasha-ingesters` group, forced command or sudoers restrictions, and read-only log access.
- **RISK-003**: Raw downloads or temp files could fill the OS disk. Mitigation: preflight `/srv/akasha` paths, document disk guardrails, and keep raw/temp roots under `/srv/akasha`.
- **RISK-004**: Job status files may diverge from the SQLite ingestion ledger when the worker fails before writing expected manifests. Mitigation: status files record runner-level failures, and monitoring continues reading the ledger for product-level status.
- **RISK-005**: `systemd-run` behavior can differ across Linux distributions. Mitigation: `start` launches the runner detached (`systemd-run` when present, else `setsid nohup ... &` with a `runner.pid`) and always returns immediately, so the async `status`/`logs` contract holds even without `systemd-run`; it never runs synchronously.
- **RISK-006**: Shell JSON parsing can be fragile. Mitigation: keep request schema simple, validate locally in Python, and use Python one-liners or `python3` inside remote scripts for JSON extraction when `jq` is not guaranteed.
- **RISK-007**: Local MinIO import can fail when the local Docker stack is not running. Mitigation: `doctor` checks local Docker/Compose, and `sync-local` surfaces the exact failing local command.
- **RISK-008**: Future API/admin UI could accidentally use the temporary in-memory diagnostics pattern. Mitigation: this plan explicitly requires a Postgres-backed `IngestionJob` table for the API phase.
- **RISK-009**: Without a shared lock, an ad hoc job and the scheduled `akasha-bhoonidhi-sync`/`akasha-bhoonidhi-liss4-sync` timers could run the same source/AOI concurrently and double-hit Bhoonidhi. Mitigation: the runner passes and checks the same `/srv/akasha/ingestion/bhoonidhi-sync.<aoi_id>.worker.lock` path (CON-004) and refuses concurrent same-source/AOI jobs (CON-006).
- **RISK-010**: Delegating `prepare_script_name` to a partial registry would silently route `sentinel-1-grd`, `eos-04-sar-mrs-l2b`, and `nisar-ssar-beta-gcov` to the LISS-3 prepare script. Mitigation: the registry mirrors the full `PREPARE_SCRIPTS` mapping and `tests/test_pipeline_registry.py` asserts each source's script (CON-005, TASK-004).
- **ASSUMPTION-001**: Aakasha Staging continues to have the approved Bhoonidhi/Bhuvan egress IP `20.219.3.35`.
- **ASSUMPTION-002**: The deployed Coolify Compose stack continues to include `ingestion-worker` and the required Bhoonidhi/S3/STAC/Postgres environment values.
- **ASSUMPTION-003**: The existing ResourceSat ingestion path remains the canonical path for MVP sources.
- **ASSUMPTION-004**: Developers have or can be granted SSH access to the staging VM through an approved team access model.
- **ASSUMPTION-005**: Developers use local Docker Compose/MinIO/STAC for testing final transformed COG/TIFF artifacts.

## 8. Related Specifications / Further Reading

- `AGENTS.md` — repository architecture, one-public-service rule, ResourceSat guardrails, ingestion commands, and testing commands.
- `docs/impl-plan/isro-bhoonidhi-ingestion-phase-plan.md` — canonical ResourceSat/Bhoonidhi ingestion pipeline and satellite-data rules.
- `infra/selfhosted/README.md` — self-hosted Coolify/Azure deployment, scheduled Bhoonidhi sync, staging validation, and one-shot job guidance.
- `infra/selfhosted/systemd/akasha-bhoonidhi-sync.sh` — existing scheduled sync wrapper to reuse for Compose discovery and worker command shape.
- `infra/selfhosted/systemd/akasha-bhoonidhi-sync.env.example` — existing sync environment template to mirror for ad hoc job defaults.
- `services/ingestion/worker.py` — existing ingestion worker CLI and `bhoonidhi-sync` command.
- `services/ingestion/akasha_ingest/sync.py` — existing SQLite ledger, lock, backfill, retry, and prepare-script helper behavior.
- `scripts/sync_staging_raster_bundle.py` — existing SSH tar-stream final bundle sync and local MinIO/STAC import script.
- `scripts/validate_selfhosted_staging_bhoonidhi.py` — existing staging validation script.
- `apps/api/app/source_monitoring.py` — existing ledger reader, failure classification, and secret-redaction patterns.
- `apps/api/app/routers/bhoonidhi_router.py` — temporary diagnostics job pattern; useful as a polling-shape reference only, not as a production persistence pattern.
- `docs/data-ingestion-and-satellite-rules.md` — satellite data, masks, indices, COG/STAC, and source capability guardrails.
- `docs/engineering-dos-donts.md` — engineering guardrails for services, browser access, and satellite-source correctness.
