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

Before patching Coolify, staging and production deploy workflows verify that all four immutable
SHA-tagged images exist in GHCR. If any image is missing, the workflow must fail before the
Coolify stack is changed.

Important: the staging workflow patches the **Coolify Compose definition** with the immutable Git
SHA. It may not update the separate `IMAGE_TAG` row shown in Coolify's environment-variable UI.
When checking what is actually deployed, trust the service image tag shown under the stack's
Services list (for example `akasha-api:<git-sha>`) or the image label, not only the env-var row.
If you manually redeploy from the Coolify UI without running the workflow, then the env-var row
matters only if the stored Compose still references `${IMAGE_TAG}`.

## Phase 3 Bhoonidhi deploy acceptance

Use this sequence for the Phase 3 scheduled-sync hardening changes before
moving to the next implementation phase:

1. Commit and push the Phase 3 hardening changes, including the new files under
   `infra/selfhosted/systemd/`, `scripts/`, and `tests/`.
2. Let the staging workflow build and push the four SHA-tagged images. The
   workflow must pass the immutable GHCR image verification step before it
   patches Coolify.
3. Validate the deployed SHA from a workstation with staging SSH access:

```bash
python scripts/validate_selfhosted_staging_bhoonidhi.py \
  --expected-sha <deployed-git-sha> \
  --skip-timer-check \
  --public-origin https://staging.gis.cidsaglobal.com
```

4. Install the timer on the staging VM:

```bash
infra/selfhosted/systemd/install-akasha-bhoonidhi-sync.sh
```

5. Set `AKASHA_SYNC_DRY_RUN=true` in `/etc/akasha/bhoonidhi-sync.env`, run the
   service once, and inspect the journal:

```bash
sudo systemctl start akasha-bhoonidhi-sync.service
journalctl -u akasha-bhoonidhi-sync.service -n 200 --no-pager
```

6. Re-run the validator without `--skip-timer-check`.
7. Remove `AKASHA_SYNC_DRY_RUN=true`, enable the timer, then run one live
   service invocation only after the dry-run logs are clean.

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
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item
```

After deploying a Bhoonidhi ingestion change, run the repeatable staging validator from a
workstation that can SSH to the staging VM:

```bash
python scripts/validate_selfhosted_staging_bhoonidhi.py --expected-sha <git-sha> --skip-timer-check
```

Remove `--skip-timer-check` after the Phase 3 systemd timer is installed. The validator confirms
the Coolify compose image tags, running `web`/`api` image revisions, container health,
`worker.py verify`, `worker.py verify-cogs`, current-window Bhoonidhi search behavior, and the
known historical dry-run sync window. It stops immediately when the expected image tag is not
running; use `--continue-after-failure` only when intentionally gathering diagnostics from a
known-bad deploy.

To include the public gateway/API smoke in the same run, add `--public-origin
https://<staging-domain>`. Without a strict flag, public smoke is advisory because
staging product endpoints normally require authentication. Add `--smoke-login`
when `AKASHA_SMOKE_USERNAME` and `AKASHA_SMOKE_PASSWORD` are set locally; that
makes the public smoke a required gate. Add `--require-public-smoke`,
`--require-raster`, or `--require-monitoring-clean` only when that stricter gate
is expected to pass. `--require-monitoring-clean` automatically runs the smoke
with `--login`; it fails storage errors, zero-byte COG objects, stale/missing
refresh heartbeats, missing active field composites, low coverage/usable pixels,
unresolved ingestion failures, and tile-unavailable dates. A stale ResourceSat
catalog/composite date is allowed only when the Bhoonidhi search heartbeat is
fresh and the source reports the explicit `UPSTREAM_DATA_STALE` warning class.

6. If `AUTH_ALLOW_BOOTSTRAP=true`, create the first admin user through `/api/auth/bootstrap`, then set `AUTH_ALLOW_BOOTSTRAP=false` in Coolify and redeploy.
7. Run unauthenticated smoke checks:

```bash
python scripts/smoke-test.py https://<staging-domain>
```

8. Run authenticated smoke checks after a user exists:

```bash
AKASHA_SMOKE_USERNAME=<username> AKASHA_SMOKE_PASSWORD=<password> python scripts/smoke-test.py https://<staging-domain> --login
```

9. Verify operator monitoring after a user exists:

```bash
curl -fsS -b cookies.txt https://<staging-domain>/api/monitoring/imagery-sources
```

The payload should include `sources`, `storage`, and `ingestionLedger`. If
`ingestionLedger.status` is `missing`, confirm the API service has the read-only
`/srv/akasha/ingestion` mount and the worker writes `BHOONIDHI_LEDGER_PATH`.

10. Verify private ports from outside the host:

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
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item
```

## Scheduled Bhoonidhi sync

Phase 3 uses a systemd timer on the staging worker VM so Bhoonidhi traffic comes
from the whitelisted static IP and raw/work/ledger files stay under
`/srv/akasha`.

Install the timer artifacts:

```bash
infra/selfhosted/systemd/install-akasha-bhoonidhi-sync.sh
```

Edit `/etc/akasha/bhoonidhi-sync.env` for AOI, window, and per-run download
cap. `AKASHA_COMPOSE_FILE` and `AKASHA_COMPOSE_PROJECT` can usually stay unset
on Coolify hosts; the wrapper auto-detects the rendered compose file and uses
the existing local image with `AKASHA_SYNC_PULL_POLICY=never`. The service uses
a host-level `flock` at `/srv/akasha/ingestion/bhoonidhi-sync.systemd.lock`;
the worker also uses its own ledger lock, so overlapping timer/manual runs fail
fast.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now akasha-bhoonidhi-sync.timer
systemctl list-timers akasha-bhoonidhi-sync.timer
journalctl -u akasha-bhoonidhi-sync.service -n 200 --no-pager
```

The installer also accepts `--enable`, `--start`, and `--dry-run`. For the
first staging validation, set `AKASHA_SYNC_DRY_RUN=true` in
`/etc/akasha/bhoonidhi-sync.env`, then run
`sudo systemctl start akasha-bhoonidhi-sync.service` and inspect the journal
before enabling live downloads.

For the launch backfill, set `AKASHA_SYNC_BACKFILL_DAYS=90` and
`AKASHA_SYNC_BACKFILL_STEP_DAYS=15` in `/etc/akasha/bhoonidhi-sync.env`. Each
timer run processes one bounded historical window and advances
`AKASHA_SYNC_BACKFILL_STATE_PATH` (default under `/srv/akasha/ingestion`). Remove
those settings after the backfill completes so the daily timer returns to the
rolling current window. For a manual one-off window, set
`AKASHA_SYNC_WINDOW_START` and `AKASHA_SYNC_WINDOW_END`, then run
`sudo systemctl start akasha-bhoonidhi-sync.service`.

For additional AOIs, set `AOI_CONFIG_DIR` to a directory containing one GeoJSON
file per AOI, using filenames such as `mysore-60km.geojson`, then pass the
matching id to ingestion commands:

```bash
python worker.py bhoonidhi-search --source resourcesat-2a-liss3-boa --aoi mysore-60km --aoi-dir /app/data/seed/aois
python worker.py build-composite --source resourcesat-2a-liss3-boa --aoi mysore-60km --aoi-dir /app/data/seed/aois --window-start 2026-03-01 --window-end 2026-03-31
```

EOS-04 and NISAR SAR sources are registered as gated context layers until a validated native
operator-download/prep workflow is available. The `ingestion-sar` service still contains the legacy
Sentinel-1 regression path; use `docs/sentinel-1-grd-cog-prep-runbook.md` only for that explicit
legacy workflow, not for production ISRO SAR onboarding.

## Rollback

1. Pick a previous known-good Git SHA image tag.
2. Set `IMAGE_TAG` in Coolify to that exact SHA, or run the production/staging workflow with that exact SHA when supported.
3. Redeploy the same Compose stack.
4. Rerun smoke checks and private-port checks.

## Production promotion

Production is created only after staging acceptance passes. The production workflow requires manual GitHub Environment approval and accepts an explicit `image_tag`. It does not build images.

Use only the exact Git SHA tag already validated in staging.
