---
goal: Two-VM Akasha Deployment Migration and CI/CD Implementation Plan
version: 1.2
date_created: 2026-07-04
last_updated: 2026-07-04
owner: Akasha Engineering
tags: infrastructure, migration, cicd, deployment, ingestion, coolify, azure
---

# Introduction

This plan defines the complete implementation path to move the Akasha product application from `akasha-staging` to `akasha-control`, convert `akasha-staging` into the provider-whitelisted standalone ingestion/pipeline VM, create CI/CD for `akasha-ingestion`, deploy the ingestion platform on `akasha-staging`, and validate private app-to-ingestion connectivity end-to-end.

The final target architecture is:

- `akasha-control`: Coolify control/public-app VM running the product application (`akasha-em-git`) and exposing only the product web gateway to browsers.
- `akasha-staging`: provider-whitelisted ingestion VM running the standalone `akasha-ingestion` platform, including ingestion API, workers, Postgres/PostGIS/pgSTAC, MinIO, Redis, TiTiler, scheduler, and dispatchers.
- Browser traffic must call only the product app origin. The product app BFF calls ingestion server-to-server over private networking using `INGESTION_API_URL` and `INGESTION_API_KEY`.

## 0. Review Validation Snapshot

Validated on 2026-07-04 against the current `akasha-em-git` repository, sibling `akasha-ingestion` repository, and non-interactive SSH checks to `akasha-control` / `akasha-staging`.

- `akasha-control` currently runs Coolify services only; it does not yet run the product app stack.
- `akasha-staging` still runs the old product app stack (`web`, `api`, `stac-api`, `titiler`, `postgis`, `minio`) at image SHA `8080b9f71d3baf94bcc19123febe4fa0a31ae690`; cleanup/decommissioning must remain gated behind backup and acceptance.
- Private reachability from `akasha-control` to `akasha-staging` is open for `22`, `80`, and `443`; `8000`, `8080`, `5432`, `6379`, `9000`, and `9001` are closed from the control VM.
- `akasha-staging` still has host listeners on `0.0.0.0:80`, `0.0.0.0:443`, `0.0.0.0:8080`, and `0.0.0.0:8888`. Before declaring ingestion private, the plan must close, bind, or explicitly justify every non-required public listener, especially `8080` and `8888`.
- Current app deploy workflows still build and verify `akasha-ingestion-worker` and `akasha-ingestion-sar` images, and `infra/selfhosted/coolify-compose.yml` still defines those services. The app-only split must update compose and both deploy workflows atomically.
- The sibling `akasha-ingestion` repository has CI at `.github/workflows/ci.yml`, but no sync/deploy workflows yet. Its base `deploy/docker-compose.yml` uses local `build:` contexts and publishes Caddy as `${AKASHA_HTTP_PORT:-8080}:80`; CI/CD must add a production/staging override that uses immutable GHCR images and private/bound ingress.
- App admin ingestion triggers currently write request JSON to the API container's local `INGESTION_JOB_INBOX_DIR`. After the BFF moves to `akasha-control`, that local path will not be drained by the `akasha-staging` dispatcher unless a remote handoff is implemented. Keep `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false` on `akasha-control` until the handoff is explicitly solved.
- Current product app compose hardcodes `/srv/akasha` host mounts, while `akasha-control`'s data disk is `/data`. The app-only compose must parameterize its host data root and use `/data/akasha` on `akasha-control`, otherwise Docker can create app Postgres/MinIO data on the 64 GiB OS disk.
- The app API image runs `python -m app.cli db upgrade` before Uvicorn on every startup. If preserving existing app data, the staging dump must be restored before the control API container first starts against the target database.
- The ingestion compose has multiple `build:` services (`api`, `migrate`, `seed`, `scheduler`, `worker-*`, and `pgbackrest`) and the init jobs are under `profiles: ["tools"]`. A SHA deploy must replace every runtime build with immutable images and run profiled init jobs explicitly before `up -d`.
- The migration cannot validate only Sentinel-2 pipeline analytics. The product app's native default ResourceSat path (`resourcesat-2a-liss3-boa`) must either be smoke-tested on `akasha-control` or intentionally disabled/repointed during migration.

## 1. Requirements & Constraints

- **REQ-001**: Move the product app currently running on `akasha-staging` to `akasha-control` under Coolify.
- **REQ-002**: Keep `akasha-staging` dedicated to ingestion because Bhoonidhi/ISRO provider access is whitelisted only there.
- **REQ-003**: Clean `akasha-staging` after product app migration so it contains only required ingestion/runtime dependencies and data.
- **REQ-004**: Preserve product app data during migration: users, teams, fields, seasons, operations, settings, and any app-owned data required for current functionality.
- **REQ-005**: Add or validate CI/CD for the product app after the VM move.
- **REQ-006**: Add CI/CD for `akasha-ingestion`, including source-to-client sync if required, GHCR image build/push, immutable SHA deployment, and rollback path.
- **REQ-007**: Deploy `akasha-ingestion` on `akasha-staging` and validate readiness, field-index statistics, and field-clipped overlay rendering.
- **REQ-008**: Configure private app-to-ingestion networking from `akasha-control` to `akasha-staging`.
- **REQ-009**: Validate the frontend field analytics page can retrieve Sentinel-2 NDVI statistics and field-clipped overlays through the app BFF.
- **REQ-010**: Keep field analytics map rendering on the clipped overlay path: `GET /api/fields/{fieldId}/overlay/NDVI.png?sourceId=sentinel-2-l2a&acquisitionDate=...`.
- **REQ-011**: Ensure `AKASHA_PUBLIC_BASE_URL` in `akasha-ingestion` exactly matches the app BFF `INGESTION_API_URL` prefix.
- **REQ-012**: Ensure app-side browser responses do not expose ingestion hostnames, signed ingestion URLs, MinIO URLs, Postgres, pgSTAC, or TiTiler URLs.
- **REQ-013**: Keep admin live ingestion triggers disabled on `akasha-control` until there is a validated cross-VM handoff to `akasha-staging` (for example an ingestion API job endpoint, a private remote mount, or a forced-command SSH dispatcher). A local inbox on the control VM is not sufficient.
- **REQ-014**: Product app persistent mounts on `akasha-control` must use the control data disk (`/data/akasha` or an explicitly approved equivalent), not staging-only `/srv/akasha` paths.
- **REQ-015**: When preserving product app data, restore the app Postgres backup before the target API container first runs its startup Alembic upgrade.
- **REQ-016**: Validate the product app's native ResourceSat/FCC/default-source functionality after the move, not only the Sentinel-2 ingestion bridge.
- **SEC-001**: The browser must never call `akasha-staging`, ingestion API, MinIO, Postgres, pgSTAC, Redis, or TiTiler directly.
- **SEC-002**: Ingestion API must require `X-API-Key` for all API routes except `/health` and signed URL routes (`/api/v1/analytics/field-index/{query_id}` and `/api/v1/analytics/field-index/{query_id}/overlay.png`), which must require valid HMAC `op/exp/kid/sig` parameters.
- **SEC-003**: Store ingestion API keys hashed in `AKASHA_API_KEY_HASHES`; store plaintext `INGESTION_API_KEY` only in app deployment secrets.
- **SEC-004**: Do not commit real secrets, passwords, Bhoonidhi credentials, API keys, signing secrets, Coolify tokens, SSH keys, or database dumps.
- **SEC-005**: Ingestion Postgres, MinIO, Redis, pgSTAC, and TiTiler must not have public domains or broad public firewall rules.
- **SEC-006**: Prefer private DNS plus TLS for app-to-ingestion; minimum staging posture is private network + API key + app-VM private-IP allowlist.
- **SEC-007**: `akasha-staging` must not keep broad public listeners for ingestion or legacy Coolify routes. Public listeners `8080` and `8888` must be closed, rebound to private/localhost, or documented with an explicit owner and firewall rule before acceptance.
- **OPS-001**: Observed VM capacity: `akasha-control` is Azure `Standard_D4s_v4`, 4 vCPU, ~16 GiB RAM, 64 GiB OS disk, 256 GiB `/data` disk.
- **OPS-002**: Observed VM capacity: `akasha-staging` is Azure `Standard_D4s_v4`, 4 vCPU, ~16 GiB RAM, 256 GiB OS disk, 512 GiB `/srv/akasha` disk.
- **OPS-003**: Observed private IPs: `akasha-control=10.10.1.4`, `akasha-staging=10.10.2.4`.
- **OPS-004**: Observed private connectivity from `akasha-control` to `akasha-staging`: ports `22`, `80`, and `443` open; ports `8000`, `8080`, `5432`, `6379`, `9000`, and `9001` closed.
- **OPS-005**: Observed `akasha-control` runtime: Coolify services only (`coolify`, `coolify-db`, `coolify-redis`, `coolify-realtime`, `coolify-proxy`, `coolify-sentinel`); no product app containers running yet.
- **OPS-006**: Observed `akasha-staging` runtime: old product app containers are still running and healthy (`web`, `api`, `stac-api`, `titiler`, `postgis`, `minio`) at app image SHA `8080b9f71d3baf94bcc19123febe4fa0a31ae690`.
- **OPS-007**: Observed `akasha-staging` host listeners include `0.0.0.0:80`, `0.0.0.0:443`, `0.0.0.0:8080`, and `0.0.0.0:8888`; these must be reconciled with the private-ingestion target before external acceptance.
- **CON-001**: Product app bulk raster/provider processing must not be moved to `akasha-control`.
- **CON-002**: All ingestion raw/download/work/COG/composite/scratch data must stay under `/srv/akasha` on `akasha-staging`.
- **CON-003**: Current VM size is acceptable for MVP only with bounded ingestion jobs; scale up before concurrent heavy backfills/composites.
- **CON-004**: Existing product app CI/CD uses source repo sync to client repo and Coolify deploy on a runner labeled `akasha-control`.
- **CON-005**: Existing `akasha-ingestion` repo has CI only; sync/deploy workflows must be added.
- **CON-006**: Product app deploy workflows currently build/verify legacy app-bundled ingestion images. Removing those services from the product compose also requires removing those images from the app workflow build matrix and manifest verification loops.
- **CON-007**: `akasha-ingestion` base Compose currently uses local `build:` contexts. Automated staging deployment must render or override it to use immutable GHCR image references, not source builds on the VM.
- **CON-008**: `akasha-ingestion` base Compose publishes Caddy with `${AKASHA_HTTP_PORT:-8080}:80` on all host interfaces by default. Staging deployment must bind this to a private IP/localhost or enforce equivalent firewall/NSG restrictions.
- **CON-009**: `infra/selfhosted/coolify-compose.yml` currently uses `/srv/akasha` host paths; the app-only compose must not place control VM data there unless `/srv/akasha` is explicitly created on the control data disk.
- **CON-010**: `apps/api/Dockerfile` auto-runs Alembic on API startup; migration sequencing must account for this instead of starting the API before restoring preserved data.
- **CON-011**: `akasha-ingestion` init jobs (`pgstac-migrate`, `migrate`, `seed`) are profiled tools services; a plain `docker compose up -d` does not run them.
- **CON-012**: Existing legacy app MinIO and new ingestion MinIO can collide on `/srv/akasha/minio` if old app volumes are preserved. Use a distinct ingestion data root or move legacy data before deploy.
- **PAT-001**: Use immutable Git SHA image tags for app and ingestion deployments.
- **PAT-002**: Verify GHCR image manifests before patching/deploying runtime stacks.
- **PAT-003**: Preserve one-public-service rule: only the product `web` service receives a public browser-facing endpoint.
- **PAT-004**: Prefer direct Docker Compose/systemd deployment for private ingestion on `akasha-staging`; use Coolify for the product app on `akasha-control`.
- **PAT-005**: Keep app-side `pipeline_proxy_records` only for opaque app-domain proxy metadata; field map path uses clipped overlay endpoint, not full-scene XYZ tiles.

## 2. Implementation Steps

### Implementation Phase 1: Baseline Capture and Rollback Preparation

- GOAL-001: Capture the current runtime state and create safe rollback points before moving any service.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | On `akasha-control`, capture current VM state: `hostname`, Azure VM size, private IP, disk usage, Docker version, running containers, Coolify stack UUIDs, public FQDNs, and image tags. Store sanitized output in the operator handoff notes; do not include secrets. | | |
| TASK-002 | On `akasha-staging`, capture current VM state: running product app containers, image tags, mounted volumes, private IP, disk usage, Docker version, and current port listeners. Store sanitized output in the operator handoff notes. | | |
| TASK-003 | Backup product app Postgres from `akasha-staging` before migration. Include schemas/tables for users, teams, fields, seasons, activities, reports, settings, sessions if needed, and `pipeline_proxy_records` if retaining local integration history. | | |
| TASK-004 | Backup product app MinIO/app object data from `akasha-staging` only if it contains app-native required runtime data. Do not copy ingestion raw/work/COG bulk data to `akasha-control`. | | |
| TASK-005 | Export or screenshot the current Coolify service stack configuration on `akasha-control`, including service UUIDs and environment variable names without values. | | |
| TASK-006 | Define rollback artifacts: previous app GHCR SHA, previous Coolify compose, product app DB dump path, and restoration command owner. | | |

### Implementation Phase 2: Documentation and Agent Guardrails

- GOAL-002: Make the two-VM architecture explicit in agent instructions and deployment runbooks.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Verify `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\AGENTS.md` contains the `akasha-control` + `akasha-staging` topology, server-to-server ingestion rule, `AKASHA_PUBLIC_BASE_URL`/`INGESTION_API_URL` prefix rule, and field-clipped overlay contract. | | |
| TASK-008 | Verify `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\AGENTS.md` contains provider-whitelisted staging rules, product-app integration contract, and field-clipped `overlayUrl` requirements. | | |
| TASK-009 | Update `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\README.md` to describe product app deployment on `akasha-control`, private ingestion bridge variables, and app migration validation. | | |
| TASK-010 | Update `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\docs\phase-1\deployment-runbook.md` to describe `akasha-staging` standalone ingestion deployment, `/srv/akasha` layout, API key setup, and private Caddy/API exposure. | | |
| TASK-011 | Commit this plan file at `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\docs\impl-plan\infrastructure-two-vm-cicd-migration-1.md`. | | |

### Implementation Phase 3: Product App Compose Split

- GOAL-003: Remove provider-ingestion responsibility from the product app deployment stack.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Review `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\coolify-compose.yml` and list services that belong to the product app versus legacy bundled ingestion. | | |
| TASK-013 | Create an app-only Coolify compose path by either editing `infra/selfhosted/coolify-compose.yml` or adding a new app-only compose file. Product app services must include `web`, `api`, and app-owned data services needed for current ResourceSat/native functionality. Parameterize all app host mount roots with `APP_DATA_ROOT` (recommended default on `akasha-control`: `/data/akasha`) and replace staging-only `/srv/akasha` binds for app Postgres, MinIO, seed/reference data, and any API mounts. Either populate seed/reference mounts under `APP_DATA_ROOT` or point `AOI_CONFIG_PATH` at an in-image default so `/api/config` does not silently lose the Bangalore AOI. | | |
| TASK-014 | Remove or disable legacy provider execution services from the product app stack: `ingestion-worker` and `ingestion-sar`. If rollback requires retaining them, set `profiles` or documented disabled state so they do not run by default on `akasha-control`. Also remove Bhoonidhi provider credentials, diagnostics mounts, and scheduler/inbox mounts from the control VM unless there is an explicit non-provider diagnostic requirement. | | |
| TASK-015 | Ensure only `web` has a Coolify public FQDN. Confirm `api`, app DB, MinIO, TiTiler, and STAC services have no host `ports:` mappings or public domains. | | |
| TASK-016 | Update `infra/selfhosted/env.example` to keep server-only ingestion bridge variables and remove any wording that implies browser-visible ingestion access. Required values: `APP_DATA_ROOT=/data/akasha`, `INGESTION_API_URL`, `INGESTION_API_KEY`, `INGESTION_FIELD_INDEX_ENABLED`, `INGESTION_FIELD_INDEX_SOURCE_ID`, `INGESTION_READINESS_ENABLED`, `INGESTION_AOI_ID`, and `INGESTION_PIPELINE_TILE_LAYER_ENABLED=false`. Keep `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false` unless Phase 9 adds a validated cross-VM trigger handoff. | | |
| TASK-017 | Run `docker compose -f infra/selfhosted/coolify-compose.yml config --quiet` or an equivalent rendered-template validation after compose changes. | | |

### Implementation Phase 4: Product App CI/CD Verification and Adjustment

- GOAL-004: Ensure the product app source-to-client sync and Coolify deployment work for the new `akasha-control` target.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Verify source workflow `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\sync-client-main.yml` syncs source `main` to the client repository `Akasha-TechCatalyst/akasha-project` as intended. | | |
| TASK-019 | Verify client repository secrets: `CLIENT_REPO_SYNC_SSH_KEY`, `COOLIFY_API_URL`, `COOLIFY_TOKEN`. Do not print values. | | |
| TASK-020 | Verify client repository variables: `COOLIFY_STAGING_SERVICE_UUID`, `COOLIFY_PRODUCTION_SERVICE_UUID`, `VITE_BASEMAP_PROVIDER`, `VITE_ESRI_API_KEY`, `VITE_ESRI_BASEMAP_STYLE`, `VITE_ESRI_BASEMAP_STYLE_FAMILY`, `VITE_ESRI_BASEMAP_PLACES`, `VITE_ESRI_BASEMAP_SESSION_SECONDS`. | | |
| TASK-021 | Verify `deploy-staging.yml` runs on self-hosted runner labels `[self-hosted, linux, x64, akasha-control]` and that the runner is online in GitHub. | | |
| TASK-022 | Update image matrix and manifest verification loops in `.github/workflows/deploy-staging.yml` and `.github/workflows/deploy-production.yml` to match the app-only product stack. Current workflows still build/verify `akasha-ingestion-worker` and `akasha-ingestion-sar`; remove those once Phase 3 removes or profiles them out of the product compose. | | |
| TASK-023 | Run app CI from `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\ci.yml` on the migration branch. Required jobs: Python API tests, Alembic migration checks, frontend lint/test/build, validators, ingestion scheduler tests, Trivy. | | |
| TASK-024 | Trigger a manual staging deployment after compose/env changes and verify deployed app image SHA matches the workflow SHA in Coolify. The workflow must not stop at a successful Coolify PATCH; it must poll deployment/container health or public `web` `/health` until healthy, and fail/rollback on crash loops. | | |

### Implementation Phase 5: Product App Migration to `akasha-control`

- GOAL-005: Run the product app from `akasha-control` and validate it before decommissioning the old app stack on `akasha-staging`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | In Coolify on `akasha-control`, create or update the product app staging service stack using the app-only compose from Phase 3, but keep the API service from starting until preserved Postgres data has been restored. Use a temporary disabled/zero-replica API state or restore into the target database before deploying the full stack. | | |
| TASK-026 | Configure Coolify environment variables using `infra/selfhosted/env.example`. Set `APP_DATA_ROOT=/data/akasha`, `PUBLIC_ORIGIN`, `SERVICE_FQDN_WEB`, app DB credentials including `POSTGRES_PASSWORD_URLENCODED`, auth secrets, `INGESTION_FIELD_INDEX_SOURCE_ID`, and ingestion bridge variables. | | |
| TASK-027 | Restore product app Postgres data from the `akasha-staging` backup if preserving current users/fields/operations is required. Restore must complete before the API container's startup `python -m app.cli db upgrade`; never start the API against an empty DB when preserving current app data. | | |
| TASK-028 | Apply/verify app Alembic migrations after restore. The preferred path is to let the API startup migration bring the restored schema to head, then confirm revision includes `apps/api/alembic/versions/20260703_0005_pipeline_proxy_records.py`. | | |
| TASK-029 | Validate product app service health: `web` healthy, `api` healthy, app DB reachable, and `python -m app.cli db verify-current` passes inside the API container. | | |
| TASK-030 | Validate user flow on `akasha-control`: login, field list, field detail, field analytics page, and admin ingestion page load without server errors. | | |
| TASK-031 | Keep old app stack on `akasha-staging` stopped but restorable until all Phase 11 UI smoke checks pass. | | |

### Implementation Phase 6: Cleanup of `akasha-staging` Product App Artifacts

- GOAL-006: Clean `akasha-staging` so it can be dedicated to standalone ingestion.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | Stop old product app containers on `akasha-staging`: `web-*`, `api-*`, app `postgis-*`, app `minio-*`, app `titiler-*`, app `stac-api-*`, and related app-only services. | | |
| TASK-033 | Confirm no product app public web route remains active on `akasha-staging`. | | |
| TASK-034 | Preserve app DB/object backups for the agreed rollback window. Do not delete old app volumes until backup integrity and control deployment acceptance are confirmed. If old app volumes remain under `/srv/akasha`, move them under a dated `/srv/akasha/legacy-app/` path or choose a distinct ingestion data root before starting ingestion. | | |
| TASK-035 | Remove old app volumes after approval. Keep `/srv/akasha` reserved for ingestion data, logs, backups, raw, work, COGs, MinIO, Postgres, Redis, and monitoring. Assert new ingestion data targets are empty or intentionally restored before `docker compose up`. | | |
| TASK-036 | Confirm required host dependencies remain installed: Docker, Docker Compose plugin, SSH, firewall/NSG configuration, monitoring/backup tooling, and provider/network utilities. | | |
| TASK-037 | Confirm disk layout after cleanup: `/srv/akasha` on the 512 GiB data disk is available for ingestion; bulk data is not placed under `/`, `/tmp`, `/var/tmp`, `/var/lib/docker`, or `/data/coolify`. Confirm host listeners `8080` and `8888` are either closed or explicitly owned by the new private ingestion deployment. | | |

### Implementation Phase 7: Ingestion CI/CD Workflow Creation

- GOAL-007: Add repeatable CI/CD for `akasha-ingestion`, matching the quality of product app deployment automation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-038 | Confirm ingestion source repository: `nishanthturnstile/akasha-ingestion`. | | |
| TASK-039 | Confirm or create ingestion client/mirror repository. Proposed default: `Akasha-TechCatalyst/akasha-ingestion`. If a different repo is required, record it in the workflow env and deployment runbook. | | |
| TASK-040 | Add source sync workflow `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\.github\workflows\sync-client-main.yml`. It must mirror the app sync pattern, guard execution to the source repo, require a deploy key secret, and push source `main` to client `main`. | | |
| TASK-041 | Extend or retain ingestion CI at `.github/workflows/ci.yml`. Required checks: `python -m pip install -e ".[dev]"`, `ruff check .`, `pytest`, compose config validation, pgSTAC init, Alembic upgrade, seed, API image build, worker image build, geospatial import checks. | | |
| TASK-042 | Add ingestion staging deploy workflow in the client repo path `.github/workflows/deploy-staging.yml`. It must build and push immutable GHCR images for `akasha-ingestion-api` and `akasha-ingestion-worker` using Dockerfiles `docker/api.Dockerfile` and `docker/worker.Dockerfile`. Decide whether `pgbackrest` is published as a third immutable image, built only for backup profile runs, or omitted from the staging runtime. | | |
| TASK-043 | Add image manifest verification before deployment. The deploy workflow must fail before runtime changes if any expected SHA image is missing in GHCR. | | |
| TASK-044 | Choose deployment mechanism. Recommended implementation: SSH to `akasha-staging`, write/update a rendered compose/env bundle, run pgSTAC migration/Alembic/seed, and execute `docker compose up -d` for the ingestion stack. The rendered compose must remove every runtime `build:` entry: map `api`, `migrate`, and `seed` to `akasha-ingestion-api:<sha>`; map `scheduler`, `worker-search`, `worker-download`, `worker-process`, and `worker-heavy` to `akasha-ingestion-worker:<sha>`; handle `pgbackrest` per TASK-042. | | |
| TASK-045 | Add rollback workflow or documented manual rollback. It must deploy a previous immutable SHA and preserve the current env file and DB backups. | | |
| TASK-046 | Add GitHub secrets/vars for ingestion deployment: sync key, GHCR permissions, staging SSH private key, `AKASHA_STAGING_HOST`, deploy user, env-file secret source, and optional private Caddy hostname. | | |

### Implementation Phase 8: Standalone Ingestion Deployment on `akasha-staging`

- GOAL-008: Deploy `akasha-ingestion` on the provider-whitelisted VM with all runtime data under `/srv/akasha`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-047 | Prepare directories on `akasha-staging`: either `/srv/akasha/postgres`, `/srv/akasha/redis`, `/srv/akasha/minio`, `/srv/akasha/scratch`, `/srv/akasha/data/raw`, `/srv/akasha/data/work`, `/srv/akasha/monitoring`, `/srv/akasha/backups`, `/srv/akasha/caddy`, or a collision-free root such as `/srv/akasha/ingestion-platform/...` if legacy app data remains. | | |
| TASK-048 | Create ingestion env file outside source control. Required values include `AKASHA_DATA_ROOT=/srv/akasha` or the chosen collision-free subroot, `AKASHA_RUNTIME_BACKEND=external`, `AKASHA_API_KEY_HASHES`, `AKASHA_SIGNING_SECRET`, `AKASHA_PUBLIC_BASE_URL`, Postgres credentials, MinIO credentials, Redis URL, and provider credentials. If `AKASHA_SCRATCH_DIR` stays `/tmp/akasha` inside containers, confirm it is bind-mounted from the chosen data root's `scratch`; otherwise set it directly to that scratch path. | | |
| TASK-049 | Set `AKASHA_PUBLIC_BASE_URL` to the exact private URL that the app BFF will use as `INGESTION_API_URL`, including scheme, host, and port, with no trailing slash. Example for HTTP staging on the open private port: `http://10.10.2.4`. Verify a returned `overlayUrl` starts with that exact prefix. | | |
| TASK-050 | Deploy using `deploy/docker-compose.yml` plus `deploy/compose.prod.yml` and a new `deploy/compose.staging.yml` if needed. Ensure `AKASHA_DATA_ROOT` is set to the approved `/srv/akasha` root or collision-free subroot, immutable GHCR images are used, and Caddy/API ingress does not bind broadly to a public interface by default. | | |
| TASK-051 | Initialize database explicitly because the init services are under `profiles: ["tools"]`: run `docker compose --profile tools run --rm pgstac-migrate`, then `docker compose --profile tools run --rm migrate`, then `docker compose --profile tools run --rm seed` before the normal runtime `up -d`. | | |
| TASK-052 | Start ingestion services: API, scheduler, workers, Postgres/PostGIS/pgSTAC, Redis, MinIO, TiTiler, and Caddy. | | |
| TASK-052A | For `Standard_D4s_v4`, create a trimmed `compose.staging.yml`: gate monitoring behind an explicit profile or keep only required exporters, set Prometheus/Loki retention, cap `worker-heavy` memory/CPU, and configure host swap before first heavy composite/backfill. | | |
| TASK-053 | Configure worker resources for `Standard_D4s_v4`: heavy worker concurrency `1`, avoid concurrent heavy backfills, and monitor disk I/O during first full pipeline runs. | | |
| TASK-054 | Validate ingestion `/health` from the host and from `akasha-control`. | | |
| TASK-055 | Validate authenticated ingestion route `/api/v1/analytics/readiness?sourceId=sentinel-2-l2a&aoiId=bangalore_60km_geodesic_aoi` with `X-API-Key`. | | |

### Implementation Phase 9: Private Networking and Security Validation

- GOAL-009: Make the app BFF able to reach ingestion privately while keeping ingestion internals private.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-056 | Configure ingestion Caddy/API on `akasha-staging` to listen on the selected private endpoint, preferably private DNS over HTTPS or IP-allowlisted private HTTP/HTTPS for staging. Because private `8080` is currently closed from `akasha-control`, set `AKASHA_HTTP_PORT=80` for HTTP staging or terminate TLS on `443`; do not leave the default `${AKASHA_HTTP_PORT:-8080}:80` binding open on all interfaces unless NSG/firewall rules restrict it to the app VM. | | |
| TASK-056A | Decide the TLS posture. For HTTPS, update ingestion Caddy to use `:443` with `tls internal` or a provisioned private certificate and set both `AKASHA_PUBLIC_BASE_URL` and `INGESTION_API_URL` to `https://...`. Otherwise document HTTP-on-private-80 plus API key and app-VM private-IP allowlist as the accepted staging posture. | | |
| TASK-057 | Configure Azure NSG/firewall to allow app VM private IP `10.10.1.4` to the ingestion API endpoint on `akasha-staging`. | | |
| TASK-058 | Deny public access to ingestion Postgres, MinIO, Redis, pgSTAC, and TiTiler. | | |
| TASK-059 | From `akasha-control`, verify private ingestion API connectivity using `/health` and authenticated readiness. | | |
| TASK-060 | From an external workstation, verify ingestion internals are not reachable. At minimum test public exposure for ports `5432`, `6379`, `9000`, `9001`, `8080`, `8000`, `8888`, and any internal TiTiler/pgSTAC ports. | | |
| TASK-061 | Configure product app on `akasha-control` with `INGESTION_API_URL`, `INGESTION_API_KEY`, `INGESTION_FIELD_INDEX_ENABLED=true`, `INGESTION_READINESS_ENABLED=true`, and `INGESTION_AOI_ID=bangalore_60km_geodesic_aoi`. Keep `ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false` until a cross-VM trigger handoff is validated. | | |
| TASK-061A | Decide and validate the admin trigger and scheduler-observability handoff model for the two-VM split. Acceptable options include adding authenticated ingestion API routes, mounting private staging paths into the control API container, or using a forced-command SSH dispatcher from control to staging. Do not rely on local control-VM inbox, scheduler job, or ledger paths for staging-owned ingestion state. | | |
| TASK-062 | Confirm app BFF prefix validation passes by calling field overlay and verifying no `PIPELINE_UPSTREAM_FORBIDDEN` error occurs. | | |

### Implementation Phase 10: Ingestion Data Readiness Validation

- GOAL-010: Confirm ingestion has usable data before enabling the app-facing feature.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-063 | Run a bounded provider/backfill canary on `akasha-staging`. Use low concurrency and keep all raw/work/output data under `/srv/akasha`. | | |
| TASK-064 | Verify object lake state in MinIO: expected raw/source/derived COG objects exist and are non-zero size. | | |
| TASK-065 | Verify catalog state in Postgres/pgSTAC: collections, items, assets, scene records, raster outputs, and profile seeds are present. | | |
| TASK-066 | Verify `POST /api/v1/analytics/field-index` returns `AVAILABLE` for a test polygon inside the available Sentinel-2 scene footprint. | | |
| TASK-067 | Verify signed `overlayUrl` returns `image/png` and `X-Akasha-Overlay-Corners`. | | |
| TASK-068 | Verify readiness returns `AVAILABLE` for source `sentinel-2-l2a`, AOI `bangalore_60km_geodesic_aoi`, and NDVI coverage. | | |

### Implementation Phase 11: Product UI End-to-End Validation

- GOAL-011: Confirm the deployed frontend retrieves and renders ingestion data correctly through the app BFF.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-069 | Open the product app public origin served by `akasha-control`. | | |
| TASK-070 | Log in with a staging test user. | | |
| TASK-071 | Open a field analytics page for a field inside the available Sentinel-2 AOI/date. | | |
| TASK-072 | Select source `sentinel-2-l2a` and layer `NDVI`. | | |
| TASK-073 | Confirm the browser requests only app-domain field overlay endpoint: `/api/fields/{fieldId}/overlay/NDVI.png?sourceId=sentinel-2-l2a&acquisitionDate=...`. | | |
| TASK-074 | Confirm browser network has zero calls to ingestion host, MinIO, TiTiler, pgSTAC, signed ingestion URLs, or `/api/pipeline/tiles/*` for the field heatmap. | | |
| TASK-075 | Confirm map renders a field-clipped NDVI PNG only inside the field polygon. | | |
| TASK-076 | Confirm chart statistics render from the pipeline: mean, std dev, min, max, valid percentage, freshness, quality, and provider route. | | |
| TASK-077 | Confirm app and ingestion logs show expected server-to-server calls and no secret leakage. | | |
| TASK-077A | Validate native ResourceSat/default-source behavior on `akasha-control`: `/api/config`, `/api/sources`, source dates/layers, FCC tile rendering, and at least one app-native statistics request for `resourcesat-2a-liss3-boa`. If native ResourceSat is not expected during this migration, explicitly disable/repoint the default source before UI acceptance. | | |

### Implementation Phase 12: CI/CD Acceptance, Monitoring, and Rollback

- GOAL-012: Confirm both app and ingestion deployments are repeatable and reversible.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-078 | App CI/CD acceptance: push a no-op or versioned commit through source main, confirm sync to client repo, GHCR image build, Coolify patch on `akasha-control`, and running image SHA match. | | |
| TASK-079 | Ingestion CI/CD acceptance: push a no-op or versioned commit through ingestion source main, confirm sync if applicable, GHCR image build, deploy to `akasha-staging`, and running image SHA match. | | |
| TASK-080 | Confirm app rollback procedure restores the previous Coolify compose, environment, and immutable image SHA together. A rollback that only swaps the image tag is insufficient if compose/env changed during the migration. | | |
| TASK-081 | Confirm ingestion rollback procedure deploys a previous immutable SHA and preserves/restores the previous env file and database backup if needed. | | |
| TASK-082 | Add monitoring checks for ingestion readiness freshness, worker failures, MinIO disk usage, Postgres disk usage, and field-index error rate. | | |
| TASK-083 | Add a scheduled cleanup job or operational command for expired app `pipeline_proxy_records`. | | |
| TASK-084 | After acceptance, remove old app stack backups from `akasha-staging` only after explicit approval and retention-window completion. | | |

## 3. Alternatives

- **ALT-001**: Keep the product app on `akasha-staging` and move Coolify there. Rejected because Bhoonidhi provider access and ingestion disk/I/O workloads should be isolated on `akasha-staging`, and Coolify already runs on `akasha-control`.
- **ALT-002**: Run ingestion on `akasha-control` next to the product app. Rejected because Bhoonidhi/ISRO provider access is whitelisted only for `akasha-staging` and because raster processing should not compete with the public app/Coolify VM.
- **ALT-003**: Expose ingestion API publicly and call it from the browser. Rejected for security and architecture reasons; ingestion URLs, API keys, MinIO, Postgres, pgSTAC, and TiTiler must remain server-side/private.
- **ALT-004**: Keep product-app bundled ingestion workers in `akasha-em-git` self-hosted compose permanently. Rejected because it preserves the old collapsed deployment and conflicts with standalone `akasha-ingestion` ownership.
- **ALT-005**: Deploy ingestion through Coolify on `akasha-control`. Rejected as the primary recommendation because ingestion must run on provider-whitelisted `akasha-staging`. Coolify may still manage a remote/private ingestion stack only if it can run on staging with correct data mounts and no public exposure.
- **ALT-006**: Use full-scene XYZ tiles for field NDVI heatmap. Rejected because field analytics requires polygon-clipped NDVI rendering for the exact user-drawn coordinates.

## 4. Dependencies

- **DEP-001**: `akasha-control` SSH access and Coolify administrator access.
- **DEP-002**: `akasha-staging` SSH access and provider whitelist verification.
- **DEP-003**: GitHub access to source repositories `nishanthturnstile/akasha-project` and `nishanthturnstile/akasha-ingestion`.
- **DEP-004**: GitHub access to client/mirror repositories. App client repo is `Akasha-TechCatalyst/akasha-project`; ingestion client repo must be confirmed or created.
- **DEP-005**: GHCR package permissions for app and ingestion images.
- **DEP-006**: Coolify API token and service UUIDs for product app stacks on `akasha-control`.
- **DEP-007**: Ingestion deployment SSH key or equivalent deployment credential for `akasha-staging`.
- **DEP-008**: Bhoonidhi credentials and provider whitelist for `akasha-staging`.
- **DEP-009**: Azure private routing between `10.10.1.4` and `10.10.2.4`.
- **DEP-010**: Postgres/PostGIS/pgSTAC, MinIO, Redis, TiTiler, Docker, and Docker Compose runtime availability.
- **DEP-011**: App BFF ingestion bridge code already implemented: `IngestionClient`, `analytics_router` pipeline branch, field-clipped overlay path, and readiness bridge.
- **DEP-012**: Ingestion field-index and overlay code already implemented: `AnalyticsService.field_index`, signed `overlayUrl`, `overlay_for_query`, and `processing/overlay.py`.

## 5. Files

- **FILE-001**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\AGENTS.md` — app-side deployment and integration guardrails.
- **FILE-002**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\AGENTS.md` — ingestion-side deployment and integration guardrails.
- **FILE-003**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\sync-client-main.yml` — existing app source-to-client sync workflow.
- **FILE-004**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\deploy-staging.yml` — existing app staging deploy workflow.
- **FILE-005**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\deploy-production.yml` — existing app production deploy workflow.
- **FILE-006**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\.github\workflows\ci.yml` — app CI workflow.
- **FILE-007**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\coolify-compose.yml` — product app Coolify compose; must be split from legacy bundled ingestion.
- **FILE-008**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\env.example` — product app Coolify env template.
- **FILE-009**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\README.md` — product app self-hosted deployment runbook.
- **FILE-010**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\.github\workflows\ci.yml` — existing ingestion CI workflow.
- **FILE-011**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\.github\workflows\sync-client-main.yml` — new ingestion sync workflow to add if a mirror repo is required.
- **FILE-012**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\.github\workflows\deploy-staging.yml` — new ingestion staging deploy workflow to add.
- **FILE-013**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\.github\workflows\deploy-production.yml` — optional production ingestion deploy workflow to add after staging is stable.
- **FILE-014**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\deploy\docker-compose.yml` — standalone ingestion stack.
- **FILE-015**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\deploy\compose.prod.yml` — ingestion resource limits.
- **FILE-016**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\deploy\compose.staging.yml` — optional new staging override for private deployment and resource limits.
- **FILE-017**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\deploy\caddy\Caddyfile` — ingestion API ingress route.
- **FILE-018**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\docs\phase-1\deployment-runbook.md` — ingestion deployment runbook to update.
- **FILE-019**: `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\docs\impl-plan\infrastructure-two-vm-cicd-migration-1.md` — this implementation plan.

## 6. Testing

- **TEST-001**: Run app CI workflow checks locally or in GitHub: API tests, Alembic migration checks, frontend lint/test/build, validators, ingestion scheduler tests, and Trivy.
- **TEST-002**: Run ingestion CI workflow checks: install, `ruff check .`, `pytest`, compose config validation, pgSTAC init, Alembic upgrade, seed, API image build, worker image build, geospatial import checks.
- **TEST-003**: Validate app deploy workflow by triggering staging deploy and confirming Coolify stack on `akasha-control` runs expected image SHA.
- **TEST-004**: Validate ingestion deploy workflow by triggering staging deploy and confirming `akasha-staging` runs expected ingestion API/worker image SHA.
- **TEST-005**: Validate private connectivity from app VM/container to ingestion API `/health` and authenticated readiness.
- **TEST-006**: Validate public exposure scan: browser/public internet cannot reach ingestion Postgres, MinIO, Redis, pgSTAC, or TiTiler.
- **TEST-007**: Validate ingestion field-index: `POST /api/v1/analytics/field-index` returns `AVAILABLE` for a test polygon/date.
- **TEST-008**: Validate ingestion field-clipped overlay: signed `overlayUrl` returns `image/png` plus `X-Akasha-Overlay-Corners`.
- **TEST-009**: Validate deployed UI: field analytics map renders clipped NDVI only inside polygon and chart stats render.
- **TEST-010**: Validate browser network: only app-domain calls; no ingestion host, signed ingestion URL, MinIO, pgSTAC, TiTiler, or `/api/pipeline/tiles/*` for field heatmap.
- **TEST-011**: Validate cleanup: old product app containers are stopped on `akasha-staging`; ingestion containers are healthy; `/srv/akasha` disk usage is within thresholds.
- **TEST-012**: Validate rollback: redeploy previous app SHA and previous ingestion SHA in a non-production rehearsal.
- **TEST-013**: Validate native ResourceSat/default-source smoke on `akasha-control`: config/sources/dates/layers, FCC tiles, and a representative statistics call.

## 7. Risks & Assumptions

- **RISK-001**: Bhoonidhi provider access may fail if ingestion jobs run anywhere other than `akasha-staging`.
- **RISK-002**: App data migration can lose users/fields if Postgres backup/restore is incomplete.
- **RISK-003**: `AKASHA_PUBLIC_BASE_URL` and `INGESTION_API_URL` mismatch will cause BFF prefix validation failures such as `PIPELINE_UPSTREAM_FORBIDDEN`.
- **RISK-004**: Leaving legacy app-bundled ingestion workers enabled can cause provider jobs to run from the wrong VM.
- **RISK-005**: `Standard_D4s_v4` is not sufficient for concurrent heavy raster workloads; uncontrolled backfills can cause CPU, memory, or disk I/O contention.
- **RISK-006**: Public firewall or Coolify domain misconfiguration can expose ingestion internals.
- **RISK-007**: Ingestion CI/CD mirror repo is not yet confirmed; workflow implementation can be blocked until repository/permissions exist.
- **RISK-008**: Removing old app volumes from `akasha-staging` before acceptance can break rollback.
- **RISK-009**: No swap is configured on either VM; memory pressure during heavy raster jobs can kill containers.
- **RISK-010**: Admin live ingestion triggers can appear submitted but never execute after the BFF moves to `akasha-control` if they only write to a local inbox directory that the `akasha-staging` dispatcher does not read.
- **RISK-011**: The ingestion compose default Caddy binding can publish `8080` broadly. Without explicit bind/firewall changes, a private API can accidentally become public.
- **RISK-012**: Product app deploy workflows will fail or keep building obsolete images if the app-only compose split is not synchronized with the GHCR image matrix and manifest verification loops.
- **RISK-013**: Hardcoded `/srv/akasha` app mounts on `akasha-control` can put Postgres/MinIO on the small OS disk instead of the `/data` disk.
- **RISK-014**: Starting the app API before restoring preserved data can auto-run Alembic against an empty database and make the later restore conflict or lose data.
- **RISK-015**: Ingestion deployment can silently build from source on the VM if not every `build:` service is replaced by an immutable image in the rendered compose.
- **RISK-016**: Sentinel-2 bridge acceptance can pass while the product app's default ResourceSat/FCC path is broken after migration.
- **ASSUMPTION-001**: `akasha-control` remains the Coolify control/public-app VM.
- **ASSUMPTION-002**: `akasha-staging` remains provider-whitelisted for Bhoonidhi/ISRO access.
- **ASSUMPTION-003**: Azure private routing between `10.10.1.4` and `10.10.2.4` remains available.
- **ASSUMPTION-004**: Product app public traffic continues to enter only through the app `web` service.
- **ASSUMPTION-005**: Sentinel-2 NDVI pipeline field map uses clipped overlay PNG, not full-scene XYZ tiles.
- **ASSUMPTION-006**: Product app ResourceSat/native raster requirements are either preserved in the app stack or separately migrated in a later phase.

## 8. Related Specifications / Further Reading

- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\AGENTS.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\AGENTS.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\docs\impl-plan\feature-ui-pipeline-integration-1.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\README.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-em-git\infra\selfhosted\coolify-compose.yml`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\docs\phase-1\deployment-runbook.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\docs\architecture-technical-stack.md`
- `c:\Users\v-mnmurugan\thaarei projects\akasha\akasha-ingestion\deploy\docker-compose.yml`
