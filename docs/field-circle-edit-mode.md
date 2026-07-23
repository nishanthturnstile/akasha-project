# Circle field editing: 4-handle mode (replacing 64-vertex select editing)

**Date:** 2026-07-23.
**Status:** Implemented, merged with the CIDSA design-system migration, fully
green on typecheck/lint/tests (423/423). Handle-count and re-render behavior
confirmed live in-browser; live drag *motion* and a from-scratch redraw in
this session's automation could not be confirmed due to Browser-pane
tooling limitations (see "Verification" below) — not attributed to the code.
**Files touched:**
[`apps/frontend/src/components/fields/circleGeometry.ts`](../apps/frontend/src/components/fields/circleGeometry.ts) (new),
[`apps/frontend/src/components/fields/circleEditMode.ts`](../apps/frontend/src/components/fields/circleEditMode.ts) (new),
[`apps/frontend/src/components/fields/FieldDrawController.tsx`](../apps/frontend/src/components/fields/FieldDrawController.tsx),
[`apps/frontend/src/components/seasons/EditFieldDialog.tsx`](../apps/frontend/src/components/seasons/EditFieldDialog.tsx),
[`apps/frontend/src/map/colors.ts`](../apps/frontend/src/map/colors.ts).

Related: [field-create-terradraw-edit-fix.md](field-create-terradraw-edit-fix.md),
[field-whole-shape-drag.md](field-whole-shape-drag.md) (prior TerraDraw
editing fixes this builds on top of).

## Context

`FieldDrawController.tsx` draws circles with `TerraDrawCircleMode({ segments:
64 })` — a plain 64-vertex polygon. Once selected for editing,
`TerraDrawSelectMode` exposes **all 64 vertices as independent drag
handles** (confirmed by reading `terra-draw@1.31.0`'s own source — there is
no vertex-count-limiting option in the library). This matches neither a
sensible editing UX nor how EOS (a competing ag platform) handles circular
fields: a center point + 4 resize handles.

A standalone SVG prototype (interaction-only, no MapLibre/TerraDraw) first
validated the target UX and, in the process, surfaced a real implementation
hazard: **rebuilding handle DOM/feature elements on every drag-move event
silently breaks pointer capture and truncates the gesture after one move.**
This finding directly shaped the real implementation (see below).

## Decision: heuristic detection, not persisted metadata

Two ways to make a *reopened* saved field remember it was drawn as a circle
were considered:

1. **Persist `shapeType`/`shapeParams` on the `Field` record** — requires an
   Alembic migration + schema/repo/router changes on the backend, plus
   remembering to clear the flag whenever geometry is mutated by something
   other than the circle editor (e.g. the freehand cut tool).
2. **Heuristic**: derive "is this a circle" from the ring's geometry alone,
   every time it's loaded, with no stored flag at all.

**Chosen: heuristic — frontend-only, zero backend changes.** The `POST`/
`PATCH /api/fields` payload is byte-identical to a hand-drawn polygon, always.
Cutting a circle naturally produces a ring that fails the heuristic on next
open — there is nothing to remember to invalidate, unlike a stored flag.

### The heuristic (`circleGeometry.ts`, `deriveCircleFromRing`)

A ring counts as circle-editable only if **all** of:

- vertex count is exactly 64 (`TerraDrawCircleMode({ segments: 64 })`'s
  output, minus the closing repeat of the first point) — not a range;
- every vertex's distance from the centroid is within **0.5%** of the mean
  radius (radius uniformity);
- the angle between consecutive vertices, seen from the centroid, is uniform
  within **2°** of the expected `360/64` step (angular uniformity).

Radius uniformity alone can't rule out a non-circular closed curve with the
same average distance from centroid; angular uniformity is what actually
pins it down. A hand-drawn ring satisfying both checks across exactly 64
points is not achievable by manual clicking. Verified against **real saved
data** (not just theory): fetched a saved circle field back via the live API
and replayed the exact math — radius deviation 0.00015%, angular deviation
0.15°, both far inside tolerance.

Also non-destructive by construction: even a hypothetical false positive
changes nothing on its own — the ring is only ever regenerated (snapped to a
mathematically perfect circle) when a handle is actually dragged, never just
from opening a field for editing.

## The custom mode (`circleEditMode.ts`, `TerraDrawCircleEditMode`)

Extends `TerraDrawBaseDrawMode` (public base class via `terra-draw`'s
`TerraDrawExtend` namespace — the same class `TerraDrawCircleMode`/
`TerraDrawPolygonMode` themselves extend). Registered permanently alongside
the other modes; which feature it targets is pushed in live via
`TerraDraw.updateModeOptions('circle-edit', { targetFeatureId })` (a public,
documented API for updating an already-registered mode's options without
reconstructing the whole `TerraDraw` instance).

- **4 handles only** (N/E/S/W cardinal), no separate center dot — moving the
  whole circle happens by dragging the shape body, mirroring how plain
  polygons already move via `flags.polygon.feature.draggable: true`
  ([field-whole-shape-drag.md](field-whole-shape-drag.md)).
- Handle features are created **once** per target and only ever get their
  geometry **patched in place** (`store.updateGeometry`) on drag — never
  removed/recreated mid-drag. This directly avoids the pointer-capture bug
  found in the prototype.
- Hit-testing: `onDragStart` checks handle proximity first (pixel-distance
  via the mode's own `project` function), then falls back to a point-in-ring
  test against the target polygon's current geometry for whole-body drag.
- Resize: `radiusMeters = distance(center, pointer)`; regenerate the ring via
  `@turf/circle` (new dep, same modular-turf family as the existing
  `@turf/difference`/`@turf/helpers`/`@turf/line-intersect`).
- `stop()`/`cleanUp()` always remove the 4 handle features — required not
  just for tidiness but because the freehand-cut-tool mode transition in
  `FieldDrawController.tsx` depends on the previous mode cleaning up after
  itself (see "Cut-tool hop fix" below).

## Wiring changes

- **`FieldDrawController.tsx`**: mode registered in the `modes: [...]`
  array; the `finish` handler routes a just-completed circle into
  `circle-edit` (instead of `select`) whenever `enableVertexDragRef.current`
  is true; the single-plot `mode === 'edit'` entry runs
  `deriveCircleFromRing()` on the loaded geometry to decide `circle-edit` vs
  `select`.
- **`EditFieldDialog.tsx`**: same custom mode registered in its own,
  separate mini-map `TerraDraw` instance (it never draws a *new* circle,
  only edits an existing geometry, so `TerraDrawCircleMode` itself is not
  needed there); load path runs the same heuristic.
- **Cut-tool hop fix** (`FieldDrawController.tsx`): the freehand-cut
  transition effect only special-cased hopping `select → polygon` before
  entering `freehand-linestring` (a pre-existing TerraDraw quirk — it can't
  transition directly from `select`). Widened to also hop from
  `circle-edit`, otherwise activating the cut tool while a circle was in
  `circle-edit` would leave it stuck active (4 handles still on screen)
  since the mode switch silently no-ops via the surrounding `catch`.

## Bug found during verification: circle invisible in `EditFieldDialog`

**Symptom** (user-reported): reopening a saved circle field via
`EditFieldDialog` showed nothing at all — not even the plain boundary, let
alone handles.

**Root cause**, confirmed by reading TerraDraw's own source
(`getModeStyles()` in `terra-draw.module.js`): a feature's paint style is
resolved by looking up `styles[feature.properties.mode]`, built from
`Object.keys(this._modes)` — i.e. only from **mode names actually
registered on that `TerraDraw` instance**. Both files tagged circle features
`properties.mode: 'circle'`, but `EditFieldDialog.tsx`'s `modes` array only
registers `polygon`, `select`, and `circle-edit` (deliberately no
`TerraDrawCircleMode`, since that dialog never draws a brand-new circle) —
so the lookup resolved to `undefined` and the feature silently failed to
render. `FieldDrawController.tsx` didn't hit this because it *does* register
`TerraDrawCircleMode` (name `'circle'`) for drawing new circles. Also
confirmed directly in `addFeatures`'s own validation path, which explicitly
rejects a feature whose `properties.mode` doesn't match a registered mode.

**Fix:** tag the polygon feature `properties.mode: 'polygon'` **always**,
regardless of shape, in both files. Safe because `TerraDrawCircleEditMode`
never reads `properties.mode` to find its target — it uses the explicit
`targetFeatureId` passed via `updateModeOptions`. The tag is purely a
display-styling concern, and `TerraDrawPolygonMode` is reliably registered
in both files.

## Merge with the CIDSA design-system migration

While this feature was in progress, 5 commits landed upstream
(`feat: migrate UI to CIDSA design system` and follow-ups) touching the same
two files plus `package.json`/`yarn.lock`. Pulled via stash → fast-forward
pull → stash pop; all four overlapping files auto-merged cleanly (no
conflict markers).

One real incompatibility: the redesign added a `designSystem.test.ts`
guardrail banning hardcoded hex-color literals in `.tsx` files (checking
`Object.keys` of source files ending in `.tsx`, not `.ts` — so the two new
`.ts` files were unaffected). The handle styling
(`handleColor: '#f59e0b'`, `handleOutlineColor: '#ffffff'`) tripped it in
the two `.tsx` files. Fixed by adding a `handle: '#f59e0b'` entry to the
existing `MAP_UI_COLORS` palette (`src/map/colors.ts`) and referencing
`MAP_UI_COLORS.handle` / `MAP_UI_COLORS.white` instead — consistent with how
the redesign already handled the polygon/select colors elsewhere in the
same files.

## Verification

- **Typecheck** (`tsconfig.json` and `tsconfig.node.json`): clean.
- **Lint**: clean on all touched/new files.
- **Full test suite**: 423/423 tests passing across 63 files (not just the
  circle-related ones — the entire suite, post-merge).
- **Live, confirmed with screenshots**:
  - A freshly drawn circle shows **exactly 4 handles**, not 64.
  - After the `properties.mode` fix, reopening a saved circle field via
    `EditFieldDialog` renders the boundary **and** all 4 handles correctly.
  - A saved circle's real ring, pulled from the live API, passes the
    heuristic with radius/angle deviations far inside tolerance.
- **Not cleanly confirmed in this session**: live drag *motion* (only
  `onDragStart` could be observed firing correctly via temporary
  instrumentation; the Browser pane's synthetic drag/click primitives
  repeatedly failed to generate the intermediate pointer-move events
  MapLibre's gesture recognizer needs — a known category of limitation for
  this tooling with canvas/WebGL map libraries, documented previously in
  [field-whole-shape-drag.md](field-whole-shape-drag.md)'s "Debugging
  playbook" reference). Regular DOM button clicks continued to work
  correctly throughout, isolating the issue to map-canvas gesture
  recognition specifically, not a general tooling breakdown.
