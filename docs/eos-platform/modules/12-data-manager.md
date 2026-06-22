# Module 12 — Data Manager

Guide page: <https://eos.com/user-guide/crop-monitoring/data-manager/>

## Purpose
Upload machine/equipment field data (harvesting, fertilization, spraying, planting,
etc.) from a vehicle's on-board computer and visualize it as parameter maps (yield,
moisture, sowing density, and other recorded technological parameters). Also
integrates external farm-management accounts (John Deere) via **Connections**.
Separate sidebar tab. Use: quality-control of field-activity completion (application
rates, seed rate, harvested amount/moisture, etc.).

## 12.A Data (dataset upload & visualization)

### 12.1 Uploading Datasets
- Save data as a **ZIP** containing **SHP** format (full set: SHP, SHX, DBF, PRJ;
  PRJ may be absent).
- Three upload paths: drag-drop to the **Data** field, drag-drop to the **viewer**,
  or **Add Dataset** → pick a file.

### 12.2 Dataset Processing
- Async; user can keep working. A green **notification** appears on success. Open the
  processed ZIP from the **Data** field to continue.

### 12.3 Assigning Data to the Field
Two scenarios:
- **No matching field** → a **Create and Assign Field** form: name the field, select
  activity type, start date, optional description, choose parameters from the map (as
  configured in the equipment's on-board computer). The new field auto-appears in the
  system. Editable later.
- **Matches one/more fields** → an **Add Activity** window: select activity, select
  parameters, optional description, select the matching field(s) (check the **Overlay**
  value), select start date → **Assign Field**.

### 12.4 Data Visualization
- Assigned activities show in the **Data** field; click a completion date to view the
  visualized data. Switch between **parameters** via the legend (color↔value).
- Parameters and their numeric values come from the file and are **read-only** — you
  may only switch/compare parameters.

## 12.B Connections (external integrations — John Deere)
The **Connections** section (in the Data Manager tab) links a John Deere account.

### 12.5 Connect
- **Connect** → John Deere authorization (username/password/Sign In) → returns with a
  list of your John Deere **organizations** → **Connect** an org → grant access in
  John Deere settings → org shows as **connected**.

### 12.6 Data Integration
- Click a connected org → list of its fields. Before integrating, choose:
  - **Add to season** — target season for the data.
  - **Integrate a data type**: **Field boundaries** (boundaries + names only) or
    **Field boundaries and Machinery data** (also equipment data).
- Only equipment data with execution dates matching the selected season is integrated.
- Select multiple/all fields → **Save**. Re-integration marks already-integrated
  fields. Success → **Notifications** entry. Equipment data lands in the **Data** section.

### 12.7 Data Update
- **Update** (Connections) re-syncs when: new equipment data appears for integrated
  fields in the current season; field names/boundaries changed in John Deere;
  integrated fields moved to other seasons.
- The org-list **Update** also refreshes org-level changes: org renamed, fields
  added/removed, org deleted, new org added.

## Cross-references
- Uploaded datasets feed **Map Builder** "Uploaded files" layer (module 10).
- Integrations create fields/activities (modules 05/11) and post Notifications.

## Notes for replica
- Two halves: (a) self-serve SHP dataset upload → async processing → field
  assignment (create-or-match) → read-only parameter map visualization; (b) OAuth-style
  external connector (John Deere) with org/field sync, season-scoped data-type
  integration, and an update/refresh job.
- Parameter maps are categorical/continuous rasters rendered from the file's columns.
