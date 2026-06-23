# Sentinel-1 GRD SAFE ZIP → Akasha backscatter COG runbook

This runbook documents the Sentinel-1 SAR preprocessing/runtime path for one-scene validation. Sentinel-1 GRD is radar data, not optical imagery: the first Akasha display product is calibrated terrain-corrected VV backscatter in dB rendered as grayscale.

## Source products

Use native Copernicus Data Space Ecosystem Sentinel-1 GRD SAFE ZIP products from STAC collection `sentinel-1-grd`.

First-validation product filters:

- `sar:instrument_mode = "IW"`
- `product:type` is a GRDH type such as `IW_GRDH_1S`
- `sar:polarizations` includes `VV`; prefer `VV,VH`
- nearest pass around the target date, not exact Sentinel-2 date matching

The native SAFE ZIP must be available before SNAP preprocessing starts. If CDSE exposes only metadata or non-native assets, stop and record the manifest warning; do not run SNAP from incomplete metadata.

## Dry-run discovery and credentials

The downloader phase is dry-run-first and should write:

```text
data/raw/sentinel-1-grd/coverage_manifest.json
```

Credentials must come from ignored environment files or process environment, for example `CDSE_ACCESS_TOKEN` or `CDSE_USERNAME`/`CDSE_PASSWORD`. Never commit, log, paste, or write secrets into manifests.

CDSE download URL modes to record in the manifest:

- STAC `Product` asset href when present.
- OData native product URL: `https://download.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/$value`.
- OData ZIP URL where documented/available: `.../Products(<uuid>)/$zip`.

If neither `$value`, `$zip`, nor an equivalent native SAFE ZIP URL is accessible for the selected product, fail before preprocessing with a sanitized message.

Expected local ZIP layout:

```text
data/raw/sentinel-1-grd/{productId}/{productId}.SAFE.zip
```

## Build and smoke-test the SAR runtime

Sentinel-1 uses a separate SAR image so the existing Sentinel-2 ingestion worker is not bloated with Java/SNAP.

```bash
docker compose -f infra/docker/docker-compose.yml build ingestion-sar
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-sar gpt -h
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-sar \
  python scripts/prepare_sentinel1_grd_cogs.py --help
```

The image installs Java, ESA SNAP GPT, rasterio, rio-cogeo, and numpy. The Compose service mounts:

```text
../../data    -> /app/data
../../scripts -> /app/scripts:ro
snap_cache    -> /snap-cache
```

SNAP uses `/snap-cache` for DEM/orbit/user cache via `SNAP_USER_DIR`. Keep this volume persistent across runs to avoid repeated DEM/orbit downloads.

Recommended VM/container resources for real scenes:

| Resource | Recommendation |
|---|---|
| Memory | 16 GiB minimum; set `SNAP_JAVA_MAX_HEAP=12g` or lower if needed. |
| Disk | 100+ GiB free for SAFE ZIPs, extracted work/intermediates, DEM cache, and COGs. |
| Network | Outbound HTTPS for CDSE downloads, SNAP orbit files, and DEM downloads. |

Useful non-secret env knobs are documented in `infra/docker/.env.example`: `SNAP_CACHE_SIZE`, `SNAP_PARALLELISM`, `SNAP_JAVA_MAX_HEAP`, `AKASHA_S1_DEM_SOURCE`, `AKASHA_S1_FALLBACK_DEM_SOURCE`, `AKASHA_S1_TARGET_CRS`, `AKASHA_S1_PIXEL_SPACING_METERS`, and `AKASHA_S1_VV_RESCALE`.

The SAR image uses the current ESA SNAP Sentinel toolbox installer:

```text
https://download.esa.int/step/snap/13.0/installers/esa-snap_sentinel_linux-13.0.0.sh
```

If ESA changes installer paths, update `services/ingestion-sar/Dockerfile` after confirming the new link from the SNAP download page.

## SNAP preprocessing steps

`scripts/prepare_sentinel1_grd_cogs.py` requires ESA SNAP GPT. If `gpt` is unavailable, it fails with a clear message pointing back to this runbook.

The generated SNAP graph performs:

1. `Read` native SAFE ZIP or extracted `.SAFE`.
2. `Apply-Orbit-File` with Sentinel precise orbit auto-download.
3. `ThermalNoiseRemoval`.
4. `Remove-GRD-Border-Noise` when the installed SNAP operator is available (`--border-noise auto`, default).
5. `Calibration` to linear `Sigma0` (`outputImageScaleInDb=false`).
6. Optional `Speckle-Filter` only when `--speckle-filter` is passed; disabled by default for first validation.
7. `Terrain-Correction` to deterministic target CRS/pixel spacing.
8. GeoTIFF output for post-processing.

DEM default is `Copernicus 30m Global DEM`; if SNAP processing fails with that DEM, the script retries `SRTM 1Sec HGT` by default and records the DEM actually used. The DEM/orbit cache path in Docker is `/snap-cache`.

After SNAP, Python converts linear sigma0 to dB:

```text
10 * log10(max(sigma0, 1e-8))
```

It writes Float32 nodata `-9999.0`, band 1 `VV_dB`, and band 2 `VH_dB` when VH is present. Internal COG overviews use average resampling.

## Run preprocessing

Manifest-driven mode:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-sar \
  python scripts/prepare_sentinel1_grd_cogs.py \
    --selection-manifest data/raw/sentinel-1-grd/coverage_manifest.json \
    --overwrite
```

Single-product mode:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-sar \
  python scripts/prepare_sentinel1_grd_cogs.py \
    --zip-path data/raw/sentinel-1-grd/<PRODUCT_ID>/<PRODUCT_ID>.SAFE.zip \
    --relative-orbit <RELATIVE_ORBIT_OR_OMIT> \
    --overwrite
```

Useful flags:

| Flag | Use |
|---|---|
| `--selection-manifest` | Batch selected products from downloader manifest. |
| `--zip-path` | Single native SAFE ZIP or extracted `.SAFE` directory. |
| `--output-root` | Default `data/seed/rasters/sentinel-1-grd`. |
| `--border-noise auto|on|off` | Default auto uses the operator only when available. |
| `--speckle-filter` | Enable speckle filtering; off by default. |
| `--target-crs` | Default `EPSG:4326`. |
| `--pixel-spacing-meters` | Default `10`. |
| `--keep-intermediate` | Keep SNAP and dB intermediate GeoTIFFs for debugging. |
| `--display-fallback-from-cog-safe` | Display-only fallback from extracted CDSE COG_SAFE measurement TIFFs when SNAP terrain correction is unavailable. |

### Display fallback from CDSE COG_SAFE

The preferred production path remains SNAP terrain correction. For one-scene display validation, CDSE Sentinel-1 GRD COG_SAFE products can also be converted into an Akasha display COG when SNAP terrain correction is blocked by local runtime/operator issues.

This fallback requires an extracted `.SAFE` directory and performs:

1. Read `measurement/*vv*cog.tiff` and optional `*vh*cog.tiff`.
2. Apply SAFE `annotation/calibration/calibration-*.xml` `sigmaNought` LUTs to convert DN to linear sigma0.
3. Convert to dB with `10 * log10(max(DN^2 / sigmaNought^2, 1e-8))`.
4. Approximate georeferencing from the SAFE annotation geolocation grid.
5. Write `backscatter.tif` as a Float32 COG with average overviews.

Example:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-sar \
  python scripts/prepare_sentinel1_grd_cogs.py \
    --zip-path data/raw/sentinel-1-grd/<PRODUCT_ID>/<PRODUCT_ID>.SAFE \
    --relative-orbit <RELATIVE_ORBIT> \
    --orbit-direction <ascending|descending> \
    --polarizations VV,VH \
    --display-fallback-from-cog-safe \
    --overwrite
```

Manifests created by this mode are marked with `processing_graph_version: akasha-s1-grd-cog-safe-display-fallback-v1` and include a warning that SNAP terrain-corrected output remains preferred for production.

## Output layout and manifests

Each prepared scene writes:

```text
data/seed/rasters/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif
data/seed/rasters/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/prepare_manifest.json
```

Manifest-driven mode also writes:

```text
data/seed/rasters/sentinel-1-grd/batch_prepare_manifest.json
```

`prepare_manifest.json` includes product id, platform, acquisition datetime/date, relative orbit, orbit direction, polarizations, processing graph version, DEM source, output COG path, WGS84 bbox/geometry when available, CRS, transform, dimensions, nodata, and display rescale defaults. The default VV display rescale is `-25,5` dB and can be overridden with `AKASHA_S1_VV_RESCALE`.

## MinIO, STAC, BFF, and UI behavior

Runtime storage should use source-specific object keys:

```text
s3://akasha-cogs/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif
```

STAC registration should use SAR-specific metadata and a `backscatter` asset. Sentinel-1 has no SCL and no optical vegetation indices; source metadata should advertise radar/SAR semantics and `supportedIndices: []`.

BFF/UI expectations:

- Browser tile URLs remain same-origin `/api/*`; never expose MinIO URLs or credentials.
- First display mode is `VV_GRAYSCALE`.
- UI copy should make clear: radar layer, cloud-penetrating, not true colour.
- Optical index controls must stay hidden/disabled for Sentinel-1 until SAR-specific metrics are implemented.

## One-scene validation vs later mosaic

This scope validates one selected Sentinel-1 scene end-to-end. The South India bbox may require multiple Sentinel-1 scenes for full coverage. Do not make the browser manage one raster layer per SAR scene. Later production coverage should add a backend mosaic/pre-mosaic strategy so the frontend still receives one date/source/display-mode tile template.

## Troubleshooting

### `gpt` not found

Build/run `ingestion-sar` or install ESA SNAP locally and set `SNAP_GPT` to the GPT executable path.

### Native SAFE ZIP unavailable

Stop before SNAP. Re-run discovery/download and verify a STAC `Product`, OData `$value`, or OData `$zip` native product URL is available.

### DEM/orbit download failures

Check outbound network access and the persistent `/snap-cache` volume. Re-running usually reuses completed cache entries.

### SNAP out of memory

Increase VM memory, reduce `SNAP_PARALLELISM`, reduce `SNAP_CACHE_SIZE`, or lower `SNAP_JAVA_MAX_HEAP` to fit the container host.
