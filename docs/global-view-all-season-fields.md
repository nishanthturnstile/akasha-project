# Global View: render all season fields on the map

**Date:** 2026-07-18
**Status:** Implemented and verified live, including two follow-up fixes (click-to-select and a hover name label).
**Files touched:** [`apps/frontend/src/state/mapViewState.ts`](../apps/frontend/src/state/mapViewState.ts), [`apps/frontend/src/state/mapViewContext.tsx`](../apps/frontend/src/state/mapViewContext.tsx), [`apps/frontend/src/components/shell/AppShell.tsx`](../apps/frontend/src/components/shell/AppShell.tsx), [`apps/frontend/src/pages/MapPage.tsx`](../apps/frontend/src/pages/MapPage.tsx)

## Context

A reference video (a competing ag platform) showed: once "Global View" is
active, the map displays every field boundary for the selected season at
once. In Akasha, "Global View" already existed as a UI mode — clicking the
"Global View" nav item opened a side panel (`GlobalViewPanel`) listing the
season's fields — but **the map itself never drew any of those boundaries**.
`MapPage.tsx` only ever rendered a single `<FieldBoundaryLayer>` for whichever
one field was currently selected. This change makes the map actually draw all
of the season's fields when Global View is active.

Per an explicit decision during planning, the *season-selector* navigation
behavior (clicking a season jumps straight to a remembered/first field when
one exists) was **not** changed — only the map-rendering gap was fixed.

## Root finding

- `globalViewOpen` was local `useState` in `AppShell.tsx`, toggled through a
  single funnel function, `setGlobalViewMode`, that all ~6 call sites already
  used. It was not exposed to `MapPage.tsx` in any way.
- `MapPage.tsx` already had every field loaded client-side (`const plotsQ = useFields()`)
  and already knew the current season id via `useSeasonContext()` (rendered
  inside `<SeasonProvider seasonId={effectiveSeasonId}>` in `AppShell.tsx`).
- `<FieldBoundaryLayer>` already supported a `layerPrefix` prop that namespaces
  its MapLibre source/layer ids (`fieldBoundaryLayerHelpers.ts`), so mounting
  one instance per field with `layerPrefix={field.id}` is a safe, already-built
  pattern — just never previously used with more than one instance at a time.
- `focusPlot(map, plot)` already existed to fit the map to one field's bounds;
  trivially extended to `focusPlots(map, plots)` by combining all their
  coordinates before computing min/max.

## The fix

**1. Expose `globalViewOpen` to `MapPage` via the shared map-view context.**
Added a `globalViewOpen: boolean` field (default `false`) to `MapViewState`
and a `setGlobalViewOpen` action, following the exact same pattern as the
neighboring `overlaysVisible`/`setOverlaysVisible` field. In `AppShell.tsx`,
mirrored the value at the single existing funnel point:

```tsx
const setGlobalViewMode = (isGlobalView: boolean) => {
  setGlobalViewOpen(isGlobalView);
  view.setOverlaysVisible(!isGlobalView);
  view.setGlobalViewOpen(isGlobalView); // NEW
};
```

(plus the equivalent in the mount-sync effect). This was the *only* change to
`AppShell.tsx` — none of its ~20 other `globalViewOpen` read/write call sites
needed to change, since they all already funnel through this one function or
read the pre-existing local state for AppShell's own rendering.

**2. Render all season fields on the map in `MapPage.tsx`.**
- `seasonFields = globalViewOpen && seasonId ? (plotsQ.data ?? []).filter(f => f.seasonIds?.includes(seasonId)) : []`
  — reuses the already-loaded `plotsQ`, no new query.
- The single `<FieldBoundaryLayer plot={selectedPlot} .../>` now passes
  `plot={globalViewOpen ? null : selectedPlot}` (so it renders nothing under
  its own default-prefixed layer while Global View is active, avoiding a
  double-render of whichever field happens to be selected), and a new block
  renders one `<FieldBoundaryLayer key={field.id} plot={field} layerPrefix={field.id} .../>`
  per season field when `globalViewOpen` is true.
- A new effect calls `focusPlots(map, seasonFields)` (a `fitBounds` over the
  combined coordinates of every season field) whenever Global View turns on
  or the season changes while it's already on, guarded by a `prevGlobalViewFitKey`
  ref so it only re-fits when the season or field count actually changes, not
  on every render.

Not changed: the season-selector's jump-to-remembered-field navigation
(explicit scope decision); no differentiated styling for a "previously
selected" field vs. the rest; no bulk-merged-GeoJSON-source renderer for very
large seasons (the existing per-field `layerPrefix` pattern is reused as-is,
since building a bulk-source variant would solve a scaling problem this app
doesn't have yet).

## Follow-up fix: clicking a field on the map in Global View

After the above landed, testing surfaced a real gap: the map's existing
click/hover handler (in `MapPage.tsx`, the "Field boundary interactions"
effect) only ever hit-tested against the single default-prefixed boundary
layer (`FIELD_BOUNDARY_FILL_LAYER_ID`). Since that layer is now empty while
Global View is active (`plot={globalViewOpen ? null : selectedPlot}`),
clicking *any* of the season-field boundaries drawn on the map did nothing —
there was no way to select a specific field from the map, which was
especially confusing where multiple fields' boundaries visually overlap.

**Fix:** the hit-test now builds its layer list from all of the season
fields' own prefixed fill layers when `globalViewOpen` is true (falling back
to the single selected-field layer otherwise), and reads the clicked
feature's `properties.plotId` (already set correctly per field by
`buildFieldBoundaryFeatureCollectionFromGeometry`) instead of the stale
`selectedPlotId` closed over from before. Overlapping fields are disambiguated
by whichever is topmost in MapLibre's render order — the same behavior any
map app has for overlapping features; not something to special-case further.

This surfaced a second, deeper issue: clicking a field on the map only
`navigate()`d to its URL — it didn't close Global View or update the shared
selection state, so the UI stayed showing the Global View panel/all fields
underneath the changed URL. `GlobalViewPanel`'s own field-row click already
does the right thing (`view.setSelectedPlotId`, `view.setFocusNonce`,
`onClose()` which is AppShell's `setGlobalViewMode(false)`, then navigate),
but `AppShell`'s `setGlobalViewMode`/`globalViewOpen` was local state with only
a one-way mirror into the shared `mapViewContext` (written by `AppShell`, read
by `MapPage`) — `MapPage` calling the mirrored setter would update its own
copy but not `AppShell`'s, causing a desync (map reverts to single-field
rendering while the side panel still shows "Global View").

**Fix:** promoted `globalViewOpen` to live *only* in `mapViewContext`,
removing `AppShell`'s local `useState` entirely. `AppShell`'s route-aware
initial value is now computed once as a plain `const` and pushed into the
context on mount; every other read/write in `AppShell` (~10 sites: nav-item
highlighting, the panel-visibility flag, the "re-expand nav group on close"
effect) now goes through `view.globalViewOpen`/`view.setGlobalViewOpen`
instead of the old local state. `MapPage`'s click handler mirrors
`GlobalViewPanel`'s row-click exactly: `setLastFieldForSeason`, then
`view.setSelectedPlotId` / `view.setFocusNonce` / `view.setGlobalViewOpen(false)`,
then `navigate(...)`.

## Verification

- `npx tsc --noEmit` clean on both `tsconfig.json` and `tsconfig.node.json`,
  after every change (including the `AppShell` state migration).
- Live-tested against the running dev stack:
  - Opened Global View for a season with 4 fields — confirmed the map drew a
    boundary for every field (verified via `map.getStyle().sources`/`.layers`,
    which showed 4 distinct `<fieldId>akasha-field-boundary-*` entries) and
    fit the view to include all of them. Three of the four fields happened to
    be geographically clustered within ~100m of each other in this test
    account's data, which initially looked like "only 2 fields rendered" at
    normal zoom — zooming in confirmed all 3 render as distinct overlapping
    shapes, not a rendering bug.
  - Confirmed the click-hit-test fix with `map.queryRenderedFeatures` and a
    directly-fired `map.fire('click', ...)` (bypassing synthetic-input
    precision issues — see the "Debugging playbook" in
    [field-create-terradraw-edit-fix.md](field-create-terradraw-edit-fix.md))
    before confirming it with a real click in the browser: clicking one of the
    three overlapping fields correctly navigated to *that specific field's*
    id, not a stale or wrong one.
  - After the `AppShell` state migration, clicking a field on the map now
    correctly closes Global View (panel disappears, nav highlights "Field
    analytics") in addition to navigating — matching the panel's own row-click
    behavior.
  - Clicking a field row in the Global View panel still closes Global View and
    navigates to that field's single-field analytics view, showing exactly
    one boundary with no leftover layers from the other season fields.
  - Confirmed the plain single-field flow (`FieldAnalyticsPage`) is visually
    unaffected when Global View isn't active.
  - A transient batch of React error-boundary console errors appeared during
    active HMR edits (stale component instances referencing state from a
    just-removed hook mid hot-reload) — confirmed via a full page reload that
    these did not persist and were not a real bug in the final code.
- `yarn vitest run` (full frontend suite): **53 test files / 395 tests
  passed**, no regressions — re-run after the `AppShell` state migration too.

## Follow-up: field-name hover label in Global View

**Ask:** while Global View shows every season field on the map, hovering over
one gives no indication of which field it is — the shape alone doesn't say
"Field 5", and that's actively confusing where several fields overlap (as the
three clustered test fields above do). Requested fix: show the field's name
near the cursor on hover.

### Why this was cheap to add

Two pieces already existed and needed no new infrastructure:

1. **The hit-test was already running on every mouse move.** The "Field
   boundary interactions" effect in `MapPage.tsx` (the same one behind the
   click-to-select fix above) already calls `fieldAtPoint(e)` on every
   `mousemove` to decide whether to show a pointer cursor. That returned
   MapLibre feature already carries a `name` property — set on every field
   feature by `buildFieldBoundaryFeatureCollectionFromGeometry` (in
   `fieldBoundaryLayerHelpers.ts`) as `properties: { name, plotId }`. So no
   new query, no new hit-test — just read one more field off an object
   already in hand.
2. **The cursor-following floating-label pattern already existed.**
   `apps/frontend/src/components/map/CoordinateReadout.tsx` already renders a
   small absolutely-positioned tooltip that follows the cursor over the map,
   using a `requestAnimationFrame`-coalesced `mousemove` handler so it updates
   smoothly without a React re-render on every raw pixel of mouse movement.
   The new label copies that exact mechanism at a much smaller scale.

### The change

**State** (`MapPage.tsx`, next to the other page-level `useState`s):

```tsx
const [hoveredField, setHoveredField] = useState<{ name: string; x: number; y: number } | null>(null);
const hoveredFieldFrame = useRef<number | null>(null);
const pendingHoveredField = useRef<{ name: string; x: number; y: number } | null>(null);
```

Two different mechanisms for two different jobs: `hoveredField` is the value
React actually renders from; `pendingHoveredField` is the *latest* value seen
on any `mousemove`, updated synchronously and cheaply on every event;
`hoveredFieldFrame` makes sure at most one `requestAnimationFrame` callback is
in flight, so `setHoveredField` (the actual state update, which triggers a
render) fires at most once per animation frame no matter how many
`mousemove` events MapLibre dispatches in that frame.

**Hit-test + rAF-coalesced update** (inside the existing "Field boundary
interactions" `useEffect`, extending the existing `moveHandler`):

```tsx
const moveHandler = (e: maplibregl.MapMouseEvent) => {
  if (fieldMode) return;
  const feature = fieldAtPoint(e);          // <- already existed, for cursor styling
  canvas.style.cursor = feature ? hoverCursor : '';
  if (globalViewOpen) {
    const name = feature?.properties?.name as string | undefined;
    pendingHoveredField.current = name ? { name, x: e.point.x, y: e.point.y } : null;
    if (hoveredFieldFrame.current === null) {
      hoveredFieldFrame.current = requestAnimationFrame(() => {
        hoveredFieldFrame.current = null;
        setHoveredField(pendingHoveredField.current);
      });
    }
  }
};
const leaveHandler = () => {
  canvas.style.cursor = '';
  pendingHoveredField.current = null;
  setHoveredField(null);
};
```

Gated on `globalViewOpen` — in single-field view the header already shows the
selected field's name, so the label would be redundant there, and the effect
already branches its layer-id list on `globalViewOpen` anyway (see the
click-to-select fix above).

**Cleanup**, added to the effect's existing `return () => { ... }` teardown,
so a stale label can't linger (e.g. if the mouse is mid-hover the instant
Global View is toggled off, which re-runs this effect since `globalViewOpen`
is in its dependency array):

```tsx
return () => {
  map.off('mousemove', moveHandler);
  map.off('mouseout', leaveHandler);
  map.off('click', clickHandler);
  canvas.style.cursor = '';
  if (hoveredFieldFrame.current !== null) {
    cancelAnimationFrame(hoveredFieldFrame.current);
    hoveredFieldFrame.current = null;
  }
  pendingHoveredField.current = null;
  setHoveredField(null);
};
```

**Render** (JSX, right after the per-field `<FieldBoundaryLayer>` loop, inside
the same `relative`-positioned map container `CoordinateReadout` renders
into, so raw `event.point.x`/`.y` pixel coordinates map directly to CSS
`left`/`top` with no extra offset math):

```tsx
{ globalViewOpen && hoveredField && (
  <div
    data-testid="global-view-field-hover-label"
    aria-hidden="true"
    className="glass pointer-events-none absolute z-popover select-none rounded-md px-2.5 py-1 text-[12px] font-medium text-foreground on-map-text"
    style={ {
      left: hoveredField.x,
      top: hoveredField.y,
      transform: 'translate(-50%, calc(-100% - 10px))',
    } }
  >
    { hoveredField.name }
  </div>
) }
```

`translate(-50%, calc(-100% - 10px))` centers the label horizontally on the
cursor and floats it 10px above the cursor's own tip (translating up by its
own full height plus the 10px gap) — the same offset idea `CoordinateReadout`
uses for its own tooltip, just without that component's extra edge-clamping
logic (`TOOLTIP_HALF_WIDTH_PX`/`TOOLTIP_TOP_GUARD_PX`), since a short one-line
field name is far less likely to overflow the viewport edge than that
component's multi-line index readout.

`pointer-events-none` keeps the label from intercepting the next `mousemove`/
`click` meant for the map underneath it; `glass`/`on-map-text` are the same
utility classes `CoordinateReadout` already uses for its own on-map tooltip,
so the new label matches the existing visual language with no new CSS.

**Verified live:** hovering one of the three overlapping clustered test
fields showed its correct name ("Field 5") in a label following the cursor;
moving to empty map space cleared the label; moving off the map entirely
(`mouseout`) also cleared it. Typecheck clean on both tsconfigs; full test
suite (395 tests) still passing after this change.
