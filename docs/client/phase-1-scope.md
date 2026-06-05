# Akasha — Phase 1 Scope of Work for SoW

## Overview

Akasha will deliver a crop-monitoring web application that mirrors the core
field-monitoring workflow of the EOSDA Crop Monitoring portal. Users will log in,
set up seasons and fields, draw their fields on an interactive map, browse satellite
imagery over time, and analyze vegetation health using standard vegetation indices.

Satellite imagery, analytics, weather, and zoning are powered by the **EOSDA API
Connect** trial provider, integrated **behind Akasha's own backend (BFF)**. The
browser only ever calls Akasha same-origin routes — never EOS directly.

---

## In Scope

### 1. User Authentication
- Basic username and password login.

### 2. Season & Field Management
- Season creation and field creation, modeled on the EOSDA portal.
- Interactive field drawing and editing directly on the map.

### 3. Satellite Imagery
- Use of available satellite data sourced through EOSDA (or equivalent) to power
  imagery and analytics.

### 4. Time-Based Monitoring (Timeline — X-axis)
- A horizontal timeline allowing users to step through available acquisition dates.
- Index selection integrated into the timeline for date-by-date comparison.

### 5. Vegetation Index Analysis
- Field-level vegetation index visualization and identification across:
  - **NDVI**
  - **NDRE**
  - **MSAVI**
  - **RECI**

### 6. Core Navigation Modules (Y-axis — EOSDA parity)
- **Monitoring**
- **Weather**
- **VRA Maps**

---

## Out of Scope

- Crop Info module
- Charts / advanced analytics dashboards
- Activities / field activity log
- CDSE-to-Akasha authentication integration
- Integration with the Bhoonidhi portal
- Guided user onboarding flow

---

## EOS Integration Status (against this scope)

Status legend:
- **Implemented (demo/mock)** — wired behind the BFF and passing mock tests; not yet
  validated against a live EOS account.
- **Akasha-native** — delivered by Akasha directly, not via the EOS API.
- **Build required** — not covered by EOS; must be built by Akasha.

| Scope item | Source | EOS API used | Status | Notes |
|---|---|---|---|---|
| Basic username/password login | Akasha-native | — | **Build required** | Auth is currently a dev shell (`get_current_team` uses `DEV_TEAM_ID`). Real auth/session must be built; not an EOS feature. |
| Season + field creation | EOS + Akasha | `/field-management` | **Implemented (demo/mock)** | Field mirroring via `/api/fields/{id}/providers/eos/sync`. "Season" stored as Akasha metadata. |
| Available satellite data | EOS | `/scene-search/for-field` | **Implemented (demo/mock)** | Field scene timeline via `/api/fields/{id}/scenes`; native STAC fallback exists. |
| Draw field on map | Akasha-native | — | **Implemented (Akasha-native)** | MapLibre + Terra Draw + PostGIS. Mirrored to EOS after drawing. |
| Timeline (X-axis) + index selection | EOS | `/scene-search/for-field`, render/tiles | **Implemented (demo/mock)** | Scene timeline + display modes + same-origin tile proxy. |
| NDVI / NDRE / MSAVI / RECI imagery | EOS | `/api/render/{view_id}/...` | **Implemented (demo/mock)** | Index imagery is EOS-backed; native fallback is currently RGB-only. |
| Monitoring module | EOS | scene/tile routes | **Implemented (demo/mock)** | True-colour remains the default layer. |
| Weather module | EOS | `/weather/forecast`, `/weather/historical-*` | **Implemented (demo/mock)** | Forecast, history, accumulated weather. Soil moisture may be plan-gated. |
| VRA Maps module | EOS | `/zoning/vegetation-map`, `/zoning/maps` | **Implemented (demo/mock)** | Vegetation zoning create/list/detail/export. List/delete/export paths and async status must be verified against live EOS docs. |

### Summary
- **All in-scope satellite/monitoring/weather/VRA/index features are achievable with
  the EOS API**, and the integration already exists behind the BFF in demo/mock mode.
- **Login must be built by Akasha** — it is not an EOS feature and is currently a dev shell.
- **Field drawing is Akasha-native** (already working), then mirrored to EOS.

---

## Key Risks & Caveats (before client demo)

1. **No live EOS validation yet.** Everything above is validated in **mock/demo mode
   only**. A real `EOS_API_KEY` must be configured and the live smoke test (`TASK-109`)
   passed to confirm live schemas, timings, and visual parity.
2. **Trial-plan gating & rate limits.** VRA zoning, high-accuracy weather, soil
   moisture, and some indices (MSAVI/RECI/NDRE) may be plan-gated or rate-limited on a
   trial account. Confirm with one live test field before committing demo dates.
3. **Auth & tenant isolation are shell-level.** Field/data ownership is not yet
   production tenant-safe; required for any real pilot data.
4. **Field scene tokens are not production-safe.** Current unsigned base64 tile tokens
   must be signed/team-bound or replaced with server-side handles before pilot.

---

## Recommended First Step
Configure a real `EOS_API_KEY` and run a single end-to-end live test on one sample field:
field mirror → scene search → true-colour tile → NDVI/NDRE/MSAVI/RECI → weather
forecast/history → vegetation VRA map. This confirms what the trial plan actually
unlocks before scope is committed to the client.
