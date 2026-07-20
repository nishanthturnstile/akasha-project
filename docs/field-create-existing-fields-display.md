# Show existing season fields while adding a field

**Date:** 2026-07-19
**Status:** Implemented and verified live, including a follow-up fix for a
whole-field-drag regression this introduced.
**Files touched:** [`apps/frontend/src/pages/monitoring/FieldCreatePage.tsx`](../apps/frontend/src/pages/monitoring/FieldCreatePage.tsx), [`apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`](../apps/frontend/src/components/fields/FieldBoundaryLayer.tsx)

Related: [global-view-all-season-fields.md](global-view-all-season-fields.md)
(the Global View feature this extends the same idea to).

## Context

`FieldCreatePage` (the "Add field" flow) drew nothing on the map except the
field(s) currently being created — existing saved fields for the season were
completely invisible while drawing. This made it hard to see where existing
fields already were while drawing a new one nearby (avoiding overlaps,
orienting relative to neighbors). The user asked to extend the same "display
all fields" capability just built for Global View to this flow.

Two decisions scoped this down deliberately from a full Global View port:

- **No hover-name label.** Global View's cursor-following name tooltip
  (see the "field-name hover label" section of
  [global-view-all-season-fields.md](global-view-all-season-fields.md)) was
  **not** ported here — just the boundaries.
- **No click handling.** Existing fields are a purely visual backdrop.
  Clicking on or near one still behaves exactly like clicking empty map space
  (places a draw vertex, as today) — nothing navigates away or interrupts an
  in-progress multi-field draw.

## Root finding / reused pieces

- `FieldCreatePage.tsx` already calls `const fieldsQ = useFields();` (all
  fields, client-side), previously used only by the auto-naming effect to
  find the next "Field N" number for the season via
  `f.seasonIds?.includes(selectedSeasonId ?? '')`. The exact same filter
  gives the season's existing fields for rendering — no new query.
- `<FieldBoundaryLayer>` already supports many simultaneous instances via its
  `layerPrefix` prop (namespacing MapLibre source/layer ids in
  `fieldBoundaryLayerHelpers.ts`), the exact mechanism already proven for
  Global View's `seasonFields.map((field) => <FieldBoundaryLayer .../>)` block
  in `MapPage.tsx`. It's a pure GeoJSON visual layer, entirely separate from
  `FieldDrawController`'s own TerraDraw feature store, so it can't be
  selected/dragged and can't interfere with drawing.
- `FieldCreatePage` already tracks the active season via `selectedSeasonId`
  local state (pre-filled from `?seasonId=` when deep-linked) — no new state
  needed to know which season's fields to show.

## The fix

```tsx
// Existing saved fields for the season, shown as background reference
// outlines while drawing new ones -- purely visual, not part of TerraDraw's
// own feature store, so they can't be selected/dragged/interfere with draw.
const existingSeasonFields = useMemo(() => {
  if (!selectedSeasonId) return [];
  return (fieldsQ.data ?? []).filter((f) => f.seasonIds?.includes(selectedSeasonId));
}, [selectedSeasonId, fieldsQ.data]);
```

```tsx
{ existingSeasonFields.map((field) => (
  <FieldBoundaryLayer
    key={ field.id }
    map={ map }
    plot={ field }
    featureId={ field.id }
    name={ field.name }
    layerPrefix={ field.id }
  />
)) }
```

Rendered right alongside the existing `draftGeometry &&` boundary-layer block.
No `geometry` prop is passed (only `plot`), matching how Global View renders
each season field in `MapPage.tsx`.

That's the entire change — no new event handlers, no camera/fit-bounds
changes. The page keeps centering on the AOI/draw zoom as before; auto-fitting
the camera to existing fields would fight the "start drawing immediately"
flow and wasn't asked for.

## Follow-up fix: whole-field drag broke after this landed

**Symptom:** after adding the existing-fields display, a newly drawn field's
own fill/outline stopped rendering — only its tiny vertex/midpoint dots
remained visible. From the user's perspective, "dragging the entire field
(which was already fixed earlier) stopped working" — in reality vertex
dragging still worked (grabbing one of the visible dots), but there was no
visible fill/body left to grab for a whole-shape drag, since it wasn't being
drawn at all.

**Root cause:** `FieldBoundaryLayer.tsx` (`apps/frontend/src/components/fields/FieldBoundaryLayer.tsx`)
registers `map.on('styledata', ...)` / `map.on('idle', ...)` listeners that
call `ensureFieldBoundaryOrder()` on *every* such event, which calls
`map.moveLayer(fill); map.moveLayer(outline);` — moving that instance's
layers to the absolute top of the *entire* style's layer stack, every time.
This is fine for a single instance (the "draft field" or "currently selected
field" layer, which just needs to stay above the basemap/imagery). But once
4 *existing-field* instances are rendering simultaneously, each with its own
copy of these listeners, they all fight to re-assert themselves to the top on
every style change — including style changes caused by `FieldDrawController`
adding/updating its own TerraDraw-managed layers for the actively-drawn
field. Whichever background instance's listener fires last after such a
change wins the top slot, perpetually burying the actively-drawn field's own
fill/outline underneath the 4 background reference layers.

(TerraDraw's own click/drag hit-testing is unaffected by any of this — it's
confirmed via reading the library's source that `FeatureAtPointerEventBehavior.find()`
searches TerraDraw's own in-memory feature store by geometry, not MapLibre's
rendered pixel content — so vertex dragging kept working throughout. Only the
*visual* fill/outline, and by extension the user's ability to see where to
grab the shape's body for a whole-field drag, was broken.)

**Fix:** added an opt-out `keepOnTop?: boolean` prop to `FieldBoundaryLayer`
(default `true`, preserving today's behavior for every other caller — the
single draft/selected/edited-field usages in `MapPage.tsx`/`EditFieldDialog.tsx`/
`FieldCreatePage.tsx`'s own draft layer, and Global View's per-field loop in
`MapPage.tsx`, none of which have multiple competing instances alongside an
actively-edited TerraDraw feature). When `keepOnTop` is `false`, the effect
skips attaching the `styledata`/`idle` re-assertion listeners entirely —
the layer still gets added (and lands below whatever is added after it,
including `FieldDrawController`'s layers, since MapLibre appends new layers to
the top of the stack by default), it just stops perpetually reclaiming the
top spot. `FieldCreatePage.tsx`'s existing-fields loop now passes
`keepOnTop={false}`.

## Verification

- `npx tsc --noEmit` clean on both `tsconfig.json` and `tsconfig.node.json`,
  after both the original change and the `keepOnTop` fix.
- Live-tested against the running dev stack:
  - Selected a season ("Pre-winter 25") with 4 existing fields on the Add
    Field page. Confirmed via `map.getStyle().sources`/`.layers` that all 4
    `<fieldId>akasha-field-boundary-*` entries were registered.
  - **Before the `keepOnTop` fix:** drew a new field and confirmed the exact
    reported regression — only vertex/midpoint dots rendered, no visible
    fill/outline for the new shape.
  - **After the fix:** redrew a new field — fill and outline rendered
    correctly on top of the background reference layers, exactly as before
    the existing-fields feature was added.
  - Dragged from inside the shape's body (away from any vertex/midpoint) —
    confirmed a true whole-shape translate (area unchanged, same
    size/orientation, just repositioned), not a vertex/midpoint deformation.
  - Confirmed no season selected → no existing-field boundaries rendered (no
    errors, no stray layers) — matches the `!selectedSeasonId` short-circuit.
- `yarn vitest run` (full frontend suite) re-run after the `keepOnTop` fix to
  confirm no regressions.
