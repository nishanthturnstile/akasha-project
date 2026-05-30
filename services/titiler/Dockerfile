# Akasha TiTiler service — Slice 0 (skeleton).
#
# RGB display tiles + optional index *display* overlays from COGs in MinIO.
# Masked statistics are computed by the BFF (api), NOT here.
#
# Pinned (engineering-dos-donts.md): pin GDAL/rasterio/rio-tiler/TiTiler.
# TiTiler 1.0.0 pairs with rio-tiler 8.x. Health endpoint: GET /healthz.
FROM ghcr.io/developmentseed/titiler:1.0.0

# GDAL S3 / MinIO access is configured entirely via environment variables
# (see .env.example and infra/docker/docker-compose.yml). No custom
# expressions/extensions in Slice 0; raster wiring lands in Slice 2.

# Internal service. Referenced as http://titiler.railway.internal:8000.
EXPOSE 8000

# The base image already defines an entrypoint that serves titiler.application
# on port 8000 with a /healthz route. We keep the default CMD.
