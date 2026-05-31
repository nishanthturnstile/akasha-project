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

Next implementation chat should start Phase 1 only: PostGIS/PostGIS schema, pgSTAC/STAC setup, MinIO bucket structure, Sentinel-2 collection seed, and internal service variables. Do not implement raster math, tiles/statistics, product BFF endpoints, or frontend map UX yet.

Before exposing a public Railway demo, review the remaining container scanner warning on `caddy:2.10-alpine` in `infra/gateway/Dockerfile` and either accept it explicitly for the demo or replace the gateway base/image strategy consistently across Dockerfile, validator, service metadata, and docs.
