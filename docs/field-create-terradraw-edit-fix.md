# FieldCreatePage: post-draw vertex editing fixes

**Date:** 2026-07-17
**Files touched:** [`apps/frontend/src/pages/monitoring/FieldCreatePage.tsx`](../apps/frontend/src/pages/monitoring/FieldCreatePage.tsx), [`apps/frontend/src/components/fields/FieldDrawController.tsx`](../apps/frontend/src/components/fields/FieldDrawController.tsx)

## Background

`FieldCreatePage` lets a user draw one or more field boundaries on the main
map before saving them (multi-draw mode). `EditFieldDialog` — used elsewhere
to edit an already-saved field's boundary in a small popup map — already
supported dragging a polygon's vertices/midpoints via TerraDraw's
`TerraDrawSelectMode`. `FieldCreatePage` was supposed to offer the same
in-place editing directly on the main map after a shape is drawn, but it
didn't work: you could draw a field, but you couldn't then drag its vertices
to adjust it.

Three separate, compounding bugs were found and fixed. A fourth request
(reduce a drawn circle to 4 edit points) was investigated but **reverted at
the user's request** — see [Circle vertex count (reverted)](#circle-vertex-count-investigated-then-reverted).

## Bug 1 — the auto-opened naming dialog blocked the map entirely

**Symptom:** "we're able to draw in map but unable to edit after draw."

**Root cause:** [`FieldCreatePage.tsx`](../apps/frontend/src/pages/monitoring/FieldCreatePage.tsx)'s
`handlePolygonComplete` called `setEditingPendingField(newField)` immediately
after every finished shape, which mounted `EditFieldDialog` as a full-screen
modal (`fixed inset-0` overlay with `onInteractOutside={(e) => e.preventDefault()}`).
That modal blocked all pointer events to the main map underneath it. Even
though `FieldDrawController` correctly put the just-finished shape into
TerraDraw select mode with draggable vertices/midpoints, the user could never
reach the map to use them — the dialog was always in the way, immediately.

**Fix:** Removed the `setEditingPendingField(newField)` call from
`handlePolygonComplete`. Default field naming (`Field`, `Field 1`, ...) still
happens automatically; the pencil icon in the side panel still opens
`EditFieldDialog` on demand for renaming or editing vegetation cycles.

## Bug 2 — an unstable callback silently reset TerraDraw's mode every render

**Symptom (after fixing Bug 1):** still couldn't edit; clicking near a shape
did nothing useful visually at first glance, and deeper testing showed the
draw mode was flipping back to "place a new vertex" mode right after each
shape finished.

**Root cause:** `FieldCreatePage` passed two inline arrow functions as
props to `FieldDrawController`:

```tsx
<FieldDrawController
  ...
  onCancel={ () => setFieldMode(null) }
  onUpdateField={ () => Promise.resolve() }
  ...
/>
```

Every time `FieldCreatePage` re-rendered (e.g. because `handlePolygonComplete`
calls `setPendingFields`), these got new function identities.
`FieldDrawController`'s main `useEffect` (the one that puts TerraDraw into
`'draw'` mode and picks `'polygon'` vs `'circle'`) lists `onCancel` in its
dependency array, so the effect re-ran on every single `FieldCreatePage`
render — and unconditionally called `draw.setMode('polygon')` again each
time it ran. The very first thing that happens after a shape finishes is
`handlePolygonComplete` calling `setPendingFields`, which triggers exactly
this re-render/re-run cycle, snapping TerraDraw straight back from `'select'`
to `'polygon'` mode a fraction of a second after it had been switched.

**Fix:** wrapped both callbacks in `useCallback` with stable (empty)
dependency arrays:

```tsx
const handleCancelDraw = useCallback(() => setFieldMode(null), []);
const handleUpdateField = useCallback(() => Promise.resolve(), []);
```

and passed `handleCancelDraw` / `handleUpdateField` instead of the inline
arrows. This stopped the spurious mode-reset effect from re-running on every
render.

## Bug 3 — TerraDraw's own SelectMode re-fires `'finish'`, causing duplicate fields / an infinite loop

**Symptom (after fixing Bugs 1 & 2):** dragging a vertex/midpoint *did* move
it, but each such edit also added a brand-new duplicate pending field to the
side panel ("Field 6", "Field 7", ...) — confirmed via live debugging to be
an unbounded loop, not a one-off duplicate.

**Root cause:** confirmed by temporarily instrumenting `FieldDrawController`'s
`'finish'`/`'select'`/`'deselect'` handlers with `console.log`/`console.error`
and reproducing the bug live. The observed event sequence for a *single* user
drag was:

```
select(id A) → finish(id A, terraDrawMode=select) → deselect(id A)
  → select(id B) → finish(id B, terraDrawMode=select) → deselect(id B)
  → select(id C) → ...
```

`FieldDrawController`'s `draw.on('finish', ...)` handler had no way to tell
"a brand-new polygon/circle was just completed by the user" apart from "the
already-selected feature just committed an edit." It treated *every*
`'finish'` event the same way: remove the feature, re-add it with a new
internal id, call `draw.setMode('select'); draw.selectFeature(newId)`, and
call `onPolygonComplete` — which unconditionally appends a new pending field.

The catch: `draw.selectFeature(newId)` itself makes TerraDraw's
`TerraDrawSelectMode` internally emit **another** `'finish'` event as part of
its own select/edit lifecycle. Since our handler didn't check what mode
TerraDraw was actually in when `'finish'` fired, it treated that self-emitted
event as "a new shape was drawn" too — re-running the exact same
remove-and-reselect dance, which fired another `'finish'`, forever. One real
user drag was enough to kick off a self-perpetuating loop; each cycle
produced one more duplicate pending field until something (React re-render
throttling, or the user's patience) stopped it.

**Fix:** `draw.getMode()` is now checked at the top of the `'finish'` handler.
`'finish'` is only treated as "a new shape completed drawing" when TerraDraw
was actually in a *drawing* mode (`'polygon'`, `'circle'`, or
`'freehand-linestring'` for the cut-line tool) at that moment. If it fired
while already in `'select'` mode, the event is ignored outright:

```tsx
draw.on('finish', (id) => {
  if (modeRef.current !== 'draw') return;
  const terraDrawMode = draw.getMode();
  if (terraDrawMode !== 'polygon' && terraDrawMode !== 'circle' && terraDrawMode !== 'freehand-linestring') {
    return;
  }
  // ... existing "a shape was completed" handling, now only reachable
  // for genuine new-shape completions.
});
```

This also incidentally fixed **"after this I am not able to add multiple
fields"** — see Bug 4.

## Bug 4 — multi-field drawing needed an explicit way to re-enter drawing mode

**Symptom (introduced by fixing Bugs 2 & 3):** once the mode was no longer
being (buggily) reset to `'polygon'` on every render, there was nothing left
to put TerraDraw back into a drawing mode after a shape finished and TerraDraw
settled into `'select'` mode. Clicking on empty map space while in `'select'`
mode doesn't place new vertices — it only interacts with the selected
feature or deselects it — so once a shape was drawn, the user was stuck; the
only way to draw a second field had accidentally been Bug 2's "reset to
polygon on every render" glitch.

**Fix:** the existing polygon/circle toggle buttons in the left toolbar (used
to pick which shape to draw) now also explicitly re-arm TerraDraw's drawing
mode when clicked:

```tsx
onClick={ () => {
  if (cutMode) { setCutMode(false); }
  setShapeMode('polygon');
  try { drawInstanceRef.current?.setMode('polygon'); } catch { /* ignore */ }
  ...
} }
```

(and the equivalent for the circle button with `'circle'`). After finishing
and editing one field, clicking the polygon/circle tool icon again starts the
next one.

## Verification

All four fixes were verified live against the running dev stack (Docker
backend + `yarn dev` frontend), not just by reading the diff:

- Drew a field → no dialog interrupted the map; the shape stayed selected
  with visible drag handles.
- Dragged a vertex → the shape updated in place; pending-field count stayed
  unchanged (no duplicate).
- Clicked the polygon toolbar icon again after finishing one field → drew a
  second, independent field; pending-field count went from 1 to 2, not more.
- Checked `preview_logs` / browser console after each change for build or
  runtime errors — none.

## Circle vertex count (investigated, then reverted)

A separate request came in: "after drawing a circle the points should be
only 4, currently it is creating more points." TerraDraw stores a drawn
circle as a many-vertex polygon approximation (`segments: 64` in
`TerraDrawCircleMode`'s config), and — once the mode-mislabeling bug above is
fixed so a circle is correctly tagged `properties.mode: 'circle'` instead of
`'polygon'` — every one of those 64 vertices was individually draggable via
the shared `polygon` select-mode flags.

Two approaches were investigated:

1. Added a dedicated `flags.circle` entry using TerraDraw's
   `coordinates.resizable: 'center'` option instead of `draggable`, hoping it
   would expose a small, fixed set of resize handles instead of all 64
   points. **This didn't work** — reading TerraDraw's source showed that
   `TerraDrawSelectMode` renders a "selection point" marker at *every*
   coordinate of a selected feature whenever a `flags.<mode>.feature.coordinates`
   object exists at all, regardless of whether it says `draggable` or
   `resizable`. There is no built-in "N fixed handles" resize widget in this
   version of TerraDraw (`terra-draw@^1.31.0`).
2. Reducing `segments: 64` → `segments: 4` in `TerraDrawCircleMode`, which
   would make a drawn "circle" an actual 4-vertex polygon (visually a
   diamond/rounded shape, not smooth) with exactly 4 draggable points.

The user asked to **not** pursue either change and to leave circle behavior
exactly as it was before this investigation (smooth 64-segment circle,
mislabeled internally as `'polygon'` for select-mode flag purposes, all 64
vertices draggable). All circle-specific edits (the `segments` change, the
`flags.circle` block, and the `properties.mode` preservation used to
distinguish circles from polygons) were reverted. **Only the Bug 3 fix
(`'finish'`-event mode guard) was kept**, since it is unrelated to circle
rendering and independently fixes the duplicate-field/infinite-loop bug for
both polygons and circles.

If "circles should have fewer edit points" is revisited later, the two
options above (accept a low-poly circle shape, or build a custom N/E/S/W
resize-handle overlay bypassing TerraDraw's select-mode rendering for
circles) are the realistic paths; there is no simpler flag-only fix within
TerraDraw's current select-mode implementation.

## Debugging playbook for future TerraDraw issues in this codebase

Bug 3 (the actual duplicate-field/infinite-loop cause) was not something
reading the diff or the code in isolation would have found — `FieldDrawController`'s
own code looked reasonable in isolation; the bug only existed in the
*interaction* between our code and TerraDraw's internal event dispatch. The
following approach found it and is worth repeating for similar issues:

### 1. Reproduce against the running app, not just by reading code
This repo's dev stack (Docker backend + `yarn dev` frontend on `:5173`, proxied
through the gateway) was already running. Rather than reason purely from the
source, the Browser pane tools (`preview_start` / `navigate` / `computer` /
`read_console_messages`) were used to actually draw fields, drag vertices, and
watch what happened. Several theories that looked plausible from reading the
code alone (e.g. "an unstable `onCancel` callback is the *only* cause") turned
out to be real but incomplete — only confirmed/refuted by testing live.

### 2. Instrument TerraDraw's own events, not just your own handler
Our code's `'finish'` handler looked internally consistent. The actual proof
came from listening to **all** the relevant TerraDraw-level events at once and
logging enough context to see the full picture in one shot:

```ts
draw.on('select', (id) => console.log('[DEBUG select]', id));
draw.on('deselect', (id) => console.log('[DEBUG deselect]', id));
draw.on('finish', (id) => {
  console.log('[DEBUG finish]', 'mode=', draw.getMode(), 'id=', id);
  ...
});
```

The key extra piece of information was `draw.getMode()` captured **at the
moment `'finish'` fired**, not after our own code had already mutated the
mode. That single addition revealed that `'finish'` was firing while
`draw.getMode()` was already `'select'` — the tell that this wasn't a genuine
new-shape completion.

When adding this kind of instrumentation, log *before* your handler mutates
any state, and log enough (mode, feature id, properties) to reconstruct the
full event sequence afterwards — a single log line ("finish fired") is not
enough to distinguish "normal" from "self-triggered" firings.

### 3. Read the library's own type declarations and (if needed) minified source
`terra-draw` ships full `.d.ts` files under `node_modules/terra-draw/dist/`
even though the runtime bundle is minified. When behavior wasn't obvious from
usage alone:

- `terra-draw.d.ts` — confirmed the full public event map (`finish`, `change`,
  `select`, `deselect`) exists, which is what led to adding `select`/`deselect`
  logging in step 2.
- `modes/select/select.mode.d.ts` — showed the `ModeFlags` shape
  (`flags: { [mode: string]: ModeFlags }`, keyed **by mode name**, with
  `feature.coordinates.{draggable,midpoints,resizable,deletable}`), which is
  what led to realizing circles needed their own `flags.circle` entry instead
  of reusing `flags.polygon`.
- When the `.d.ts` files described *shape* but not *behavior*, `grep`-ing the
  minified `dist/terra-draw.module.js` for a stable identifier (e.g.
  `getSelectedFlags=function`, `selectionPoints.create(`) and reading the
  ~200 characters around each match was enough to confirm exact runtime
  behavior — e.g. that `selectionPoints.create()` (the "draw a dot at every
  vertex" behavior) runs whenever `flags.<mode>.feature.coordinates` exists
  *at all*, regardless of `draggable` vs `resizable`. This is how the circle
  "4 points" investigation was resolved (as a dead end) without having to
  trial-and-error every possible flag combination live in the browser.

### 4. Treat React effect dependency arrays as a prime suspect for "state resets itself"
Bug 2's symptom ("mode keeps resetting") is a classic signature of an
unstable prop identity feeding a `useEffect` dependency array. Whenever
something that should only run once on mount/transition appears to be
re-running unexpectedly:

- Find the `useEffect`/`useCallback`/`useMemo` responsible and list every
  dependency.
- For each dependency that's a function or object, check whether it's created
  inline in JSX (`onCancel={() => ...}`) — inline arrow functions/object
  literals get a new identity every render, which will make any effect that
  depends on them re-run every render.
- The fix is always the same shape: hoist the inline function into a
  `useCallback` with a correct (usually empty) dependency array, or otherwise
  memoize it.

### 5. Don't trust HMR to reflect your latest edit — reload when in doubt
Editing `FieldDrawController.tsx` mid-session sometimes left a **stale**
`TerraDraw` instance running with the old `TerraDrawSelectMode` config,
because `ensureDraw()` only constructs a new `TerraDraw` instance when
`drawRef.current` is `null`, and React Fast Refresh doesn't necessarily
remount a child component (and its refs) just because a file it's defined in
changed. If a fix "doesn't seem to have any effect" after an edit, do a full
page reload (not just wait for HMR) before concluding the fix is wrong.

### 6. Watch for logging/tooling artifacts vs. real duplicate execution
Console messages captured via the Browser pane's `read_console_messages`
consistently appeared **twice** for every single message in this
environment — including messages present since page load, before any of our
code ran. That is a tooling artifact, not evidence of double execution. To
tell real duplication (like Bug 3's loop) apart from this artifact, count
**application state**, not log lines — e.g. the "Save N fields" button label
or the number of pending-field rows in the side panel, which only change when
`setPendingFields` actually runs an extra time.

### 7. Automated drag/click gestures are unreliable for drag-heavy interactions
The Browser pane's `computer` tool's synthetic `left_click`/`left_click_drag`
frequently missed small TerraDraw vertex/midpoint hit-targets (resulting in a
map pan instead of a vertex drag) and struggled to reliably simulate
TerraDraw's circle tool (click-to-center, move, click-to-set-radius — which
needs a real intervening `mousemove`, not just two discrete clicks). When a
fix depends on a precise drag gesture, prefer having the actual user verify it
with their real mouse rather than spending many turns fighting synthetic
input precision.
