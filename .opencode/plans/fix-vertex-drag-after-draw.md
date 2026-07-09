# Fix: vertex-drag after draw in Add Field page

## Problems

1. **Circle projection** — `TerraDrawCircleMode` is created with `projection: 'EPSG:4326'`.
   TerraDraw v1.31's `Projection` type only accepts `"web-mercator" | "globe"`.
   The invalid value causes undefined behaviour when placing the circle.

2. **SelectMode vertex dragging doesn't activate** — After drawing (polygon or circle),
   `draw.selectFeature(id)` only visually highlights the feature. The interactive
   vertex handles (draggable coordinates, midpoints) are only activated when the
   feature has `properties.mode === 'polygon'` (matching the SelectMode flags config).
   - PolygonMode creates features with `mode: 'polygon'` — but `selectFeature` still
     doesn't enable handles because the feature was added via drawing, not via
     `addFeatures()`.
   - CircleMode creates features with `mode: 'circle'` — the `polygon` flags never
     match, so vertex dragging is impossible.

## Fix: FieldDrawController.tsx

**File:** `apps/frontend/src/components/fields/FieldDrawController.tsx` (lines 130–266)

### Change 1 — Fix circle projection (line 164)

```
-   projection: 'EPSG:4326' as never,
+   projection: 'web-mercator',
```

### Change 2 — Restructure the `on('finish')` handler (lines 189–234)

**Why:** After the user finishes drawing, we `clear()` TerraDraw's store and
re-add the feature via `draw.addFeatures()`. This gives it a feature ID that
SelectMode's `selectFeature` can properly activate for interactive editing.
The new feature is created with `properties: { mode: 'polygon' }` so the
SelectMode flags (`polygon.feature.coordinates.draggable`) match.

**What changes:**
1. Move `onPolygonCompleteRef.current` — called after the feature is properly
   set up for each branch, not before the multiDraw/vertexDrag check.
2. In `multiDraw + enableVertexDrag` branch: clear, re-add with `addFeatures()`,
   switch to select mode, select new ID, then call `onPolygonCompleteRef.current`
   with the new ID so `featureToPendingRef` maps correctly.
3. In the other branches (`multiDraw` without vertexDrag, single-draw): call
   `onPolygonCompleteRef.current` as before.

## Verification

```bash
cd apps/frontend
npx tsc --noEmit     # no type errors
yarn test --run      # all 342 tests pass
```
