## Satellite Data Dev Flow

Bhoonidhi API access is IP-whitelisted, so real ISRO search/download must run
only from the Akasha staging VM (`akasha-staging`, egress `20.219.3.35`).
Developer laptops should not call Bhoonidhi directly.

### Staging Ingestion

On the staging VM, the ingestion worker runs:

```bash
python worker.py bhoonidhi-sync --source resourcesat-2a-liss3-boa --aoi bangalore-60km
```

This flow:

1. Searches/downloads Bhoonidhi ResourceSat products.
2. Converts raw ZIPs into scene COGs: `analytic.tif` + provisional `mask.tif`.
3. Builds the final AOI/date composite: `analytic.tif`, `mask.tif`, `prepare_manifest.json`.
4. Uploads the final COGs to MinIO and registers the STAC item.

Final shareable bundle layout:

```text
data/seed/rasters/resourcesat-2a-liss3-boa/composite/bangalore-60km/<date>/
  analytic.tif
  mask.tif
  prepare_manifest.json
```

### Local Developer Import

Developers pull the final processed bundle from staging, then import it into
their local Docker MinIO + pgSTAC:

```bash
bash scripts/dev-local.sh --backend-only

python scripts/sync_staging_raster_bundle.py \
  --host akasha-staging \
  --import-local \
  --verify-local
```

For a specific composite date:

```bash
python scripts/sync_staging_raster_bundle.py \
  --host akasha-staging \
  --date 2026-03-19 \
  --overwrite \
  --import-local \
  --force-upload \
  --verify-local
```

This copies only processed COGs and manifest files. It does not copy raw
Bhoonidhi downloads and does not expose Bhoonidhi credentials locally.
