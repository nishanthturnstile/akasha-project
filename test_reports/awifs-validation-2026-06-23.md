# AWiFS validation — 2026-06-23

## Scope

Implementation Phase 6 AWiFS staging dry-run and capped real run using the safe staging ingestion wrapper only.

Source: `resourcesat-2a-awifs-boa`
Bhoonidhi collection: `ResourceSat-2A_AWIFS_BOA`
AOI: `bangalore-60km`
Staging host: `akasha-staging`

## Safe-wrapper commands

All Phase 6 Bhoonidhi/AWiFS work used `python scripts/staging_ingestion_job.py trigger --host akasha-staging ...` from the workstation. No direct staging `docker run`, `docker compose run`, or direct `worker.py` commands were used for ingestion/composite/verification.

### Search dry-run

Job: `ingest-20260623T175748Z-a810615f`

Result: `succeeded`

Evidence from job log:

- `found 9 Bhoonidhi item(s)`
- `selected 9 candidate(s)`
- `skipped existing 0 product(s)`
- `new products 9`
- `sync window: 2026-02-24..2026-06-23`
- `deferred 8 product(s) due to max downloads per sync (1)`
- coverage manifest: `/srv/akasha/data/work/bhoonidhi/resourcesat-2a-awifs-boa/bangalore-60km/coverage_manifest.new.json`
- `dry-run: stopping before download/prepare/composite/ingest`

### Capped real run: max-downloads=1

Job: `ingest-20260623T175830Z-697347bf`

Result: `validation_failed`, exit code `1`

Downloaded product:

- `RAW20MAR2026048167010400065PSANSTLCSRHTDC.zip`
- Size: `300606167` bytes
- Path: `/srv/akasha/data/raw/bhoonidhi/resourcesat-2a-awifs-boa/RAW20MAR2026048167010400065PSANSTLCSRHTDC.zip`

Product structure:

- `BAND2.tif`
- `BAND3.tif`
- `BAND4.tif`
- `BAND5.tif`
- `BAND_META.txt`
- product `.meta`

Metadata findings from `BAND_META.txt`:

- `SENSOR=AW`
- `NOOFBANDS=4`
- `BANDNUMBERS=2345`
- `BYTESPERPIXEL=2`
- `BITSPERPIXEL=12`
- `INPUTRESOLUTIONALONG=56.00`
- `INPUTRESOLUTIONACROSS=66.00`
- `OUTPUTRESOLUTIONALONG=56.00`
- `OUTPUTRESOLUTIONACROSS=56.00`
- `IMAGEFORMAT=GEOTIFF`
- `PROCESSINGLEVEL=AtmosphericallyCorrectedProduct`
- `MAPPROJECTION=LCC`

Prepare output:

- Prepared scene manifest: `/app/data/seed/rasters/resourcesat-2a-awifs-boa/scene/2026-03-20/20260320T000000Z_path-104_row-65_4b7e36f51ad5/prepare_manifest.json`
- Manifest source: `resourcesat-2a-awifs-boa`
- Collection: `ResourceSat-2A_AWIFS_BOA`
- Analytic band order: `BAND2`, `BAND3`, `BAND4`, `BAND5`
- Band role mapping: `GREEN=BAND2`, `RED=BAND3`, `NIR=BAND4`, `SWIR1=BAND5`
- Mask method: Akasha threshold mask v1 for AWiFS, provisional
- Reflectance metadata remains `scale=0.0001`, `offset=0.0`; no alternate reflectance multiplier/offset was found in inspected metadata.

Coverage failure:

- The first candidate only overlaps the southern edge of the AOI.
- Composite verification failed with `coverage 0.0% below threshold 95.0%`.
- Local read-only inspection of the generated masks showed:
  - prepared scene mask nonzero coverage: `79.726034%`
  - composite mask nonzero coverage: `0.0%`
- This means product structure and scene mask generation worked; the single candidate did not produce valid AOI-grid coverage for the launch AOI.

### Capped real retry: max-downloads=3

Job: `ingest-20260623T180332Z-de5f08a9`

Result: `validation_failed`, exit code `1`

Additional downloaded products:

- `RAW19MAR2026048153009900062PSANSTLCSRHTDC.zip` — `295985839` bytes
- `RAW15MAR2026048096010300067PSANSTLCSRHTDA.zip` — `339199018` bytes
- `RAW15MAR2026048096010300062PSANSTLCSRHTDC.zip` — `325681471` bytes

All retained AWiFS ZIPs inspected contain:

- `BAND2.tif`
- `BAND3.tif`
- `BAND4.tif`
- `BAND5.tif`
- `BAND_META.txt`
- product `.meta`

Metadata fields are consistent across inspected products:

- `SENSOR=AW`
- `NOOFBANDS=4`
- `BANDNUMBERS=2345`
- `BYTESPERPIXEL=2`
- `BITSPERPIXEL=12`
- `OUTPUTRESOLUTIONALONG=56.00`
- `OUTPUTRESOLUTIONACROSS=56.00`
- `IMAGEFORMAT=GEOTIFF`
- `PROCESSINGLEVEL=AtmosphericallyCorrectedProduct`
- `MAPPROJECTION=LCC`

Coverage result:

- Composite rebuilt for `2026-03-20`
- Verification failed with `coverage 62.9839% below threshold 95.0%`

## Candidate footprint notes

The 120-day dry-run found 9 candidates. The first candidate selected by date order had a small overlap area (`0.084629`) and failed coverage. Broader candidates exist in the same search manifest, but the first 4 prepared products still reached only `62.9839%` AOI coverage. AWiFS should therefore remain gated until a later/broader bounded run reaches the required `95%` coverage threshold.

## Phase 6 decision

- TASK-046: PASS — AWiFS search found 9 candidates from `ResourceSat-2A_AWIFS_BOA`.
- TASK-047: PASS — non-zero AWiFS ZIPs were downloaded and retained for inspection.
- TASK-048: PASS — product structure validated: four band GeoTIFFs, uint16-style metadata, LCC projection, 56 m output resolution, no native quality mask requirement.
- TASK-049: BLOCKED — safe-wrapper sync/prepare/composite ran, but post-ingest acceptance cannot pass because coverage is below `95%` (`62.9839%` after max-downloads=3). AWiFS remains gated.
- TASK-050–TASK-053: NOT RUN / BLOCKED — do not run BFF activation smokes or flip AWiFS active until TASK-049 passes.
