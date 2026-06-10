# Emergent.sh Context

Use this file as the short prompt wrapper for Emergent.sh. The actual requirements live in the source-of-truth files linked from [`platform-plan.md`](./platform-plan.md).

## Prompt

Build the Akasha Railway MVP incrementally, one slice at a time. Use the docs in this folder as source of
truth, but include ONLY the documents/sections listed for the current slice in the prompt-slice table in
platform-plan.md. Build only the requested slice — do not implement future phases or Wave 2 features unless
they are explicitly included. Preserve the API/data contracts established by previous slices. Generate a
Dockerized multi-service application (not one collapsed service). Follow engineering-dos-donts.md as hard
guardrails.

Prove the raster slice (Slice 2) before any frontend polish: TiTiler renders one true-colour tile from a
COG in MinIO, and the BFF returns one cloud-masked, offset-corrected NDVI statistic for a polygon.

## Next-chat handoff after Phase 0 verification

Phase 0/Slice 0 skeleton has been verified locally from this repository state:

- `python scripts/validate_slice0.py` passes with `94` checks and `0` failures.
- `apps/api` unit tests pass (`6/6`).
- `apps/frontend` locked install, lint, and Vite build pass with `yarn@1.22.22`.
- Local Docker Compose passes on alternate host port `18080` when `8080` is already occupied.
- Gateway smoke test passes: `/health`, `/api/health`, `/api/_skeleton/services`, and `/api/_skeleton/manifest`.
- Internal TiTiler health is `GET /healthz` on port `8000`; set `PORT=8000` because the upstream image defaults to port `80`.
- Internal STAC API health is `GET /_mgmt/ping` for `stac-fastapi-pgstac:5.0.2`; do not use `/_mgmt/health`.
- Local Compose intentionally uses pinned upstream images directly for TiTiler and STAC API to avoid exporting huge no-op wrapper images; Railway still uses the per-service Dockerfiles.

Historical note: the next implementation chat after this section was Phase 1.
Phase 1 has since been reviewed and locally verified; use the newer Phase 1
handoff below for the current state.

Before exposing a public Railway demo, review the remaining container scanner warning on `caddy:2.10-alpine` in `infra/gateway/Dockerfile` and either accept it explicitly for the demo or replace the gateway base/image strategy consistently across Dockerfile, validator, service metadata, and docs.

## Next-chat handoff after Phase 1 verification

Phase 1/Slice 1 storage/catalog work has been reviewed and validated locally:

- `python scripts/validate_slice0.py` passes with `94` checks and `0` failures.
- `python scripts/validate_slice1.py` passes with `67` checks and `0` failures.
- `python -m pytest -q apps/api/tests` passes (`6/6`).
- `ruff check apps/api services/ingestion scripts/validate_slice1.py scripts/validate_slice0.py` passes.
- `apps/frontend` lint/build still passes with `yarn@1.22.22`.
- Local Docker clean-stack verification passed:
  - `api python -m app.cli db upgrade` applies the app schema.
  - `api python -m app.cli check` verifies PostGIS and API-to-MinIO liveness.
  - `ingestion-worker python worker.py seed` runs pgSTAC migration, loads the Sentinel-2 collection/item, and creates the MinIO bucket/keys.
  - `ingestion-worker python worker.py verify` verifies PostGIS, STAC collection availability, and deterministic MinIO keys.
- `worker.py verify` now checks expected MinIO keys exist; it must not silently pass on an empty bucket.
- Phase 1 intentionally may create empty placeholder objects when real COG files are absent. Phase 2 must require non-empty real COG objects.

For Phase 2, use `docs/prompts/phase-2-raster-de-risk-emergent-prompt.md` as the implementation prompt. Key memory for that prompt:

- Legacy sample COG artifacts were expected at `data/seed/rasters/2025-09-14/analytic.tif` and `data/seed/rasters/2025-09-14/scl.tif`; do not commit them. Manifest-driven production scenes now use `data/seed/rasters/{date}/{mgrsTile}/`.
- If those ignored files are missing in the execution environment, do not fabricate results or commit placeholder rasters. Report runtime validation as blocked unless the user explicitly authorizes re-download/re-conversion.
- The current `data/seed/sample-plot.geojson` is outside the real 2025-09-14 raster footprint; use an in-footprint test polygon for NDVI validation.
- Update `SAMPLE_SCENE` and `data/seed/stac/sentinel-2-l2a-sample-item.json` from the old 2026/43PGQ placeholder to the real 2025-09-14/43PHP scene.
- TiTiler is display-only. Cloud/SCL-masked NDVI statistics must be computed in the FastAPI BFF using rasterio/rio-tiler over both analytic and SCL COG windows.
- The gateway currently proxies `/tiles/*` to TiTiler without rewriting. If Phase 2 exposes a friendly `/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png` route, implement and verify the rewrite/proxy path explicitly.

Do not proceed to full frontend map UX, plot CRUD UX, auth, custom domains, Wave 2 ingestion automation, or Railway hardening in Phase 2.

## Next-chat handoff after Phase 2 verification

Phase 2/Slice 2 (raster de-risk) has been implemented and statically + synthetically validated from this repository state (no Docker available in the Emergent container):

- `python scripts/validate_slice0.py` passes (`94/0`).
- `python scripts/validate_slice1.py` passes (`67/0`, scene constants updated to the real 2025-09-14/43PHP scene).
- `python scripts/validate_slice2.py` passes (`76/0`), including a full **synthetic dual-COG** read→reproject→mask→stat pipeline.
- `python -m pytest -q apps/api/tests` passes (`24/24` = 6 Slice 0/1 + 18 Slice 2).
- `python scripts/smoke-test.py <base>` passes `8/0` with `2 BLOCKED` (RGB tile + statistics return a clean `503 RASTER_BACKEND_UNAVAILABLE` because MinIO/COGs/TiTiler are absent in the preview).

What was built:

- `SAMPLE_SCENE` and `data/seed/stac/sentinel-2-l2a-sample-item.json` now describe the real scene `sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11` (EPSG:32643, 10980×10980, scale 0.0001/offset −0.1, frozen 9-band `eo:bands`). AOI usable/cloud/coverage are flagged `akasha:metrics_provisional` — recompute per-AOI from the SCL COG during real ingestion.
- BFF raster package `apps/api/app/raster/*` (heavy deps imported lazily): `indices`, pure-numpy `statistics_core`, `catalog_resolver` (STAC API + seed-JSON fallback), `raster_reader` (rasterio dual-COG windows + GDAL/S3), `tiles` (TiTiler RGB url + proxy), `geo_validate`, `errors`, `models`, `service`.
- Endpoints: `GET /api/config|sources|sources/{id}/dates|layers/default`, `GET /api/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png` (BFF→TiTiler proxy under `/api/` so it is reachable behind the Emergent ingress; COG url/creds hidden), `POST /api/indices/statistics`.
- Infra: `docker-compose` titiler `PORT=8000`; api service gets AWS_*/GDAL env so rasterio can read MinIO COGs; `apps/api/requirements.txt` pins `rasterio/rio-tiler/shapely/pyproj/numpy`; api Dockerfile installs `libexpat1`.
- Ingestion: `storage.seed_keys` tags real uploads (`akasha-placeholder=false`) vs Slice 1 empty placeholders; new `storage.verify_real_cogs`, `verify.run_phase2`, and `worker.py verify-cogs` (assert both COG objects exist and are non-empty real COGs).

BLOCKED runtime exit criteria (run on Railway / local Docker with operator COGs):

- For manifest-driven scenes, run `python worker.py ingest-manifest` and verify with `python worker.py verify-manifest-cogs`; dynamic object keys are `s3://akasha-cogs/sentinel-2-l2a/{date}/{mgrsTile}/{sceneComponent}/...` (see `docs/sentinel-2-l2a-cog-prep-runbook.md`). Use `verify-cogs` only for the legacy sample scene.
- Render a real RGB PNG tile via the gateway and compute the real cloud-masked NDVI for `data/seed/phase2-ndvi-sample-polygon.geojson`, comparing against a QGIS/notebook reference.

Note: the live preview keeps `skeleton.SLICE = 0` (so existing Slice 0 tests stay green and the dashboard is unchanged); only the roadmap status data was advanced (slice0/1 done, slice2 active). `APP_VERSION` is `0.2.0-slice2`.

Do not proceed to full frontend map UX, plot CRUD UX, auth, custom domains, or Railway hardening in Phase 2.
