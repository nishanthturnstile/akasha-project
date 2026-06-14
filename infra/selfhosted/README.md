# Akasha self-hosted Coolify deployment

This directory contains the repository-side deployment artifacts for the self-hosted Coolify path.

- `coolify-compose.yml` — staging/production Docker Compose source of truth for Coolify service stacks.
- `env.example` — environment-variable template. Copy values into Coolify; never commit real secrets.

The stack preserves Akasha's one-public-service rule: **only `web` is public**. Browser traffic must enter through `web` and use same-origin `/api/*` and `/tiles/*` paths.

## Architecture guardrails

- `web` is the only service with a Coolify FQDN via `SERVICE_FQDN_WEB=/`.
- `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and `ingestion-sar` have no host `ports:` mappings.
- Staging and production pull prebuilt images from GHCR.
- Production deploys an already validated Git SHA image tag; it does not build release images.
- Persistent runtime state is mounted under `/srv/akasha` on the target server.

## Required target directories

Create these directories on each runtime server before deploying:

```bash
sudo mkdir -p /srv/akasha/postgis /srv/akasha/minio /srv/akasha/data/raw /srv/akasha/data/work /srv/akasha/data/seed/rasters /srv/akasha/logs /srv/akasha/backups /srv/akasha/snap-cache
```

## Coolify staging setup

1. Open project `akasha` and environment `staging`.
2. Open the existing service stack `akasha-staging-compose`.
3. Replace the placeholder Compose content with `infra/selfhosted/coolify-compose.yml`.
4. Copy variables from `infra/selfhosted/env.example` into the Coolify service stack environment.
5. Replace all `CHANGE_ME_*` values in Coolify.
6. Set `IMAGE_TAG` to the Git SHA image tag that exists in GHCR.
7. Assign a public domain/FQDN only to the `web` service.
8. Do not assign public domains to private services.
9. Deploy the service stack only after the required env values are present.

Postgres password note: `POSTGRES_PASSWORD` is passed directly to the Postgres
container, while `POSTGRES_PASSWORD_URLENCODED` is used inside `DATABASE_URL` for
`api` and `ingestion-worker`. If the password contains URL-special characters
such as `@`, `/`, `:`, `#`, `%`, `?`, or `&`, URL-encode it before setting
`POSTGRES_PASSWORD_URLENCODED`.

Generate the encoded value locally without printing the password in chat:

```bash
python -c "import urllib.parse, getpass; print(urllib.parse.quote(getpass.getpass('Postgres password: '), safe=''))"
```

For temporary HTTP public-IP rehearsal, set:

```text
PUBLIC_ORIGIN=http://<staging-public-ip>
AUTH_COOKIE_SECURE=false
```

For DNS/TLS staging or production, set:

```text
PUBLIC_ORIGIN=https://<final-domain>
AUTH_COOKIE_SECURE=true
```

## Required GitHub configuration

Repository secrets:

- `COOLIFY_API_URL` — Coolify API base URL including `/api/v1`, for example `http://20.204.163.166:8000/api/v1`.
- `COOLIFY_TOKEN` — Coolify API bearer token.

Repository variables:

- `COOLIFY_STAGING_SERVICE_UUID` — UUID of the `akasha-staging-compose` service stack.
- `COOLIFY_PRODUCTION_SERVICE_UUID` — UUID of the future `akasha-production-compose` service stack.
- `VITE_ESRI_API_KEY` — optional frontend build key, referrer-restricted in ArcGIS.
- `VITE_ESRI_BASEMAP_STYLE` — optional, defaults to `arcgis/imagery`.
- `VITE_ESRI_BASEMAP_STYLE_FAMILY` — optional, defaults to `arcgis`.
- `VITE_ESRI_BASEMAP_PLACES` — optional, defaults to `none`.
- `VITE_ESRI_BASEMAP_SESSION_SECONDS` — optional, defaults to `43200`.

GitHub Environment:

- Create environment `production`.
- Require manual reviewers before `deploy-production.yml` can run.

## Image build and staging deploy

The staging workflow builds and pushes these images from the client repository on the self-hosted runner:

- `ghcr.io/akasha-techcatalyst/akasha-web:<git-sha>`
- `ghcr.io/akasha-techcatalyst/akasha-api:<git-sha>`
- `ghcr.io/akasha-techcatalyst/akasha-ingestion-worker:<git-sha>`
- `ghcr.io/akasha-techcatalyst/akasha-ingestion-sar:<git-sha>`

It then renders `coolify-compose.yml` with `IMAGE_TAG=<git-sha>`, patches the Coolify staging service stack, and triggers a Coolify deployment.

## First staging deployment checklist

1. Confirm `IMAGE_TAG` exists in GHCR for all four Akasha images.
2. Confirm Coolify env values are set and no `CHANGE_ME` placeholders remain.
3. Deploy `akasha-staging-compose`.
4. Run API migrations inside the `api` container:

```bash
python -m app.cli migrate
```

5. Seed or verify catalog/storage only when required for the staging dataset, from `ingestion-worker`:

```bash
python worker.py seed
python worker.py verify
python worker.py verify-cogs
```

6. If `AUTH_ALLOW_BOOTSTRAP=true`, create the first admin user through `/api/auth/bootstrap`, then set `AUTH_ALLOW_BOOTSTRAP=false` in Coolify and redeploy.
7. Run unauthenticated smoke checks:

```bash
python scripts/smoke-test.py https://<staging-domain>
```

8. Run authenticated smoke checks after a user exists:

```bash
AKASHA_SMOKE_USERNAME=<username> AKASHA_SMOKE_PASSWORD=<password> python scripts/smoke-test.py https://<staging-domain> --login
```

9. Verify private ports from outside the host:

```bash
for p in 5432 9000 9001 8080 8000; do timeout 4 bash -lc "</dev/tcp/<staging-public-ip>/$p" && echo "$p open" || echo "$p closed_or_filtered"; done
```

## One-shot jobs

Run one-shot jobs from the Coolify terminal or container shell. Do not expose these services publicly.

App schema migration from `api`:

```bash
python -m app.cli migrate
```

Catalog/storage seed and verification from `ingestion-worker`:

```bash
python worker.py seed
python worker.py verify
python worker.py verify-cogs
```

SAR preprocessing from `ingestion-sar` depends on staged input data under `/srv/akasha/data` and should follow `docs/sentinel-1-grd-cog-prep-runbook.md`.

## Rollback

1. Pick a previous known-good Git SHA image tag.
2. Set `IMAGE_TAG` in Coolify to that exact SHA, or run the production/staging workflow with that exact SHA when supported.
3. Redeploy the same Compose stack.
4. Rerun smoke checks and private-port checks.

## Production promotion

Production is created only after staging acceptance passes. The production workflow requires manual GitHub Environment approval and accepts an explicit `image_tag`. It does not build images.

Use only the exact Git SHA tag already validated in staging.
