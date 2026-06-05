---
goal: EOSDA Crop Monitoring map-screen UI replication — section-by-section capture + Akasha mapping + implementation plan
version: 1.0
date_created: 2026-06-04
last_updated: 2026-06-04
owner: Akasha Engineering
tags: eos, crop-monitoring, ui-parity, map-screen, frontend, maplibre, layout, deep-linking
---

# EOS Crop Monitoring — Map Screen UI Parity Plan

This document captures the **EOSDA Crop Monitoring "Field analytics" map screen** UI section by
section from the **live logged-in application**, maps every region/control to the corresponding
Akasha frontend component, identifies gaps, and defines an implementation plan to replicate the
same layout, placement, and interaction behavior in Akasha — using **Akasha branding and styling**
(GUD-002: replicate structure/behavior, do **not** copy EOS visual assets), keeping **true-colour as
the default map layer** (REQ-007), and routing everything through the **same-origin `/api/*` BFF**
(the browser never calls EOS directly).

> Scope: **map-screen layout + interaction parity only** (top bar, map, layer controls, right nav +
> its subsections, bottom timeline) plus **EOS-style deep-linkable URL state**. Deep functional
> wiring of non-map modules (Weather pages, VRA pages, Reporting, etc.) is tracked separately in
> [`feature-eos-crop-monitoring-parity-1.md`](./feature-eos-crop-monitoring-parity-1.md) and the
> [acceptance matrix](./eos-parity-acceptance-matrix.md).

---

## 0. Live validation method and evidence

- **Account / field validated:** `Field 10`, `42 ha`, Sentinel-2, NDVI overlay, Season 2.
- **Validated URL:**
  `https://crop-monitoring.eos.com/analytics/field/10975093?sceneID=S2B_tile_20260512_43PGQ_0&period_from=2026-03-05&period_to=2026-06-04`
- **Evidence captured this session:**
  - Full accessibility/DOM snapshot of the analytics screen (every control, `data-id`, and label).
  - Full-screen screenshot of the analytics workspace.
  - Focused screenshots of the right nav rail and the layer-control bar + bottom timeline.
- **Cross-referenced** with the prior live-exploration findings in
  [`eos-crop-monitoring-replication-research.md`](./eos-crop-monitoring-replication-research.md)
  (same account, captured 2026-06-02 on `Field 9`), which already enumerated the contents of every
  pop-up menu and accordion submenu.
- **Interactive click-through completed (2026-06-04):** the integrated browser became fully
  interactive this session, so every right-nav accordion, utility menu, account popover, source
  selector, and index selector was opened and read live — see [§14.1](#141-confirmed-live-via-interactive-clicks-2026-06-04)
  for the confirmed inventory.
- **Field-analytics screen confirmed live (2026-06-04):** the user drew **Field 11** (152.4 ha,
  `/analytics/field/10976428`), which unblocked the field-only controls. The **dynamic/static
  legend**, **cloud mask** (Cirrus/Clouds/Cloud shadows), **download** (NDVI.tiff/NDVI.shp/
  Contours.shp), the **scene filmstrip** (~17 S2 scenes), and the **analytics panel tabs**
  (Crop info / Chart / Activities) were all opened and read live — see
  [§14.1b](#141b-field-analytics-screen-confirmed-live-2026-06-04-field-11). The remaining gaps
  (calendar internals, season panel, split-view mode, plan-gated card contents) are tracked in
  [§14.2](#142-still-blocked--requires-a-configured-cropseason-or-paid-plan).

### Observed EOS frontend stack (for parity context only — not to be copied)

- **Angular + Angular Material** (`mat-expansion-panel`, `mat-mdc-menu-trigger`, `cdk-accordion`).
- Map is a full-bleed raster/vector canvas with a separate field-boundary overlay and an index
  raster overlay above true-colour basemap.
- State is **URL-encoded** (`/analytics/field/{id}?sceneID=...&period_from=...&period_to=...`).

Akasha stays on its existing stack: **React 18 + Vite + TypeScript + MapLibre GL + Terra Draw +
TanStack Query + react-router v6 + shadcn/Tailwind**.

---

## 1. Global layout map

```
┌────────────────────────────────────────────────────────────────────┬───────────────┐
│ TOP BAR: ← | ▱ Field 10 | 42 ha | ⤴Upgrade | ? | ✎edit | Get Overview│   RIGHT NAV   │
│                                              ............ All fields ▼│   (icon rail  │
├──────────────────────────────────────────────────────────────────── │   + accordion │
│  ┌ coord readout 13.19°N 77.49°E                      [scale 200 m]  ││   panels)     │
│  ┌MAP CTRL┐                                                          ││ ▣ Season 2    │
│  │ ⬓ split │            ░░░ FIELD BOUNDARY + INDEX RASTER ░░░        ││ ◆ Monitoring ▼│
│  │ ＋ / －  │                  over true-colour basemap               ││ ☁ Weather   ▼ │
│  │ 📏 ruler│                                                         ││ ✔ Activity log│
│  │ ◎ locate│                                                         ││ ▦ VRA maps  ▼ │
│  └─────────┘                                                         ││ ◉ Scout tasks │
│                                                                      ││ ▤ Data mgr  ▼ │
│         LAYER BAR ▸ [Sentinel-2 ▾][NDVI ▾][⚠][▣static][☁mask][⬇][⌃] ││ ⛓ Field mgr ▼ │
│   BOTTOM TIMELINE ▸ 📅 | ◀ 07Apr 09Apr … 12May ☁ 01Jun ▶ | Next img │├───────────────┤
│                                                          | ⛶ full    ││ ✦ AI assistant│
├──────────────────────────────────────────────────────────────────── │ 🔔 Notifications│
│ ANALYTICS PANEL (below map): [Crop info] [Chart] [Activities]        ││ ? Help Center▼│
│   Crop rotation | Sown area % | Growth stages | Current risks | …    ││ 🛍 Marketplace▼│
│                                                                      ││ 👤 Account   ▼ │
│                                                                      ││ Try Full / Up │
└────────────────────────────────────────────────────────────────────┴───────────────┘
```

Akasha shell today (for reference):
[App.tsx](apps/frontend/src/App.tsx) → `MapViewProvider` → [ProductRoutes.tsx](apps/frontend/src/routes/ProductRoutes.tsx)
→ [AppShell.tsx](apps/frontend/src/components/shell/AppShell.tsx) (grid: content `<Outlet/>` + right
`<aside>` 19rem) with [MapPage.tsx](apps/frontend/src/pages/MapPage.tsx) as the analytics workspace.

---

## 2. TOP BAR

### 2.1 EOS capture

| # | Control | DOM hook | Behavior |
|---|---------|----------|----------|
| 1 | **Back** (←) | `button` (e12) | Returns to previous view / all-fields map. |
| 2 | **Field glyph + name** | `▱ Field 10` (e18/e26) | Shows boundary thumbnail + active field name. |
| 3 | **Field area** | `42 ha` (e28) | Server-computed field area. |
| 4 | **Upgrade Plan** | `button "Upgrade Plan"` (e32) | Plan upsell → `/pricing`. |
| 5 | **Help** (?) | `button` (e40) | Contextual help. |
| 6 | **Edit field** (✎) | `button` (e45) | Enters boundary edit mode for the active field. |
| 7 | **Get Overview** | `button [disabled]` | AI/plan-gated field overview (disabled on current plan). |
| 8 | **All fields ▼** | `data-id=all-fields-btn` (e51) | Opens the all-fields list/selector panel (search, filter, field cards, add fields). Also reachable at route `/main-map/fields/all`. |

Behavior notes: selecting a field here drives the **URL** (`/analytics/field/{id}`) and refocuses
the map on the field; area and name come from the server, not the client.

### 2.2 Akasha mapping + gap

| EOS element | Akasha today | Action |
|---|---|---|
| Back, field name, area, edit, Get Overview | None — [TopBar.tsx](apps/frontend/src/components/map/TopBar.tsx) only floats Layers + ⌘K + theme toggle | **Build `FieldContextHeader`** rendered in the AppShell content header for the analytics route: back, field-name + boundary glyph, server `areaHa`, edit-field (drives `FieldDrawController` edit mode), disabled "Get Overview" placeholder. |
| All fields ▼ | [AllFieldsPanel.tsx](apps/frontend/src/components/fields/AllFieldsPanel.tsx) exists (left overlay) | Add a header **All fields** trigger that opens `AllFieldsPanel`; keep selection in `mapViewContext.selectedPlotId`. |
| Upgrade / Help | Akasha-branded placeholders | Render as branded buttons; non-functional placeholders for now. |

Guardrail: `areaHa` is **server-computed** (REQ-008) — never trust client area.

---

## 3. RIGHT NAV (icon rail + accordion panels)

### 3.1 EOS capture

A fixed right rail with a **collapse chevron** (e3/`›`) at the top, the **CROP monitoring** logo,
a **Season selector**, primary module accordions, and a bottom utility cluster.

Primary groups (top):

| Item | DOM | Type | Submenu / route |
|---|---|---|---|
| **Season 2** | `button "Season 2"` (e460) | dropdown | Season panel: explanation, Create season, Active/Planned/Ended groups, date ranges, total area, Edit/Delete. |
| **Monitoring** | `mat-expansion-panel-header` (e468) | accordion | Global view, Field analytics, Field leaderboard, Reporting, Diseases & Pests. |
| **Weather** | accordion (e484) | accordion | Analytics, Forecast. |
| **Field activity log** | `link → /work-log` (e500) | route | Activity calendar/log. |
| **VRA maps** | accordion (e508) | accordion | Sowing, Vegetation, P&K, Map builder, Soil sampling. |
| **Scout tasks** | `link → /main-task/tasks/new` (e524) | route | Map-pin scouting tasks. |
| **Data manager** | accordion (e532) | accordion | Data, Connections. |
| **Field manager** | accordion (e548) | accordion | Field groups. |

Bottom utility cluster:

| Item | DOM | Submenu |
|---|---|---|
| **AI assistant** | `button` (e569) | Beta assistant panel + text input (evidence-bound). |
| **Notifications** | `button` (e578) | Notifications panel (empty-state when none). |
| **Help Center** | accordion (e587) | What's New, User guide, Case studies, Crop management guide, Contact us. |
| **Marketplace** | accordion (e603) | Add-ons, Solutions, Partnership module, White Label. |
| **Account / team** | `button` (e618) — "Nishanth Murugan / Team Nishanth Murugan" | Profile email, team name, owner role, Switch team, Team Management, API, Settings, Upgrade plan, Log out. |
| **Try Full-Featured Access** | `button` (e634) | Trial upsell. |
| **Upgrade Plan** | `link → /pricing` (e640) | Plan upsell. |

Interaction model: rail can **collapse to icons**; module entries are **accordions that expand
in place** (not slide-out overlays); leaf items are route links.

### 3.2 Akasha mapping + gap

Akasha already has the **exact same group/leaf taxonomy** in
[productNavigation.ts](apps/frontend/src/routes/productNavigation.ts) (Monitoring / Weather /
Operations / VRA maps / Utility) rendered by [AppShell.tsx](apps/frontend/src/components/shell/AppShell.tsx)
as an always-expanded 19rem `<aside>`.

| EOS behavior | Akasha today | Action |
|---|---|---|
| Collapsible icon rail + in-place accordions | Always-expanded `<aside>`, flat route links | **Refactor `AppShell` aside into a collapsible rail**: icon-only collapsed state + expand chevron (matches EOS e3), accordion groups that expand in place. Preserve `productNavigation` data. |
| Season selector at top of rail | None | Add a **Season** trigger at the top of the rail (placeholder panel: Active/Planned/Ended + Create season) — backend deferred; shell + panel only for layout parity. |
| Bottom utility cluster (AI/Notifications/Help/Marketplace/Account) | `Utility` group exists in nav data | Move utility items to a **bottom-pinned cluster** in the rail to match EOS placement; keep as branded route links/placeholders. |
| Account/team menu | Account/API routes are `planned` | Add an **account/team popover** in the rail footer (profile, team, settings, API, logout placeholders). |

EOS routes → Akasha routes (already defined): `/work-log` → `/activity-log`;
`/main-task/tasks/new` → `/scout-tasks`; Monitoring/Weather/VRA submenus map 1:1 to existing
`productNavigation` paths.

---

## 4. MAP CANVAS + FIELD BOUNDARY

### 4.1 EOS capture
- Full-bleed map; **true-colour basemap** with the **index raster (NDVI here) clipped to the field
  polygon**, the rest of the map showing plain satellite basemap.
- Field boundary drawn with a **thick white outline**.
- Coordinate readout (top-left, `13.1931° N · 77.4952° E`) and **scale bar** (`200 m`, top-right).

### 4.2 Akasha mapping
- [MapLayerManager.tsx](apps/frontend/src/components/map/MapLayerManager.tsx) +
  [satelliteLayer.ts](apps/frontend/src/lib/satelliteLayer.ts) own the MapLibre instance and raster
  source/layer swaps. **Reuse as-is.**
- [FieldBoundaryLayer.tsx](apps/frontend/src/components/fields/FieldBoundaryLayer.tsx) renders the
  selected polygon. **Reuse**; tune outline to a thick white stroke for parity.
- [CoordinateReadout.tsx](apps/frontend/src/components/map/CoordinateReadout.tsx) + MapLibre scale
  control already cover coord + scale. **Reuse.**
- **Gap:** EOS clips the index raster to the field polygon. Akasha field-scene tiles are
  served per-field by the BFF; verify the index overlay is masked to the AOI (BFF concern), keep
  **RGB true-colour as default** (REQ-007). Action: confirm field-scoped index tiles render clipped;
  no frontend change if BFF already returns AOI-clipped tiles.

---

## 5. MAP CONTROLS (left cluster)

### 5.1 EOS capture

| Control | DOM | Behavior |
|---|---|---|
| **Split view** | `button` (e74) | A/B split-screen scene compare. |
| **Zoom in / out** | `button` (e79 / e83) | `＋` / `－`. |
| **Ruler / measure** | `button` (e89) | Distance/area measurement. |
| **Locate / find field** | `button` (e94) | Recenter/geolocate to the field. |

### 5.2 Akasha mapping + gap

| EOS | Akasha today | Action |
|---|---|---|
| Split view | [CompareControl.tsx](apps/frontend/src/components/map/CompareControl.tsx) (A-over-B opacity blend) | Keep; optionally add a true **side-by-side split** mode later. Placement: move to left cluster for parity. |
| Zoom ± | [MapControls.tsx](apps/frontend/src/components/map/MapControls.tsx) | Reuse. |
| Ruler | [MeasureTool.tsx](apps/frontend/src/components/map/MeasureTool.tsx) | Reuse. |
| Locate/find field | `MapControls` (geolocate/locate field) | Reuse; ensure "locate field" fits bounds to the selected plot. |

Action: **regroup these into a single left-edge vertical cluster** to match EOS placement (currently
some live in `MapControls` on the right). No new logic, only layout/placement.

---

## 6. LAYER CONTROL BAR (bottom-right, above timeline)

### 6.1 EOS capture

A horizontal bar: `[ Sentinel-2 ▾ ] [ NDVI ▾ ] [ ⚠ anomaly(locked) ] [ ▣ static/legend ] [ ☁ cloud
mask ] [ ⬇ download ] [ ⌃ collapse ]`.

**Two layer-bar variants observed.** The **field-analytics** screen (now confirmed live on this
account 2026-06-04 after drawing **Field 11**, 152.4 ha, `/analytics/field/10976428`) shows the
full bar with cloud mask + download. The **Global view** screen shows a reduced bar with two
display-mode toggles instead. Both are captured below.

| Control | DOM | Menu contents |
|---|---|---|
| **Source selector** | `data-id=menu-trigger`, `source-name` (e62) | **Confirmed live 2026-06-04** (radio groups): **Satellites** (selected) → Sentinel-2 `S2` 10 m (only entry, checkbox checked+disabled on this plan); **My crops**; **Risk map**. Prior field-account capture also showed PlanetScope `PS` 3 m (add-on), Elevation map, Slope map. |
| **Index/layer selector** | menu-trigger (field screen e111) | **Confirmed live 2026-06-04**: **Natural Color**; **Vegetation Indices:** NDVI, NDRE, MSAVI, RECI; **Moisture Indices:** NDMI; **+ Add new index** (Add-on). No "Vegetation Meta index" entry on this plan. |
| **Display-mode toggles (Global view)** | buttons e81 / e92 | **Confirmed live 2026-06-04**: **Anomaly detection** toggle (tooltip: “Anomalies can be caused by unidentified clouds… Go to Split View”) and **Mean index** toggle. These replace the cloud-mask/download cluster in Global view. |
| **Anomaly layer** | `button` (field screen e119, disabled) | Anomaly-detection overlay toggle (interactive in Global view; plan-gated/disabled on field screen). |
| **Dynamic / static legend** | `button` (field screen e121) | **Confirmed live 2026-06-04 on Field 11.** Toggles the index raster between a **continuous/dynamic gradient** (default, smooth blend) and a **discrete static classified palette** (sharp red/yellow/green class zones). GA event `dynamic_legend_click` with `eventPosition=contrast-view` (active) / `standard-view` (default). |
| **Cloud mask** | `button` (field screen e127, `cursor=pointer`) | **Confirmed live 2026-06-04.** Three independent checkboxes, all checked by default: **Cirrus clouds**, **Clouds**, **Cloud shadows**; each row has a secondary square swatch control. |
| **Download / export** | `button` (field screen e134, `data-id=download-btn`) | **Confirmed live 2026-06-04.** File options keyed to the selected index/date: `NDVI.tiff`, `NDVI.shp`, `Contours.shp`. |
| **Collapse bar** | `button` (field screen e142) | Collapse/expand the layer bar. |

### 6.2 Akasha mapping + gap

| EOS | Akasha today | Action |
|---|---|---|
| Source selector (grouped) | [SourceList.tsx](apps/frontend/src/components/layers/SourceList.tsx) inside [LayersSurface.tsx](apps/frontend/src/components/layers/LayersSurface.tsx) | **Build a compact `SourceSelector` dropdown** in the layer bar driven by `/api/sources`; group as Satellites / Elevation / Slope (elevation+slope are `planned` placeholders). |
| Index selector (grouped) | Display mode currently chosen in source/layer state; no grouped menu | **Build `IndexSelector` dropdown**: Natural Color (RGB, default) + Vegetation (NDVI, NDRE, MSAVI*, RECI*) + Moisture (NDMI). `*` MSAVI/RECI need BFF [indices.py](apps/api/app/raster/indices.py) extension (REQ-012). Never default to an index (REQ-007). |
| Anomaly (locked) | None | Add a **disabled "anomaly" placeholder** button for layout parity. |
| Dynamic/static legend | [Legend.tsx](apps/frontend/src/components/map/Legend.tsx) + `legendOpen` | Add a **dynamic↔static toggle**: continuous gradient vs discrete classified palette. Drives both the raster render style and the legend ramp. |
| Cloud mask toggles | [CloudMaskControl.tsx](apps/frontend/src/components/monitoring/CloudMaskControl.tsx) + `cloudMask {clouds, cloudShadows, cirrus}` | **Already matches** EOS's three toggles — reuse; surface it in the layer bar. |
| Download | [DownloadMenu.tsx](apps/frontend/src/components/monitoring/DownloadMenu.tsx) | Reuse; expose `.tiff` / `.shp` / contours options (server-side export, SEC-003). |
| Collapse | None | Add a collapse chevron for the bar. |

---

## 7. LEGEND

- **EOS:** colour ramp legend toggle (`button` e151), bottom-left, reflecting the active index.
- **Akasha:** [Legend.tsx](apps/frontend/src/components/map/Legend.tsx) + `legendOpen` state already
  exist. **Reuse**; ensure ramps for NDVI/NDRE/NDMI/MSAVI/RECI and hide for RGB.

---

## 8. BOTTOM TIMELINE

### 8.1 EOS capture

`[ 📅 calendar ] | [ ◀ ] [ 07 Apr'26 · S2 ] [ 09 Apr'26 · S2 ] … [ 12 May'26 (selected) ] [ ☁ 01
Jun'26 · S2 ] [ ▶ ] | [ → Next image · Jun 6, 2026 ] | [ ⛶ fullscreen ]`

| Element | DOM | Behavior |
|---|---|---|
| **Calendar** | `button "Open calendar"` (field screen, inside e154) | Date-range picker driving `period_from`/`period_to` (live URL: `period_from=2026-03-05&period_to=2026-06-04`). |
| **Scene chips** | `generic [cursor=pointer]` per date (field screen e170…e303) | **Confirmed live 2026-06-04** on Field 11: ~17 Sentinel-2 scenes `08 Mar'26 … 12 May'26`, each with a `S2` sensor badge; selected chip highlighted (`12 May'26`); **cloud icon** marks cloudy scenes. Clicking sets `?sceneID`. |
| **Prev/next chip nav** | `button` (field screen e163 / e310-disabled) | Step through scenes. |
| **Next image** | `button "Next image Jun 6, 2026"` (field screen e312) | Prompt for the next expected acquisition. |
| **Fullscreen** | `button` (field screen, right of timeline) | Fullscreen map. |

### 8.2 Akasha mapping + gap

| EOS | Akasha today | Action |
|---|---|---|
| Scene filmstrip + chips + sensor badge | [TimelineBar.tsx](apps/frontend/src/components/timeline/TimelineBar.tsx) + [DateChip.tsx](apps/frontend/src/components/timeline/DateChip.tsx) | **Already strong.** Add sensor badge (`S2`) + cloud icon per chip from scene `cloudMaskedPercent`. |
| Calendar range picker | None (filmstrip only) | **Add a calendar/date-range control** driving `period_from`/`period_to` (new URL params). |
| Prev/next + playback | `TimelineBar` arrows + [PlaybackControls.tsx](apps/frontend/src/components/timeline/PlaybackControls.tsx) | Reuse. |
| "Next image" prompt | None | **Add a next-expected-acquisition prompt** (derive from revisit cadence / scene metadata). |
| Fullscreen | `MapControls` fullscreen | Reuse. |

---

## 9. ANALYTICS PANEL (below the map)

### 9.1 EOS capture

Panel docks below the map (map shrinks to top). Tab bar: **Crop info** (e616, active) · **Chart**
(e620) · **Activities** (e624). **All three tabs confirmed live 2026-06-04 on Field 11.**

**Crop info tab** — three columns of cards:

| Card | DOM | Contents |
|---|---|---|
| **Crop rotation** | e633 | `Season: sdasdasd`, `+ Add crop`, `Show all`. |
| **Sown area detected, %** | e650 | Plan-gated: "Detection of sown area is available in the Essential or Professional plans". |
| **Crop management guide** | e667 | "Explore EOSDA Crop Monitoring applications for different crops here" + `Go to guide` external link. |
| **Growth Stages** | e676 | "Select a crop to view its growth stages"; `Edit`. |
| **Current risks** | e693 | Plan-gated (Essential/Professional). |
| **NDVI values split** | e711 | Plan-gated (Essential/Professional). |

**Chart tab** (e733) — confirmed live: NDVI time-series **line chart** (y-axis 0–1, x-axis
`Mar 5 → Jun 3`), with a multi-year overlay legend: **NDVI (2026)** active (green) + **NDVI 2025 /
2024 / 2023 / 2022** each plan-locked (lock icon). Left rail: **Weather Data** overlay selector
("Select data" combobox), **Start date** / **End date** pickers (`Mar 5, 2026` → `Jun 4, 2026`,
disabled here), and a **Data Source** note: "Sentinel-2 and PlanetScope data can be used in the
chart". Below the chart: a range scrubber + "Press here to select a crop and view growth stages";
export/download button (plan-locked).

**Activities tab** (e867) — confirmed live: header "Activities" + `+ Add`; empty state
"No activities added to the field" with an **Add activity** button.

### 9.2 Akasha mapping + gap

| EOS | Akasha today | Action |
|---|---|---|
| Tabbed analytics panel (docks below map) | [IndexPanel.tsx](apps/frontend/src/components/scaffold/IndexPanel.tsx) is a scaffold (stats + trend) | **Expand `IndexPanel` into a tabbed panel:** Crop info / Chart / Activities; dock below map and shrink map when open. |
| Chart: multi-year NDVI series + weather overlay + date range | `FieldTrendChart` via `useFieldTrend` (`/api/fields/:id/analytics/trend`) | Wire into the **Chart** tab. Add **multi-year series toggles** (current year active, prior years gated), a **Weather Data** overlay selector, and **Start/End date** inputs bound to the period. |
| Crop rotation / Add crop / Season | None | **Crop info** tab cards (placeholders + season context) — schema/back-end deferred; layout parity now. |
| Sown area / Current risks / NDVI split | None | Render **plan-gated placeholder cards** (Akasha-branded, no diagnosis) for layout parity. |
| Growth stages | None | Placeholder card ("select a crop"); generic stage model deferred. |
| Activities tab (empty-state + Add activity) | None | Add an **Activities** tab with an empty state + Add-activity affordance; activity model deferred. |

---

## 10. UTILITY / ACCOUNT MENUS (rail footer)

| EOS menu | Contents | Akasha action |
|---|---|---|
| **Account / team** | Email, team, owner role, Switch team, Team Management, API, Settings, Upgrade, Log out | Rail-footer **account popover** (placeholders; auth deferred to Phase 12). |
| **Help Center** | What's New, User guide, Case studies, Crop management guide, Contact us | Branded Help popover (external/placeholder links). |
| **Marketplace** | Add-ons, Solutions, Partnership, White Label | Branded Marketplace popover (placeholders). |
| **Notifications** | Panel; empty-state | Reuse planned notifications route/panel. |
| **AI assistant** | Beta panel + input (evidence-bound) | Disabled/evidence-only shell (no agronomic invention). |

---

## 11. URL deep-link state model (new)

EOS encodes view state in the URL so views are shareable/deep-linkable:

```
/analytics/field/{fieldId}?sceneID={sceneId}&period_from={YYYY-MM-DD}&period_to={YYYY-MM-DD}
```

### Akasha target

- **Route:** nest the field id in the analytics path, e.g.
  `/monitoring/field-analytics/field/:plotId` (react-router param), keeping
  `MAIN_MONITORING_ROUTE` as the index when no field is selected.
- **Search params:** `?scene={acquisitionDate}` (Akasha equivalent of `sceneID`),
  `?from=`/`?to=` (period), `?source=`, `?layer=` (displayMode). Keep Akasha-native names; do not
  leak provider scene ids.
- **Bridge:** add a `useMapUrlState` hook bridging `useSearchParams`/route params ↔
  [mapViewContext.tsx](apps/frontend/src/state/mapViewContext.tsx):
  - On mount: **hydrate** reducer from URL (field, scene/date, period, source, layer).
  - On change: **`navigate(..., { replace: true })`** (no history spam).
  - Keep the existing `localStorage` `akasha.selectedPlotId` fallback when no URL field is present.
- **Reducer additions:** `periodFrom`/`periodTo` (currently absent) to back the calendar range.

Guardrail: scene/date param is an **Akasha acquisition date or Akasha scene id**, never an EOS
`S2B_tile_...` id.

---

## 12. Component mapping summary (EOS → Akasha)

| EOS region | Akasha component(s) | Status | Work |
|---|---|---|---|
| Top bar field context | **`FieldContextHeader`** (new) | missing | build |
| All fields | `AllFieldsPanel` | exists | wire to header trigger |
| Right nav rail | `AppShell` aside → **collapsible rail** | exists (flat) | refactor to icon rail + accordions |
| Season selector | **`SeasonSelector`** (new, placeholder) | missing | build shell |
| Map + boundary | `MapLayerManager`, `satelliteLayer`, `FieldBoundaryLayer` | exists | reuse |
| Coord + scale | `CoordinateReadout` + MapLibre scale | exists | reuse |
| Map controls (split/zoom/ruler/locate) | `CompareControl`, `MapControls`, `MeasureTool` | exists | regroup to left cluster |
| Source selector | **`SourceSelector`** (new) | missing | build (driven by `/api/sources`) |
| Index selector | **`IndexSelector`** (new) | missing | build (grouped; RGB default) |
| Anomaly (locked) | placeholder | missing | disabled placeholder |
| Static/legend mode | `Legend` + toggle | partial | add static toggle |
| Cloud mask | `CloudMaskControl` | exists (3 toggles) | reuse, surface in bar |
| Download | `DownloadMenu` | exists | reuse (`.tiff`/`.shp`/contours) |
| Legend | `Legend` | exists | reuse + ramps |
| Timeline filmstrip | `TimelineBar`, `DateChip`, `PlaybackControls` | exists | add sensor/cloud badge |
| Calendar range | **calendar control** (new) | missing | build → `from`/`to` params |
| Next image prompt | placeholder | missing | build |
| Analytics tabs | `IndexPanel` → tabbed | scaffold | expand (Crop info/Chart/Activities) |
| Utility/account menus | nav `Utility` group | partial | rail-footer popovers |
| URL deep-link | `mapViewContext` + **`useMapUrlState`** (new) | missing | build bridge |

---

## 13. Implementation phases

> Frontend-only layout/interaction parity. Each phase ends with `yarn lint && yarn build &&
> yarn test` green in [apps/frontend](apps/frontend). No EOS visual assets; Akasha branding only.

- **Phase A — URL deep-link bridge (foundation).** Add `/field/:plotId` route param + `useMapUrlState`
  hook; add `periodFrom`/`periodTo` to `mapViewContext`; hydrate-on-mount + replace-on-change; keep
  localStorage fallback. Tests for hydration/serialization round-trip.
- **Phase B — Field-context top bar.** New `FieldContextHeader` (back, name+glyph, server area, edit,
  Get-Overview placeholder, All-fields trigger → `AllFieldsPanel`).
- **Phase C — Right nav rail.** Refactor `AppShell` aside into collapsible icon rail + in-place
  accordions (preserve `productNavigation`); add Season trigger (top) and utility/account cluster
  (footer). *(parallelizable with B)*
- **Phase D — Layer control bar.** `SourceSelector` + grouped `IndexSelector` + anomaly placeholder +
  static toggle + collapse; surface `CloudMaskControl` and `DownloadMenu` in the bar; regroup
  left-edge map controls. RGB stays default.
- **Phase E — Bottom timeline parity.** Sensor + cloud badges on chips; calendar range control →
  `from`/`to`; next-image prompt.
- **Phase F — Analytics panel tabs.** Expand `IndexPanel` into Crop info / Chart / Activities; wire
  `FieldTrendChart` into Chart; placeholder cards for Crop info.
- **Phase G — Tests + side-by-side validation.** Vitest for URL sync, header, nav rail, selectors,
  timeline; manual side-by-side vs the live EOS screen.

Dependency: **A first** (everything else reads/writes URL state). C and B can run in parallel after A.

---

## 14. Open validation items

### 14.1 Confirmed live via interactive clicks (2026-06-04)

The integrated browser became fully interactive this session. The following were verified by
expanding the real menus on the logged-in account (`Team Nishanth Murugan`, free trial, Global view):

- ✅ **Right-nav submenus** (exact items + routes): Monitoring (Global view, Field analytics,
  Field leaderboard `/field-leaderboard`, Reporting `/custom-report`, Diseases & Pests `/diseaserisk`);
  Weather (Analytics `/weather-history/field/all`, Forecast `/weather-forecast/field/all`);
  VRA maps (Sowing, Vegetation, P&K, Map builder, Soil sampling under `/zoning/*`);
  Data manager (Data `/data-manager`, Connections `/machinery-connections`);
  Field manager (Field groups `/field-group-management`).
- ✅ **Utility menus**: Help Center (What's New, User guide, Case studies, Crop management guide,
  Contact us); Marketplace (Add-ons `/addons`, Solutions `/solutions`, Partnership module, White Label).
- ✅ **Account/team popover**: profile name + email, team name + Owner role + Switch team,
  Team Management, API, Settings, Upgrade plan, Log out.
- ✅ **Source selector**: radio groups Satellites / My crops / Risk map; Satellites → Sentinel-2 only.
- ✅ **Index selector**: Natural Color; Vegetation Indices NDVI, NDRE, MSAVI, RECI; Moisture Indices
  NDMI; + Add new index (Add-on). (No "Vegetation Meta index" on this plan.)
- ✅ **Global-view layer toggles**: Anomaly detection + Mean index.

### 14.1b Field-analytics screen confirmed live (2026-06-04, Field 11)

After drawing **Field 11** (152.4 ha, `/analytics/field/10976428`) the field-analytics screen
became reachable and the previously-blocked controls were verified by live clicks:

- ✅ **Dynamic/static legend** (e121): continuous gradient ↔ discrete classified palette (verified
  by screenshot — field shows sharp red/yellow/green class zones in static mode).
- ✅ **Cloud mask** (e127): three independent checkboxes — **Cirrus clouds**, **Clouds**,
  **Cloud shadows** (all checked by default), each with a secondary swatch control. Matches
  Akasha's `cloudMask {clouds, cloudShadows, cirrus}` exactly.
- ✅ **Download** (e134, `download-btn`): `NDVI.tiff`, `NDVI.shp`, `Contours.shp`.
- ✅ **Timeline filmstrip**: ~17 Sentinel-2 scenes `08 Mar'26 … 12 May'26` with `S2` badges,
  selected `12 May'26`, cloud icons on cloudy scenes, "Next image Jun 6, 2026".
- ✅ **Analytics panel tabs**: **Crop info** (Crop rotation / Sown area% / Crop management guide /
  Growth Stages / Current risks / NDVI values split — several plan-gated), **Chart** (multi-year
  NDVI line chart + Weather Data overlay + Start/End date + multi-year series toggles), and
  **Activities** (empty state + Add activity). See [§9](#9-analytics-panel-below-the-map).

### 14.2 Still blocked — requires a configured crop/season or paid plan

With Field 11 drawn but no crop/season configured (and on the free trial), these remain unverified:

1. **Calendar** range picker internal layout and how it prunes the filmstrip (button is intercepted
   by an overlay label; URL params `period_from`/`period_to` confirmed).
2. **Season** dropdown panel structure (Active/Planned/Ended, create/edit/delete) — current season
   placeholder shows `sdasdasd`.
3. **Split view** (e69/e584): confirm true side-by-side vs opacity blend (Akasha currently blends).
4. **Chart with a crop configured**: growth-stage bands and populated multi-year series.
5. **Plan-gated cards** (Sown area %, Current risks, NDVI values split) actual populated contents
   require Essential/Professional plan.

---

## 15. Guardrails (non-negotiable)

- Browser calls only same-origin `/api/*` and tile/download routes; **never EOS directly**.
- **True-colour is the default** map layer; NDVI/any index is never the default (REQ-007).
- **Akasha branding/styling only** — replicate structure/placement/behavior, not EOS visual assets
  (GUD-002).
- Field **area/geometry validated server-side** (REQ-008).
- No EOS keys, scene ids, MinIO/STAC/TiTiler internals, or COG paths exposed to the browser.
- Provider remains swappable behind the BFF adapter layer.
