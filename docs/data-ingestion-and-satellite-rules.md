# Data Ingestion and Satellite Rules

## Purpose

This document is the source of truth for imagery sources, COG layout, STAC metadata, cloud masking, and index calculation rules. Product UX belongs in `product-plan.md`; service architecture belongs in `architecture-tech-stack.md`; Railway runtime details belong in `railway-deployment-guide.md`.

## MVP source strategy

Wave 1 uses Sentinel-2 L2A over the Bangalore AOI. Other sources are intentionally deferred until the Sentinel-2 pipeline proves end-to-end rendering and cloud-masked statistics.

| Source | Provider | MVP status | Role |
|---|---|---|---|
| Sentinel-2 L2A | ESA / Copernicus Data Space Ecosystem | Primary | True-colour display plus NDVI, NDRE, NDMI, NDWI_GREEN_NIR. |
| Sentinel-1 | ESA | Wave 2 | SAR fallback/product layer for cloudy periods; not an optical index source. |
| ResourceSat-2A | ISRO/NRSC | Wave 2 | Optical agriculture source after access and data terms are confirmed. |
| Cartosat-3 | ISRO/NRSC | Wave 2+ | High-resolution visual context after licensing; not primary for NDVI. |
| EOS-04 / NISAR | ISRO / NASA-ISRO | Wave 2+ | SAR product layers; not optical vegetation-index sources. |
| EOS-06 / IRS-1C | ISRO | Not planned for field MVP | Too coarse or archival/decommissioned for this product goal. |

## Data access rules

### Sentinel-2

- Use Copernicus Data Space Ecosystem for current Sentinel access.
- Wave 1 may ingest manually downloaded products or a provided Bangalore `.tif` for the first spike.
- Wave 2 should automate discovery/download using CDSE STAC/OData/S3 APIs.
- Use L2A products because SCL is needed for cloud/shadow masking.

ISRO/Bhoonidhi access notes are deferred to the Appendix and are not for MVP prompts.

## Area of interest rules

- Initial AOI is Bangalore and nearby agricultural areas.
- AOI must be configurable, not hard-coded into components.
- Compute AOI-level cloud/usable-pixel percentage per acquisition date.
- “Latest usable” means the newest date whose usable-pixel percentage is above the configured threshold.

## COG asset layout

Do not combine mixed-resolution continuous reflectance bands and categorical SCL into one ambiguous raster.

For each Sentinel-2 scene/date, create/register these assets:

1. **Analytic reflectance COG**
   - Contains spectral bands needed for RGB and supported indices.
   - Resampled to a common 10 m grid.
   - Continuous reflectance bands use bilinear/cubic resampling.
   - Preserve uint16 source values; do not pre-stretch.
   - Build internal overviews.

2. **SCL COG**
   - Contains Sentinel-2 Scene Classification Layer.
   - Keep categorical values intact.
   - Use nearest-neighbour resampling only.
   - SCL COG internal overviews must also use nearest-neighbour resampling.
   - Register as a separate STAC asset.

## Frozen Sentinel-2 analytic band order

Use this order for the Wave 1 analytic COG unless there is a documented migration:

| Position | Band | Meaning | Used for |
|---:|---|---|---|
| 1 | B04 | Red | RGB, NDVI |
| 2 | B08 | NIR | NDVI, NDRE, NDMI, NDWI_GREEN_NIR |
| 3 | B05 | Red edge 1 | NDRE |
| 4 | B06 | Red edge 2 | Future red-edge variants |
| 5 | B07 | Red edge 3 | Future red-edge variants |
| 6 | B11 | SWIR 1 | NDMI |
| 7 | B12 | SWIR 2 | Future moisture/burn variants |
| 8 | B03 | Green | RGB, NDWI_GREEN_NIR |
| 9 | B02 | Blue | RGB |

STAC `eo:bands` and `raster:bands` metadata must match this order exactly. The BFF builds TiTiler expressions from this metadata.

With the frozen analytic band order, true-colour RGB uses **bands [1, 8, 9]** (B04 Red=b1, B03 Green=b8, B02 Blue=b9), in that order, with display rescale configured separately from reflectance/index math. Do NOT assume RGB = bands 1,2,3.

## Supported index formulas

| Index id | Label | Formula | Bands |
|---|---|---|---|
| NDVI | NDVI | (NIR-Red)/(NIR+Red) | (B08-B04)/(B08+B04) |
| NDRE | NDRE | (NIR-RedEdge)/(NIR+RedEdge) | (B08-B05)/(B08+B05) |
| NDMI | NDMI (vegetation moisture) | (NIR-SWIR)/(NIR+SWIR) | (B08-B11)/(B08+B11) |
| NDWI_GREEN_NIR | Water NDWI (McFeeters) | (Green-NIR)/(Green+NIR) | (B03-B08)/(B03+B08) |

Supported indices list (config/sources): `["NDVI","NDRE","NDMI","NDWI_GREEN_NIR"]`. Default = NDVI.

TiTiler expressions are positional (`b1`, `b2`, …), so the BFF must translate band names to positions using STAC metadata.

## Reflectance correction rules

Wave 1 stores **raw uint16 DN** COGs, and all index/stat code applies per-band scale/offset.

```text
QUANTIFICATION_VALUE = 10000
BOA_ADD_OFFSET       = -1000   # raw DN units; read per band from product metadata; 0 for baselines < 04.00

If storing raw DN (Wave 1 choice):
  corrected_reflectance = (raw_dn + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE

STAC raster:bands uses the convention  physical = raw * scale + offset, so:
  scale  = 1 / QUANTIFICATION_VALUE          # 0.0001
  offset = BOA_ADD_OFFSET / QUANTIFICATION_VALUE   # -0.1   (NOT -1000)
```

Offsets may be band-specific and must be read per band; do not reuse the raw-DN `-1000` as a STAC `offset` — the STAC offset is `-0.1`. Confirm exact values from product metadata at ingestion.

Do not assume the offset cancels out for all indices. It can bias denominators and therefore index values.

## Cloud and validity masking

Default excluded set: **0, 1, 2, 3, 7, 8, 9, 10, 11**.

| SCL class | Meaning | Default action |
|---:|---|---|
| 0 | No data | Exclude |
| 1 | Saturated/defective | Exclude |
| 2 | Dark area / cast & topographic shadow | Exclude |
| 3 | Cloud shadow | Exclude |
| 7 | Unclassified | Exclude |
| 8 | Cloud medium probability | Exclude |
| 9 | Cloud high probability | Exclude |
| 10 | Thin cirrus | Exclude |
| 11 | Snow/ice | Exclude unless locally irrelevant and reviewed |

Keep class **6 (Water)** included by default (NDWI may intentionally analyze water); a plot with high water coverage may be flagged but is not auto-excluded. Also exclude nodata/out-of-coverage pixels.

> Cloud-masked index statistics are computed in the **BFF (FastAPI) using rasterio/rio-tiler**, not by
> plain TiTiler `/cog/statistics`. The BFF reads the analytic COG window and the SCL COG window for the
> request polygon, applies per-band scale/offset, applies the SCL mask, then computes
> min/max/mean/stddev and the pixel-percentage fields. **TiTiler serves RGB display tiles (and
> optional index *display* overlays) only — it is not used for masked statistics**, because vanilla
> TiTiler `/cog/statistics` takes a single `url` and cannot apply a categorical mask from a second COG.

### Pixel accounting and percentages

```text
totalPixels      = pixels intersecting the request geometry at 10 m analysis grid
nodataPixels     = out-of-coverage / nodata pixels
coveragePixels   = totalPixels - nodataPixels
sclExcludedPixels= pixels excluded by the SCL mask (within coverage)
validPixels      = coveragePixels - sclExcludedPixels

validPixelPercent  = validPixels      / totalPixels    * 100
cloudMaskedPercent = sclExcludedPixels / totalPixels    * 100
coveragePercent    = coveragePixels   / totalPixels    * 100
```

For AOI-level "latest usable" date selection, use:

```text
usablePixelPercent = validPixels / coveragePixels * 100   # ignores partial-coverage edges
```

## STAC metadata requirements

Every scene/date item must include:

- Collection id, source name, acquisition datetime, product level, MGRS tile where applicable.
- `proj` extension fields per asset: EPSG, shape, transform, bbox/geometry.
- `eo` extension band names matching the frozen order.
- `raster` extension band metadata: data type, nodata/mask, scale, offset, units where available.
- Asset roles:
  - `data` for analytic reflectance COG;
  - `metadata` or clear custom role for SCL COG;
  - optional `thumbnail` or preview later.
- AOI cloud/usable-pixel percentage for layer-date display.

## Ingestion pipeline

### Wave 1 manual path

1. Start with provided Bangalore `.tif` or manually downloaded Sentinel-2 L2A products.
2. Convert inputs into analytic reflectance COG and SCL COG.
3. Validate COGs.
4. Upload COGs to MinIO using the deterministic seed layout.
5. Register STAC collection/item/assets.
6. Smoke-test one RGB tile and one index statistics request.

```text
Bucket: akasha-cogs
Object key: sentinel-2-l2a/{acquisitionDate}/analytic.tif  and  sentinel-2-l2a/{acquisitionDate}/scl.tif
Repo seed folder:
data/seed/
  bangalore-aoi.geojson
  sample-plot.geojson
  stac/sentinel-2-l2a-collection.json
  stac/sentinel-2-l2a-sample-item.json
  rasters/{acquisitionDate}/analytic.tif   # operator-provided; large rasters not committed
  rasters/{acquisitionDate}/scl.tif
```

Wave 2 automated ingestion is deferred to the Appendix and is not for MVP prompts.

## Idempotency rules

Use a deterministic scene key:

```text
{satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}
```

Re-ingesting the same scene must not create duplicate STAC items or overwrite validated assets unless explicitly forced.

## Validation checklist

- `rio cogeo validate` passes for each COG.
- `gdalinfo` confirms COG driver/overviews and expected CRS.
- JP2 decoding works in the ingestion container when SAFE products are used.
- STAC item validates against required extensions.
- TiTiler can render a true-colour tile with sensible rescale.
- A known polygon returns NDVI statistics matching an independent QGIS/notebook reference within agreed tolerance.
- AOI cloud/usable-pixel percentage is computed and stored.

Storage and retention notes are deferred to the Appendix and are not for MVP prompts.

## Appendix (not for MVP prompts)

### ISRO/Bhoonidhi

- Treat high-resolution ISRO data as a commercial/licensing dependency.
- Request/confirm API access, pricing, quota, licensing, and allowed redistribution before implementation.
- Add ISRO sources as new STAC collections; do not change the frontend layer model.

### Wave 2 automated path

1. Scheduled worker queries CDSE and later Bhoonidhi.
2. Worker filters by AOI, date, and cloud constraints.
3. Worker downloads candidate scenes.
4. Worker converts and validates COGs.
5. Worker uploads assets to MinIO.
6. Worker registers or updates STAC idempotently.
7. Worker records ingestion status and errors.

### Storage and retention

- Expect each Sentinel-2 date over the AOI to require hundreds of MB to a few GB depending on clipping, bands, compression, and overviews.
- Keep raw downloads temporary unless needed for audit/reprocessing.
- Retain the last configurable number of usable scenes per source.
- Purge failed/partial conversion artifacts.
- Monitor MinIO volume usage and alert before disk pressure affects writes.
