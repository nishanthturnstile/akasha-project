# Sentinel-2 L2A SAFE ZIP → Akasha analytic + SCL COG runbook

This runbook documents the operator workflow for turning Copernicus Sentinel-2 L2A SAFE products into the COG assets Akasha needs.

**Important coverage rule:** one complete Sentinel-2 L2A SAFE ZIP is one MGRS tile/granule. It is not full coverage for a large polygon such as the South India production target. Large AOIs require a coverage manifest that selects one or more SAFE ZIPs per intersecting MGRS tile.

Manifest-driven preparation writes collision-safe outputs:

```text
data/seed/rasters/{acquisitionDate}/{mgrsTile}/analytic.tif
data/seed/rasters/{acquisitionDate}/{mgrsTile}/scl.tif
data/seed/rasters/{acquisitionDate}/{mgrsTile}/prepare_manifest.json
```

These files are large operator-provided/generated rasters and are intentionally ignored by git.

## When to use this

Use this process when you need to prepare production-like Sentinel-2 coverage for Akasha:

1. Dry-run CDSE discovery and write a coverage manifest.
2. Explicitly download the selected complete SAFE ZIPs.
3. Prepare one analytic COG and one SCL COG per selected SAFE ZIP.
4. Upload/register the prepared COGs through the ingestion worker.
5. Verify registered COGs and smoke-test BFF tile/statistics routes.

Do **not** use the Sentinel-2 Global Mosaics path for this workflow. Global mosaics only provide a visual/NIR subset and do not include all Akasha analytic bands or SCL.

## Source products

The downloader targets CDSE STAC collection `sentinel-2-l2a` and downloads the complete native product ZIP from the `Product` asset.

A SAFE ZIP must contain at least these source assets:

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

## 1. Dry-run coverage discovery

The downloader defaults to **dry-run**. Without `--download` or `--download-selected`, it searches, ranks candidates, writes a manifest, and downloads nothing.

Production-like South India target dry-run:

```bash
uv run python scripts/download_sentinel2_l2a_product.py \
  --bbox-preset south-india-target \
  --max-items 100 \
  --max-cloud-cover 30
```

The command writes:

```text
data/raw/sentinel-2-l2a/coverage_manifest.json
```

The manifest includes selected product ids, selected MGRS tiles, overlap metadata, warnings, and estimated total download size.

### 2026 default date range behavior

If `--datetime` is omitted, the implemented downloader uses a 90-day interval constrained to calendar year 2026:

- before 2026: `2026-01-01T00:00:00Z/2026-03-31T23:59:59Z`
- during 2026: the last 90 days ending today, capped to 2026
- after 2026: the final 90 days of 2026

Use `--datetime START/END` to override this, for example:

```bash
uv run python scripts/download_sentinel2_l2a_product.py \
  --bbox-preset south-india-target \
  --datetime 2026-01-01T00:00:00Z/2026-03-31T23:59:59Z
```

## 2. Explicit batch download

Downloads are opt-in. The default remains dry-run.

Batch download every coverage-selected product from the manifest selection logic:

```bash
uv run python scripts/download_sentinel2_l2a_product.py \
  --bbox-preset south-india-target \
  --max-items 100 \
  --max-cloud-cover 30 \
  --download-selected \
  --yes \
  --prompt-credentials
```

Useful downloader flags implemented by `scripts/download_sentinel2_l2a_product.py`:

| Flag | Use |
|---|---|
| `--download-selected` | Download all coverage-selected products serially. |
| `--download` | Legacy/single-product download path using `--candidate-index` or `--item-id`. |
| `--yes` | Required for large or unknown-size downloads. |
| `--prompt-credentials` | Prompt for CDSE username/password if env vars are absent. |
| `--force` | Re-download existing ZIPs. |
| `--out-dir` | Download root; default `data/raw/sentinel-2-l2a`. |
| `--max-items` | Maximum STAC items to inspect; default `50`. |
| `--max-cloud-cover` | Candidate filter; default `30.0`. |
| `--datetime` | Explicit STAC datetime interval; otherwise the 2026 default above is used. |

Credentials may also come from ignored `.env`, `CDSE_ACCESS_TOKEN`, or `CDSE_USERNAME`/`CDSE_PASSWORD`. Do not commit or paste credentials.

Expected ZIP layout:

```text
data/raw/sentinel-2-l2a/{productId}/{productId}.SAFE.zip
```

Expect multiple GB of network and disk usage for large AOIs because each selected MGRS tile is a complete SAFE ZIP.

## 3. Build the ingestion image

Run COG prep inside the `ingestion-worker` image rather than directly on Windows. This avoids local GDAL/rasterio/JP2 dependency problems.

```bash
docker compose -f infra/docker/docker-compose.yml build ingestion-worker
```

The image includes `numpy`, `rasterio`, `rio-cogeo`, and the OS runtime packages needed by GDAL wheels.

### Linux VM / on-prem repeatability checklist

Use the same Docker Compose workflow on a Linux VM. Do not install GDAL/rasterio directly on the VM unless you are debugging the image itself.

Minimum VM prerequisites:

| Requirement | Guidance |
|---|---|
| OS | Ubuntu 22.04/24.04 LTS or another Docker-supported Linux distribution. |
| Docker | Docker Engine plus Docker Compose plugin. |
| Disk | Start with at least 100–200 GiB free for South India dry-run + several SAFE ZIPs + generated COGs. Entire India requires substantially more and should use a dedicated data volume. |
| Memory | 16 GiB recommended minimum for full-tile COG preparation; more is better for batch runs. |
| Network | Stable outbound HTTPS access to Copernicus Data Space APIs and enough bandwidth for multi-GB ZIPs. |
| Secrets | `.env` file with MinIO/Postgres secrets and CDSE credentials or environment variables supplied by the operator. Do not commit `.env`. |

First-time Linux VM setup:

```bash
git clone <akasha-repo-url> akasha
cd akasha
cp infra/docker/.env.example infra/docker/.env  # if present; otherwise create from infra/selfhosted/env.example values
cp .env.example .env  # if present; add CDSE_USERNAME/CDSE_PASSWORD or CDSE_ACCESS_TOKEN
docker compose -f infra/docker/docker-compose.yml up -d postgis minio stac-api titiler api web
docker compose -f infra/docker/docker-compose.yml build ingestion-worker
```

Recommended VM storage layout:

```text
/srv/akasha/repo                  # git checkout
/srv/akasha/data                  # bind-mounted data volume for raw SAFE ZIPs, work dirs, and COG outputs
/srv/akasha/minio                 # MinIO persistent volume if not using Docker named volumes
/srv/akasha/postgis               # PostGIS persistent volume if not using Docker named volumes
```

For large regional runs, prefer putting `data/` and MinIO on a large attached disk. The repository already bind-mounts `../../data:/app/data` into `ingestion-worker`, so host `data/` content remains reusable across container rebuilds.

Linux VM validation after setup:

```bash
docker compose -f infra/docker/docker-compose.yml ps
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py healthcheck
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py migrate-catalog
```

Then run the same dry-run/download/prepare/upload/register steps documented below.

## 4. Manifest-driven batch COG preparation

Prepare every downloaded product selected by the coverage manifest:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python scripts/prepare_sentinel2_l2a_cogs.py \
    --selection-manifest data/raw/sentinel-2-l2a/coverage_manifest.json \
    --overwrite
```

The batch path writes one output directory per acquisition date and MGRS tile:

```text
data/seed/rasters/2026-01-15/43PGQ/analytic.tif
data/seed/rasters/2026-01-15/43PGQ/scl.tif
data/seed/rasters/2026-01-15/43PGQ/prepare_manifest.json
data/seed/rasters/batch_prepare_manifest.json
```

By default, the prep script:

1. Reads selected products from the downloader manifest.
2. Finds each downloaded `*.SAFE.zip`.
3. Extracts each SAFE ZIP to `data/work/sentinel-2-l2a/`.
4. Uses `B04_10m` as the 10 m reference grid.
5. Builds a 9-band `uint16` analytic intermediate in frozen Akasha order.
6. Resamples continuous 20 m bands to 10 m using bilinear resampling.
7. Resamples SCL to 10 m using nearest-neighbour resampling.
8. Translates both intermediates to COGs with internal overviews.
9. Validates both COGs using `rio-cogeo`.
10. Writes each `prepare_manifest.json` plus a batch manifest.
11. Removes temporary intermediate files unless `--keep-intermediate` is supplied.

Useful prep flags:

| Flag | Use |
|---|---|
| `--selection-manifest` | Downloader coverage manifest for batch COG preparation. |
| `--output-root` | Output root; default `data/seed/rasters`. |
| `--overwrite` | Replace existing outputs. |
| `--reextract` | Re-extract SAFE ZIPs even if `data/work` already exists. |
| `--keep-intermediate` | Keep temporary GeoTIFFs for debugging. |
| `--skip-validation` | Skip COG validation; only use for debugging. |

The legacy single-ZIP mode still exists for the old sample workflow:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python scripts/prepare_sentinel2_l2a_cogs.py \
    --zip-path data/raw/sentinel-2-l2a/<PRODUCT_ID>/<PRODUCT_ID>.SAFE.zip \
    --date YYYY-MM-DD \
    --overwrite
```

Single-ZIP mode writes `data/seed/rasters/{date}/analytic.tif` and `scl.tif`; treat that date-only layout as legacy/sample-only because it cannot represent multiple MGRS tiles on the same acquisition date.

## 5. Validate prepared outputs

The prep script should print one `valid COG:` line per generated `analytic.tif` and `scl.tif`, then:

```text
COG preparation complete
```

Expected analytic band descriptions:

```text
B04, B08, B05, B06, B07, B11, B12, B03, B02
```

Expected SCL band description:

```text
SCL
```

`prepare_manifest.json` records source ZIP, extracted SAFE path, product identity, output paths, CRS, resolution, dimensions, dtype, nodata, and band descriptions.

## 6. Upload and register manifest-driven COGs

Use the ingestion worker to upload every prepared COG and register corresponding STAC items:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py ingest-manifest --method upsert
```

By default, the worker discovers both prepared manifest layouts:
`data/seed/rasters/{date}/prepare_manifest.json` for legacy/single-ZIP output and
`data/seed/rasters/{date}/{tile}/prepare_manifest.json` for tile-scoped output. If outputs
are somewhere else, pass a glob:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py ingest-manifest \
    --manifest-glob "data/seed/rasters/*/*/prepare_manifest.json" \
    --method upsert
```

The worker uploads to collision-safe object keys:

```text
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/analytic.tif
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/scl.tif
```

`--method upsert` is the default and keeps STAC registration idempotent. Use `--force` only when intentionally replacing existing object-store assets.

Verify the uploaded COGs:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
  python worker.py verify-manifest-cogs
```

## 7. BFF serving contract

The BFF exposes date-level contracts:

- `GET /api/sources/{sourceId}/dates` returns one row per acquisition date with aggregated `sceneCount`, bounds, and pixel metrics.
- `GET /api/layers/default` chooses the latest usable acquisition date and returns one tile template for that date.
- `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png` serves a single COG when only one scene exists for the date. Multi-scene dates keep the date-level metadata contract but return a sanitized `MOSAIC_TILES_UNAVAILABLE` 503 until a supported MosaicJSON/pgSTAC mosaic backend is configured.

The browser never sees MinIO object URLs or credentials.

## 8. Large-area storage and streaming strategy

For South India or all-India coverage, do **not** try to create one huge COG for the whole region as the first production path. Store and register each Sentinel-2 SAFE product as an independent scene COG pair, then serve a date-level layer through the BFF.

Recommended storage model:

```text
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/analytic.tif
s3://akasha-cogs/sentinel-2-l2a/{acquisitionDate}/{mgrsTile}/{sceneComponent}/scl.tif
```

Why this model is preferred:

- Sentinel-2 products are naturally delivered as MGRS tiles/granules.
- Per-scene COGs avoid enormous monolithic files and allow partial reprocessing.
- COG byte-range reads let TiTiler/rasterio read only the tile windows needed for map display or polygon statistics.
- STAC can represent many scenes for one acquisition date and the BFF can merge date metadata without exposing object paths to the UI.

Rendering model by date:

| Scenario | Current behavior | Production target |
|---|---|---|
| One scene for the selected date | BFF proxies TiTiler `/cog/tiles/...` and returns transparent PNGs for out-of-footprint edge tiles. | Keep this path. |
| Multiple scenes for one selected date | BFF returns date metadata but RGB tile requests are blocked with sanitized `MOSAIC_TILES_UNAVAILABLE` until a mosaic backend is configured. | Configure TiTiler MosaicJSON or titiler-pgstac so one UI tile request can compose multiple scene COGs. |
| Entire South India / India | Many per-scene COG pairs in MinIO and many STAC items grouped by date. | Use a mosaic backend for display tiles; keep per-scene COGs for storage and statistics. |

Do not make the browser manage one raster source per MGRS tile. The frontend should keep one selected date and one tile template; backend services decide which scene COGs contribute to each `{z}/{x}/{y}` tile.

Before attempting full South India or India ingestion:

1. Run dry-run discovery and review `coverage_manifest.json`.
2. Confirm estimated SAFE ZIP download size and available disk.
3. Download a small capped subset first using `--item-id` or a future `--max-selected` implementation.
4. Prepare/upload/register that subset and confirm UI rendering.
5. Only then run the full selected coverage batch.

## Cleanup after a successful run

The prep script removes per-scene `_tmp` folders by default. It does not remove extracted SAFE folders because keeping them during debugging is useful. After successful COG validation, it is safe to delete `data/work/sentinel-2-l2a/` if disk pressure is high.

Keep raw SAFE ZIPs if you need audit/reprocessing. Delete them only if disk pressure is high and COGs are already validated/backed up.

Stop local dependency containers if they were started only for this task:

```bash
docker compose -f infra/docker/docker-compose.yml stop postgis minio
```

## Troubleshooting

### Partial coverage for a large polygon

This is expected if the dry-run selects only one or a few MGRS tiles. A SAFE ZIP is one tile/granule, so full large-polygon coverage requires multiple selected MGRS tiles. Inspect `coverage_manifest.json` for `selected_mgrs_tiles`, overlap percentages, and warnings.

### No candidates in the default date range

The default range is constrained to 2026. Re-run with an explicit `--datetime` interval and/or a larger `--max-items` value.

### High cloud cover or no usable low-cloud candidates

Raise `--max-cloud-cover` temporarily to inspect availability, but keep cloud/usable-pixel metrics provisional until SCL-based AOI metrics are computed after ingestion.

### Batch download refuses to start

Large or unknown-size downloads require `--yes`. Credentials must be supplied by `CDSE_ACCESS_TOKEN`, `CDSE_USERNAME`/`CDSE_PASSWORD`, ignored `.env`, or `--prompt-credentials`.

### JP2 decode failure

Run inside `ingestion-worker`, rebuild the image after dependency changes, and confirm the SAFE ZIP is intact and contains the required JP2 files.

### COG validation failure

Do not upload/register failed COGs. Re-run with `--keep-intermediate`, inspect the generated `_tmp` rasters and `prepare_manifest.json`, then rerun without `--skip-validation`.

### TiTiler mosaic endpoint unavailable

Single-scene dates use the normal TiTiler COG tile route. The current BFF does not emit ad-hoc repeated-`url` TiTiler mosaic requests for multi-scene dates because that is not a verified contract for the deployed TiTiler 1.0.0 image. Multi-scene tile requests return `MOSAIC_TILES_UNAVAILABLE` (503) without exposing internal object URLs. Enable a supported MosaicJSON/pgSTAC backend before promising rendered date-level mosaics.
