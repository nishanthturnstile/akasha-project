# `apps/api` — Akasha BFF (FastAPI)

Thin backend-for-frontend / orchestration layer. **Private service** — never
given a public domain. Browser traffic only ever arrives through the `web`
gateway at same-origin `/api/*`.

## Slice 0 scope

This is the **skeleton** only. Implemented endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness for Railway/Compose health checks. |
| GET | `/api/health` | Same payload, reachable through the gateway/ingress. |
| GET | `/api/_skeleton/services` | Multi-service topology + live status overlay. |
| GET | `/api/_skeleton/manifest` | Slice metadata, pinned images, scope, repo tree. |
| GET | `/api/_skeleton/env-matrix` | Documented env-var matrix (placeholders only). |

**Not implemented yet** (later slices, contracts preserved): plot CRUD,
GeoJSON import/export.

## Slice 2 scope (Phase 2 — raster de-risk)

Product surface for the raster proof path. Heavy geospatial deps
(`rasterio`/`shapely`/`pyproj`) are imported **lazily** in `app.raster.*`, so
importing the app never requires them.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | AOI, map defaults, limits, supported indices. |
| GET | `/api/sources` | Satellite/product sources (STAC collections). |
| GET | `/api/sources/{id}/dates` | Acquisition dates + cloud/usable-pixel %. |
| GET | `/api/layers/default` | Default source/date + same-origin RGB tile template. |
| GET | `/api/tiles/{sourceId}/{date}/rgb/{z}/{x}/{y}.png` | BFF→TiTiler proxy; true-colour RGB (`bidx=1,8,9`). COG url/creds stay server-side. |
| POST | `/api/indices/statistics` | Cloud/SCL-masked, offset-corrected index stats computed in the BFF (reads analytic + SCL COG windows with rasterio). |

TiTiler serves RGB display tiles only; masked statistics are computed in the
BFF. When MinIO/COGs/TiTiler are unavailable the tile/stat routes return a
clean `503 RASTER_BACKEND_UNAVAILABLE`. Validate with
`python scripts/validate_slice2.py` and `python -m pytest -q tests`.

## Slice 3 scope (Phase 3 — BFF API: plots)

Plot CRUD + GeoJSON import/export over PostGIS. Geometry is validated
server-side (Polygon/MultiPolygon, validity, max area/vertices) and the area is
always recomputed (never trusted from the client). Blocking psycopg calls run
off the event loop. Migration `002_plots_polygon_multipolygon.sql` relaxes the
`plots.geometry` column to accept both Polygon and MultiPolygon.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/plots` | List saved plots (newest first). |
| POST | `/api/plots` | Create a named plot from a geometry (201). |
| GET | `/api/plots/{plotId}` | Get one plot (404 if missing/invalid id). |
| PATCH | `/api/plots/{plotId}` | Update name and/or geometry (`NO_UPDATE_FIELDS` if neither). |
| DELETE | `/api/plots/{plotId}` | Delete a plot (204, or 404). |
| POST | `/api/plots/import/geojson` | Import FeatureCollection/Feature/raw geometry; partial `imported`+`rejected` (max 500 features). |
| GET | `/api/plots/{plotId}/export.geojson` | Export one plot as a GeoJSON `Feature` (`application/geo+json`). |
| GET | `/api/plots/export.geojson` | Export all plots as a `FeatureCollection`. |

When PostGIS is unreachable (e.g. the Emergent preview has no DB) plot routes
return a sanitized `503 PLOTS_BACKEND_UNAVAILABLE` — no DSN, credentials, SQL,
or stack traces are exposed. Validate with `python -m pytest -q tests`
(`tests/test_slice3.py` monkeypatches the persistence layer, so no DB needed).

## Run locally (standalone)

```bash
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# GET http://localhost:8000/health
```

## Build (Docker)

```bash
docker build -t akasha-api apps/api
docker run -p 8000:8000 akasha-api
```

Listens on `$PORT` (default `8000`) to match `http://api.railway.internal:8000`.
