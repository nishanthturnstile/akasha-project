# Module 03 — Work with Crop Map

Guide page: <https://eos.com/user-guide/crop-monitoring/work-with-crop-map/>

## Purpose
The main map canvas and its global navigation, measurement, comparison, and
multi-field overlay tools. This is the spatial workspace where the user finds
locations, draws/inspects fields, compares imagery, and visualizes index data
across many fields at once.

## Sub-features

### 3.1 Find Location
- Two ways to recenter the map:
  1. **Search box** — type a place/geographic name.
  2. **Coordinates** — enter coordinates in the search box, **longitude first,
     latitude second**. Use a leading minus for southern latitudes / western
     longitudes.
- Entry point for getting to a field's area before drawing/adding it.

### 3.2 Zoom tool
- On-map "+" / "−" controls; mouse wheel does the same.

### 3.3 Distance & Area measurements
- Measure tool in the left sidebar.
- Outline a shape to get total **area**, or trace a path to get **distance**.
- Result is displayed at the bottom of the screen.

### 3.4 Split View
- Side-by-side comparison of the SAME field across two independent viewers.
- Each viewer has its own **timeline** (date) and its own **index switch**, so the
  user can compare: same index across two dates, OR two different indices on the
  same date.
- Supports the 5 core vegetation indices for comparison.
- Synchronized hover: hovering a point in the field shows that point's index value
  on BOTH viewers simultaneously (compare same location, different date/index).
- Legend can be expanded per viewer (same as single view).
- Default: NDVI on the last available image date for the selected field.
- Date selection via timeline or via a calendar (available image dates highlighted
  in white).
- Per-index **download** button next to the index name.
- Enter via the Split view icon on the left menu (with a field selected); exit back
  to single view via the corresponding icon.
- Historical index data goes back **5 years**.
- Use cases called out: track vegetation development over time; detect water stress
  via NDMI; cross-check NDVI against another index in early growth (bare soil skews NDVI).

### 3.5 Layers (multi-field overlays)
"Layers" visualizes the state of ALL fields at once via a drop-down with 5 layers.
The system only uses images with **<90% cloudiness** that cover all fields; cloudy
areas get a mask. Zoom in to resolve pins into field outlines. Crop + year filter
(right menu) lets the user analyze a crop's history across all fields over 5 years.

- **3.5.1 My Crops layer** — fields colored by crop; legend bottom-right; shows most
  recently planted crops by default; crop + year filter; visualizes 5-year rotation.
- **3.5.2 Vegetation layer** — average **NDVI** per field, bucketed into **10 ranges**
  (color legend). Selecting a field on the map switches to that field's monitoring
  (NDVI at selected date). Can create a new field group from vegetation data.
  Default = last available image (images that include all fields). Images >1 year
  old are Pro-only; over-acreage fields are marked with a Pro icon.
- **3.5.3 Water Stress layer** — average **NDMI** per field, 10 ranges. Field
  select → monitoring (NDMI). Default last available image. **Pro only.**
- **3.5.4 Vegetation Rating layer** — fields ranked by average NDVI (a map analogue
  of Field Leaderboard). Default last available image. Field/crop/year filter.
  **Pro only.**
- **3.5.5 Crop Classification layer** — country-wide EOSDA crop classification map.
  **Ukraine only.** Crop list legend replaces the index legend. Filter by season
  only. Any field on this map can be added to the user's Field List (select → Add
  Field). **Pro only.**

### 3.6 Contrast View
- Toggle (icon, lower-right of map; turns blue when active) between **Standard** and
  **Contrast** palettes for the displayed index.
- **Standard** view: best when index values span a wide range (e.g. NDVI −1..1);
  smooth shade transitions, low contrast.
- **Contrast** view: stretches low-variability values into distinctly different
  colors to reveal problem areas otherwise hidden in similar shades.
- Applies to all indices, including NDMI.

### 3.7 Latest Image layer
(From the combined guide's "Layers" basemap section.)
- When the default basemap is stale, switch to the **Latest Image** layer to see
  recent (weeks-old) satellite imagery for the area.
- Workflow: switch to Latest Image → zoom to ~2 km scale → click **Search this
  area** to fetch the latest available image for the visible extent.
- Can pick among other available images by clicking an image date.
- If none available, pan to another area or revert to the default map.

## States / notes
- Multi-field layers depend on "available images" = images that cover all of the
  user's fields at once; cloudy regions are masked.
- Heavy plan gating: Water Stress, Vegetation Rating, Crop Classification, and
  >1-year-old imagery are Pro-only.

## Notes for replica
- Map canvas = base map + per-field vector overlays + raster index tiles. The 5
  "Layers" are aggregate per-field colorings driven by an average index value per
  field for a chosen date — distinct from the single-field raster index view.
- Split view = two synced map instances sharing geometry + a synced cursor readout.
- Contrast view = alternate color-ramp stretch (percentile/standard-deviation based)
  applied to the same index raster.
- Coordinate order (lon, lat) and minus-sign convention should match.
