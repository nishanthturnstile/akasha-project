# Local Slice 2 Raster Validation — 2026-05-31

Validated on Windows with Docker Desktop using the local Compose topology in
`infra/docker/docker-compose.yml` and gateway port `18080`.

## Required ignored raster artifacts

These files are intentionally ignored by Git and must exist locally before
running the real raster/storage checks:

| Path | Size | SHA-256 |
|---|---:|---|
| `data/seed/rasters/2025-09-14/analytic.tif` | 2,410,275,199 bytes | `febd2c776a7613879fa50147d450e283a1601d2e94089f2995b7df37e15dc268` |
| `data/seed/rasters/2025-09-14/scl.tif` | 6,581,080 bytes | `b9ec25438629611453b9682e9b7530e202bdcba096accb87f754be0bf095ff27` |
| `data/seed/rasters/2025-09-14/prepare_manifest.json` | 1,806 bytes | `a9fea95cec760314a668b27ad3fe89c3ad6c589205fbd90af6b043bedf3a3b02` |

## Local COG metadata validation

Both COGs were opened with `rasterio` before upload:

- analytic: EPSG:32643, 10980x10980, 9 bands, `uint16`, nodata `0`, overviews `[2, 4, 8, 16, 32]`
- SCL: EPSG:32643, 10980x10980, 1 band, `uint8`, nodata `0`, overviews `[2, 4, 8, 16, 32]`
- CRS, transform, width, and height match between analytic and SCL.

## Validation results

Commands run from the repository root:

```bash
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
python -m pytest -q apps/api/tests
python -m ruff check apps/api services/ingestion scripts/validate_slice0.py scripts/validate_slice1.py scripts/validate_slice2.py scripts/smoke-test.py
git diff --check
```

Results:

- Slice 0 validator: 94 passed / 0 failed
- Slice 1 validator: 67 passed / 0 failed
- Slice 2 validator: 76 passed / 0 failed
- API tests: 24 passed / 0 failed
- Ruff: passed
- Whitespace diff check: passed

## Local Docker storage flow

The local Compose env was initialized with local-only credentials in
`infra/docker/.env` and `WEB_PORT=18080`.

The local stack was reset once to avoid stale PostGIS credentials in the named
volume:

```bash
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml down -v
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml up --build -d
```

Then the app schema, catalog, and storage were seeded:

```bash
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml exec -T api python -m app.cli migrate
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml exec -T api python -m app.cli check
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py seed --force
WEB_PORT=18080 docker compose --env-file infra/docker/.env -f infra/docker/docker-compose.yml run --rm ingestion-worker python worker.py verify-cogs
```

`verify-cogs` result: 4/4 passed.

Uploaded MinIO keys (legacy single-sample layout used by this historical Slice 2 validation; manifest-driven production keys include `{date}/{mgrsTile}/`):

- `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/analytic.tif` (legacy sample layout)
- `s3://akasha-cogs/sentinel-2-l2a/2025-09-14/scl.tif`

## Strict smoke test

Strict smoke test was run through the gateway:

```bash
python scripts/smoke-test.py http://localhost:18080 --require-raster
```

Result: 10 passed / 0 failed / 0 blocked.

The real raster path was validated with:

- RGB PNG tile: `/api/tiles/sentinel-2-l2a/2025-09-14/rgb/12/2937/1909.png`
- NDVI statistics: `POST /api/indices/statistics`

## Notes

- `12/2937/1909` is the in-footprint WebMercator tile for the Phase 2 sample polygon center.
- `12/2937/1881` is outside the scene footprint and correctly returned a TiTiler 404 through the BFF.
- Rasterio MinIO reads require `rasterio.session.AWSSession`; direct `rasterio.Env(AWS_...)` credential options fail in this stack.