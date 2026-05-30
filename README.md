# Akasha — Railway MVP

Geospatial MVP for browsing true-colour Sentinel-2 imagery over an Area of
Interest (Bangalore) and computing cloud-masked vegetation-index statistics for
user-drawn plots. Railway-first, but fully portable to Docker Compose / on-prem.

> **Status: Slice 0 — Skeleton.** This repository currently contains the
> multi-service skeleton only: monorepo structure, per-service Dockerfiles,
> health endpoints, local Docker Compose, Railway configuration examples, and
> `.env.example` placeholders. Storage/catalog, raster, BFF product contracts,
> and the map UX are delivered in later slices (see the roadmap below).

## Architecture (one public service)

```
Browser ──> web (Caddy + React SPA)  ── /api/*  ──> api (FastAPI BFF)
                  │                   ── /tiles/* ─> titiler (rio-tiler/GDAL)
                  │
   api ──> stac-api (pgSTAC) ──> postgis (PostgreSQL + PostGIS)
   api ──> titiler ──> minio (S3-compatible COG storage)
   ingestion-worker ──> minio / stac-api / postgis
```

Only the **`web`** gateway is publicly reachable. The browser calls `/api/*`
and `/tiles/*` on that same origin; the gateway proxies to the internal `api`
and `titiler` services. `api`, `titiler`, `stac-api`, `postgis`, and `minio`
are never given a public domain.

## Repository layout

```text
apps/
  frontend/          React + Vite + TypeScript SPA (skeleton; map UX in Slice 4)
  api/               FastAPI BFF (skeleton; /health + /api/_skeleton/*)
services/
  titiler/           TiTiler image/config (RGB display tiles)
  stac-api/          stac-fastapi-pgstac wrapper/config
  ingestion/         Python ingestion worker (no-op skeleton)
infra/
  gateway/           Caddy reverse proxy + multi-stage web Dockerfile
  railway/           Per-service Railway config + env matrix + deploy notes
  docker/            Local docker-compose.yml (dev / on-prem portability)
docs/                Source-of-truth product/architecture/deploy docs
scripts/             validate_slice0.py + smoke-test.py
```

## Services & health endpoints

| Service | Public | Internal port | Health | Image (pinned) |
|---|---:|---:|---|---|
| web (gateway) | yes | 80 | `GET /health` | `caddy:2.8-alpine` + React build |
| api (FastAPI BFF) | no | 8000 | `GET /health` | `python:3.11-slim` |
| titiler | no | 8000 | `GET /healthz` | `ghcr.io/developmentseed/titiler:1.0.0` |
| stac-api | no | 8080 | `GET /_mgmt/health` | `ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2` |
| postgis | no | 5432 | `pg_isready` | `postgis/postgis:16-3.5` |
| minio | no | 9000 | `/minio/health/live` | `minio/minio:RELEASE.2025-10-15T17-29-55Z` |
| ingestion-worker | no | — | CLI | `python:3.11-slim` |

## Run locally (Docker Compose)

```bash
cd infra/docker
cp .env.example .env        # set strong secrets (no defaults)
docker compose up --build
curl http://localhost:8080/health
curl http://localhost:8080/api/health
python ../../scripts/smoke-test.py http://localhost:8080
```

## Validate the skeleton (no Docker required)

```bash
python scripts/validate_slice0.py
```

## Deploy to Railway

Each service is a **separate** Railway service. See
[`infra/railway/README.md`](infra/railway/README.md) for the service→config
matrix, environment variables ([`ENV_MATRIX.md`](infra/railway/ENV_MATRIX.md)),
and the deployment sequence.

## Slice roadmap

| Slice | Focus | Status |
|---|---|---|
| 0 | Repository & service skeleton | **done (this slice)** |
| 1 | Database, catalog & object storage foundation | planned |
| 2 | Raster de-risk (tile + masked NDVI statistic) | planned |
| 3 | BFF API implementation | planned |
| 4 | Frontend map & layer UX | planned |
| 5 | Plot & index UX | planned |
| 6 | Railway deployment hardening | planned |
| 7 | Acceptance & QA | planned |

Engineering guardrails: [`docs/engineering-dos-donts.md`](docs/engineering-dos-donts.md).

---

### Emergent preview note

The Emergent sandbox has no Docker engine, so it runs a single FastAPI process
(mounting `apps/api`) plus a React **Service Skeleton Dashboard** that visualises
this topology live. The Dockerized multi-service stack above is the artifact that
builds and runs on local Docker / Railway.
