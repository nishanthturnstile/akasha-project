# MVP Execution Plan

## Execution strategy

Build the MVP from the inside out: data/raster proof first, then API contracts, then frontend UX, then Railway hardening. Do not spend time polishing the map UI until one COG tile and one cloud-masked index statistic are proven end to end.

## Phase 0 — Repository and service skeleton

Deliverables:

- Monorepo structure with `apps/frontend`, `apps/api`, `services/titiler`, `services/stac-api`, `services/ingestion`, and `infra` folders.
- Dockerfile per deployable service.
- Local Docker Compose for development.
- Railway-ready service configuration examples.
- `.env.example` files with placeholders only.
- Shared formatting/linting conventions.

Prompt inputs — Include: emergent-context; architecture: architecture goal/component responsibilities/tech choices/repo layout; railway: local dev + env names; execution Phase 0
Slice mapping: Phase 0 → Slice 0
Prompt inputs — Exclude: formulas, STAC depth, frontend UX, Wave 2
Validation: services start locally; `/health` works for frontend/gateway, API, TiTiler, and STAC API where applicable.
Do not proceed until: Services start locally and `/health` works for frontend/gateway, API, TiTiler, and STAC API where applicable.

Exit criteria:

- Services start locally.
- `/health` works for frontend/gateway, API, TiTiler, and STAC API where applicable.

## Phase 1 — Database, catalog, and object storage foundation

Deliverables:

- PostgreSQL/PostGIS schema for plots.
- pgSTAC/STAC setup for catalog data.
- MinIO bucket structure for COG assets.
- Seed script for Sentinel-2 collection metadata.
- Internal service variables for MinIO/PostGIS/STAC.

Prompt inputs — Include: architecture: data model boundaries; data-ingestion: STAC metadata + seed layout; railway: PostGIS/MinIO env; execution Phase 1
Slice mapping: Phase 1 → Slice 1
Prompt inputs — Exclude: frontend, plot drawing, Wave 2 ingestion
Validation: PostGIS is verified; STAC API can return the Sentinel-2 collection; MinIO bucket is reachable from API/ingestion containers.
Do not proceed until: PostGIS is verified, STAC API can return the Sentinel-2 collection, and MinIO bucket is reachable from API/ingestion containers.

Exit criteria:

- PostGIS is verified.
- STAC API can return the Sentinel-2 collection.
- MinIO bucket is reachable from API/ingestion containers.

## Phase 2 — Raster de-risk milestone

Deliverables:

- Convert or place first analytic COG and SCL COG.
- Register one STAC item with correct asset metadata.
- Configure TiTiler to read MinIO via S3-compatible GDAL settings.
- Render one true-colour tile through TiTiler.
- Compute one cloud-masked NDVI statistic for a known polygon.
> Cloud-masked index statistics are computed in the **BFF (FastAPI) using rasterio/rio-tiler**, not by
> plain TiTiler `/cog/statistics`. The BFF reads the analytic COG window and the SCL COG window for the
> request polygon, applies per-band scale/offset, applies the SCL mask, then computes
> min/max/mean/stddev and the pixel-percentage fields. **TiTiler serves RGB display tiles (and
> optional index *display* overlays) only — it is not used for masked statistics**, because vanilla
> TiTiler `/cog/statistics` takes a single `url` and cannot apply a categorical mask from a second COG.

Prompt inputs — Include: data-ingestion: COG layout/band order/RGB bands/formulas/reflectance correction/SCL masking/stats engine; architecture: raster flows/runtime decisions; execution Phase 2
Slice mapping: Phase 2 → Slice 2
Prompt inputs — Exclude: full frontend UX, auth, custom domains, future sources
Validation: one RGB tile returns a PNG; one `/api/indices/statistics` returns valid JSON with NDVI stats; result is compared against QGIS/notebook reference.
Do not proceed until: Tile renders with sensible RGB rescale, statistics are offset-corrected and SCL-masked, and result is compared against QGIS/notebook reference.

Exit criteria:

- Tile renders with sensible RGB rescale.
- Statistics are offset-corrected and SCL-masked.
- Result is compared against QGIS/notebook reference.

This phase is the biggest technical risk reducer. Complete it before major frontend work.

### Phase 2 status — Emergent build (statically + synthetically validated)

DELIVERED & validated (no Docker required):

- STAC sample item re-pointed to the **real** scene
  `S2B_MSIL2A_20250914T050649_N0511_R019_T43PHP` (key
  `sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11`), with correct
  `proj:*`, frozen 9-band `eo:bands`, and `raster:bands` scale `0.0001`/offset `-0.1`.
- BFF raster package `apps/api/app/raster/*`: index registry (NDVI/NDRE/NDMI/
  NDWI_GREEN_NIR), STAC band-name→position mapping (RGB = `[1,8,9]`), a
  **pure-numpy masked-statistics engine** (offset/scale correction + SCL mask +
  pixel accounting), a lazy rasterio dual-COG window reader, a geometry
  validator (area/vertex guardrails), and the standard `{error:{code,message,
  details}}` shape.
- Product endpoints: `GET /api/config`, `/api/sources`, `/api/sources/{id}/dates`,
  `/api/layers/default`, `GET /api/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png`
  (BFF→TiTiler proxy, RGB `bidx=1,8,9`, COG url/creds kept server-side), and
  `POST /api/indices/statistics`.
- TiTiler `PORT=8000` fix + api S3/GDAL env so rasterio can read MinIO COGs.
- De-risk proof: the NDVI math is verified against a hand-computed reference
  (red_dn 2000→0.1, nir_dn 4000→0.3 ⇒ **NDVI 0.5**, offset *does not* cancel) and
  a **full synthetic dual-COG read→reproject→mask→stat pipeline** in
  `scripts/validate_slice2.py` and `apps/api/tests/test_slice2.py`.

BLOCKED until operator COGs are uploaded to MinIO on Railway / local Docker
(the live Emergent container has neither Docker, MinIO, nor the 2.24 GiB COGs):

- Render a real RGB PNG tile through TiTiler/gateway.
- Compute the real cloud-masked NDVI statistic for the reference polygon and
  compare it against a QGIS/notebook reference.
- Verify with `python services/ingestion/worker.py verify-cogs` (asserts both
  COG objects exist and are non-empty real COGs, not Slice 1 placeholders).

The BFF returns a clean `503 RASTER_BACKEND_UNAVAILABLE` for the tile/stat routes
in any environment where MinIO/COGs are absent, so the contract is exercisable
end-to-end without fabricating raster data.

## Phase 3 — BFF API implementation

Deliverables:

- `/api/config`.
- `/api/sources`.
- `/api/sources/{sourceId}/dates` with AOI cloud/usable-pixel percentages.
- Plot CRUD endpoints.
- GeoJSON import/export endpoints.
- `/api/indices/statistics` with validation, max-area enforcement, timeout handling, and normalized response shape.

Prompt inputs — Include: architecture: BFF API contracts; product: acceptance; dos-donts backend rules
Slice mapping: Phase 3 → Slice 3
Prompt inputs — Exclude: full Railway deploy, Wave 2
Validation: API returns typed, frontend-ready payloads; invalid polygons and oversized polygons fail with clear errors; API never exposes raw MinIO credentials or direct internal service details.
Do not proceed until: API returns typed, frontend-ready payloads; invalid polygons and oversized polygons fail with clear errors; API never exposes raw MinIO credentials or direct internal service details.

Exit criteria:

- API returns typed, frontend-ready payloads.
- Invalid polygons and oversized polygons fail with clear errors.
- API never exposes raw MinIO credentials or direct internal service details.

## Phase 4 — Frontend map and layer UX

Deliverables:

- MapLibre map centered on Bangalore.
- Basemap source configured.
- Satellite tile overlay from API-provided tile metadata.
- Layer panel with source/date selector, cloud indicator, visibility toggle, and opacity.
- Loading, empty, and error states.

Prompt inputs — Include: product: map browsing + journeys; architecture: frontend + tile URL contract; dos-donts frontend
Slice mapping: Phase 4 → Slice 4
Prompt inputs — Exclude: ingestion automation, Wave 2
Validation: user can switch dates without disturbing the basemap; the latest usable scene is selected by default; frontend has no hard-coded COG URLs.
Do not proceed until: User can switch dates without disturbing the basemap, the latest usable scene is selected by default, and frontend has no hard-coded COG URLs.

Exit criteria:

- User can switch dates without disturbing the basemap.
- The latest usable scene is selected by default.
- Frontend has no hard-coded COG URLs.

## Phase 5 — Plot and index UX

Deliverables:

- Terra Draw polygon draw/edit flow.
- GeoJSON import/export.
- Named plot save/list/delete flow.
- Index selector for NDVI, NDRE, NDMI, NDWI_GREEN_NIR.
- Statistics panel with min/max/mean/stddev, valid-pixel percentage, cloud-masked percentage, and legend.

Prompt inputs — Include: product: plot/index sections; architecture API contracts; dos-donts frontend+backend
Slice mapping: Phase 5 → Slice 5
Prompt inputs — Exclude: Wave 2 analytics
Validation: drawn/imported polygon can be analyzed; index request uses selected source/date; user sees clear cloud/no-data messaging.
Do not proceed until: Drawn/imported polygon can be analyzed, index request uses selected source/date, and user sees clear cloud/no-data messaging.

Exit criteria:

- Drawn/imported polygon can be analyzed.
- Index request uses selected source/date.
- User sees clear cloud/no-data messaging.

## Phase 6 — Railway deployment hardening

Deliverables:

- Railway services configured separately.
- Persistent volumes attached to PostGIS and MinIO.
- Only web/gateway public.
- Health checks configured.
- Internal service URLs use Railway private networking.
- Rate limits and request-size limits configured.
- Seed data loaded in production environment.
- A repo `scripts/smoke-test` (cross-platform Python or ps1) must check, in order: `/health` of web+api+titiler+stac-api → `/api/config` → `/api/sources` → `/api/sources/{id}/dates` → `/api/layers/default` → one RGB tile returns a PNG → one `/api/indices/statistics` returns valid JSON with NDVI stats. Plus unit tests: index formula/band-position mapping, geometry validation, error shape; and a frontend component smoke test.

Prompt inputs — Include: railway full; architecture topology; execution Phase 6
Slice mapping: Phase 6 → Slice 6
Prompt inputs — Exclude: product roadmap
Validation: Railway deployment is green; smoke test passes from public web URL; internal services are not directly reachable publicly; smoke-test checks pass.
Do not proceed until: Railway deployment is green, smoke test passes from public web URL, and internal services are not directly reachable publicly.

Exit criteria:

- Railway deployment is green.
- Smoke test passes from public web URL.
- Internal services are not directly reachable publicly.

## Phase 7 — Acceptance and QA

Deliverables:

- Manual QA checklist completed.
- Reference index comparison documented.
- Known limitations documented in app copy/readme.
- Demo dataset and reset instructions available.
- Smoke-test checks pass: `/health` of web+api+titiler+stac-api → `/api/config` → `/api/sources` → `/api/sources/{id}/dates` → `/api/layers/default` → one RGB tile returns a PNG → one `/api/indices/statistics` returns valid JSON with NDVI stats. Plus unit tests: index formula/band-position mapping, geometry validation, error shape; and a frontend component smoke test.

Prompt inputs — Include: product acceptance; execution Phase 7; data-ingestion validation checklist
Slice mapping: Phase 7 → Slice 7
Prompt inputs — Exclude: future roadmap
Validation: product acceptance criteria in `product-plan.md` pass; no critical security/data-exposure issues remain; smoke-test checks pass; MVP is ready for demo/pilot use with non-sensitive data.
Do not proceed until: Product acceptance criteria in `product-plan.md` pass, no critical security/data-exposure issues remain, and the MVP is ready for demo/pilot use with non-sensitive data.

Exit criteria:

- Product acceptance criteria in `product-plan.md` pass.
- No critical security/data-exposure issues remain.
- The MVP is ready for demo/pilot use with non-sensitive data.
