# Module 09 — Overview

Guide page: <https://eos.com/user-guide/crop-monitoring/overview/>

## Purpose
Account-/season-wide analytics and reporting. Bundles three substantial
sub-modules: **Season Analytics** (season dashboard), **Field Leaderboard**
(priority ranking by NDVI change), and **Custom Report** (configurable tabular
reports). Figures are computed from **full-access (Pro) fields only**.

---

## 9.A Season Analytics
A season dashboard. All figures use full-access fields only.

### Header summary
- Season **Name**, **Duration** (dates).
- Count + total area (ha) of **full-access** fields.
- Count + total area (ha) of **limited-access** fields.

### Widgets
- **Crops** — list of crops sown this season with, per crop, the number of fields
  and total area. For an **active** season, a **Risks** indicator shows how many
  fields are affected; clicking it lists the affected fields.
- **Sown areas by crop** — visual area breakdown per crop, with each crop's % of
  total area.
- **Field activity log** — per crop, total activities split into **Planned /
  Progress / Overdue / Completed**.
- **Activities costs** — costs per crop from the Field Activity Log; requires costs
  on both planned and completed activities; shows planned-vs-actual deviation.
- **Weekly Crop Performance** — average crop development over time by NDVI across all
  season fields with the selected crop:
  - Y = NDVI value; X = weeks since the earliest sowing date of the crop.
  - Hover shows the week's average NDVI plus that week's max/min.
  - Below: tables of **top-10 best** and **top-10 worst** fields for the crop,
    split by whether a field's average NDVI is above/below the crop's overall
    average. Active season only.

---

## 9.B Field Leaderboard
Prioritize field management by **NDVI value change**. Arranges all fields by 1 of
**8 categories**: Name, Location, Area, Group, Crop, Index value, Value change,
Image date. Each arrangement is an exportable ranked list (PDF and/or XLS).

### Default
- Arranged by **latest available image** and **most negative NDVI change** (so the
  most urgent drops surface first, even vs. fields with older images).

### Notifications
- On new imagery for any field(s), the leaderboard updates and emails the user.
- Email contains, per field: current index value, change vs previous image, field
  name, location, new image date, previous image date. Up to **3 top** fields per email.

### NDVI Drop
- Rank purely by NDVI change: largest drop → top, largest rise → bottom.

### Parameters
- Click a parameter above the leaderboard to switch arrangement; the active one
  lights up; only one active at a time.

### Color Code
- Drop = red with "−"; rise = green with "+"; no change = white.

### Group
- Filter by group: All groups, fields without a group, or a specific group.

### Crop
- Arrange by currently growing crop (fields lacking crop-rotation data can't be
  arranged by crop).

### Download
- Up to **9 different** arranged lists; export each as PDF and/or XLS (auto-starts).

### Select Date
- A **Report date** field above the leaderboard; pick a date in the popup calendar →
  leaderboard refreshes to the NDVI change between the two images preceding that date
  (~3–5 day cadence).

### Free Account
- Field Leaderboard requires Essential/Professional; Free users can try it on the
  **Demo field** only.

### Sort
- Additionally sort within the leaderboard by **7 attributes**: Name, Location, Area,
  Group, Index value, Value change, Image date (asc/desc as applicable). Up to 7
  different sorted leaderboards, each exportable (PDF/XLS).

---

## 9.C Custom Report
Generate configurable tabular reports on current field state. No limit on number of
reports; tables scroll vertically/horizontally. **Created per chosen season and for
Pro fields only** (limited-functionality fields are excluded).

### Lifecycle
- **Create first report** — Create template → name it → pick from available columns
  → reorder columns (drag) → hide unneeded columns (Field and Crop columns have fixed
  order and cannot be hidden) → Save (kicks off data processing, seconds–~1 hour).
- **Create new template** — click current template name → Create new template →
  same flow.
- **Update existing template** — a banner appears when data is stale; **Update data**
  reprocesses.
- **Edit existing template** — Edit (same steps as create).
- **Delete template** — Delete + confirm; irreversible.
- **Filter data** — filter table by crops and field groups.

### Data available in Custom Report
1. **Crop rotation**: Crop, Maturity, Variety, Sowing/Planting date, Harvesting
   date, Target yield t/ha, Actual yield t/ha.
2. **Field info**: Field name, Field group, Area, Tillage type, Irrigation type.
3. **Indices** (NDVI, NDRE, MSAVI, ReCI, NDMI): date of last image, index value of
   last image, change vs previous image, NDVI values split.
4. **Yield estimation** (add-on, some crops): dry biomass tons & t/ha, dry yield
   tons & t/ha, wet yield tons & t/ha, recommended harvesting date.
5. **Current risks** (some are add-ons, some crops): index risk, disease risk, cold
   stress risk, hot stress risk, rainfall risk, wind risk.

## Notes for replica
- Three distinct features sharing the Overview entry. Season Analytics = aggregation
  dashboard; Field Leaderboard = ranked, exportable, notification-driven list;
  Custom Report = user-defined column templates over per-field computed metrics with
  async processing.
- Strong Pro/full-access gating across all three (limited fields excluded from figures).
- Reuses: activity statuses (module 11), costs (module 11), risks (module 06),
  group/crop filters (module 02), index metrics (module 06).
