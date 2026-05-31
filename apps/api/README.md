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
