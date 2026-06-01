# Emergent prompt — Phase 2 Raster de-risk milestone

Use this prompt in Emergent.sh for the next implementation slice.

> Historical note: this prompt predates manifest-driven production ingestion.
> Date-only paths such as `sentinel-2-l2a/2025-09-14/analytic.tif` are legacy
> single-sample references; current production docs use
> `sentinel-2-l2a/{date}/{mgrsTile}/analytic.tif`.

---

We are continuing Akasha MVP implementation in the existing repo. Implement **Phase 2 — Raster de-risk milestone** only. Do not start full frontend UX/auth/custom domains/future sources.

## Goal

Complete the raster proof path end-to-end:

1. Use the already-generated Sentinel-2 L2A analytic COG and SCL COG.
2. Upload/register them into MinIO/STAC with correct metadata.
3. Configure/verify TiTiler can read the analytic COG via S3-compatible MinIO.
4. Render one true-colour RGB tile through TiTiler/gateway.
5. Compute one cloud/SCL-masked, offset-corrected NDVI statistic for a known polygon in the BFF using rasterio/rio-tiler, **not** TiTiler `/statistics`.
6. Add/update smoke checks so this milestone is repeatably verifiable.

This phase is the biggest technical risk reducer. Keep changes scoped and practical.

## Current verified baseline before Phase 2

The repo has already been reviewed after Phase 1. Preserve these contracts and
do not regress them:

- `python scripts/validate_slice0.py` passes: `94/0`.
- `python scripts/validate_slice1.py` passes: `67/0`.
- `python -m pytest -q apps/api/tests` passes: `6/6`.
- `ruff check apps/api services/ingestion scripts/validate_slice1.py scripts/validate_slice0.py` passes.
- Local Docker Phase 1 exit checks passed after `api python -m app.cli migrate`,
  `api python -m app.cli check`, `ingestion-worker python worker.py seed`, and
  `ingestion-worker python worker.py verify`.
- `python -m app.cli check` now verifies both PostGIS and API-to-MinIO liveness via
  `S3_ENDPOINT_URL`.
- `worker.py verify` now verifies the deterministic MinIO keys exist, not just the bucket.
- STAC API health path is `/_mgmt/ping`, not `/_mgmt/health`.
- TiTiler must run on `PORT=8000`; the upstream image defaults to port `80` if not set.

Before starting Phase 2 changes, run the Slice 0/1 validators. If either fails,
fix that regression first.

## Must-read context files

Read these files before coding:

- `docs/mvp-execution-plan.md` — Phase 2 section.
- `docs/emergent-context.md` — latest verified handoff/memory from previous slices.
- `docs/data-ingestion-and-satellite-rules.md` — COG layout, band order, RGB bands, index formulas, reflectance correction, SCL masking, validation checklist.
- `docs/architecture-tech-stack.md` — raster flows and BFF/TiTiler responsibility split.
- `docs/sentinel-2-l2a-cog-prep-runbook.md` — exact SAFE ZIP → analytic/SCL COG process already completed.
- `data/seed/README.md` — seed raster layout.
- `data/seed/stac/sentinel-2-l2a-collection.json` — collection metadata and item-assets conventions.
- `data/seed/stac/sentinel-2-l2a-sample-item.json` — currently placeholder sample item; update it to the real COG scene.
- `services/ingestion/akasha_ingest/{config.py,scene.py,storage.py,catalog.py,seed.py,verify.py}` — current catalog/storage seed flow.
- `services/ingestion/worker.py` — ingestion CLI.
- `services/ingestion/requirements.txt` and `services/ingestion/Dockerfile` — raster prep dependencies already added.
- `infra/docker/docker-compose.yml` — local service wiring, TiTiler/MinIO env.
- `apps/api/app/{main.py,config.py,db.py,cli.py,skeleton.py}` — BFF skeleton and current config patterns.
- `apps/api/requirements.txt` and `apps/api/Dockerfile` — may need raster/stat dependencies for Phase 2 BFF stats.
- `scripts/prepare_sentinel2_l2a_cogs.py` — already generated COGs; do not rewrite unless necessary.
- `scripts/download_sentinel2_l2a_product.py` — full L2A downloader; not needed unless COGs are missing.
- `scripts/smoke-test.py` — extend or add a Phase 2 smoke check if appropriate.
- `scripts/validate_slice0.py` and `scripts/validate_slice1.py` — must continue to pass.

## Current local raster artifacts

The SAFE ZIP → COG process has already succeeded locally. Do **not** re-run the expensive conversion unless outputs are missing.

First, explicitly check whether the ignored raster files below exist in the
environment. If they are missing in Emergent, **do not fabricate COGs, do not
commit placeholders as if they were real, and do not re-download/re-convert the
SAFE product unless the user explicitly asks**. Implement code/metadata changes
that can be validated statically, then report runtime tile/stat validation as
blocked on missing ignored raster artifacts.

Generated, ignored-by-git files:

```text
data/seed/rasters/2025-09-14/analytic.tif
data/seed/rasters/2025-09-14/scl.tif
data/seed/rasters/2025-09-14/prepare_manifest.json
```

These files are intentionally ignored and must not be committed.

`prepare_manifest.json` output summary:

```json
{
  "analytic": {
    "path": "/app/data/seed/rasters/2025-09-14/analytic.tif",
    "crs": "EPSG:32643",
    "bounds": [799980.0, 1290240.0, 909780.0, 1400040.0],
    "resolution": [10.0, 10.0],
    "width": 10980,
    "height": 10980,
    "dtype": "uint16",
    "band_count": 9,
    "nodata": 0.0,
    "descriptions": ["B04", "B08", "B05", "B06", "B07", "B11", "B12", "B03", "B02"]
  },
  "scl": {
    "path": "/app/data/seed/rasters/2025-09-14/scl.tif",
    "crs": "EPSG:32643",
    "bounds": [799980.0, 1290240.0, 909780.0, 1400040.0],
    "resolution": [10.0, 10.0],
    "width": 10980,
    "height": 10980,
    "dtype": "uint8",
    "band_count": 1,
    "nodata": 0.0,
    "descriptions": ["SCL"]
  }
}
```

Host file sizes from the successful run:

- `analytic.tif`: about `2.24 GiB`
- `scl.tif`: about `6.28 MiB`

Both printed as valid COGs:

```text
valid COG: /app/data/seed/rasters/2025-09-14/analytic.tif
valid COG: /app/data/seed/rasters/2025-09-14/scl.tif
COG preparation complete
```

Geographic footprint computed from the raster bounds:

```json
{
  "bbox4326": [77.75127791535229, 11.647042899643449, 78.77093931726162, 12.65022495916365],
  "polygon4326": [
    [77.75127791535229, 11.65842813454628],
    [78.7570038087712, 11.647042899643449],
    [78.77093931726162, 12.63784146528649],
    [77.76149663867514, 12.65022495916365],
    [77.75127791535229, 11.65842813454628]
  ]
}
```

Source product:

```text
S2B_MSIL2A_20250914T050649_N0511_R019_T43PHP_20250914T074457.SAFE
```

Scene metadata to use:

- collection/source: `sentinel-2-l2a`
- satellite/platform: `sentinel-2b`
- product level: `L2A`
- MGRS tile: `43PHP`
- acquisition datetime: `2025-09-14T05:06:49.024000Z`
- acquisition date: `2025-09-14`
- processing baseline: `05.11` (from `N0511`)
- cloud cover from CDSE STAC discovery: `17.153746`

Recommended deterministic scene key:

```text
sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11
```

Recommended item id, if following current `SceneIdentity.item_id` convention:

```text
sentinel-2-l2a_43PHP_20250914_0511
```

Object keys for that legacy single-sample milestone were:

```text
sentinel-2-l2a/2025-09-14/analytic.tif   # legacy sample layout
sentinel-2-l2a/2025-09-14/scl.tif
```

## Raster artifact availability model

Large raster artifacts are intentionally **not** checked into git and will not be
available in normal Railway builds.

Treat the paths as different lifecycle stages:

| Stage | Path | Git? | Runtime source of truth? | Purpose |
|---|---|---:|---:|---|
| Raw SAFE ZIP | `data/raw/sentinel-2-l2a/...SAFE.zip` | No | No | Local/operator reproducible source download |
| Local generated COG staging | `data/seed/rasters/2025-09-14/*.tif` | No | No, except during local seed/upload | Local operator-produced COGs used by `worker.py seed --force` |
| Runtime COGs | `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/*.tif` | No | Yes | MinIO/S3 assets read by TiTiler and the BFF |

For local development, if `data/seed/rasters/2025-09-14/analytic.tif` and
`data/seed/rasters/2025-09-14/scl.tif` exist, ingestion can upload them to MinIO.

For Emergent or Railway builds, do **not** assume these local files exist. Code
must be written so runtime uses STAC asset hrefs/object-storage keys. If local
COGs are missing during validation, report runtime tile/stat validation as
blocked and point to `docs/sentinel-2-l2a-cog-prep-runbook.md` or an operator
upload step. Do not replace missing COGs with fake committed files.

For Railway specifically, use one of these deployment/operator flows before the
Phase 2 smoke test:

1. Preferred MVP path: upload the validated COGs to the Railway MinIO volume or
  compatible object storage at the object keys above, then seed/register STAC
  metadata pointing to those keys.
2. Acceptable local-dev path only: mount/use `data/seed/rasters/...` and run
  `worker.py seed --force` to upload real COGs into local MinIO.
3. Avoid for now: downloading the SAFE ZIP and generating COGs inside Railway;
  this is CPU/disk heavy and requires CDSE credentials at runtime.

## Important constraints

- Do not commit or copy large raster files into git.
- Do not make application runtime depend on `data/raw/`, `data/work/`, or local
  `data/seed/rasters/` paths. Runtime must resolve COGs from STAC/MinIO/S3.
- Do not commit `.env` or secrets.
- Do not rely on deleted/obsolete `data/sentinel-2-global-mosaics` data.
- Do not use `sentinel-2-global-mosaics` for Phase 2 analytic/SCL work.
- Do not combine SCL and reflectance bands into one raster.
- TiTiler is for RGB/display tiles only.
- Cloud-masked index statistics must be computed in FastAPI BFF with rasterio/rio-tiler reading both analytic and SCL COG windows.
- TiTiler `/cog/statistics` is not acceptable for masked stats because it cannot apply a categorical mask from a second COG.
- Apply reflectance correction before index math:
  - raw DN is stored
  - scale = `0.0001`
  - offset = `-0.1`
  - corrected reflectance = `raw * 0.0001 + (-0.1)`
- Do not assume the offset cancels in NDVI; it affects denominators.
- Default excluded SCL classes: `0,1,2,3,7,8,9,10,11`; keep water class `6` included.
- Phase 2 validation must distinguish real COG uploads from Slice 1 empty placeholder
  objects. For Phase 2, the two MinIO objects must have `ContentLength > 0`.
- `data/seed/sample-plot.geojson` is outside the 2025-09-14 raster footprint and
  should **not** be used as the Phase 2 NDVI reference polygon.

Use this deterministic in-footprint polygon for Phase 2 tile/stat smoke tests
unless you compute a better one from the COG footprint:

```json
{
  "type": "Polygon",
  "coordinates": [[
    [78.2, 12.1],
    [78.205, 12.1],
    [78.205, 12.105],
    [78.2, 12.105],
    [78.2, 12.1]
  ]]
}
```

## Implementation tasks

### 1. Update sample scene identity and STAC seed item

Update `services/ingestion/akasha_ingest/scene.py` so `SAMPLE_SCENE` matches the real COG scene:

- `mgrs_tile="43PHP"`
- `acquisition_datetime="2025-09-14T05:06:49.024000Z"`
- `processing_baseline="05.11"`

Update `data/seed/stac/sentinel-2-l2a-sample-item.json` so it matches the generated rasters:

- item id: `sentinel-2-l2a_43PHP_20250914_0511` unless you intentionally keep another deterministic id and update all code accordingly
- `bbox`: `[77.75127791535229, 11.647042899643449, 78.77093931726162, 12.65022495916365]`
- geometry polygon as listed above
- `properties.datetime`: `2025-09-14T05:06:49.024000Z`
- platform: `sentinel-2b`
- `eo:cloud_cover`: `17.153746`
- `proj:epsg`: `32643`
- `proj:shape`: `[10980, 10980]`
- `proj:transform`: `[10, 0, 799980, 0, -10, 1400040, 0, 0, 1]`
- `proj:bbox`: `[799980, 1290240, 909780, 1400040]`
- `s2:mgrs_tile`: `43PHP`
- `s2:processing_baseline`: `05.11`
- `akasha:acquisition_date`: `2025-09-14`
- asset hrefs:
  - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/analytic.tif` (legacy sample layout)
  - `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/scl.tif`
- per-asset `proj:shape`, `proj:transform`, `proj:bbox`, `proj:epsg` should match the rasters
- analytic asset band order remains exactly `[B04,B08,B05,B06,B07,B11,B12,B03,B02]`
- SCL asset remains separate with classification classes `0..11`

If you can safely compute AOI usable/cloud/coverage percentages using SCL, do it; otherwise set conservative placeholder values but mark them clearly for later refinement. Do not leave the old 2026/43PGQ values.

### 2. Ensure MinIO seeding uploads the real COGs

The then-current legacy sample storage code uploaded local rasters if present at:

```text
data/seed/rasters/{acquisitionDate}/analytic.tif   # legacy sample layout
data/seed/rasters/{acquisitionDate}/scl.tif
```

After updating `SAMPLE_SCENE` to `2025-09-14`, `worker.py seed-minio --force` or `worker.py seed --force` should upload the generated real COGs instead of placeholders.

If needed, improve logs/metadata so uploaded objects are distinguishable from placeholders.

### 3. Configure API/BFF and TiTiler access to MinIO COGs

Local Compose already gives TiTiler GDAL S3 settings. Verify and adjust if needed:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_ENDPOINT=minio:9000`
- `AWS_VIRTUAL_HOSTING=FALSE`
- `AWS_HTTPS=NO`
- `AWS_REGION=us-east-1`
- `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`
- `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff`

If the BFF needs to read COGs directly for statistics, add equivalent S3/GDAL/rasterio configuration to the `api` service environment and settings without exposing secrets to the browser.

For the BFF statistics path, configure the API container with the S3/GDAL env it
needs to read MinIO COGs directly (for example `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT`, `AWS_VIRTUAL_HOSTING=FALSE`,
`AWS_HTTPS=NO`, `AWS_REGION`, and/or rasterio session settings). Keep these
server-side only.

### 4. Add minimal Phase 2 BFF endpoints/contracts

Implement the minimum BFF surface needed for Phase 2 verification. Keep it backend-only and avoid full frontend work.

Recommended endpoints:

- `GET /api/config`
- `GET /api/sources`
- `GET /api/sources/{sourceId}/dates`
- `GET /api/layers/default` or equivalent layer endpoint returning a same-origin tile URL template/proxy path for RGB
- `POST /api/indices/statistics`

The layer endpoint should return enough metadata for a client/smoke test to request one true-colour PNG through the gateway/TiTiler.

For RGB display use analytic bands `[1,8,9]` = B04/B03/B02. Do not assume RGB bands 1/2/3.

Inspect the running TiTiler OpenAPI/routes and use the actual TiTiler 1.0 route shape. Do not guess if the route differs; verify with the local service.

Important gateway caveat: the current Caddy gateway proxies `/tiles/*` to TiTiler
with the path preserved. TiTiler does not natively understand Akasha's friendly
`/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png` path unless you add an explicit
rewrite/proxy strategy or serve this friendly route from the BFF/gateway. Implement
the smallest same-origin route that returns a PNG through the public gateway; do
not expose MinIO URLs or credentials to the browser.

### 5. Implement masked NDVI statistics in BFF

Implement only enough statistics logic for the Phase 2 proof:

- Accept a known polygon / GeoJSON geometry request.
- Resolve source/date analytic and SCL assets from STAC or deterministic config.
- Map NDVI to analytic band positions:
  - red = B04 = band 1
  - nir = B08 = band 2
- Read the analytic and SCL windows for the request polygon using rasterio/rio-tiler.
- Apply nodata/out-of-coverage mask.
- Apply SCL exclusion classes `0,1,2,3,7,8,9,10,11`.
- Apply reflectance correction before NDVI:
  - `red_reflectance = red_dn * 0.0001 - 0.1`
  - `nir_reflectance = nir_dn * 0.0001 - 0.1`
- Compute NDVI:
  - `(nir_reflectance - red_reflectance) / (nir_reflectance + red_reflectance)`
- Return normalized JSON with at least:
  - `min`
  - `max`
  - `mean`
  - `stddev`
  - `totalPixels`
  - `nodataPixels`
  - `coveragePixels`
  - `sclExcludedPixels`
  - `validPixels`
  - `validPixelPercent`
  - `cloudMaskedPercent`
  - `coveragePercent`
  - source/date/index metadata

Add practical validation: polygon geometry required, max area enforced if existing config supports it, clear errors for unsupported index/source/date.

### 6. Add validation / smoke tests

Add or update scripts so Phase 2 can be verified locally. Prefer extending `scripts/smoke-test.py` or adding a new focused script like `scripts/validate_slice2.py` if cleaner.

Validation must check:

1. Local stack starts.
2. API health works.
3. STAC collection/item are loaded.
4. MinIO has non-empty real COG objects at the legacy sample keys:
   - `sentinel-2-l2a/2025-09-14/analytic.tif` (legacy sample layout)
   - `sentinel-2-l2a/2025-09-14/scl.tif`
5. TiTiler can render one RGB PNG through the gateway `/tiles/*` path.
6. `POST /api/indices/statistics` returns valid NDVI JSON for a known polygon.
7. Stats are offset-corrected and SCL-masked.
8. Existing Slice 0 and Slice 1 validators still pass after Phase 2 changes.

For a known polygon, do not use the existing sample plot unless you first prove it
intersects the real scene. The current `sample-plot.geojson` is outside the
2025-09-14 raster footprint; use the deterministic in-footprint polygon above or
add a documented replacement fixture.

### 7. Documentation updates

Update relevant docs after implementation:

- `docs/mvp-execution-plan.md` Phase 2 status/notes if applicable
- `docs/sentinel-2-l2a-cog-prep-runbook.md` only if process changed
- `data/seed/README.md` if scene/date changed
- `scripts/README.md` if new validation commands/scripts are added

## Suggested local validation commands

Start from repo root.

These commands assume the ignored local COG staging files exist. If they do not,
do not fabricate them; either run the runbook locally or report the runtime
validation portion as blocked on operator-provided raster artifacts.

Build raster/API images after dependency changes:

```bash
docker compose -f infra/docker/docker-compose.yml build ingestion-worker api
```

If local port `8080` is occupied, use `WEB_PORT=18080` consistently for compose
and smoke commands.

Start required services:

```bash
docker compose -f infra/docker/docker-compose.yml up -d postgis minio stac-api titiler api web
```

Apply app schema:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm api python -m app.cli migrate
```

Seed catalog and MinIO with real COGs:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py seed --force
```

Verify Slice 1 foundation still passes:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify
```

Verify the uploaded COG objects are real, not Slice 1 placeholders:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker python - <<'PY'
import boto3
from akasha_ingest import config
from akasha_ingest.scene import SAMPLE_SCENE

client = boto3.client(
  "s3",
  endpoint_url=config.S3_ENDPOINT_URL,
  aws_access_key_id=config.S3_ACCESS_KEY,
  aws_secret_access_key=config.S3_SECRET_KEY,
  region_name=config.S3_REGION,
)
for key in [SAMPLE_SCENE.analytic_key, SAMPLE_SCENE.scl_key]:
  obj = client.head_object(Bucket=config.BUCKET, Key=key)
  print(key, obj["ContentLength"], obj.get("Metadata", {}))
  assert obj["ContentLength"] > 0, key
PY
```

Then run the new/updated Phase 2 smoke validation. If you add `scripts/validate_slice2.py`, expected command could be:

```bash
python scripts/validate_slice2.py http://localhost:8080
```

or if extending smoke test:

```bash
python scripts/smoke-test.py http://localhost:8080
```

Stop services when done:

```bash
docker compose -f infra/docker/docker-compose.yml stop
```

## Acceptance criteria for this Emergent run

- `data/seed/stac/sentinel-2-l2a-sample-item.json` and `SAMPLE_SCENE` match the real 2025-09-14 / 43PHP generated COGs.
- `worker.py seed --force` uploads the real COG files to MinIO, not empty placeholders.
- STAC API can return the real Sentinel-2 item and its analytic/SCL assets.
- One true-colour RGB tile can be fetched through the gateway/TiTiler as PNG.
- One NDVI statistics request succeeds through the BFF and applies both reflectance offset/scale and SCL masking.
- Phase 2 validation/smoke command is documented and passes locally.
- No secrets or large rasters are committed.
- Existing Slice 0/1 checks are not broken.

If Emergent cannot access ignored raster files, it should still implement the
code/docs/static validation pieces and explicitly mark only the runtime
tile/stat smoke checks as blocked on operator COG upload. It should not downgrade
the requirements or create fake raster assets.

## Out of scope

Do not implement full frontend map UX, auth, custom domains, future sources, Wave 2 ingestion automation, or production Railway deployment hardening in this prompt. Keep this slice focused on raster proof and backend validation.
