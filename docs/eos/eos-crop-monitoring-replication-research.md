# EOSDA Crop Monitoring replication research

Date: 2026-06-02
Purpose: define the baseline feature set to replicate from EOSDA Crop Monitoring, identify which EOSDA API Connect endpoints can be used for trial integration, and outline the path to replace EOS with Akasha-owned data/services for production.

## Executive summary

The client is asking for two phases:

1. **Baseline parity:** reproduce the core Crop Monitoring product behavior first, especially crop monitoring, satellite imagery, vegetation analytics, weather, field workflows, and VRA maps.
2. **India-specific productization:** after parity is established, adapt the workflows for Indian crops, seasons, languages, farm sizes, public datasets, advisory models, and cost constraints.

EOSDA API Connect is useful as a **short-term integration sandbox** because it exposes satellite scene search, rendered imagery tiles, index imagery downloads, multi-temporal statistics, field management, weather, soil moisture, zoning/VRA-like maps, colorization, terrain, point values, and high-resolution imagery workflows. It should not be treated as the long-term production backend because the business goal is to avoid paid dependency. Architecturally, Akasha should implement an internal **provider adapter layer** so the UI and BFF can call a stable Akasha API while the data provider can be EOS during evaluation and native STAC/COG/weather services later.

## Sources reviewed

Primary sources:

- EOSDA API Connect quickstart: https://doc.eos.com/docs/quickstart/
- EOSDA Crop Monitoring product page: https://eos.com/products/crop-monitoring/
- EOSDA precision agriculture feature page: https://eos.com/products/crop-monitoring/precision-agriculture-software/
- EOSDA API docs for Search, Field Management, Field Analytics, Imagery, Render, Statistics, Weather, Zoning, Colorization, High Resolution Imagery, Terrain, Point Value, Cloud Mask, Clustering, FAQ, and API-vs-Crop-Monitoring comparison.
- EOSDA product pages for VRA maps and weather analytics.
- Public Crop Monitoring login UI inspected without private credentials.
- Authenticated product screenshot shared by the client/demo context.
- Authenticated Crop Monitoring UI explored on 2026-06-02 using the shared logged-in browser session for field `Field 9` / `5.5 ha`.

## Authenticated UI findings from live exploration

The logged-in application exposes more concrete modules than the public product pages alone. These should be treated as the current baseline UI surface for parity planning.

### Global shell and navigation

- Header shows back navigation, field name, area, plan upgrade, edit field, disabled `Get Overview`, and `All fields` selector.
- Right sidebar groups:
  - `Monitoring`: Global view, Field analytics, Field leaderboard, Reporting, Diseases & Pests.
  - `Weather`: Analytics, Forecast.
  - `Field activity log`.
  - `VRA maps`: Sowing, Vegetation, P&K, Map builder, Soil sampling.
  - `Scout tasks`.
  - `Data manager`: Data, Connections.
  - `Field manager`: Field groups.
  - Utility/account modules: AI assistant, Notifications, Help Center, Marketplace, account/team menu, Try Full-Featured Access, Upgrade Plan.
- Account/team menu exposes user profile email, team name, owner role, switch team, Team Management, API, Settings, Upgrade plan, and Log out.
- Help Center menu links to What's New, User guide, Case studies, Crop management guide, and Contact us.
- Marketplace menu links to Add-ons, Solutions, Partnership module, and White Label.
- Notifications panel showed an empty state: no notifications yet; field-change notifications appear there.
- AI assistant panel showed a beta/basic assistant message and text input.

### Field analytics screen details

- Map controls observed:
  - split view, zoom in/out, ruler/measure, find field, full-screen mode.
  - source selector, index/layer selector, anomaly layer button (disabled in current plan), static/legend mode, cloud mask filter, download/export, legend toggle.
  - date timeline with Sentinel-2 scene chips and next-image prompt.
- Source selector options:
  - Satellites: PlanetScope `PS` 3 m as add-on, Sentinel-2 `S2` 10 m selected.
  - Elevation map.
  - Slope map.
- Layer/index selector options:
  - Natural Color.
  - Vegetation Indices group: Vegetation Meta index, NDVI, NDRE, MSAVI, RECI.
  - Moisture Indices group: NDMI.
  - Add new index as an add-on.
- Cloud mask menu has independent toggles for cirrus clouds, clouds, and cloud shadows.
- Download menu supports `NDVI.tiff`, `NDVI.shp`, and `Contours.shp` for the selected index/date.
- Analytics panel tabs/sections observed:
  - Crop info.
  - Chart.
  - Activities.
  - Crop rotation.
  - Season selector context: `Season: Season 2`.
  - Add crop.
  - Sown area detected percentage, gated behind Essential/Professional plan.
  - Crop management guide link.
  - Growth stages, requiring crop selection.
  - Current risks, gated behind Essential/Professional plan.
  - NDVI values split, gated behind Essential/Professional plan.

### All-fields, seasons, and field admin

- `All fields` panel includes search, filter, risk filtering icons, field list cards with crop/area/source/plan status, and `Add fields`.
- `Season` panel includes:
  - explanation that platform data is filtered by selected season and fields added to it.
  - Create season.
  - Active / Planned / Ended groups.
  - Active seasons show date ranges, total area, and Edit/Delete actions.
- `Field group manager` includes Add new group and an empty-state prompt to create groups.

### Monitoring modules

- `Field leaderboard` includes PDF and XLS exports and filter columns for Index, Group, Crop, Variety, Report date, Field, Location, Coordinates, Area, Sowing/Planting, Index value, Value change, Actual yield, Image date, and Preview/Open.
- Field leaderboard is positioned as weekly field reports for detecting field changes; the sample UI advertises identify risks, email alerts, export/share.
- `Reporting` page is a custom report builder: Create template and select table columns.
- `Diseases & Pests Risk` includes Manage Disease List, field/crop/sowing/growth stage metadata, disease/pest rows, low/medium/high risk legend, calendar timeline, and plan-gated disease-risk tracking. It explicitly lists benefits: predict occurrence, prevent occurrence, avoid yield losses.

### Weather modules

- `Weather Analytics` tabs: Analytics and Forecast.
- Weather analytics page exposes parameters, date range, comparison mode, index/satellite selectors, and charts for:
  - Accumulated precipitation.
  - Daily precipitation.
  - Daily temperatures.
  - Sum of Active Temperatures.
  - Evapotranspiration.
  - Relative humidity.
  - Global radiation.
- Weather analytics also advertises weather risk prediction, crop growth-stage estimation, and field knowledge; limited field access was shown on the current plan.
- `Weather Forecast` page includes current weather cards for temperature, precipitation, relative humidity, clouds, and wind, with a forecast-loading state in the sampled account.

### Operations, scouting, data, and machinery

- `Field activity log` includes:
  - Free activities count, Download report, Add activity.
  - Filters for Group, Crop, Variety, All activities, Assignees, Clear.
  - Calendar/month timeline across the year for field activities.
- `Scout tasks` includes map + task list, Search, Filter, New/Closed task tabs, empty state, and `ADD NEW TASK` instruction to drop a pin on a map.
- `Data manager > Data` supports upload/drop zone for datasets with formats `ZIP (*SHP, *SHX, *DBF, *PRJ)` and `ZIP (ISO-XML)`, max upload size 10 MB, and `ADD DATASET`.
- `Data manager > Connections` exposes John Deere Integration for field boundaries and machinery data via John Deere Operations Center, with a Connect action.

### VRA map modules

- `Sowing maps`: create precision sowing maps based on field productivity and optimize seed placement.
- `Vegetation-based maps`: apply the right input at the right time; includes `+ Create map`.
- `P&K fertilization`: develop precision maps for potassium and phosphate fertilizer application.
- `Map builder`: customize differential application maps by combining layers and indices; includes `+ Create map`.
- `Soil sampling`: divide fields into sections and identify sample points to collect soil samples; empty state includes `Create new maps`.

## Product feature inventory to replicate

### 1. Account, onboarding, and field setup

Observed or documented capabilities:

- Sign up/sign in with email/password, Google, and Facebook.
- Language selector on public login.
- Free monitoring onboarding and upgrade prompts.
- Add fields by drawing boundaries or uploading/importing boundaries.
- Store field name, group/client group, area, crop type, season/year, sowing date, and other season attributes.
- Display field area and selected field name in the map header.
- Manage multiple fields and switch between all fields and individual field views.
- Manage seasons with Active, Planned, and Ended states; season selection filters all platform data.
- Manage teams, team switching, settings, API access, and subscription plan actions.

EOS API support:

- `POST /field-management` creates a field from GeoJSON polygon and optional `properties.name`, `properties.group`, `properties.years_data.crop_type`, `year`, and `sowing_date`.
- `PATCH /field-management/{field_id}` updates field metadata.
- `GET /field-management/{field_id}` retrieves one field.
- `GET /field-management/fields` lists fields.
- `DELETE /field-management/{field_id}` and `DELETE /field-managements` delete fields.
- `GET /api/crop-types` or documented crop-type endpoint returns supported crop names.

Akasha baseline implication:

- Extend existing plot CRUD into field/season management: field groups, crop seasons, sowing/harvest dates, crop catalog, and area units.
- Keep field geometry in our PostGIS tables; optionally mirror to EOS only for trial workflows.
- Add first-party team/account settings and API-key/admin pages when auth is introduced.

### 2. Map-based satellite monitoring

Core behavior to replicate:

- Full-screen map with field polygon overlay.
- Field boundary highlighted with a thick white outline.
- Satellite imagery layer under field boundary.
- Date timeline/carousel at the bottom, showing available images and cloud status.
- Sensor selector, e.g. Sentinel-2; high-resolution PlanetScope is marketed as available up to about 3 m.
- Layer/index selector, including true color and vegetation indices.
- Same-origin map interaction: zoom, scale bar, coordinate readout, pan, field focus.
- Default map layer should remain true color imagery, not NDVI, consistent with current Akasha guardrails.
- Split-view, ruler/measure, full-screen, find-field, cloud-mask toggle, legend toggle, and download/export controls.
- Slope and elevation maps as first-class map sources.

EOS API support:

- Scene search:
  - Raw AOI: `POST /api/lms/search/v2/{dataset_id}` for one dataset.
  - Multi-dataset: `POST /api/lms/search/v2` with `search.satellites`.
  - Field-based: `POST /scene-search/for-field/{field_id}` then `GET /scene-search/for-field/{field_id}/{request_id}`.
- Render tiles:
  - `GET /api/render/{view_id}/{bands}/{z}/{x}/{y}` for XYZ tiles.
  - True color Sentinel-2: `B04,B03,B02`.
  - False color: `B08,B04,B03`.
  - Index tile examples: `NDVI`, virtual band formulas, clustering, cloud masks.
- Download imagery:
  - Visual image: `POST /api/gdw/api` with `type: "jpeg"` and `params.view_id`, `bm_type`, `geometry`, `format`, `px_size`, `colormap`, `calibrate`.
  - Bandmath raster: `type: "bandmath"` returns Float32 GeoTIFF for index output.
  - Raw bands: `type: "lbe"` downloads original scene bands cropped to AOI.

Akasha baseline implication:

- Current Akasha already has the right architectural direction: STAC/COG catalog, TiTiler for RGB tiles, BFF statistics, and MapLibre frontend.
- Add a date timeline UI driven by scene search results.
- Add index overlay rendering for selected date/layer while keeping true color as the default.
- Add export support for selected index raster (`.tiff`), vectorized classes/zones (`.shp`), and contours (`.shp`) where applicable.

### 3. Vegetation indices and crop analytics

Documented EOS indices:

- Statistics docs mention 17 built-in indices: `NDVI`, `NDSI`, `NDWI`, `RECI`, `NDMI`, `SAVI`, `ARVI`, `EVI`, `GCI`, `SIPI`, `NBR`, `MSI`, `ISTACK`, `FIDET`, `NDRE`, `CCCI`, `MSAVI`.
- Product pages emphasize 10+ built-in vegetation indices, custom indices on request, cloud/cirrus/shadow filtering, and index suggestions by growth stage.
- Client screenshot shows an index selector set to `NDVI`.
- Live UI confirmed visible index/layer choices: Natural Color, Vegetation Meta index, NDVI, NDRE, MSAVI, RECI, NDMI, and Add new index as an add-on.
- Live UI confirmed plan-gated analytics blocks: sown-area detected %, current risks, and NDVI values split per field.

Important parity note from EOS docs:

- To match Crop Monitoring imagery with EOS API output, EOS recommends:
  - Use Sentinel-2 L2A (`sentinel2l2a` / `S2L2A`) from 2018 onward.
  - Add `calibrate: 1` for image tasks.
  - Use the same Crop Monitoring colormaps/thresholds.
  - Pay attention to aliases vs formulas; aliases may not always match Crop Monitoring formulas exactly.
- For Crop Monitoring parity, prefer explicit formulas where needed:
  - NDVI: `(B08-B04)/(B08+B04)` or `(NIR-RED)/(NIR+RED)`.
  - NDRE: `(NIR-B05)/(NIR+B05)`.
  - NDMI: `(NIR-SWIR1)/(NIR+SWIR1)`.
  - RECI: `(NIR/RED)-1` in EOS comparison notes, but product/API pages also discuss Red Edge variants; verify before finalizing.
  - MSAVI formula differs in docs depending on alias/formula context; verify against Crop Monitoring visual output.

EOS API support:

- Multi-temporal statistics:
  - `POST /api/gdw/api` with `type: "mt_stats"`.
  - `GET /api/gdw/api/{task_id}` returns scene/date/cloud plus min, max, average, std, variance, median, q1, q3, p10, p90.
- Field analytics:
  - `POST /field-analytics/trend/{field_id}` then `GET /field-analytics/trend/{field_id}/{request_id}`.
  - Returns per-scene trend metrics for a field.
- Classification area:
  - `POST /classification-area/{field_id}` or generic `type: "cl_stats"`.
  - Calculates area per threshold class for an index and scene.
- Point value:
  - `GET /api/render/{sensor}/point/{scene}/{bands}/{lat}/{lon}` returns index/band value at a point.
- Slice/profile:
  - `GET /api/render/{sensor}/slice` returns pixel values along a line.

Akasha baseline implication:

- Current BFF masked-statistics engine already covers NDVI/NDRE/NDMI/NDWI-like statistics for polygons. To match EOS baseline, add:
  - More indices: MSAVI, RECI, EVI, SAVI, MSI, etc.
  - Time-series endpoint returning per-scene statistics.
  - Threshold classification/area endpoint.
  - Index legend/color rules matching selected index.
  - Optional point-inspection tool on map click.
  - Growth-stage and crop-info panels driven by crop/season metadata.
  - Crop rotation and activity overlays in the analytics panel.

### 4. Cloud masking and data quality

EOS behavior:

- Statistics can use `exclude_cover_pixels` and `cloud_masking_level` for Sentinel-2.
- `cloud_masking_level` values:
  - `1`: high probability clouds.
  - `2`: medium + high probability clouds.
  - `3`: medium + high probability + thin cirrus + cloud shadows + unclassified pixels.
  - `4`: medium + high probability + thin cirrus.
- Cloud mask tile API can render cloud pixels as a mask overlay; docs say cloud pixels are white and cloudless pixels are transparent.
- EOS recommends combining SCL and GML cloud masks for best statistics.
- Live UI exposes separate filter toggles for cirrus clouds, clouds, and cloud shadows.

Akasha baseline implication:

- Akasha already applies Sentinel-2 SCL masking in the BFF. Preserve that rule.
- Add UI controls/metadata for cloud percentage, masked-pixel percentage, and low-quality scene warnings.
- For EOS trial, use conservative cloud masking level `3` for parity unless the client wants visual parity with exact Crop Monitoring settings.
- Implement user-selectable mask-class toggles for visual layers, while keeping safe default cloud masking for statistics.

### 5. Risk map and alerts

Product-documented behavior:

- Risk map compares NDVI between the two newest Sentinel-2 images.
- Disease and pest infestation risks are based on plant growth stages and weather forecasts.
- Extreme weather risks include heat/cold stress, high winds, and heavy rains.
- Notifications appear on-platform and by email.

EOS API support:

- Direct risk-map endpoint was not found in the public API docs reviewed.
- Possible building blocks:
  - Scene search and NDVI statistics for latest scenes.
  - Change Detection API: `GET /api/render/{sensor}/diff/{band}/{z}/{x}/{y}?scene1=...&scene2=...`.
  - Weather forecast/high-accuracy forecast endpoints.
  - Classification area for thresholded risk classes.

Akasha baseline implication:

- Build risk map as Akasha logic:
  - Compare latest two cloud-clean scenes for NDVI/NDRE/NDMI deltas.
  - Flag fields with negative vegetation delta, high cloud gaps, drought/heat/cold/wind/rain risk.
  - Later incorporate crop-stage disease/pest heuristics for Indian crops.

### 6. Weather analytics and forecast

Product behavior:

- Historical weather from 1979 onward.
- 14-day hourly agriculture forecast.
- Weather parameters: temperature, precipitation, relative humidity, evapotranspiration, global radiation, wind speed/direction, cloudiness.
- Weather risk alerts for cold stress and heat stress.
- Thresholds and durations on weather analytics charts.
- Soil moisture analytics for surface and root zone.
- Ground weather station integration, including Davis and other stations by request.
- Downloadable Excel/XLSX reports.

EOS API support:

- Geometry-based weather:
  - `POST /weather/v1/forecast/` for 14-day forecast with 3-hour update step.
  - `POST /weather/forecast-history` for historical weather by AOI.
- Field-based weather:
  - `POST /weather/forecast/{field_id}`.
  - `POST /weather/forecast-high-accuracy/{field_id}` for 14-day, 1-hour forecast.
  - `POST /weather/historical-accumulated/{field_id}` for accumulated rainfall/temperature.
  - `POST /weather/historical-high-accuracy/{field_id}`; docs recommend date ranges up to one month.
- Soil moisture:
  - `POST /api/gdw/api` with `type: "mt_stats"`, `bm_type: "soilmoisture"`, `sensors: ["soilmoisture"]`.
  - Surface soil moisture is returned in `average`; root zone value is returned in `ctime_10`.
  - EOS soil moisture docs list India as covered, available from 2015, 250 m resolution, 2-3 day revisit/update. The FAQ page appears older and omits India in one place, so coverage should be verified with a real request.

Akasha baseline implication:

- Implement weather as a separate provider-backed module.
- For EOS trial, use field-based forecast and historical endpoints.
- For production India path, evaluate IMD/open weather datasets, ECMWF/GFS/Open-Meteo, NASA SMAP, and ground-station ingest.

### 7. VRA maps and zoning

Product behavior:

- VRA maps are used for variable-rate sowing, fertilization, desiccation, crop protection, irrigation, and soil sampling.
- VRA map categories visible in the screenshot/sidebar:
  - Sowing.
  - Vegetation.
  - P&K.
  - Map builder.
  - Soil sampling.
- Product page says VRA supports NDVI, NDMI, RECI, MSAVI, elevation, machinery data, historical imagery, and high-resolution imagery.
- Vegetation maps split fields into 2 to 7 zones for nitrogen fertilization/irrigation/crop protection.
- Productivity maps use long-term NDVI to guide P/K fertilization, differential seeding, and soil sampling.
- Outputs can be downloaded as SHP; product pages mention machinery-compatible prescription files.

EOS API support:

- Vegetation map:
  - `POST /zoning/vegetation-map` with `field_id`, `vegetation_index`, `zone_quantity`, `min_zone_area`, `image_date`, `dataset_id`, `need_answer`, optional `callback_url`.
  - `GET /zoning/maps/{field_id}/{zmap_id}` returns zone geometry, area, percent, fertilizer values, k-means values, image link.
- Productivity map:
  - `POST /zoning/productivity-map` or documented `/api/zoning/vmaps/` form with date range.
  - `GET /zoning/maps/{field_id}/{zmap_id}` returns productivity zones.
- Generic zoning:
  - `GET /api/zoning/{field_id}` lists maps.
  - `GET /api/zoning/{field_id}/{zmap_id}` retrieves map.
  - `GET /api/zoning/shp/{field_id}/{zmap_id}` downloads SHP archive.
  - `DELETE /api/zoning/{field_id}/{zmap_id}` deletes a map.
- Clustering API:
  - `POST /api/render/clustering_options/` saves k-means options.
  - `GET /api/render/{sensor}/clustering_band/{scene_id}/{band}` calculates cluster centroids.
  - Render API can request NDVI clustering tiles with `CLUSTERING=kmeans`, `CLUSTERS_NO`, and `MIN_AREA`.

Akasha baseline implication:

- Build zoning as an Akasha service using existing raster/index outputs plus k-means/quantile segmentation.
- Start with vegetation map zones and SHP/GeoJSON export.
- Add productivity maps after multi-season archive coverage is available.
- Map builder can be a later advanced feature combining index layers, elevation, soil, yield, and uploaded machinery data.

### 8. Reporting, leaderboard, and global views

Product/sidebar behavior:

- Monitoring section includes Global view, Field analytics, Field leaderboard, Reporting, Diseases & Pests.
- Automated reports can be configured for one field or all fields.
- Reports include vegetation status, seasonal productivity analytics, and risk-based filtering/downloads.
- Weather reports are downloadable in XLSX format.
- Field leaderboard helps consultants manage multiple clients/fields and rank fields by crop status/risk.
- Live UI confirms Field leaderboard PDF/XLS export and table fields for index, group, crop, variety, report date, field, location, coordinates, area, sowing/planting, index value, value change, actual yield, image date, and preview/open.
- Live UI confirms Custom report template creation and column selection.

EOS API support:

- No dedicated reporting/leaderboard endpoint was found in reviewed public docs.
- Building blocks:
  - Field list.
  - Field analytics trends.
  - Weather and risk metrics.
  - Zoning maps.

Akasha baseline implication:

- Implement reporting and leaderboard inside Akasha:
  - Field health score from latest index average, index delta, cloud-free recency, weather risk, and activity status.
  - CSV/XLSX/PDF export.
  - Scheduled email reports later.
  - Custom report templates with selectable table columns.

### 9. Field activity log, team management, and collaboration

Product behavior:

- Field activity log tracks tillage, watering, pesticide spraying, scouting, tasks, assigned performers, status, supplies, costs, and planned-vs-actual analysis.
- Team management supports roles, permissions, task assignments, notifications, and up to 50 members according to product page.
- Reports can be shared with stakeholders.
- Live UI confirms activity log has free activity count, report download, Add activity, filters, assignees, and yearly calendar timeline.
- Live UI confirms Scout tasks has map-based task creation by dropping pins, New/Closed tabs, Search, and Filter.
- Live UI confirms notifications panel for field-change notifications and beta AI assistant panel.

EOS API support:

- Public EOSDA API Connect docs reviewed do not expose activity log/team management endpoints.

Akasha baseline implication:

- Build these as first-party app modules.
- Minimum baseline:
  - Activity type, date, field, assignee, cost, input product, notes, photos/attachments.
  - Role-based access after auth is introduced.
  - Scout task geometry/pin, task status, assignee, and field linkage.
  - Notification center for changes, risks, tasks, and report availability.

### 10. Yield estimation and growth stages

Product behavior:

- Growth stages / BBCH timeline based on sowing dates.
- Yield estimation forecasts dry biomass, dry yield, and recommended harvest date.
- Yield/biomass projections are described as model-based and available around crop emergence / productive-part visibility / 14 days before harvest.

EOS API support:

- The reviewed public API docs did not reveal a direct yield-estimation endpoint.
- Inputs exist via field crop/sowing metadata, vegetation trends, weather, and soil moisture.

Akasha baseline implication:

- Treat yield estimation as a later model feature.
- For India, crop-specific models and calibration data will matter more than visual parity.

### 11. Machinery and external integrations

Product behavior:

- John Deere Operations Center integration for field boundaries and historical machinery records.
- VRA/prescription export compatible with agricultural machinery.
- Ground weather station integration.
- Data manager accepts uploaded datasets as zipped SHP components and zipped ISO-XML, max 10 MB in the observed plan.

EOS API support:

- Public EOS API docs reviewed do not expose John Deere integration endpoints.
- SHP export is available for zoning maps.

Akasha baseline implication:

- Defer John Deere until the client confirms target user segment in India.
- Prioritize simple GeoJSON/SHP/KML import/export and mobile-friendly field workflows.
- Include SHP and ISO-XML import/export in the baseline plan if VRA/machinery parity is required.

## Feature-to-API mapping

| Crop Monitoring feature | EOS API to test | Purpose | Native production replacement direction |
|---|---|---|---|
| Field create/edit/list | Field Management API | Mirror user fields into EOS trial account | PostGIS `fields`, `field_seasons`, crop catalog |
| Scene/date timeline | Search API / field scene search | Get available scenes, date, cloud %, `view_id` | STAC/pgSTAC scene search over Akasha catalog |
| True color map tiles | Render API `B04,B03,B02` | Display scene tiles | TiTiler over Akasha COGs |
| NDVI/NDRE/NDMI/MSAVI/RECI layer | Render API or Imagery API | Visual index overlay | TiTiler/BFF raster expression rendering |
| Download index image | Imagery `type: jpeg` or `bandmath` | Get PNG/TIFF for AOI | BFF/TiTiler export endpoint |
| Field analytics trend | Field Analytics or Statistics API | Time-series chart per field | BFF statistics over STAC scenes |
| Classification area | Classification Area / `cl_stats` | Area per index threshold class | BFF thresholded raster area calculation |
| Cloud quality | Search cloud %, cloud mask tile, stats cloud masking | Scene quality and masked display | SCL/cloud mask assets in Akasha COG/STAC |
| Risk map | Render Change Detection + stats + weather | NDVI deltas and weather risks | Akasha risk engine |
| Forecast weather | Weather field forecast/high-accuracy | 14-day forecast | IMD/GFS/ECMWF/Open-Meteo/provider abstraction |
| Historical weather | Weather historical/high-accuracy/accumulated | Weather charts and reports | IMD/ERA5/AgERA5/native weather warehouse |
| Soil moisture | Statistics `soilmoisture` | Surface/root-zone soil moisture | NASA SMAP/ISRO/soil model pipeline |
| Vegetation VRA map | Zoning vegetation map | N zones from current scene/index | Akasha zoning/k-means service |
| Productivity/P&K map | Zoning productivity map | Long-period NDVI productivity zones | Multi-season Akasha archive analytics |
| SHP export | Zoning SHP endpoint | Machinery/GIS export | GeoJSON/SHP/ISO-XML export service |
| Terrain/elevation | Terrain tile/point API | Slope/elevation overlays | SRTM/Copernicus DEM/Mapzen terrain tiles |
| High-res imagery | High Resolution Imagery API | Planet imagery trial | Optional paid provider adapter; not core free production |
| Reports/leaderboard | Compose from fields + analytics + weather | Aggregated decision UI | Akasha reports and scoring service |
| Custom report templates | Not found as public EOS API | Select report columns and export | Akasha report-template service |
| Disease & pest risk UI | Not found as public EOS API | Crop disease/pest calendar and low/med/high risk display | Akasha crop-risk rules/model service |
| Scout tasks | Not found as public EOS API | Map pin tasks with New/Closed states | Akasha task/scouting service |
| Activity calendar/log | Not found as public EOS API | Add/filter activities and report operations | Akasha field-operations service |
| Data uploads | Not found as public EOS API | Upload SHP/ISO-XML datasets | Akasha import pipeline and object storage |
| John Deere connection | Not found as public EOS API | Machinery boundary/data integration | Optional machinery adapter |
| Team/API/settings | Not found as public EOS API | Account admin, team switching, API page | Akasha auth/team/admin modules |
| AI assistant/notifications | Not found as public EOS API | Assistant panel and field-change notifications | Akasha notification + assistant layer |

## EOS API integration workflow for trial

### Recommended BFF adapter shape

Do not call EOS directly from the frontend. Keep the existing Akasha rule: browser calls Akasha BFF only. Add an EOS adapter behind the BFF for trial data.

Suggested provider concepts:

- `FieldProvider`: create/list/update/delete field mirrors.
- `SceneProvider`: search available scenes for field/AOI.
- `TileProvider`: provide tile URL template or proxy endpoint.
- `AnalyticsProvider`: get trend statistics, classification areas, and point values.
- `WeatherProvider`: forecast, historical, accumulated weather, soil moisture.
- `ZoningProvider`: create/retrieve/export VRA/zoning maps.

Store external IDs separately, e.g. `external_provider = eos`, `external_field_id`, `external_request_id`, `external_zmap_id`, so Akasha can switch providers later without changing product UI.

### Minimal EOS trial sequence

1. Create or mirror field in EOS Field Management.
2. Search scenes for that `field_id` and chosen date range.
3. Render true color and selected index tiles for the map using `view_id`.
4. Fetch field analytics trend for NDVI/NDRE/NDMI/MSAVI/RECI.
5. Fetch weather forecast and historical weather for the field.
6. Create a vegetation zoning map for selected image/index/zone count.
7. Retrieve zones and display/export them.

### Environment variable

For local trial integration, use:

- `EOS_API_KEY`: EOSDA API Connect key from the EOS dashboard.

A local root `.env` placeholder has been added and is ignored by git.

## API limits and operational notes

- Authorization uses `x-api-key: <api_key>` header; some examples also allow `?api_key=<api_key>`.
- Trial accounts are documented as having 1000 requests unless increased by support.
- Weather default limit is documented as 10 requests per minute.
- Statistics endpoints are documented as 10 requests per minute per API key.
- One API request can include field size up to 200 sq. km / 20,000 ha.
- Statistics docs recommend one field per request and a date range up to 365 days. Quickstart mentions up to around 3 indices per request; FAQ says up to around 5. Use the conservative value of 3 until tested.
- Imagery download workflow typically costs 3 requests: search scene, create task, get image.
- Field-ID vegetation index download flow in FAQ costs 4 requests: scene-search task, scene-search result, imagery task, image result.
- Zoning workflow costs at least 2-3 requests: create field if needed, create map, retrieve map.
- Zoning processing usually takes 30-180 seconds, and some docs mention up to 300 seconds.
- Download indices API states max AOI area of 8 km² for bandmath downloads.
- High Resolution Imagery requires service activation for specific fields and cannot be assumed available in trial.
- Cache scene search, tile metadata, analytics, weather, and completed task results aggressively to avoid rate-limit and cost problems.

## Baseline replication priority

### Phase 1: Client-visible parity foundation

- Field management: draw/import/list/group fields and season metadata.
- Map screen: field polygon, date timeline, true color, index overlay, sensor/date selector.
- Scene metadata: date, cloud %, sensor, image availability.
- Core indices: NDVI, NDRE, NDMI, MSAVI, RECI, true color, false color.
- Field analytics panel: trend chart, min/max/avg/std, cloud warnings.
- Cloud mask toggles, legend/download controls, split/ruler/find-field/full-screen map tools.
- Weather forecast and historical weather cards/charts.
- Basic reports export for field analytics.
- Field groups, seasons, all-fields search/filter, and custom report template skeleton.

### Phase 2: Decision-support parity

- Risk map from latest-scene vegetation delta and weather stress rules.
- Field leaderboard across all fields.
- Classification area by index thresholds.
- VRA vegetation map with zone count, min zone area, zone geometry, and SHP/GeoJSON export.
- Productivity/P&K map from multi-season index archive.
- Field activity log with tasks, inputs, costs, and status.
- Scout tasks with map pin workflow and new/closed lifecycle.
- Data manager for SHP/ISO-XML imports and basic machinery connection placeholder.
- Notifications center and account/team admin shell.

### Phase 3: Advanced parity

- Disease and pest risk models.
- Growth-stage/BBCH timeline.
- Yield/biomass estimation.
- Team roles and notifications.
- AI assistant workflows tied to field analytics/advisory content.
- Ground weather station ingest.
- Machinery integrations and prescription formats beyond SHP.
- High-resolution imagery provider adapter.

## India-specific modifications after baseline

Once EOS-like parity exists, the India version should diverge deliberately:

- **Crop calendar localization:** Kharif/Rabi/Zaid seasons, state-wise sowing windows, crop-specific growth stages.
- **Crop catalog:** paddy, wheat, sugarcane, cotton, maize, pulses, oilseeds, horticulture crops, plantation crops, and region-specific varieties.
- **Smallholder UX:** many small fields, mobile-first workflows, low bandwidth, offline capture, WhatsApp/SMS advisory delivery.
- **Language support:** English plus Hindi and priority regional languages depending on launch geography.
- **Weather and advisories:** IMD forecasts/warnings, rainfall anomaly, heatwave/cold-wave alerts, monsoon onset/withdrawal context.
- **Irrigation relevance:** canal/tank/borewell context, drought/waterlogging advisories, soil moisture tied to irrigation scheduling.
- **Government and insurance workflows:** PMFBY-style crop loss support, panchayat/village aggregation, state boundaries, survey/khata identifiers where legally available.
- **Data alternatives:** Copernicus/CDSE Sentinel-2 and Sentinel-1, Landsat, NASA SMAP, SRTM/Copernicus DEM, IMD/ERA5/AgERA5/Open-Meteo/GFS weather, public soil maps, and optional commercial high-res imagery only when paid customers justify it.
- **Pricing architecture:** avoid hard dependency on paid APIs for core monitoring; keep paid providers as pluggable premium adapters.

## Open questions for client/product

1. Which EOS modules are mandatory for first demo parity: only Monitoring + Field Analytics, or also Weather + VRA + Reports?
2. Does the client expect exact visual color parity with EOS Crop Monitoring, or functional parity with Akasha branding?
3. Which Indian region/crops should drive the first localized version?
4. Should high-resolution Planet-like imagery be included in baseline, or treated as premium/optional?
5. Is authentication/team management needed before analytics parity?
6. Are machinery prescription exports important for the initial Indian target users, or is advisory/reporting more important?
7. Can we obtain a real EOS trial key and a sample field to validate API behavior, request limits, output schema, and visual parity?

## Recommended next action

Implement an EOS trial spike behind the Akasha BFF, not in the frontend. The spike should mirror one Akasha field into EOS, retrieve scene dates, render one true-color layer, retrieve one NDVI trend, and create one vegetation zoning map. That will prove the integration path while keeping the production architecture ready for Akasha-native providers.
