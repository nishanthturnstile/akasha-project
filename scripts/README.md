# `scripts`

| Script | Purpose | Needs Docker? |
|---|---|---|
| `validate_slice0.py` | Static validation of all Slice 0 skeleton artifacts (files, pinned images, compose structure, health-check wiring, railway configs, env-secret hygiene). | No |
| `smoke-test.py` | Hits the live health/skeleton endpoints in order. Future-slice checks are listed as SKIPPED. | No (needs a running gateway/api) |
| `download_sentinel2_l2a_product.py` | Searches CDSE `sentinel-2-l2a` and downloads a complete native L2A SAFE ZIP containing the bands/SCL needed for Slice 2 COG preparation. | No |
| `prepare_sentinel2_l2a_cogs.py` | Converts a downloaded Sentinel-2 L2A SAFE ZIP into Akasha Slice 2 `analytic.tif` and `scl.tif` COGs. | No, but run via ingestion Docker image to avoid local GDAL setup |

## Run

```bash
# Static artifact validation (works in any environment)
python scripts/validate_slice0.py

# Smoke test against a running stack (local Docker Compose default :8080)
python scripts/smoke-test.py http://localhost:8080

# ...or against the deployed public web URL
python scripts/smoke-test.py https://<web-public-domain>

# Dry-run Sentinel-2 L2A candidate discovery for Slice 2 inputs
python scripts/download_sentinel2_l2a_product.py --bbox-preset bengaluru-install

# Download the selected full L2A SAFE ZIP; credentials come from ignored .env,
# CDSE_* environment variables, or the terminal prompt.
python scripts/download_sentinel2_l2a_product.py --bbox-preset bengaluru-install --download --yes --prompt-credentials

# Build the Slice 2 analytic + SCL COGs from the downloaded SAFE ZIP.
# Recommended on Windows: run inside the ingestion image with pinned raster deps.
docker compose -f infra/docker/docker-compose.yml build ingestion-worker
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_sentinel2_l2a_cogs.py --overwrite
```

`smoke-test.py` uses only the Python standard library. `validate_slice0.py`
requires `pyyaml`.
