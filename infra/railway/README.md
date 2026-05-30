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
| `stac-api` | `services/stac-api` | `services/stac-api/railway.json` | `Dockerfile` | `/_mgmt/health` | no | no |
| `postgis` | image-based | — | `postgis/postgis:16-3.5` | `pg_isready` | no | **yes** |
| `minio` | image-based | — | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | `/minio/health/live` | no | **yes** |
| `ingestion-worker` | `services/ingestion` | `services/ingestion/railway.json` | `Dockerfile` | n/a (worker) | no | optional temp |

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
4. Add `minio` (persistent volume, private only).
5. Add `stac-api` (run pgSTAC/STAC migrations — Slice 1).
6. Add `titiler` (GDAL S3/MinIO vars).
7. Add `api` (database/STAC/TiTiler vars).
8. Add `web` as the only public service.
9. Configure health checks for `web`, `api`, `titiler`, `stac-api`.
10. Seed COGs + STAC items (Slices 1–2).
11. Run `scripts/smoke-test.py` against the public web URL.

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
