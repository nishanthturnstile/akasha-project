# Module 06 — Fields / Monitoring (field analytics)

Guide page: <https://eos.com/user-guide/crop-monitoring/fields/>

## Purpose
The single-field analytics workspace (the product's analytical core). With a field
selected, the right-hand panel + map exposes imagery sources, a date timeline, crop
agronomy info, charts, the vegetation-index engine, value details, downloads, and
cloud masking. Default index on open = **NDVI**.

## Sub-features

### 6.1 Image sources
- **Sentinel-2** at **10 m** resolution is the default source.
- Optional **PlanetScope** at **3 m**, daily — can be connected.
- Both sources allow adjustable **cloud + shadow coverage thresholds** so statistics
  use a representative selection; visual checks via **Natural Color** when needed.
- The source/layer selector (panel showing the satellite name, e.g. "Sentinel 2")
  also exposes terrain layers:

#### 6.1.1 Elevation map
- Digital elevation model of the field; reveals flood zones, limited-water areas,
  erosion, etc. Combined with NDVI/productivity to flag growth-impeding factors and
  estimate true field size (for seed/fuel cost & treatment-time calc).
- Access: click the satellite-name panel → select **Elevation map** from the dropdown.
- Visual: shade gradient (dark green lowlands → dark red highlands); hover shows
  actual elevation in **meters**.
- **Download** as **.tiff** (download arrow, lower-right panel).

#### 6.1.2 Slope map
- Terrain slope steepness in **degrees**; shade gradient (red steep → dark green
  gentle); color meanings in the legend.

### 6.2 Date line (timeline)
- Shows all available images; selecting a date applies the chosen index to that day's
  image.
- Hover a date → preview with **% cloud & shadow** coverage and acquisition time (GMT).
- Free tier: last **3 months** of imagery. Imagery from **2016** onward requires
  Essential/Professional (also available on the gift field). Year via calendar icon.
- Default: only images with **<50% cloud cover** shown; threshold adjustable in
  account settings.

### 6.3 Crop info panel
Shows crop data/analytics for the field within the active season:
- **6.3.1 Crop rotation** — empty by default; add a crop via **+ Add crop** (crop +
  sowing date drive growth stages, risks, yield). Multiple crops per season
  supported; pick one via radio button. Crop switching only in the season being
  viewed. Correct crop/sowing date is required for accurate results.
- **6.3.2 Growth stages** — current stage per the **BBCH** system; view stage start
  dates and switch stages. Per crop/stage the platform marks **recommended** indices
  (research-validated, most informative) vs **additional** indices (supporting/
  verification). Some crops need manual entry of the stage start date (edit growth
  stage → pick start date). Availability varies by crop.
- **6.3.3 Current risks** — requires Essential/Professional. Each risk has a
  probability level; click a risk icon to expand details. **Disease risks** are a
  paid **add-on**.
- **6.3.4 Yield estimation** — available as an **add-on**; relevant for certain crops.

### 6.4 Charts
Show the dynamics of the selected index/metric over time.
- **6.4.1 Vegetation indices chart** — index curves; toggle each curve via colored
  legend buttons; compare across years.
- **6.4.2 Weather chart** — choose a data type from the dropdown:
  - Temperature section: min/max temp (°C), threat of cold/heat stress.
  - Moisture section: precipitation (mm), root-zone moisture, soil-surface moisture (%).
- **6.4.3 Temperature** — min-temp history (cold threat at **−6 °C**) and max-temp
  history (heat stress at **+30 °C**) curves.
- **6.4.4 Moisture** — precipitation (mm), soil-surface moisture (top few cm),
  root-zone moisture curves for irrigation planning.
- **6.4.5 Growth stages** — current crop stage (needs crop + sowing date for some
  crops).
- **6.4.6 Period intervals** — default 1 year or the calendar-selected range; **Update**
  resets to the annual overview.

### 6.5 Indices (vegetation-index engine)
Default date-line index = NDVI; pick another from the dropdown. Index catalog:

Core (in monitoring):
- **VMI** — Vegetation Meta Index; RGB composite (R=MSAVI, G=NDRE, B=NDVI);
  crop/region/time-independent color scheme; EOSDA-developed, early stage.
- **NDVI** — vegetation vigor; low = pest/disease risk, abnormally high = weeds.
- **NDRE** — red-edge; nitrogen/photosynthetic activity mid/late season; aging
  vegetation & disease; harvest timing.
- **MSAVI** — soil-adjusted; early emergence with much bare soil; early-stage
  fertilizer maps.
- **ReCI** — red-edge chlorophyll; chlorophyll∝nitrogen; flags yellow/faded leaves.
- **NDMI** — moisture index (NIR vs SWIR); water-stress detection; range −1..1.
- **Natural color** — true image to verify clouds/haze/fog/shadow didn't skew data.

Add-on indices: **GNDVI, EVI, SIPI, ARVI, RENDVI, PSRI, GCI, NDYI, NRFI, NDPI**.
**CI (Custom Index)** — request a custom formula/threshold from EOSDA.
(Unlisted indices can be requested via support.)

### 6.6 Details
- Expand (panel above the analytics window) to inspect the field's index value
  breakdown; display in **hectares or percentages**; **download as XLS**.

### 6.7 Download
- Download the index map as **.tiff** (rendered image with index applied) or **.shp**
  (per-pixel index value at each point), or field contours.

### 6.8 Mask filter
- Recognizes **clouds, cirrus clouds, cloud shadows** to account for them in index
  calculation. All three masks on by default; each can be toggled off in the dropdown.
- Accuracy caveat: verify against Natural Color via Split View.

### 6.9 Available features for crops
- A large **crop × feature** support matrix indicating which feature groups are
  available per crop. Used to know, per crop, what analytics the platform supports.
- Full captured matrix: [Crop × Feature Support Matrix](../data/crop-feature-support-matrix.md)
  (`286` crop rows × `7` feature columns: Disease Risk, Growth Stages, Yield
  Estimation, Variety, Weather Risk, Recommended indices, Typical index range).
- Implementation note: model as a `crop → { growthStages, recommendedIndices,
  additionalIndices, yieldEstimation, risks }` capability map; the table is data,
  not logic.

### 6.10 Weather shortcut
- From Monitoring, a **Forecast** action / **Weather** analytics tab jumps to the
  Weather page (module 07) for deeper weather analysis.

## Plan gating summary
- PlanetScope (add-on source), imagery >3 months / pre-2016 (Essential/Pro),
  Current risks (Essential/Pro), Disease risk + Yield estimation (add-ons).

## Notes for replica
- This module is the convergence point of: imagery sourcing, the index engine,
  cloud masking, agronomy (crop rotation/BBCH/risks/yield), weather series, and
  export. Build the index engine + masking first (Akasha already has NDVI/NDMI/
  NDWI/MSAVI), then layer crop agronomy and charts.
- Index dropdown should be data-driven from a per-source supported-index list and a
  per-crop recommended/additional split.
- Exports: TIFF (rendered), SHP (per-pixel values), XLS (value breakdown).
