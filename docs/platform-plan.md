# Akasha Platform Plan

This file is the current documentation index for the Akasha platform. Historical product/MVP/Emergent slice docs have been archived under [`archive/`](./archive/) so active work stays easy to find without losing traceability.

## Prompt slicing for Emergent.sh

Do not include every document in every Emergent prompt; use the prompt-slice table below.

| Slice | Goal | Include (docs/sections) | Exclude |
|---|---|---|---|
| 0 Skeleton | Monorepo, Dockerfiles, health, compose, env examples | historical context: `archive/emergent-context.md`; architecture: architecture goal/component responsibilities/tech choices/repo layout; deployment: local dev + env names; historical execution: `archive/mvp-execution-plan.md` Phase 0 | formulas, STAC depth, frontend UX, Wave 2 |
| 1 Storage/catalog | PostGIS, MinIO, STAC collection seed, buckets | architecture: data model boundaries; data-ingestion: STAC metadata + seed layout; deployment: PostGIS/MinIO env; execution Phase 1 | frontend, plot drawing, Wave 2 ingestion |
| 2 Raster proof | 1 ResourceSat FCC tile + 1 masked offset-corrected NDVI stat vs reference | data-ingestion: COG layout/band order/FCC bands/formulas/reflectance correction/mask/stats engine; architecture: raster flows/runtime decisions; execution Phase 2 | full frontend UX, auth, custom domains, future sources |
| 3 BFF contracts | All Wave 1 endpoints | architecture: BFF API contracts; product: acceptance; backend engineering guardrails | full deploy, Wave 2 |
| 4 Frontend map | Map + layer/date panel | product: map browsing + journeys; architecture: frontend + tile URL contract; frontend engineering guardrails | ingestion automation, Wave 2 |
| 5 Plot/index UX | Draw/import, named plots, index panel | product: plot/index sections; architecture API contracts; frontend and backend engineering guardrails | Wave 2 analytics |
| 6 Deploy | Services, exposure, env, volumes, health, smoke | deployment full; architecture topology; execution Phase 6 | product roadmap |
| 7 QA/demo | Acceptance + reference check | product acceptance; execution Phase 7; data-ingestion validation checklist | future roadmap |

## Source-of-truth boundaries

| Topic | Owning file |
|---|---|
| Product goals, UX, acceptance criteria | `india-specific-productization-plan.md`, `map-screen-redesign.md`, `design-system.md`, plus active plans in `impl-plan/` |
| Services, architecture, stack, API shape | `architecture-tech-stack.md` |
| Imagery sources, COGs, STAC metadata, index math | `data-ingestion-and-satellite-rules.md` |
| ResourceSat LISS-3 BOA ingestion and COG prep | `impl-plan/isro-bhoonidhi-ingestion-phase-plan.md` |
| Deployment service setup and runtime operations | `infra/selfhosted/README.md` |
| Implementation order | active plans in `impl-plan/`; completed/superseded plans in `impl-plan/archive/` |
| Engineering rules and anti-patterns | `engineering-dos-donts.md` |

If two files appear to conflict, prefer the narrower source-of-truth file for that topic.

Historical product planning, early MVP sequencing, and Emergent handoff context live in [`archive/`](./archive/). Treat them as preserved history, not active product direction.

## Current direction snapshot

- Self-hosted Coolify (Azure VM) MVP, Docker-compatible for future on-prem/customer-controlled deployment.
- ResourceSat-2A LISS-3 BOA first, Bangalore 60 km AOI first.
- React/TypeScript + MapLibre + Terra Draw frontend.
- FastAPI BFF.
- TiTiler for COG display tiles; the BFF computes masked statistics with rasterio/rio-tiler/GDAL.
- STAC/pgSTAC catalog.
- PostgreSQL/PostGIS for plots and catalog backend.
- MinIO/S3-compatible storage for COGs.
- Only the `web` (gateway) service is publicly reachable. The browser calls `/api/*` and `/tiles/*` on the **same public origin**; the gateway proxies them to the internal `api` and `titiler` services. FastAPI, TiTiler, STAC API, PostGIS and MinIO are **never** given a public domain.
