# Sentinel-2 L2A SAFE ZIP → Akasha analytic + SCL COG runbook

This runbook documents the repeatable Slice 2 raster-prep workflow we used to turn a complete Copernicus Sentinel-2 L2A SAFE product into the two COG assets Akasha needs:

```text
data/seed/rasters/{acquisitionDate}/analytic.tif
data/seed/rasters/{acquisitionDate}/scl.tif
```

These files are large operator-provided/generated rasters and are intentionally ignored by git.

## When to use this

Use this process when you need to unblock or reproduce the **Phase 2 — Raster de-risk milestone**:

1. Convert or place one analytic COG and one SCL COG.
2. Validate both COGs.
3. Upload/register them for TiTiler and masked-statistics testing.

Do **not** use the Sentinel-2 Global Mosaics path for this milestone. Global mosaics only provide a visual/NIR subset and do not include all Akasha analytic bands or SCL.

## Source product

Use a complete Sentinel-2 L2A product from Copernicus Data Space, downloaded by:

```bash
uv run python scripts/download_sentinel2_l2a_product.py --bbox-preset bengaluru-install --download --yes --prompt-credentials
```

The download script writes complete SAFE ZIPs under:

```text
data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip
```

The SAFE ZIP must contain at least these source assets:

| Akasha output | SAFE source asset |
|---|---|
| analytic band 1 `B04` | `B04_10m.jp2` |
| analytic band 2 `B08` | `B08_10m.jp2` |
| analytic band 3 `B05` | `B05_20m.jp2` |
| analytic band 4 `B06` | `B06_20m.jp2` |
| analytic band 5 `B07` | `B07_20m.jp2` |
| analytic band 6 `B11` | `B11_20m.jp2` |
| analytic band 7 `B12` | `B12_20m.jp2` |
| analytic band 8 `B03` | `B03_10m.jp2` |
| analytic band 9 `B02` | `B02_10m.jp2` |
| `scl.tif` | `SCL_20m.jp2` |

Recommended metadata files to keep available for later STAC/item updates:

- `MTD_MSIL2A.xml`
- tile metadata XML
- `manifest.safe`

## Why run through Docker

Run the COG prep inside the `ingestion-worker` image rather than directly on Windows. This avoids local GDAL/rasterio/JP2 dependency problems.

The ingestion image includes the Slice 2 raster-prep dependencies:

- `numpy`
- `rasterio`
- `rio-cogeo`
- `libexpat1` OS runtime package required by rasterio/GDAL wheels

## One-time image build

From the repository root:

```bash
docker compose -f infra/docker/docker-compose.yml build ingestion-worker
```

This builds the raster-enabled ingestion image. If this fails with a missing shared library, update `services/ingestion/Dockerfile` rather than installing GDAL manually on Windows.

## Run the COG preparation

From the repository root:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_sentinel2_l2a_cogs.py --overwrite
```

By default, the script:

1. Finds the newest `*.SAFE.zip` under `data/raw/sentinel-2-l2a/`.
2. Infers the acquisition date from the SAFE product name.
3. Extracts the SAFE ZIP to `data/work/sentinel-2-l2a/`.
4. Uses `B04_10m` as the 10 m reference grid.
5. Builds a 9-band `uint16` analytic intermediate in frozen Akasha order.
6. Resamples continuous 20 m bands to 10 m using bilinear resampling.
7. Resamples SCL to 10 m using nearest-neighbour resampling.
8. Translates both intermediates to COGs with internal overviews.
9. Validates both COGs using `rio-cogeo`.
10. Writes `prepare_manifest.json`.
11. Removes temporary intermediate files unless `--keep-intermediate` is supplied.

To process a specific product or output date:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_sentinel2_l2a_cogs.py \
  --zip-path data/raw/sentinel-2-l2a/<PRODUCT_ID>/<PRODUCT_ID>.SAFE.zip \
  --date YYYY-MM-DD \
  --overwrite
```

Useful flags:

| Flag | Use |
|---|---|
| `--zip-path` | Explicit SAFE ZIP path instead of newest raw download |
| `--date` | Explicit output folder date |
| `--overwrite` | Replace existing outputs |
| `--reextract` | Re-extract SAFE ZIP even if `data/work` already exists |
| `--keep-intermediate` | Keep temporary GeoTIFFs for debugging |
| `--skip-validation` | Skip COG validation; only use for debugging |

## Expected output

For a product acquired on `2025-09-14`, outputs are:

```text
data/seed/rasters/2025-09-14/analytic.tif
data/seed/rasters/2025-09-14/scl.tif
data/seed/rasters/2025-09-14/prepare_manifest.json
```

The successful run we performed produced:

| File | Size | CRS | Resolution | dtype | Bands | Nodata |
|---|---:|---|---|---|---:|---:|
| `analytic.tif` | about 2.24 GiB | EPSG:32643 | 10 m | `uint16` | 9 | 0 |
| `scl.tif` | about 6.28 MiB | EPSG:32643 | 10 m | `uint8` | 1 | 0 |

`prepare_manifest.json` records source ZIP, extracted SAFE path, source assets, output paths, CRS, resolution, dimensions, dtype, nodata, and band descriptions.

Expected analytic band descriptions:

```text
B04, B08, B05, B06, B07, B11, B12, B03, B02
```

Expected SCL band description:

```text
SCL
```

## Validation signals

The script should print:

```text
valid COG: /app/data/seed/rasters/{date}/analytic.tif
valid COG: /app/data/seed/rasters/{date}/scl.tif
COG preparation complete
```

You can also inspect the manifest from the host:

```bash
python - <<'PY'
from pathlib import Path
import json
manifest = Path('data/seed/rasters/2025-09-14/prepare_manifest.json')
data = json.loads(manifest.read_text())
for name, summary in data['outputs'].items():
    print(name, summary['crs'], summary['resolution'], summary['dtype'], summary['band_count'], summary['descriptions'])
PY
```

## Cleanup after a successful run

The script removes its `_tmp` folder by default. It does not remove the extracted SAFE folder because keeping it during debugging is useful. After successful COG validation, it is safe to delete extracted work data:

```bash
python - <<'PY'
from pathlib import Path
import shutil
work = Path('data/work/sentinel-2-l2a')
if work.exists():
    shutil.rmtree(work)
    print(f'deleted {work}')
PY
```

Keep the raw SAFE ZIP if you want reproducibility/audit. Delete it only if disk pressure is high and the COGs are already validated/backed up.

Stop local dependency containers if they were started only for this task:

```bash
docker compose -f infra/docker/docker-compose.yml stop postgis minio
```

## Troubleshooting

### `ImportError: libexpat.so.1`

Cause: rasterio/GDAL wheel needs `libexpat1` in the slim Python image.

Fix: ensure `services/ingestion/Dockerfile` installs `libexpat1` before Python dependencies.

### JP2 decode failure

Cause: GDAL/rasterio image cannot read Sentinel-2 JP2 files.

Fixes:

1. Confirm the command is running inside `ingestion-worker`, not a host Python environment.
2. Rebuild the image after dependency changes.
3. Confirm the SAFE ZIP is intact and contains the required JP2s.

### COG validation failure

Do not upload/register failed COGs. Rerun with:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python scripts/prepare_sentinel2_l2a_cogs.py --overwrite --keep-intermediate
```

Then inspect `_tmp/analytic_intermediate.tif`, `_tmp/scl_intermediate.tif`, and the generated manifest.

### Run is slow

This is expected for a full Sentinel-2 tile. The slowest parts are:

- resampling 20 m bands to the 10 m grid
- writing the 9-band analytic COG
- building internal overviews

On the verified run, the full conversion took roughly tens of minutes. Prefer running inside Docker and avoid parallel heavy disk activity.

## What this unlocks next

After this runbook succeeds, Phase 2 can proceed to:

1. Upload the validated COGs to MinIO at:
   - `sentinel-2-l2a/{acquisitionDate}/analytic.tif`
   - `sentinel-2-l2a/{acquisitionDate}/scl.tif`
2. Register/update the STAC item assets.
3. Render a true-colour tile through TiTiler.
4. Compute an SCL-masked NDVI statistic in the BFF.
5. Compare the statistic against a QGIS/notebook reference.
