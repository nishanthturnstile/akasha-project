# Global View: field-menu and map-click regressions

**Date:** 2026-07-27
**Files touched:** [`apps/frontend/src/components/discovery/DiscoveryBrowser.tsx`](../apps/frontend/src/components/discovery/DiscoveryBrowser.tsx), [`apps/frontend/src/components/discovery/DiscoveryBrowser.test.tsx`](../apps/frontend/src/components/discovery/DiscoveryBrowser.test.tsx), [`apps/frontend/src/pages/MapPage.tsx`](../apps/frontend/src/pages/MapPage.tsx)

## Background

Two previously-working Global View behaviors stopped working:

1. The 3-dot menu on a field card only showed "Field analytics" (i.e. "Open
   analytics") — Edit, Delete, and Pin were missing.
2. Clicking a field boundary directly on the Global View map no longer opened
   the field; it just silently selected/highlighted it.

## Root cause

Both regressions trace to the same commit: `1a5bb8a` ("feat: add shared field
and scouting discovery"), which replaced the legacy field list/map-click
implementation with the new discovery browser and dropped two behaviors in
the process.

### Issue 1 — 3-dot menu missing Edit/Delete/Pin/Export Contours

The pre-regression `GlobalViewPanel.tsx` had a `FieldMenu` with **Edit,
Pin/Unpin, Export Contours, Delete**. `1a5bb8a` replaced that component's
usage with `DiscoveryBrowser.tsx`'s `FieldCard`, whose dropdown was rewritten
from scratch and only kept **"Open analytics"** — the other four items were
never carried over.

(`Export Contours` was already a non-functional stub before the regression —
its old `onClick` just closed the menu. There is no contour/shapefile export
endpoint anywhere in the codebase; the equivalent "Contours SHP" button in
[`DownloadMenu.tsx`](../apps/frontend/src/components/monitoring/DownloadMenu.tsx)
is permanently disabled with the reason "Available after native vector
exports.")

### Issue 2 — map click no longer opens the field

In [`MapPage.tsx`](../apps/frontend/src/pages/MapPage.tsx), the map's
`clickHandler` for the Global View boundary layer used to do this (commit
`cd46b8f`, immediately before the regression):

```tsx
if (globalViewOpen) {
  if (seasonId) setLastFieldForSeason(seasonId, plotId);
  view.setSelectedPlotId(plotId);
  view.setFocusNonce(Date.now());
  view.setGlobalViewOpen(false);
  view.setOverlaysVisible(true);
}
navigate(`/monitoring/field-analytics/field/${plotId}`);
```

`1a5bb8a` rewrote this block (to switch the boundary source from the legacy
per-field layers to the new `discoveryFillLayerId`/`discoveryOutlineLayerId`
viewport-driven layer) and, in doing so, replaced it with:

```tsx
if (globalViewOpen) {
  view.setSelectedPlotId(plotId);
  return; // <-- navigate() below never runs
}
navigate(`/monitoring/field-analytics/field/${plotId}`);
```

The early `return` silently drops the `navigate(...)` call for every
Global-View map click, so a click only ever highlights the field.

## Fix

### `DiscoveryBrowser.tsx` — restore the full field-card menu

`FieldCard`'s dropdown now has, in the original order:

- **Open analytics** (unchanged)
- **Edit** — lazily fetches the full `Field` via `useField(fieldId)` (the
  discovery summary lacks `geometry`/`vegetationData`) and opens the existing
  `EditFieldDialog`, wired to `useUpdateField`.
- **Pin / Unpin** — added to the dropdown using the existing `togglePin`
  (the separate footer Pin/Find Field buttons are unchanged and stay in
  sync with the same state).
- **Export Contours** — restored as a **disabled** item with the reason
  "Available after native vector exports.", matching `DownloadMenu.tsx`'s
  treatment, since it was never wired to a real export.
- **Delete** — confirmed via `AlertDialogRoot` (same pattern as the old
  `GlobalViewPanel`), calling `useDeleteField`.

The dropdown (`<details>`) now closes itself after Edit/Pin/Delete via a
`ref` so it doesn't stay open once the side panel re-renders in place (it
previously only "closed" implicitly because "Open analytics" navigated away).

Both render sites (`page.pinnedItems` and `page.items`, which share
`FieldCard`) were updated with the new `onEdit`/`onDeleteRequest` props.

### `MapPage.tsx` — restore full click behavior in Global View

The `globalViewOpen` branch of `clickHandler` now mirrors the pre-regression
behavior (and `FieldCard`'s own "Open analytics" action): select the field,
bump the focus nonce, close Global View, show overlays, persist
last-field-per-season — and then fall through to `navigate(...)` instead of
returning early.

### Test fix

`DiscoveryBrowser.test.tsx` fully mocks `@/lib/queries`, so it only exposed
the exports `DiscoveryBrowser.tsx` used *before* this fix. Once the component
started importing `useField`/`useUpdateField`/`useDeleteField` and the real
`EditFieldDialog` (which transitively pulls in MapLibre-dependent map
components), the test's module graph broke with a MapLibre CJS/ESM
`SyntaxError`. Fixed the same way `MapPage.test.tsx` already isolates itself
from `MapLayerManager`: added the three missing query-hook mocks and stubbed
`EditFieldDialog` to `() => null` in the test file.

## Verification

- `tsc -p tsconfig.json --noEmit`, `eslint`, and the full `vitest run` suite
  (67 files / 437 tests) all pass.
- Verified live against the running dev stack, not just by reading the diff:
  - Opened Global View → 3-dot menu on a field card shows Open analytics,
    Edit, Pin, Export Contours (disabled), Delete.
  - **Open analytics** navigates into that field's analytics page.
  - **Edit** opens `EditFieldDialog` pre-populated with the field's real
    geometry/crop data; **Cancel → Discard** leaves the field unchanged.
  - **Pin** (dropdown) toggles the same pinned state as the footer Pin
    button — a "Pinned" section appears/disappears accordingly; unpinning
    restores the original list order.
  - **Delete** opens the "Delete field?" confirmation; **Cancel** leaves the
    field list untouched (did not exercise the destructive "Delete" path
    against real data).
  - Clicking a field boundary directly on the Global View map navigates
    straight into that field's analytics page, matching "Open analytics".
- No regressions: existing Pin/Find Field footer buttons, Open analytics,
  filters, pagination, and scouting-task cards were unaffected.
