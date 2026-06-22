# NISAR S-SAR Beta GCOV COG preparation runbook

Display-only (Phase 1) ingestion of NISAR S-SAR Beta GCOV backscatter into
Akasha, via ISRO Bhoonidhi. NISAR is a **radar/backscatter** source — never an
optical vegetation-index source. GCOV is already geocoded, so **no ESA SNAP step
is required**.

GCOV (Geocoded Covariance) products are commonly **HDF5** (`.h5`) whose diagonal
covariance terms (`HHHH`, `HVHV`, `VHVH`, `VVVV`) are backscatter power in linear
units; some distributions provide geocoded GeoTIFFs instead. The prepare script
handles both.

Pipeline: `bhoonidhi-search` -> `bhoonidhi-download` ->
`scripts/prepare_nisar_ssar_beta_gcov_cogs.py` -> `worker.py ingest-manifest`.
Do **not** use `bhoonidhi-sync` / `build-composite`.

## Prerequisites

- Bhoonidhi credentials and AOI config; MinIO + pgSTAC reachable.
- Python 3.11 with `numpy`, `rasterio`, `rio-cogeo`. For HDF5 GCOV inputs, GDAL
  must have the HDF5 driver (present in the ingestion container).

## Step 0 — Validate the real product format (do this first)

```bash
gdalinfo NISAR_..._GCOV_....h5     # lists HDF5 subdatasets
# or, for a GeoTIFF distribution:
gdalinfo NISAR_..._GCOV_....tif
```

For HDF5, note the subdataset path(s) of the **diagonal** covariance terms (e.g.
`.../frequencyA/HHHH`) — these are the backscatter layers. Confirm:
- which polarizations are present (HH/HV/VH/VV),
- whether values are **linear power** (GCOV default; small positives) or dB,
- nodata, CRS/EPSG, resolution.

## Step 1 — Search and download

```bash
python worker.py bhoonidhi-search   --source nisar-ssar-beta-gcov --aoi bangalore-60km
python worker.py bhoonidhi-download --manifest <out>/coverage_manifest.json
```

## Step 2 — Prepare the backscatter COG

```bash
python scripts/prepare_nisar_ssar_beta_gcov_cogs.py \
  --selection-manifest <out>/download_manifest.json \
  --input-scale auto          # GCOV diagonal terms are linear power
```

Single-product mode (one ZIP / `.h5` / GeoTIFF):

```bash
python scripts/prepare_nisar_ssar_beta_gcov_cogs.py --zip-path <raw>/<product>.h5
```

Band discovery order: explicit `--band-path` (a GeoTIFF path **or** an HDF5
subdataset string) > GCOV covariance-diagonal subdatasets in `.h5` > polarization
tokens in GeoTIFF filenames > sorted GeoTIFFs. Diagonal terms map
`HHHH->HH`, `HVHV->HV`, `VHVH->VH`, `VVVV->VV`.

Outputs (deterministic):
```
data/seed/rasters/nisar-ssar-beta-gcov/<date>/<relativeOrbitOrUnknown>/<sceneComponent>/backscatter.tif
data/seed/rasters/nisar-ssar-beta-gcov/<date>/<relativeOrbitOrUnknown>/<sceneComponent>/prepare_manifest.json
```

The COG is Float32 **dB**, nodata `-9999.0`, blocksize 512 with `average`
overviews. The manifest carries `source_id`, scene identity,
`sar:polarizations`, `outputs.backscatter`, and `bbox`/`geometry`.

Useful flags: `--band-path` (GeoTIFF path or HDF5 subdataset string),
`--polarizations`, `--input-scale {auto,linear,amplitude,db}`, `--overwrite`,
`--reextract`, `--keep-intermediate`, `--skip-validation`.

## Step 3 — Ingest (upload COG + load STAC item)

```bash
python worker.py ingest-manifest --collection-id nisar-ssar-beta-gcov
```

Uploads to
`s3://akasha-cogs/nisar-ssar-beta-gcov/<date>/<relativeOrbit>/<sceneComponent>/backscatter.tif`
(idempotent; `--force` to overwrite) and upserts a SAR STAC item into pgSTAC.

## Step 4 — Verify

- COG: band count >= 1 with band-1 overviews.
- API: `GET /api/sources` lists `nisar-ssar-beta-gcov` active;
  `GET /api/sources/nisar-ssar-beta-gcov/dates` returns the ingested date (null
  optical metrics);
  `GET /api/tiles/nisar-ssar-beta-gcov/<date>/VV_GRAYSCALE/{z}/{x}/{y}.png`
  returns a PNG (prefers VV when present; otherwise renders the first band).
- UI: grayscale backscatter renders with no NDVI/cloud controls.

## Notes

- Already registered and activated (display-only) in
  `apps/api/app/raster/catalog_resolver.py` and
  `data/seed/stac/nisar-ssar-beta-gcov-collection.json`.
- If a GCOV HDF5 sample reveals a different group/layer layout than the diagonal
  covariance terms, pass the exact subdataset via `--band-path` and update
  `COVARIANCE_DIAGONAL_TERMS` / discovery in the prepare script.
- SAR statistics/analytics and multi-scene mosaics are out of scope for Phase 1.
