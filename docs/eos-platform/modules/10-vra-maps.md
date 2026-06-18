# Module 10 — VRA Maps (Variable Rate Application / Zoning)

Guide page: <https://eos.com/user-guide/crop-monitoring/vra-maps/>

## Purpose
Productivity zoning and variable-rate prescription maps that split a field into
zones and assign per-zone input rates (seed/fertilizer), exportable to farm
machinery. ("Zoning" in the onboarding videos = this module.) Zone data is derived
from vegetation indices (and optionally elevation / uploaded machine data).

## Entry & navigation
- Right sidebar → **VRA maps** → submenu picks a map type:
  - **Seeding** — variable-rate seed planting + soil sampling.
  - **Nitrogen** — variable-rate nitrogen fertilizer.
  - **P&K** — variable-rate potassium + phosphorus fertilizer.
  - **Map Builder** — multi-layer combined (indices + elevation + uploaded data).
- Then choose a field → its maps list (only maps of the current type) → open a map or
  **+ Create map**.

## Common patterns (all map types)
- **Zones:** 2–7 (default 3). Per-zone you manually enter input **amount per ha/ac**;
  the system computes the **total per zone** as UOM.
- **Color meaning:** red = lower productivity/vegetation; green = higher.
- **Export:** **EXPORT** → choose format → auto-download. Hover a format for two
  options: **Get link to this map** (clipboard link, valid **10 days**) or
  **Download this map** (file).
- Created maps are saved to the field's maps list (see Save maps below).

## Sub-features

### 10.1 Create Sowing maps
- Based on **average productivity over a selected period** (NDVI), period from **2016**.
- Pick period (use the widest range for precision; avoid current year if unharvested)
  + number of zones → **CALCULATE** (≤ ~1 min).
- Algorithm uses all cloudless images in the period, excluding anomalies.
- Use: differential sowing, P&K application, precision soil sampling.

### 10.2 Create Nitrogen fertilization maps
- Based on a **single recent image** + chosen vegetation index.
- Steps: select index → select **Date** (one of the latest images; previewable) →
  number of zones + **detail level** (max detail for small fields, lower for large)
  → **CALCULATE** (seconds).
- **Opacity slider** (default 80%) overlays the natural image to spot anomalies;
  0% = natural view, 100% = full map view.

### 10.3 Create P&K fertilization maps
- Same approach as Sowing maps: representative **period** (from 2016) of average
  productivity (NDVI) + zones → CALCULATE; cloudless-image, anomaly-excluded algorithm.

### 10.4 Map Builder (multi-layer)
- Combine up to **5 layers** to compute zones:
  - Step 1: number of zones (2–7; 3–5 typical) + level of detail.
  - Step 2: **+Add layer** from: vegetation indices (NDVI, NDRE, MSAVI, ReCI),
    moisture indices (NDMI), Elevation map, plus any **custom indices**, and
    **Uploaded files** (machine/yield data from Data Manager).
  - Step 3: pick a satellite-image **date per layer** (Elevation needs no date).
  - Step 4: set each layer's **weight** (relative influence, e.g. NDVI 100% vs
    Elevation 50% → 2:1). **Opacity** helps visually compare layers (does not affect
    calculation).
  - **CALCULATE** → map + zones (Zone 1 = highest values). **Parameters** tab compares
    the result against source layers.
- **Map from Yield Data:** add an **Uploaded files** layer → latest Data Manager file
  for the field auto-added; choose another file via "Activity and date"; or upload a
  new file; select the data layer in **Parameters** (yield/seeding recommended).

### 10.5 Calculate savings on variable-rate application
- **Total savings calculator** (after a VRA map exists) compares VRA vs flat-rate.
- Inputs: per-zone input amounts (UOM/ha or /ac), **price per unit** (currency
  auto-by-location), flat-rate amount.
- Outputs: total fertilizer (flat-rate), total budget (flat-rate), fertilizer saved,
  total money saved.

### 10.6 Supported formats for agriculture machinery
- **SHP** — John Deere, Amazone, Trimble, plus a **universal SHP**. Trimble displays:
  CFX 750 (FM-750), FmX (FM-1000), CFX-350 (XCN-750), GFX-750 (XCN-1050),
  TMX-2050 (XCN-2050).
- **ISO-XML** — ISOBUS equipment.

### 10.7 Save the created maps
- After create/save/download, the map appears in the **maps list on the field's page**
  (per type).

## Plan/data notes
- Sowing/P&K use multi-year period averages; Nitrogen uses a single recent image;
  Map Builder is weighted multi-layer. All produce per-zone prescriptions.
- Shareable map links expire after 10 days.

## Notes for replica
- Core engine: zone segmentation (k-zones) over a chosen raster basis (period-average
  index, single-date index, or weighted multi-layer composite incl. elevation +
  uploaded machine rasters), then per-zone rate entry → totals → export (SHP/ISO-XML).
- Reuses: index engine + elevation (module 06), uploaded datasets (module 12).
- Savings calculator is a standalone cost model on top of a created map.
