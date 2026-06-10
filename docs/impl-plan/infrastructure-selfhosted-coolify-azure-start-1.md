---
goal: Azure rehearsal startup plan for Akasha self-hosted Coolify deployment
version: 1.0
date_created: 2026-06-10
last_updated: 2026-06-10
owner: Akasha deployment operator
tags:
  - infrastructure
  - self-hosted
  - coolify
  - azure
  - deployment
---

# Introduction

This implementation plan defines the initial, executable steps for starting the Akasha self-hosted Coolify deployment rehearsal on Azure virtual machines.

Azure is used only as commodity infrastructure for Linux VMs, disks, static public IPs, firewall rules, and DNS/IP plumbing. The target architecture remains portable to university servers, physical servers, virtualized servers, VPS providers, and local/on-prem Linux hosts.

This plan starts with the control plane and staging environment. Production is provisioned only after the control plane and staging deployment path are validated.

## 1. Requirements & Constraints

- **REQ-001**: Use a three-VM target architecture with `akasha-control`, `akasha-staging`, and `akasha-production`.
- **REQ-002**: Use Ubuntu 24.04 LTS for all Azure rehearsal VMs.
- **REQ-003**: Use Coolify only on `akasha-control`.
- **REQ-004**: Use a GitHub self-hosted runner only on `akasha-control`.
- **REQ-005**: Use Docker Compose as the Akasha runtime source of truth.
- **REQ-006**: Preserve Akasha's multi-service topology; do not collapse services into one container.
- **REQ-007**: Preserve the one-public-service rule: only `web` is public.
- **REQ-008**: Browser traffic must use same-origin paths: `/api/*` and `/tiles/*` through `web`.
- **REQ-009**: Staging and production must pull prebuilt images from a registry during normal deploys.
- **REQ-010**: Production must not build release images during normal deploys.
- **REQ-011**: Use Git SHA image tags for built Akasha images.
- **REQ-012**: Build only these repository images: `web`, `api`, `ingestion-worker`, and `ingestion-sar`.
- **REQ-013**: Use pinned upstream images for `titiler`, `stac-api`, `postgis`, and `minio`.
- **SEC-001**: Disable password-based SSH login on all VMs.
- **SEC-002**: Disable root SSH login after bootstrap if operationally possible.
- **SEC-003**: Restrict `22/tcp` on all VMs to admin IPs and required control-plane access.
- **SEC-004**: Restrict `443/tcp` for the Coolify UI to admin IPs or VPN.
- **SEC-005**: Do not expose Postgres `5432`, MinIO `9000` or `9001`, STAC API `8080`, FastAPI `8000`, or TiTiler `8000` publicly.
- **SEC-006**: Do not store production secrets in repository files.
- **SEC-007**: Do not run untrusted fork pull request code on the `akasha-control` self-hosted runner.
- **CON-001**: Do not use Azure App Service.
- **CON-002**: Do not use Azure Database.
- **CON-003**: Do not use Azure Blob Storage.
- **CON-004**: Do not use Azure Container Registry unless explicitly approved later.
- **CON-005**: Do not use Azure DevOps.
- **CON-006**: Do not use Azure Key Vault for this initial path.
- **CON-007**: Do not install Docker through Snap.
- **CON-008**: Do not assign public Coolify domains to private Akasha services.
- **GUD-001**: Start with `akasha-control`, then `akasha-staging`, then `akasha-production`.
- **GUD-002**: Use Azure Dsv5 VM sizes by default for stable CPU performance.
- **GUD-003**: Use Bsv2 only as a cost-saving option for `akasha-control`, not for production raster workloads.
- **PAT-001**: Mount staging and production persistent data at `/srv/akasha`.
- **PAT-002**: Mount control-plane build/Coolify data at `/data` or Docker's configured data path.
- **PAT-003**: Keep repository deployment files under `infra/selfhosted/`.
- **PAT-004**: Keep implementation plans under `docs/impl-plan/`.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Prepare Azure account-level prerequisites and avoid creating incompatible managed services.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create an Azure resource group named `rg-akasha-selfhosted` in the selected Azure region. | Yes — created in `centralindia`. | 2026-06-10 |
| TASK-002 | Confirm the Azure subscription has at least `16` available Dsv5-family vCPUs in the selected region. Required final capacity is `4` vCPU for `akasha-control`, `4` vCPU for `akasha-staging`, and `8` vCPU for `akasha-production`. | No — Central India `Standard DSv5 Family vCPUs` quota is `0`; Dsv5 quota increase required. | 2026-06-10 |
| TASK-003 | If the subscription quota is below `16` Dsv5-family vCPUs, request quota increase before provisioning production. Continue only with `akasha-control` and `akasha-staging` if at least `8` Dsv5-family vCPUs are available. | Pending — `akasha-control` deployed with approved `Standard_D4s_v4` fallback; request quota before Dsv5 staging/production. | 2026-06-10 |
| TASK-004 | Create or select an SSH public key for VM access. Store the private key outside the repository. | Yes — selected `~/.ssh/id_ed25519_thaarei.pub`. | 2026-06-10 |
| TASK-005 | Record the operator's current public admin IP address for SSH and Coolify allowlisting. | Yes — initial IP was `49.206.113.102/32`; SSH/HTTPS were later temporarily opened to any IP by operator request and must be restricted again. | 2026-06-10 |
| TASK-006 | Confirm the default container registry is GitHub Container Registry (`ghcr.io`) for the initial implementation. | Pending — GHCR remains the planned default, but registry credentials have not been configured in Coolify yet. | 2026-06-10 |
| TASK-007 | Do not create Azure App Service, Azure Database, Azure Blob Storage, Azure Container Registry, Azure DevOps, or Azure Key Vault resources for this deployment path. | Yes — only Azure VM/network/disk/resource-group primitives created so far. | 2026-06-10 |

### Implementation Phase 2

- GOAL-002: Provision the `akasha-control` VM for Coolify, image builds, and GitHub Actions runner execution.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Create Azure VM `akasha-control` using Ubuntu 24.04 LTS. Use `Standard_D4s_v5` with `4` vCPU and `16` GiB RAM. Cost-saving alternative for rehearsal only is `Standard_B4s_v2`. | Yes — deployed Ubuntu 24.04 LTS as `Standard_D4s_v4` fallback because Dsv5/Bsv2 quota is `0`. | 2026-06-10 |
| TASK-009 | Attach SSD-backed storage so `akasha-control` has at least `256` GB total usable disk capacity. | Yes — attached `256` GiB Premium SSD `datadisk-akasha-control-001`; visible as `/dev/sdb`. | 2026-06-10 |
| TASK-010 | Assign a static public IP address to `akasha-control`. | Yes — `20.204.163.166`. | 2026-06-10 |
| TASK-011 | Configure Azure network security group rules for `akasha-control`: allow `22/tcp` only from the admin IP; allow `443/tcp` only from the admin IP or VPN; allow outbound `443/tcp` to GitHub, GHCR, package registries, staging, and production. | Partially — setup ports `22/tcp`, `80/tcp`, `443/tcp`, `8000/tcp`, `6001/tcp`, and `6002/tcp` are now restricted to current admin IP `49.206.113.102/32`; add team/VPN CIDRs later and revisit which public proxy ports remain open. | 2026-06-10 |
| TASK-012 | Log in to `akasha-control` using the configured SSH key. | Yes — SSH verified as `akashaadmin@20.204.163.166`. | 2026-06-10 |
| TASK-013 | Update system packages on `akasha-control`. | Yes — apt metadata refreshed and packages upgraded; reboot completed; no reboot currently required. | 2026-06-10 |
| TASK-014 | Create the persistent data mount for Coolify and build artifacts at `/data`, or configure Docker to use an equivalent persistent data path. | Yes — `/dev/sdb` formatted as ext4, mounted at `/data`, and directories `/data/docker`, `/data/coolify`, `/data/builds`, and `/data/logs` created. Docker data-root is `/data/docker`. | 2026-06-10 |
| TASK-015 | Configure `/etc/fstab` so the control-plane disk mount survives reboot. | Yes — `/data` added to `/etc/fstab` by disk UUID with `nofail`. | 2026-06-10 |
| TASK-016 | Reboot `akasha-control` once and verify the persistent data mount is active after reboot. | Yes — rebooted successfully; `/data` remounted from `/dev/sdb` after reboot. | 2026-06-10 |
| TASK-017 | Disable password SSH login on `akasha-control`. | Yes — SSH hardening drop-in sets `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, and `ChallengeResponseAuthentication no`. | 2026-06-10 |
| TASK-018 | Disable root SSH login on `akasha-control` after bootstrap if operationally possible. | Partially — root password login remains disabled, but root public-key SSH is enabled as `PermitRootLogin prohibit-password` for standard Coolify localhost management. Reassess after Coolify server validation. | 2026-06-10 |
| TASK-019 | Enable a host firewall on `akasha-control` with the same inbound policy as the Azure network security group. | Partially — UFW enabled with default deny incoming/default allow outgoing; setup ports `22/tcp`, `80/tcp`, `443/tcp`, `8000/tcp`, `6001/tcp`, and `6002/tcp` are restricted to current admin IP `49.206.113.102`. Add team/VPN CIDRs later. | 2026-06-10 |
| TASK-020 | Install and enable `fail2ban` on `akasha-control`. | Yes — `fail2ban` installed, enabled, active, and `sshd` jail verified. | 2026-06-10 |
| TASK-021 | Enable unattended security updates on `akasha-control`. | Yes — `unattended-upgrades` installed, enabled, and active. | 2026-06-10 |
| TASK-022 | Install Docker from the official Docker packages on `akasha-control`. Do not install Docker from Snap. | Yes — Docker Engine `29.5.3` and Docker Compose plugin `v5.1.4` installed from Docker's official apt repo; Snap Docker absent; hello-world smoke test passed. | 2026-06-10 |

### Implementation Phase 3

- GOAL-003: Install and secure Coolify on `akasha-control`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | Install Coolify on `akasha-control` using the official Coolify self-hosted installer for Ubuntu LTS. | Yes — installed Coolify `4.1.2` using the official quick installer; containers are healthy. | 2026-06-10 |
| TASK-024 | Open the displayed Coolify URL immediately after installation. | Yes — opened `http://20.204.163.166:8000`, completed onboarding, and reached the Coolify dashboard/project flow. | 2026-06-10 |
| TASK-025 | Create the first Coolify admin account immediately after opening the registration page. | Yes — first Coolify admin account created by operator; unauthenticated registration is now disabled and public access redirects to login. | 2026-06-10 |
| TASK-026 | Configure the Coolify access domain if DNS is already available. Use `control.<final-domain>` when final DNS is known; otherwise use the Azure public IP temporarily. | Yes for initial rehearsal — using Azure public IP `20.204.163.166` temporarily; final DNS not configured yet. | 2026-06-10 |
| TASK-027 | Restrict Coolify UI access using Azure network security group rules, host firewall rules, VPN, or trusted IP allowlisting. | Yes for current operator — Azure NSG and UFW now restrict `22/tcp`, `80/tcp`, `443/tcp`, `8000/tcp`, `6001/tcp`, and `6002/tcp` to current admin IP `49.206.113.102/32`; add team/VPN CIDRs later. | 2026-06-10 |
| TASK-028 | Add GHCR or approved registry credentials to Coolify. | Blocked on operator secret input — requires a GitHub/GHCR token or GitHub App credentials entered directly into Coolify; do not paste credentials into chat. | 2026-06-10 |
| TASK-029 | Verify Coolify can access Docker on `akasha-control`. | Yes for localhost control plane — Coolify containers are healthy, Docker data-root is `/data/docker`, Traefik `/ping` returns `OK`, and Coolify's generated root SSH key can inspect Docker. UI currently shows a stale `Proxy Exited` badge despite healthy container state. | 2026-06-10 |
| TASK-030 | Configure notification channels in Coolify if available. | Deferred — no notification provider/channel selected yet; configure after choosing email, Slack, Discord, or another approved target. | 2026-06-10 |

Phase 3 operational notes:

- Coolify environment file was backed up without printing secrets:
  - VM root-only backup: `/data/coolify/manual-backups/coolify-env-20260610-171450.env`
  - Local operator backup outside repository: `~/.akasha-secrets/coolify-env-akasha-control-20260610-171450.env`
- Coolify proxy validation from the host passed with `docker inspect` healthy status and `http://localhost:80/ping` returning `OK`.
- The Coolify UI still shows a stale `Proxy Exited` badge on the server header even though the `coolify-proxy` container is running and healthy; re-check after future Coolify refresh/update before deploying workloads.

### Implementation Phase 4

- GOAL-004: Provision the `akasha-staging` VM and prepare it as a private Coolify-managed runtime server.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-031 | Create Azure VM `akasha-staging` using Ubuntu 24.04 LTS and `Standard_D4s_v5` with `4` vCPU and `16` GiB RAM. | | |
| TASK-032 | Attach SSD-backed data storage of at least `512` GB to `akasha-staging`. | | |
| TASK-033 | Assign a static public IP address to `akasha-staging`. | | |
| TASK-034 | Configure Azure network security group rules for `akasha-staging`: allow `80/tcp` and `443/tcp`; allow `22/tcp` only from admin IP and `akasha-control`; deny public access to `5432`, `9000`, `9001`, `8080`, and `8000`. | | |
| TASK-035 | Log in to `akasha-staging` using the configured SSH key. | | |
| TASK-036 | Update system packages on `akasha-staging`. | | |
| TASK-037 | Mount the staging data disk at `/srv/akasha`. | | |
| TASK-038 | Configure `/etc/fstab` so `/srv/akasha` survives reboot. | | |
| TASK-039 | Create directories `/srv/akasha/postgis`, `/srv/akasha/minio`, `/srv/akasha/data`, `/srv/akasha/logs`, and `/srv/akasha/backups`. | | |
| TASK-040 | Reboot `akasha-staging` once and verify `/srv/akasha` is mounted after reboot. | | |
| TASK-041 | Disable password SSH login on `akasha-staging`. | | |
| TASK-042 | Disable root SSH login on `akasha-staging` after bootstrap if operationally possible. | | |
| TASK-043 | Enable a host firewall on `akasha-staging` with the same inbound policy as the Azure network security group. | | |
| TASK-044 | Install and enable `fail2ban` on `akasha-staging`. | | |
| TASK-045 | Enable unattended security updates on `akasha-staging`. | | |
| TASK-046 | Install Docker from the official Docker packages on `akasha-staging`. Do not install Docker from Snap. | | |

### Implementation Phase 5

- GOAL-005: Register `akasha-staging` in Coolify and create the Coolify project structure.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-047 | From the Coolify UI on `akasha-control`, add `akasha-staging` as a remote server over SSH. | | |
| TASK-048 | Verify Coolify can connect to `akasha-staging` over SSH. | | |
| TASK-049 | Verify Coolify can control Docker on `akasha-staging`. | | |
| TASK-050 | Create Coolify project `akasha`. | | |
| TASK-051 | Create Coolify environment `staging` under project `akasha`. | | |
| TASK-052 | Create a placeholder Docker Compose resource named `akasha-staging-compose` under the `staging` environment. Do not deploy until `infra/selfhosted/coolify-compose.yml` exists in the repository. | | |
| TASK-053 | Assign a public domain only to the future `web` service. Do not assign public domains to `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, or `ingestion-sar`. | | |

### Implementation Phase 6

- GOAL-006: Configure GitHub self-hosted runner on `akasha-control` for CI/CD image builds and deployment triggers.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-054 | Create a dedicated Linux user on `akasha-control` for the GitHub Actions runner. | Yes — created `github-runner` on `akasha-control`. | 2026-06-10 |
| TASK-055 | Install the GitHub Actions self-hosted runner under the dedicated runner user. | Yes — installed runner `2.335.1` under `/data/actions-runner/akasha-control` and installed it as a systemd service. | 2026-06-10 |
| TASK-056 | Register the runner to repository `nishanthturnstile/akasha-project` or the owning GitHub organization. | Yes — registered to client repository `Akasha-TechCatalyst/akasha-project`. | 2026-06-10 |
| TASK-057 | Apply runner labels `self-hosted`, `linux`, `x64`, and `akasha-control`. | Yes — runner registered with labels `self-hosted`, `linux`, `x64`, and `akasha-control`. | 2026-06-10 |
| TASK-058 | Grant the runner Docker access required for image builds. | Yes — `github-runner` is a member of the `docker` group and can access Docker with data-root `/data/docker`. | 2026-06-10 |
| TASK-059 | Verify the runner can make outbound HTTPS connections to `github.com`, `api.github.com`, `*.actions.githubusercontent.com`, `ghcr.io`, and GitHub package domains. | Yes — runner connected to GitHub, downloaded actions, built images, and pushed all four Akasha images to GHCR from client workflow run `27290559364`. | 2026-06-10 |
| TASK-060 | Configure GitHub repository or organization policy so untrusted fork pull request code does not run on the self-hosted runner. | | |
| TASK-061 | Run a minimal GitHub Actions workflow on the self-hosted runner to verify job pickup and completion. | Yes — client `Build client images` workflow completed successfully on `akasha-control`; jobs `akasha-api`, `akasha-ingestion-sar`, `akasha-ingestion-worker`, and `akasha-web` all succeeded. | 2026-06-10 |

### Implementation Phase 7

- GOAL-007: Prepare repository deployment artifacts required before the first staging deployment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-062 | Create `infra/selfhosted/coolify-compose.yml` from `infra/docker/docker-compose.yml`, adapted for Coolify-managed self-hosted deployment. | | |
| TASK-063 | Create `infra/selfhosted/env.example` documenting all required staging and production variables without real secrets. | | |
| TASK-064 | Create `infra/selfhosted/README.md` documenting Coolify setup, first deploy, one-shot jobs, and rollback. | | |
| TASK-065 | Create `.github/workflows/ci.yml` with Python lint, API tests, frontend lint/test/build, slice validators, gitleaks, and Trivy checks. | Partially — created base CI with API tests, frontend lint/test/build, and Slice 0/1/2 validators on branch `dev-akasha-core`; gitleaks and Trivy still to add before production readiness. | 2026-06-10 |
| TASK-066 | Create `.github/workflows/deploy-staging.yml` to build `web`, `api`, `ingestion-worker`, and `ingestion-sar`, tag them with the Git SHA, push to GHCR, and trigger Coolify staging deploy with `IMAGE_TAG=<git-sha>`. | | |
| TASK-067 | Create `.github/workflows/deploy-production.yml` to deploy only an already validated image SHA after manual GitHub Environment approval. | | |
| TASK-068 | Extend `scripts/smoke-test.py` with optional `--login` mode that reads credentials from environment variables and reuses the session cookie for authenticated product checks. | | |

Repository ownership and sync notes:

- Client repository created at `Akasha-TechCatalyst/akasha-project` and configured locally as remote `client` via SSH alias `github-akasha`.
- Client `main` is aligned to source `origin/main` at commit `2df880f98bc422cddec0ca8f76eb97ff9aeb1825`; the earlier feature-branch snapshot was corrected.
- Added `.github/workflows/sync-client-main.yml` on source branch `dev-akasha-core`; after PR merge to source `main`, pushes to source `main` will sync to client `main` using secret `CLIENT_REPO_SYNC_SSH_KEY`.
- The sync workflow is guarded to run only in source repository `nishanthturnstile/akasha-project`, so the copied workflow should not recursively run in the client repository.
- Added client-only `.github/workflows/build-client-images.yml`; after sync to `Akasha-TechCatalyst/akasha-project`, client workflow run `27290559364` successfully built and pushed `akasha-api`, `akasha-ingestion-sar`, `akasha-ingestion-worker`, and `akasha-web` to `ghcr.io/akasha-techcatalyst/*` with Git SHA tag `a7f67f47f3b801e5a62dcd053a7d1a54296b144e` and `main` tags.

### Implementation Phase 8

- GOAL-008: Deploy and validate staging before creating production.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-069 | Enter staging environment variables in Coolify. Use environment-specific secrets and do not reuse production secrets. | | |
| TASK-070 | Deploy `akasha-staging-compose` from `infra/selfhosted/coolify-compose.yml`. | | |
| TASK-071 | Verify only the `web` service has a public domain or public route. | | |
| TASK-072 | Run app schema migration inside the `api` container using the repository-supported app migration command. | | |
| TASK-073 | Run catalog/storage seed or verification commands from the `ingestion-worker` container only when required for the staging dataset. | | |
| TASK-074 | Bootstrap the first admin user only if `AUTH_MODE=enabled` and no password users exist. Set `AUTH_ALLOW_BOOTSTRAP=false` after bootstrap. | | |
| TASK-075 | Run unauthenticated smoke checks against `/health`, `/api/health`, and `/api/_skeleton/services`. | | |
| TASK-076 | Run authenticated smoke checks against `/api/config`, `/api/sources`, `/api/sources/sentinel-2-l2a/dates`, `/api/layers/default`, one RGB tile request, and one NDVI statistics request. | | |
| TASK-077 | From outside the host, verify ports `5432`, `9000`, `9001`, `8080`, and `8000` are refused or filtered on the staging public IP. | | |
| TASK-078 | Perform one staging rollback rehearsal by redeploying a previous known-good image tag and rerunning smoke checks. | | |

### Implementation Phase 9

- GOAL-009: Provision production only after staging acceptance criteria pass.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-079 | Confirm staging acceptance criteria are complete before creating `akasha-production`. | | |
| TASK-080 | Create Azure VM `akasha-production` using Ubuntu 24.04 LTS and `Standard_D8s_v5` with `8` vCPU and `32` GiB RAM. | | |
| TASK-081 | Attach SSD-backed data storage of at least `1` TB to `akasha-production`. | | |
| TASK-082 | Assign a static public IP address to `akasha-production`. | | |
| TASK-083 | Configure Azure network security group rules for `akasha-production`: allow `80/tcp` and `443/tcp`; allow `22/tcp` only from admin IP and `akasha-control`; deny public access to `5432`, `9000`, `9001`, `8080`, and `8000`. | | |
| TASK-084 | Prepare `akasha-production` with the same OS hardening, Docker installation, `/srv/akasha` mount, and directory structure used for staging. | | |
| TASK-085 | Add `akasha-production` as a Coolify remote server over SSH. | | |
| TASK-086 | Create Coolify environment `production` under project `akasha`. | | |
| TASK-087 | Create Docker Compose resource `akasha-production-compose` using the same `infra/selfhosted/coolify-compose.yml`. | | |
| TASK-088 | Enter production environment variables in Coolify using production-only secrets. | | |
| TASK-089 | Deploy production only with the exact Git SHA image tag that passed staging. | | |
| TASK-090 | Run production app schema migration, required verification jobs, first admin bootstrap, authenticated smoke checks, private-port checks, and backup validation before production acceptance. | | |

## 3. Alternatives

- **ALT-001**: Use one VM for all services. Rejected because it does not exercise the intended Coolify control-plane separation and increases blast radius between builds, staging runtime, and production runtime.
- **ALT-002**: Use Azure App Service, Azure Database, Azure Blob Storage, or Azure Container Registry. Rejected because the target deployment must remain portable to university servers, physical servers, VPS providers, and on-prem Linux hosts.
- **ALT-003**: Build images directly on staging or production. Rejected because staging and production should pull immutable, tested image tags; production must not build release images during normal deploys.
- **ALT-004**: Expose `api`, `titiler`, `stac-api`, `postgis`, or `minio` directly. Rejected because Akasha requires the one-public-service rule and same-origin frontend contract through `web`.
- **ALT-005**: Start with production first. Rejected because the staging path must validate deployments, migrations, smoke tests, private service isolation, and rollback before production exists.

## 4. Dependencies

- **DEP-001**: Azure subscription with enough Dsv5-family vCPU quota in the selected region.
- **DEP-002**: SSH key pair for VM access.
- **DEP-003**: Admin public IP address or VPN for allowlisting.
- **DEP-004**: Ubuntu 24.04 LTS VM images available in the selected Azure region.
- **DEP-005**: Docker official package repositories reachable from all VMs.
- **DEP-006**: Coolify official self-hosted installer reachable from `akasha-control`.
- **DEP-007**: GitHub repository access for `nishanthturnstile/akasha-project`.
- **DEP-008**: GitHub Container Registry access or an explicitly approved replacement registry.
- **DEP-009**: Outbound HTTPS from `akasha-control` to GitHub, GHCR, package registries, and target VMs.
- **DEP-010**: Final DNS names before production acceptance. Temporary public IP access is acceptable before DNS is configured.
- **DEP-011**: ArcGIS/Esri frontend build key strategy confirmed before release image builds.
- **DEP-012**: University or operator backup policy confirmed before production go-live.

## 5. Files

- **FILE-001**: `docs/self-hosted-coolify-3vm-deployment-plan.md` — Source deployment architecture and constraints for the self-hosted 3-VM plan.
- **FILE-002**: `docs/impl-plan/infrastructure-selfhosted-coolify-azure-start-1.md` — This initial Azure rehearsal implementation plan.
- **FILE-003**: `infra/docker/docker-compose.yml` — Source Compose file to adapt for Coolify-managed deployment.
- **FILE-004**: `infra/selfhosted/coolify-compose.yml` — New self-hosted Coolify Compose file to create before staging deploy.
- **FILE-005**: `infra/selfhosted/env.example` — New environment variable template to create before staging deploy.
- **FILE-006**: `infra/selfhosted/README.md` — New operator runbook to create before staging deploy.
- **FILE-007**: `.github/workflows/ci.yml` — New CI workflow to create before automated deployments.
- **FILE-008**: `.github/workflows/deploy-staging.yml` — New staging deployment workflow to create before automated deployments.
- **FILE-009**: `.github/workflows/deploy-production.yml` — New production deployment workflow to create before production deployment.
- **FILE-010**: `scripts/smoke-test.py` — Existing smoke test script to extend with authenticated `--login` mode.

## 6. Testing

- **TEST-001**: Verify `akasha-control` reboots and keeps the Coolify/build data mount active. **Status**: Passed on 2026-06-10; `/data` remounted from `/dev/sdb` after reboot.
- **TEST-002**: Verify `akasha-staging` reboots and keeps `/srv/akasha` mounted.
- **TEST-003**: Verify `akasha-production` reboots and keeps `/srv/akasha` mounted before production deployment.
- **TEST-004**: Verify SSH login works by key and password login is disabled on all VMs. **Status**: Passed for `akasha-control` on 2026-06-10; SSH key login works for `akashaadmin`, password and root SSH login are disabled.
- **TEST-005**: Verify Docker is installed from official packages and not from Snap on all VMs. **Status**: Passed for `akasha-control` on 2026-06-10; Docker Engine `29.5.3` and Compose plugin `v5.1.4` installed from Docker apt repo, Snap Docker absent, `hello-world` smoke test passed.
- **TEST-006**: Verify Coolify can control Docker on `akasha-staging`.
- **TEST-007**: Verify Coolify can control Docker on `akasha-production` before production deployment.
- **TEST-008**: Verify GitHub self-hosted runner appears online with labels `self-hosted`, `linux`, `x64`, and `akasha-control`.
- **TEST-009**: Verify a minimal GitHub Actions job completes on the self-hosted runner.
- **TEST-010**: Verify GHCR image push succeeds from `akasha-control` runner.
- **TEST-011**: Verify staging deploy reaches healthy state in Coolify.
- **TEST-012**: Verify staging unauthenticated health checks pass for `/health`, `/api/health`, and `/api/_skeleton/services`.
- **TEST-013**: Verify staging authenticated product checks pass after login.
- **TEST-014**: Verify one staging RGB tile request returns a PNG response.
- **TEST-015**: Verify one staging NDVI statistics request returns valid JSON.
- **TEST-016**: Verify private service ports `5432`, `9000`, `9001`, `8080`, and `8000` are not externally reachable on staging.
- **TEST-017**: Verify staging rollback rehearsal succeeds.
- **TEST-018**: Verify production deploy uses the exact image tag previously validated in staging.
- **TEST-019**: Verify production unauthenticated and authenticated smoke checks pass.
- **TEST-020**: Verify private service ports `5432`, `9000`, `9001`, `8080`, and `8000` are not externally reachable on production.

## 7. Risks & Assumptions

- **RISK-001**: Azure subscription quota may be insufficient for all three VMs. Mitigation: start with control and staging if `8` Dsv5-family vCPUs are available; request quota increase before production.
- **RISK-002**: Bsv2 burstable VMs may throttle builds or raster workloads. Mitigation: use Dsv5 by default; use Bsv2 only for cost-saving control-plane rehearsal.
- **RISK-003**: Coolify registration page is temporarily open after installation. Mitigation: create the first admin account immediately and restrict access by firewall or VPN.
- **RISK-004**: Staging HTTPS is required when `AUTH_COOKIE_SECURE=true`. Mitigation: configure TLS on staging before testing authenticated login flows.
- **RISK-005**: Docker installed through Snap can break expected Docker/Coolify behavior. Mitigation: install Docker only from official Docker packages.
- **RISK-006**: Public exposure of private services would violate Akasha architecture. Mitigation: enforce network security group rules, host firewall rules, Coolify domain assignment discipline, and external port scans.
- **RISK-007**: Self-hosted runner can expose secrets if it runs untrusted fork code. Mitigation: restrict workflows and repository settings so untrusted fork PRs do not execute on the runner.
- **RISK-008**: Production deploy can drift from staging if images are rebuilt. Mitigation: production deploy must reuse the exact Git SHA image tag validated in staging.
- **RISK-009**: Insufficient backup validation can cause unrecoverable production data loss. Mitigation: complete VM/data-disk backup validation or schedule Akasha-specific backups before go-live.
- **ASSUMPTION-001**: The operator has access to the Azure portal and permission to create VMs, disks, public IPs, and network security groups.
- **ASSUMPTION-002**: GitHub remains the source-control system for the repository.
- **ASSUMPTION-003**: GHCR is acceptable unless university policy later requires a self-hosted registry or Harbor.
- **ASSUMPTION-004**: Final DNS names may not be ready at the beginning; temporary Azure public IP access is acceptable during early infrastructure preparation.
- **ASSUMPTION-005**: The existing Akasha application service boundaries remain unchanged.

## 8. Related Specifications / Further Reading

- `docs/self-hosted-coolify-3vm-deployment-plan.md`
- `docs/platform-plan.md`
- `docs/architecture-tech-stack.md`
- `docs/engineering-dos-donts.md`
- `docs/railway-deployment-guide.md`
- `infra/docker/docker-compose.yml`
- Coolify installation: <https://coolify.io/docs/get-started/installation>
- Coolify Docker Compose behavior: <https://coolify.io/docs/knowledge-base/docker/compose>
- GitHub self-hosted runners: <https://docs.github.com/en/actions/reference/runners/self-hosted-runners>
- Azure Dsv5 VM sizing: <https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dsv5-series>
- Azure Bsv2 VM sizing: <https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bsv2-series>
