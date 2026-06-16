# Akasha STAC API service — Slice 0 (skeleton).
#
# Catalog collections/items, date/source discovery, asset metadata.
# Backed by pgSTAC in the PostGIS service.
#
# Health endpoint: GET /_mgmt/ping (built into stac-fastapi-pgstac 5.0.2).
FROM ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2

# stac-fastapi reads its bind host/port from APP_HOST/APP_PORT. Pin to 8080 to
# match http://stac-api:8080. Database connection vars
# (POSTGRES_HOST_READER/WRITER/PORT/USER/PASS/DBNAME) are supplied via env.
ENV APP_HOST=0.0.0.0 \
    APP_PORT=8080

# Internal service. Referenced as http://stac-api:8080.
EXPOSE 8080

# pgSTAC schema migrations are run during Slice 1 (database/catalog foundation),
# not in this skeleton. The base image's default entrypoint serves the app.
