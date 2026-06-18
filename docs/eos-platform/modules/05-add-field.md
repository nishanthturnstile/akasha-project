# Module 05 — Add Field

Guide page: <https://eos.com/user-guide/crop-monitoring/add-field/>

## Purpose
All ways to create field boundaries in the account. Fields are the prerequisite for
satellite imagery, weather, and analytics. Entry point: **+ADD FIELD** button
(bottom-right). A dialog offers three options:
- **Draw field on map**
- **Upload fields**
- **Custom upload** (contact EOSDA — bespoke/large imports)

## Sub-features

### 5.1 Draw field boundary
- The drawing tool is active by default on the field-drawing page.
- Place the first point on the map, add points, **double-click the first point to
  close**. Minimum **3 points** to complete.
- After completion, save the field and proceed to analytics (indices, etc.).
- **Multiple fields in one session:** after finishing one, click the drawing tool
  again to draw another; save all to the field list when done.

#### 5.1.1 Round boundaries (Circle tool)
- Place a center point and stretch the circle to size; adjust by dragging one of the
  four handle points.

#### 5.1.2 Cut parts of a boundary (cutting tool)
- Remove unwanted areas (buildings, ravines, roads, unplanted zones) for more
  accurate vegetation data.
- Activate the cutting tool, draw the contour to remove, close it; the area is cut
  and the field area is **recalculated**.

### 5.2 Upload fields — without parameters
- Upload files with pre-drawn contours. Supported: **.shp, .kml, .kmz, .geojson**.
- Drag-and-drop onto the page, or click **Add your fields**.
- When contours + field-card data appear, click **ADD TO MY FIELDS** (or **Cancel**).
- A modal offers **SAVE AND CONTINUE** (add to list) or **DELETE AND CONTINUE**
  (discard).
- Then enrich the field: **Field Name**, **Group Name**, **Crop Rotation data**
  (crop, sowing date, season — accuracy of monitoring depends on correct rotation data).

### 5.3 Upload fields — with parameters (Fields Upload Manager)
- Triggered when the uploaded .zip(.shp/.dbf/.prj/.shx), .kml, .kmz, or .geojson
  contains attributes like crop type, field name, group, sowing date, harvest date,
  notes, season.
- A **Fields upload manager** opens showing the file's parameters auto-classified
  into columns. Per column, a drop-down maps it to the correct platform parameter,
  or **Skip** to hide it.
- For **Sowing date** / **Harvesting date** columns, the user must select the
  **date format** used in the file. Dependency: sowing-date mapping is only enabled
  after a crop is selected; harvesting-date only after sowing date is set.
- **Reconcile seasons/crops/groups:** for values in the file (e.g. "No data" and
  "2023"), assign each to an account season/crop/group. Groups can map to an existing
  group or a newly created one (enter name → "add new group").
- Final step: map + field-list verification → **ADD TO MY FIELDS** saves fields with
  the chosen parameters into the selected seasons.

### 5.4 Supported file formats (reference)
- **SHAPE FILE** — `.shp` geometry (mandatory), `.shx` index (mandatory), `.dbf`
  attributes (mandatory), `.prj` coordinate system (important). Only polygon
  geometry (≥3 connected points) is imported.
- **KML / KMZ** — full layer/map elements; only polygon geometry is imported.
- **GeoJSON** — points/lines/polygons/multitypes; only polygons are imported.
- **ZIP** — archive bundling shapefile parts (.shp/.shx/.dbf/.prj).

### 5.5 Upload error types (validation messages)
- **Missing .prj** — coordinate system undeterminable; add .prj and re-upload.
- **Unsupported format** — must be .shp/.kml/.geojson or a zip of .shp/.shx/.dbf.
- **No polygons found** — points/lines/labels/photos/roads are unsupported; need a
  polygon (≥3 connected points).
- **File > 10 Mb** — zip shapefiles; or split many objects across 2+ files.
- **Intersecting contours** — overlapping/self-crossing contours not allowed; fix at
  source.
- **Field > 10,000 ha / 24,710 ac** — too large; resize at source or draw manually.

### 5.6 Latest Image layer (during add/inspect)
- If the default basemap is stale, switch to **Latest Image** layer → zoom to ~2 km →
  **Search this area** to fetch the most recent image for the visible extent; choose
  among available image dates; if none, pan elsewhere or revert to default map.

## Constraints (for replica)
- Polygon-only; min 3 vertices; max area 10,000 ha; max upload 10 MB; no
  self-intersections; CRS required (.prj for shapefiles).
- Area auto-recalculates after cut operations.
- Upload-with-parameters is effectively an import wizard with column mapping + entity
  reconciliation (seasons/crops/groups) — the most complex part of this module.

## Notes for replica
- Drawing stack: polygon + circle + cut (difference) operations with live area
  recompute.
- Importer: parse SHP/KML/KMZ/GeoJSON → extract polygons → optional attribute column
  mapping → reconcile to seasons/crops/groups → persist. Enforce all validations as
  typed errors with the same user-facing messages.
