# Split Crop Map Design QA

**Comparison target**

- Source visual truth: `/home/nishanth/.codex/attachments/a62e72d8-7b26-4992-95c2-5b16489e93d5/Screenshot 2026-07-22 at 18.06.56.png`
- Browser-rendered implementation: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/02-two-sided-hover.png`
- Deployed route: `https://staging.gis.cidsaglobal.com/monitoring/field-analytics/field/:fieldId`
- State: authenticated Field Analytics; Split View active; left viewer on Sentinel-2 L2A / NDVI / 2026-05-12; right viewer on Sentinel-2 L2A / NDMI / 2026-03-03; one synchronized hover coordinate with both sample cards visible; Single View tooltip visible.
- Implementation viewport: 2048 × 1024 CSS px, device scale factor 1, light browser preference with the Akasha dark product theme.
- Pixel normalization: the source is 3496 × 1762 px and the implementation is 2048 × 1024 px. The full-view evidence normalizes both to 2048 × 1024 before placing them side by side. The source appears to be a high-density desktop capture; its original CSS viewport and density are not embedded in the PNG, so no false pixel-level typography claims are made.

**Evidence**

- Full-view combined comparison: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/05-reference-implementation-comparison.png`
- Focused controls/timeline comparison: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/06-focused-controls-comparison.png`. The source's bottom 3496 × 222 px and the implementation map region's bottom 1792 × 140 px are each normalized to 2048 × 240 to judge control grouping, density, and alignment without the Akasha analytics shell affecting the comparison.
- Single-view return: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/03-single-view-return.png`
- Restored split state: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/04-restored-split-state.png`
- Automated browser record: `/home/nishanth/.codex/visualizations/2026/07/22/019f8926-00f2-76e3-add8-9b0f29ba2c2e/split-redesign/audit-results.json`

**Findings**

- No actionable P0, P1, or P2 differences remain for the requested split-view behavior.
- [P3] A cold comparison sample settled in 1.964 seconds on the final staging run. Both markers and both `Reading value…` cards appear immediately, so interaction feedback is not blocked. A later performance pass could warm or cache sample-side raster/profile resolution.

**Required fidelity surfaces**

- Fonts and typography: Akasha keeps its existing Space Grotesk/Inter/JetBrains Mono hierarchy rather than copying the reference application's typeface. At the focused control scale, labels remain legible, compact, and consistently weighted; no truncation or wrapping obscures the active source, index, date, or mode.
- Spacing and layout rhythm: the two viewers are equal width with a one-pixel divider. Each pane owns one compact bottom toolbar and one compact timeline. Controls do not cross the pane boundary or overlap the date filmstrip at 2048 × 1024. The reference uses a full-canvas map, while Akasha intentionally retains its field header, analytics content, and product navigation around the map.
- Colors and visual tokens: the implementation uses Akasha's dark glass surfaces, orange focus/selection accent, semantic borders, and existing elevation tokens. This differs from the reference's near-black controls but preserves the same hierarchy and keeps text contrast readable.
- Image quality and assets: both panes use the real Esri imagery basemap and the deployed raster overlays; no placeholder maps, CSS-drawn assets, or fake imagery are present. Map labels and clipped field rasters remain sharp at the tested density.
- Copy and content: `Left`/`Right`, source, index, date, `Standard`/`Contrast`, mask controls, `Split View`, and `Single View` are concise and self-explanatory. Hover cards show the pane's independent index/date/value/category rather than ambiguous shared text.
- Icons and affordances: Lucide icons match the existing Akasha control family. The split action changes to a square Single View icon and exposes the `Single View` tooltip and accessible name in split mode.
- Responsiveness and accessibility: native labelled selects, labelled buttons, visible focus rings, `aria-pressed` state, and tooltip text are present. The existing under-768 px split gate is preserved to avoid an unusable narrow dual-map layout.

**Comparison history**

1. Pre-comparison deployed browser validation found two P2 issues: the legacy single-view NDVI tooltip duplicated the new left split sample card, and comparison categories were described as raster “bands.” The fix suppresses `CoordinateReadout` only while Split View is active and renders server-category wording with a `Class n` fallback. Unit coverage was added for both behaviors.
2. Post-fix combined pass used the full-view and focused evidence above. Both panes now have one hover card, one independent source/index/profile/mask control group, and one independent date filmstrip. No P0/P1/P2 findings remained.

**Primary interactions tested**

- Entered Split View and confirmed exactly two MapLibre canvases.
- Changed only the right timeline from 2026-05-12 to 2026-03-03; the left date stayed on 2026-05-12.
- Changed only the right vegetation index from NDVI to NDMI.
- Hovered one map coordinate and received independent HTTP 200 sample values in both panes.
- Verified the split icon exposes `Single View`, returned to one map, then re-entered Split View with the right-side index/date preserved.
- Checked post-auth console output: no application errors or page exceptions. Remaining output is headless WebGL performance noise and one non-blocking Esri style-image warning.

**Implementation checklist**

- [x] Separate per-pane source and vegetation-index selection.
- [x] Separate per-pane timeline and date state.
- [x] Synchronized marker with independent left/right hover values.
- [x] Compact per-pane render profile and mask controls.
- [x] Dynamic Split View / Single View icon, tooltip, and accessible label.
- [x] Split state retained after returning to single view and reopening split.
- [x] Duplicate single-view hover UI removed in split mode.
- [x] Staging deployment, automated browser validation, focused visual comparison, lint, tests, and production build.

**Follow-up polish**

- Consider server-provided semantic category labels in the comparison-sampling payload so every sample can show names such as `Peak vegetation`, even when overlay response headers do not include a legend label array.
- Track cold sample duration and the existing Esri style-image warning separately from functional split-view telemetry.

final result: passed
