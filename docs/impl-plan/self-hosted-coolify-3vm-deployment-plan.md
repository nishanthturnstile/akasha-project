# Self-hosted Coolify 3-VM deployment plan

## Purpose

This document is the review plan for deploying Akasha on self-managed Linux
servers using Coolify and Docker Compose.

The immediate rehearsal environment is Azure VMs, but Azure is used only as
commodity virtual machines, disks, networking, and DNS/IP plumbing. The target
architecture must remain portable to:

- university physical servers,
- university virtualized servers,
- rented VPS providers,
- local/on-prem Linux hosts.

Do not use Azure managed services for the target deployment path:

- no Azure App Service,
- no Azure Database,
- no Azure Blob Storage,
- no Azure Container Registry unless explicitly approved later,
- no Azure DevOps,
- no Azure Key Vault.

The application runtime remains Akasha's existing multi-service topology. The
deployment control plane is self-hosted Coolify, but the application service
boundaries do not change.

## Final decision

Use three VMs:

| VM | Role | Minimum CPU | Minimum RAM | Minimum storage |
| --- | --- | ---: | ---: | ---: |
| `akasha-control` | Coolify control plane, GitHub self-hosted runner, Docker image builds, deploy orchestration | 4 vCPU | 16 GB | 256 GB SSD |
| `akasha-staging` | Full staging Akasha stack | 4 vCPU | 16 GB | 512 GB SSD |
| `akasha-production` | Full production Akasha stack | 8 vCPU | 32 GB | 1 TB SSD |

Use Coolify as the deployment/control plane.

Use GitHub as source control.

Use a GitHub self-hosted runner on `akasha-control`.

Build Docker images on `akasha-control`, push them to a registry, and make
staging/production pull tested images. Staging and production must not build
production release images during normal deploys.

Only four services are built from this repo and tagged with the Git SHA:
`web`, `api`, `ingestion-worker`, `ingestion-sar`. The remaining services run
**pinned upstream images** and are never rebuilt: `titiler`
(`ghcr.io/developmentseed/titiler:1.0.0`), `stac-api`
(`ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2`), `postgis`
(`postgis/postgis:16-3.5`), `minio` (`minio/minio:RELEASE.2025-09-07T16-13-09Z`).

Use Docker Compose for the Akasha runtime. The Compose file remains the source
of truth for Akasha services, storage, internal networking, health checks, and
environment variable references.

Preserve the one-public-service rule:

- `web` is the only public Akasha service.
- Browser traffic uses same-origin paths:
  - `/api/*` through `web` to internal `api`
  - `/tiles/*` through `web` to internal `titiler`
- `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and
  `ingestion-sar` are private services.
- The browser must never receive MinIO, PostGIS, STAC API, TiTiler, or object
  storage URLs.

## Why Coolify fits this deployment

Coolify is used as an open-source self-hosted PaaS/control plane. It can manage
remote servers over SSH, deploy Docker Compose applications, route public
domains, manage environment variables, provide deployment history, and expose
container logs.

Coolify replaces:

- hand-written `systemd` wrappers for normal Compose deploys,
- manual `docker compose up` release operations,
- manual TLS certificate setup for public domains,
- manual deploy history tracking,
- basic container log access,
- basic deployment health visibility.

Coolify does not replace:

- Akasha's `web` gateway contract,
- GitHub Actions CI quality gates,
- production approval rules,
- application smoke tests,
- database/app migration discipline,
- restore validation,
- host security hardening,
- long-term backup policy if university VM backup is insufficient.

## VM sizing rationale

### `akasha-control`

Minimum:

- 4 vCPU
- 16 GB RAM
- 256 GB SSD

Azure rehearsal example:

- preferred: `Standard_D4s_v5` or equivalent,
- cost-saving option: `Standard_B4s_v2`, only if build throttling is acceptable.

Why this size:

- Coolify itself can run on much smaller hardware, but this VM also runs the
  GitHub self-hosted runner and Docker image builds.
- Akasha builds include frontend Node/Vite work, Python dependency resolution,
  Docker layers, raster/GDAL-related images, Trivy scans, and build cache.
- 2 vCPU / 2 GB RAM is not realistic for this combined control/build role.

Suggested disk layout:

| Mount | Size | Purpose |
| --- | ---: | --- |
| `/` | 64 GB | OS, packages, Coolify base files |
| `/var/lib/docker` or `/data` | 192 GB | Docker images, layers, runner workdir, scans, Coolify data |

If using a single disk, allocate at least 256 GB and monitor Docker usage.

### `akasha-staging`

Minimum:

- 4 vCPU
- 16 GB RAM
- 512 GB SSD

Azure rehearsal example:

- `Standard_D4s_v5` or equivalent.

Why this size:

- Staging runs the full service topology, not a mocked app.
- It needs enough memory for PostGIS, pgSTAC/STAC API, MinIO, TiTiler, FastAPI,
  Caddy, and one-shot ingestion jobs.
- It should be able to validate production-like smoke tests and rollback.

Suggested disk layout:

| Mount | Size | Purpose |
| --- | ---: | --- |
| `/` | 64 GB | OS and Docker runtime |
| `/srv/akasha` | 512 GB | PostGIS data, MinIO data, seed/ingestion data, app persistent files |

### `akasha-production`

Minimum:

- 8 vCPU
- 32 GB RAM
- 1 TB SSD

Azure rehearsal example:

- `Standard_D8s_v5` or equivalent.

Why this size:

- Production handles real user traffic plus raster workloads.
- PostGIS/pgSTAC and MinIO share the host with TiTiler and BFF raster
  statistics.
- Cloud-masked vegetation-index statistics can be CPU and I/O heavy because the
  BFF reads analytic COG and SCL COG windows.
- 1 TB is the minimum for MVP Bangalore with limited scene history. More AOIs,
  more dates, or regional ingestion need more disk before anything else.

Suggested disk layout:

| Mount | Size | Purpose |
| --- | ---: | --- |
| `/` | 64 GB | OS and Docker runtime |
| `/srv/akasha` | 1 TB minimum | PostGIS, MinIO COGs, seed/ingestion data, app persistent files |

## Storage paths

Use consistent paths across Azure, physical servers, and VPS providers.

On staging and production:

```text
/srv/akasha/
  postgis/
  minio/
  data/
  logs/
  backups/
```

Expected use:

- `/srv/akasha/postgis` stores PostgreSQL/PostGIS data.
- `/srv/akasha/minio` stores MinIO object data, including COGs.
- `/srv/akasha/data` stores seed data, ignored raw downloads, COG prep work, and
  manifests.
- `/srv/akasha/logs` is optional if logs are drained to host files later.
- `/srv/akasha/backups` is reserved for optional Akasha-level backups if
  university VM backup is insufficient.

For production, use SSD-backed storage. Avoid slow HDD-backed storage for
PostGIS and active MinIO COG reads.

## Network and DNS

### DNS records

Use these names in Azure rehearsal and equivalent names later on university/VPS
servers:

| Host | DNS example | Public? |
| --- | --- | --- |
| `akasha-control` | `control.akasha.example.edu` | Admin-only |
| `akasha-staging` | `staging.akasha.example.edu` | Yes, restricted if needed |
| `akasha-production` | `akasha.example.edu` | Yes |

### Firewall rules

`akasha-control`:

- allow `22/tcp` only from admin IPs,
- allow `443/tcp` for Coolify UI only from admin IPs or VPN,
- allow outbound `443/tcp` to GitHub, GHCR, package registries, and target VMs,
- allow SSH from control to staging/production.

`akasha-staging`:

- allow `80/tcp` and `443/tcp` publicly or from approved testing IPs,
- allow `22/tcp` only from admin IPs and `akasha-control`,
- do not expose app private service ports.

`akasha-production`:

- allow `80/tcp` and `443/tcp` publicly,
- allow `22/tcp` only from admin IPs and `akasha-control`,
- do not expose app private service ports.

Private Akasha services must not have public host port mappings:

- Postgres `5432`,
- MinIO `9000` and `9001`,
- STAC API `8080`,
- TiTiler `8000`,
- FastAPI `8000`.

## Operating system baseline

Preferred OS:

- Ubuntu 24.04 LTS.

Acceptable alternatives:

- Ubuntu 22.04 LTS,
- Debian 12,
- another Linux distribution supported by Docker and Coolify.

Baseline setup for every VM:

- SSH key authentication only,
- password SSH login disabled,
- root SSH login disabled after bootstrap if operationally possible,
- firewall enabled,
- unattended security updates enabled,
- fail2ban installed for SSH,
- time sync enabled,
- Docker installed from official Docker packages,
- Docker installed normally, not via Snap,
- data disk mounted persistently in `/etc/fstab`,
- monitoring for disk usage configured at minimum by host alerting or Coolify.

## Coolify control-plane setup

Coolify is installed only on `akasha-control`.

Steps:

1. Provision `akasha-control`.
2. Install Ubuntu 24.04 LTS.
3. Attach and mount the Docker/Coolify data disk.
4. Configure firewall before exposing the host.
5. Install Coolify using the official self-hosted installer.
6. Open the displayed Coolify URL immediately.
7. Create the first admin account immediately.
8. Configure the public/admin domain, for example
   `https://control.akasha.example.edu`.
9. Restrict Coolify UI access by firewall, VPN, or trusted IP allowlist.
10. Add outbound SSH access from `akasha-control` to staging and production.
11. Add staging and production as Coolify servers.
12. Verify Coolify can connect to each server and control Docker.

Coolify project structure:

```text
Project: akasha
  Environment: staging
    Resource: akasha-staging-compose
  Environment: production
    Resource: akasha-production-compose
```

Each environment uses the same Compose file but different:

- domain,
- environment variables,
- secrets,
- image tags,
- persistent host paths.

## GitHub self-hosted runner setup

Install the GitHub Actions runner on `akasha-control`.

Runner labels:

```text
self-hosted
linux
x64
akasha-control
```

The runner needs:

- outbound HTTPS to GitHub Actions,
- outbound HTTPS to GHCR or the chosen registry,
- Docker access for image builds,
- permissions to trigger Coolify deploys,
- no direct production database or MinIO credentials unless a job explicitly
  requires them.

Security posture:

- use a dedicated Linux user for the runner,
- avoid running untrusted fork pull request code on this runner,
- restrict workflows so deployment jobs only run from trusted branches,
- use GitHub Environments for production approvals,
- rotate runner registration tokens and Coolify API tokens when needed.

## Container registry

Default choice:

- GitHub Container Registry (GHCR), because GitHub is already selected.

Image tags:

```text
ghcr.io/<org-or-user>/akasha-web:<git-sha>
ghcr.io/<org-or-user>/akasha-api:<git-sha>
ghcr.io/<org-or-user>/akasha-ingestion:<git-sha>
ghcr.io/<org-or-user>/akasha-ingestion-sar:<git-sha>
```

Production must deploy an immutable Git SHA tag that has already passed staging.

If university policy disallows GHCR, replace GHCR with a self-hosted registry or
Harbor. That change should not alter the Akasha Compose topology.

### `web` image is build-time configured (important)

The `web` image bakes the frontend at build time. The `VITE_ESRI_*` values are
Docker **build args** (see `infra/gateway/Dockerfile`), not runtime environment
variables. Setting them in Coolify's runtime env panel has no effect on an
already-built image.

Decision (keep it simple): use **one** referrer-restricted ArcGIS key whose
allowed referrers include both the staging and production domains. Build a single
`akasha-web:<sha>` image and deploy that same image to staging and production.
This preserves the "same SHA to production" rule. The only per-environment `web`
runtime values are `PUBLIC_APP_NAME` and `PUBLIC_DEFAULT_AOI_NAME`; everything
else the SPA needs comes from the same-origin `/api/config` response.

## Repository changes required before implementation

Add a self-hosted deployment folder:

```text
infra/selfhosted/
  coolify-compose.yml
  env.example
  README.md
```

Add GitHub Actions workflows:

```text
.github/workflows/
  ci.yml
  deploy-staging.yml
  deploy-production.yml
```

Legacy hosting deployment docs and config have been removed from the repository
now that the self-hosted Coolify/Azure path is the source of truth.

One small code change is required: extend `scripts/smoke-test.py` with an
optional `--login` mode (username/password from env) so the authenticated
product checks can run against an `AUTH_MODE=enabled` deployment. The existing
unauthenticated checks (`/health`, `/api/health`, `/api/_skeleton/*`) stay as-is.
See "Smoke tests" for why this is needed.

## Coolify Compose requirements

Create `infra/selfhosted/coolify-compose.yml` from the current
`infra/docker/docker-compose.yml`, adapted for managed self-hosted deployment.

Required changes from local Compose:

- assign a public domain only to `web` in Coolify; give no other service a
  domain,
- do not publish host ports for any service except what Coolify needs to route
  to `web`,
- keep all other services private on the Compose network,
- use registry image tags driven by `${IMAGE_TAG:?}` for the four built services
  (`web`, `api`, `ingestion-worker`, `ingestion-sar`); keep the pinned upstream
  images for `titiler`, `stac-api`, `postgis`, `minio`,
- use `${VAR:?}` for required secrets so a missing secret fails the deploy
  loudly,
- use bind mounts under `/srv/akasha` instead of named volumes (see below),
- keep one-shot ingestion services out of normal health requirements,
- preserve existing health checks where possible.

### Public routing (one-public-service under Coolify)

Coolify's built-in proxy terminates TLS and forwards the public domain to the
`web` service on its container port `80`. `web` (Caddy) then serves the SPA and
reverse-proxies `/api/*` to `api:8000` and `/tiles/*` to `titiler:8000` on the
internal Compose network. This is two proxies in series (Coolify proxy -> Caddy)
and is expected. `web` stays plain HTTP on `:80` internally; HTTPS is handled by
Coolify at the edge. Assign the domain to `web` only.

Set `SERVICE_FQDN_WEB` to the exact public web origin, for example
`https://staging.gis.cidsaglobal.com`, and keep `PUBLIC_ORIGIN`/`CORS_ALLOWED_ORIGINS`
aligned with the same value. Do not leave `SERVICE_FQDN_WEB=/` for staging or
production; that makes Coolify generate a temporary HTTP domain and leaves the
canonical HTTPS domain unrouted.

### Image tags from CI

The four built services reference the deployed Git SHA through one variable:

```text
image: ghcr.io/<org-or-user>/akasha-web:${IMAGE_TAG}
image: ghcr.io/<org-or-user>/akasha-api:${IMAGE_TAG}
image: ghcr.io/<org-or-user>/akasha-ingestion:${IMAGE_TAG}
image: ghcr.io/<org-or-user>/akasha-ingestion-sar:${IMAGE_TAG}
```

CD sets `IMAGE_TAG=<git-sha>` per environment. Production reuses the exact
`IMAGE_TAG` already validated in staging.

### Volumes (bind mounts under `/srv/akasha`)

Local Compose uses named volumes (`postgis_data`, `minio_data`, `snap_cache`).
For self-hosted deployment, convert these to host bind mounts so backups and
restores operate on plain files:

```text
postgis -> /srv/akasha/postgis:/var/lib/postgresql/data
minio   -> /srv/akasha/minio:/data
data    -> /srv/akasha/data:/app/data   (ingestion services)
```

Create these directories with correct ownership before the first deploy.

Private internal URLs should stay as Docker DNS names:

```text
API_UPSTREAM_URL=http://api:8000
TITILER_UPSTREAM_URL=http://titiler:8000
DATABASE_URL=postgresql://<user>:<password>@postgis:5432/<db>
STAC_API_URL=http://stac-api:8080
TITILER_URL=http://titiler:8000
S3_ENDPOINT_URL=http://minio:9000
AWS_S3_ENDPOINT=minio:9000
```

## Environment variables

Use separate variables for staging and production. Never share secrets between
environments.

### `web`

Runtime env (Coolify) is intentionally minimal — the SPA is already built into
the image and gets its config from same-origin `/api/config`:

```text
SERVICE_FQDN_WEB=https://<environment-domain>
PUBLIC_ORIGIN=https://<environment-domain>
PUBLIC_APP_NAME=Akasha
PUBLIC_DEFAULT_AOI_NAME=Bangalore
API_UPSTREAM_URL=http://api:8000
TITILER_UPSTREAM_URL=http://titiler:8000
GATEWAY_BASIC_AUTH=
```

The `VITE_ESRI_*` values are **build args**, not runtime env. They are supplied
once when CI builds the `web` image (see "`web` image is build-time configured").
Do not list them as Coolify runtime variables.

### `api`

```text
APP_ENV=production
PORT=8000
DATABASE_URL=postgresql://<user>:<password>@postgis:5432/<db>
STAC_API_URL=http://stac-api:8080
TITILER_URL=http://titiler:8000
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=<minio-user>
AWS_SECRET_ACCESS_KEY=<minio-password>
AWS_S3_ENDPOINT=minio:9000
AWS_VIRTUAL_HOSTING=FALSE
AWS_HTTPS=NO
AWS_REGION=us-east-1
GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff
AKASHA_RGB_RESCALE=0,3000
AKASHA_S1_VV_RESCALE=-25,5
DEFAULT_SOURCE_ID=resourcesat-2a-liss3-boa
# Optional multi-AOI selector. Leave blank to use AOI_CONFIG_PATH as the default AOI.
DEFAULT_AOI_ID=
BASEMAP_PROVIDER=esri
ESRI_BASEMAP_STYLE=arcgis/imagery
ESRI_BASEMAP_STYLE_FAMILY=arcgis
ESRI_BASEMAP_USAGE_MODEL=session
ESRI_BASEMAP_PLACES=none
ESRI_BASEMAP_SESSION_SECONDS=43200
USABLE_PIXEL_THRESHOLD_PERCENT=70
MAX_POLYGON_AREA_HA=50
MAX_POLYGON_VERTICES=5000
INDEX_REQUEST_TIMEOUT_SECONDS=30
RATE_LIMIT_INDEX_PER_MINUTE=30
MAX_REQUEST_BODY_BYTES=1048576
CORS_ALLOWED_ORIGINS=https://<environment-domain>
AUTH_MODE=enabled
AUTH_ALLOW_DISABLED=false
AUTH_PASSWORD_PEPPER=<generated-secret>
AUTH_ALLOW_SIGNUP=false
AUTH_COOKIE_SECURE=true
AUTH_SESSION_COOKIE_NAME=akasha_session
AUTH_SESSION_TTL_MINUTES=480
AUTH_REMEMBER_TTL_DAYS=30
AUTH_LOGIN_RATE_LIMIT_PER_MINUTE=10
AUTH_SIGNUP_RATE_LIMIT_PER_HOUR=20
```

### `titiler`

```text
PORT=8000
AWS_ACCESS_KEY_ID=<minio-user>
AWS_SECRET_ACCESS_KEY=<minio-password>
AWS_S3_ENDPOINT=minio:9000
AWS_VIRTUAL_HOSTING=FALSE
AWS_HTTPS=NO
AWS_REGION=us-east-1
GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff
```

### `stac-api`

```text
POSTGRES_HOST_READER=postgis
POSTGRES_HOST_WRITER=postgis
POSTGRES_PORT=5432
POSTGRES_USER=<postgres-user>
POSTGRES_PASS=<postgres-password>
POSTGRES_DBNAME=<postgres-db>
APP_HOST=0.0.0.0
APP_PORT=8080
```

### `postgis`

```text
POSTGRES_USER=<generated-user>
POSTGRES_PASSWORD=<generated-password>
POSTGRES_DB=akasha
```

### `minio`

```text
MINIO_ROOT_USER=<generated-user>
MINIO_ROOT_PASSWORD=<generated-password>
MINIO_BROWSER=off
```

### `ingestion-worker`

```text
DATABASE_URL=postgresql://<user>:<password>@postgis:5432/<db>
STAC_API_URL=http://stac-api:8080
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=<minio-user>
S3_SECRET_KEY=<minio-password>
S3_REGION=us-east-1
AKASHA_COG_BUCKET=akasha-cogs
SEED_DATA_DIR=/app/data/seed
AOI_CONFIG_PATH=/app/data/seed/bangalore-60km-aoi.geojson
```

## CI workflow

Pull requests run validation only.

Required CI jobs:

1. Python lint:

   ```bash
   ruff check apps/api services/ingestion scripts
   ```

2. API tests:

   ```bash
   cd apps/api
   python -m pytest -q
   ```

3. Frontend checks:

   ```bash
   cd apps/frontend
   yarn install --frozen-lockfile
   yarn lint
   yarn test
   yarn build
   ```

4. Slice validators:

   ```bash
   python scripts/validate_slice0.py
   python scripts/validate_slice1.py
   python scripts/validate_slice2.py
   ```

5. Security scans:

   ```bash
   gitleaks detect
   trivy fs .
   ```

CI should fail on:

- lint errors,
- failing tests,
- failed frontend build,
- failed validators,
- committed secrets,
- high/critical vulnerabilities according to the threshold selected during
  implementation.

## CD workflow

### Staging

Trigger:

- merge to `main`.

Steps:

1. Checkout repository on `akasha-control` runner.
2. Run CI gates or depend on completed CI workflow.
3. Build the four images (`web`, `api`, `ingestion-worker`, `ingestion-sar`).
4. Tag images with the Git SHA.
5. Push images to GHCR or approved registry.
6. Tell Coolify to deploy staging with `IMAGE_TAG=<git-sha>`.
7. Wait for deployment to become healthy.
8. Run app schema migrations on the `api` container:

   ```bash
   python -m app.cli db upgrade
   ```

9. Run smoke test (authenticated; see "Smoke tests"):

   ```bash
   python scripts/smoke-test.py https://staging.akasha.example.edu --login
   ```

10. Record deployed Git SHA.

### Production

Trigger:

- manual GitHub Environment approval,
- only after staging has passed for the same Git SHA.

Steps:

1. Confirm requested production SHA equals the staging-tested SHA.
2. Optionally confirm latest university VM backup status.
3. Trigger Coolify production deploy with the exact same image tags.
4. Run app schema migrations: `python -m app.cli db upgrade` on the `api`
   container (Alembic; covers all app tables, not just plots).
5. Run catalog/storage seed or ingestion verification if required by the
   release.
6. Wait for deployment to become healthy.
7. Run smoke test (authenticated; see "Smoke tests"):

   ```bash
   python scripts/smoke-test.py https://akasha.example.edu --login
   ```

8. Keep previous image tag available for rollback.

Production must not build images. It pulls already-tested immutable image tags.

### Migrations and one-shot jobs under Coolify

Migrations, seeding, and verification are one-shot commands, not long-running
services. Run them as command executions against the relevant container after
the stack is healthy (Coolify's container terminal/exec, or an SSH step from the
`akasha-control` runner):

```bash
# app schema (api container) — Alembic, idempotent
python -m app.cli db upgrade

# catalog + storage seed / verify (ingestion-worker container)
python worker.py seed       # only when (re)initialising ResourceSat catalog scaffolding
python worker.py verify     # PostGIS/STAC/MinIO reachability
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km
```

`ingestion-worker` and `ingestion-sar` stay `restart: "no"` and must not count
toward stack health. Never run seed automatically on every deploy — it is an
explicit, on-demand action.

## Azure rehearsal implementation steps

### 1. Provision infrastructure

1. Create three Ubuntu 24.04 LTS VMs:
   - `akasha-control`
   - `akasha-staging`
   - `akasha-production`
2. Attach SSD data disks:
   - control: 256 GB total minimum,
   - staging: 512 GB data disk,
   - production: 1 TB data disk.
3. Assign static public IPs.
4. Create DNS records:
   - `control.akasha.example.edu`
   - `staging.akasha.example.edu`
   - `akasha.example.edu`
5. Configure network security groups/firewall:
   - public `80/443` for staging and production,
   - restricted `443` for control,
   - restricted `22` for all VMs.

### 2. Prepare every VM

1. Update packages.
2. Create admin/deploy users.
3. Install SSH keys.
4. Disable password SSH login.
5. Enable firewall.
6. Install fail2ban.
7. Enable unattended security updates.
8. Install Docker from official Docker packages.
9. Mount data disks:
   - staging/production at `/srv/akasha`,
   - control at `/data` or Docker's configured data path.
10. Reboot once and verify mounts survive reboot.

### 3. Install Coolify on `akasha-control`

1. Run the official Coolify installer.
2. Create the first admin immediately.
3. Configure the Coolify domain.
4. Restrict access to admin IPs or VPN.
5. Configure notification channel if available.
6. Add registry credentials.
7. Add GitHub integration if used.

### 4. Configure GitHub runner

1. Install GitHub Actions runner on `akasha-control`.
2. Register it to the Akasha repository or organization.
3. Apply labels:
   - `self-hosted`
   - `linux`
   - `x64`
   - `akasha-control`
4. Install required build tools:
   - Docker,
   - Git,
   - Node/Yarn if not using build containers,
   - Python if not using build containers,
   - Trivy,
   - Gitleaks.
5. Verify a simple workflow can run on the runner.

### 5. Register staging and production in Coolify

1. Add `akasha-staging` as a Coolify server.
2. Add `akasha-production` as a Coolify server.
3. Verify SSH connectivity.
4. Verify Docker connectivity.
5. Verify Coolify can create networks and containers on both servers.

### 6. Deploy staging

1. Create Coolify project `akasha`.
2. Create environment `staging`.
3. Create Docker Compose resource using `infra/selfhosted/coolify-compose.yml`.
4. Enter staging environment variables.
5. Assign domain only to `web`.
6. Deploy.
7. Run app schema migration: `python -m app.cli db upgrade` (api container).
8. Run seed/verify commands if needed (ingestion-worker container).
9. Create/provision the first user (see "Auth and first user").
10. Run smoke test.
11. Verify private services are not publicly reachable.

### 7. Deploy production

1. Create environment `production`.
2. Create Docker Compose resource using the same Compose file.
3. Enter production environment variables.
4. Assign domain only to `web`.
5. Deploy only the staging-tested Git SHA.
6. Run app schema migration: `python -m app.cli db upgrade` (api container).
7. Run seed/verify commands if needed (ingestion-worker container).
8. Create/provision the first user (see "Auth and first user").
9. Run smoke test.
10. Verify private services are not publicly reachable.

### 8. Rollback rehearsal

1. Identify previous working image tag.
2. Change production resource image tag back to previous SHA.
3. Redeploy through Coolify.
4. Run smoke test.
5. Record rollback time and any manual steps.

## Physical server or VPS migration steps

These steps reproduce the same setup outside Azure.

### 1. Provision servers

Provision three Linux servers with equivalent or better resources:

| Server | Minimum CPU | Minimum RAM | Minimum storage |
| --- | ---: | ---: | ---: |
| control | 4 vCPU or physical cores | 16 GB | 256 GB SSD |
| staging | 4 vCPU or physical cores | 16 GB | 512 GB SSD |
| production | 8 vCPU or physical cores | 32 GB | 1 TB SSD |

For physical servers, prefer:

- SSD/NVMe storage,
- hardware RAID or reliable storage controller if available,
- redundant power/network where the university provides it,
- UPS-backed power if possible.

For VPS providers, prefer:

- dedicated vCPU or non-heavily-throttled shared CPU,
- SSD/NVMe disk,
- ability to attach/expand block storage,
- firewall/security group support,
- static IPs.

### 2. Install the same OS baseline

1. Install Ubuntu 24.04 LTS or approved equivalent.
2. Create the same users.
3. Install the same SSH keys.
4. Configure the same firewall rules.
5. Install the same Docker version family.
6. Mount storage at the same paths:

   ```text
   /srv/akasha
   ```

7. Confirm directory ownership and free disk space.

### 3. Recreate the control plane

1. Install Coolify on the physical/VPS control server.
2. Create the admin account.
3. Configure `control.<new-domain>`.
4. Add the physical/VPS staging and production servers in Coolify.
5. Reconnect GitHub and registry credentials.
6. Register or move the GitHub self-hosted runner to the new control server.

### 4. Recreate Akasha resources

1. Create Coolify project `akasha`.
2. Create environments:
   - `staging`
   - `production`
3. Create Compose resources using the same
   `infra/selfhosted/coolify-compose.yml`.
4. Enter staging variables.
5. Enter production variables.
6. Assign only the `web` service domains.
7. Pull the same image tags from the registry.

### 5. Move data if needed

If moving from Azure rehearsal to physical/VPS production with real data:

1. Stop writes on source production.
2. Export or restore PostGIS data.
3. Copy or restore MinIO data.
4. Copy seed/manifests under `/srv/akasha/data` if needed.
5. Start target stack.
6. Run verification:

   ```bash
   python -m app.cli check
   python worker.py verify
   python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km
   ```

7. Run smoke test against the target staging/production domain.

If Azure had only rehearsal data, do not migrate it. Re-seed or ingest cleanly
on the university/VPS servers.

### 6. Cut over DNS

1. Lower DNS TTL before cutover.
2. Deploy and smoke test the new physical/VPS production host.
3. Point production DNS to the new public IP.
4. Verify TLS.
5. Run smoke test using the final public domain.
6. Keep Azure production stopped but recoverable until acceptance is complete.

## Backup position

Current decision:

- The university may provide complete VM-level backups.
- Akasha-specific backup implementation is deferred unless that backup is not
  sufficient.

Before production go-live, validate the university backup:

- backup frequency,
- retention period,
- whether attached data disks are included,
- whether backups are crash-consistent or application-consistent,
- restore time objective,
- restore point objective,
- whether a single file, whole disk, or full VM can be restored,
- whether restore has been tested by the university team.

Minimum acceptance for relying on VM backup:

- production VM and attached data disk are included,
- restore can recover `/srv/akasha`,
- restore can recover Docker/Coolify data if needed,
- one restore drill succeeds into staging or a temporary VM.

If university backup is insufficient, implement:

- pgBackRest or scheduled `pg_dump` for PostGIS/pgSTAC,
- restic for `/srv/akasha/minio` and `/srv/akasha/data`,
- off-host SFTP/NAS storage,
- monthly restore drill.

## Auth and first user

Product, plot, and feature endpoints are auth-protected. In every deployed
environment `AUTH_MODE=enabled`, so unauthenticated requests to `/api/config`,
`/api/sources`, `/api/layers/default`, tiles, and `/api/indices/statistics`
return `401`. Only `/health`, `/api/health`, and `/api/_skeleton/*` are open.

First-user setup is handled by the standard `/signup` flow when
`AUTH_ALLOW_SIGNUP=true` is intentionally enabled for that environment. If
public sign-up should stay closed, provision users through the approved
operator/user-management process before running authenticated smoke checks.

`AUTH_COOKIE_SECURE=true` requires HTTPS end-to-end. Coolify must terminate TLS
on **staging as well as production**, or the login session cookie is dropped and
sign-in silently fails.

## Smoke tests

Run smoke tests after every staging deploy and production deploy. The preferred
automated command is:

```bash
python scripts/smoke-test.py https://<domain> --login
```

The script logs in (credentials from env) and reuses the session cookie for the
authenticated checks. Manual equivalent:

### Tier 1 — open checks (no auth)

```bash
curl -fsS https://<domain>/health
curl -fsS https://<domain>/api/health
curl -fsS https://<domain>/api/_skeleton/services
```

### Tier 2 — authenticated product checks

```bash
# 1. Log in, capturing the session cookie
curl -fsS -c cookies.txt -X POST https://<domain>/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<user>","password":"<password>"}'

# 2. Reuse the cookie for product endpoints
curl -fsS -b cookies.txt https://<domain>/api/config
curl -fsS -b cookies.txt https://<domain>/api/sources
curl -fsS -b cookies.txt https://<domain>/api/sources/resourcesat-2a-liss3-boa/dates
curl -fsS -b cookies.txt https://<domain>/api/layers/default
```

Then confirm, using the same cookie:

- one ResourceSat FCC tile returns a PNG,
- one NDVI statistics request returns valid JSON.

### Tier 3 — private services must not be reachable

Test from outside the host (not via the public domain on a port). Each must be
refused or filtered, never connect:

```bash
# replace <host-ip> with the server's public IP
for port in 5432 9000 9001 8080 8000; do
  nc -z -w3 <host-ip> $port && echo "OPEN $port (FAIL)" || echo "closed $port (ok)"
done
```

## Acceptance criteria

Staging is accepted when:

- Coolify deploys the full stack successfully.
- Only `web` is public.
- Health checks pass.
- Authenticated smoke test passes (Tier 1 + Tier 2).
- Private services are not externally reachable (Tier 3).
- The browser never receives internal service URLs.
- One rollback rehearsal succeeds.

Production is accepted when:

- production deploy uses the exact image SHA tested in staging,
- manual approval gate is enforced,
- production smoke test passes,
- private services are not externally reachable,
- first admin/user bootstrap is complete and disabled afterward,
- VM backup has been validated or Akasha-specific backup work is scheduled as a
  go-live blocker.

Physical/VPS migration readiness is accepted when:

- a fresh non-Azure server can be prepared using the documented steps,
- Coolify can register the server over SSH,
- the same Compose file deploys without Azure-specific changes,
- DNS cutover steps are rehearsed,
- smoke tests pass on the non-Azure target.

## Open items before implementation

- Confirm final domain names.
- Confirm whether GHCR is acceptable for the university deployment.
- Confirm whether the university permits outbound HTTPS from the control server
  to GitHub and GHCR.
- Confirm whether the university backup covers attached data disks and restore
  drills.
- Confirm expected Sentinel data retention for production beyond MVP Bangalore.
- Confirm who owns production approval in GitHub.
- Confirm the single referrer-restricted ArcGIS key lists both the staging and
  production domains as allowed referrers (so one `web` image serves both).
- Confirm Coolify terminates TLS on staging as well as production (required for
  `AUTH_COOKIE_SECURE=true` login to work).

## References

- Coolify installation:
  <https://coolify.io/docs/get-started/installation>
- Coolify Docker Compose behavior:
  <https://coolify.io/docs/knowledge-base/docker/compose>
- GitHub self-hosted runners:
  <https://docs.github.com/en/actions/reference/runners/self-hosted-runners>
- Azure Dsv5 VM sizing:
  <https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dsv5-series>
- Azure Bsv2 VM sizing:
  <https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bsv2-series>
