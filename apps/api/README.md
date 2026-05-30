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

**Not implemented yet** (later slices, contracts preserved): `/api/config`,
`/api/sources`, `/api/sources/{id}/dates`, `/api/layers/default`, plot CRUD,
GeoJSON import/export, `/api/indices/statistics`. No database / STAC / TiTiler
calls in Slice 0.

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
