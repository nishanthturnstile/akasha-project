# EOS API Integration Review Summary

> **Client-facing scope is defined in [`client/phase-1-scope.md`](../client/phase-1-scope.md).**
> This document is an **internal engineering review** of the full EOSDA integration and
> intentionally covers more modules than the committed Phase 1 client scope (login, season/field
> creation, field drawing, timeline + index selection, NDVI/NDRE/MSAVI/RECI, and the Monitoring /
> Weather / VRA Maps modules). Modules described here that are not in `phase-1-scope.md` are
> **deferred to Phase 2+** and must not be presented to the client as Phase 1 deliverables.

**Status headline:** Akasha is **demo-ready behind the FastAPI BFF** for EOS-style crop monitoring workflows, with **live EOS validation and production auth/tenant isolation still pending**.

This handoff summarizes the EOSDA API Connect trial integration, architecture review, prior implementation audit findings, and recommended next steps for optimization and production hardening. It does not claim fresh live EOS verification, and it intentionally excludes secrets, private URLs, and raw stack traces.

## Executive summary

- Akasha now exposes an EOS-like crop monitoring workflow while preserving the core guardrail: the browser calls only same-origin Akasha routes (`/api/*` and tile/export routes), never EOS directly.
- EOSDA is integrated as a temporary provider behind server-side adapters. The implementation should be treated as **demo-ready / implementation-with-pending-items**, not production-complete.
- This summary is based on source inspection plus prior plan/audit/model-review findings; live EOS behavior is still unverified until credentials are configured and `TASK-109` passes.
- Native Akasha capabilities remain wired: STAC/COG discovery, true-colour default imagery, BFF cloud-masked statistics, PostGIS plots/fields, MapLibre/Terra Draw, and same-origin tile contracts.
- The largest blockers before a customer pilot are live-provider smoke testing with real credentials, real auth/session/team enforcement, tenant-scoped route checks, and provider coupling cleanup in frontend DTOs.

## What was implemented

| Area | Implemented capability | Review status |
|---|---|---|
| Field foundation | Plot/field CRUD, import/export, metadata, provider-link fields, selection, drawing/editing, boundary rendering | Implemented; provider links exist separately from Akasha field IDs |
| EOS provider layer | `apps/api/app/providers/base.py`, normalized provider models, EOS client, and EOS provider modules | Implemented; protocols exist, but routes still instantiate concrete `Eos*Provider` classes directly |
| Monitoring | Field sync, field scene timeline, true-colour and index display modes, cloud-mask controls, same-origin tile proxy | Implemented; true-colour remains default |
| Analytics | Field statistics and trend routes; native masked-statistics fallback; trend chart UI | Implemented; field-level index imagery is EOS-only while native fallback is currently RGB-only |
| Weather | Forecast, history, accumulated weather, soil-moisture unavailable handling | Implemented via normalized BFF routes |
| VRA/zoning | Vegetation zoning create/list/detail/export UI and BFF routes | Implemented; EOS list/delete paths should be verified against official docs |
| Exports | Index export route, analytics CSV, report/leaderboard CSV, zoning export | Implemented; export URLs remain same-origin |
| Product shell | EOS-like navigation, reports, operations, scouting, data manager, risk, account/team/notifications/assistant surfaces | Implemented, but some modules are shells or rule-based first versions |
| Audit fixes | Mutable Pydantic defaults changed to `Field(default_factory=...)`; report-template request models now override the shared alias generator to avoid ineffective alias metadata warnings | Applied before this handoff |

## EOS API integrations table

| Akasha functionality | EOS API used | Provider module | Public Akasha surface | Notes |
|---|---|---|---|---|
| Field sync/mirroring | `/field-management` | `apps/api/app/providers/eos/field_provider.py` | `/api/fields/{plot_id}/providers/eos/sync` | Stores EOS field ID separately as provider metadata |
| Scene timeline/search | `/scene-search/for-field` | `scene_provider.py` | `/api/fields/{plot_id}/scenes` | Uses field-specific EOS scenes when synced/configured; native fallback otherwise |
| Tiles/rendering | `/api/render/{view_id}/...` | `tile_provider.py` | `/api/tiles/fields/{plot_id}/{scene_token}/{display_mode}/{z}/{x}/{y}.png` | Browser receives only Akasha same-origin templates |
| Analytics trends | `/field-analytics/trend` | `analytics_provider.py` | `/api/fields/{plot_id}/analytics/trend` | Normalized trend points; provider IDs still surface in frontend DTOs |
| Weather forecast/history | `/weather/forecast`, `/weather/historical-high-accuracy`, `/weather/historical-accumulated` | `weather_provider.py` | `/api/fields/{plot_id}/weather/*` | Soil moisture currently returns provider-unavailable when unsupported |
| Cloud imagery export | `/api/gdw/api` | `imagery_provider.py` | `/api/fields/{plot_id}/exports/index` | BFF creates and retrieves provider export; signed/provider URLs are not exposed |
| Vegetation VRA/zoning | `/zoning/vegetation-map`, `/zoning/maps`, `/api/zoning` | `zoning_provider.py` | `/api/fields/{plot_id}/zoning/*` | Verify list/delete endpoint paths and async status behavior with live EOS |

## Architecture/security review

| Guardrail | Current result | Caveat |
|---|---|---|
| Browser never calls EOS directly | Passed in reviewed frontend API layer: calls are relative `/api/*` routes | Frontend DTOs still expose `externalFieldId`, `sceneId`, and `viewId`, which couples UI/tests to provider concepts |
| EOS key stays server-side | Passed: EOS client reads server config and uses `x-api-key`; provider status route does not return the key | Real deployment must set secrets only through ignored `.env` or platform secrets |
| Same-origin tiles/exports | Passed: tile/export routes proxy through BFF/gateway | Field scene tokens are unsigned base64, replayable, and non-production-safe until signed/team-bound or replaced with server-side handles |
| Sanitized errors | Mostly passed: standard Akasha error envelope and sanitized provider errors are present | Continue testing provider edge cases and async failures |
| True-colour default | Passed: default display mode is `RGB`; NDVI is user-selected | Keep this invariant during optimization |
| Native Akasha routes preserved | Passed: product, plots, STAC/COG, and BFF statistics routes remain wired | Do not replace native masked-statistics logic with EOS-only logic |
| Auth/team isolation | Shell only | `get_current_team` uses `DEV_TEAM_ID`; auth-disabled Railway deploys can return 503 until real auth is configured |

## Validation performed

From the prior implementation audit and final verification:

| Validation | Result |
|---|---|
| `python -m ruff check apps\api --quiet` | Passed |
| API parity tests | 81 passed / 1 skipped |
| Frontend parity tests | 73 passed |
| `npm run build` | Passed with Vite chunk-size warning only |
| Full API test suite (`cd apps\api && python -m pytest -q`) | 155 passed / 1 skipped |
| Report-template alias warning regression | Focused test passed with `UnsupportedFieldAttributeWarning` treated as an error |
| Live EOS smoke (`TASK-109`) | Skipped unless `EOS_API_KEY` is configured |

## Known gaps/pending items

| Priority | Gap | Why it matters |
|---|---|---|
| Blocking before pilot | Live EOS smoke test with real `EOS_API_KEY` | Mock validation does not prove live schemas, rate limits, plan-gated features, async timings, or visual parity |
| Blocking before pilot | Real auth/session/team/tenant isolation | Current auth is a shell; protected routes are not production tenant-safe yet |
| Blocking before pilot | Bind field tile scene tokens to plot/team or replace with server-side scene handles | Current unsigned base64 tokens are non-production-safe and can be replayed or mixed across fields if route checks are not tightened |
| High | Remove provider IDs from frontend public DTOs where possible | `externalFieldId`, `sceneId`, and `viewId` leak EOS concepts into UI contracts and make native replacement harder |
| High | Route-level provider factory/injection | Provider protocols exist, but routes instantiate concrete EOS providers directly |
| High | Verify EOS zoning list/delete/export paths against current official docs | Zoning API docs have multiple path variants; live behavior may differ |
| Medium | Clarify shell vs functional modules in acceptance matrix | Some advanced modules are implemented as shells/rule-based first versions, not full EOS equivalents |
| Medium | Native parity for field-level index imagery | Native fallback is currently RGB-oriented while EOS backs field index imagery |
| Medium | OSM basemap fallback | Acceptable for dev, but not production-scale/commercial traffic |

## Optimization recommendations

1. **Run live-provider validation first.** Use one sample field to validate field mirror, scene search, true-colour tile, NDVI trend, weather forecast/history, vegetation zoning, and export behavior.
2. **Add provider factory seams.** Keep `FieldProvider`, `SceneProvider`, `TileProvider`, `AnalyticsProvider`, `WeatherProvider`, and `ZoningProvider` as injectable services so EOS can be swapped for native providers.
3. **Harden authorization and tokens.** Enforce team ownership on fields, provider links, reports, uploads, tasks, zoning maps, and tile/export handles.
4. **Normalize frontend DTOs further.** Prefer Akasha-owned IDs/scene handles and provider-neutral names over EOS-shaped fields.
5. **Cache provider-heavy calls.** Scene search, analytics, weather, zoning status, and export polling should respect EOS trial limits and avoid repeated calls.
6. **Separate shells from validated functionality.** Label AI assistant, disease/pest, advanced VRA, machinery, and account/team surfaces clearly until backed by production logic.
7. **Preserve native replacement path.** Continue building native STAC/COG analytics, weather adapters, and zoning services behind the same public BFF contracts.

## Operator notes for EOS_API_KEY/secrets

- Do not commit EOS credentials or print them in logs, tests, docs, screenshots, or browser responses.
- Set `EOS_API_KEY` only in an ignored local `.env` or deployment secret store.
- Ensure provider mode/enabled settings are configured server-side before running live smoke tests.
- Use mocked tests by default; run the live EOS smoke only when credentials are intentionally configured.
- If a live provider call fails, capture sanitized status, endpoint category, and request ID only; do not paste raw provider payloads containing secrets or private URLs into tickets.

## Suggested next steps

1. Configure `EOS_API_KEY` in a safe local/deployment secret and run `TASK-109` live EOS smoke.
2. Implement real auth/session management and team-scoped ownership checks before any customer pilot data is used.
3. Replace unsigned field scene tokens with server-side handles or signed, team-bound tokens.
4. Refactor route construction to use provider factories/protocols instead of direct `Eos*Provider` instantiation.
5. Remove or encapsulate provider-specific frontend DTO fields and update tests to assert provider-neutral contracts.
6. Verify zoning endpoints and async behavior against current EOS docs and a live account.
7. Update the acceptance matrix to distinguish mocked-pass, live-pass, shell-only, and production-ready states.

## Model-review caveats

- Prior multi-model critique agrees the BFF boundary, secret hygiene, same-origin tile templates, sanitized errors, true-colour default, and native route preservation are directionally sound.
- The same critique warns this should be framed as **demo-ready with pending production work**, not fully production-complete.
- The most important caveats are mock-only validation unless live credentials are configured, and auth/ownership remaining shell-level until real auth is wired.
