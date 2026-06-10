# Map Screen Redesign — Complete Implementation Plan

> **Status: planning only — not yet implemented.** This is the single source-of-truth spec for the
> Map Screen redesign. When implementation begins, execute it **phase by phase from this document**
> (§9) and keep this file updated as phases land. It is canonical per the `docs/` rule in
> [CLAUDE.md](../CLAUDE.md).

---

## 1. Context — why we're doing this

The current Map Screen ([apps/frontend/src/pages/MapPage.tsx](../apps/frontend/src/pages/MapPage.tsx))
works but its layer + date model was built for a single satellite source and a short list of dates.
The product is moving toward **multiple imagery sources** (Sentinel-2 optical, Sentinel-1 SAR today;
Landsat / other rasters later) and **time-series exploration**, so two things need a rethink:

1. **Layer management** — today a left `LayerPanel` mixes "which source", "which date", and
   "opacity/visibility" into one always-open 320px panel. It doesn't scale to N sources, per-source
   metadata, display modes (RGB/NDVI/false-colour), or comparison.
2. **Temporal navigation** — today dates are a **vertical scrollable list** inside that panel
   ([DateList.tsx](../apps/frontend/src/components/layers/DateList.tsx)). For time-series imagery a
   **horizontal bottom timeline** is the established, map-first pattern.

Goal: a **map-first, modern, scalable** screen — a collapsed **Layers** control that expands into a
real layer manager, and a **bottom filmstrip timeline** for dates — built entirely on the **existing
design system** (Tailwind + Radix/shadcn glass panels, saffron primary, dark-default) and the
**existing BFF contracts**, with clear extension points for compare/playback/more sources.

### What already exists (reuse, don't reinvent)
- **Map engine**: [MapLayerManager.tsx](../apps/frontend/src/components/map/MapLayerManager.tsx) owns the
  MapLibre lifecycle with a ref-isolated map (never re-renders). Satellite layer swap logic is pure
  helpers in [satelliteLayer.ts](../apps/frontend/src/lib/satelliteLayer.ts) (`applySatelliteLayer`,
  `setSatelliteOpacity`, `setSatelliteVisibility`, `SAT_SOURCE_ID`/`SAT_LAYER_ID`). **Basemap is never
  restyled** on date/source change — only the one raster overlay swaps. This invariant must survive.
- **Data**: [api.ts](../apps/frontend/src/lib/api.ts) + [queries.ts](../apps/frontend/src/lib/queries.ts) →
  `/api/config`, `/api/sources`, `/api/sources/{id}/dates`, `/api/layers/default`, and
  `composeTileTemplate()` for relative `/api/tiles/...` URLs. Types in
  [types/api.ts](../apps/frontend/src/types/api.ts) (`Source`, `SceneDate`, `AppConfig`, `DefaultLayer`).
- **Design system**: tokens and Tailwind v4 `@theme` variables in
  [globals.css](../apps/frontend/src/styles/globals.css); `.glass` / `.contour` / `.on-map-text`
  recipes; shadcn primitives in [components/ui/](../apps/frontend/src/components/ui/) (button, card,
  tooltip, slider, switch, separator, scroll-area, badge, skeleton); lucide icons; documented in
  [docs/design-system.md](design-system.md).
- **Existing controls to keep/restyle**: [MapControls.tsx](../apps/frontend/src/components/map/MapControls.tsx)
  (zoom/compass/geolocate), [ThemeToggle.tsx](../apps/frontend/src/components/ThemeToggle.tsx),
  [CloudUsabilityChip.tsx](../apps/frontend/src/components/layers/CloudUsabilityChip.tsx),
  [selectDefaultDate.ts](../apps/frontend/src/lib/selectDefaultDate.ts),
  [usability.ts](../apps/frontend/src/lib/usability.ts).

### Decisions locked with the user
| Topic | Decision |
|---|---|
| Deliverable | One complete planning doc; **implement later, phase by phase**, from this doc |
| Layer model | **Single active layer + Compare-ready structure** (panel built for future stacking; compare itself is backlog) |
| Timeline | **Bottom filmstrip + scrubber** (date chips with usability badges, jump-to-latest, optional play later) |
| In-scope features | **Display modes (NDVI/false-colour)** + **Map utilities** (legend, coordinate/scale readout, measurement, fullscreen, basemap switcher) |
| Backlogged features | **Compare mode** (swipe/opacity), **Timeline playback animation** |

> Note: a concept image was referenced during planning but did not reach the assistant; this plan is
> research-driven. Reconcile against that image before/at Phase 1 kickoff if it represents hard constraints.

---

## 2. UX research findings (modern GIS / EO platforms)

Synthesized from EO Browser, NASA Worldview, ArcGIS, Google Earth/Timelapse, Earth Engine, Planet,
and Material/NN-g mobile guidance. Sources listed at the end of this section.

**Layer management**
- Leading EO tools keep a **collapsible left rail / drawer** of sources (EO Browser checkboxes on the
  left; ArcGIS layer lists). The trend (EO Browser "Smart Panel") is **fewer clicks to first
  visualization** — show latest imagery for the location in ~2 clicks. → Our "collapsed Layers button
  → expand" matches this.
- Each layer row exposes **visibility, opacity, and metadata**; ordering matters only when multiple
  layers are simultaneously visible (we defer true stacking, so ordering UI is deferred too).
- **Display/render mode** (true-colour vs false-colour vs index) is a per-source switch, kept distinct
  from "which layer".

**Temporal navigation**
- **Bottom horizontal timeline** is the dominant map-first pattern. Google Earth Timelapse = bottom
  slider with year highlight + play/pause + speed. Earth Engine offers **filmstrip-of-thumbnails** for
  quick spatiotemporal assessment.
- EO Browser pairs a **calendar** (jump to any date, filter by month) with inline next/prev on the
  visualization. Best practice: **filmstrip for browsing recent dates + calendar affordance for jumping
  far**. → We adopt filmstrip-first with a calendar popover as a secondary jump.
- Disabled/empty dates must be visually distinct (we already compute `tileAvailable`).

**Comparison (backlog, but design for it now)**
- Two canonical patterns: **swipe** (draggable divider reveals before/after at the same position) and
  **opacity blend**. NASA Worldview ships **both** ("Swipe mode" + "Opacity mode"). ArcGIS Swipe and
  Esri World Imagery Wayback are the reference implementations. Split-screen (two synced maps) is the
  heavier alternative.

**Mobile vs desktop**
- **Desktop** → side panel/drawer (full map, organized collapsible sections).
- **Mobile** → **bottom sheet** (Material: persistent, drag to expand/collapse, co-exists with map).
  Material guidance explicitly says a bottom sheet on mobile can become a **side sheet on larger
  screens** — so we build one logical "Layers surface" that renders as a left drawer ≥md and a bottom
  sheet on small screens.

**Accessibility & performance**
- WCAG 2.1.1 (keyboard operable), 2.1.2 (no keyboard trap), visible focus (never `outline:none`),
  and a **"skip the map" bypass link** (2.4.1). Keep tabbable points on the map low (~≤20).
- Large rasters: keep one active overlay, use `bounds`/`minzoom`/`maxzoom` (already done) to avoid
  out-of-footprint tile requests, crossfade on swap (already done), and lazy-load heavy UI
  (calendar/command palette).

Sources:
[EO Browser UX redesign](https://forum.sentinel-hub.com/t/eo-browser-collecting-feedback-for-ux-ui-redesign/4874) ·
[EO Browser](https://www.sentinel-hub.com/explore/eobrowser/) ·
[Copernicus Browser docs](https://documentation.dataspace.copernicus.eu/Applications/Browser.html) ·
[NASA Worldview](https://www.earthdata.nasa.gov/data/tools/worldview) ·
[Worldview comparison feature](https://www.earthdata.nasa.gov/news/blog/introducing-worldviews-comparison-feature) ·
[Esri swipe/compare apps](https://www.esri.com/arcgis-blog/products/arcgis-online/mapping/swipe-compare-apps) ·
[Swipe map pattern](https://mapuipatterns.com/swipe/) ·
[Split-screen map](https://mapular.com/glossary/split-screen-map) ·
[Google Earth Timelapse](https://earthengine.google.com/timelapse/) ·
[Earth Engine filmstrip/visualization](https://developers.google.com/earth-engine/guides/ic_visualization) ·
[Material bottom sheets](https://m2.material.io/components/sheets-bottom) ·
[NN/g bottom sheets](https://www.nngroup.com/articles/bottom-sheet/) ·
[Mobile map navigation patterns](https://www.maplibrary.org/10503/7-alternative-navigation-patterns-for-mobile-maps/) ·
[Web map accessibility (MN IT)](https://mn.gov/mnit/assets/Accessibility%20Guide%20for%20Interactive%20Web%20Maps_tcm38-403564.pdf) ·
[Map accessibility (Sparkgeo)](https://sparkgeo.com/blog/the-accessibility-of-web-maps/).

---

## 3. Recommended layout & wireframes

**Principle: map-first.** Chrome floats over the map as glass panels anchored to edges; the center
stays clear. One primary control rail (left), one temporal strip (bottom), utilities in corners.

### 3.1 Desktop (≥ md) — collapsed default

```
┌──────────────────────────────────────────────────────────────────────┐
│ [≡ Layers]                    · Akasha · Bangalore ·         [search] [☼]│  top: brand center, theme + search right
│                                                                          │
│                                                                          │
│                              M A P   C A N V A S                         │
│                                                                          │
│                                                            ┌───────────┐ │
│                                                            │  Legend   │ │  legend (when index/SAR active)
│                                                            └───────────┘ │
│                                                                   [＋]    │  bottom-right: zoom
│  12.97°N 77.59°E   |——— 1 km ———|                                 [－]    │  coord + scale readout (bottom-left)
│                                                                   [⊕][⤢]  │  compass / geolocate / fullscreen
├──────────────────────────────────────────────────────────────────────┤
│ ◀  Oct '25 ··· 11-02  11-15  12-01 [12-14] 01-15 ··· latest ▶   📅  ▷   │  bottom timeline filmstrip + scrubber
│        🟢      🟢     🟡     🟢    ●sel    🟢                              │  usability badges under each chip
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Desktop — Layers expanded (left drawer)

```
┌─ Layers ───────────────┐
│ ⌕ search sources       │   (search shown when list grows)
│ ───────────────────────│
│ IMAGERY                │   section label
│ ┌────────────────────┐ │
│ │● Sentinel-2 L2A  ◐ │ │   active source card: radio dot + kebab
│ │  optical · 10 m    │ │   metadata line (source · resolution)
│ │  2026-01-15        │ │   selected date echo
│ │  Mode: [RGB|NDVI|◳]│ │   display-mode segmented control (ToggleGroup)
│ │  Opacity ▓▓▓▓░ 80% │ │   slider (reuses OpacitySlider)
│ │  👁 visible         │ │   visibility switch (reuses VisibilityToggle)
│ └────────────────────┘ │
│ ┌────────────────────┐ │
│ │○ Sentinel-1 GRD    │ │   inactive source: click to activate
│ │  radar · VV        │ │
│ └────────────────────┘ │
│ ┌────────────────────┐ │
│ │○ Landsat (soon)    │ │   future sources render disabled/"soon"
│ └────────────────────┘ │
│ ───────────────────────│
│ BASEMAP   [Streets ▾]  │   basemap switcher (popover/select)
│ [ Compare ▸ (soon) ]   │   compare entry point (disabled until backlog phase)
└────────────────────────┘
```

### 3.3 Mobile (< md) — bottom sheet

```
┌─────────────────────────┐
│        MAP CANVAS        │
│                          │
│                   [＋][－]│
│                   [⊕][⤢] │
│  ◀ 12-01 [12-14] 01-15 ▶│  collapsed timeline (peek) above sheet
├─────────────────────────┤
│ ▁▁▁ (drag handle)        │  bottom sheet, peek → half → full
│ Layers · Sentinel-2 RGB  │  peek row: active layer summary
│ Opacity ▓▓▓▓░ 80%   👁   │  quick controls in peek
└─────────────────────────┘
   (expand sheet → full source list + modes + basemap)
```

**Why this layout**
- **Collapsed-by-default Layers** keeps the map clear and matches EO Browser's low-friction direction.
- **Bottom filmstrip** is the map-first temporal standard; it frees the left rail to be a true layer
  manager rather than a date list.
- **One responsive "Layers surface"** (Radix Dialog/Sheet driven by a `useMediaQuery`) = left drawer on
  desktop, bottom sheet on mobile — single component tree, two presentations (Material guidance).

---

## 4. Component hierarchy

New/renamed components live under `apps/frontend/src/components/`. Existing leaf controls
(`OpacitySlider`, `VisibilityToggle`, `CloudUsabilityChip`) are **reused** inside the new shells.

```
MapPage
├─ MapViewProvider                      NEW  client UI state (reducer/context) — see §6
├─ MapLayerManager                      KEEP map lifecycle; extend to read active layer from context
│   └─ (MapLibre canvas + ScaleControl)
├─ TopBar                               NEW  brand + theme + search/command trigger
│   ├─ LayersToggleButton  [≡ Layers]   NEW  collapsed entry (FAB-style glass pill)
│   ├─ BrandMark                         KEEP/move from MapPage
│   ├─ CommandPalette (lazy)            NEW  ⌘K search (sources/dates/places)  [Phase 4]
│   └─ ThemeToggle                       KEEP
├─ LayersSurface                        NEW  responsive shell (Drawer ≥md / Sheet <md)
│   ├─ SourceSearch                     NEW  filter (shown when >N sources)     [Phase 1, optional]
│   ├─ SourceList                       NEW  maps /api/sources → SourceCard[]
│   │   └─ SourceCard                   NEW  per-source: select, metadata, mode, opacity, visibility
│   │       ├─ DisplayModeToggle        NEW  ToggleGroup RGB/NDVI/false-colour  [Phase 3]
│   │       ├─ OpacitySlider            REUSE
│   │       ├─ VisibilityToggle         REUSE
│   │       └─ SourceMetadata           NEW  source · resolution · platform · date
│   ├─ BasemapSwitcher                  NEW  popover/select over basemap styles  [Phase 4]
│   └─ CompareEntry (disabled)          NEW  opens Compare; inert until backlog phase
├─ TimelineBar                          NEW  bottom filmstrip + scrubber (replaces date nav)
│   ├─ TimelineTrack                    NEW  horizontal scroll/drag of DateChip[]
│   │   └─ DateChip                     NEW  date + CloudUsabilityChip (REUSE) badge
│   ├─ TimelineScrubber                 NEW  draggable handle / keyboard arrows
│   ├─ JumpToLatest                     NEW  button → selectDefaultDate() target
│   ├─ CalendarPopover (lazy)           NEW  jump to far dates / month filter
│   └─ PlaybackControls (hidden)        NEW  play/pause/speed; ships in backlog phase
├─ MapUtilities                         NEW  corner cluster
│   ├─ MapControls                      KEEP zoom/compass/geolocate (+ add Fullscreen)
│   ├─ CoordinateReadout                NEW  lng/lat under cursor (mono, tabular)
│   ├─ ScaleReadout                     KEEP MapLibre ScaleControl (already added)
│   ├─ MeasureTool (lazy)               NEW  distance/area via Terra Draw or turf  [Phase 4]
│   └─ Legend                           NEW  colour ramp / SAR note for active mode
└─ Attribution                          KEEP dynamic source + basemap credit
```

Deprecated after migration: [LayerPanel.tsx](../apps/frontend/src/components/layers/LayerPanel.tsx),
[SourceSelector.tsx](../apps/frontend/src/components/layers/SourceSelector.tsx),
[DateList.tsx](../apps/frontend/src/components/layers/DateList.tsx) (logic absorbed into `SourceCard` /
`TimelineBar`; delete once the replacement is verified).

---

## 5. Interaction flows

1. **Open the map (cold)** → `useDefaultLayer()` resolves source+date+mode; map shows true-colour;
   `LayersSurface` collapsed; `TimelineBar` shows that source's dates with the default selected.
2. **Switch source** → click a `SourceCard` → set active source in context → `useDates(sourceId)`
   (cached) → `selectDefaultDate()` picks a date → `TimelineBar` re-renders for the new source →
   `MapLayerManager` swaps the raster (basemap untouched). SAR shows the "radar · not true colour"
   note + an info `Legend`.
3. **Pick a date** → click a `DateChip` or drag the scrubber → context `selectedDate` updates → tile
   template recomputed → overlay crossfades. Disabled chips (`tileAvailable=false`) are not selectable.
4. **Jump to latest** → `JumpToLatest` → `selectDefaultDate(dates)` → scrubber animates to that chip.
5. **Change display mode** (Phase 3) → `DisplayModeToggle` (RGB→NDVI) → tile template's `displayMode`
   changes → overlay swaps → `Legend` switches to the index colour ramp. **True-colour stays the
   default**; NDVI is never auto-selected (CLAUDE.md rule).
6. **Adjust opacity / visibility** → existing helpers `setSatelliteOpacity` / `setSatelliteVisibility`
   (no tile refetch).
7. **Basemap switch** (Phase 4) → `BasemapSwitcher` sets the basemap style; overlay re-added on top.
8. **Measure / fullscreen / coordinates** (Phase 4) → utility cluster; measure uses Terra Draw (already
   a dependency) or turf for distance/area; fullscreen via Fullscreen API.
9. **Compare** (backlog) → `CompareEntry` → pick A/B (date or source) → swipe (Resizable divider) or
   opacity blend → `Legend`/`Attribution` reflect both.
10. **Mobile** → tap `[≡ Layers]` → bottom sheet (peek→half→full); timeline collapses to a slim peek
    strip above the sheet; one-handed scrub.

---

## 6. Client state model (UI) — `MapViewProvider`

Server state stays in TanStack Query. The growing **UI** state (active source, selected date,
display mode, per-source opacity/visibility, panel open/collapsed, future compare) is consolidated
into one reducer/context to avoid prop-drilling from `MapPage`.

- Add `apps/frontend/src/state/mapViewContext.tsx` exporting `MapViewProvider` + `useMapView()`
  (React `useReducer` + context — **no new dependency**; Zustand optional later if it grows).
- Shape (illustrative):
  ```ts
  type MapViewState = {
    activeSourceId: string | null;
    selectedDate: string | null;            // YYYY-MM-DD
    displayMode: string;                     // 'RGB' default; 'NDVI' etc. Phase 3
    opacity: number;                         // 0..100
    visible: boolean;
    layersOpen: boolean;                     // surface expanded?
    compare?: { enabled: boolean; mode: 'swipe'|'opacity'; b?: {sourceId,date,displayMode} };
  };
  ```
- `MapLayerManager` reads `activeSourceId/selectedDate/displayMode/opacity/visible` from context and
  drives `applySatelliteLayer`/`setSatelliteOpacity`/`setSatelliteVisibility`. Keep its ref-isolation;
  subscribe via selector to avoid map re-creation.

---

## 7. Data layer (TanStack Query) plan

Reuse [queries.ts](../apps/frontend/src/lib/queries.ts); apply skill guidance:

- **Query-key factory**: formalize `queryKeys` (already partially present) as
  `{ config, sources, dates(sourceId), defaultLayer }`. Keep **dates keyed by `sourceId` only** —
  display mode is client state, so RGB↔NDVI causes **no refetch** (tiles swap via MapLibre).
- **No churn on date/mode switch**: `useDates` uses `placeholderData: keepPreviousData` so the
  filmstrip doesn't flash while a newly-selected source loads.
- **Prefetch on intent**: on `SourceCard` hover/focus, `queryClient.prefetchQuery(queryKeys.dates(id))`
  so switching sources is instant. (Skill: hover-prefetch.)
- **Timeline pre-warm (optional, perf)**: on scrub/hover of an adjacent `DateChip`, warm tiles by
  issuing a couple of hidden `Image()` requests for the center tile of the new date's `bounds`
  (tiles are MapLibre-managed, not Query — keep this a tiny helper, off by default).
- **`select` for timeline shape**: derive a sorted, oldest→newest array + latest-usable index via
  `select` so `TimelineTrack` gets render-ready data and only re-renders when dates change.
- Keep `staleTime` 5min / `gcTime` 30min and `refetchOnWindowFocus:false` (already set in
  [queryClient.ts](../apps/frontend/src/lib/queryClient.ts)).

---

## 8. Design-system alignment

Build only from existing tokens/recipes ([globals.css](../apps/frontend/src/styles/globals.css),
[docs/design-system.md](design-system.md)).

- **Surfaces**: every floating panel = `.glass` + `shadow-e2`, headers use `.contour`; on-map text uses
  `.on-map-text`. Saffron `--primary` for active/selection; semantic `--success/--warning/--destructive/
  --nodata` for usability badges only (not chrome). Motion via `duration-*` + `ease-*` tokens;
  panel entrances reuse `animate-panel-in`.
- **shadcn primitives to ADD** (via CLI into [components/ui/](../apps/frontend/src/components/ui/), then
  restyle to glass/tokens): `sheet`, `dialog` (or `drawer`/`vaul` for mobile bottom-sheet),
  `popover`, `tabs`, `toggle-group`, `command`, `resizable` (compare), `calendar` (lazy), `select`.
  Radix deps already present for tooltip/slider/switch/scroll-area/separator/slot.
- **New helpers**: `useMediaQuery` hook (drives drawer vs bottom-sheet); a **z-index scale** in
  Tailwind theme (`--z-map`, `--z-panel`, `--z-toolbar`, `--z-overlay`, `--z-popover`) to replace ad-hoc
  `z-10/z-20` — codify so timeline/legend/compare layer predictably.
- **Tokens to add**: a small `--timeline-height` var + safe-area insets for mobile; reuse existing
  width pattern (`w-[320px]` rail) and add `--rail-width` token so fit-to-bounds padding in
  `sceneFitPadding()` ([MapLayerManager.tsx](../apps/frontend/src/components/map/MapLayerManager.tsx)) is
  computed from tokens, not magic numbers.

---

## 9. Phased implementation roadmap

Each phase is independently shippable and preserves earlier contracts. Run after each phase:
`cd apps/frontend && yarn build && yarn lint && yarn test`.

### Phase 0 — Foundations (no visible change)
- Add shadcn primitives listed in §8; add `useMediaQuery`, `MapViewProvider`
  (`src/state/mapViewContext.tsx`), z-index tokens, `--rail-width`/`--timeline-height`.
- Wrap `MapPage` in `MapViewProvider`; migrate current source/date/opacity/visibility `useState` in
  [MapPage.tsx](../apps/frontend/src/pages/MapPage.tsx) into the reducer **without** changing UI.
- **Accept**: app behaves identically; `MapLayerManager` now reads from context; tests green.

### Phase 1 — Layers surface (collapsed → expand) + SourceCard
- Build `LayersToggleButton`, `LayersSurface` (Drawer ≥md / Sheet <md via `useMediaQuery`),
  `SourceList`, `SourceCard` (reusing `OpacitySlider`, `VisibilityToggle`, `SourceMetadata`).
- Drive from `useSources()`/`useDates()`; map "active source" to `MapViewProvider`. Render future
  sources (e.g., Landsat) as disabled "soon" rows from a config flag.
- Replace `LayerPanel` usage in `MapPage`. Keep `SourceSelector`/`DateList` until Phase 2 verifies
  date behavior, then delete.
- **Accept**: collapsed by default; expanding shows all `/api/sources`; switching source swaps the
  overlay; opacity/visibility still work; SAR shows the radar note.

### Phase 2 — Bottom timeline filmstrip + scrubber
- Build `TimelineBar` (`TimelineTrack` + `DateChip` reusing `CloudUsabilityChip`, `TimelineScrubber`,
  `JumpToLatest`, lazy `CalendarPopover`). Source dates from `useDates(activeSourceId)` with the
  `select` shape from §7; default selection via [selectDefaultDate.ts](../apps/frontend/src/lib/selectDefaultDate.ts).
- Wire keyboard (←/→ step, Home/End first/last), prefetch-on-hover, disabled chips for
  `tileAvailable=false`. Update `sceneFitPadding()` to reserve `--timeline-height` at the bottom.
- Remove the vertical date list from the layer surface (date nav now lives in the timeline). Delete
  `DateList`/`SourceSelector` after replacement checks.
- **Accept**: dates render as a horizontal strip per source; selecting/scrubbing swaps imagery;
  jump-to-latest works; mobile shows a slim peek strip.

### Phase 3 — Display modes (NDVI / false-colour)  *(frontend landed; NDVI render tiles need BFF — see §10)*
- `DisplayModeToggle` (segmented control) inside `SourceCard`, options from `source.displayModes`
  — **done** (Phase 1). Renders only when a source exposes >1 mode; selecting a mode sets `displayMode`
  in `MapViewProvider`; `composeTileTemplate()` already takes a `displayMode` segment → overlay swaps
  with **no dates refetch** (display mode is client state).
- `Legend` ([components/map/Legend.tsx](../apps/frontend/src/components/map/Legend.tsx)) renders the
  colour ramp for index modes (NDVI/NDRE/NDMI/NDWI), a false-colour key, and the SAR dB backscatter
  ramp; **true-colour shows none** — **done**. Wired bottom-left above attribution; hidden when the
  overlay is toggled off.
- **Guardrail**: true-colour (`RGB`) remains the default layer; NDVI/false-colour are never the cold
  default (CLAUDE.md). Index **display tiles** are a TiTiler colormap/expression render — distinct from
  the BFF's cloud-masked **statistics** engine, which is unchanged.
- **Remaining (BFF, §10)**: optical `source.displayModes` still returns only `['RGB']`, so the toggle
  stays single-mode until the API adds `NDVI`/`FALSE_COLOR_*` and the tile route renders them. The
  frontend lists only modes the API returns, so this ships safely ahead of the backend.
- **Accept**: toggling RGB↔NDVI re-renders tiles with no dates refetch; legend matches the mode.

### Phase 4 — Map utilities
- Add to utility cluster: **Fullscreen** (Fullscreen API button in `MapControls`) — **done**;
  **CoordinateReadout** ([components/map/CoordinateReadout.tsx](../apps/frontend/src/components/map/CoordinateReadout.tsx);
  mousemove→lng/lat, mono/tabular, rAF-coalesced, hidden on touch/leave) — **done**, placed in the
  bottom-right cluster above `MapControls`.
- **MeasureTool** ([components/map/MeasureTool.tsx](../apps/frontend/src/components/map/MeasureTool.tsx))
  — **done**. Distance/area via **Terra Draw** (`terra-draw` + `terra-draw-maplibre-gl-adapter`,
  dynamically imported so the ~220 kB engine is a lazy chunk). Geodesic math is dependency-free in
  [lib/measure.ts](../apps/frontend/src/lib/measure.ts) (haversine length + spherical-excess area).
  Sits in the bottom-right cluster between `CoordinateReadout` and `MapControls`.
- **CommandPalette** ([components/map/CommandPalette.tsx](../apps/frontend/src/components/map/CommandPalette.tsx))
  — **done**. ⌘K / Ctrl-K via `cmdk` (Radix Dialog under the hood). Groups: Sources (switch),
  Dates (jump, tile-available only), Actions (toggle layers). Triggered by the global hotkey and a
  search pill in `TopBar`. Places/geocoder search left out until a geocoder exists.
- **Deferred (need a new dep or more config)**: **BasemapSwitcher** (only one basemap style is
  configured today — revisit when multiple styles ship).
- **Accept**: each utility works without blocking map interaction; all keyboard-reachable; lazy chunks
  don't bloat initial bundle.

### Phase 5 — Backlog (design captured; build when prioritized)
- **Compare mode**: `CompareEntry` → choose A/B (two dates or two sources). **Opacity mode done**
  ([components/map/CompareControl.tsx](../apps/frontend/src/components/map/CompareControl.tsx)) —
  enable compare, pick the B date, and the overlay-opacity slider blends A over B. The B raster is
  added beneath A via `applyCompareLayer`/`removeCompareLayer` in
  [lib/satelliteLayer.ts](../apps/frontend/src/lib/satelliteLayer.ts) (basemap untouched); state lives
  in `MapViewProvider` (`compareEnabled`/`compareDate`). **Swipe mode** (two synced MapLibre instances
  + Resizable divider) is still a deferred spike — mirrors NASA Worldview's second mode.
- **Timeline playback**: **done**
  ([components/timeline/PlaybackControls.tsx](../apps/frontend/src/components/timeline/PlaybackControls.tsx))
  — play/pause + speed (1×/2×/4×) steps `selectedDate` oldest → newest, looping at the end (Google
  Earth Timelapse pattern), with next-scene pre-warm. Lives in the `TimelineBar` right cluster and
  auto-disables when fewer than two scenes are selectable.

---

## 10. BFF / API changes required

The frontend redesign mostly consumes existing contracts. Two areas need backend work; scope them
with the API owner before the relevant phase.

- **Phase 3 (display modes)** — required: extend optical `source.displayModes` beyond `['RGB']` to
  include e.g. `NDVI`, `FALSE_COLOR_URBAN`, and have the tile route render them (TiTiler expression +
  colormap, applying SCL mask) at
  `/api/tiles/{sourceId}/{date}/{mode}/{z}/{x}/{y}.png`. Touch points:
  [product.py](../apps/api/app/product.py) (tile route),
  [catalog_resolver.py](../apps/api/app/raster/catalog_resolver.py) (source registry / `displayModes`),
  band→position via [indices.py](../apps/api/app/raster/indices.py) (never hard-code positions). Add
  contract tests in [apps/api/tests/test_slice2.py](../apps/api/tests/test_slice2.py).
- **Optional metadata enrichment** (improves `SourceMetadata`/timeline tooltips) — surface fields that
  exist in STAC but aren't in the API today: `gsd`/resolution, `platform`, `s2:mgrs_tile`,
  `eo:cloud_cover`, processing baseline. Add to `/api/sources` and/or `/api/sources/{id}/dates`
  responses + the TS types in [types/api.ts](../apps/frontend/src/types/api.ts). Non-blocking; degrade
  gracefully when absent.
- **Out of scope here**: new sources (Landsat) are data/ingestion work; the UI renders whatever
  `/api/sources` returns and shows known-but-unavailable sources as disabled "soon".

---

## 11. Accessibility (apply every phase)
- All controls keyboard-operable; visible focus rings (reuse `--ring`); no `outline:none`.
- Add a **"Skip the map"** bypass link near the top (WCAG 2.4.1). Keep map tab-stops low.
- Radix primitives give roles/focus-trap for Drawer/Sheet/Popover/Command; preserve their ARIA.
- Timeline: `role="slider"` semantics on the scrubber (`aria-valuemin/max/now`, arrow keys); chips are
  buttons with `aria-current`/`aria-disabled`. Mirror existing `aria-*` usage in
  [DateList.tsx](../apps/frontend/src/components/layers/DateList.tsx)/[SourceSelector.tsx](../apps/frontend/src/components/layers/SourceSelector.tsx).
- Respect `prefers-reduced-motion` for panel/crossfade/playback animations.

---

## 12. Verification (per phase + end-to-end)
- **Automated** (after each phase): `cd apps/frontend && yarn build && yarn lint && yarn test`.
  Add/extend Vitest specs alongside new components (the repo already tests
  `MapPage`/`MapLayerManager`/layer leaves); mock `/api/*` per existing patterns.
- **Manual** (run the SPA): `cd apps/frontend && yarn dev` and verify the phase's "Accept" criteria;
  use the `/run` skill or Playwright (`playwright-cli` skill) for click-through:
  collapse/expand layers, switch source, scrub timeline, toggle mode, opacity/visibility, utilities,
  mobile bottom-sheet at a narrow viewport.
- **Contract/back-end** (Phase 3): `cd apps/api && python -m pytest tests/test_slice2.py -q` for new
  display-mode tile routes; confirm tiles render and SCL mask applies.
- **Invariants to assert**: basemap never restyles on source/date/mode change; only one overlay layer
  active (until compare); tile URLs stay relative `/api/...`; true-colour is the cold default.

---

## 13. Risks & open questions
- **Compare swipe** with MapLibre needs a spike: two synced maps vs single-map clip — decide in Phase 5.
- **NDVI display tiles** depend on BFF render support (§10); if deferred, ship Phase 3 UI behind a
  feature flag that only lists modes the API actually returns.
- **Measurement** tool choice (Terra Draw vs turf) — Terra Draw is already a dep and is slated for plot
  drawing (Phase 5 of the product), so prefer it to avoid a new dependency.
- **Bottom-sheet library**: Radix `Dialog`/`Sheet` can do it, but `vaul` gives nicer drag physics;
  decide in Phase 1 (prefer no new dep unless the UX needs it).
- Reconcile with the **concept image** if it imposes hard constraints (not available to this plan).

---

## 14. Appendix — key files

**Reuse / extend**: [MapPage.tsx](../apps/frontend/src/pages/MapPage.tsx) ·
[MapLayerManager.tsx](../apps/frontend/src/components/map/MapLayerManager.tsx) ·
[satelliteLayer.ts](../apps/frontend/src/lib/satelliteLayer.ts) ·
[api.ts](../apps/frontend/src/lib/api.ts) · [queries.ts](../apps/frontend/src/lib/queries.ts) ·
[types/api.ts](../apps/frontend/src/types/api.ts) ·
[selectDefaultDate.ts](../apps/frontend/src/lib/selectDefaultDate.ts) ·
[usability.ts](../apps/frontend/src/lib/usability.ts) ·
[CloudUsabilityChip.tsx](../apps/frontend/src/components/layers/CloudUsabilityChip.tsx) ·
[MapControls.tsx](../apps/frontend/src/components/map/MapControls.tsx) ·
[basemap.ts](../apps/frontend/src/map/basemap.ts) ·
[globals.css](../apps/frontend/src/styles/globals.css).

**New (by phase)**: `state/mapViewContext.tsx`, `hooks/useMediaQuery.ts` (P0); `components/layers/
LayersToggleButton|LayersSurface|SourceList|SourceCard|SourceMetadata.tsx` (P1); `components/timeline/
TimelineBar|TimelineTrack|DateChip|TimelineScrubber|JumpToLatest|CalendarPopover.tsx` (P2);
`components/layers/DisplayModeToggle.tsx`, `components/map/Legend.tsx` (P3); `components/map/
CoordinateReadout|BasemapSwitcher|MeasureTool.tsx`, `components/TopBar/CommandPalette.tsx` (P4);
`components/compare/*`, `components/timeline/PlaybackControls.tsx` (P5).

**Deprecate after migration**: [LayerPanel.tsx](../apps/frontend/src/components/layers/LayerPanel.tsx) ·
[SourceSelector.tsx](../apps/frontend/src/components/layers/SourceSelector.tsx) ·
[DateList.tsx](../apps/frontend/src/components/layers/DateList.tsx).

**BFF (Phase 3 / optional)**: [product.py](../apps/api/app/product.py) ·
[catalog_resolver.py](../apps/api/app/raster/catalog_resolver.py) ·
[indices.py](../apps/api/app/raster/indices.py) ·
[test_slice2.py](../apps/api/tests/test_slice2.py).
