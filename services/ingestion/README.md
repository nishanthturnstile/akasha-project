# `services/ingestion` - Ingestion worker

Python worker for getting ResourceSat LISS-3 BOA composites into the catalog
and object store. Sentinel helpers remain as legacy/regression tools, but the
production default workflow is Bhoonidhi ResourceSat.
**Private, no public HTTP surface.** Runs on demand (manual/seed first;
scheduled Bhoonidhi refresh later).

- Base image: `python:3.11.14-slim-bookworm`.
- No HTTP health endpoint; `worker.py healthcheck` validates required env vars.

## Slice 0 (skeleton)

`worker.py` is a no-op CLI:

```bash
python worker.py info          # print resolved config (secrets redacted)
python worker.py healthcheck   # exit 0 if required env vars present
```

Real subcommands discover/download Bhoonidhi products, prepare validated
ResourceSat `analytic.tif` + provisional `mask.tif` COGs, register STAC items,
upload to MinIO, build composites, and verify catalog/object-store state. In
Docker Compose this runs one-shot (`info`) and exits unless invoked manually.

## ResourceSat Bhoonidhi operations

Use the staging worker host for Bhoonidhi calls so egress stays on the
whitelisted static IP. Keep raw downloads and work output on the data disk, not
the OS disk.

```bash
python worker.py bhoonidhi-search \
  --source resourcesat-2a-liss3-boa \
  --aoi bangalore-60km \
  --aoi-path /app/data/seed/bangalore-60km-aoi.geojson

python worker.py bhoonidhi-sync \
  --source resourcesat-2a-liss3-boa \
  --aoi bangalore-60km \
  --window-start 2026-03-01 \
  --window-end 2026-03-31

python worker.py verify-composite \
  --source resourcesat-2a-liss3-boa \
  --aoi bangalore-60km
```

For multiple AOIs, place one GeoJSON file per AOI under `AOI_CONFIG_DIR` and
select with `--aoi <id> --aoi-dir <dir>`. If the AOI carries
`compositeGridCrs`, `composite_grid_crs`, or `akasha:composite_grid_crs` either
at top level or under `properties`, `build-composite` and `verify-composite`
use it as the composite grid CRS unless `--expected-crs` is passed explicitly.
`verify-composite` also checks that the selected AOI id matches the
`prepare_manifest.json` `aoi_id`, so a Bangalore composite cannot accidentally
pass a Mysore verification run. Run verification once per source/AOI pair:

```bash
python worker.py verify-composite \
  --source resourcesat-2a-liss3-boa \
  --aoi mysore-60km \
  --aoi-dir /srv/akasha/config/aois
```

`verify-composite` requires the dated composite STAC item by default. Use
`--local-only` only for explicit local file/COG validation before catalog ingest.

`bhoonidhi-sync` records download, conversion, composite, storage upload, and
STAC registration failures in `BHOONIDHI_LEDGER_PATH`. The BFF monitoring
endpoint `/api/monitoring/imagery-sources` reads that ledger and reports latest
successful search heartbeat, successful composite date, recent failure kinds,
MinIO usage, and stale catalog/composite dates. A stale latest ResourceSat date
is treated as an operator warning only when the latest Bhoonidhi search
heartbeat is fresh and no newer upstream Online=Y product is available for the
AOI; stale searches, unresolved failures, low coverage/usable pixels, storage
errors, and tile-unavailable dates remain blockers. Storage usage includes
`zeroByteObjectCount` totals by bucket and source prefix; any non-zero
ResourceSat count usually means placeholder or incomplete COG objects still
need replacement before live tile/stat validation.

## Manual visual context imports

Cartosat-3 is intentionally gated because no direct Bhoonidhi API collection has
been validated. If an operator receives a licensed visual GeoTIFF, prepare it
with the manual context adapter, verify the generated COG, then ingest it:

```bash
python worker.py prepare-context-cog \
  --source cartosat-3-gated \
  --input /srv/akasha/data/raw/cartosat/CARTOSAT3_ORDER_42.tif \
  --product-id CARTOSAT3_ORDER_42 \
  --acquisition-datetime 2026-04-16T05:30:00Z

python worker.py verify-manifest-cogs --collection-id cartosat-3-gated
python worker.py ingest-manifest --collection-id cartosat-3-gated --method upsert
```

The command writes `visual.tif` and `prepare_manifest.json` under
`data/seed/rasters/cartosat-3-gated/<date>/<sceneComponent>/`. The generated
manifest has this shape:

```json
{
  "source_id": "cartosat-3-gated",
  "product_id": "operator-stable-product-id",
  "platform": "cartosat-3",
  "product_level": "VISUAL-CONTEXT",
  "product:type": "operator-upload-visual",
  "acquisition_datetime": "2026-04-16T05:30:00Z",
  "bbox": [77.0, 11.0, 78.0, 12.0],
  "outputs": {
    "visual": {
      "path": "visual.tif",
      "crs": "EPSG:32643",
      "bounds": [799980, 1290240, 909780, 1400040],
      "resolution": [1.0, 1.0],
      "width": 10980,
      "height": 10980,
      "dtype": "uint16",
      "band_count": 3,
      "gsd": 1.1,
      "descriptions": ["red", "green", "blue"]
    }
  }
}
```

Cartosat-3 manifests default to 1.1 m class GSD metadata. Pass `--gsd` only
when the licensed product/order metadata specifies a different delivered
resolution.

This path registers only a `visual` asset. It does not enable crop indices,
field-level analytics, cloud metrics, or Bhoonidhi automation for Cartosat.
