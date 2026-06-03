---
goal: EOSDA Crop Monitoring Functional-Parity Acceptance Matrix
version: 1.0
date_created: 2026-06-03
last_updated: 2026-06-03
owner: Akasha Engineering
tags: eos, crop-monitoring, acceptance-matrix, parity, checklist, provider-adapter
---

# EOS Parity Acceptance Matrix

This is the executable checklist for the EOSDA Crop Monitoring functional-parity effort. It
converts the findings in [`eos-crop-monitoring-replication-research.md`](./eos-crop-monitoring-replication-research.md)
into one row per EOS module, classifies how Akasha will deliver each module, and defines the exact
**first parity demo** slice and its non-goals. It is the shared scope reference for
[`impl-plan/feature-eos-crop-monitoring-parity-1.md`](./impl-plan/feature-eos-crop-monitoring-parity-1.md)
(Phase 0, GOAL-000).

## How to read this document

- **Architecture is fixed.** The browser calls only Akasha same-origin `/api/*` and tile/download
  routes. EOSDA API Connect is a **temporary trial provider** reached only through the FastAPI BFF /
  provider-adapter layer, and must be replaceable later by Akasha-native STAC/COG/weather/zoning
  services. The default map layer stays true-colour; NDVI/any index is never the default.
- **Provider strategy** classifies every module as exactly one of:
  - `reuse-existing-akasha` — already shipped/native; use as-is.
  - `wire-existing-backend` — backend exists; only frontend wiring/plumbing is missing.
  - `eos-backed-trial` — delivered via the EOS adapter behind the BFF for the trial, with a documented
    Akasha-native replacement direction.
  - `akasha-native-first-party` — built natively in Akasha (BFF/raster/frontend), not EOS-backed.
  - `defer` — out of scope until a later phase.
- **First-demo required** marks the modules in the first parity demo slice (TASK-002 / GUD-001).
- **Acceptance check** is a concrete, verifiable pass condition. `eos-backed-trial` checks must pass
  with **no real EOS key** by surfacing a `provider-unconfigured` status (PAT-003).

## Acceptance matrix

| Module | EOS capability | Akasha status | Implementation owner | Provider strategy | First-demo required | Acceptance check | Dependencies |
|--------|----------------|---------------|----------------------|-------------------|---------------------|------------------|--------------|
| 1. Field management | Create/edit/list/import/export fields; groups, seasons, crop/variety/status | partial (backend CRUD/import/export in `apps/api/app/plots.py`; frontend disabled, CON-002/004/005/006) | BFF + frontend + schema | wire-existing-backend | Yes | Draw or import a GeoJSON field; server validates geometry and computes area (REQ-008); field appears in list and on map | Phase 1 (TASK-005..016) |
| 2. Scene / date timeline | Available scenes per field: date, cloud %, sensor, availability | partial (`/api/sources`, `/api/sources/{id}/dates` exist source-wide, REQ-006; field-AOI-aware filtering not yet wired) | BFF + frontend | wire-existing-backend | Yes | Selecting a field lists scene dates with cloud % filtered to the field AOI | Phase 4 (depends 1) |
| 3. True-colour map tiles | Display scene true-colour (B04/B03/B02) | exists (`/api/tiles/...`, `/api/layers/default`, REQ-007) | BFF + frontend | reuse-existing-akasha | Yes | Selected field renders true-colour tiles as the default layer for a chosen date | Phase 4 |
| 4. Vegetation index layers | NDVI/NDRE/NDMI/MSAVI/RECI + false-colour overlays | partial (NDVI/NDRE/NDMI/NDWI native; MSAVI/RECI missing, FILE-021, REQ-012) | raster (`indices.py`) + BFF + frontend | akasha-native-first-party | Yes (NDVI) | Switch from true-colour to an NDVI overlay for the selected field/date; index never becomes default (REQ-007) | Phase 4/5 |
| 5. Index image download / export | Download index image (PNG/TIFF) for AOI | none | BFF/TiTiler export | akasha-native-first-party | Yes | Export one analytics/index result server-side; no provider-signed URL leaked (SEC-003) | Phase 6 |
| 6. Field analytics trend + statistics | Time-series index chart; min/max/avg/std; cloud warnings | partial (single-date stats in `apps/api/app/product.py`, CON-007) | BFF (raster stats) + frontend | akasha-native-first-party | Yes | NDVI trend chart over scene dates with min/max/avg/std and cloud-quality warning per point (REQ-013) | Phase 5 (depends 1,4) |
| 7. Classification area | Area per index-threshold class (`cl_stats`) | none | BFF (thresholded raster area) | akasha-native-first-party | No | Given an index + thresholds, return area per class for the field | Phase 5 |
| 8. Cloud masking & data quality | Cloud %, cloud-mask tile, masked statistics, UI warnings/toggles | partial (SCL mask + masked-pixel math exist in raster engine, REQ-013; UI exposure/toggles not yet wired) | raster + frontend | wire-existing-backend | Yes | Every scene/statistics result exposes cloud % and masked-pixel fields to the UI | Phase 6 |
| 9. Risk map & alerts | NDVI delta (change detection) + weather stress rules | none | BFF + provider | defer | No | — (Phase 11) | Phase 11 |
| 10. Weather forecast | 14-day field forecast | implemented (`/api/fields/{plot_id}/weather/forecast` + `WeatherForecastPage`) | provider-adapter (`WeatherProvider`) + BFF + frontend | eos-backed-trial | Yes | Forecast cards/timeline load through the BFF weather route; with no EOS key, the route returns a sanitized provider-unavailable error; native IMD/GFS/Open-Meteo path remains the replacement direction (REQ-014) | Phase 7 |
| 11. Weather historical | Historical/accumulated weather | implemented (`/api/fields/{plot_id}/weather/history` + `WeatherAnalyticsPage`) | provider-adapter + BFF + frontend | eos-backed-trial | Yes | Historical/accumulated weather charts load through normalized `WeatherProvider` series; provider-unavailable and rate-limit states are sanitized | Phase 7 |
| 12. Soil moisture | Surface/root-zone soil moisture (`soilmoisture`) | optional unsupported response implemented (`/api/fields/{plot_id}/weather/soil-moisture`) | provider-adapter + BFF | defer | No | Route returns `available=false` with a clear unavailable reason until EOS trial/native SMAP support exists | Phase 11 |
| 13. Vegetation VRA zoning map | N vegetation zones from current scene/index | none | provider-adapter (`ZoningProvider`) + BFF + frontend | eos-backed-trial | Yes | Create a vegetation VRA map (N zones) for the field via BFF zoning route; unconfigured-safe; Akasha k-means zoning is the native replacement | Phase 8 |
| 14. Productivity / P&K zoning map | Long-period NDVI productivity zones | none | provider-adapter + BFF | defer | No | — (needs multi-season archive) | Phase 8 |
| 15. Zoning export (SHP/GeoJSON) | SHP/ISO-XML zone export for machinery/GIS | none | BFF export service | akasha-native-first-party | Yes (GeoJSON) | Export zones as GeoJSON server-side; SHP/ISO-XML deferred (DEP-013) | Phase 6/8 |
| 16. Terrain / elevation | Slope/elevation overlays | none | BFF + provider | defer | No | — (DEM later) | Phase 11 |
| 17. High-resolution imagery | Planet-like high-res imagery trial | none | optional paid adapter | defer | No | — (premium adapter only) | — |
| 18. Reports & leaderboard | Aggregated multi-field decision UI + leaderboard | none | BFF + frontend | akasha-native-first-party | No | Composed from fields + analytics + weather (REQ-015) | Phase 9 |
| 19. Custom report templates | Select report columns and export | none (no public EOS API) | BFF + frontend | defer | No | — (native template service later) | Phase 9 |
| 20. Disease & pest risk | Crop disease/pest calendar + low/med/high risk | none (no public EOS API) | BFF/model service | defer | No | — (India model path, Phase 11) | Phase 11 |
| 21. Scout tasks | Map-pin tasks with new/closed lifecycle | none (no public EOS API) | BFF + frontend | defer | No | — (native task service, Phase 10) | Phase 10 |
| 22. Activity calendar / log | Add/filter field activities, inputs, costs, status | none (no public EOS API) | BFF + frontend | defer | No | — (native ops service, Phase 10) | Phase 10 |
| 23. Data manager (uploads) | Upload SHP/ISO-XML datasets | none (no public EOS API) | BFF + object storage | defer | No | — (native import pipeline, Phase 10) | Phase 10 |
| 24. Machinery / John Deere | Machinery boundary/data integration | none (no public EOS API) | optional adapter | defer | No | — (optional, non-core) | — |
| 25. Account / team / API / settings | Account admin, team switching, API page | none (no public EOS API) | BFF + frontend + auth | defer | No | — (pilot readiness, Phase 12, SEC-004; auth = Better Auth username/password only) | Phase 12 |
| 26. AI assistant & notifications | Assistant panel + field-change notifications | none (no public EOS API) | BFF + frontend | defer | No | — (Phase 11/12) | Phase 11/12 |
| 27. Navigation shell | EOS-like product navigation surface | partial (single `MapPage`, no router, CON-001) | frontend | akasha-native-first-party | No | EOS-like nav with documented placeholders (REQ-011) | Phase 3 (depends 0) |
| 28. Yield estimation & growth stages | Yield/biomass estimate; BBCH growth-stage timeline | none | BFF/model service | defer | No | — (Phase 3 advanced parity) | Phase 11 |
| 29. Map interaction tools | Split-view compare, ruler/measure, fullscreen, find-field, legend toggle, cloud-mask toggle | partial (basic MapLibre map exists; tools not built) | frontend | akasha-native-first-party | No | EOS-like map tools available on the monitoring map; cloud-mask/legend toggles wired to Module 8 | Phase 4/6 |
| 30. VRA — sowing / map builder / soil sampling | Sowing prescription, manual zone map builder, soil-sampling point planning | none | BFF + frontend | defer | No | — (beyond vegetation/productivity zoning, later VRA work) | Phase 8 |

> Granular EOS sub-tools are folded into the rows above to keep the matrix one-row-per-module:
> point-value/slice analytics tools → Module 6; ground weather stations and XLSX weather report
> export → Modules 11/18 (deferred); cloud-mask/legend toggles → Modules 8/29.

**First-demo modules** (`First-demo required = Yes`): 1, 2, 3, 4 (NDVI), 5, 6, 8, 10, 11, 13, 15
(GeoJSON). This is the smallest vertical slice per GUD-001.

## First-demo acceptance path

The first parity demo passes only when this exact end-to-end happy path succeeds (TASK-002). Each
step is gated by the acceptance check of its module(s) above.

1. **Create or import a field.** Draw a polygon or import GeoJSON. The BFF validates geometry and
   computes the field area server-side; client-supplied area is not trusted (REQ-008). *(Module 1)*
2. **Select the field.** The field becomes the active selection and the map focuses on it. *(Module 1)*
3. **Sync the field to EOS.** The BFF provider adapter mirrors the field into the EOS trial account.
   The browser never calls EOS directly (REQ-003/005). With no EOS key, the route returns a
   `provider-unconfigured` status instead of failing the app (PAT-003). *(Module 1 + adapter)*
4. **Load the field scene timeline.** Scene dates with cloud % are listed for the field AOI. *(Module 2, 8)*
5. **Display the true-colour layer.** The selected date renders as true-colour, which stays the
   default map layer (REQ-007). *(Module 3)*
6. **Switch to NDVI.** The user switches from true-colour to an NDVI overlay. *(Module 4)*
7. **Show the NDVI trend.** A time-series NDVI chart (min/max/avg/std) renders with per-point
   cloud-quality warnings (REQ-013). *(Module 6, 8)*
8. **Show weather forecast and history.** Forecast and historical weather cards/charts load via the
   BFF `WeatherProvider`; provider-unavailable and rate-limit states stay sanitized. *(Module 10, 11)*
9. **Create a vegetation VRA zoning map.** N vegetation zones are generated for the field via the BFF
   `ZoningProvider`; unconfigured-safe. *(Module 13)*
10. **Export one result.** One output (e.g. GeoJSON zones or analytics CSV) is produced server-side
    with no provider-signed URL leaked (SEC-003). *(Module 5, 15)*

All ten steps green = first-demo acceptance.

**Two acceptance modes.** Steps 3, 8, and 9 are EOS-backed:

- *Offline / test mode* (no `EOS_API_KEY`): these steps must return a `provider-unconfigured` status
  cleanly without breaking the app (PAT-003); the rest of the path (field, timeline, true-colour,
  NDVI, trend, export) must still pass. This is the default CI/dev acceptance.
- *Configured demo mode* (real key present): the live EOS sync, weather, and zoning flows must
  actually succeed end-to-end. This is the client-demo acceptance.

## Non-goals for first demo

The following are explicitly **out of scope** for the first parity demo and remain `defer` until
later phases:

- Full crop disease and pest risk models.
- Yield / biomass estimation and BBCH growth-stage timeline.
- AI assistant workflows.
- Marketplace / commerce features.
- John Deere and other machinery integrations.
- Full team roles, RBAC, and team/account administration.
- Paid high-resolution (Planet-like) imagery.
- Productivity / P&K multi-season zoning maps.
- Terrain / elevation overlays.
- Custom report-template builder.
- Scout tasks, activity log, and data manager (uploads).
- Notifications center.

## Resolved decisions (Phase 0 sign-off)

These were the carry-over questions from research; resolved with product on 2026-06-03:

1. **First-demo scope:** the full superset — **Monitoring + Analytics + Weather + VRA + export**
   (confirms TASK-002 / GUD-001). No narrowing to Monitoring + Analytics only.
2. **Branding:** **Akasha branding** — functional parity only. Do not copy EOS visual assets, colors,
   or proprietary content (GUD-002).
3. **EOS trial key:** **available.** Operator places it in the git-ignored `.env` as
   `EOS_API_KEY` (read server-side only by the BFF; SEC-001). The *configured-demo* acceptance mode is
   therefore testable, not just offline/test mode. The key must never be committed, logged, shown in
   frontend code, or returned by any API (REQ-016).
4. **Authentication:** **Better Auth**, **username + password only** (no social/OAuth/SSO for now).
   Scope stays in Phase 12 (pilot readiness) and remains a `defer` for the first demo. See the
   integration note below — Better Auth is a TypeScript/Node library while the BFF is FastAPI, so the
   auth boundary needs a deliberate design decision before Phase 12.

> **Auth integration note (carry into Phase 12 design):** Better Auth runs in the Node/Vite layer.
> Decide early whether (a) auth runs in a small Node/edge layer at the gateway and the FastAPI BFF
> trusts a verified session/JWT, or (b) the SPA holds a Better Auth session and forwards a bearer
> token the BFF validates. Field/provider-link/report/export ownership checks (SEC-004) must be
> enforced in the BFF regardless of where Better Auth issues the session.
