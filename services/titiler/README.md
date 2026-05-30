# `services/titiler` — TiTiler (raster display tiles)

Serves RGB display tiles (and optional index *display* overlays in Wave 2) from
Cloud-Optimized GeoTIFFs stored in MinIO. **Private service** — reached only
through the gateway at same-origin `/tiles/*`.

- Image: `ghcr.io/developmentseed/titiler:1.0.0` (rio-tiler 8.x).
- Internal port: `8000`. Health: `GET /healthz`.
- MinIO/S3 access via GDAL env vars (see `.env.example`).

> **Not** used for masked statistics. Vanilla TiTiler `/cog/statistics` takes a
> single `url` and cannot apply a categorical SCL mask from a second COG, so the
> BFF computes masked index statistics with rasterio/rio-tiler (Slice 2).

Slice 0 provides only the pinned image + env contract. Mosaics, COG layout, and
index expressions are added in Slice 2.
