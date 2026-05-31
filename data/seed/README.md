# `data/seed` — Akasha Slice 1 seed assets

Deterministic seed data for the storage/catalog foundation. The ingestion
worker (`services/ingestion`) consumes these to populate pgSTAC and MinIO.

```text
data/seed/
  bangalore-aoi.geojson                     AOI polygon (configurable; not hard-coded)
  sample-plot.geojson                       Example named plot (“North field”)
  stac/
    sentinel-2-l2a-collection.json          STAC Collection (eo/raster/proj/classification)
    sentinel-2-l2a-sample-item.json         STAC Item for the sample scene
  rasters/{acquisitionDate}/                operator-provided COGs (NOT committed)
    analytic.tif                            frozen 9-band uint16 DN reflectance COG
    scl.tif                                 categorical SCL COG (nearest resampling)
```

## Frozen analytic band order (Wave 1)

| Pos | Band | Common name | Used for |
|---:|---|---|---|
| 1 | B04 | red | RGB, NDVI |
| 2 | B08 | nir | NDVI, NDRE, NDMI, NDWI |
| 3 | B05 | rededge | NDRE |
| 4 | B06 | rededge | future red-edge |
| 5 | B07 | rededge | future red-edge |
| 6 | B11 | swir16 | NDMI |
| 7 | B12 | swir22 | future moisture/burn |
| 8 | B03 | green | RGB, NDWI |
| 9 | B02 | blue | RGB |

True-colour RGB = analytic bands **[1, 8, 9]** (B04, B03, B02). Reflectance:
raw uint16 DN; `scale = 0.0001`, `offset = -0.1` (NOT -1000). SCL default
excluded classes: `0,1,2,3,7,8,9,10,11` (class 6 water kept).

## Deterministic scene

Slice 2 uses the real prepared Sentinel-2 L2A scene (see
[`../../docs/sentinel-2-l2a-cog-prep-runbook.md`](../../docs/sentinel-2-l2a-cog-prep-runbook.md)).
Source product: `S2B_MSIL2A_20250914T050649_N0511_R019_T43PHP_20250914T074457.SAFE`.

```text
scene key : sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11
item id   : sentinel-2-l2a_43PHP_20250914_0511
bucket    : akasha-cogs
keys      : sentinel-2-l2a/2025-09-14/analytic.tif
            sentinel-2-l2a/2025-09-14/scl.tif
footprint : EPSG:32643, shape 10980x10980, 10 m, bbox4326
            [77.7513, 11.6470, 78.7709, 12.6502]
```

## Seeding (run on Railway / local Docker — see infra/railway/README.md)

```bash
# 1) app schema (PostGIS + plots) — from the api service
python -m app.cli migrate
# 2) catalog + storage — from the ingestion worker (idempotent)
python worker.py seed         # pgSTAC migrate -> load collection/item -> MinIO bucket/keys
python worker.py verify       # checks the 3 Slice 1 exit criteria
```

Real COGs are operator-provided. If `rasters/{date}/*.tif` are absent, the MinIO
seed creates **empty placeholder objects** at the deterministic keys so the
layout is established; Slice 2 replaces them with validated COGs.

For the repeatable Sentinel-2 L2A SAFE ZIP → `analytic.tif` + `scl.tif` process,
see [`../../docs/sentinel-2-l2a-cog-prep-runbook.md`](../../docs/sentinel-2-l2a-cog-prep-runbook.md).
