# Plan — Akasha Design System ("Calm Instrument, Living Earth")

## Goal
Transform `docs/design-system.md` from a generic shadcn `globals.css` token dump (Emerald-600 "agri-green") into a comprehensive, finalized design system for **Akasha**, a Sentinel-2 satellite imagery platform for Indian agriculture. It must be **simple, unique, highly engaging, and modern**, and must deliberately avoid standard/generic GIS aesthetics.

## Context (verified from repo)
- Stack: React + Vite + TypeScript, **MapLibre GL JS**, **Terra Draw**, **shadcn/ui + Tailwind CSS** (`docs/architecture-tech-stack.md`).
- Key components already named in architecture: `MapPage`, `LayerPanel`, `PlotToolbar`, `IndexPanel`, `MapLayerManager` (`architecture-tech-stack.md:61-68`).
- Product: map-first browsing of true-colour imagery; source/date selector; AOI cloud/usable-pixel indicator; opacity + visibility; draw/import/export plots; on-demand NDVI/NDRE/NDMI/NDWI statistics with legend (`product-plan.md`).
- Current `design-system.md` is literally a CSS token file → it will be rewritten as a true markdown design doc that still ships the implementable CSS + Tailwind tokens.

## Creative concept (approved direction)
**"Calm Instrument, Living Earth" — an Orbital Field Instrument.**
- The colorful satellite imagery is the hero; UI recedes into calm, frosted **"orbital glass"** panels floating at the screen edges, each carrying a **halo** so it stays readable over forest, cloud, soil, or water.
- Signature cartographic motif: subtle **contour-line / graticule texture** in panel headers, dividers, and loading ("scan sweep") states — unique DNA without clutter.
- **Brand accent = Saffron / Solar Amber** (dusk-sky, culturally resonant for Indian agriculture, high contrast over green/blue/brown imagery). Generic GIS green is **demoted to a data-only role** (NDVI legend ramp), never UI chrome.
- **Instrument typography:** Space Grotesk (display) + Inter (UI) + JetBrains Mono (coordinates, lat/long, index statistics — tabular figures).

## Execution steps (after approval)
1. Overwrite `docs/design-system.md` with the finalized content below (verbatim).
2. (Optional follow-up, not in this doc task) wire the tokens into `apps/frontend` Tailwind config + `globals.css` when the frontend slice is built (Phase 4).

## Deliverable — full content to write into `docs/design-system.md`

````markdown
# Akasha Design System

> **Theme: "Calm Instrument, Living Earth."**
> Akasha is a window to the sky. The vivid satellite imagery is the living subject; the interface is a calm,
> precise scientific instrument that frames it. UI recedes; the Earth advances.

---

## 1. Design philosophy

Akasha (आकाश — "sky / aether") shows farmers and agronomists their land from orbit. The product's emotional
promise is **clarity from above**: a quiet, trustworthy instrument that makes complex remote-sensing data feel
effortless.

### Principles

1. **Imagery is the hero.** Chrome is translucent and minimal. Never let UI compete with the map for attention.
2. **Floating instrument, not a dashboard.** Controls live in frosted **orbital-glass** panels that float at the
   edges and can be dismissed. No heavy toolbars, no gray ESRI/QGIS frames.
3. **Readable over anything.** Every floating surface carries a **halo** + scrim so text survives over bright
   cloud, dark forest, brown soil, or blue water.
4. **One brand voice, many data voices.** Saffron is the single brand accent. Scientific index ramps (NDVI, NDMI,
   …) are a *separate* palette so brand and data never get confused. **Green is data, not chrome.**
5. **Numbers are instruments.** Coordinates, dates, and index statistics use a monospace with tabular figures so
   values align and scan like a readout.
6. **Time is first-class.** Acquisition date and cloud usability are always visible and always legible.
7. **Motion communicates, never decorates.** Transitions explain change (a new date, a new layer, a computed
   stat) and respect reduced-motion.

### Anti-patterns (the "generic GIS" look we reject)
- Neon NDVI-green UI chrome, gray docked toolbars, dense icon walls.
- Opaque rectangular panels that box in the map.
- Mapbox/Leaflet default control chrome left unstyled.
- Pure-black "hacker" dark mode; flat #fff "office" light mode.

---

## 2. Color system

Colors are defined as HSL channels (shadcn convention: `H S% L%`) so they compose with Tailwind `hsl(var(--x) / a)`.

### 2.1 Brand — Saffron / Solar Amber
The dusk sky over a field. Used for primary actions, active state, focus, brand marks. Use sparingly — it should
feel like a highlight, not a fill color.

| Token | HSL | Hex ≈ | Use |
|---|---|---|---|
| `saffron-50`  | `36 100% 97%` | `#FFF8EE` | faint tint backgrounds |
| `saffron-100` | `35 100% 92%` | `#FFEACF` | hover tint |
| `saffron-200` | `34 97% 84%`  | `#FFD8A6` | selected tint |
| `saffron-300` | `33 96% 72%`  | `#FFBE73` | borders on tint |
| `saffron-400` | `33 95% 60%`  | `#FFA13D` | secondary accent |
| `saffron-500` | `32 95% 52%`  | `#F58A14` | **primary (light)** |
| `saffron-600` | `28 90% 46%`  | `#DF6B0E` | hover/pressed |
| `saffron-700` | `24 85% 39%`  | `#B7510E` | text on tint |
| `saffron-800` | `22 78% 32%`  | `#8E3D12` | deep |
| `saffron-900` | `21 70% 27%`  | `#6F3112` | deepest |

### 2.2 Neutral — Orbital Ink
Cool, slightly blue ink (the night sky) for light text and dark surfaces; warm haze paper for light surfaces so
the app never feels clinical.

| Role | Light | Dark |
|---|---|---|
| Page background | `40 30% 98%` (warm haze) | `222 38% 7%` (night ink) |
| Foreground text | `222 28% 12%` | `210 28% 92%` |
| Muted text | `220 12% 42%` | `215 16% 62%` |
| Hairline border | `40 14% 88%` | `220 20% 18%` |

### 2.3 Semantic + cloud-usability
Usability uses its own scale (independent of brand saffron) so a "marginal cloud" amber never reads as a button.

| Token | Light HSL | Dark HSL | Meaning |
|---|---|---|---|
| `success` | `152 55% 38%` | `152 50% 45%` | usable scene (≥70% usable px) |
| `warning` | `40 90% 48%` | `40 88% 55%` | marginal cloud (40–70%) |
| `destructive` | `4 84% 56%` | `4 70% 48%` | error / no usable data (<40%) |
| `info` | `205 80% 45%` | `200 75% 55%` | neutral info / tips |
| `nodata` | `220 9% 46%` | `220 10% 55%` | scene unavailable |

**Cloud usability chip mapping:** `≥70% → success`, `40–70% → warning`, `<40% → destructive`, `none → nodata`.

### 2.4 Map-overlay contrast tokens (the "orbital glass")
These keep floating UI legible over arbitrary imagery. Apply surface color with alpha + `backdrop-blur`.

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `--panel` | `40 33% 99%` | `222 30% 12%` | glass surface base color |
| `--panel-alpha` | `0.72` | `0.62` | surface fill opacity |
| `--panel-blur` | `16px` | `18px` | backdrop blur radius |
| `--on-map-ring` | `0 0% 100% / .55` | `0 0% 100% / .10` | hairline that lifts glass off imagery |
| `--halo` | `222 30% 10% / .18` | `0 0% 0% / .45` | soft drop shadow color |
| `--scrim-from` | `222 30% 8% / 0` | `222 40% 4% / 0` | text-over-imagery gradient start |
| `--scrim-to` | `222 30% 8% / .55` | `222 40% 4% / .70` | gradient end (behind labels) |

> **Rule:** any text rendered *directly on imagery* (map labels, plot names, scale bar) must sit on a scrim or
> carry a 1px text-halo (`text-shadow: 0 0 2px hsl(var(--halo))`). Glass panels handle this automatically.

### 2.5 Scientific index ramps (data only — never UI chrome)
Continuous legends for index overlays/legends. Provide as CSS gradients; values map to the stated domain.

| Index | Domain | Stops (low → high) |
|---|---|---|
| **NDVI** (vegetation) | −0.2 … 0.9 | `#6E4B2A → #C9A227 → #E9DA67 → #9CCB5B → #4FA02C → #1F6B2E` |
| **NDRE** (chlorophyll) | −0.1 … 0.8 | `#4B3A2A → #B8902F → #E0C957 → #7FB46A → #2E8B57` |
| **NDMI** (moisture) | −0.5 … 0.6 | `#8C5A2B → #D9C18A → #F2F2F0 → #6FC3C9 → #1C6FA8` |
| **NDWI** (water) | −0.3 … 0.8 | `#F4F1E9 → #BFE3E6 → #5FB4D6 → #2A6FB0 → #123C73` |

All ramps are colour-blind checked for monotonic lightness; always pair the ramp with numeric min/max labels.

### 2.6 Token reference (CSS)

```css
@layer base {
  :root {
    /* Surfaces — warm haze paper */
    --background: 40 30% 98%;
    --foreground: 222 28% 12%;
    --card: 40 33% 99%;
    --card-foreground: 222 28% 12%;
    --popover: 40 33% 99%;
    --popover-foreground: 222 28% 12%;

    /* Brand — Solar Amber / Saffron */
    --primary: 32 95% 52%;
    --primary-foreground: 24 75% 12%;

    --secondary: 40 16% 93%;
    --secondary-foreground: 222 25% 18%;
    --muted: 40 16% 94%;
    --muted-foreground: 220 12% 42%;
    --accent: 32 92% 94%;
    --accent-foreground: 24 70% 24%;

    /* Semantic */
    --success: 152 55% 38%;
    --warning: 40 90% 48%;
    --info: 205 80% 45%;
    --destructive: 4 84% 56%;
    --destructive-foreground: 40 33% 99%;
    --nodata: 220 9% 46%;

    --border: 40 14% 88%;
    --input: 40 14% 88%;
    --ring: 32 95% 52%;
    --radius: 0.75rem;

    /* Orbital glass / map overlay */
    --panel: 40 33% 99%;
    --panel-alpha: 0.72;
    --panel-blur: 16px;
    --on-map-ring: 0 0% 100%;
    --on-map-ring-alpha: 0.55;
    --halo: 222 30% 10%;
    --halo-alpha: 0.18;
  }

  .dark {
    --background: 222 38% 7%;
    --foreground: 210 28% 92%;
    --card: 222 32% 10%;
    --card-foreground: 210 28% 92%;
    --popover: 222 32% 10%;
    --popover-foreground: 210 28% 92%;

    --primary: 33 96% 56%;
    --primary-foreground: 24 80% 8%;

    --secondary: 220 24% 16%;
    --secondary-foreground: 210 28% 92%;
    --muted: 220 22% 15%;
    --muted-foreground: 215 16% 62%;
    --accent: 30 55% 18%;
    --accent-foreground: 33 90% 75%;

    --success: 152 50% 45%;
    --warning: 40 88% 55%;
    --info: 200 75% 55%;
    --destructive: 4 70% 48%;
    --destructive-foreground: 210 30% 96%;
    --nodata: 220 10% 55%;

    --border: 220 20% 18%;
    --input: 220 20% 18%;
    --ring: 33 96% 56%;

    --panel: 222 30% 12%;
    --panel-alpha: 0.62;
    --panel-blur: 18px;
    --on-map-ring: 0 0% 100%;
    --on-map-ring-alpha: 0.10;
    --halo: 0 0% 0%;
    --halo-alpha: 0.45;
  }
}
```

---

## 3. Typography

Three voices: a characterful grotesk for identity, a workhorse sans for UI, a mono for instrument readouts.

| Role | Family | Notes |
|---|---|---|
| Display / headings | **Space Grotesk** | geometric grotesk, slight character; tighten tracking |
| UI / body | **Inter** | optical sizing, excellent at 12–14px |
| Numeric / coordinates | **JetBrains Mono** | `font-variant-numeric: tabular-nums`; lat/long, dates, stats |

```css
--font-display: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
--font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
--font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", monospace;
```

### Type scale

| Token | Size / line-height | Tracking | Family | Use |
|---|---|---|---|---|
| `display-lg` | 36 / 40 | −0.02em | Display | hero / empty states |
| `display` | 28 / 34 | −0.02em | Display | panel section title |
| `h1` | 22 / 28 | −0.015em | Display | screen title |
| `h2` | 18 / 24 | −0.01em | Display | card title |
| `h3` | 16 / 22 | −0.005em | Sans 600 | sub-section |
| `body-lg` | 16 / 26 | 0 | Sans | long copy |
| `body` | 14 / 20 | 0 | Sans | **UI default** |
| `label` | 13 / 16 | 0.005em | Sans 500 | controls, chips |
| `caption` | 12 / 16 | 0.01em | Sans | helper / meta |
| `stat` | 28 / 32 | −0.01em | Mono, tabular | big index value |
| `stat-sm` | 16 / 20 | 0 | Mono, tabular | min/max/stddev |
| `coord` | 12 / 16 | 0 | Mono, tabular | lat/long, dates |

### Map-readability rules
- **Minimum on-map text:** 12px Inter 500 with halo; never below 11px.
- Use **mono + tabular-nums** for all numeric readouts so digits align across rows.
- Avoid pure black/white on imagery — use `foreground` on scrim, not raw `#000`/`#fff`.
- Truncate plot names to one line with tooltip on overflow.

---

## 4. Foundations

### Spacing — 4px base
`2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48`. Panel padding **16**, control gap **8**, section gap **12**.

### Radius
| Token | px | Use |
|---|---|---|
| `radius-sm` | 6 | chips, inputs |
| `radius-md` | 10 | buttons, controls |
| `radius-lg` | 14 | floating panels / cards |
| `radius-pill` | 999 | toggles, badges, search bar |

### Elevation (designed to read on imagery)
```css
--shadow-e1: 0 1px 2px hsl(var(--halo) / var(--halo-alpha));               /* map controls */
--shadow-e2: 0 8px 28px -6px hsl(var(--halo) / calc(var(--halo-alpha) + .08)),
             0 2px 6px hsl(var(--halo) / var(--halo-alpha));               /* floating panel */
--shadow-e3: 0 16px 48px -8px hsl(var(--halo) / calc(var(--halo-alpha) + .14));/* popover */
--ring-onmap: inset 0 0 0 1px hsl(var(--on-map-ring) / var(--on-map-ring-alpha));
```
Every floating glass surface = `--shadow-e2` **+** `--ring-onmap` (the halo that lifts it off the imagery).

### Orbital-glass surface recipe
```css
.glass {
  background: hsl(var(--panel) / var(--panel-alpha));
  backdrop-filter: blur(var(--panel-blur)) saturate(1.1);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-e2), var(--ring-onmap);
}
```

### Signature motif — contour lines
A faint topographic line texture for panel headers, dividers, and loading states. Keep ≤ 6% opacity so it's felt,
not seen.
```css
--contour: repeating-radial-gradient(
  circle at 30% 120%, transparent 0 14px,
  hsl(var(--foreground) / 0.05) 14px 15px);
```

### Iconography
Lucide, 1.75px stroke, 20px default (16px dense, 24px primary map controls). Rounded line caps to match the soft
radii. Never fill icons except active toggles.

### Layout — floating instrument
- The map fills the viewport (`MapPage`). Panels float above it; nothing docks the map into a frame.
- **Anchors:** search top-center; `PlotToolbar` top-left; `LayerPanel` left; `IndexPanel` right; map controls
  bottom-right; date scrubber bottom-center; attribution bottom-left (muted).
- Panels are collapsible to a single glass pill so the user can clear the view.
- Mobile: panels become bottom sheets; controls collapse into one cluster.

---

## 5. Components

Each spec lists anatomy, key tokens, states, and behavior.

### 5.1 Search bar (geocoder / coordinate jump)
- **Anatomy:** glass pill, leading search icon, input, trailing `⌘K` hint; results dropdown (`--shadow-e3`) with
  place name (Inter 500) + `coord` mono lat/long; recent searches when empty.
- **Behavior:** debounced 250ms; accepts `lat, lng`; Enter flies camera to result; Esc clears/closes.
- **States:** focus → saffron `ring`; loading → contour scan-sweep in trailing slot; error → caption in
  `destructive`.
- **Motion:** dropdown `fade + slide-down 6px` over `base` with `decelerate` easing; row hover tint `accent`.

### 5.2 Layer panel (`LayerPanel`)
- **Source row:** segmented control of sources (Sentinel-2 default). Active = saffron underline, not a fill.
- **Date selector:** scrollable list of acquisition dates; each row shows `coord`-mono date + a **cloud usability
  chip** (see 5.6); "latest usable" row gets a small saffron dot. Default selection = latest usable (≥70%).
- **Visibility toggle:** custom pill switch (5.5). **Opacity slider:** track shows live `NN%` in mono; dragging
  updates the map layer in real time.
- **Rules:** basemap visibility is independent from the satellite layer; changing date never disturbs the basemap.
- **Empty/error:** "No usable optical scene in range" with `info` icon and the most recent attempted date.

### 5.3 Information card (`IndexPanel` statistics)
- **Header:** index name (h2) + selected date (`coord`) + plot name; index switcher chips (NDVI/NDRE/NDMI/NDWI),
  active chip = saffron.
- **Hero stat:** **mean** as `stat` mono with count-up animation; under it the legend ramp (2.5) with min/max
  endpoints labeled.
- **Readout grid:** `stat-sm` mono rows for min, max, mean, stddev — right-aligned, tabular so they form a column.
- **Quality footer:** `valid-pixel %` and `cloud-masked %` as inline meters; if cloud-masked is high, show a
  `warning` note. No-data → `destructive` empty state with retry.
- **Request lifecycle:** idle → "Select a plot to analyze"; loading → skeleton rows + scan-sweep (3–5s budget);
  done → count-up reveal.

### 5.4 Map controls cluster
- **Members:** zoom +/−, compass (rotates with bearing, click to reset north), geolocate, basemap/style switch,
  scale bar. Grouped as a vertical glass capsule bottom-right (`--shadow-e1` per button, shared `ring-onmap`).
- **Scale bar + compass** render directly on imagery → carry text-halo.
- **States:** hover lifts button bg to `accent`; active/pressed = saffron tint; disabled at 40% opacity.

### 5.5 Toggle / switch
- Pill track; off = `muted`, on = saffron. Knob morphs (scale 0.9→1) on toggle; a faint check fades in when on.
- Focus = saffron ring; 44px min touch target on mobile.

### 5.6 Cloud usability chip
- Small pill: status dot + `NN% usable` in `label`. Color from §2.3 mapping. Tooltip explains usable-pixel
  threshold (70%). This is the most repeated "time-is-first-class" signal — keep it crisp.

### 5.7 Plot toolbar (`PlotToolbar`, Terra Draw)
- Glass capsule top-left: Draw, Edit, Import GeoJSON, Export GeoJSON, Delete. Active tool = saffron filled icon.
- **Draw affordances:** crosshair cursor; vertices are 8px saffron dots with white ring; the closing vertex
  pulses; live area readout (`coord` mono, ha) follows the cursor and turns `destructive` past the 50 ha limit.
- Save dialog: name input + plot color swatch (from a curated, non-saffron set so plots never read as brand).

### 5.8 Date scrubber (timeline)
- Bottom-center glass rail of acquisition dates; tick height encodes usability (taller = more usable);
  selected tick saffron. Dragging crossfades the imagery (5.9). Optional on small screens (falls back to 5.2 list).

### 5.9 Buttons, chips, inputs, tooltip, toast
- **Button variants:** `primary` (saffron fill, dark text), `secondary` (glass/`secondary`), `ghost`, `outline`,
  `destructive`. Height 36 (sm 30, lg 44), `radius-md`, label `label` style.
- **Inputs:** `input` border, focus saffron ring, error `destructive` border + caption.
- **Tooltip:** ink popover, `caption`, 8px offset, 120ms delay.
- **Toast:** bottom-left glass, status stripe (success/warning/info/destructive), auto-dismiss 5s.

---

## 6. Motion & micro-interactions

Motion explains state change and reinforces the "instrument" feel. It is always interruptible and always honors
`prefers-reduced-motion`.

### Motion tokens
```css
--ease-standard: cubic-bezier(0.2, 0, 0, 1);
--ease-decelerate: cubic-bezier(0.05, 0.7, 0.1, 1);   /* entrances */
--ease-accelerate: cubic-bezier(0.3, 0.0, 0.8, 0.15); /* exits */
--ease-emphasis: cubic-bezier(0.2, 0, 0, 1.1);        /* subtle overshoot */

--dur-instant: 80ms;
--dur-fast: 140ms;
--dur-base: 220ms;
--dur-slow: 360ms;
--dur-deliberate: 540ms;
```

### Signature interactions
| Interaction | Behavior |
|---|---|
| **Panel enter/exit** | enter: `opacity 0→1` + `translate 8px→0` + `scale .98→1` @ `base`/`decelerate`; exit reverse @ `fast`/`accelerate`. |
| **Imagery date change** | old layer crossfades to new over `slow`; basemap untouched; usability chip updates last. |
| **Opacity drag** | live, no transition while dragging; mono `%` updates each frame. |
| **Toggle** | knob slides @ `fast`, scale-morph + check fade-in @ `instant`. |
| **Loading ("scan sweep")** | a faint saffron contour line sweeps across the skeleton/panel — replaces generic spinners. |
| **Stat reveal** | mean **counts up** from 0 over `deliberate` with `ease-decelerate`; ramp marker glides to value. |
| **Draw vertex** | drop @ `instant` scale pop; closing vertex pulses once; area readout color-shifts on limit. |
| **Hover** | controls lift bg to `accent` over `fast`; focus shows saffron ring instantly. |
| **Camera fly-to** | MapLibre `flyTo`, ~`deliberate`–800ms, ease-decelerate; panels stay put. |

### Reduced motion
With `prefers-reduced-motion: reduce`: drop transforms/scale/parallax, keep `opacity` crossfades ≤ `fast`,
disable count-up (show final value), replace scan-sweep with a static contour shimmer.

---

## 7. Accessibility & quality bar
- Contrast: body text ≥ 4.5:1 against its surface (glass alpha accounted for); on-map text always on scrim/halo.
- Saffron-on-imagery never used for required text — only marks/controls that also have shape/icon.
- Never encode meaning by color alone: usability chips pair color + label; index ramps pair color + numbers.
- All controls keyboard-reachable; visible saffron focus ring; 44px min touch targets on mobile.
- Respect `prefers-reduced-motion` and `prefers-color-scheme` (default dark, since imagery pops on ink).

---

## 8. Implementation notes (Tailwind)
Akasha uses Tailwind CSS v4 in the canonical `apps/frontend` SPA. Define theme utilities with
CSS-first `@theme` variables in `apps/frontend/src/styles/globals.css` instead of a
JavaScript/TypeScript `tailwind.config` file.

```css
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

@theme inline {
  --color-background: hsl(var(--background));
  --color-foreground: hsl(var(--foreground));
  --color-primary: hsl(var(--primary));
  --color-primary-foreground: hsl(var(--primary-foreground));
  --color-success: hsl(var(--success));
  --color-warning: hsl(var(--warning));
  --color-info: hsl(var(--info));
  --color-destructive: hsl(var(--destructive));
  --color-panel: hsl(var(--panel));
  --color-border: hsl(var(--border));

  --font-display: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", monospace;

  --radius-lg: var(--radius);
  --radius-md: calc(var(--radius) - 4px);
  --radius-sm: calc(var(--radius) - 8px);
  --shadow-e1: 0 1px 2px hsl(var(--halo) / var(--halo-alpha));
  --shadow-e2: 0 8px 28px -6px hsl(var(--halo) / calc(var(--halo-alpha) + 0.08)),
    0 2px 6px hsl(var(--halo) / var(--halo-alpha));
  --shadow-e3: 0 16px 48px -8px hsl(var(--halo) / calc(var(--halo-alpha) + 0.14));
}
```

```css
@layer base {
  * { @apply border-border; }
  body { @apply bg-background text-foreground font-sans antialiased; }
  h1,h2,h3 { @apply font-display; }
}
```

---

*Akasha — clarity from above. Keep the instrument calm; let the Earth speak.*
````

## Notes / open items
- Index ramp hex stops are tuned for monotonic lightness and colour-blind safety; confirm against the actual
  TiTiler/legend output during Phase 5 and adjust domains if the data team uses different min/max.
- Dark mode is treated as the default surface (imagery reads best on ink); light "haze" mode is fully specified
  as the alternate.
- Web fonts (Space Grotesk, Inter, JetBrains Mono) must be self-hosted/bundled in the frontend per the
  "no public CDN for production assets" posture implied by the deployment docs.
