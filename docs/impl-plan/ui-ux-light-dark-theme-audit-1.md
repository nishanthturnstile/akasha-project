---
goal: Map-screen UI/UX audit & remediation — Light + Dark theme parity, overlap fixes, responsiveness, accessibility
version: 1.0
date_created: 2026-06-04
last_updated: 2026-06-04
owner: Akasha Engineering
tags: frontend, ui, ux, accessibility, dark-mode, responsive, map, design-system
---

# Introduction

This plan captures a live UI/UX audit of the Akasha map screen (`/monitoring/field-analytics`)
performed in the integrated browser in **both Light and Dark themes** and across viewport widths
390 / 768 / 1024 / 1280 / 1440 px. It records each defect with severity, measured evidence, root
cause, and a proposed fix, then sequences the remediation. No code is changed until this plan is
approved.

Audit method: MapLibre map screen rendered live; element bounding boxes, computed colors, and grid
tracks were read with scripted `getBoundingClientRect` / `getComputedStyle` probes; screenshots were
captured per theme and per viewport; retained Akasha product workflows were used to sanity-check the
intended chrome placement.

## Summary of findings (by severity)

| ID | Severity | Title | Theme(s) | Widths affected |
|----|----------|-------|----------|-----------------|
| C1 | Critical | App shell layout collapses below 1024px (map crammed into 304px rail column) | Both | < 1024px |
| C2 | Critical | Bottom-left legend overlaps map-control buttons (hide-legend/fullscreen unreachable) | Both | All |
| H1 | High | Dark-mode glass overlays fail contrast over the (light) default basemap | Dark | All |
| M1 | Medium | On-map attribution unreadable on a light basemap; collides with map labels | Dark | All |
| M2 | Medium | Theme is not persisted; light→dark flash on first paint (FOUC) | Both | All |
| M3 | Medium | `mapViewContext` re-renders every consumer on any view change | Both | All |
| L1 | Low | Console flooded with HTTP 400s for NDVI tiles (data, not UI) | Both | All |
| L2 | Low | Right-side panels hidden between 1024–1280px with no fallback | Both | 1024–1280px |

## 1. Requirements & Constraints

- **REQ-001**: The app shell must render a single full-width content column below the `lg` (1024px) breakpoint; the right product rail only occupies a track at `lg+`.
- **REQ-002**: No two floating map-chrome elements (controls, legend, attribution, layer bar, panels, timeline) may overlap at any tested width (390/768/1024/1280/1440) in either theme.
- **REQ-003**: Text on glass overlays must meet WCAG AA (≥ 4.5:1 for body/caption, ≥ 3:1 for large text) in **both** themes, regardless of basemap luminance.
- **REQ-004**: The legend visibility toggle and all map-control buttons must be reachable (not occluded) in both themes and at all widths.
- **REQ-005**: User theme choice must persist across reloads and must apply before first paint (no light→dark flash).
- **REQ-006**: Preserve the Akasha design-system identity (Solar Amber primary, glass tokens, Space Grotesk/Inter) and the CLAUDE.md rule that true-colour is the default layer; do not restyle into a generic look.
- **SEC-001**: No change may introduce direct browser calls to MinIO/STAC/TiTiler or hard-coded tile/object URLs; same-origin `/api/*` + `/tiles/*` only.
- **CON-001**: Tailwind v4 + CSS custom-property theme tokens in `apps/frontend/src/styles/globals.css`; `:root` = light, `.dark` = dark. Keep this structure.
- **CON-002**: `gridTemplateColumns` is currently an inline style (dynamic `railWidth`), so Tailwind responsive variants cannot override it — the fix must move the responsive column logic out of the inline style.
- **GUD-001**: Prefer token-level fixes (one place) over per-component patches where a token drives many surfaces.
- **GUD-002**: Keep changes minimal and targeted; do not refactor unrelated components.
- **PAT-001**: Map-chrome stacking continues to use the `--z-*` tokens (`z-toolbar`, `z-panel`, `z-popover`).

## 2. Detailed findings

### C1 — App shell collapses below 1024px (Critical)
- **Evidence (measured):** `[data-testid="product-shell"]` computed `grid-template-columns` is `"86.4px 304px"` at 390px and `"464px 304px"` at 768px. The map (`shell-content`) renders at **width 304px** (the 19rem rail track) positioned at x=86 (390px) / x=464 (768px); grid row 2 is left empty. At 1024px it correctly becomes `"720px 304px"` single-row with the rail visible.
- **Root cause:** `AppShell.tsx` sets `style={{ gridTemplateColumns: 'minmax(0,1fr) {railWidth}' }}` **unconditionally**, and only `lg:grid-rows-1` is responsive. Below `lg` the two-column track persists while `grid-rows-[auto_minmax(0,1fr)]` adds a second row, so auto-placement drops the mobile `<header>` into col 1 and the map `<section>` into the narrow col 2.
- **Proposed fix:** Drive the columns responsively. Pass `railWidth` as a CSS variable and use Tailwind classes:
  - `style={{ ['--rail-w']: railWidth }}`
  - className: `grid-cols-1 lg:grid-cols-[minmax(0,1fr)_var(--rail-w)] grid-rows-[auto_minmax(0,1fr)] lg:grid-rows-1`
  - Mobile = one column (header row + content row); `lg+` = content + rail. Verify content spans full width at 360/390/768 and the rail returns at 1024.

### C2 — Bottom-left legend overlaps map controls (Critical)
- **Evidence (measured):** `[data-testid="map-controls"]` = 36×258 at (16,568..826); `[data-testid="map-legend"]` = 176×88 at (16,714..802). Overlap = **36×88px** at 1440 (and 36×87 at 1092). The legend paints over the bottom ~3 control buttons — *Find selected field*, *Hide legend*, *Enter full screen* — so only 4 of 7 buttons are clickable; the "Hide legend" button is fully occluded. The attribution row likewise overlaps the controls by 36×16px. Reproduces identically in Light and Dark.
- **Root cause:** In `MapPage.tsx` two absolutely-positioned containers share the **same anchor** `absolute bottom-[calc(var(--timeline-height)+1.125rem)] left-4 z-toolbar` — one wraps `<MapControls>`, the other wraps `<Legend>` + attribution. Equal `z-toolbar` + later DOM order makes the legend paint over the controls.
- **Proposed fix:** Merge the two bottom-left containers into **one** `flex flex-col items-start gap-2` anchored bottom-left, ordered `[Legend, MapControls, attribution]` so they stack with real layout (no overlap) at every width. Add a short-viewport guard so the legend hides under ~560px height if needed.

### H1 — Dark-mode overlays fail contrast on light basemap imagery (High)
- **Evidence (measured):** Glass panels compute `background: rgba(21,27,40,0.62)` with `blur(18px)`. Over light basemap imagery, the composited panel background is approximately `rgb(105,108,114)`. Resulting contrast: legend caption (`--muted-foreground` `rgb(143,156,174)`) is approximately **1.8:1**; body text (`rgb(229,235,240)`) is approximately **4.0:1** — both below AA 4.5:1. Affects legend, timeline, layer bar, field header, command palette, cloud-mask popover (all use `.glass`).
- **Root cause:** Dark `--panel-alpha: 0.62` was tuned for *dark satellite imagery*; over bright basemap imagery the map bleeds through and washes out foreground/muted text. `--on-map-ring-alpha: 0.1` also gives panels almost no edge against a light map.
- **Proposed fix (token-level, one place in `globals.css` `.dark`):**
  - `--panel-alpha`: `0.62 → ~0.86` (legible over any basemap, still subtly translucent).
  - `--muted-foreground`: lighten ~`215 16% 62% → 215 18% 70%`.
  - `--on-map-ring-alpha`: `0.1 → ~0.16` for panel-edge definition.
  - Re-measure caption + body contrast to confirm ≥ 4.5:1; spot-check Light theme stays ≥ 4.5:1 (nudge light `--panel-alpha` `0.72 → ~0.8` only if needed for dark imagery robustness).

### M1 — On-map attribution unreadable on light basemap (Medium)
- **Evidence:** Attribution computes `color: oklab(... /0.7)` (`text-foreground/70`) with **no** background (`rgba(0,0,0,0)`), rendered directly on the map with only an `on-map-text` shadow. In dark theme that can put light text over light basemap imagery, causing very low contrast and visual collision with basemap labels.
- **Root cause:** Credit line relies on a text-shadow halo that assumes dark imagery underneath.
- **Proposed fix:** Give the attribution a minimal glass backing chip (`rounded-sm`, `bg-[hsl(var(--panel)/0.55)]`, `px-1.5 py-0.5`, `backdrop-blur-sm`) that reads in both themes; keep it `pointer-events-none`. Overlap with controls is independently resolved by C2.

### M2 — Theme not persisted; first-paint flash (Medium)
- **Evidence:** `ThemeToggle` uses `useState<'dark'>('dark')` and applies the class only in a post-mount `useEffect`. `:root` defaults to **light**, so the first frame is light then snaps to dark (FOUC). There is no `localStorage`, so every reload discards the user's choice.
- **Root cause:** Theme is component-local, applied after hydration, and not persisted.
- **Proposed fix:** Persist theme to `localStorage` (`akasha.theme`), initialize state from the stored value (falling back to `prefers-color-scheme`/dark), and apply the class before paint (lazy initializer reading storage + applying class synchronously, or a tiny inline pre-hydration script in `index.html`).

### M3 — Context re-renders all consumers (Medium, optional)
- **Evidence:** `mapViewContext` memoizes its `value` on `[state]`, recreating every action callback whenever any field changes, so all `useMapView()` consumers (including those that only dispatch) re-render on every view change.
- **Root cause:** Single context carrying both state and (unstable) actions.
- **Proposed fix (optional):** Either `useCallback`/`useMemo` the action set independently of `state`, or split into a state context and a stable-dispatch context. Low user-visible impact; include only if time permits and keep it isolated.

### L1 — NDVI tile 400s flood the console (Low / likely out of UI scope)
- **Evidence:** Repeated `AJAXError: Bad Request (400): /api/tiles/sentinel-2-l2a/2026-04-27/NDVI/z/x/y.png` on pan/zoom.
- **Root cause:** Dev seed appears to lack NDVI tiles for that date (data/backend), not a frontend layout bug.
- **Proposed action:** Note only; out of scope for this UI/UX pass. Optionally suppress noisy retries later.

### L2 — Right panels hidden 1024–1280px (Low)
- **Evidence:** `FieldSceneStatusPanel` / `IndexPanel` are `hidden … xl:flex`; between `lg` and `xl` they vanish with no alternative surface.
- **Proposed action:** Confirm intended; optionally provide a compact placement at `lg`. Defer unless requested.

## 3. Implementation steps (after approval)

| Task | Files | Notes |
|------|-------|-------|
| T-1 (C1) | `apps/frontend/src/components/shell/AppShell.tsx` | Move columns to responsive Tailwind classes + `--rail-w` var; drop inline `gridTemplateColumns`. |
| T-2 (C2) | `apps/frontend/src/pages/MapPage.tsx` | Merge the two bottom-left containers into one ordered flex column; short-height guard for legend. |
| T-3 (H1) | `apps/frontend/src/styles/globals.css` | `.dark` token tweaks: `--panel-alpha`, `--muted-foreground`, `--on-map-ring-alpha`; verify Light unaffected. |
| T-4 (M1) | `apps/frontend/src/pages/MapPage.tsx` | Attribution glass backing chip. |
| T-5 (M2) | `apps/frontend/src/components/ThemeToggle.tsx` (+ maybe `index.html`) | Persist + pre-paint theme. |
| T-6 (M3, optional) | `apps/frontend/src/state/mapViewContext.tsx` | Stable actions / split context. |

## 4. Verification plan

- Re-measure C1 grid tracks at 360/390/768/1024/1280/1440: content must be full-width below `lg`, rail present at `lg+`.
- Re-measure C2 overlap pairs (controls↔legend, controls↔attribution): expect `false` (no overlap) at every width, both themes.
- Re-measure H1 contrast (legend caption + body, timeline, layer bar) in Dark: expect ≥ 4.5:1; confirm Light ≥ 4.5:1.
- Visual screenshot diff per theme at 1440 / 768 / 390; confirm Hide-legend + Fullscreen buttons clickable.
- Run `cd apps/frontend && yarn lint && yarn test && yarn build`; fix any regressions in affected component tests (`AppShell.test.tsx`, `MapControls.test.tsx`, `Legend.test.tsx`).

## 5. Out of scope

- Backend/data tile availability (L1), new features, pixel-parity audits, and any change to the satellite/index/mask domain rules.
