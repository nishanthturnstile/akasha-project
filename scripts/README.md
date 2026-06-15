# `scripts`

| Script | Purpose | Needs Docker? |
|---|---|---|
| `validate_slice0.py` | Static validation of all Slice 0 skeleton artifacts (files, pinned images, compose structure, health-check wiring, railway configs, env-secret hygiene). | No |
| `validate_slice1.py` | Static validation of Slice 1 storage/catalog artifacts (PostGIS schema, STAC seeds, MinIO layout, ingestion CLI). | No |
| `validate_slice2.py` | Static + **synthetic** validation of Slice 2 (Phase 2 raster de-risk): scene/STAC metadata, BFF raster package, deps/infra, a pure-numpy NDVI reference, in-process TestClient endpoint contracts, and a full synthetic dual-COG read→mask→stat pipeline (when rasterio is installed). Lists the runtime tile/stat checks that are BLOCKED until operator COGs are in MinIO. | No |
| `smoke-test.py` | Hits the live health/skeleton + Phase 2 product endpoints in order. The RGB-tile and statistics steps are reported as BLOCKED (not failed) when real COGs/MinIO/TiTiler are unavailable. | No (needs a running gateway/api) |
| `download_sentinel2_l2a_product.py` | Searches CDSE `sentinel-2-l2a`, writes dry-run coverage manifests, and downloads complete native L2A SAFE ZIPs containing the bands/SCL needed for COG preparation. | No |
| `prepare_sentinel2_l2a_cogs.py` | Converts downloaded Sentinel-2 L2A SAFE ZIPs into Akasha `analytic.tif` and `scl.tif` COGs; manifest mode writes `data/seed/rasters/{date}/{mgrsTile}/`. | No, but run via ingestion Docker image to avoid local GDAL setup |
| `prepare_resourcesat_liss3_boa_cogs.py` | Converts Bhoonidhi ResourceSat-2A LISS-3 BOA ZIPs into Akasha `analytic.tif` and provisional `mask.tif` COGs; manifest mode writes `data/seed/rasters/resourcesat-2a-liss3-boa/scene/{date}/{sceneComponent}/`. | No, but run via ingestion Docker image to avoid local GDAL setup |

See [`../docs/sentinel-2-l2a-cog-prep-runbook.md`](../docs/sentinel-2-l2a-cog-prep-runbook.md) for the full SAFE ZIP → analytic/SCL COG runbook, validation checks, and cleanup steps.

## Run

```bash
# Static artifact validation (works in any environment)
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py   # Phase 2: static + synthetic NDVI de-risk

# Smoke test against a running stack (local Docker Compose default :8080)
python scripts/smoke-test.py http://localhost:8080

# ...or against the deployed public web URL
python scripts/smoke-test.py https://<web-public-domain>

# Dry-run Sentinel-2 L2A coverage discovery for production-like inputs.
# Default is dry-run and uses the implemented 2026 date-range default.
python scripts/download_sentinel2_l2a_product.py --bbox-preset south-india-target --max-items 100

# Download all coverage-selected full L2A SAFE ZIPs explicitly.
python scripts/download_sentinel2_l2a_product.py --bbox-preset south-india-target --max-items 100 --download-selected --yes --prompt-credentials

# Build analytic + SCL COGs from the downloaded SAFE ZIPs.
# Recommended on Windows: run inside the ingestion image with pinned raster deps.
docker compose -f infra/docker/docker-compose.yml build ingestion-worker
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_sentinel2_l2a_cogs.py --selection-manifest data/raw/sentinel-2-l2a/coverage_manifest.json --overwrite

# Build ResourceSat LISS-3 analytic + provisional mask COGs from a Bhoonidhi download manifest.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_resourcesat_liss3_boa_cogs.py --selection-manifest data/work/bhoonidhi/resourcesat-2a-liss3-boa/download_manifest.json --overwrite

# Upload/register prepared COGs and verify object-store metadata.
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py ingest-manifest --method upsert
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify-manifest-cogs
```

`smoke-test.py` uses only the Python standard library. `validate_slice0.py`
requires `pyyaml`. `validate_slice2.py` runs fully on its static + numpy-only
checks; its synthetic dual-COG E2E section runs only when `rasterio`/`pyproj`
are installed (otherwise it is skipped, since that path is covered on Railway).
