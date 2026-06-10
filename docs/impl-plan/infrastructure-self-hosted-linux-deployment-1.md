---
goal: Self-Hosted Linux Deployment Rehearsal for Azure VM, VPS, and Physical Server
version: 1.0
date_created: 2026-06-09
last_updated: 2026-06-09
owner: Akasha Engineering
tags: infrastructure, deployment, azure-vm, linux, docker-compose, on-prem, vps, railway-portability
---

# Introduction

This implementation plan prepares Akasha for a future self-hosted Linux deployment while keeping Railway as the current MVP deployment path. The immediate objective is to use an Azure Linux VM as a rehearsal environment that closely simulates a future raw physical Linux server or VPS deployment. The output of this plan is a repeatable, documented, and reviewable deployment kit under `infra/server/` plus validation runbooks that prove the application can be rebuilt, restarted, backed up, restored, and smoke-tested without relying on Railway-specific infrastructure.

The plan does not replace Railway. Railway remains the fastest production/demo path for the current MVP. This plan creates a parallel self-hosted path based on Docker Compose, Caddy, private Docker networking, persistent storage, scripted setup, backup/restore, and smoke testing. The final acceptance standard is that a fresh Azure VM can be provisioned and configured from the repository, environment secrets, and backups, and the same process can later be repeated on a physical Linux server or VPS.

## 1. Requirements & Constraints

- **REQ-001**: Railway must remain the active MVP deployment target until the self-hosted path passes all validation phases.
- **REQ-002**: The self-hosted deployment must preserve Akasha's service topology: `web`, `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and optional `ingestion-sar`.
- **REQ-003**: The self-hosted deployment must preserve the one-public-service rule: only `web`/Caddy is reachable from the internet.
- **REQ-004**: Browser traffic must remain same-origin through `web`: `/api/*` routes to `api`, and `/tiles/*` routes to `titiler`.
- **REQ-005**: `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and `ingestion-sar` must remain private on the Docker network.
- **REQ-006**: The Azure VM rehearsal must use Ubuntu LTS, Docker Engine, Docker Compose plugin, Caddy through the existing gateway container, persistent directories, and systemd-managed startup.
- **REQ-007**: The deployment kit must be stored under `infra/server/` and must not replace `infra/docker/docker-compose.yml`, which remains the local development Compose topology.
- **REQ-008**: The production-like self-hosted Compose file must use explicit persistent bind mounts under `/srv/akasha/data/` for PostGIS and MinIO state.
- **REQ-009**: The deployment must include backup and restore scripts for PostGIS and MinIO before it is considered production-ready.
- **REQ-010**: The deployment must include a smoke-test procedure that verifies `web`, `api`, `titiler`, `stac-api`, `/api/config`, `/api/sources`, `/api/layers/default`, one RGB tile, and one index statistics request when data is available.
- **REQ-011**: The Azure VM rehearsal must validate full reboot recovery, container restart recovery, backup creation, restore into a clean VM, and smoke-test success after restore.
- **REQ-012**: Operators must be able to rebuild the server from the repository, `.env` secrets, and backup artifacts without relying on undocumented manual commands.
- **REQ-013**: The self-hosted deployment must use exact internal Docker service hostnames, including `api`, `titiler`, `stac-api`, `postgis`, and `minio`, not Railway `*.railway.internal` domains.
- **REQ-014**: The self-hosted deployment must keep Railway environment variable names conceptually aligned with the Railway deployment guide where practical, while replacing upstream URLs with Docker service names.
- **REQ-015**: The implementation must include reviewer-facing sign-off gates for infrastructure, security, data persistence, backup/restore, and application smoke tests.
- **SEC-001**: SSH password login must be disabled on the Azure VM and future Linux servers.
- **SEC-002**: Only ports `22`, `80`, and `443` may be publicly reachable during the VM rehearsal. Port `22` may be limited to operator IP ranges where possible.
- **SEC-003**: PostGIS port `5432`, MinIO ports `9000` and `9001`, STAC API port `8080`, FastAPI port `8000`, and TiTiler port `8000` must not be published to the public internet.
- **SEC-004**: Production-like deployments must set `AUTH_MODE=enabled`, `AUTH_ALLOW_DISABLED=false`, `AUTH_COOKIE_SECURE=true`, and exact `CORS_ALLOWED_ORIGINS` values.
- **SEC-005**: Secrets must be supplied through an operator-managed `.env` file or secret manager and must not be committed to git.
- **SEC-006**: Default database, MinIO, bootstrap, and password pepper values must not be used in Azure VM, VPS, or physical server deployments.
- **SEC-007**: MinIO console must remain disabled or private. `MINIO_BROWSER=off` is required for the baseline self-hosted profile.
- **SEC-008**: `GATEWAY_BASIC_AUTH` may be used as an outer demo gate but must not replace application authentication.
- **OPS-001**: The deployment must define a standard server root at `/srv/akasha`.
- **OPS-002**: Persistent data must be stored under `/srv/akasha/data/postgis` and `/srv/akasha/data/minio`.
- **OPS-003**: Backups must be stored under `/srv/akasha/backups/postgis` and `/srv/akasha/backups/minio` or copied to an external backup target.
- **OPS-004**: Logs and operator output must be inspectable through Docker Compose and systemd commands.
- **OPS-005**: A separate Azure data disk should be mounted at `/srv/akasha/data` for rehearsal and production-like runs.
- **CON-001**: The existing `infra/docker/docker-compose.yml` is a local development and portability artifact, not a hardened production server Compose file.
- **CON-002**: The existing `infra/gateway/Caddyfile` already implements the required same-origin gateway shape and should be reused unless production TLS/domain routing requires a server-specific overlay.
- **CON-003**: Real raster data under `data/raw/`, `data/work/`, and generated COG output can be large and must not be committed to git.
- **CON-004**: PostGIS and MinIO are stateful and must not run on ephemeral-only storage for self-hosted deployments.
- **CON-005**: Azure VM rehearsal is not a substitute for backup/restore validation; a deployment is not production-ready until restore has been tested on a clean VM.
- **GUD-001**: Prefer repeatable scripts and runbooks over manual SSH steps.
- **GUD-002**: Every manual fix performed during the Azure VM rehearsal must be converted into a script, Compose change, or documented runbook step before sign-off.
- **GUD-003**: Prefer Docker Compose for the single-server self-hosted path. Do not introduce Kubernetes until multi-node scheduling or advanced orchestration is required.
- **GUD-004**: Prefer building immutable images in CI and pulling tagged images on the server after the first rehearsal succeeds.
- **GUD-005**: Keep Railway, local development, and self-hosted deployment documentation separate but aligned.
- **PAT-001**: Use Caddy as the only public gateway, matching the existing Railway and local Compose architecture.
- **PAT-002**: Use Docker service names for private internal networking on self-hosted deployments.
- **PAT-003**: Use systemd to start and restart the Compose stack after host reboot.
- **PAT-004**: Use explicit versioned Docker image tags and avoid floating `latest` tags.

## 2. Implementation Steps

### Implementation Phase 1 — Architecture Confirmation and Gap Closure

- GOAL-001: Confirm the current Railway/local topology is portable and document the gap between local Compose and production self-hosted deployment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Review `docs/railway-deployment-guide.md` and confirm the one-public-service topology remains authoritative for Railway and self-hosted deployments. | ✅ | 2026-06-09 |
| TASK-002 | Review `infra/docker/docker-compose.yml` and confirm it contains `web`, `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and `ingestion-sar` service boundaries. | ✅ | 2026-06-09 |
| TASK-003 | Review `infra/gateway/Caddyfile` and confirm it serves `/health`, proxies `/api/*` to `api`, proxies `/tiles/*` to `titiler`, and serves the React SPA. | ✅ | 2026-06-09 |
| TASK-004 | Record the identified infrastructure gap: `infra/docker/docker-compose.yml` is suitable for local development and portability, but a dedicated production-like Linux server deployment kit under `infra/server/` is missing. | ✅ | 2026-06-09 |
| TASK-005 | Do not modify Railway service topology as part of this plan. Railway must continue using separate Railway services, not a single Compose appliance. | | |

### Implementation Phase 2 — Create the Self-Hosted Deployment Kit

- GOAL-002: Add a dedicated server deployment package that can be used on Azure VM, VPS, and physical Linux servers.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | Create directory `infra/server/` for self-hosted Linux deployment artifacts. | | |
| TASK-007 | Create `infra/server/docker-compose.prod.yml` with production-like services `web`, `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and optional `ingestion-sar`. Use private Docker networking and publish only `web` ports `80` and `443` or only `80` for first rehearsal if TLS is deferred. | | |
| TASK-008 | In `infra/server/docker-compose.prod.yml`, configure `postgis` with bind mount `/srv/akasha/data/postgis:/var/lib/postgresql/data`. | | |
| TASK-009 | In `infra/server/docker-compose.prod.yml`, configure `minio` with bind mount `/srv/akasha/data/minio:/data`. | | |
| TASK-010 | In `infra/server/docker-compose.prod.yml`, configure `api` environment values with `DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgis:5432/${POSTGRES_DB}`, `STAC_API_URL=http://stac-api:8080`, `TITILER_URL=http://titiler:8000`, and `S3_ENDPOINT_URL=http://minio:9000`. | | |
| TASK-011 | In `infra/server/docker-compose.prod.yml`, configure `web` environment values with `API_UPSTREAM_URL=http://api:8000` and `TITILER_UPSTREAM_URL=http://titiler:8000`. | | |
| TASK-012 | In `infra/server/docker-compose.prod.yml`, configure TiTiler and API GDAL/S3 variables: `AWS_S3_ENDPOINT=minio:9000`, `AWS_VIRTUAL_HOSTING=FALSE`, `AWS_HTTPS=NO`, `AWS_REGION=us-east-1`, `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, and `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff`. | | |
| TASK-013 | Create `infra/server/.env.example` containing non-secret defaults and placeholder values for all required server variables. Include placeholders for `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `AUTH_PASSWORD_PEPPER`, `AUTH_BOOTSTRAP_TOKEN`, `CORS_ALLOWED_ORIGINS`, `PUBLIC_APP_NAME`, and `PUBLIC_DEFAULT_AOI_NAME`. | | |
| TASK-014 | Create `infra/server/systemd/akasha.service` that runs Docker Compose from `/srv/akasha/current` with `docker compose -f infra/server/docker-compose.prod.yml --env-file /srv/akasha/env/akasha.env up -d` on start and `docker compose -f infra/server/docker-compose.prod.yml --env-file /srv/akasha/env/akasha.env down` on stop. | | |
| TASK-015 | Create `infra/server/scripts/install-docker.sh` for Ubuntu LTS that installs Docker Engine and the Docker Compose plugin using the official Docker repository. | | |
| TASK-016 | Create `infra/server/scripts/prepare-host.sh` that creates Linux user `akasha`, creates `/srv/akasha/current`, `/srv/akasha/env`, `/srv/akasha/data/postgis`, `/srv/akasha/data/minio`, `/srv/akasha/backups/postgis`, `/srv/akasha/backups/minio`, and sets ownership to `akasha:akasha`. | | |
| TASK-017 | Create `infra/server/scripts/deploy.sh` that pulls the repository or updates `/srv/akasha/current`, validates `/srv/akasha/env/akasha.env`, starts the systemd service, and prints service status. | | |
| TASK-018 | Create `infra/server/README.md` with exact Azure VM, VPS, and physical server setup instructions, including prerequisites, environment file creation, deployment, health checks, backup, restore, and rollback. | | |

### Implementation Phase 3 — Azure VM Provisioning Rehearsal

- GOAL-003: Provision an Azure Linux VM that behaves like a future single physical server or VPS deployment target.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Provision an Azure VM using Ubuntu 22.04 LTS or Ubuntu 24.04 LTS. Use at least 4 vCPU, 16 GB RAM, 64 GB OS disk, and a separate data disk of at least 500 GB for raster and database rehearsal. | | |
| TASK-020 | Configure Azure Network Security Group inbound rules to allow TCP `22`, `80`, and `443` only. Restrict TCP `22` to operator IP addresses when possible. | | |
| TASK-021 | Disable SSH password authentication on the VM by setting `PasswordAuthentication no` in the SSH daemon configuration and reloading SSH. | | |
| TASK-022 | Mount the Azure data disk at `/srv/akasha/data` using `/etc/fstab` with a stable disk UUID. | | |
| TASK-023 | Install Docker Engine and Docker Compose plugin by running `infra/server/scripts/install-docker.sh`. | | |
| TASK-024 | Prepare host directories and user permissions by running `infra/server/scripts/prepare-host.sh`. | | |
| TASK-025 | Copy or clone the repository into `/srv/akasha/current`. Checkout the intended branch, initially `dev-akasha-core` unless a release branch is created. | | |
| TASK-026 | Create `/srv/akasha/env/akasha.env` from `infra/server/.env.example` and replace every placeholder with a non-default value. | | |
| TASK-027 | Start the stack through systemd using `akasha.service`. | | |
| TASK-028 | Verify `docker compose ps` shows healthy or running status for `web`, `api`, `titiler`, `stac-api`, `postgis`, and `minio`. | | |
| TASK-029 | Verify the host reboot path by rebooting the VM and confirming `akasha.service` restarts the stack without manual intervention. | | |

### Implementation Phase 4 — Data Initialization and Catalog Verification

- GOAL-004: Prove that the self-hosted server can initialize the database, object storage, and STAC catalog using the existing Akasha ingestion flow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-030 | Run the API Alembic ORM baseline inside the `api` container using `python -m app.cli db upgrade`. | | |
| TASK-031 | Run API infrastructure check inside the `api` container using `python -m app.cli check`. | | |
| TASK-032 | Run ingestion seed command using the `ingestion-worker` service: `python worker.py seed`. | | |
| TASK-033 | Run ingestion verification using the `ingestion-worker` service: `python worker.py verify`. | | |
| TASK-034 | If real COGs are available, run `python worker.py verify-cogs` or the current manifest verification command used by the ingestion service. | | |
| TASK-035 | Confirm MinIO bucket `akasha-cogs` exists and contains expected `analytic.tif` and `scl.tif` objects for the seeded scene or prepared manifest scenes. | | |
| TASK-036 | Confirm STAC API health endpoint is reachable from within the Docker network and the catalog contains expected collection and item records. | | |

### Implementation Phase 5 — Public Gateway, TLS, and Auth Hardening

- GOAL-005: Expose only the gateway service and harden application access for production-like review.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-037 | Point a rehearsal DNS name to the Azure VM public IP if a domain is available. If no domain is available, complete HTTP-only rehearsal first and record TLS as deferred. | | |
| TASK-038 | Configure Caddy/TLS in `infra/server/docker-compose.prod.yml` and server-specific Caddy configuration only if a domain is available. Preserve `/health`, `/api/*`, `/tiles/*`, and SPA fallback behavior. | | |
| TASK-039 | Set `AUTH_MODE=enabled`, `AUTH_ALLOW_DISABLED=false`, `AUTH_COOKIE_SECURE=true`, and exact `CORS_ALLOWED_ORIGINS=https://<self-hosted-domain>` for TLS-enabled rehearsal. | | |
| TASK-040 | Set `AUTH_ALLOW_BOOTSTRAP=false` after first-run account bootstrap is complete. If bootstrap is needed, require `AUTH_ALLOW_BOOTSTRAP=true` and `AUTH_BOOTSTRAP_TOKEN=<one-time-secret>` only during the controlled setup window. | | |
| TASK-041 | Confirm public scans or manual checks cannot access PostGIS, MinIO, STAC API, FastAPI, or TiTiler directly from the internet. | | |
| TASK-042 | If `GATEWAY_BASIC_AUTH` is enabled for demos, document it as an outer shared-secret gate only and confirm application auth remains enabled. | | |

### Implementation Phase 6 — Backup and Restore Implementation

- GOAL-006: Make data recovery testable before treating the Azure VM rehearsal as production-like.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-043 | Create `infra/server/scripts/backup-postgis.sh` that writes timestamped compressed logical backups to `/srv/akasha/backups/postgis`. Use `pg_dump` from the `postgis` container or an equivalent PostgreSQL client container. | | |
| TASK-044 | Create `infra/server/scripts/restore-postgis.sh` that restores a selected backup into a clean or explicitly confirmed target database. Require an explicit backup path argument. | | |
| TASK-045 | Create `infra/server/scripts/backup-minio.sh` that copies MinIO bucket contents to `/srv/akasha/backups/minio/<timestamp>` or to an operator-specified external S3-compatible backup target. | | |
| TASK-046 | Create `infra/server/scripts/restore-minio.sh` that restores a selected MinIO backup into the `akasha-cogs` bucket. Require an explicit backup path argument. | | |
| TASK-047 | Create `infra/server/scripts/backup-all.sh` that runs PostGIS and MinIO backups and writes a manifest file containing timestamps, source service versions, backup paths, and checksums where practical. | | |
| TASK-048 | Create `infra/server/scripts/restore-all.sh` that restores PostGIS and MinIO from a selected backup manifest into a fresh VM or reset data directory. | | |
| TASK-049 | Test backup scripts on the Azure VM and confirm backup files exist outside the Docker containers under `/srv/akasha/backups`. | | |
| TASK-050 | Provision a second clean Azure VM or wipe the first VM data directories after backup export, then run restore and confirm the smoke test passes. | | |

### Implementation Phase 7 — Smoke Testing and Operational Validation

- GOAL-007: Validate that the self-hosted deployment behaves like the Railway deployment from the browser and API contract perspective.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-051 | Create `infra/server/scripts/smoke-test.sh` that accepts a base URL and runs the same ordered checks documented in `docs/railway-deployment-guide.md`. | | |
| TASK-052 | Run `GET /health` against the public `web` endpoint and require HTTP `200`. | | |
| TASK-053 | Run `GET /api/config` and require valid JSON without leaked secrets or internal credentials. | | |
| TASK-054 | Run `GET /api/sources` and require the configured source list to include `sentinel-2-l2a`. | | |
| TASK-055 | Run `GET /api/sources/{id}/dates` for `sentinel-2-l2a` and require valid JSON. | | |
| TASK-056 | Run `GET /api/layers/default` and require a true-colour default layer contract. | | |
| TASK-057 | Request one RGB tile URL through the public gateway and require `200 image/png` when seeded raster data is available. | | |
| TASK-058 | Run one `/api/indices/statistics` request against a known sample polygon and require valid NDVI statistics JSON when seeded raster data is available. | | |
| TASK-059 | Restart the `api`, `titiler`, `stac-api`, `postgis`, and `minio` containers individually and rerun the smoke test after each restart. | | |
| TASK-060 | Reboot the VM and rerun the smoke test after systemd restarts the stack. | | |

### Implementation Phase 8 — CI Image Build and Release Discipline

- GOAL-008: Move from server-side builds to repeatable tagged images after the Azure VM proof succeeds.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-061 | Add or update CI workflow to build `web`, `api`, `ingestion-worker`, and `ingestion-sar` images from repository Dockerfiles. | | |
| TASK-062 | Push images to a registry such as GitHub Container Registry using immutable tags based on git SHA and optional release tags. | | |
| TASK-063 | Update `infra/server/docker-compose.prod.yml` to support pulling tagged images through environment variables such as `AKASHA_WEB_IMAGE`, `AKASHA_API_IMAGE`, and `AKASHA_INGESTION_IMAGE`. | | |
| TASK-064 | Keep local build mode available for emergency or development use, but document registry-pull mode as the preferred server deployment mode. | | |
| TASK-065 | Add rollback instructions to `infra/server/README.md` that pin the previous known-good image tags and restart `akasha.service`. | | |

### Implementation Phase 9 — Stakeholder Review and Physical Server Readiness

- GOAL-009: Package the Azure VM rehearsal results into a reviewable handoff for stakeholders before repeating the process on VPS or physical Linux hardware.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-066 | Create `docs/self-hosted-linux-deployment-review.md` after the Azure VM rehearsal completes. Include VM size, OS version, disk layout, deployed git SHA, image tags, environment profile summary, public URL, smoke-test results, backup results, restore results, and known gaps. | | |
| TASK-067 | Record infrastructure sign-off: only `web` is public; private services are not externally reachable. | | |
| TASK-068 | Record security sign-off: SSH password login disabled, auth enabled, exact CORS origin configured, no default credentials, and no secrets committed. | | |
| TASK-069 | Record persistence sign-off: PostGIS and MinIO use `/srv/akasha/data` bind mounts on a persistent disk. | | |
| TASK-070 | Record backup/restore sign-off: restore into a clean VM completed and smoke test passed after restore. | | |
| TASK-071 | Record operations sign-off: reboot recovery, container restart recovery, log inspection, and rollback process were verified. | | |
| TASK-072 | Approve physical server/VPS replication only after TASK-067 through TASK-071 are complete. | | |

## 3. Alternatives

- **ALT-001**: Continue using Railway only. This remains valid for the MVP but does not prove portability to customer-owned Linux servers, physical servers, or VPS environments.
- **ALT-002**: Manually configure an Azure VM and document the commands afterward. This was rejected because it creates an unreproducible snowflake server and weakens disaster recovery.
- **ALT-003**: Deploy directly to a physical server first. This was rejected because Azure VM rehearsal provides faster reset, snapshot, and rebuild cycles before touching customer or owned hardware.
- **ALT-004**: Use Kubernetes for the self-hosted target immediately. This was rejected for the first self-hosted milestone because the required topology is a single-host multi-container application and Docker Compose is simpler to operate and review.
- **ALT-005**: Install PostGIS, MinIO, TiTiler, and FastAPI directly on the host without containers. This was rejected because it increases host drift and makes replication to VPS or physical servers harder.
- **ALT-006**: Publish API, STAC, MinIO, or TiTiler directly for convenience. This was rejected because it violates the one-public-service rule and increases the security surface.
- **ALT-007**: Use anonymous Docker volumes only for stateful services. This was rejected because explicit bind mounts under `/srv/akasha/data` are easier to inspect, back up, restore, and migrate to physical storage.
- **ALT-008**: Treat Azure VM as the long-term production target immediately. This was rejected because the VM is first a rehearsal environment; production readiness requires backup/restore and operational sign-off.

## 4. Dependencies

- **DEP-001**: Existing Railway deployment guide at `docs/railway-deployment-guide.md` for the authoritative service topology and environment variable matrix.
- **DEP-002**: Existing local Docker Compose topology at `infra/docker/docker-compose.yml` for service boundary reference.
- **DEP-003**: Existing Caddy gateway configuration at `infra/gateway/Caddyfile` for same-origin public routing.
- **DEP-004**: Existing gateway image build at `infra/gateway/Dockerfile` for React SPA plus Caddy packaging.
- **DEP-005**: Existing FastAPI Dockerfile at `apps/api/Dockerfile`.
- **DEP-006**: Existing ingestion Dockerfile at `services/ingestion/Dockerfile`.
- **DEP-007**: Existing ingestion SAR Dockerfile at `services/ingestion-sar/Dockerfile` if SAR processing is included in the self-hosted profile.
- **DEP-008**: TiTiler image `ghcr.io/developmentseed/titiler:1.0.0` or the pinned custom service image defined by `services/titiler/Dockerfile`.
- **DEP-009**: STAC API image `ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2` or the pinned custom service image defined by `services/stac-api/Dockerfile`.
- **DEP-010**: PostGIS image `postgis/postgis:16-3.5`.
- **DEP-011**: MinIO image pinned in the deployment Compose file.
- **DEP-012**: Ubuntu 22.04 LTS or Ubuntu 24.04 LTS for Azure VM rehearsal.
- **DEP-013**: Azure VM, Azure Network Security Group, Azure managed disk, and optional DNS record.
- **DEP-014**: Docker Engine and Docker Compose plugin on the Linux host.
- **DEP-015**: Operator-provided secrets for PostGIS, MinIO, authentication, bootstrap, and optional gateway basic auth.
- **DEP-016**: Seed raster/STAC data or prepared Sentinel COGs for full smoke-test coverage.

## 5. Files

- **FILE-001**: `docs/impl-plan/infrastructure-self-hosted-linux-deployment-1.md` — This implementation plan.
- **FILE-002**: `infra/server/docker-compose.prod.yml` — Production-like self-hosted Docker Compose topology for Azure VM, VPS, and physical Linux server.
- **FILE-003**: `infra/server/.env.example` — Self-hosted environment variable template with placeholders and safe defaults.
- **FILE-004**: `infra/server/README.md` — Operator runbook for provisioning, deployment, validation, backup, restore, and rollback.
- **FILE-005**: `infra/server/systemd/akasha.service` — systemd unit for starting and stopping the Compose stack.
- **FILE-006**: `infra/server/scripts/install-docker.sh` — Ubuntu LTS Docker installation script.
- **FILE-007**: `infra/server/scripts/prepare-host.sh` — Host user, directory, and permission setup script.
- **FILE-008**: `infra/server/scripts/deploy.sh` — Self-hosted deployment script.
- **FILE-009**: `infra/server/scripts/backup-postgis.sh` — PostGIS logical backup script.
- **FILE-010**: `infra/server/scripts/restore-postgis.sh` — PostGIS restore script.
- **FILE-011**: `infra/server/scripts/backup-minio.sh` — MinIO object backup script.
- **FILE-012**: `infra/server/scripts/restore-minio.sh` — MinIO object restore script.
- **FILE-013**: `infra/server/scripts/backup-all.sh` — Combined backup script and backup manifest writer.
- **FILE-014**: `infra/server/scripts/restore-all.sh` — Combined restore script from a backup manifest.
- **FILE-015**: `infra/server/scripts/smoke-test.sh` — Public URL smoke test script for self-hosted deployments.
- **FILE-016**: `docs/self-hosted-linux-deployment-review.md` — Stakeholder review report created after Azure VM rehearsal completes.
- **FILE-017**: `docs/railway-deployment-guide.md` — May be updated with a cross-link to this self-hosted plan after initial review.
- **FILE-018**: `.github/workflows/*` — Optional future CI image build workflow for registry-pushed tagged images.

## 6. Testing

- **TEST-001**: Markdown validation: confirm `docs/impl-plan/infrastructure-self-hosted-linux-deployment-1.md` exists and contains exactly one top-level introduction heading.
- **TEST-002**: Compose validation: run `docker compose -f infra/server/docker-compose.prod.yml --env-file <test-env> config` and require success.
- **TEST-003**: Public port validation: confirm only `web` publishes host ports in `infra/server/docker-compose.prod.yml`.
- **TEST-004**: Private service validation: confirm `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and `ingestion-sar` do not publish public host ports.
- **TEST-005**: Data persistence validation: create data in PostGIS and MinIO, restart containers, and confirm data remains.
- **TEST-006**: Reboot validation: reboot the Azure VM and confirm `akasha.service` starts the stack automatically.
- **TEST-007**: API migration validation: run `python -m app.cli db upgrade` inside the `api` container and require success.
- **TEST-008**: API infrastructure validation: run `python -m app.cli check` inside the `api` container and require success.
- **TEST-009**: Ingestion seed validation: run `python worker.py seed` inside the `ingestion-worker` container and require success.
- **TEST-010**: Ingestion verification validation: run `python worker.py verify` inside the `ingestion-worker` container and require success.
- **TEST-011**: Web health validation: call `GET /health` through the public gateway and require HTTP `200`.
- **TEST-012**: API config validation: call `GET /api/config` through the public gateway and require valid JSON without secrets.
- **TEST-013**: Source list validation: call `GET /api/sources` and require `sentinel-2-l2a` to be present.
- **TEST-014**: Date list validation: call `GET /api/sources/sentinel-2-l2a/dates` and require valid JSON.
- **TEST-015**: Default layer validation: call `GET /api/layers/default` and require the default true-colour imagery layer contract.
- **TEST-016**: Tile validation: request one RGB tile through the public gateway and require `200 image/png` when raster data is seeded.
- **TEST-017**: Statistics validation: request `/api/indices/statistics` with a known sample polygon and require valid NDVI statistics JSON when raster data is seeded.
- **TEST-018**: Backup validation: run PostGIS and MinIO backups and confirm backup artifacts exist under `/srv/akasha/backups`.
- **TEST-019**: Restore validation: restore backups into a clean VM or reset data directory and require smoke tests to pass afterward.
- **TEST-020**: Security validation: scan or manually test public IP and confirm PostGIS, MinIO, STAC API, FastAPI, and TiTiler are not publicly reachable.
- **TEST-021**: Auth validation: confirm production-like environment rejects disabled auth unless explicitly configured for local/dev/test.
- **TEST-022**: Rollback validation: deploy a previous known-good image tag or git revision and confirm the stack returns to healthy state.

## 7. Risks & Assumptions

- **RISK-001**: Azure VM sizing may be insufficient for raster statistics or Sentinel COG preparation. Mitigation: start with at least 4 vCPU and 16 GB RAM, then scale to 8 vCPU and 32 GB RAM if TiTiler/API workloads are slow.
- **RISK-002**: Raster data can consume disk quickly. Mitigation: mount a separate data disk at `/srv/akasha/data`, monitor disk usage, and test cleanup/retention procedures.
- **RISK-003**: MinIO on a single VM is operationally simple but not highly available. Mitigation: accept for rehearsal and small self-hosted deployments; revisit external S3-compatible storage for larger production datasets.
- **RISK-004**: PostGIS backups may be inconsistent if taken during heavy writes. Mitigation: use PostgreSQL-native logical backups and document maintenance windows for large restore operations.
- **RISK-005**: Server-side builds can be slow or fail due to low VM resources. Mitigation: move to CI-built tagged images after the first rehearsal succeeds.
- **RISK-006**: Manual Azure VM changes can create drift from the future physical server process. Mitigation: convert every manual change into `infra/server` scripts or README steps before sign-off.
- **RISK-007**: TLS setup requires a real domain name. Mitigation: complete HTTP-only functional rehearsal first, then perform TLS hardening once DNS is available.
- **RISK-008**: Secrets stored only in a local `.env` file can be lost. Mitigation: require secure external secret backup outside git.
- **RISK-009**: Restore may not work if backups are never tested. Mitigation: make restore into a clean VM a mandatory acceptance gate.
- **RISK-010**: Publishing non-gateway services by mistake would violate the security model. Mitigation: automated Compose validation must confirm only `web` publishes host ports.
- **ASSUMPTION-001**: Railway continues to host the MVP while the Azure VM rehearsal is built and tested.
- **ASSUMPTION-002**: The first self-hosted deployment target is a single Linux host, not a multi-node cluster.
- **ASSUMPTION-003**: Docker Compose is acceptable for initial VPS and physical server deployments.
- **ASSUMPTION-004**: Operators can provide Azure VM access, DNS if TLS is required, and secure secrets outside git.
- **ASSUMPTION-005**: Seed data or prepared Sentinel COGs are available for full tile/statistics smoke testing.
- **ASSUMPTION-006**: Physical server replication will use the same `/srv/akasha` directory structure and Docker Compose deployment kit.

## 8. Related Specifications / Further Reading

- `docs/railway-deployment-guide.md`
- `docs/architecture-tech-stack.md`
- `docs/platform-plan.md`
- `docs/engineering-dos-donts.md`
- `docs/data-ingestion-and-satellite-rules.md`
- `docs/sentinel-2-l2a-cog-prep-runbook.md`
- `docs/sentinel-1-grd-cog-prep-runbook.md`
- `infra/docker/docker-compose.yml`
- `infra/gateway/Caddyfile`
- `infra/gateway/Dockerfile`
- `apps/api/Dockerfile`
- `services/ingestion/Dockerfile`
- `services/ingestion-sar/Dockerfile`
- Azure Linux Virtual Machines documentation: `https://learn.microsoft.com/azure/virtual-machines/linux/`
- Docker Engine installation on Ubuntu: `https://docs.docker.com/engine/install/ubuntu/`
- Docker Compose documentation: `https://docs.docker.com/compose/`
- Caddy documentation: `https://caddyserver.com/docs/`
- PostgreSQL backup documentation: `https://www.postgresql.org/docs/current/backup.html`
- MinIO documentation: `https://min.io/docs/minio/linux/index.html`
