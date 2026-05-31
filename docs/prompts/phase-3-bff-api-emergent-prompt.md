# Emergent Prompt — Phase 3 BFF API Implementation

Use this file as the copy/paste prompt for Emergent to build **Phase 3 — BFF API implementation**.

## Phase 3 analysis summary

Phase 3 is **partially complete already** from the Phase 2 raster de-risk work.

Already implemented in `apps/api/`:

- `GET /api/config`
- `GET /api/sources`
- `GET /api/sources/{sourceId}/dates` with AOI cloud/usable-pixel percentages
- `GET /api/layers/default`
- `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png`
- `POST /api/indices/statistics` with validation, max-area enforcement, timeout handling, rate limiting, and normalized response shape
- Standard error shape via `AkashaError`: `{ "error": { "code", "message", "details" } }`
- Shared geometry validation via `app.raster.geo_validate.validate_polygon()`
- Existing PostGIS migration for `akasha.plots`

Still pending for Phase 3:

1. Plot CRUD API endpoints.
2. GeoJSON import/export API endpoints.
3. Tests proving typed frontend-ready payloads, clear invalid/oversized polygon errors, and no internal credential/service leakage.

Important schema mismatch to resolve during implementation:

- Product docs allow GeoJSON `Polygon` and `MultiPolygon`.
- Current migration has `akasha.plots.geometry geometry(Polygon, 4326)`.
- `validate_polygon()` already accepts both `Polygon` and `MultiPolygon`.
- Preferred Phase 3 fix: add an idempotent migration that allows both `Polygon` and `MultiPolygon` without breaking existing rows.

---

## Copy/paste prompt for Emergent

You are working in the Akasha repository. Implement **Phase 3 — BFF API implementation** for the FastAPI backend, but do not rebuild or duplicate already-completed Phase 2 work.

### Current project context

Akasha is a Railway-first satellite imagery visualization MVP for Indian agriculture. The public browser talks only to the `web` gateway; all backend services stay private. The FastAPI BFF owns app-specific APIs and must never expose MinIO URLs, raw COG paths, STAC internals, database URLs, credentials, or private service hostnames to the browser.

Relevant source-of-truth docs:

- `docs/mvp-execution-plan.md` — Phase 3
- `docs/architecture-tech-stack.md` — BFF API contracts and service boundaries
- `docs/product-plan.md` — Wave 1 plot and index acceptance criteria
- `docs/engineering-dos-donts.md` — backend/API guardrails

Current backend structure:

- `apps/api/app/main.py` registers the existing skeleton and product routers.
- `apps/api/app/product.py` already implements `/api/config`, `/api/sources`, `/api/sources/{sourceId}/dates`, `/api/layers/default`, tile proxy, and `/api/indices/statistics`.
- `apps/api/app/db.py` exposes synchronous lazy `psycopg` connection helper `get_connection()`.
- `apps/api/app/raster/errors.py` exposes `AkashaError`, `akasha_error_handler`, and helper constructors such as `bad_request()`, `invalid_geometry()`, `polygon_too_large()`, `not_found()`, etc.
- `apps/api/app/raster/geo_validate.py` exposes `validate_polygon()` and `geodesic_area_ha()`.
- `apps/api/migrations/001_app_schema.sql` already creates `akasha.plots`, `akasha.index_requests`, and `akasha.app_settings`.
- Existing tests are in `apps/api/tests/test_health.py` and `apps/api/tests/test_slice2.py`.

### What is already done — do not redo

Do not rewrite or regress these existing endpoints:

- `GET /api/config`
- `GET /api/sources`
- `GET /api/sources/{sourceId}/dates`
- `GET /api/layers/default`
- `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png`
- `POST /api/indices/statistics`

Only modify these if a small integration update is required, such as registering a new router in `main.py` or updating app version/docstring.

### Required implementation scope

Implement the missing Plot API and GeoJSON import/export surface.

Required endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/plots` | List saved plots, newest first. |
| `POST` | `/api/plots` | Create a named plot from GeoJSON geometry. |
| `GET` | `/api/plots/{plotId}` | Return one saved plot. |
| `PATCH` | `/api/plots/{plotId}` | Update plot name and/or geometry. |
| `DELETE` | `/api/plots/{plotId}` | Delete a plot. |
| `POST` | `/api/plots/import/geojson` | Import one or more GeoJSON Polygon/MultiPolygon features. |
| `GET` | `/api/plots/{plotId}/export.geojson` | Export one plot as a GeoJSON Feature. |

Optional only if simple and tested:

- `GET /api/plots/export.geojson` to export all plots as a FeatureCollection.

### Required payload contracts

Plot response object:

```json
{
  "id": "uuid",
  "name": "North field",
  "geometry": { "type": "Polygon", "coordinates": [] },
  "areaHa": 12.4,
  "createdAt": "2026-05-31T00:00:00Z",
  "updatedAt": "2026-05-31T00:00:00Z"
}
```

`POST /api/plots` request:

```json
{
  "name": "North field",
  "geometry": { "type": "Polygon", "coordinates": [] }
}
```

`PATCH /api/plots/{plotId}` request:

```json
{
  "name": "Renamed field",
  "geometry": { "type": "Polygon", "coordinates": [] }
}
```

Both fields are optional for PATCH, but at least one of `name` or `geometry` must be present.

`POST /api/plots/import/geojson` accepts:

- GeoJSON `FeatureCollection`
- GeoJSON `Feature`
- Raw GeoJSON `Polygon` or `MultiPolygon`

Import response must be frontend-ready and deterministic:

```json
{
  "imported": [
    { "id": "uuid", "name": "Plot A", "geometry": {}, "areaHa": 1.2, "createdAt": "...", "updatedAt": "..." }
  ],
  "rejected": [
    { "index": 1, "code": "POLYGON_TOO_LARGE", "message": "Polygon exceeds maximum area of 50 ha." }
  ],
  "importedCount": 1,
  "rejectedCount": 1
}
```

`GET /api/plots/{plotId}/export.geojson` returns a GeoJSON Feature:

```json
{
  "type": "Feature",
  "id": "uuid",
  "geometry": { "type": "Polygon", "coordinates": [] },
  "properties": {
    "id": "uuid",
    "name": "North field",
    "areaHa": 12.4,
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

Use `application/geo+json` as the response media type for GeoJSON export endpoints.

### Database and migration requirements

Current table in `apps/api/migrations/001_app_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS akasha.plots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    geometry geometry(Polygon, 4326) NOT NULL,
    area_ha double precision,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT plots_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT plots_geometry_valid CHECK (ST_IsValid(geometry))
);
```

Because Wave 1 allows `Polygon` and `MultiPolygon`, add a new idempotent migration, for example:

- `apps/api/migrations/002_plots_polygon_multipolygon.sql`

The migration must:

1. Preserve existing rows.
2. Keep SRID 4326.
3. Allow both `POLYGON` and `MULTIPOLYGON`.
4. Keep topological validity checks.
5. Preserve or recreate the existing GIST index.
6. Use the repo migration separator `--;;` between SQL statements.

Recommended approach:

- Change the column type to `geometry(Geometry, 4326)`.
- Add or replace a check constraint that enforces `GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON')` and `ST_IsValid(geometry)`.
- Keep existing rows as-is; do not force all Polygons into MultiPolygons unless needed.

If the existing constraint name conflicts, drop and recreate it idempotently.

### API implementation requirements

Use existing project patterns:

1. Create a dedicated router module, preferably `apps/api/app/plots.py`.
2. Optionally create a small persistence module, preferably `apps/api/app/plots_repo.py`, to keep raw SQL out of the route handlers.
3. Register the new router in `apps/api/app/main.py`.
4. Bump `APP_VERSION` from `0.2.0-slice2` to `0.3.0-slice3` only if tests pass.
5. Use Pydantic v2 models for request and response schemas.
6. Use `validate_polygon()` for server-side geometry validation and area calculation.
7. Enforce `settings.max_polygon_area_ha` and `settings.max_polygon_vertices` for create, update, and import.
8. Never trust client-provided area values.
9. Store geometry using PostGIS functions such as `ST_SetSRID(ST_GeomFromGeoJSON(...), 4326)`.
10. Read geometry back using `ST_AsGeoJSON(geometry)` and return parsed GeoJSON objects, not strings.
11. Use raw SQL with parameter binding only. Do not string-format user input into SQL.
12. Keep synchronous `psycopg` DB calls out of the event loop by running blocking operations in `anyio.to_thread.run_sync`.
13. Keep `psycopg` imports lazy if you create helper modules.
14. Do not introduce SQLAlchemy or another ORM for Phase 3.
15. Do not add frontend work in this phase.
16. Do not deploy to Railway in this phase.

### Error handling requirements

All application errors must use the existing standard shape:

```json
{ "error": { "code": "INVALID_GEOMETRY", "message": "...", "details": {} } }
```

Use stable codes and appropriate statuses:

| Status | Code examples | Situation |
|---:|---|---|
| `400` | `BAD_REQUEST`, `INVALID_NAME`, `NO_UPDATE_FIELDS`, `INVALID_GEOJSON`, `TOO_MANY_FEATURES` | malformed request or import body |
| `404` | `NOT_FOUND` | plot id does not exist or invalid UUID |
| `413` | `POLYGON_TOO_LARGE` | area exceeds configured max |
| `422` | `INVALID_GEOMETRY` | invalid/self-intersecting/unsupported geometry |
| `503` | `PLOTS_BACKEND_UNAVAILABLE` | database missing/unreachable in preview/dev |

Security requirement:

- Never include raw exception text, `DATABASE_URL`, credentials, internal hostnames, MinIO bucket names, COG paths, stack traces, or SQL text in API responses.
- Log backend details server-side if useful, but response details must be sanitized.

### GeoJSON import rules

- Accept only Polygon/MultiPolygon geometries in EPSG:4326.
- Validate every feature server-side.
- Compute area server-side.
- Name resolution order for imported features:
  1. `properties.name`
  2. `properties.Name`
  3. `properties.title`
  4. fallback `Imported plot N`
- Trim names; reject or sanitize blank names.
- Enforce a bounded maximum import feature count, for example 500, and return a clear `TOO_MANY_FEATURES` error if exceeded.
- Support partial import: valid features should be imported and invalid features should appear in `rejected` with index, code, and message.
- Do not echo very large feature payloads in error responses.

### Files expected to change or be added

Expected:

- `apps/api/app/plots.py`
- `apps/api/app/plots_repo.py` or equivalent helper module
- `apps/api/app/main.py`
- `apps/api/migrations/002_plots_polygon_multipolygon.sql`
- `apps/api/tests/test_slice3.py`

Allowed if useful:

- `apps/api/app/raster/models.py` or a new local model section in `plots.py`
- `apps/api/README.md` only if endpoint docs are updated briefly

Do not modify unrelated frontend files.

### Test requirements

Add `apps/api/tests/test_slice3.py`.

Tests must run without Docker, MinIO, PostGIS, or Railway. Monkeypatch the persistence layer for API contract tests where needed.

Required test coverage:

1. `POST /api/plots` happy path returns 201 and typed plot payload.
2. `GET /api/plots` returns a list of typed plot payloads.
3. `GET /api/plots/{plotId}` returns one plot or 404 with standard error shape.
4. `PATCH /api/plots/{plotId}` updates name and/or geometry.
5. `PATCH /api/plots/{plotId}` with no fields returns 400 `NO_UPDATE_FIELDS`.
6. `DELETE /api/plots/{plotId}` returns 204 on success and 404 on missing plot.
7. Invalid GeoJSON geometry returns 422 `INVALID_GEOMETRY`.
8. Oversized polygon returns 413 `POLYGON_TOO_LARGE`.
9. Too many vertices returns 400 `TOO_MANY_VERTICES`.
10. `POST /api/plots/import/geojson` imports valid features and reports rejected invalid features.
11. `GET /api/plots/{plotId}/export.geojson` returns a GeoJSON Feature with `application/geo+json` media type.
12. Responses never contain `DATABASE_URL`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`, `MINIO`, raw COG paths, or private internal service URLs.

Also run the existing tests to ensure no regressions:

- `apps/api/tests/test_health.py`
- `apps/api/tests/test_slice2.py`

### Validation commands

Run from repository root or from `apps/api` as appropriate:

```bash
cd apps/api
python -m pytest tests/test_health.py tests/test_slice2.py tests/test_slice3.py -q
```

If import paths require it, run with the same pattern already used by the repo tests. Do not require a live database for unit tests.

### Done criteria

Phase 3 is complete only when all of these are true:

- Plot CRUD endpoints exist and return typed frontend-ready JSON.
- GeoJSON import/export endpoints exist and return the specified shapes.
- Invalid polygons fail with clear standard errors.
- Oversized polygons fail with `POLYGON_TOO_LARGE`.
- MultiPolygon support is intentionally handled through the migration and tested, or explicitly documented in tests if rejected. Preferred result is support for both Polygon and MultiPolygon.
- API responses do not expose raw MinIO credentials, object paths, database URLs, private service URLs, stack traces, or SQL.
- Existing Phase 2 endpoints still pass tests.
- `python -m pytest tests/test_health.py tests/test_slice2.py tests/test_slice3.py -q` passes.

### Out of scope

Do not implement:

- Frontend plot drawing UI.
- Terra Draw integration.
- Railway deployment changes.
- Authentication/user accounts.
- Wave 2 analytics or time-series.
- KML/shapefile import.
- New satellite sources.
- Direct browser access to MinIO, STAC, TiTiler, or PostGIS.

### Final response expected from Emergent

After implementation, report:

1. Files changed.
2. Endpoints added.
3. Migration added and why.
4. Tests added.
5. Exact test command run and result.
6. Any remaining limitations or follow-ups.
