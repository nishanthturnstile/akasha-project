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
- `VITE_BASEMAP_PROVIDER` — optional frontend basemap provider; use `esri` for staging/production, `osm` for development previews, or `empty` for no-network debugging.
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

It then renders `coolify-compose.yml` with `IMAGE_TAG=<git-sha>` and patches the Coolify staging service stack with `instant_deploy=true`, so Coolify queues the service deployment as part of the service update.

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

4. Install the scheduler timer on the staging VM:

```bash
infra/selfhosted/systemd/install-akasha-ingestion-scheduler.sh
```

5. Keep `AKASHA_SCHEDULER_ACTIVE=false` or `AKASHA_SCHEDULER_DRY_RUN=true` in
   `/etc/akasha/ingestion-scheduler.env`, run the service once, and inspect the journal:

```bash
sudo systemctl start akasha-ingestion-scheduler.service
journalctl -u akasha-ingestion-scheduler.service -n 200 --no-pager
```

6. Re-run the validator without `--skip-timer-check`.
7. Set `AKASHA_SCHEDULER_ACTIVE=true`, keep `AKASHA_SCHEDULER_DRY_RUN=true` for
   a canary, then set `AKASHA_SCHEDULER_DRY_RUN=false` only after the dry-run logs are clean.

## First staging deployment checklist

1. Confirm `IMAGE_TAG` exists in GHCR for all four Akasha images.
2. Confirm Coolify env values are set and no `CHANGE_ME` placeholders remain.
3. Deploy `akasha-staging-compose`.
4. Confirm the `api` container is healthy. For the current single-replica
   staging/production model, app-schema migrations run automatically during API
   container startup before Uvicorn accepts traffic.
5. Verify the live app schema is at the deployed image's Alembic head from the
   `api` container:

```bash
python -m app.cli db verify-current
```

6. Seed or verify catalog/storage only when required for the staging dataset, from `ingestion-worker`:

```bash
python worker.py seed
python worker.py verify
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km
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

7. Create the first user through the web app `/signup` flow only when `AUTH_ALLOW_SIGNUP=true` is intentionally enabled for that environment; otherwise provision users through the approved operator/user-management process before authenticated smoke checks.
8. Run unauthenticated smoke checks:

```bash
python scripts/smoke-test.py https://<staging-domain>
```

9. Run authenticated smoke checks after a user exists:

```bash
AKASHA_SMOKE_USERNAME=<username> AKASHA_SMOKE_PASSWORD=<password> python scripts/smoke-test.py https://<staging-domain> --login
```

10. Verify operator monitoring after a user exists:

```bash
curl -fsS -b cookies.txt https://<staging-domain>/api/monitoring/imagery-sources
```

The payload should include `sources`, `storage`, and `ingestionLedger`. If
`ingestionLedger.status` is `missing`, confirm the API service has the read-only
`/srv/akasha/ingestion` mount and the worker writes `BHOONIDHI_LEDGER_PATH`.

11. Verify private ports from outside the host:

```bash
for p in 5432 9000 9001 8080 8000; do timeout 4 bash -lc "</dev/tcp/<staging-public-ip>/$p" && echo "$p open" || echo "$p closed_or_filtered"; done
```

## Private database GUI access with DBeaver

Use DBeaver from your workstation and connect through an SSH tunnel. Do **not**
assign a Coolify domain to PostGIS, do **not** add a public `ports:` mapping for
Postgres, and do **not** publish pgAdmin/Adminer for staging or production.

The tunnel targets the private PostGIS container from the SSH host and exposes it
only on your laptop's loopback interface. Local port `15433` intentionally avoids
conflicting with the local-dev DBeaver port `15432`.

1. SSH to the target VM with an approved admin shell account:

   ```bash
   ssh akasha-staging
   ```

2. On the VM, identify the running PostGIS container and its private Docker IP:

   ```bash
   POSTGIS_CONTAINER="$(docker ps --format '{{.Names}}' | grep -E '(^|-)postgis(-|$)' | head -n 1)"
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$POSTGIS_CONTAINER"
   ```

3. From your workstation, open the SSH tunnel. Replace `<postgis-container-ip>`
   with the private IP printed in the previous step:

   ```bash
   ssh -N -L 127.0.0.1:15433:<postgis-container-ip>:5432 akasha-staging
   ```

   Keep this terminal open while using DBeaver. Close it to remove the tunnel.
   If SSH reports `bind [127.0.0.1]:15433: Permission denied` or cannot listen
   on `15433`, another local process is already using that port. On Windows,
   check whether an existing tunnel is already running:

   ```powershell
   Get-NetTCPConnection -LocalPort 15433 -ErrorAction SilentlyContinue
   ```

   If the listener is an existing `ssh -N -L ... akasha-staging` process, keep it
   open and use DBeaver normally. Otherwise, stop the stale listener or choose a
   different local port such as `25433` and use that same port in DBeaver.

4. Create a DBeaver connection:

   | Field | Value |
   |---|---|
   | Connection name | `Akasha Coolify PostGIS` |
   | Host | `localhost` |
   | Port | `15433` |
   | Database | `POSTGRES_DB` from the Coolify service environment |
   | Username | `POSTGRES_USER` from the Coolify service environment |
   | Password | `POSTGRES_PASSWORD` from the Coolify service environment |

5. Prefer read-only browsing and run only safe inspection queries unless you are
   intentionally performing an operator task:

   ```sql
   SELECT current_database(), current_user;
   SELECT postgis_full_version();
   ```

If the container IP changes after a redeploy, rerun the `docker inspect` step and
restart the SSH tunnel. For team-wide access, prefer a dedicated read-only
Postgres role and a restricted SSH tunnel account over sharing broad admin
credentials.

## One-shot jobs

Run one-shot jobs from the Coolify terminal or container shell. Do not expose these services publicly.

App schema migration/verification from `api`.

The API image already runs `python -m app.cli db upgrade` on startup for the
current single-replica deployment model. Run these manually only for
repair/debug/verification from the Coolify terminal:

```bash
python -m app.cli db upgrade
python -m app.cli db verify-current
```

Catalog/storage seed and verification from `ingestion-worker`:

```bash
python worker.py seed
python worker.py verify
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km
```

## Scheduled Bhoonidhi ingestion

The provider-agnostic scheduler uses a systemd timer on the staging worker VM so
Bhoonidhi traffic comes from the whitelisted static IP and raw/work/ledger files
stay under `/srv/akasha`. The old source-specific Bhoonidhi timers were removed;
ResourceSat LISS-3, LISS-4, and AWiFS are scheduler-owned.

Install the scheduler artifacts:

```bash
infra/selfhosted/systemd/install-akasha-ingestion-scheduler.sh
```

Edit `/etc/akasha/ingestion-scheduler.env` for scheduler-wide defaults, canary
filters, `AKASHA_SCHEDULER_ACTIVE`, `AKASHA_SCHEDULER_DRY_RUN`, and
`AKASHA_SCHEDULER_APPROVED_RUNTIME`. `AKASHA_COMPOSE_FILE` and
`AKASHA_COMPOSE_PROJECT` can usually stay unset on Coolify hosts; the wrapper
auto-detects the rendered compose file and uses the existing local image with
`AKASHA_SYNC_PULL_POLICY=never`. The service uses a host-level `flock` at
`/srv/akasha/ingestion/scheduler.global.lock`; worker locks are canonical
`<source>.<aoi>.worker.lock` files in the scheduler lock directory, so overlapping
automatic/manual runs fail fast.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now akasha-ingestion-scheduler.timer
systemctl list-timers akasha-ingestion-scheduler.timer
journalctl -u akasha-ingestion-scheduler.service -n 200 --no-pager
```

The installer also accepts `--enable`, `--start`, and `--dry-run`. For the first
staging validation, keep `AKASHA_SCHEDULER_DRY_RUN=true`, then run
`sudo systemctl start akasha-ingestion-scheduler.service` and inspect the journal
before enabling live downloads. For a manual one-off/backfill window, use
`python scripts/staging_ingestion_job.py trigger --source ... --window-start ... --window-end ... --max-downloads ...`;
the staging runner invokes `worker.py schedule-source --approved-runtime --manual`.

For additional AOIs, set `AOI_CONFIG_DIR` to a directory containing one GeoJSON
file per AOI, using filenames such as `mysore-60km.geojson`, then pass the
matching id to ingestion commands:

```bash
python worker.py bhoonidhi-search --source resourcesat-2a-liss3-boa --aoi mysore-60km --aoi-dir /app/data/seed/aois
python worker.py build-composite --source resourcesat-2a-liss3-boa --aoi mysore-60km --aoi-dir /app/data/seed/aois --window-start 2026-03-01 --window-end 2026-03-31
```

EOS-04 and NISAR SAR sources are registered as gated context layers until a validated native
operator-download/prep workflow is available. The `ingestion-sar` service still contains the legacy
Sentinel-1 regression path; use `docs/archive/sentinel-1-grd-cog-prep-runbook.md` only for that explicit
legacy workflow, not for production ISRO SAR onboarding.

## Orchestrator scheduler ownership

`akasha-ingestion-scheduler.timer` is the single orchestrator timer that replaces timer-per-source
growth with one bounded due-source check. Rollback means pausing the scheduler and using bounded
manual `schedule-source` jobs through `scripts/staging_ingestion_job.py` while the issue is
investigated.

Install the scheduler artifacts (Phase 8):

```bash
infra/selfhosted/systemd/install-akasha-ingestion-scheduler.sh
```

Edit `/etc/akasha/ingestion-scheduler.env` for scheduler-wide defaults (cadence, max concurrent
sources, dry-run/canary flags, stale-lock TTL, and source/AOI ownership notes). The scheduler starts
with `AKASHA_SCHEDULER_ACTIVE=false` and `AKASHA_SCHEDULER_DRY_RUN=true`.

### One-owner rule

Every source/AOI must have exactly one active owner at all times. Do not force an ad hoc manual
scheduler job while an automatic scheduler job is in-flight for the same source/AOI. Both paths use
the same worker lock directory.

| Source/AOI | Current scheduler state |
|---|---|
| `resourcesat-2a-liss3-boa` / `bangalore-60km` | `scheduler_active` |
| `resourcesat-2a-liss4-mx70-l2` / `bangalore-60km` | `scheduler_active` |
| `resourcesat-2a-awifs-boa` / `bangalore-60km` | `scheduler_active` (regional/coarse; 60% minimum usable coverage) |

### Canary flow

1. Install the scheduler timer with the default `AKASHA_SCHEDULER_ACTIVE=false` and
   `AKASHA_SCHEDULER_DRY_RUN=true`.

   ```bash
   infra/selfhosted/systemd/install-akasha-ingestion-scheduler.sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now akasha-ingestion-scheduler.timer
   systemctl list-timers akasha-ingestion-scheduler.timer
   ```

2. Let the scheduler run one dry-run cycle. Inspect the journal and monitoring pages:

   ```bash
   journalctl -u akasha-ingestion-scheduler.service -n 200 --no-pager
   ```

3. Validate that the schedule plan shows the correct due decisions, lock paths, and next windows
   for all registered sources.
4. Switch the scheduler to live mode for one source/AOI canary
   (`AKASHA_SCHEDULER_DRY_RUN=false`, `AKASHA_SCHEDULER_MAX_CONCURRENT_SOURCES=1`). Let one capped
   real job complete and confirm the output (composites, STAC items, ledger entries).
5. Widen the source list and run budget only after the canary is clean.

### Rollback / pause automatic scheduling

If the scheduler shows unexpected behavior for any source/AOI, pause it immediately:

1. Stop and disable the orchestrator scheduler timer:

   ```bash
   sudo systemctl stop akasha-ingestion-scheduler.timer akasha-ingestion-scheduler.service
   sudo systemctl disable akasha-ingestion-scheduler.timer
   ```

2. Confirm no scheduler job is queued or running for the affected source/AOI:

   ```bash
   journalctl -u akasha-ingestion-scheduler.service --since "1 hour ago" --no-pager
   ```

3. Use bounded manual runs only when needed:

   ```bash
   python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --dry-run
   ```

4. Run monitoring/doctor checks before re-enabling the scheduler timer:

   ```bash
   python scripts/staging_ingestion_job.py doctor --host akasha-staging
   ```

## Centralized ad hoc ingestion jobs

Phase 5 adds a restricted staging-side job wrapper for team-triggered ingestion without granting
interactive SSH shells or moving raw provider archives to laptops. Install these artifacts on the
staging worker VM:

```bash
infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh --dry-run
infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh
```

The installer copies the wrappers to `/opt/akasha/bin/`, preserves an existing
`/etc/akasha/ingestion-jobs.env`, and creates `/srv/akasha/ingestion/jobs` for durable
`request.json`, `status.json`, `command.txt`, `job.log`, and `result.json` files. Keep
`/etc/akasha/ingestion-jobs.env` on the VM only. It controls the job root, allowed sources/AOIs,
default download caps, retention, Coolify Compose discovery overrides, raw/work roots, ledger path,
and pull policy:

```text
AKASHA_INGESTION_JOB_ROOT=/srv/akasha/ingestion/jobs
AKASHA_INGESTION_ALLOWED_SOURCES=resourcesat-2a-liss3-boa,resourcesat-2a-liss4-mx70-l2,resourcesat-2a-awifs-boa
AKASHA_INGESTION_ALLOWED_AOIS=bangalore-60km
AKASHA_INGESTION_DEFAULT_MAX_DOWNLOADS=3
AKASHA_SYNC_RAW_ROOT=/srv/akasha/data/raw/bhoonidhi
AKASHA_SYNC_TEMP_ROOT=/srv/akasha/data/work/bhoonidhi
AKASHA_SYNC_LEDGER_PATH=/srv/akasha/ingestion/ledger.sqlite
AKASHA_SYNC_PULL_POLICY=never
```

Restrict job access to an OS group instead of general shell users:

```bash
sudo groupadd --system akasha-ingesters
sudo usermod -aG akasha-ingesters <developer-linux-user>
sudo chgrp -R akasha-ingesters /srv/akasha/ingestion/jobs
sudo chmod 2750 /srv/akasha/ingestion/jobs
```

For each approved team SSH key, use a forced-command `authorized_keys` line. The forced command
validates `doctor`, `start`, `status`, `logs`, `list`, `retry`, `validate`, and `prune`, then execs
only the job wrapper:

```text
command="/opt/akasha/bin/akasha-ingestion-forced-command.sh",restrict ssh-ed25519 <team-public-key> <developer>
```

On each developer machine, add an SSH alias named `akasha-staging`:

```sshconfig
Host akasha-staging
  HostName <staging-host>
  User <developer-linux-user>
  IdentityFile ~/.ssh/<developer-key>
```

Then run the local Windows/Linux/macOS-safe CLI from the repository root. Use the placeholder host
`akasha-staging`; do not put secrets in commands, notes, or docs.

```bash
# Check local SSH/Docker plus the remote wrapper, Compose discovery, env, and writable job root.
python scripts/staging_ingestion_job.py doctor --host akasha-staging

# Rehearse the request without downloading provider data.
python scripts/staging_ingestion_job.py trigger --host akasha-staging \
  --source resourcesat-2a-liss3-boa --aoi bangalore-60km --dry-run --wait

# Run one capped real ingestion job and wait for a terminal state.
python scripts/staging_ingestion_job.py trigger --host akasha-staging \
  --source resourcesat-2a-liss3-boa --aoi bangalore-60km \
  --max-downloads 1 --wait

# Inspect progress and logs.
python scripts/staging_ingestion_job.py status <job_id> --host akasha-staging
python scripts/staging_ingestion_job.py logs <job_id> --host akasha-staging --follow

# Retry a failed job with the same request and a new job id.
python scripts/staging_ingestion_job.py retry <job_id> --host akasha-staging \
  --overwrite --force-upload --notes "retry after operator review"

# Validate remote composite output, then pull only final prepared artifacts locally.
python scripts/staging_ingestion_job.py validate <job_id> --host akasha-staging
python scripts/staging_ingestion_job.py sync-local <job_id> --host akasha-staging \
  --import-local --verify-local
```

`sync-local` delegates to `scripts/sync_staging_raster_bundle.py`: it reads the job result and opens
a non-interactive tar stream for the selected final bundle under the staging raster work root. If a
developer key is forced-command-only for job subcommands, provision an approved artifact-sync SSH
path or a separate SSH alias for `sync-local`; do not grant broader access than final
`analytic.tif`, `mask.tif`, and `prepare_manifest.json` bundle reads.

Ad hoc jobs and scheduled sync share collision protection. The job wrapper rejects another
`queued`/`running` job for the same `(source, AOI)`, and the runner also uses the Bhoonidhi worker
lock used by the scheduled timer. A collision exits as `blocked_by_lock`; wait for the timer or
other developer job to finish, then run `retry <job_id>`.

To roll back the ad hoc job wrappers, remove the forced-command lines from `authorized_keys`, then
run:

```bash
infra/selfhosted/systemd/install-akasha-ingestion-jobs.sh --uninstall
```

`--uninstall` removes `/opt/akasha/bin/akasha-ingestion-job*.sh` and
`/opt/akasha/bin/akasha-ingestion-forced-command.sh`; it intentionally keeps
`/etc/akasha/ingestion-jobs.env` and `/srv/akasha/ingestion` job/data artifacts for audit and
manual cleanup.

## Rollback

1. Pick a previous known-good Git SHA image tag.
2. Set `IMAGE_TAG` in Coolify to that exact SHA, or run the production/staging workflow with that exact SHA when supported.
3. Redeploy the same Compose stack.
4. Rerun smoke checks and private-port checks.

## Production promotion

Production is created only after staging acceptance passes. The production workflow requires manual GitHub Environment approval and accepts an explicit `image_tag`. It does not build images.

Use only the exact Git SHA tag already validated in staging.
