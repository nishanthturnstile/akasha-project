# Product Plan

## Product summary

Akasha is a satellite imagery visualization platform for Indian agriculture. The MVP lets users inspect recent usable satellite imagery over a map, browse source/date combinations, draw or import farm plot boundaries, and compute vegetation/moisture index statistics only when requested.

The first build is a self-hosted (Coolify/Azure VM) MVP for fast iteration and demonstration. The architecture remains portable to an on-prem/customer-controlled deployment later by using Dockerized services, S3-compatible object storage, and STAC-based catalog abstractions.

## Product metadata

| Item | Decision |
|---|---|
| Product | Akasha Satellite Imagery Visualization Platform |
| Market | Indian agriculture |
| Initial AOI | Bangalore region |
| MVP imagery source | Sentinel-2 L2A |
| MVP hosting | Self-hosted Coolify (Azure VM) multi-service stack |
| User access model | No in-app accounts/roles in Wave 1; protect deployment with gateway rate limits and optional `GATEWAY_BASIC_AUTH` shared-secret gate; customer data requires the gate |
| Primary index outputs | NDVI, NDRE, NDMI (vegetation moisture), NDWI_GREEN_NIR / Water NDWI (McFeeters) statistics for selected plots |
| Default display | Basemap + latest usable Sentinel-2 true-colour imagery |

## Guiding product principles

1. **Map-first experience:** users should understand the area visually before requesting analytics.
2. **Open-data first:** validate Wave 1 on Sentinel-2 before adding licensed or restricted imagery.
3. **Compute only what is requested:** do not compute or display index layers by default.
4. **Time is first-class:** every satellite layer is tied to acquisition dates and cloud usability.
5. **Source-agnostic UX:** adding a new satellite source should not require frontend rewrites.
6. **No hidden security assumptions:** no app-level auth in Wave 1 does not mean public exposure of internal services; protect the gateway with rate limits and optional `GATEWAY_BASIC_AUTH` shared-secret gate, and do not deploy real/customer data publicly unless the gate is enabled.

## Wave 1 MVP scope

### Map and layer browsing

- Show a basemap covering India/world, centered initially on Bangalore.
- Use Esri `arcgis/imagery` through `@esri/maplibre-arcgis` basemap sessions with a
  referrer-restricted `VITE_ESRI_API_KEY`.
- Overlay Sentinel-2 true-colour imagery above the basemap.
- Provide a layer panel with:
  - source list;
  - acquisition date selector;
  - AOI cloud-cover/usable-pixel indicator per date;
  - layer visibility toggle;
  - opacity control.
- Default to the latest usable Sentinel-2 scene/date for the configured AOI.
- Keep basemap behavior independent from satellite layer toggles.

### Plot tools

- Let users draw, edit, name, and delete polygons.
- Persist named plots in PostGIS for Wave 1.
- Import and export GeoJSON.
- Geometry contract: GeoJSON Polygon/MultiPolygon, EPSG:4326, max area 50 ha, max 5000 vertices; full rules in architecture docs.
- Treat KML and shapefile import as fast-follow unless implementation is trivial.

### Index statistics

- Compute NDVI by default, with NDRE, NDMI (vegetation moisture), and NDWI_GREEN_NIR / Water NDWI (McFeeters) selectable.
- Compute only for the selected polygon, source, and acquisition date.
- Return min, max, mean, standard deviation, valid-pixel percentage, and cloud-masked percentage.
- Exact denominators for `validPixelPercent` and `cloudMaskedPercent` are defined in data-ingestion "Pixel accounting and percentages".
- Optionally render a clipped colorized index overlay for the selected plot after statistics work correctly.

### Cloud usability messaging

- Show AOI-level cloud/usable-pixel percentage for each date.
- Define “latest usable” as the newest date whose usable-pixel percentage meets the default usable-pixel threshold of 70% (`USABLE_PIXEL_THRESHOLD_PERCENT`).
- Explain when no recent usable optical scene exists.

## Out of scope for Wave 1

- User accounts, roles, permissions, and full application-level authentication.
- Automated CDSE/Bhoonidhi ingestion as the default path.
- Sentinel-1 SAR products and ISRO high-resolution layers.
- Multi-season time-series analytics.
- Production-grade agronomic recommendations or crop-specific diagnosis.
- PDF report generation.
- Self-hosted basemap tiles.
- Mobile-native apps.

## Core user journeys

### Browse latest usable imagery

1. User opens the app.
2. Map centers on Bangalore.
3. Basemap loads first.
4. Latest usable Sentinel-2 true-colour imagery appears as an overlay.
5. User checks date/cloud status in the layer panel.

### Compare source/date visually

1. User opens the layer panel.
2. User selects a different acquisition date.
3. Satellite overlay updates without changing the basemap.
4. User adjusts opacity or toggles layers.
5. Wave 2 may add swipe/compare mode for clearer visual comparison.

### Analyze a field plot

1. User draws or imports a polygon.
2. User names the plot.
3. User chooses source/date and index type.
4. App requests statistics for that polygon only.
5. User sees index statistics, valid-pixel percentage, cloud-masked percentage, and a clear legend.

## Non-functional requirements

| Area | Target |
|---|---|
| Tile performance | Warm satellite tiles should feel interactive; target ~300 ms for common AOI views after caching. |
| Index latency | Typical field polygon ≤ 50 ha should return statistics in roughly 3–5 seconds after data is warm. |
| Polygon limits | Enforce configurable max polygon area and request timeouts. |
| Availability | Deployed services expose health checks and restart policies. |
| Data quality | Index values must be cloud-masked and Sentinel-2 offset/scale corrected. |
| Portability | Services should remain Docker-compatible for future Docker Compose/on-prem deployment. |
| Security | Only the `web` (gateway) service is publicly reachable; browser calls `/api/*` and `/tiles/*` on the same public origin, and FastAPI, TiTiler, STAC API, PostGIS, and MinIO are never given a public domain. Gateway rate limits always apply; `GATEWAY_BASIC_AUTH` gates real/customer data. |

## Wave 1 acceptance criteria

- Sentinel-2 true-colour tiles render over Bangalore for at least two acquisition dates.
- Layer panel supports source/date selection, visibility toggles, and opacity.
- GeoJSON plot draw/import/export works.
- Named plots persist in PostGIS.
- NDVI, NDRE, NDMI (vegetation moisture), and NDWI_GREEN_NIR / Water NDWI (McFeeters) statistics return for a drawn polygon.
- Statistics include valid-pixel and cloud-masked percentages.
- Exact denominators for `validPixelPercent` and `cloudMaskedPercent` are defined in data-ingestion "Pixel accounting and percentages".
- Index calculations are verified against an independent reference workflow such as QGIS or a notebook.
- Deployment has health checks green for public web/API and private backing services.
- MinIO, PostgreSQL/PostGIS, TiTiler, and STAC internals are not directly exposed to end users.

## Appendix (not for MVP prompts)

### Target users

- Agronomists and crop advisory teams.
- Agri-input companies and field operations teams.
- Farmer producer organizations and cooperatives.
- Agritech product teams validating satellite workflows.
- Later: crop insurance, government, and large-scale monitoring users.

### Roadmap

#### Wave 1 — MVP

- Manual Sentinel-2 ingestion for Bangalore.
- STAC-backed source/date catalog.
- MapLibre map with basemap and Sentinel-2 overlay.
- Layer/date panel with cloud usability indicators.
- Terra Draw plot tooling.
- Plot persistence in PostGIS.
- On-demand cloud-masked index statistics.
- Deployment with private service networking, volumes, variables, health checks, and rate limits.

#### Wave 2 — Data and analytics expansion

- Automated scheduled ingestion from CDSE and later Bhoonidhi.
- Sentinel-1 SAR product layers for monsoon/cloud fallback.
- Licensed ISRO layers after access, pricing, and licensing are confirmed.
- Per-plot time-series across acquisition dates.
- Date/source compare or swipe mode.
- Clipped index overlays.
- KML/shapefile import.
- Report exports.
- Self-hosted basemap option.
- Optional OIDC/auth layer for customer deployments.
