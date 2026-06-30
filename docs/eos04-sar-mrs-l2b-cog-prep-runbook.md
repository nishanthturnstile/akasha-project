# EOS-04 SAR-MRS L2B COG preparation runbook

Display-only (Phase 1) ingestion of ISRO EOS-04 (RISAT-class C-band) SAR-MRS L2B
backscatter into Akasha. EOS-04 is a **radar/backscatter** source — never an
optical vegetation-index source. L2B is already geocoded, so **no ESA SNAP step
is required** (unlike Sentinel-1 GRD).

Manual validation pipeline: `bhoonidhi-search` -> `bhoonidhi-download` ->
`scripts/prepare_eos04_sar_mrs_l2b_cogs.py` -> `worker.py verify-raster-product` ->
`worker.py ingest-manifest`.
Do **not** use `bhoonidhi-sync` / `build-composite` (composite-coupled,
ResourceSat-only).

The STAC collection may be loadable for validation while the BFF/source registry
keeps `eos-04-sar-mrs-l2b` product exposure gated. Do not treat collection
availability as product activation.

## Prerequisites

- Bhoonidhi credentials (`BHOONIDHI_USER_ID`, `BHOONIDHI_PASSWORD`) and AOI config.
- MinIO + pgSTAC reachable (`S3_*`, `DATABASE_URL`, `STAC_API_URL`).
- Python 3.11 with `numpy`, `rasterio`, `rio-cogeo` (the ingestion container has these).

## Step 0 — Validate the real product format (do this first)

Download one product, then inspect it before trusting the defaults:

```bash
gdalinfo /path/to/EOS04_..._SAR_MRS_L2B.tif   # or the extracted band GeoTIFF(s)
```

Confirm and record:
- **Band / polarization layout** — how many bands, and which polarizations
  (EOS-04 SAR-MRS is commonly HH or HH/HV; RISAT circular RH/RV is also possible).
- **Calibration scale** — are pixel values linear sigma0 power (small positives),
  amplitude/DN (large positives), or already dB (negatives)? This sets `--input-scale`.
- **Nodata**, **CRS/EPSG**, and **resolution**.

## Step 1 — Search and download

```bash
python worker.py bhoonidhi-search   --source eos-04-sar-mrs-l2b --aoi bangalore-60km
python worker.py bhoonidhi-download --manifest <out>/coverage_manifest.json
```

`bhoonidhi-search` / `bhoonidhi-download` are source-agnostic and already
support EOS-04. The download writes `<raw>/eos-04-sar-mrs-l2b/<product_id>.zip`
and a `download_manifest.json`.

## Step 2 — Prepare the backscatter COG

```bash
python scripts/prepare_eos04_sar_mrs_l2b_cogs.py \
  --selection-manifest <out>/download_manifest.json \
  --polarizations HH,HV \
  --input-scale auto         # set linear|amplitude|db once Step 0 is known
```

Single-product mode (one ZIP, no manifest):

```bash
python scripts/prepare_eos04_sar_mrs_l2b_cogs.py \
  --zip-path <raw>/<product>.zip \
  --polarizations HH,HV
```

Outputs (deterministic):
```
data/seed/rasters/eos-04-sar-mrs-l2b/<date>/<relativeOrbitOrUnknown>/<sceneComponent>/backscatter.tif
data/seed/rasters/eos-04-sar-mrs-l2b/<date>/<relativeOrbitOrUnknown>/<sceneComponent>/prepare_manifest.json
```

The COG is Float32 **dB**, nodata `-9999.0`, blocksize 512 with `average`
overviews. The manifest carries `source_id`, scene identity
(`acquisition_datetime`, `relative_orbit`, `orbit_state`, `product_type`),
`sar:polarizations`, `outputs.backscatter` (raster summary used for the STAC
item and MinIO upload), and `bbox`/`geometry`.

Useful flags: `--band-path <tif>` (skip discovery), `--polarizations`,
`--input-scale {auto,linear,amplitude,db}`, `--overwrite`, `--reextract`,
`--keep-intermediate`, `--skip-validation`.

The prepare script fails closed if it cannot infer polarizations from filenames
and `--polarizations` is omitted. This prevents mislabeled `VV`/`HH` defaults.

## Step 3 — Validate before ingest

```bash
python worker.py verify-raster-product \
  --source eos-04-sar-mrs-l2b \
  --manifest <prepared>/prepare_manifest.json
```

The manifest must include `sar:polarizations`, a Float32 `outputs.backscatter`
asset, and no optical statistics/indices. `worker.py ingest-manifest` repeats
this EOS-04 metadata gate before upload or pgSTAC load; failed validation means
no partial COG upload and no STAC item registration.

## Step 4 — Ingest (upload COG + load STAC item)

```bash
python worker.py ingest-manifest --collection-id eos-04-sar-mrs-l2b
```

This uploads `backscatter.tif` to
`s3://akasha-cogs/eos-04-sar-mrs-l2b/<date>/<relativeOrbit>/<sceneComponent>/backscatter.tif`
(idempotent; `--force` to overwrite) and upserts a SAR STAC item with a
`backscatter` asset and `sar:*` properties into pgSTAC.

## Step 5 — Verify

- COG: `rasterio` reports band count >= 1 and non-empty band-1 overviews
  (matches `storage._verify_cog_metadata`).
- API: `GET /api/sources` lists `eos-04-sar-mrs-l2b` as a gated SAR source
  until activation; direct validation calls to
  `GET /api/sources/eos-04-sar-mrs-l2b/dates` return the ingested date with
  null optical (cloud/usable) metrics;
  `GET /api/tiles/eos-04-sar-mrs-l2b/<date>/VV_GRAYSCALE/{z}/{x}/{y}.png` returns
  a PNG (renders the first backscatter band when no VV is present).
- UI: selecting the source renders the grayscale backscatter layer with no
  NDVI/cloud controls (the SPA hides them for `kind === "sar"`).

## Activation checklist

Keep product exposure gated until all of these pass for one real product:

1. Step 0 product inspection recorded: band count, polarization order, units, nodata, CRS, resolution.
2. `prepare_eos04_sar_mrs_l2b_cogs.py` produces Float32 dB `backscatter.tif`.
3. `verify-raster-product --source eos-04-sar-mrs-l2b` passes.
4. `ingest-manifest --collection-id eos-04-sar-mrs-l2b` passes its pre-upload validation gate.
5. pgSTAC item contains explicit `sar:polarizations` and no optical fields.
6. BFF dates/tiles work for one scene and multi-scene dates remain tile-unavailable.
7. Frontend renders grayscale backscatter and keeps cloud/index/statistics controls disabled.

## Notes

- The source is registered but product-gated in
  `apps/api/app/raster/catalog_resolver.py`; its loadable STAC collection lives in
  `data/seed/stac/eos-04-sar-mrs-l2b-collection.json`.
- SAR statistics/analytics (mean VV/VH dB, VH/VV ratio) and multi-scene mosaics
  are out of scope for Phase 1.
