# `infra/docker` — Local development with Docker Compose

This Compose file mirrors the Railway topology so the architecture stays
portable to Docker Compose / on-prem. It is the **local-dev / portability**
artifact — **not** the Railway production runtime (Railway uses separate
services, each with its own `railway.json`).

## Quick start

```bash
cd infra/docker
cp .env.example .env          # edit secrets (no defaults!)
docker compose up --build
```

Then:

```bash
curl http://localhost:8080/health           # web gateway -> ok
curl http://localhost:8080/api/health       # proxied to api -> {"status":"ok"}
curl http://localhost:8080/api/_skeleton/services
```

## Topology

| Service | Public | Port (internal) | Health | Volume |
|---|---:|---:|---|---:|
| web (Caddy + SPA) | yes (`${WEB_PORT}`) | 80 | `GET /health` | — |
| api (FastAPI BFF) | no | 8000 | `GET /health` | — |
| titiler | no | 8000 | `GET /healthz` | — |
| stac-api | no | 8080 | `GET /_mgmt/ping` | — |
| postgis | no | 5432 | `pg_isready` | `postgis_data` |
| minio | no | 9000/9001 | `/minio/health/live` | `minio_data` |
| ingestion-worker | no | — | one-shot CLI | — |

Only `web` publishes a host port; everything else is private to the `akasha`
network.

## Reset local volumes (one command)

```bash
docker compose down -v
```

> Slice 0 ships the service skeleton. `stac-api` requires pgSTAC schema +
> seed data (Slice 1) and `titiler` requires COGs in MinIO (Slice 2) before
> they serve real catalog/tiles; their containers still start and expose
> health endpoints.
