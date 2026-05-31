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
  - `api python -m app.cli migrate` applies the app schema.
  - `api python -m app.cli check` verifies PostGIS and API-to-MinIO liveness.
  - `ingestion-worker python worker.py seed` runs pgSTAC migration, loads the Sentinel-2 collection/item, and creates the MinIO bucket/keys.
  - `ingestion-worker python worker.py verify` verifies PostGIS, STAC collection availability, and deterministic MinIO keys.
- `worker.py verify` now checks expected MinIO keys exist; it must not silently pass on an empty bucket.
- Phase 1 intentionally may create empty placeholder objects when real COG files are absent. Phase 2 must require non-empty real COG objects.

For Phase 2, use `docs/prompts/phase-2-raster-de-risk-emergent-prompt.md` as the implementation prompt. Key memory for that prompt:

- Real ignored COG artifacts are expected at `data/seed/rasters/2025-09-14/analytic.tif` and `data/seed/rasters/2025-09-14/scl.tif`; do not commit them.
- If those ignored files are missing in the execution environment, do not fabricate results or commit placeholder rasters. Report runtime validation as blocked unless the user explicitly authorizes re-download/re-conversion.
- The current `data/seed/sample-plot.geojson` is outside the real 2025-09-14 raster footprint; use an in-footprint test polygon for NDVI validation.
- Update `SAMPLE_SCENE` and `data/seed/stac/sentinel-2-l2a-sample-item.json` from the old 2026/43PGQ placeholder to the real 2025-09-14/43PHP scene.
- TiTiler is display-only. Cloud/SCL-masked NDVI statistics must be computed in the FastAPI BFF using rasterio/rio-tiler over both analytic and SCL COG windows.
- The gateway currently proxies `/tiles/*` to TiTiler without rewriting. If Phase 2 exposes a friendly `/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png` route, implement and verify the rewrite/proxy path explicitly.

Do not proceed to full frontend map UX, plot CRUD UX, auth, custom domains, Wave 2 ingestion automation, or Railway hardening in Phase 2.
