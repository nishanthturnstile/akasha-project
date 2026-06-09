# Railway deployment — per-service configuration

This folder documents how the monorepo maps onto **separate Railway services**
(the recommended production shape). Do **not** deploy the local Compose file as a
single production appliance.

## Service → config matrix

| Railway service | Root directory | Config file | Build | Health | Public? | Volume |
|---|---|---|---|---|---:|---:|
| `web` | repo root | `/railway.json` | `infra/gateway/Dockerfile` | `/health` | **yes** | no |
| `api` | `apps/api` | `apps/api/railway.json` | `Dockerfile` | `/health` | no | no |
| `titiler` | `services/titiler` | `services/titiler/railway.json` | `Dockerfile` | `/healthz` | no | no |
| `stac-api` | `services/stac-api` | `services/stac-api/railway.json` | `Dockerfile` | `/_mgmt/ping` | no | no |
| `postgis` | image-based | — | `postgis/postgis:16-3.5` | `pg_isready` | no | **yes** |
| `minio` | image-based | — | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | `/minio/health/live` | no | **yes** |
| `ingestion-worker` | repo root | `services/ingestion/railway.json` | `services/ingestion/Dockerfile` | n/a (worker) | no | optional temp |

> `ingestion-worker` builds from the repository root so the committed
> `data/seed` assets are included in the image. Set its Railway **Root
> Directory = repository root**.

`postgis` and `minio` are added as **image-based** Railway services (no custom
Dockerfile) with persistent volumes attached.

## Public endpoint rule

Only the `web` gateway gets a public domain. The browser calls `/api/*` and
`/tiles/*` on that same public origin; the gateway proxies to the internal
`api` and `titiler` services. FastAPI, TiTiler, STAC API, PostGIS, and MinIO are
never given a public domain.

## Private networking

Use Railway private domains / reference variables for internal calls
(`*.railway.internal`). See [`ENV_MATRIX.md`](./ENV_MATRIX.md). Use one
canonical name per concept; do not add aliases.

## Deployment sequence (summary)

1. Push the monorepo to GitHub.
2. Create a Railway project.
3. Add `postgis` (persistent volume).
4. Add `minio` (persistent volume, private only; `MINIO_BROWSER=off`).
5. Add `api` and run the app-schema upgrade once PostGIS is up:
   `python -m app.cli db upgrade` (creates PostGIS/pgcrypto extensions and API-owned `akasha` tables).
6. Add `stac-api`.
7. Add `titiler` (GDAL S3/MinIO vars).
8. Add `web` as the only public service.
9. Configure health checks for `web`, `api`, `titiler`, `stac-api`.
10. Run the catalog + storage seed from `ingestion-worker` (idempotent):
    `python worker.py seed` (pgSTAC migrate → load collection/item → MinIO bucket/keys).
11. Verify the Slice 1 exit criteria: `python worker.py verify`
    (PostGIS `postgis_version()`, STAC `sentinel-2-l2a` collection, MinIO bucket reachable).
12. (Slices 1–2) Replace MinIO placeholder keys with operator-provided COGs.
13. Run `scripts/smoke-test.py` against the public web URL.

### Slice 1 exit criteria

```bash
# (1) PostGIS
python -m app.cli check                       # prints postgis_version() + app schema status
# (2) STAC collection + (3) MinIO bucket
python worker.py verify                        # all three checks in one command
```

## PostgreSQL/PostGIS note

pgSTAC requires PostgreSQL with PostGIS. Verify after provisioning:

```sql
SELECT postgis_version();
```

Proceed with pgSTAC migrations only after PostGIS is confirmed (Slice 1).

## Security guardrails

- No default credentials. Rotate generated DB/MinIO secrets.
- Keep the MinIO console disabled/private (`MINIO_BROWSER=off`).
- Public demos only with non-sensitive seed data unless `GATEWAY_BASIC_AUTH`
  (or an equivalent edge gate) is enabled.
