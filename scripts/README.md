# `scripts`

| Script | Purpose | Needs Docker? |
|---|---|---|
| `validate_slice0.py` | Static validation of Slice 0 skeleton artifacts: files, pinned images, compose structure, health-check wiring, and env-secret hygiene. | No |
| `validate_slice1.py` | Static validation of Slice 1 storage/catalog artifacts using ResourceSat LISS-3 seed STAC, AOI seeds, PostGIS schema, MinIO layout, and ingestion CLI wiring. | No |
| `validate_slice2.py` | Static + synthetic validation of Slice 2 raster de-risk: seed metadata, BFF raster package, deps/infra, pure-numpy NDVI reference, TestClient endpoint contracts, and a synthetic dual-COG read-to-stat pipeline when rasterio is installed. | No |
| `smoke-test.py` | Hits a live gateway/API health path plus ResourceSat source/date/layer/statistics contracts. With `--login`, also verifies the operator imagery-source monitoring contract; add `--require-monitoring-clean` to fail on storage errors, zero-byte COG objects, stale active sources, missing active field composites, low coverage, or tile-unavailable dates. Real tile/stat failures are reported as blocked when COGs or backing services are unavailable. | No, but needs a running gateway/API |
| `prepare_resourcesat_liss3_boa_cogs.py` | Converts Bhoonidhi ResourceSat-2A LISS-3 BOA ZIPs into Akasha `analytic.tif` and provisional `mask.tif` COGs; manifest mode writes `data/seed/rasters/resourcesat-2a-liss3-boa/scene/{date}/{sceneComponent}/`. | No, but run via the ingestion Docker image to avoid local GDAL setup |
| `prepare_context_cog.py` | Converts a licensed operator-provided visual/context GeoTIFF (for example Cartosat-3) into a source-scoped COG + `prepare_manifest.json` for `ingest-manifest`. | No, but run via the ingestion Docker image to avoid local GDAL setup |
| `download_sentinel2_l2a_product.py` | Legacy Sentinel-2 L2A download helper retained for regression and migration reference. Not part of the production ResourceSat default workflow. | No |
| `prepare_sentinel2_l2a_cogs.py` | Legacy Sentinel-2 L2A COG preparation helper retained for regression and migration reference. Not part of the production ResourceSat default workflow. | No, but run via the ingestion Docker image if used |

## Run

```bash
# Static artifact validation
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py

# Smoke test against a running local gateway or deployed public web URL.
python scripts/smoke-test.py http://localhost:8080
python scripts/smoke-test.py https://<web-public-domain>
AKASHA_SMOKE_USERNAME=<username> AKASHA_SMOKE_PASSWORD=<password> \
  python scripts/smoke-test.py https://<web-public-domain> --login
AKASHA_SMOKE_USERNAME=<username> AKASHA_SMOKE_PASSWORD=<password> \
  python scripts/smoke-test.py https://<web-public-domain> --login --require-monitoring-clean

# Search Bhoonidhi for ResourceSat LISS-3 BOA products for the configured AOI.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py bhoonidhi-search --source resourcesat-2a-liss3-boa --aoi bangalore-60km

# Download products selected by the Bhoonidhi coverage manifest.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py bhoonidhi-download --source resourcesat-2a-liss3-boa

# Build ResourceSat LISS-3 analytic + provisional mask COGs.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python scripts/prepare_resourcesat_liss3_boa_cogs.py \
  --selection-manifest data/work/bhoonidhi/resourcesat-2a-liss3-boa/download_manifest.json \
  --overwrite

# Upload/register prepared COGs and verify object-store metadata.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py ingest-manifest --method upsert
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py verify-manifest-cogs
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item

# Prepare and register a licensed manual Cartosat/context GeoTIFF.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py prepare-context-cog \
  --source cartosat-3-gated \
  --input /srv/akasha/data/raw/cartosat/CARTOSAT3_ORDER_42.tif \
  --product-id CARTOSAT3_ORDER_42 \
  --acquisition-datetime 2026-04-16T05:30:00Z
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py ingest-manifest --collection-id cartosat-3-gated --method upsert
```

`smoke-test.py` uses only the Python standard library. `validate_slice0.py`
requires `pyyaml`. `validate_slice2.py` runs fully on static + numpy-only
checks; its synthetic dual-COG E2E section runs only when `rasterio`/`pyproj`
are installed.
