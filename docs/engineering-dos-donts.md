# Engineering Do's and Don'ts

## Purpose

This is the concise implementation guardrail checklist for Akasha. Concise guardrails; full detail lives in the owning source-of-truth doc.

## Product behavior

### Do

- Do show true-colour satellite imagery by default; indices are requested after plot selection/drawing.
- Do keep source/date selection visible and show AOI cloud/usable-pixel percentages.
- Do report valid-pixel and cloud-masked percentages with every index result.
- Do provide clear empty/error messages when no usable optical image exists.

### Don't

- Don't show NDVI or any index as the default map layer.
- Don't imply NDVI is a full crop-health diagnosis by itself.
- Don't hide cloud/no-data limitations from the user.
- Don't build user accounts/roles in Wave 1 unless explicitly re-scoped.

## Frontend and map

### Do

- Do use MapLibre GL JS and Terra Draw with the MapLibre adapter.
- Do keep basemap and satellite overlays as separate map sources/layers.
- Do derive layer/date/tile metadata from the BFF and keep the map usable while tiles load.
- Do include loading, empty, and failed-request states for layers and statistics.

### Don't

- Don't use `@mapbox/mapbox-gl-draw`; it targets Mapbox GL rather than the selected MapLibre-native drawing path.
- Don't hard-code MinIO object URLs or COG paths in frontend code.
- Don't let the browser talk directly to MinIO, PostGIS, STAC, or TiTiler.
- Don't use OpenStreetMap public tile servers for production-scale/commercial traffic.
- Don't make opacity stacking the only comparison UX forever; prefer swipe/compare in Wave 2.

## Backend/API

### Do

- Do keep FastAPI as a thin BFF/orchestration layer.
- Do validate all GeoJSON geometry server-side and compute area server-side.
- Do enforce max polygon area, max vertices, request timeouts, rate limits, and useful error responses before raster work.
- Do keep index formula mapping centralized in the BFF using `NDVI`, `NDRE`, `NDMI`, and `NDWI_GREEN_NIR`.
- Do log index request duration, source/date/index type, and failure reason.
- Do compute cloud-masked index statistics in the BFF using rasterio/rio-tiler; TiTiler serves RGB display tiles only.

### Don't

- Don't trust client-provided area calculations.
- Don't expose raw internal service URLs, credentials, or bucket names unnecessarily.
- Don't duplicate STAC asset metadata into app tables unless it is cached with a clear invalidation strategy.
- Don't let unbounded polygons or repeated requests exhaust raster compute.
- Don't send masked statistics to plain TiTiler `/cog/statistics`; it cannot apply a categorical mask from a second COG.

## Raster, STAC, and index math

### Do

- Do keep analytic reflectance COG and SCL COG as separate assets.
- Do freeze and document the Sentinel-2 analytic band order; true-colour RGB uses bands `[1, 8, 9]`, not `[1, 2, 3]`.
- Do build TiTiler expressions from STAC band metadata.
- Do apply Sentinel-2 per-band scale/offset before index math: raw `BOA_ADD_OFFSET=-1000`, STAC `raster:bands` offset `-0.1`, not `-1000`.
- Do exclude SCL classes `0, 1, 2, 3, 7, 8, 9, 10, 11` plus nodata/out-of-coverage pixels from default statistics.
- Do keep SCL class `6` water included by default.
- Do use nearest-neighbour resampling for SCL base data and SCL COG internal overviews; continuous reflectance overviews use bilinear/cubic.
- Do validate COGs and STAC items before marking scenes available.

### Don't

- Don't assume band names can be used directly in TiTiler expressions; expressions are positional.
- Don't bilinear-resample categorical SCL data or nearest-resample continuous reflectance without a specific reason.
- Don't blindly set `nodata=0`; valid reflectance can be zero.
- Don't ignore Sentinel-2 processing baseline offset metadata; offsets may be band-specific and must be read per band.
- Don't treat SAR sources as NDVI/NDRE/NDMI/NDWI_GREEN_NIR sources.

## Railway and deployment

### Do

- Do deploy as separate Railway services with persistent volumes attached to MinIO and PostGIS.
- Do expose only the `web` gateway publicly; `/api/*` and `/tiles/*` share the same public origin and proxy to internal services.
- Do use Railway private networking/reference variables for internal service calls.
- Do configure health checks for HTTP services and keep Docker Compose for local development/future on-prem portability.
- Do pin container/dependency versions, especially GDAL/rasterio/rio-tiler/TiTiler.

### Don't

- Don't rely on one production Docker Compose appliance as the Railway runtime model.
- Don't expose FastAPI, TiTiler, STAC API, PostGIS, MinIO console/API, or MinIO publicly.
- Don't use default MinIO/Postgres credentials.
- Don't store persistent raster/database data in ephemeral containers.
- Don't clone large raster datasets into every preview environment.

## Performance and reliability

### Do

- Do build COG internal overviews and add tile caching at the gateway or raster-serving layer.
- Do cap index concurrency and polygon size.
- Do benchmark with realistic Bangalore AOI plots.
- Do report partial coverage through valid-pixel percentage.
- Do monitor MinIO volume usage.

### Don't

- Don't optimize the frontend before proving raster tile/statistics performance.
- Don't run unlimited TiTiler workers without measuring memory/I/O behavior.
- Don't assume one COG will cover all future AOIs; support mosaics when needed.
- Don't skip independent reference checks for index outputs.

## Data access and licensing

### Do

- Do start with open Sentinel-2 data.
- Do confirm Bhoonidhi/API/licensing details before building ISRO automation.
- Do add new satellite sources as STAC collections.
- Do keep source-specific quirks behind ingestion/catalog metadata.

### Don't

- Don't promise high-resolution ISRO imagery until pricing/access/licensing are confirmed.
- Don't mix SAR products into optical index workflows.
- Don't design frontend features that assume one provider forever.
