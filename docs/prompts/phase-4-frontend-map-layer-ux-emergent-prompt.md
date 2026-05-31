# Emergent Prompt — Phase 4 Frontend Map & Layer UX

Use this file as the copy/paste prompt for Emergent to build **Phase 4 — Frontend map and layer UX**
(Slice 4). It builds the first real product UI: a MapLibre map over Bangalore, a true-colour
Sentinel-2 overlay driven by API tile metadata, and an orbital-glass layer panel with source/date
selection, cloud usability, visibility, and opacity.

---

## Phase 4 analysis summary

### Where we are

- The BFF (Phase 3) is **live and validated** at `https://web-production-aaf7d.up.railway.app`
  behind the Caddy `web` gateway. The browser only ever talks to the gateway; `/api/*` and
  `/tiles/*` are same-origin.
- The frontend (`apps/frontend`) is still the **Slice 0 skeleton**: React 18 + Vite 5 +
  TypeScript, no MapLibre, no Tailwind, no shadcn yet. `App.tsx` only pings
  `/api/_skeleton/services` to prove the same-origin contract.
- `docs/design-system.md` is **finalized** ("Calm Instrument, Living Earth"). Phase 4 is the first
  slice that wires those tokens into the app.

### What Phase 4 must deliver (from `docs/mvp-execution-plan.md`)

- MapLibre map centered on Bangalore.
- Basemap source configured (no public OSM raster; operator-provided style URL).
- Satellite tile overlay from API-provided tile metadata.
- Layer panel with source/date selector, cloud indicator, visibility toggle, and opacity.
- Loading, empty, and error states.

### Exit criteria (do not declare done until all true)

- User can switch dates **without disturbing the basemap**.
- The **latest usable scene is selected by default**.
- Frontend has **no hard-coded COG/MinIO/STAC/TiTiler URLs** — only same-origin `/api/*` and the
  `tileUrlTemplate` returned by the API.

### Explicitly out of scope for Phase 4 (these are Phase 5)

- Terra Draw polygon draw/edit.
- GeoJSON import/export UI.
- Named plot save/list/delete.
- Index selector and the statistics/`IndexPanel` (NDVI/NDRE/NDMI/NDWI).
- Ingestion automation and any Wave 2 analytics/time-series.

Scaffold the layout so the right-side `IndexPanel` and the `PlotToolbar` have a home, but do **not**
implement their behavior.

### Live API contracts the frontend consumes (verified against production)

`GET /api/config`
```json
{
  "appName": "Akasha",
  "aoi": {
    "id": "bangalore",
    "name": "Bangalore",
    "center": [77.59, 12.97],
    "zoom": 11,
    "bounds": [77.4, 12.8, 77.8, 13.2]
  },
  "basemapStyleUrl": "",
  "maxPolygonAreaHa": 50,
  "maxPolygonVertices": 5000,
  "usablePixelThresholdPercent": 70,
  "supportedIndices": ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"],
  "defaultIndex": "NDVI"
}
```

`GET /api/sources`
```json
[
  {
    "id": "sentinel-2-l2a",
    "label": "Sentinel-2 L2A",
    "provider": "Copernicus",
    "supportedIndices": ["NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"]
  }
]
```

`GET /api/sources/{sourceId}/dates`
```json
[
  {
    "acquisitionDate": "2025-09-14",
    "datetime": "2025-09-14T05:06:49.024000Z",
    "usablePixelPercent": 82.85,
    "cloudMaskedPercent": 17.15,
    "coveragePercent": 100.0,
    "isLatestUsable": true,
    "metricsProvisional": true,
    "tileAvailable": true
  }
]
```

`GET /api/layers/default`
```json
{
  "sourceId": "sentinel-2-l2a",
  "acquisitionDate": "2025-09-14",
  "tileUrlTemplate": "/api/tiles/sentinel-2-l2a/2025-09-14/rgb/{z}/{x}/{y}.png",
  "bounds": [77.751, 11.647, 78.770, 12.650],
  "minzoom": 8,
  "maxzoom": 14,
  "attribution": "Copernicus Sentinel-2",
  "usablePixelPercent": 82.85,
  "metricsProvisional": true
}
```

Tiles are served same-origin: `GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png`.
The error shape for any failed call is `{ "error": { "code", "message", "details" } }`.

### Contract notes that drive the implementation

- The tile raster source URL is **always** the `tileUrlTemplate` from `/api/layers/default` (default
  scene) or composed as `/api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png` when the user
  picks a different date. Never construct COG/MinIO/STAC URLs.
- `basemapStyleUrl` in `/api/config` may be empty. Resolve the basemap style in this precedence:
  1. `config.basemapStyleUrl` if non-empty, else
  2. build-time `VITE_BASEMAP_STYLE_URL`, else
  3. a bundled **fallback style** (a plain ink/“no-basemap” background style defined locally) so the
     satellite overlay is still usable and the app never tries to reach a public CDN.
- `isLatestUsable: true` marks the default-selected date. If no date has it, fall back to the newest
  date whose `usablePixelPercent >= config.usablePixelThresholdPercent`; if none qualify, select the
  newest date and surface the marginal/empty state.
- Cloud usability chip mapping (from design system §2.3): `>=70% → success`, `40–70% → warning`,
  `<40% → destructive`, missing → `nodata`.

---

## Copy/paste prompt for Emergent

You are working in the Akasha repository. Implement **Phase 4 — Frontend map and layer UX (Slice 4)**
in `apps/frontend`. Build the real product map experience on top of the existing, live BFF. Do not
modify backend services, the gateway, or Railway config.

### Project context

Akasha is a Railway-first Sentinel-2 satellite imagery MVP for Indian agriculture. The browser talks
**only** to the public `web` gateway, which serves the built SPA and reverse-proxies same-origin
`/api/*` to the FastAPI BFF and `/tiles/*` to TiTiler. FastAPI, TiTiler, STAC, PostGIS, and MinIO are
private. The frontend must never reference MinIO, COG paths, STAC, TiTiler, database URLs, or any
private hostname. It consumes only same-origin `/api/*` routes and the `tileUrlTemplate` the API
returns.

Source-of-truth docs (read before coding):

- `docs/mvp-execution-plan.md` — Phase 4 deliverables and exit criteria.
- `docs/product-plan.md` — map browsing journeys, source/date selection, cloud usability.
- `docs/architecture-tech-stack.md` — frontend stack, component names, and the tile URL contract.
- `docs/design-system.md` — the **"Calm Instrument, Living Earth"** design system (authoritative for
  all colors, typography, tokens, motion, and component specs). Follow it exactly.
- `docs/engineering-dos-donts.md` — frontend guardrails.

### Current frontend state

- `apps/frontend` is a Vite + React 18 + TypeScript skeleton (Slice 0). `src/App.tsx` only calls
  `/api/_skeleton/services`. There is no map, Tailwind, or shadcn yet.
- `apps/frontend/vite.config.ts` already proxies `/api` and `/tiles` to `http://localhost:8000` in
  dev — keep this so local dev mirrors the same-origin gateway contract.
- `apps/frontend/.env.example` already declares `VITE_BASEMAP_STYLE_URL`.
- The production SPA is built by `infra/gateway/Dockerfile` (`yarn build` → Caddy serves `/srv`).
  Your build must keep `yarn build` working with no new required env beyond `VITE_*` placeholders.
- shadcn/ui components from an earlier scaffold live under `frontend/src/components/ui/` (note: the
  legacy `frontend/`, not `apps/frontend/`). You may copy the primitives you need (button, card,
  slider, switch, tooltip, badge, scroll-area, skeleton, separator) into `apps/frontend` and restyle
  them to the design tokens. Do not add a dependency on the legacy `frontend/` folder.

### Required dependencies to add

Add to `apps/frontend/package.json` (pin reasonable current versions, use yarn):

- `maplibre-gl` — map renderer.
- `@tanstack/react-query` — server state for the API calls.
- Tailwind CSS + PostCSS + Autoprefixer, `tailwindcss-animate`, `class-variance-authority`, `clsx`,
  `tailwind-merge`, `lucide-react` for the shadcn-style component layer.
- Self-hosted web fonts for **Space Grotesk**, **Inter**, **JetBrains Mono** (bundle via
  `@fontsource/*` packages or local files — no public CDN, per the deployment posture).

Do **not** add `terra-draw`, `@mapbox/mapbox-gl-draw`, charting, or index libraries — those are
Phase 5.

### Design system integration (must follow `docs/design-system.md`)

1. Create `apps/frontend/src/styles/globals.css` (or `index.css`) with the **exact CSS token set**
   from design system §2.6 (light + `.dark`), the orbital-glass recipe (§4), elevation/halo shadows,
   the contour motif, and motion tokens (§6). Default to **dark** (imagery reads best on ink).
2. Create `apps/frontend/tailwind.config.{ts,js}` extending the theme per design system §8 (colors,
   `fontFamily` display/sans/mono, radii, `boxShadow` e1/e2/e3). Wire `tailwindcss-animate`.
3. Typography: Space Grotesk = display/headings, Inter = UI/body, JetBrains Mono +
   `tabular-nums` = all numeric readouts (dates, lat/long, percentages).
4. Every floating panel uses the `.glass` recipe (`--shadow-e2` + `--ring-onmap` halo). Any text
   rendered directly on imagery carries a scrim or text-halo.
5. Saffron is the only brand accent (active state, focus ring, primary action). Generic GIS green is
   **data-only** and not used as UI chrome in this slice.
6. Respect `prefers-reduced-motion` and `prefers-color-scheme`. Use the "scan sweep" loading motif
   instead of generic spinners where practical.

### Required scope

Build a single map screen (`MapPage`) that fills the viewport with floating orbital-glass panels.

1. **Map (`MapPage` + `MapLayerManager`)**
   - Initialize MapLibre centered on `config.aoi.center` / `config.aoi.zoom` (Bangalore), constrained
     loosely to `config.aoi.bounds`.
   - Resolve the basemap style via the precedence rule: `config.basemapStyleUrl` →
     `VITE_BASEMAP_STYLE_URL` → bundled local fallback ink style (no public CDN, no public OSM
     raster).
   - Add the Sentinel-2 true-colour overlay as a raster source/layer using the active scene's tile
     URL template (default from `/api/layers/default`; recomposed when the user changes date). Apply
     `bounds`, `minzoom`, `maxzoom`, and `attribution` from the layer metadata.
   - **Changing the date must only swap/update the satellite raster layer — never touch or reload the
     basemap.** Crossfade old→new imagery per design system motion (§6); keep camera and basemap
     fixed.
   - Map controls cluster (zoom, compass, geolocate, scale bar, attribution) styled per design
     system §5.4, bottom-right; attribution bottom-left and muted.

2. **Layer panel (`LayerPanel`)** — left, orbital glass, collapsible to a pill.
   - **Source selector**: segmented control of `/api/sources` (Sentinel-2 default, active = saffron
     underline, not a fill). With one source it can render read-only but must be structured for more.
   - **Date selector**: scrollable list of `/api/sources/{sourceId}/dates`, newest first. Each row =
     `coord`-mono acquisition date + a **cloud usability chip** (§5.6, color per §2.3 mapping). The
     `isLatestUsable` row gets the small saffron dot. **Default selection = latest usable scene.**
     Rows where `tileAvailable === false` are visibly disabled.
   - **Visibility toggle**: pill switch (§5.5) controlling the satellite layer only; basemap
     visibility is independent.
   - **Opacity slider**: live `NN%` in mono; drag updates the raster layer opacity in real time with
     no transition while dragging.

3. **States**
   - Loading: skeleton rows + scan-sweep while config/sources/dates resolve.
   - Empty: "No usable optical scene in range" with the most recent attempted date and an `info`
     icon when no date qualifies.
   - Error: standard error handling for any `/api/*` failure — read `error.code`/`error.message`
     from the BFF error shape, show a calm retry affordance, never surface raw internals.

4. **Layout scaffolding (no behavior)**
   - Reserve anchored slots for `PlotToolbar` (top-left) and `IndexPanel` (right) as empty/disabled
     glass placeholders so Phase 5 can drop in. Do not implement their logic.

### Data layer

- Add a typed API client `apps/frontend/src/lib/api.ts` (or `apiClient.ts`) with functions:
  `getConfig()`, `getSources()`, `getDates(sourceId)`, `getDefaultLayer()`. All call same-origin
  `/api/*` with `fetch`, parse the typed payloads above, and throw a typed error carrying
  `error.code`/`error.message` on non-2xx.
- Wrap the app in a TanStack Query provider; use `useQuery` for config/sources/dates with sensible
  `staleTime`. Derive the selected date in component/store state, not by refetching.
- Define TypeScript types/interfaces for every payload (`AppConfig`, `Source`, `SceneDate`,
  `DefaultLayer`). No `any` on API boundaries.

### Files (suggested)

```
apps/frontend/
  tailwind.config.ts
  postcss.config.js
  src/
    main.tsx                      # mount + QueryClientProvider
    App.tsx                       # renders MapPage
    styles/globals.css            # design-system tokens + glass + motion
    lib/api.ts                    # typed BFF client
    lib/queryClient.ts            # TanStack Query client
    types/api.ts                  # AppConfig, Source, SceneDate, DefaultLayer
    map/basemap.ts                # style resolution + local fallback ink style
    pages/MapPage.tsx
    components/map/MapLayerManager.tsx   # MapLibre lifecycle + raster swap
    components/map/MapControls.tsx
    components/layers/LayerPanel.tsx
    components/layers/SourceSelector.tsx
    components/layers/DateList.tsx
    components/layers/CloudUsabilityChip.tsx
    components/layers/OpacitySlider.tsx
    components/layers/VisibilityToggle.tsx
    components/ui/                 # shadcn primitives restyled to tokens
```

### Environment variables

- `VITE_BASEMAP_STYLE_URL` (already in `.env.example`) — optional build-time basemap style override.
- Do not introduce any other required runtime env. No API base URL var — calls are same-origin
  `/api/*`. Update `apps/frontend/.env.example` if you add any new `VITE_*` placeholder.

### Guardrails (engineering dos-donts)

- Same-origin only: never `fetch` an absolute backend/COG/STAC/MinIO/TiTiler URL. Tile URLs come only
  from API metadata.
- No secrets or private hostnames in client code or bundles.
- Keep `yarn build` green and the `infra/gateway/Dockerfile` multi-stage build unaffected.
- Accessibility: keyboard-reachable controls, visible saffron focus ring, 44px touch targets,
  color + label/shape for usability (never color alone), respect reduced-motion.

### Validation / tests

- Add component tests (Vitest + Testing Library) for: cloud usability chip color mapping
  (`>=70/40–70/<40/none`), default-date selection (`isLatestUsable` → fallback to threshold →
  newest), and the API client error mapping.
- Add a small test or assertion proving date change updates only the raster layer source/url, not the
  basemap style.
- Provide a manual verification checklist in the final report.
- Run `yarn lint`, `yarn build`, and `yarn test` (add the `test` script if missing) and report
  results.

### Done criteria (must all pass)

- Map loads centered on Bangalore with the basemap resolved via the precedence rule (no public CDN
  dependency when none is configured).
- Sentinel-2 true-colour overlay renders from API tile metadata; the **latest usable scene is
  selected by default**.
- User can switch acquisition dates and **only the satellite layer changes — the basemap stays put**.
- Layer panel shows source/date selection, per-date cloud usability chips, visibility toggle, and a
  live opacity slider, all styled to `docs/design-system.md`.
- Loading, empty, and error states are implemented and calm.
- **No hard-coded COG/MinIO/STAC/TiTiler URLs anywhere** — verified by grep.
- `yarn lint`, `yarn build`, and `yarn test` succeed.

### Out of scope (Phase 5 — do not build)

- Terra Draw drawing/editing, GeoJSON import/export, named plot save/list/delete.
- Index selector and statistics/`IndexPanel` behavior (NDVI/NDRE/NDMI/NDWI).
- Ingestion automation, Wave 2 analytics/time-series.
- Auth/user accounts, new satellite sources, gateway/Railway changes.

### Final response expected from Emergent

After implementation, report:

1. Files added/changed.
2. Dependencies added (with versions) and why.
3. How the basemap style is resolved and what the local fallback is.
4. How date switching avoids disturbing the basemap (which MapLibre calls are used).
5. Tests added and the exact `yarn lint && yarn build && yarn test` output.
6. Confirmation grep shows no hard-coded backend/COG URLs.
7. Any remaining limitations or follow-ups for Phase 5.
```
