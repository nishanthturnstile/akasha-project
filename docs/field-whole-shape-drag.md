# Whole-field dragging (move entire shape, not just vertices)

**Date:** 2026-07-18
**Status:** Implemented and confirmed working by the user.
**Files touched:** [`apps/frontend/src/components/fields/FieldDrawController.tsx`](../apps/frontend/src/components/fields/FieldDrawController.tsx), [`apps/frontend/src/components/seasons/EditFieldDialog.tsx`](../apps/frontend/src/components/seasons/EditFieldDialog.tsx)

Related: [field-create-terradraw-edit-fix.md](field-create-terradraw-edit-fix.md)
(the prior session's fixes to per-vertex editing on `FieldCreatePage`, which
this change builds on top of).

## Context

Field boundary editing already supported dragging individual vertices and
midpoints. The user asked for the ability to grab **anywhere inside** an
already-drawn field and drag the whole shape to reposition it — the same
"move the whole polygon" interaction shown in a reference video, matching how
EOS (a competing ag platform) handles field editing. Before this change,
clicking inside a selected field's body and dragging did nothing useful (it
either did nothing or panned the underlying map).

## Root finding

TerraDraw's `TerraDrawSelectMode` exposes two independent, coexisting drag
capabilities through its `flags` config (keyed by draw-mode name — `'polygon'`
in this codebase):

- `flags.polygon.feature.coordinates.draggable` — drag a single vertex.
  Already enabled.
- `flags.polygon.feature.draggable` — a **sibling** flag, one level up from
  `coordinates`, that enables dragging the *whole* feature by clicking
  anywhere on its body. This was not set anywhere in the codebase.

This was confirmed by reading TerraDraw's own type declarations
(`node_modules/terra-draw/dist/modes/select/select.mode.d.ts`, the
`ModeFlags` type) and its `DragFeatureBehavior` class
(`modes/select/behaviors/drag-feature.behavior.d.ts`), which is a distinct
behavior from `DragCoordinateBehavior` (vertex drag). TerraDraw's own
hit-testing (`canDrag`) only starts a whole-feature drag when the pointer
didn't land on a coordinate/midpoint handle, so both flags can be enabled at
once without conflict — grabbing a vertex still drags just that vertex,
grabbing the body drags the whole shape.

## The fix

Both files configure a `TerraDrawSelectMode` with a matching
`flags.polygon.feature.coordinates` block. Both got the same one-line
addition — `draggable: true` at the `feature` level, alongside the existing
`coordinates` block:

```ts
flags: {
  polygon: {
    feature: {
      draggable: true,   // NEW — drag the whole shape by its body
      coordinates: {
        draggable: true,
        midpoints: { draggable: true },
        deletable: true,
      },
    },
  },
},
```

No other wiring changes were needed:

- In `FieldDrawController.tsx`, a whole-feature drag fires the same
  `'change'` event (with the same, unchanged feature id) that vertex drags
  already fire. The existing `draw.on('change', ...)` handler — which calls
  `onGeometryChangeRef.current?.(...)` → `FieldCreatePage`'s
  `handleGeometryChange` → updates the correct pending field via
  `featureToPendingRef` — already handles this, because the feature id
  doesn't change during a whole-feature drag (unlike the `'finish'`-time
  remove/re-add dance used elsewhere in that file).
- In `EditFieldDialog.tsx`, the existing generic
  `draw.on('change', () => { const geometry = latestPolygon(draw); if (geometry) setEditedGeometry(geometry); })`
  handler already picks up any geometry mutation regardless of cause.

`rotateable`/`scaleable` were deliberately **not** added — the request was
specifically to move (translate) the shape, not rotate or resize it.

Circles are unaffected by design: per an earlier decision (see
[field-create-terradraw-edit-fix.md](field-create-terradraw-edit-fix.md)'s
"Circle vertex count" section), circles are internally mislabeled as
`properties.mode: 'polygon'` in `FieldDrawController.tsx`'s finish handler,
so they automatically inherit this same whole-shape-drag capability with no
separate change.

## Verification

- Confirmed the dev server was serving the exact edited source (fetched
  `/src/components/fields/FieldDrawController.tsx` directly from the running
  Vite dev server and checked the `flags` block) before testing, to rule out
  a stale-HMR false negative.
- Automated (synthetic) drag gestures in the Browser pane repeatedly failed
  to reliably hit the polygon's fill target precisely enough to trigger the
  whole-feature drag — they either hit a vertex/midpoint instead or missed
  the shape entirely and panned/zoomed the underlying map (confirmed via OSM
  tile-fetch errors at a much deeper zoom level in the console). This is a
  known limitation of the synthetic input tooling for drag-heavy
  interactions, not a code issue — see the "Debugging playbook" section of
  [field-create-terradraw-edit-fix.md](field-create-terradraw-edit-fix.md).
- **Confirmed working by the user** with real mouse input: dragging from
  inside a field's body now moves the whole shape.
