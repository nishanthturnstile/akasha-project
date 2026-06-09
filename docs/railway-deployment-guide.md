# Railway Deployment Guide

## Deployment position

The original product direction was on-prem first. For the MVP, deploy to Railway to accelerate code generation, demos, and iteration. Keep all services Docker-compatible so the same architecture can later move to Docker Compose/on-prem without redesign.

Railway supports multi-service projects, Dockerfile-based services, environment variables, private networking, public domains, health checks, volumes, logs/metrics, cron jobs, and database services. Railway can import Docker Compose files and can use Docker Compose for local development flows, but the recommended production shape for this app is **separate Railway services**, not one monolithic Compose runtime.

## Recommended Railway topology

| Railway service | Runtime | Public? | Persistent volume? | Purpose |
|---|---|---:|---:|---|
| `web` | Single container: static React + Caddy reverse proxy | Yes | No | Serve built React app and proxy `/api` to `api` and `/tiles` to `titiler` as one public service. Source stays in `apps/frontend` + `infra/gateway`. |
| `api` | FastAPI container | No | No | App APIs, plot CRUD, STAC lookup, index orchestration. |
| `titiler` | Custom TiTiler container | No | No | COG tiles and statistics. |
| `stac-api` | stac-fastapi-pgstac container | No | No | STAC collections/items/search. |
| `postgis` | Custom `postgis/postgis`-based container or Railway Postgres if PostGIS is verified | No | Yes | pgSTAC catalog and app plot storage. |
| `minio` | MinIO container | No | Yes | S3-compatible COG object storage. |
| `ingestion-worker` | Python worker | No | Optional temp only | Manual seed commands first; scheduled ingestion later. |

### Public endpoint rule

Only the `web` (gateway) service is publicly reachable. The browser calls `/api/*` and `/tiles/*` on the same public origin; the gateway proxies them to the internal `api` and `titiler` services. FastAPI, TiTiler, STAC API, PostGIS, and MinIO are never given a public domain.

## Repository layout for Railway-friendly generation

Recommended monorepo structure:

```text
apps/
  frontend/          React + Vite + MapLibre app
  api/               FastAPI BFF
services/
  titiler/           Custom TiTiler image/config/extensions
  stac-api/          stac-fastapi-pgstac wrapper/config
  ingestion/         Python ingestion worker
infra/
  gateway/           Caddy/Nginx config and Dockerfile
  railway/           deployment notes and per-service examples
  docker/            local compose files for development/on-prem portability
docs/                product, architecture, data, deployment context
```

Each Railway code service should have an explicit Dockerfile and health endpoint where possible.

## Service configuration

### Health checks

Use Railway health checks for all HTTP services: `web` GET `/health` 200; `api` GET `/health` 200; `titiler` GET `/healthz`; `stac-api` uses its built-in health route. Add `/health` to `web` and `api` before configuring Railway health checks.

Example `railway.json` pattern for a `/health` service:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "healthcheckPath": "/health",
    "restartPolicyType": "ALWAYS"
  }
}
```

For TiTiler, configure Railway to use `/healthz`. For `stac-api`, configure Railway to use its built-in health route.

### Volumes

Attach persistent Railway volumes to:

- `postgis`: database data directory.
- `minio`: object storage data directory.

Do not store COGs or database state in ephemeral container filesystems.

### Private networking

Use Railway private service domains/reference variables for internal calls. Configure app variables with `*.railway.internal` URLs, not public domains, for service-to-service traffic. Use one canonical name per concept; do not add aliases beyond the environment matrix below.

## Required environment variables

```text
web (gateway):
  PUBLIC_APP_NAME=Akasha
  PUBLIC_DEFAULT_AOI_NAME=Bangalore
  API_UPSTREAM_URL=http://api.railway.internal:8000
  TITILER_UPSTREAM_URL=http://titiler.railway.internal:8000
  VITE_ESRI_API_KEY=<referrer-restricted ArcGIS Location Platform key with Basemaps privilege>
  VITE_ESRI_BASEMAP_STYLE=arcgis/imagery
  VITE_ESRI_BASEMAP_STYLE_FAMILY=arcgis
  VITE_ESRI_BASEMAP_PLACES=none
  VITE_ESRI_BASEMAP_SESSION_SECONDS=43200
  GATEWAY_BASIC_AUTH=            # empty=off; set "user:pass" to gate the demo

api:
  APP_ENV=production
  DATABASE_URL=postgresql://...
  STAC_API_URL=http://stac-api.railway.internal:8080
  TITILER_URL=http://titiler.railway.internal:8000
  DEFAULT_SOURCE_ID=sentinel-2-l2a
  DEFAULT_AOI_ID=bangalore
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
  CORS_ALLOWED_ORIGINS=https://<web-public-domain>
  AUTH_MODE=enabled
  AUTH_ALLOW_DISABLED=false
  AUTH_SESSION_COOKIE_NAME=akasha_session
  AUTH_SESSION_TTL_MINUTES=480
  AUTH_REMEMBER_TTL_DAYS=30
  AUTH_PASSWORD_PEPPER=<generated-secret>
  AUTH_ALLOW_BOOTSTRAP=false
  AUTH_BOOTSTRAP_TOKEN=<one-time-setup-secret>
  AUTH_COOKIE_SECURE=true
  AUTH_LOGIN_RATE_LIMIT_PER_MINUTE=10
  AUTH_BOOTSTRAP_RATE_LIMIT_PER_HOUR=5

titiler:
  AWS_ACCESS_KEY_ID=<minio-access-key>
  AWS_SECRET_ACCESS_KEY=<minio-secret-key>
  AWS_S3_ENDPOINT=minio.railway.internal:9000     # no scheme; GDAL uses AWS_HTTPS
  AWS_VIRTUAL_HOSTING=FALSE
  AWS_HTTPS=NO
  AWS_REGION=us-east-1
  GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff

stac-api (stac-fastapi-pgstac REAL var names):
  POSTGRES_HOST_READER=postgis.railway.internal
  POSTGRES_HOST_WRITER=postgis.railway.internal
  POSTGRES_PORT=5432
  POSTGRES_USER=<user>
  POSTGRES_PASS=<password>
  POSTGRES_DBNAME=<db>

postgis:
  POSTGRES_USER=<generated>
  POSTGRES_PASSWORD=<generated>
  POSTGRES_DB=<db>

minio:
  MINIO_ROOT_USER=<generated-user>
  MINIO_ROOT_PASSWORD=<generated-password>
  MINIO_BROWSER=off
  MINIO_SERVER_URL=http://minio.railway.internal:9000

ingestion-worker:
  DATABASE_URL=postgresql://...
  STAC_API_URL=http://stac-api.railway.internal:8080
  S3_ENDPOINT_URL=http://minio.railway.internal:9000
  S3_ACCESS_KEY=<access-key>
  S3_SECRET_KEY=<secret-key>
  AOI_CONFIG_PATH=/app/config/aoi/bangalore.geojson
  # CDSE_CLIENT_ID / CDSE_CLIENT_SECRET only when Wave 2 automated ingestion is built
```

Do not add aliases such as `API_ORIGIN`, `API_INTERNAL_URL`, `TITILER_ORIGIN`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, or `PGSTAC_*`.

## PostgreSQL/PostGIS choice

pgSTAC requires PostgreSQL with geospatial support. Prefer a custom PostGIS service if the selected Railway managed PostgreSQL option does not provide the required PostGIS extension/version.

Verification query after provisioning:

```sql
SELECT postgis_version();
```

Only proceed with pgSTAC migrations after PostGIS is confirmed.

## Deployment sequence

1. Push the generated monorepo to GitHub.
2. Create a Railway project.
3. Add `postgis` with a persistent volume.
4. Add `minio` with a persistent volume and private networking only.
5. Add `stac-api` and run pgSTAC/STAC migrations.
6. Add `titiler` with GDAL S3/MinIO variables.
7. Add `api` and configure database/STAC/TiTiler variables.
8. Add `web` as the only public service.
9. Configure health checks for `web`, `api`, `titiler`, and `stac-api`.
10. Upload/seed at least one Sentinel-2 analytic COG and SCL COG to MinIO.
11. Register STAC collection/items.
12. Run `scripts/smoke-test` with the ordered checks: `/health` of web+api+titiler+stac-api → `/api/config` → `/api/sources` → `/api/sources/{id}/dates` → `/api/layers/default` → one RGB tile returns a PNG → one `/api/indices/statistics` returns valid JSON with NDVI stats.

## Local development

Use Docker Compose locally to mirror the Railway services. Keep Compose as a local/on-prem portability artifact, not the only deployment definition.

Local development should support:

- frontend hot reload;
- API reload;
- private MinIO/PostGIS/TiTiler services;
- seed data ingestion;
- one-command reset for local volumes.

## Rate limiting and security

- Apply `MAX_REQUEST_BODY_BYTES=1048576` and `MAX_POLYGON_AREA_HA=50` in the BFF.
- Enforce `MAX_POLYGON_VERTICES=5000` for plot and index request geometries.
- Time out index/statistics work after `INDEX_REQUEST_TIMEOUT_SECONDS=30`.
- Rate-limit index/statistics endpoints with `RATE_LIMIT_INDEX_PER_MINUTE=30`.
- Accept GeoJSON Polygon and MultiPolygon in EPSG:4326 only. Reject self-intersecting or invalid rings with 422; holes are allowed. Compute area by projecting to Bangalore local UTM, EPSG:32643, before enforcing `MAX_POLYGON_AREA_HA`; do not trust client-supplied area.
- Return 429 for rate limits, 504 for index timeouts, and 502 for upstream TiTiler/STAC failures.
- Keep MinIO console disabled or private.
- Rotate generated database and MinIO credentials.
- Do not use default credentials in Railway templates.
- In-app username/password login is required for user-owned fields, activities, datasets, reports, notifications, and product/raster APIs. API deployments must use `AUTH_MODE=enabled`; disabled auth requires `AUTH_ALLOW_DISABLED=true`, is local/dev/test only, and fails closed on Railway/customer deployments.
- First-run `/api/auth/bootstrap` is off unless `AUTH_ALLOW_BOOTSTRAP=true`; production bootstrap also requires the caller to provide `AUTH_BOOTSTRAP_TOKEN`.
- Never use `CORS_ALLOWED_ORIGINS=*` with application auth. Set exact web origins because the BFF uses credentialed session cookies.
- `GATEWAY_BASIC_AUTH` remains an optional outer shared-secret gate for demos; it does not replace application authentication or per-team authorization.

## Appendix (not for MVP prompts)

### Railway caveats for this project

- Large COG files consume persistent volume quickly; monitor storage from day one.
- Preview environments should not duplicate full raster datasets.
- Raster statistics are CPU/I/O heavy; scale TiTiler and API separately if needed.
- Region choice affects latency between services; keep all services in the same region.
- If MinIO-on-Railway becomes operationally painful for large datasets, switch the object-storage abstraction to another S3-compatible target without changing frontend behavior.

### Post-smoke deployment notes

- Add custom domain/TLS after the smoke test passes.
- Do not add CDSE/Bhoonidhi secrets until automated ingestion is implemented.
