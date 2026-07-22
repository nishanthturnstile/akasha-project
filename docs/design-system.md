# Akasha by CIDSA Design System

This document is the canonical frontend design contract for Akasha. CIDSA is the visual brand;
Akasha remains the product and API name. The implementation lives in
`apps/frontend/src/styles/globals.css` and uses Tailwind CSS v4 with shadcn-compatible semantic
tokens.

## Principles

1. **Light first.** New users see the light theme. A saved light or dark choice is restored before
   the first paint.
2. **Semantic styling.** Components consume `background`, `foreground`, `card`, `primary`,
   `secondary`, `muted`, `accent`, `destructive`, `border`, `input`, and `ring`; pages do not embed
   brand hex colors.
3. **Brand and data stay separate.** CIDSA green communicates navigation and action. Scientific
   imagery palettes and index ramps continue to communicate measured data.
4. **One component language.** Inputs, buttons, cards, tabs, dialogs, sheets, badges, tooltips,
   loading states, and map chrome share the same geometry and interaction states.
5. **Accessible over imagery.** Floating map controls use the glass-card surface, an edge ring,
   and enough opacity to remain legible over bright or dark basemaps.

## Brand

| Token | Value | Use |
|---|---:|---|
| `cidsa-primary` | `#16a34a` | Primary actions, active navigation, focus, endorsement |
| `cidsa-primary-dark` | `#15803d` | Primary gradient and pressed states |
| `cidsa-secondary` | `#3b82f6` | Supporting information and brand illustration |
| `cidsa-accent` | `#0891b2` | Supporting emphasis and brand illustration |

The shared lockup reads **Akasha by CIDSA**. Use its `full`, `compact`, or `icon` variant rather
than rebuilding the satellite mark and wordmark in a screen. Until an official CIDSA logo asset is
provided, the existing satellite mark uses the CIDSA green-to-cyan treatment.

## Themes

The light theme uses white page/card surfaces, slate foreground text, slate-50 secondary surfaces,
slate-200 borders, and CIDSA green for primary and focus states. Dark mode is opt-in through the
`.dark` class and uses slate-950 page surfaces, slate-900 cards, light foreground text, and a
brighter green primary for contrast.

Application semantic extensions are required:

- `success`: completed, healthy, usable.
- `warning`: caution, partial availability, stale data.
- `destructive`: failure, deletion, unsafe state.
- `info`: neutral operational information.
- `nodata`: unknown, unavailable, or gated.

Never substitute raw Tailwind colors such as `amber-500`, `red-500`, or `emerald-500` for these
roles. Brand green and success green must still be accompanied by copy, an icon, or component shape
so meaning never depends on color alone.

## Typography and Geometry

- **Display and UI:** Plus Jakarta Sans, weights 400–800.
- **Body:** Inter, weights 400–600.
- **Numeric readouts:** Inter with tabular numerals.
- **Base radius:** 12px. Cards and popovers use 12–16px; primary and secondary buttons, switches,
  segmented tabs, and compact status chips use pill geometry.
- **Focus:** 2px semantic ring with 2px offset.
- **Touch:** interactive controls should reach 44px on touch layouts; dense desktop map controls may
  use 32–40px when a tooltip and full keyboard support are present.

## Components

- **Primary button:** green gradient, white label, modest green shadow, small hover lift, pressed
  reset. Use only for the principal action in a local surface.
- **Secondary button:** transparent surface with a neutral border; green-tinted border/background on
  hover.
- **Cards:** white or semantic dark card surface, subtle border, low elevation. Decorative gradients
  and glow are limited to auth, onboarding, empty states, and primary marketing-style calls to
  action.
- **Glass card:** high-opacity semantic panel, 20px blur, green edge ring, and medium elevation.
  Required for controls floating directly over a map.
- **Forms:** semantic input border, primary focus ring, destructive validation caption, and explicit
  disabled styling.
- **Loading:** green scan sweep with a static reduced-motion fallback.

## Motion

Use the shared `fade-in`, `slide-up`, `slide-in-right`, `panel-in`, `drawer-in`, `sheet-up`, `float`,
and `pulse-glow` tokens. Functional transitions are 140–360ms. Decorative float/glow motion is not
used in dense operational or map surfaces. `prefers-reduced-motion` disables nonessential motion
and smooth scrolling.

## Scientific and Map Exceptions

Canonical NDVI, NDMI, NDWI, MSAVI, SAR, false-color, and cloud/mask colors are data contracts and
must not be replaced with CIDSA brand colors. Runtime MapLibre paint colors must be centralized in
map helpers or constants. Direct text on imagery requires a scrim, halo, or glass-card backing.

## Verification

- Verify 390, 768, 1024, and 1440px layouts in light and dark themes.
- Cover loading, empty, success, warning, destructive, disabled, dialog, popover, and mobile menu
  states.
- Text contrast must meet WCAG AA: 4.5:1 for normal text and 3:1 for large text.
- Run frontend lint, tests, and production build after design-system changes.
