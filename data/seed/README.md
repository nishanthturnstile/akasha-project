# `data/seed` - Akasha seed assets

Deterministic seed data for the storage/catalog foundation. The ingestion
worker (`services/ingestion`) consumes these assets to populate pgSTAC and
MinIO for local and self-hosted deployments.

```text
data/seed/
  bangalore-60km-aoi.geojson                production AOI polygon and composite grid metadata
  sample-plot.geojson                       example named plot ("North field")
  stac/
    resourcesat-2a-liss3-boa-collection.json
    resourcesat-2a-liss3-boa-sample-item.json
  rasters/resourcesat-2a-liss3-boa/
    scene/{date}/{sceneComponent}/          operator-prepared scene COGs (not committed)
    composite/{aoiId}/{date}/               operator-prepared composite COGs (not committed)
      analytic.tif                          4-band uint16 BOA reflectance COG
      mask.tif                              Akasha provisional validity/cloud mask COG
      prepare_manifest.json                 upload/STAC registration manifest
```

Legacy Sentinel STAC fixtures may still exist while tests cover backwards
compatibility, but ResourceSat LISS-3 is the production default seed contract.

## ResourceSat LISS-3 Analytic Bands

| Pos | Band | Common name | Used for |
|---:|---|---|---|
| 1 | BAND2 | green | FCC, NDWI |
| 2 | BAND3 | red | FCC, NDVI, MSAVI |
| 3 | BAND4 | nir | FCC, NDVI, MSAVI, NDMI, NDWI |
| 4 | BAND5 | swir16 | NDMI |

Default display is FCC with role order `NIR, RED, GREEN`. Reflectance is raw
uint16 DN with `scale = 0.0001` and `offset = 0.0`.

## Provisional Mask

ResourceSat LISS-3 BOA samples validated so far do not include a native
quality/cloud/shadow raster. Akasha generates a provisional mask:

| Value | Meaning | Default action |
|---:|---|---|
| 0 | gap/background/nodata | exclude |
| 1 | valid optical pixel | keep |
| 2 | cloud | exclude |
| 3 | shadow | exclude |
| 4 | water | keep |

Default excluded mask classes are `0,2,3`. Metrics using this mask are marked
`akasha:metrics_provisional = true`.

## Deterministic Sample Composite

```text
source id : resourcesat-2a-liss3-boa
aoi id    : bangalore-60km
item id   : resourcesat-2a-liss3-boa_bangalore-60km_2026-03-19_composite
date      : 2026-03-19
bucket    : akasha-cogs
keys      : resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/analytic.tif
            resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/mask.tif
footprint : bbox4326 [77.023647, 12.537266, 78.131561, 13.61645]
```

The checked-in sample STAC item is a contract scaffold. Real deployments should
replace placeholder/provisional metrics by running the Bhoonidhi download,
COG-preparation, ingest-manifest, and composite verification flow.

## Seeding

Run on the deployment or local Docker stack.

```bash
# App schema from the api service.
python -m app.cli db upgrade

# Catalog + storage from the ingestion worker.
python worker.py seed
python worker.py verify

# Prepared real COG ingestion.
python worker.py ingest-manifest --method upsert
python worker.py verify-manifest-cogs
python worker.py verify-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item
```

Real COGs are operator-provided and not committed. Production-like ingestion
should use prepared manifests under the ResourceSat `rasters/` tree and
`python worker.py ingest-manifest`, which uploads validated COGs and registers
STAC items idempotently.
