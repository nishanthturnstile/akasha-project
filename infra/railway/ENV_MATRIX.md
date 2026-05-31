# Railway environment matrix (placeholders only)

Verbatim variable names per service from the deployment guide. **Do not add
aliases** such as `API_ORIGIN`, `API_INTERNAL_URL`, `TITILER_ORIGIN`,
`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, or `PGSTAC_*`.

## `web` (gateway) — the only public service

```text
PUBLIC_APP_NAME=Akasha
PUBLIC_DEFAULT_AOI_NAME=Bangalore
API_UPSTREAM_URL=http://api.railway.internal:8000
TITILER_UPSTREAM_URL=http://titiler.railway.internal:8000
VITE_BASEMAP_STYLE_URL=<operator-provided MapLibre style URL>
GATEWAY_BASIC_AUTH=            # empty=off; set "user:pass" to gate the demo
```

## `api`

```text
APP_ENV=production
DATABASE_URL=postgresql://...
STAC_API_URL=http://stac-api.railway.internal:8080
TITILER_URL=http://titiler.railway.internal:8000
DEFAULT_SOURCE_ID=sentinel-2-l2a
DEFAULT_AOI_ID=bangalore
USABLE_PIXEL_THRESHOLD_PERCENT=70
MAX_POLYGON_AREA_HA=50
MAX_POLYGON_VERTICES=5000
INDEX_REQUEST_TIMEOUT_SECONDS=30
RATE_LIMIT_INDEX_PER_MINUTE=30
MAX_REQUEST_BODY_BYTES=1048576
CORS_ALLOWED_ORIGINS=https://<web-public-domain>
```

## `titiler`

```text
PORT=8000
AWS_ACCESS_KEY_ID=<minio-access-key>
AWS_SECRET_ACCESS_KEY=<minio-secret-key>
AWS_S3_ENDPOINT=minio.railway.internal:9000     # no scheme; GDAL uses AWS_HTTPS
AWS_VIRTUAL_HOSTING=FALSE
AWS_HTTPS=NO
AWS_REGION=us-east-1
GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff
```

## `stac-api` (stac-fastapi-pgstac REAL var names)

```text
POSTGRES_HOST_READER=postgis.railway.internal
POSTGRES_HOST_WRITER=postgis.railway.internal
POSTGRES_PORT=5432
POSTGRES_USER=<user>
POSTGRES_PASS=<password>
POSTGRES_DBNAME=<db>
```

## `postgis`

```text
POSTGRES_USER=<generated>
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=<db>
```

## `minio`

```text
MINIO_ROOT_USER=<generated-user>
MINIO_ROOT_PASSWORD=<generated-password>
MINIO_BROWSER=off
MINIO_SERVER_URL=http://minio.railway.internal:9000
```

## `ingestion-worker`

```text
DATABASE_URL=postgresql://...
STAC_API_URL=http://stac-api.railway.internal:8080
S3_ENDPOINT_URL=http://minio.railway.internal:9000
S3_ACCESS_KEY=<access-key>
S3_SECRET_KEY=<secret-key>
AOI_CONFIG_PATH=/app/config/aoi/bangalore.geojson
# CDSE_CLIENT_ID / CDSE_CLIENT_SECRET only when Wave 2 automated ingestion is built
```
