# Phase 1 — High-Level Module Inventory

Complete breadth-first capture of the EOSDA Crop Monitoring platform. Every
top-level module is listed with the immediate sub-features it contains. Goal: a
checklist where nothing is missed, before per-module deep dives.

Source: <https://eos.com/user-guide/crop-monitoring/> and its sub-pages.

Sub-feature status key: `[ ]` = deep-dive pending, `[x]` = deep-dive done.

---

## 1. Video Guide (Onboarding)
Guide: `/video-guide/` — short walkthrough videos that orient a new user. Acts as
the onboarding/learning hub rather than a functional tool.

- [ ] Create an Account
- [ ] A Gift Field (free demo field to explore features)
- [ ] Adding a Field
- [ ] Field Analytics
- [ ] Monitoring Indexes
- [ ] Historical Weather
- [ ] Weather Forecast
- [ ] Scouting
- [ ] Field Leaderboard
- [ ] Zoning
- [ ] Field Activity Log
- [ ] Data Manager

---

## 2. Tools for Working with Fields & Tasks
Guide: `/tools-to-work-with-fields-and-tasks/` — shared list/utility tools that
operate across the Fields list and the Scouting list.

- [ ] Filters — filter fields or scouting tasks by crop and group (checkbox + Apply)
- [ ] Sorting — Newest, Oldest, name asc/desc, area low→high / high→low
- [ ] Field Search — find a field/task by name
- [ ] Field Card — per-field summary (name, area in ha, group, crop, location)
- [ ] Find Field button — zoom-to-field on the map across any active layer; view
  several adjacent fields at once; quick return/zoom-back to a field

---

## 3. Work with Crop Map
Guide: `/work-with-crop-map/` — the main map canvas and its global navigation,
measurement, comparison, and overlay tools.

- [ ] Find Location — search by place name or by coordinates (lon first, lat last)
- [ ] Zoom tool — zoom in/out (buttons + mouse wheel)
- [ ] Distance & Area measurements — measure tool to outline area or measure distance
- [ ] Split View — side-by-side comparison of indices/dates for a field; synced
  hover values; per-side timeline + index switch; legend; data download; 5-year history
- [ ] Layers (multi-field analysis overlays) — drop-down switching between:
  - [ ] My Crops layer (fields colored by crop; 5-year crop rotation)
  - [ ] Vegetation layer (avg NDVI per field, 10 ranges)
  - [ ] Water Stress layer (avg NDMI per field; Pro)
  - [ ] Vegetation Rating layer (fields ranked by avg NDVI; Pro)
  - [ ] Crop Classification layer (country-wide crop map; Ukraine only; Pro)
- [ ] Contrast View — toggle standard vs. contrast palette to reveal low-variability
  differences across all indices
- [ ] Latest Image layer — "Search this area" to pull the most recent satellite
  image for the visible area; pick among available images

---

## 4. Seasonality (Seasons)
Guide: `/seasonality/` — define agricultural seasons so all analytics align to the
user's real farming calendar.

- [ ] About Seasonality — concept; align season start/end to farm schedule
- [ ] Create Season — name, start/end dates, optional copy fields from another
  season, select fields to include
- [ ] Edit Season — rename, change duration (auto-readjusts sowing/harvest), manage
  field list
- [ ] Delete Season — remove a season; system always keeps ≥1; reassign orphaned
  fields; default season auto-created on signup (cannot be removed)

---

## 5. Add Field
Guide: `/add-field/` — all ways to create field boundaries in the account.

- [ ] Add Field entry point (+ADD FIELD) with options: Draw on map / Upload / Custom upload
- [ ] Upload fields — without parameters (.shp, .kml, .kmz, .geojson; drag-drop)
- [ ] Upload fields — with parameters (Fields upload manager: map columns to
  crop/name/group/sowing/harvest/notes/season; date-format selection; match
  seasons/crops/groups)
- [ ] Upload formats reference — SHAPE (.shp/.shx/.dbf/.prj), KML, GeoJSON, ZIP
- [ ] Upload error types — missing .prj, unsupported format, no polygons, >10 Mb,
  intersecting contours, field >10,000 ha / 24,710 ac
- [ ] Draw boundary — polygon drawing (≥3 points, double-click to close)
- [ ] Draw multiple fields in one session
- [ ] Draw round boundaries (Circle tool)
- [ ] Cut parts of a boundary (cutting tool to exclude buildings/roads/etc.)
- [ ] Post-create field info — Field Name, Group Name, Crop Rotation data

---

## 6. Fields / Monitoring (field analytics panel)
Guide: `/fields/` — the right-sidebar analytics for a single selected field. The
analytical heart of the product.

- [ ] Image sources — Sentinel-2 (10 m) and optional PlanetScope (3 m, daily);
  cloud/shadow threshold settings
  - [ ] Elevation map (digital elevation model; hover values; .tiff download)
  - [ ] Slope map (terrain slope in degrees, color legend)
- [ ] Date line (timeline) — all available images; hover preview with cloud/shadow %
  and time; free = last 3 months; historical from 2016 (paid); cloudiness threshold
- [ ] Crop info panel:
  - [ ] Crop rotation (add/select crops, sowing date; multi-crop per season)
  - [ ] Growth stages (BBCH; recommended vs. additional indices per stage; manual stage dates)
  - [ ] Current risks (index/disease/cold/heat/etc.; probability levels; add-ons)
  - [ ] Yield estimation (add-on; select crops)
- [ ] Charts:
  - [ ] Vegetation indices chart (toggle curves, compare years)
  - [ ] Weather chart (Temperature / Moisture data selectors)
  - [ ] Temperature (min/max curves; cold −6 °C, heat +30 °C thresholds)
  - [ ] Moisture (precipitation, soil surface moisture, root-zone moisture)
  - [ ] Growth stages curve
  - [ ] Period intervals (date range; Update to reset)
- [ ] Indices (selectable index list):
  - [ ] VMI (Vegetation Meta Index — RGB composite of MSAVI/NDRE/NDVI)
  - [ ] NDVI, NDRE, MSAVI, ReCI, NDMI (core)
  - [ ] Natural color (true-color verification)
  - [ ] Add-on indices: GNDVI, EVI, SIPI, ARVI, RENDVI, PSRI, GCI, NDYI, NRFI, NDPI
  - [ ] CI (Custom Index — request custom formula)
- [ ] Details — expand index value breakdown; ha or %; download XLS
- [ ] Download — index map as .tiff or .shp; field contours
- [ ] Mask filter — clouds / cirrus / cloud shadow masks (toggle individually)
- [ ] Available features for crops — matrix of which features/indices/yield/etc. are
  supported per crop (large crop list)
- [ ] Weather shortcut — jump from Monitoring to the Weather page / analytics tab

---

## 7. Weather
Guide: `/weather/` — historical and forecast weather analytics per field.

- [ ] Historical Weather — archived temperature & precipitation; set vegetation
  period/season (from 2008); growth-stages curve overlay; Compare with 5-year average
- [ ] Accumulated & Daily Precipitation graphs (with 5-year average)
- [ ] Daily Temperatures graph (min/max + 5-year average)
- [ ] Sum of Active Temperatures (0 °C / 5 °C / 10 °C threshold options)
- [ ] Weather Forecast — 14-day forecast (wind, humidity, cloud cover, precipitation)
- [ ] Recommended time for field activities — hourly green/orange/red guidance for
  tillage & spraying based on temp, humidity, wind, rainfall, soil moisture/temp

---

## 8. Scouting
Guide: `/scouting/` — create, assign, and complete on-the-ground field inspection
tasks; produce reports.

- [ ] Task Description — General + Report views per task
- [ ] General — task owner edits name/description, uploads field photo, closes task
- [ ] Report — scout fills inspection date, client, field number, area, crop,
  hybrid, sowing date, developmental phases, plant density, final review & comment
- [ ] Download — export task report as a spreadsheet (Export button)
- [ ] Closed Tasks — completed tasks auto-move to Closed tab, shown closed on map

---

## 9. Overview
Guide: `/overview/` — account-/season-wide analytics and reporting. Contains three
major sub-modules.

- [ ] Season Analytics — season summary (name, duration, full/limited-access field
  counts & area); widgets: Crops, Sown areas by crop, Field activity log status,
  Activities costs, Weekly Crop Performance (NDVI), top-10 best/worst fields
- [ ] Field Leaderboard — rank fields by NDVI value change; sub-features:
  - [ ] Default ranking (latest image, most negative NDVI change)
  - [ ] Notifications (email on new imagery / leaderboard updates)
  - [ ] NDVI Drop ranking
  - [ ] Parameters (8 arrangement categories)
  - [ ] Color Code (red drop / green rise / white no change)
  - [ ] Group filter, Crop filter
  - [ ] Download (PDF / XLS)
  - [ ] Select Date (report date)
  - [ ] Free Account limits (Demo field only)
  - [ ] Sort (7 attributes)
- [ ] Custom Report — build tabular field reports:
  - [ ] Create first template (name, choose columns)
  - [ ] Create new template
  - [ ] Update / Edit / Delete template
  - [ ] Filter data (crops, field groups)
  - [ ] Available data columns (crop rotation, field info, indices NDVI/NDRE/MSAVI/ReCI/NDMI,
    yield estimation add-on, current risks)

---

## 10. VRA Maps (Variable Rate Application / Zoning)
Guide: `/vra-maps/` — productivity zoning and variable-rate prescription maps for
machinery.

- [ ] Getting started (VRA maps submenu: Seeding / Nitrogen / P&K / Map Builder)
- [ ] Create Sowing maps (period + zones 2–7; export; per-zone input rates)
- [ ] Create Nitrogen fertilization maps (index + date + zones + detail; opacity)
- [ ] Create P&K fertilization maps (period + zones; export)
- [ ] Map Builder (multi-layer: vegetation/moisture indices + elevation + uploaded
  yield data; weights; opacity; up to 5 layers)
- [ ] Calculate savings on variable-rate application (total savings calculator)
- [ ] Supported formats for agriculture machinery (SHP — John Deere/Amazone/Trimble/
  universal; ISO-XML for ISOBUS)
- [ ] Save the created maps (maps list on the field page)

---

## 11. Field Activity Log
Guide: `/field-activity-log/` — plan, track, and cost field activities on an
interactive calendar.

- [ ] Location (separate sidebar tab) + Demo Field
- [ ] Log Structure — Field column, Sowing Dates column, Activity Calendar
- [ ] Activity status & color — single-day, multi-day, behind/ahead of schedule,
  completed-in-past; color states (gray/red/blue/green/yellow)
- [ ] Add activity — via "+" button or directly on calendar; planned vs completed;
  multiple fields at once; cost (estimated/actual); description
- [ ] Organize activities — filters: year, field group, crop type, activity type
- [ ] Edit activity (pencil)

---

## 12. Data Manager
Guide: `/data-manager/` — upload and visualize machine/equipment field data, and
integrate external farm-management accounts.

- [ ] Data — Uploading Datasets (ZIP of SHP/SHX/DBF/PRJ; three upload paths)
- [ ] Dataset Processing (async processing + notification)
- [ ] Assigning Data to the Field (create-and-assign new field, or add-activity to
  matching field; overlay)
- [ ] Data Visualization (per-parameter maps: yield, moisture, sowing density, etc.)
- [ ] Connections — Data Integration (John Deere: connect org, choose season,
  boundaries-only or boundaries+machinery data)
- [ ] Connections — Data Update (refresh integrated org/field/equipment changes)

---

## 13. Field Manager
Guide: `/field-manager/` — organize fields by season (crop rotation) and by group.

- [ ] Crop Rotation calendar — fields × seasons grid; field statuses (not in season /
  in season no sowing / in season with sowing)
  - [ ] Manage sowing (add field to season, add/edit/delete sowing parameters:
    crop, irrigation, tillage, sowing/harvest dates, yield)
  - [ ] Crop Allocation (auto-distribute crops across fields; rotation-matrix
    indicators green/yellow/gray/none)
- [ ] Field Groups — group fields by characteristics
  - [ ] Add group (name + fields; one field per group)
  - [ ] Manage group (add/remove fields, rename, delete)

---

## 14. Team Management
Guide: `/team-management/` — shared team accounts with roles and access control.

- [ ] How to add a user (invite by email, select fields/groups, assign role)
- [ ] Roles — Admin, Scout, Observer (permission sets per role)
- [ ] Team Management dashboard (members, roles, accessible fields, last active, actions)
- [ ] Actions (edit access, reassign role, remove user, resend invitation)
- [ ] Edit Team name
- [ ] Switch Team (member of multiple teams)
- [ ] Default Team (set default team)

---

## 15. Settings
Guide: `/settings/` — account-level preferences.

- [ ] Interface language
- [ ] Metric system (units)
- [ ] Show/hide demo content (Pro only; demo field, demo scouting tasks, demo dataset)

---

## 16. Account & Pricing
Guide: `/account-and-pricing/` — subscription plans and add-on marketplace.

- [ ] Plans — Essential (up to 1000 ha), Professional (choose hectares), Enterprise
  (custom, >5000 ha / coops / advisors / IT)
- [ ] Pricing page access (upgrade arrow)
- [ ] Add-ons / Marketplace (e.g., Disease risk, Yield estimation, extra indices)

---

## 17. Access Through API
Guide: `/access-through-api/` — programmatic access to the platform.

- [ ] Current API capabilities — extended satellites (Sentinel-2/1, Landsat 8/7/5/4,
  MODIS, NAIP, CBERS-4), extended indices (NDVI, EVI, GNDVI, CVI, NDRE, MSAVI, RECI,
  NDSI, NDWI, SAVI, ARVI, GCI, SIPI, NBR, MSI, ISTACK, FIDET, CCCI), 20-year weather archive
- [ ] Get access — My Account → API → Get started → register on developer portal for API key

---

## Cross-cutting concepts (not standalone sidebar modules, but pervasive)

These appear across many modules and likely need shared specs:

- [ ] Plan gating model (Free / Essential / Professional / Enterprise / Add-ons)
- [ ] Cloud & shadow masking + cloudiness thresholds
- [ ] Vegetation index engine (shared index list, legends, standard vs contrast palettes)
- [ ] Satellite imagery sourcing & date availability (Sentinel-2 default, PlanetScope add-on, 2016+ history)
- [ ] Notifications (email + in-app)
- [ ] Demo / gift field behavior
- [ ] Export/download formats (TIFF, SHP, GeoJSON, KML/KMZ, XLS, PDF, ISO-XML)
- [ ] Account / My Account menu (entry point for Team Management, API, Settings, Pricing)
