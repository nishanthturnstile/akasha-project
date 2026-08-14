# Timeline History Design QA

**Comparison target**

- Source visual truth: `/home/akashaadmin/.codex/attachments/303db451-a046-4a85-aede-3166385820db/Screenshot 2026-08-14 at 14.43.17.png`
- Browser-rendered implementation screenshot: unavailable because the Codex in-app Browser tool was not exposed in this task.
- Local route: `http://127.0.0.1:15173/monitoring/field-analytics/field/8428c37b-f37c-4e56-9713-665e673c4bf9?source=sentinel-2-l2a&mask=111`
- Intended state: authenticated Sentinel-2 field timeline, four-month default window, then rolling 365-day history after selecting `Show historical images`.
- Source pixels: 2374 x 226 RGBA. Implementation pixels/CSS viewport/device density: unavailable, so no density normalization was possible.

**Evidence**

- Full-view combined comparison: unavailable.
- Focused timeline comparison: unavailable.
- Automated interaction evidence: `TimelineBar.test.tsx` and `MapPage.test.tsx` verify the history action, 122-to-365-day refetch, cloudy-date retention, next-image label, and absence of playback/speed/latest controls.
- Live server evidence: the authenticated local UI requested `lookbackDays=122` successfully after deployment; the live OpenAPI contract reports a maximum of 365.

**Findings**

- Visual comparison is blocked because no browser-rendered implementation capture can be produced with the tools exposed in this task.
- No functional P0/P1/P2 findings remain in automated validation.

**Required fidelity surfaces**

- Fonts and typography: not independently screen-verified; implementation reuses Akasha's existing timeline typography.
- Spacing and layout rhythm: not independently screen-verified; the history action is placed before the horizontal filmstrip and the right side retains only the next-image status.
- Colors and visual tokens: implementation uses existing Akasha button, glass, border, primary, and muted tokens.
- Image quality and asset fidelity: no new raster assets are required; the existing Lucide icon system is reused.
- Copy and content: covered by tests for `Show historical images` and `Next image`.

**Primary interactions tested**

- Default selected-field query uses a 122-day four-month window.
- Selecting `Show historical images` refetches with a 365-day window and hides the action.
- Cloud-rejected acquisitions remain visible and non-selectable.
- Playback, speed, and jump-to-latest controls are absent.
- Next-image date remains visible when the backend provides a future expected pass.

**Implementation checklist**

- [x] Four-month default query.
- [x] Rolling 365-day history expansion.
- [x] Backend 365-day ceiling and default clamp.
- [x] Cloudy acquisition retention.
- [x] Playback/speed/latest removal.
- [x] Next-image date retained.
- [x] Unit, integration, lint, and production-build validation.
- [ ] Browser screenshot comparison at the source state and viewport.

final result: blocked
