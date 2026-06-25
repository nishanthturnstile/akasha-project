---
goal: Build a provider-agnostic ingestion scheduler and observability framework for the full Akasha satellite catalog
version: 1.0
date_created: 2026-06-24
last_updated: 2026-06-25
owner: Akasha Engineering (ingestion + raster + BFF + frontend + operations)
tags: [architecture, data, ingestion, scheduler, satellite, observability, provider-adapters]
---

# Introduction

This plan defines the low-level and high-level design for a **catalogue-wide satellite ingestion scheduler** that can eventually handle all 20 platforms in [satellite-catalog.md](../reference/satellite-catalog.md), while starting implementation with the currently integrated ISRO/Bhoonidhi ResourceSat sources.

The current working path is ISRO/Bhoonidhi → ResourceSat LISS-3/LISS-4/AWiFS. The long-term platform must also support CDSE Sentinel, USGS/NASA Landsat, NASA Earthdata/ASF, Planet, JAXA, commercial VHR vendors, archive-only sources, and reference-only sources. The key architectural decision is that the scheduler must be **provider-agnostic**: it decides what source is due and records the job lifecycle; provider adapters own connection/auth/search/download/order differences.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox/table tracking and must be verified with tests before moving between phases.

**Goal:** Create one production-ready scheduler/orchestration layer that can run ISRO sources now and onboard other catalogue providers later without rewriting scheduling, monitoring, or product-selection logic.

> **Operational companion (implemented behavior):** For how the shipped scheduler works day-to-day — architecture, triggering, control/cutover, monitoring, and the step-by-step add-a-satellite checklist — see [satellite-ingestion-orchestration-and-scheduler.md](../satellite-ingestion-orchestration-and-scheduler.md). This plan is the build record; that guide is the operator/developer reference.

**Architecture:** Use a registry-driven scheduler plus provider adapters. The scheduler reads source/provider configuration, determines due jobs, invokes the correct provider adapter, writes canonical manifests, dispatches source-specific prepare/validation pipelines, updates job/source state, and exposes monitoring APIs/CLI. Provider-specific API/auth/search/download/order logic lives behind adapters such as `bhoonidhi`, `cdse`, `usgs`, `earthdata`, `asf`, `planet`, `jaxa`, and `vendor`.

**Tech Stack:** Python 3.11 ingestion worker, FastAPI BFF, SQLite ingestion/job ledger initially, pgSTAC, PostgreSQL/PostGIS, MinIO/S3-compatible object storage, rasterio/GDAL/rio-cogeo, TiTiler, systemd on staging/self-hosted infrastructure, React 18 + Vite + TypeScript frontend, TanStack Query, MapLibre GL JS.

## 1. Requirements & Constraints

### Functional requirements

- **REQ-001**: The scheduler must cover all 20 catalogue platforms conceptually, even if most are disabled/gated initially.
- **REQ-002**: The first implementation target is ISRO/Bhoonidhi. LISS-3 and LISS-4 remain active sources; AWiFS continues background/gated ingestion until coverage validation passes.
- **REQ-003**: The scheduler must not contain provider-specific HTTP/auth logic. Provider-specific connection behavior must live in provider adapters.
- **REQ-004**: Every source must have explicit, orthogonal source-state fields. Do not overload `mvp_enabled` or one `state` string to mean scheduling-enabled, product-active, user-selectable, commercially approved, AOI-applicable, and validated.
- **REQ-005**: The scheduler source-state schema must include separate fields for `lifecycleState`, `scheduleState`, `capabilities`, `productExposure`, `commercialState`, `aoiScope`, `validationState`, and `readinessReasons`. It must support at least these values across those fields: `catalogued`, `provider_configured`, `search_enabled`, `download_enabled`, `order_enabled`, `prepare_enabled`, `validate_enabled`, `background_only`, `product_active`, `commercial_blocked`, `archive_only`, `out_of_aoi`, and `reference_only`.
- **REQ-006**: Every scheduled run must create a job record and preserve redacted artifacts that answer: what was scheduled, what provider input was sent, what was found, what was selected, what was downloaded, what was rejected, why it failed or passed, and when the next run is due.
- **REQ-007**: All provider outputs must be normalized into canonical Akasha manifests before prepare/composite/STAC/monitoring stages.
- **REQ-008**: Validation must be profile-driven. Optical composites, optical scenes, SAR backscatter, precomputed context rasters, archive sources, and VHR visual sources require different validation rules.
- **REQ-009**: Source-specific cadence, lookback window, composite window, coverage thresholds, max downloads, host affinity, rate limits, and validation profile must be represented in source/provider configuration.
- **REQ-010**: Existing `bhoonidhi-search`, `bhoonidhi-download`, and `bhoonidhi-sync` commands must remain available as compatibility aliases during migration.
- **REQ-011**: The scheduler must support dry-run and plan-only modes that show due decisions without downloading, preparing, compositing, or ingesting data.
- **REQ-012**: AWiFS may run in background search/download/prepare attempts while gated. Product exposure remains blocked until coverage and source validation pass.
- **REQ-013**: Best-observation selection must be backend-owned after scheduler state is reliable. The frontend must not duplicate source ranking rules.
- **REQ-014**: Existing source-specific timelines remain available for transparency and debugging, even after a best-available timeline is added.
- **REQ-015**: Trend analytics must remain primary-source-only initially. Mixed-source trend normalization requires a separate design.
- **REQ-016**: Ingestion owns raw scheduler artifacts and the scheduler/job SQLite ledger. The BFF may read only redacted scheduler snapshots or summaries via an explicit read-only mount/config contract, unless a later phase creates API-owned SQLAlchemy ORM models plus Alembic migrations for job summaries.
- **REQ-017**: ResourceSat LISS-3 production invariants are release-blocking acceptance criteria: 4 analytic bands `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`, FCC NIR/RED/GREEN display, no Sentinel SCL, Akasha threshold mask v1 with `{1,4}` valid by default, reflectance scale `0.0001` and offset `0.0`, nearest-neighbour mask handling, separate analytic/mask COG assets, deterministic keys, and STAC upsert behavior.
- **REQ-018**: The scheduler registry must include a machine-readable mapping from every `docs/reference/satellite-catalog.md` slug to one or more Akasha source rows. Each row must include `catalogSlug`, `catalogPlatform`, `sourceId`, `providerAdapter`, `productFamily`, `instrumentMode`, and `productVariant` where applicable. A catalogue platform may map to multiple source rows (for example ResourceSat-2A maps to LISS-3, LISS-4, and AWiFS), but every source row must trace back to exactly one catalogue slug unless it is explicitly marked internal/legacy.
- **REQ-019**: Initial scheduler implementation is not allowed to change frontend source ranking, best-observation selection, or mixed-source timelines. Existing source-specific timelines remain the serving source of truth until Phase 11 explicitly introduces backend-owned best-observation selection.

### Provider/source requirements

- **SRC-001**: ISRO/Bhoonidhi sources must run only from the staging host or an approved host with whitelisted egress.
- **SRC-002**: CDSE sources must use the current supported CDSE STAC/OData APIs and OAuth2/Keycloak token handling.
- **SRC-003**: USGS/Landsat sources should prefer cloud-native STAC+COG access for Collection 2 Level-2 products.
- **SRC-004**: Earthdata/ASF sources must use Earthdata Login tokens and source-appropriate CMR/STAC/ASF access.
- **SRC-005**: Planet/JAXA/VHR commercial sources must not place paid orders without explicit operator approval and a documented commercial-readiness record.
- **SRC-006**: NAIP is US-only and must remain reference/out-of-AOI for India deployments.
- **SRC-007**: Archive-only sources such as Landsat 5, Landsat 7, and IRS-1C are on-demand/backfill sources, not routine current-monitoring sources.

### Provider capability matrix

The scheduler uses one provider adapter contract, but providers do not all support the same actions.
Capabilities must be explicit and fail closed when unsupported.

| Provider adapter | Search | Download/fetch | Order/task | Poll/cancel order | Auth model | Cost risk | Default runtime posture |
|---|---:|---:|---:|---:|---|---|---|
| `bhoonidhi` | ✅ | ✅ | ❌ | ❌ | Password grant + whitelisted egress | Low | Staging safe-wrapper only for non-dry-run ISRO jobs. |
| `cdse` | ✅ | ✅ | ❌ | ❌ | OAuth2/Keycloak + optional EOData S3 | Low | Any approved worker host with credentials. |
| `usgs` | ✅ | ✅ cloud COG fetch | ❌ | ❌ | Optional M2M/Earthdata or open cloud | Low | Prefer cloud-native STAC/COG path. |
| `earthdata` | ✅ | ✅ | ❌ | ❌ | Earthdata token | Low | Any approved worker host with credentials. |
| `asf` | ✅ | ✅ | ❌ | ❌ | Earthdata token / ASF APIs | Low | Any approved worker host with credentials. |
| `planet` | ✅ | ✅ | ✅ | ✅ | Planet API key | High | Search-only until commercial readiness + explicit paid-order flag. |
| `jaxa` | ✅/manual | ✅/manual | optional | optional | JAXA/reseller-specific | Medium/high | Free mosaic can be fetch-only; scenes remain commercial-gated. |
| `vendor` | provider-specific | provider-specific | ✅ | ✅ | Vendor-specific | High | Disabled until contract/quota/readiness is signed off. |
| `usda`/`naip` | ✅ | ✅ | ❌ | ❌ | None/open cloud | Low | Reference/out-of-AOI for India deployments. |

### Security requirements

- **SEC-001**: Provider credentials must be stored only in deployment secrets/environment variables. Never commit provider credentials, tokens, API keys, generated S3 credentials, signed URLs, or raw provider archives.
- **SEC-002**: Job artifacts, command files, request files, logs, and API responses must redact secrets, bearer tokens, passwords, API keys, provider usernames, and signed URLs.
- **SEC-003**: The frontend must never call Bhoonidhi, CDSE, USGS, Earthdata, Planet, JAXA, MinIO, pgSTAC, PostGIS, or TiTiler directly. Browser calls remain same-origin `/api/*` and `/tiles/*` through the BFF/gateway.
- **SEC-004**: Commercial order APIs must be disabled by default and require an explicit allow flag plus readiness state before executing quota/cost-incurring calls.
- **SEC-005**: Unknown providers and unknown source IDs must fail closed with explicit errors.
- **SEC-006**: Monitoring APIs must not expose raw server filesystem paths, signed provider URLs, object-store credentials, internal hostnames, or full logs to the frontend. Use redacted summaries and opaque artifact handles by default; raw artifact paths are CLI-only or restricted to elevated operator roles.
- **SEC-007**: Paid order/task/subscription methods must require all of: `commercialState != commercial_blocked`, `allowPaidOrder=true`, an operator-provided explicit command flag, and a documented commercial-readiness record for the source/provider. Tests must prove commercial adapters cannot place paid orders by default even when credentials exist.

### Operational constraints

- **OPS-001**: Heavy staging ingestion must use the safe wrapper path. Do not run direct ad hoc heavy Docker commands on `akasha-staging`.
- **OPS-002**: Bulk raster/raw/work/COG data must stay under `/srv/akasha`; do not use `/tmp`, `/`, `/var/tmp`, `/var/lib/docker`, or Coolify storage for raster intermediates.
- **OPS-003**: Jobs must use locks scoped by provider/source/AOI so one failed source does not block unrelated sources.
- **OPS-004**: The scheduler may run frequently, but it must decide due sources from cadence and source state. Do not create one long-lived busy loop.
- **OPS-005**: Initial implementation may use JSON job artifacts plus the existing SQLite ledger. SQL-backed job history can follow when UI/history retention requirements stabilize.
- **OPS-006**: Scheduler monitoring must be available via CLI/API first. UI is useful but not required for the first operational release.
- **OPS-007**: The scheduler must have a safe cutover model: a global scheduler lock, provider/source/AOI worker locks compatible with existing Bhoonidhi jobs during migration, explicit max-concurrent-source limits, a dry-run/canary period, and a documented rollback path to legacy source-specific timers.
- **OPS-008**: Scheduler and provider adapters must enforce approved-runtime preflights for staging-only providers. Bhoonidhi jobs fail closed unless they run through the safe wrapper or an explicitly approved dry-run/local-test mode.
- **OPS-009**: Scheduler storage must define SQLite WAL/busy-timeout behavior, first-run due behavior, retention/pruning, stale-lock reclaim rules, and disk-pressure thresholds before the scheduler is enabled.
- **OPS-010**: Scheduler cutover must maintain a source/AOI ownership matrix with `ownedBy`, `legacyTimerName`, `schedulerEnabled`, `cutoverDate`, and rollback commands. Legacy source-specific timers and the scheduler must never own the same source/AOI simultaneously.

### Geospatial/raster constraints

- **GEO-001**: Optical index support is determined by band roles, not satellite names. NDVI/MSAVI need NIR+RED; NDMI needs NIR+SWIR1; NDWI_GREEN_NIR needs GREEN+NIR; NDRE needs NIR+RED_EDGE.
- **GEO-002**: SAR sources must not advertise optical vegetation indices. SAR products use SAR-specific display/analytics only.
- **GEO-003**: Context/precomputed products such as MODIS NDVI or EOS-06 OCM NDVI must not be represented as raw reflectance field-statistics sources unless a validated raw-band pipeline exists.
- **GEO-004**: Composite-capable optical sources must register dated `akasha:composite=true` STAC items when those composites are the served product.
- **GEO-005**: Source-specific mask classes and scale/offset metadata must be preserved in STAC and BFF responses.
- **GEO-006**: Scheduler refactors must preserve current ResourceSat LISS-3 semantics exactly before enabling new source selection, validation profiles, or best-observation behavior.

### Documentation requirements

- **DOC-001**: Update [satellite-catalog.md](../reference/satellite-catalog.md) with ingestion state/cadence summaries for the 20 catalogue entries.
- **DOC-002**: Update [satellite-ingestion-onboarding-matrix.md](../reference/satellite-ingestion-onboarding-matrix.md) with the provider adapter model, scheduler state taxonomy, and per-provider scheduling implications.
- **DOC-003**: Update [data-ingestion-and-satellite-rules.md](../data-ingestion-and-satellite-rules.md) with scheduler/onboarding/validation/monitoring rules.
- **DOC-004**: Update [staging-ingestion-developer-guide.md](../staging-ingestion-developer-guide.md) with orchestrator commands and staging-safe scheduler operations.
- **DOC-005**: Keep the existing multi-source roadmap linked from this plan. This file provides the scheduler architecture layer; the existing roadmap still tracks provider onboarding tasks.

## 2. Implementation Steps

### Implementation Phase 0 — Architecture contracts and rollout gates

- GOAL-000: Resolve the cross-service contracts and safety gates that must be stable before runtime scheduler implementation begins.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-000A | Define the typed source-state schema with `lifecycleState`, `scheduleState`, `capabilities`, `productExposure`, `commercialState`, `aoiScope`, `validationState`, and `readinessReasons`. Include precedence rules and invalid combinations such as `commercial_blocked + order_enabled`, `archive_only + routine schedule`, and `background_only + product_active`. | Yes | 2026-06-24 |
| TASK-000B | Decide and document job-state ownership. Default: ingestion owns raw artifacts and SQLite under `/srv/akasha`; scheduler writes redacted `schedule_state.json` and job summary snapshots; BFF reads only those snapshots through an explicit read-only mount/config. If API-owned job tables are later required, define them in SQLAlchemy ORM models and Alembic only. | Yes | 2026-06-24 |
| TASK-000C | Define the monitoring API boundary: paginated/filterable job lists, capped detail payloads, redacted summaries, opaque artifact handles, no raw paths in frontend responses, and elevated-role requirements for any operator-only artifact access. | Yes | 2026-06-24 |
| TASK-000D | Define scheduler cutover and rollback: install disabled/dry-run first, canary one source/AOI, use lock paths compatible with existing Bhoonidhi jobs, disable legacy timers per migrated source, cap max concurrent sources, and document rollback to the previous timer/env setup. | Yes | 2026-06-24 |
| TASK-000E | Define ResourceSat LISS-3 release-blocking invariants and parity tests covering band order, FCC display, mask semantics, scale/offset, separate analytic/mask COGs, deterministic keys, STAC metadata, and upsert behavior. | Yes | 2026-06-24 |
| TASK-000F | Define the scheduler job ledger contract: per-AOI/window fields, first-run due behavior, SQLite WAL/busy timeout, retention/pruning, and how `nextDueAt` is calculated from the job ledger rather than the legacy product ledger. | Yes | 2026-06-24 |
| TASK-000G | Define approved-runtime preflights for staging-only providers so direct `worker.py schedule-*` execution fails closed for Bhoonidhi unless running in safe-wrapper mode or explicit dry-run/local-test mode. | Yes | 2026-06-24 |
| TASK-000H | Define operator alerts/runbooks for missed due runs, repeated failures, stale searches, failed validation, low coverage, disk pressure, MinIO upload failures, STAC registration failures, provider auth/rate-limit failures, stale locks, and scheduler rollback. | Yes | 2026-06-24 |
| TASK-000I | Define the catalogue slug-to-source mapping contract. Required fields: `catalogSlug`, `catalogPlatform`, `sourceId`, `providerAdapter`, `productFamily`, `instrumentMode`, `productVariant`, `analysisLevel`, `validationProfile`, and `productExposure`. Document one-to-many mappings such as `resourcesat-2a -> resourcesat-2a-liss3-boa/resourcesat-2a-liss4-mx70-l2/resourcesat-2a-awifs-boa` and fail closed for source rows without a catalogue slug unless marked `internal_legacy`. | Yes | 2026-06-24 |
| TASK-000J | Define the legacy-timer versus scheduler source-ownership matrix. Include `sourceId`, `aoiId`, `ownedBy` (`legacy_timer`, `scheduler_dry_run`, `scheduler_active`, `manual_only`), `legacyTimerName`, `schedulerEnabled`, `cutoverDate`, and rollback command. | Yes | 2026-06-24 |

### Implementation Phase 1 — Source-state taxonomy and catalogue registry

- GOAL-001: Make the full 20-platform catalogue explicit in source/scheduler state before changing runtime orchestration.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add the Phase 0 typed source-state taxonomy to `docs/reference/satellite-ingestion-onboarding-matrix.md`, including `reference_only`, field definitions, transition rules, and invalid-combination examples. | Yes | 2026-06-24 |
| TASK-002 | Extend `services/ingestion/akasha_ingest/pipeline_registry.py` or split a new `services/ingestion/akasha_ingest/source_registry.py` so each source row can represent schedule state, provider adapter, licence state, AOI scope, validation profile, cadence, host pool, and product exposure separately from `mvp_enabled`. Keep `mvp_enabled` only as a derived/backwards-compatible property until all call sites are migrated. | Yes | 2026-06-24 |
| TASK-003 | Add registry entries for all 20 catalogue sources. Only existing ISRO/ResourceSat sources are executable initially; future provider rows are disabled/gated with explicit reasons. | Yes | 2026-06-24 |
| TASK-004 | Add tests in `tests/test_satellite_catalog_registry.py` proving all 20 slugs from `docs/reference/satellite-catalog.md` have a corresponding source-state row or an explicit `out_of_aoi`/`reference_only` exclusion. The test must also prove no executable source row is missing a catalogue slug, and that one catalogue slug may map to multiple source rows only through an explicit `productVariant` split. | Yes | 2026-06-24 |
| TASK-005 | Add tests proving commercial sources default to `commercial_blocked`, archive-only sources are not current-scheduled, NAIP is excluded for `bangalore-60km`, and contradictory state combinations fail closed. | Yes | 2026-06-24 |
| TASK-006 | Update `docs/reference/satellite-catalog.md` with a short ingestion-state line for each platform: provider adapter, default cadence class, scheduling state, and product exposure status. | Yes | 2026-06-24 |

### Implementation Phase 2 — Provider adapter contract

- GOAL-002: Make provider-specific API/auth/search/download/order logic pluggable behind a common contract.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Create `services/ingestion/akasha_ingest/providers/base.py` defining typed provider request/result objects and a synchronous `ProviderAdapter` protocol with `search`, `normalize_candidate`, `download`, optional `order`, optional `poll_order`, optional `cancel_order`, and `close` methods. The contract must include pagination, token refresh hooks, rate-limit/backoff metadata, resumable download/idempotency fields, quota/cost preflight fields, and order lifecycle states for future providers. | Yes | 2026-06-24 |
| TASK-008 | Create `services/ingestion/akasha_ingest/providers/registry.py` with `get_provider_adapter(provider: str)`. Unknown providers must raise a clear fail-closed exception. | Yes | 2026-06-24 |
| TASK-009 | Create `services/ingestion/akasha_ingest/providers/bhoonidhi_adapter.py` as a thin wrapper around `akasha_ingest.bhoonidhi.BhoonidhiClient`, `candidate_from_item`, and existing manifest helpers. | Yes | 2026-06-24 |
| TASK-010 | Add provider adapter placeholders for future providers: `cdse_adapter.py`, `usgs_adapter.py`, `earthdata_adapter.py`, `asf_adapter.py`, `planet_adapter.py`, `jaxa_adapter.py`, and `vendor_adapter.py`, each raising `NotImplementedError` until that provider phase begins. | Yes | 2026-06-24 |
| TASK-011 | Add `tests/test_provider_adapter_contract.py` proving Bhoonidhi adapter emits the same normalized candidate/download result shape as the existing Bhoonidhi path and unknown providers fail closed. | Yes | 2026-06-24 |
| TASK-012 | Document adapter responsibilities in `docs/reference/satellite-ingestion-onboarding-matrix.md` under the reference pattern section. | Yes | 2026-06-24 |
| TASK-012A | Add provider adapter capability tests proving unsupported methods fail closed. In particular, commercial `order`/`task` methods must fail unless the source is commercially ready and the operator passes an explicit paid-order flag. | Yes | 2026-06-24 |

### Implementation Phase 3 — Canonical manifests and redaction

- GOAL-003: Normalize provider-specific search/download/order outputs into one Akasha manifest format for downstream stages.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Create `services/ingestion/akasha_ingest/manifests.py` containing schema helpers for `search_manifest`, `download_manifest`, `order_manifest`, JSON/Pydantic validation, manifest versioning, migration helpers, and redaction utilities. | Yes | 2026-06-24 |
| TASK-014 | Define required search manifest fields: `manifestType`, `version`, `jobId`, `sourceId`, `provider`, `adapter`, `collection`, `aoi`, `datetimeRange`, `providerQuery`, `candidates`, `selection`, and `redactionVersion`. | Yes | 2026-06-24 |
| TASK-015 | Define required candidate fields: `providerItemId`, `itemId`, `acquisitionDatetime`, `bbox`, `intersectsAoi`, `overlapArea`, `downloadStatus`, `skipReason`, `providerProperties`, and `links` with sensitive URLs redacted. | Yes | 2026-06-24 |
| TASK-016 | Define required download manifest fields: `downloaded[]`, `failed[]`, `deferred[]`, bytes, local paths, provider IDs, error kind, redacted error, and retry status. | Yes | 2026-06-24 |
| TASK-017 | Update current Bhoonidhi search/download code paths to emit canonical manifests while preserving existing keys where tests or downstream code depend on them. | Yes | 2026-06-24 |
| TASK-018 | Add tests proving redaction removes passwords, tokens, bearer headers, API keys, signed URLs, and provider usernames from manifests, command files, logs, and API payloads. | Yes | 2026-06-24 |

### Implementation Phase 4 — Scheduler/orchestrator core

- GOAL-004: Add one scheduler/orchestrator that decides due sources and runs provider-specific jobs through the adapter interface.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Create `services/ingestion/akasha_ingest/orchestrator.py` with `plan_due_sources`, `run_due_sources`, and `run_source_job` functions. | Yes | 2026-06-24 |
| TASK-020 | Add due-source logic using source cadence, last successful search/composite from the new per-AOI/window job ledger, typed source state, AOI, host pool, manual overrides, and explicit first-run behavior. | Yes | 2026-06-24 |
| TASK-021 | Add `services/ingestion/akasha_ingest/jobs.py` to create job IDs, job directories, `request.json`, `status.json`, `command.txt`, `result.json`, and structured event timelines. | Yes | 2026-06-24 |
| TASK-022 | Add a global scheduler lock plus source/AOI/provider worker locks using existing `sync.acquire_lock` semantics, but centralize paths, old-wrapper compatibility, PID/timestamp stale-lock reclaim, and TTL policy in a dedicated lock helper. | Yes | 2026-06-24 |
| TASK-023 | Add `worker.py schedule-plan --json` to print due decisions without running provider calls. | Yes | 2026-06-24 |
| TASK-024 | Add `worker.py schedule-due-sources` to execute due sources from the registry with max-concurrent-source and per-run budget limits. | Yes | 2026-06-24 |
| TASK-025 | Add `worker.py schedule-source --source <sourceId> --aoi <aoiId> --dry-run` to run one source through the orchestrator. Enforce approved-runtime preflights for staging-only providers before any non-dry-run provider call. | Yes | 2026-06-24 |
| TASK-026 | Preserve `bhoonidhi-sync` as a backwards-compatible command during Phase 4. Do not delegate it to the orchestrator until Phase 7 parity tests pass. | Yes | 2026-06-24 |
| TASK-027 | Add orchestrator tests proving dry-run does not download, due-source decisions honor cadence, commercial sources are blocked, NAIP is excluded, archive sources require explicit backfill/on-demand mode, direct unsafe Bhoonidhi execution fails closed, stale locks are handled, and concurrency limits are enforced. | Yes | 2026-06-24 |
| TASK-027A | Add an orchestrator test for AWiFS below-threshold coverage. If validation returns low coverage, the job state must become `validation_failed`, `failureKind="low_coverage"` or equivalent, `productExposure` must remain `background_only`, and AWiFS must not become product-active/user-selectable. | Yes | 2026-06-24 |

### Implementation Phase 5 — Job state and scheduler observability

- GOAL-005: Make every scheduler run inspectable from CLI/API and eventually UI.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-028 | Extend job artifacts to include redacted provider input, provider response summary, canonical search manifest handle/path, download manifest handle/path, prepare manifest handles/paths, verification summary, and next due calculation. Raw paths stay CLI/operator-only; API/UI surfaces use redacted summaries and opaque handles. | Yes | 2026-06-24 |
| TASK-029 | Extend the existing SQLite ingestion ledger or add a job ledger table with `job_id`, `source_id`, `provider`, `aoi_id`, `state`, `scheduled_at`, `started_at`, `finished_at`, `window_start`, `window_end`, `found_count`, `selected_count`, `downloaded_count`, `rejected_count`, `failed_count`, `failure_kind`, `schedule_decision`, `next_due_at`, and `artifact_summary_path`. Configure WAL, busy timeout, retention, and prune behavior. | Yes | 2026-06-24 |
| TASK-030 | Extend existing `scripts/staging_ingestion_job.py` commands where possible before adding new vocabulary. Add or alias `job-inspect <job_id> --json` to fetch a combined redacted job summary from staging artifacts. | Yes | 2026-06-24 |
| TASK-031 | Add or alias `scripts/staging_ingestion_job.py job-artifact <job_id> <request|status|coverage|download|result|log>` to fetch a specific artifact for operators. Redact payloads by default and require explicit operator-only mode for raw paths/logs. | Yes | 2026-06-24 |
| TASK-032 | Add `scripts/staging_ingestion_job.py schedule-plan --source <sourceId> --aoi <aoiId> --json` to inspect why a source is or is not due. | Yes | 2026-06-24 |
| TASK-033 | Add `scripts/staging_ingestion_job.py schedule-next --source <sourceId> --aoi <aoiId>` to show next due run/window using scheduler state. | Yes | 2026-06-24 |
| TASK-034 | Add CLI tests or script-level tests proving job inspection redacts secrets and returns request/status/result/log pointers. | Yes | 2026-06-24 |

### Implementation Phase 6 — Source-aware validation profiles

- GOAL-006: Replace ResourceSat-specific verification assumptions with profile-driven validation for optical, SAR, context, archive, and VHR products.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-035 | Create `services/ingestion/akasha_ingest/validation_profiles.py` with profiles: `optical_composite`, `optical_scene`, `sar_backscatter`, `context_raster`, `archive_optical`, and `vhr_visual`. | Yes | 2026-06-24 |
| TASK-036 | Add profile fields: expected assets, band count, dtype, scale, offset, nodata, CRS rules, resolution tolerance, overview requirement, mask asset, mask classes, STAC required fields, and allowed display/statistics roles. | Yes | 2026-06-24 |
| TASK-037 | Add or refactor `worker.py verify-raster-product --source <sourceId> --profile <profile> --manifest <path>` for non-composite sources. | Yes | 2026-06-24 |
| TASK-038 | Keep `worker.py verify-composite` as an alias/specialization for `optical_composite` validation. | Yes | 2026-06-24 |
| TASK-039 | Add tests proving SAR/context/archive sources are rejected by `verify-composite` with an actionable error. | Yes | 2026-06-24 |
| TASK-040 | Add tests proving `verify-raster-product` accepts valid SAR/context fixtures and rejects wrong band counts or optical-index metadata on SAR sources. | Yes | 2026-06-24 |
| TASK-040A | Add ResourceSat LISS-3 invariant tests proving the scheduler/validation refactor preserves 4-band order, FCC display metadata, no-SCL mask semantics, `{1,4}` valid mask policy, scale/offset, separate analytic/mask COGs, deterministic keys, and STAC upsert behavior. | Yes | 2026-06-24 |

### Implementation Phase 7 — ISRO/Bhoonidhi scheduler implementation first

- GOAL-007: Move the current ISRO sources into the generic scheduler while preserving production behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-041 | Configure `resourcesat-2a-liss3-boa` as active, field optical, search/download/prepare/composite/validate enabled, with 95% coverage threshold and Bhoonidhi staging host affinity. Runtime registry/config is present; live orchestrator execution remains fail-closed until the full provider pipeline is wired. | Partial (dry-run/config) | 2026-06-25 |
| TASK-042 | Configure `resourcesat-2a-liss4-mx70-l2` as active high-resolution field enhancement, with narrow-swath acceptance and field-intersection fallback semantics. Runtime registry/config is present; live orchestrator execution remains fail-closed until the full provider pipeline is wired. | Partial (dry-run/config) | 2026-06-25 |
| TASK-043 | Configure `resourcesat-2a-awifs-boa` as background/search-enabled and product-gated until validated composite coverage reaches the accepted threshold. Runtime registry/config is present; live orchestrator execution remains fail-closed until the full provider pipeline is wired. | Partial (dry-run/config) | 2026-06-25 |
| TASK-044 | Add disabled/scaffolded ISRO rows for EOS-04, EOS-06, NISAR, IRS-1C, and Cartosat-3 with correct provider, state, validation profile, and reason. | Yes | 2026-06-24 |
| TASK-045 | Run parity tests proving `bhoonidhi-sync` and `schedule-source --source resourcesat-2a-liss3-boa` produce equivalent search/download/prepare/composite/ingest behavior in dry-run mode. Current tests prove dry-run stop-point parity (`before_download`) only; live search/download/prepare/composite/ingest remains intentionally fail-closed. Only after full parity passes may `bhoonidhi-sync` delegate to the orchestrator. | Partial (dry-run stop-point) | 2026-06-25 |
| TASK-046 | Run safe-wrapper staging dry-runs for LISS-3, LISS-4, and AWiFS through the scheduler commands. Unit/static wrapper coverage is present; fresh staging execution evidence is still required before cutover. | Partial (tests; staging evidence pending) | 2026-06-25 |
| TASK-047 | Confirm AWiFS below-threshold coverage remains background/gated and appears in monitoring with the validation failure reason. | Yes | 2026-06-24 |

> Phase 7 note: this behavior is already evidenced by the 2026-06-23 AWiFS run in
> `test_reports/awifs-validation-2026-06-23.md`, where a bounded safe-wrapper retry reached
> only `62.9839%` coverage against the `95%` threshold. Scheduler implementation must preserve
> that decision: background ingestion may continue, but product exposure stays gated until a
> validated AWiFS composite meets the accepted coverage threshold.

### Implementation Phase 8 — Scheduler deployment model

- GOAL-008: Replace timer-per-source growth with one orchestrator timer that runs safe, bounded due-source checks.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-048 | Add `infra/selfhosted/systemd/akasha-ingestion-scheduler.timer` with a safe cadence such as hourly or every few hours. Install disabled or dry-run-only for the initial cutover window; the orchestrator decides actual source due state. | Yes | 2026-06-24 |
| TASK-049 | Add `infra/selfhosted/systemd/akasha-ingestion-scheduler.service` that runs the safe scheduler wrapper from `/srv/akasha`. | Yes | 2026-06-24 |
| TASK-050 | Add `infra/selfhosted/systemd/akasha-ingestion-scheduler.sh` using the same staging guardrails as current Bhoonidhi scripts: bounded defaults, global scheduler lock, worker lock path, redaction, `ionice`/`nice`, no direct heavy ad hoc runs, approved-runtime signal, and rollback-friendly logging. | Yes | 2026-06-24 |
| TASK-051 | Add `infra/selfhosted/systemd/ingestion-scheduler.env.example` with scheduler-wide defaults, provider-specific knobs, max concurrent sources, per-run job budget, dry-run/canary flags, stale-lock TTL, retention/prune settings, and explicit legacy-timer ownership controls. | Yes | 2026-06-24 |
| TASK-052 | Update `tests/test_bhoonidhi_systemd_artifacts.py` or add `tests/test_ingestion_scheduler_systemd_artifacts.py` to assert the scheduler artifacts exist and preserve staging-safe behavior. | Yes | 2026-06-24 |
| TASK-053 | Mark existing source-specific timers as compatibility mode in docs once the orchestrator timer is validated. Do not let legacy timers and the scheduler own the same source/AOI simultaneously; disable one source-specific timer only after canary parity is confirmed. Document rollback by stopping the scheduler timer and re-enabling the previous timer/env. | Yes | 2026-06-24 |

### Implementation Phase 9 — Monitoring APIs

- GOAL-009: Expose schedule and job observability via authenticated BFF endpoints.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-054 | Add `apps/api/app/ingestion_jobs.py` with `GET /api/monitoring/ingestion-schedules`, `GET /api/monitoring/ingestion-jobs`, and `GET /api/monitoring/ingestion-jobs/{jobId}`. The BFF reads only the Phase 0 redacted scheduler snapshots/job summaries through explicit read-only config, not raw provider archives or unrestricted job directories. | Yes | 2026-06-24 |
| TASK-055 | Wire the new router in `apps/api/app/main.py` with the same auth/team protection as existing monitoring routes. | Yes | 2026-06-24 |
| TASK-056 | Schedule response fields must include `sourceId`, `provider`, `adapter`, `aoiId`, typed source-state fields, `scheduleEnabled`, `productExposure`, `lastRunAt`, `lastSuccessAt`, `lastFailureAt`, `nextDueAt`, `nextWindowStart`, `nextWindowEnd`, `cadenceDays`, and `dueReason`. | Yes | 2026-06-24 |
| TASK-057 | Job list response fields must include `jobId`, `sourceId`, `provider`, `aoiId`, `state`, `windowStart`, `windowEnd`, `foundCount`, `selectedCount`, `downloadedCount`, `rejectedCount`, `failureKind`, `message`, `startedAt`, `finishedAt`, and `updatedAt`. Add `limit`, `cursor`, `sourceId`, `aoiId`, `state`, `startedAfter`, and `startedBefore` filters. | Yes | 2026-06-24 |
| TASK-058 | Job detail response fields must include redacted `request`, redacted provider input, search/download manifest summaries, candidate rejection reasons, validation checks/problems, ledger rows, and opaque artifact handles. Do not expose raw server paths or full logs in frontend-safe responses. | Yes | 2026-06-24 |
| TASK-059 | Extend `apps/api/app/source_monitoring.py` so each source links to the latest scheduler job and includes schedule due/overdue status. | Yes | 2026-06-24 |
| TASK-060 | Add BFF tests for job list/detail redaction, schedule state, pagination/filtering, missing artifact handling, no raw path leakage, role-gated operator artifact access if implemented, and source-monitoring integration. | Yes | 2026-06-24 |

### Implementation Phase 10 — Optional operator UI

- GOAL-010: Add a UI only after API/CLI observability is stable.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-061 | Add frontend API types and clients in `apps/frontend/src/types/api.ts`, `apps/frontend/src/lib/api.ts`, and `apps/frontend/src/lib/queries.ts` for ingestion schedules and jobs. | Yes | 2026-06-24 |
| TASK-062 | Add `apps/frontend/src/pages/monitoring/IngestionJobsList.tsx` showing job ID, source, provider, AOI, state, window, counts, and latest message. | Yes | 2026-06-24 |
| TASK-063 | Add `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx` with tabs: Summary, Provider Inputs, Candidates, Downloads, Verification, Ledger, Logs, and Actions. | Yes | 2026-06-24 |
| TASK-064 | Add links from existing imagery source monitoring cards to the latest job detail for that source. | Yes | 2026-06-24 |
| TASK-065 | Add frontend tests for job list/detail rendering, redacted secrets, failure reasons, and gated/background source display. | Yes | 2026-06-24 |

### Implementation Phase 11 — Best-observation resolver and frontend timeline

- GOAL-011: Once scheduler state is reliable, provide backend-owned best-source-per-date selection.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-066 | Add a generalized backend resolver near `apps/api/app/raster/catalog_resolver.py`, such as `resolve_best_observation`, that ranks validated active observations across sources. | Yes | 2026-06-24 |
| TASK-067 | Add `GET /api/observations/best` for timeline/date-range use and optional `POST /api/observations/resolve` for geometry-aware decisions. | Yes | 2026-06-24 |
| TASK-068 | Ranking must consider source state, index support, date proximity, coverage, usable pixels, field intersection, analysis level, resolution, and source priority. | Yes | 2026-06-24 |
| TASK-069 | AWiFS can qualify only when validated and when the requested use case allows regional/coarse fallback; it must be excluded from small-field best decisions unless explicitly allowed. | Yes | 2026-06-24 |
| TASK-070 | Add frontend best-available timeline mode while preserving source-specific timeline mode. In best mode, use backend-resolved `sourceId` and `acquisitionDate` for tiles, overlays, stats, and exports. | Yes | 2026-06-24 |
| TASK-071 | Add frontend DateChip/TimelineBar provenance labels such as `LISS-4 · 5.8 m`, `LISS-3 · 24 m`, and `AWiFS · 56 m · coarse`. | Yes | 2026-06-24 |
| TASK-072 | Add backend/frontend tests proving best mode uses resolved source/date consistently and source-specific mode remains unchanged. | Yes | 2026-06-24 |

### Implementation Phase 12 — Future provider onboarding sequence

- GOAL-012: Add non-ISRO providers by adding adapters/source rows, not by rewriting the scheduler.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-073 | CDSE Phase: implement Sentinel-2 and Sentinel-1 adapters and validation after Phases 0–9 are stable. | Partial (docs+tests) | 2026-06-25 |
| TASK-074 | USGS Phase: implement Landsat 8/9 using cloud STAC+COG and QA_PIXEL-derived masks. | Partial (docs+tests) | 2026-06-25 |
| TASK-075 | Earthdata Phase: implement MODIS regional context and NISAR ASF readiness path. | Partial (docs+tests) | 2026-06-25 |
| TASK-076 | ISRO gated Phase: enable EOS-04, EOS-06, NISAR Bhoonidhi, IRS-1C, and Cartosat placeholders only through their validation profiles and gating rules. | Partial (docs+tests) | 2026-06-25 |
| TASK-077 | Archive Phase: add Landsat 7/5 and IRS-1C backfill/on-demand flows, not current cadence. | Partial (docs+tests) | 2026-06-25 |
| TASK-078 | Commercial Phase: implement Planet/JAXA/VHR provider adapters only after readiness checklist, contract, quota, and explicit paid-order safety are complete. | Partial (docs+tests) | 2026-06-25 |
| TASK-079 | NAIP Phase: keep documentation-only/reference-only unless Akasha supports US AOIs in a separate product scope. | Partial (docs+tests) | 2026-06-25 |

## 3. Alternatives

- **ALT-001**: Keep adding one systemd timer and one sync command per satellite. Rejected because it does not scale to 20 sources, duplicates provider logic, and makes monitoring fragmented.
- **ALT-002**: Build separate workers per provider with no common scheduler. Rejected because every provider still needs the same job lifecycle, locks, manifests, verification, and monitoring.
- **ALT-003**: Store all scheduling rules only in markdown docs. Rejected because operators need executable due-state logic and monitoring.
- **ALT-004**: Make frontend compute best satellite per date by fetching all source dates. Rejected because ranking must be shared by UI, BFF stats, exports, and monitoring.
- **ALT-005**: Implement all provider adapters before ISRO scheduler migration. Rejected because Bhoonidhi is already integrated and provides the safest first migration path.
- **ALT-006**: Auto-enable commercial providers once API credentials exist. Rejected because credentials alone do not prove contract, quota, pricing, product rights, or paid-order approval.
- **ALT-007**: Move immediately to a centralized SQL scheduler database. Deferred because JSON job artifacts plus the existing SQLite ledger are sufficient for first implementation; SQL tables can follow once job-history retention/UI requirements are stable.
- **ALT-008**: Treat archive-only sources as routine schedules. Rejected because archive sources do not produce new acquisitions and should run as explicit backfill/on-demand jobs.

## 4. Dependencies

- **DEP-001**: Existing ResourceSat LISS-3/LISS-4 ingestion and verification paths must remain healthy while migrating to the orchestrator.
- **DEP-002**: Bhoonidhi credentials and whitelisted staging egress (`20.219.3.35`) remain required for ISRO search/download.
- **DEP-003**: `/srv/akasha` staging storage remains required for all raster/raw/work/COG/job artifacts.
- **DEP-004**: Existing pgSTAC, MinIO, PostgreSQL/PostGIS, TiTiler, FastAPI BFF, and gateway services must stay reachable from ingestion jobs.
- **DEP-005**: CDSE provider implementation requires `CDSE_USERNAME`, `CDSE_PASSWORD`, optional `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID`, and optional CDSE S3 credentials.
- **DEP-006**: USGS/Landsat implementation requires a selected cloud STAC provider and optional USGS/Earthdata credentials depending on access path.
- **DEP-007**: Earthdata/ASF implementation requires `EARTHDATA_TOKEN` and selected DAAC access paths.
- **DEP-008**: Planet/JAXA/vendor implementations require commercial contracts, product bundle confirmation, quota policy, and operator approval.
- **DEP-009**: Sentinel-1 and other SAR processing requires the dedicated `ingestion-sar` runtime where SNAP/GPT is needed.
- **DEP-010**: NISAR remains data-gated until calibrated ARD products are available and validated.

## 5. Files

- **FILE-001**: `docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md` — This plan.
- **FILE-002**: `docs/reference/satellite-catalog.md` — Source inventory; update with ingestion state/cadence summaries.
- **FILE-003**: `docs/reference/satellite-ingestion-onboarding-matrix.md` — Provider/source feasibility; update with scheduler and adapter architecture.
- **FILE-004**: `docs/data-ingestion-and-satellite-rules.md` — Add scheduler, adapter, validation, promotion, and monitoring rules.
- **FILE-005**: `docs/staging-ingestion-developer-guide.md` — Add orchestrator operations and job inspection commands.
- **FILE-006**: `docs/impl-plan/data-multi-source-ingestion-roadmap-1.md` — Keep linked; update or reference this scheduler plan as the architecture prerequisite.
- **FILE-007**: `services/ingestion/akasha_ingest/pipeline_registry.py` — Current registry; extend or split for scheduling/source states.
- **FILE-008**: `services/ingestion/akasha_ingest/source_registry.py` — Optional new source-state registry if `pipeline_registry.py` becomes too large.
- **FILE-009**: `services/ingestion/akasha_ingest/providers/base.py` — New provider adapter protocol.
- **FILE-010**: `services/ingestion/akasha_ingest/providers/registry.py` — New provider factory.
- **FILE-011**: `services/ingestion/akasha_ingest/providers/bhoonidhi_adapter.py` — First provider adapter.
- **FILE-012**: `services/ingestion/akasha_ingest/providers/cdse_adapter.py` — Future CDSE adapter placeholder.
- **FILE-013**: `services/ingestion/akasha_ingest/providers/usgs_adapter.py` — Future USGS/cloud STAC adapter placeholder.
- **FILE-014**: `services/ingestion/akasha_ingest/providers/earthdata_adapter.py` — Future Earthdata adapter placeholder.
- **FILE-015**: `services/ingestion/akasha_ingest/providers/asf_adapter.py` — Future ASF/NISAR adapter placeholder.
- **FILE-016**: `services/ingestion/akasha_ingest/providers/planet_adapter.py` — Future Planet adapter placeholder.
- **FILE-017**: `services/ingestion/akasha_ingest/providers/jaxa_adapter.py` — Future JAXA adapter placeholder.
- **FILE-018**: `services/ingestion/akasha_ingest/providers/vendor_adapter.py` — Future VHR vendor adapter placeholder.
- **FILE-019**: `services/ingestion/akasha_ingest/manifests.py` — Canonical manifest schema, versioning, validation, migration, and redaction utilities.
- **FILE-020**: `services/ingestion/akasha_ingest/orchestrator.py` — Scheduler/orchestrator core.
- **FILE-021**: `services/ingestion/akasha_ingest/jobs.py` — Job artifact, scheduler snapshot, summary, and state management.
- **FILE-022**: `services/ingestion/akasha_ingest/validation_profiles.py` — Source-aware validation profiles.
- **FILE-023**: `services/ingestion/akasha_ingest/sync.py` — Reuse ledger/backfill/lock helpers; extend as needed.
- **FILE-024**: `services/ingestion/worker.py` — Add scheduler commands and compatibility aliases.
- **FILE-025**: `scripts/staging_ingestion_job.py` — Add job/schedule inspection commands.
- **FILE-026**: `infra/selfhosted/systemd/akasha-ingestion-scheduler.timer` — New scheduler timer.
- **FILE-027**: `infra/selfhosted/systemd/akasha-ingestion-scheduler.service` — New scheduler service.
- **FILE-028**: `infra/selfhosted/systemd/akasha-ingestion-scheduler.sh` — New scheduler wrapper.
- **FILE-029**: `infra/selfhosted/systemd/ingestion-scheduler.env.example` — New scheduler environment template.
- **FILE-030**: `apps/api/app/ingestion_jobs.py` — New monitoring jobs/schedules router.
- **FILE-031**: `apps/api/app/source_monitoring.py` — Extend source monitoring with schedule/job links.
- **FILE-032**: `apps/api/app/main.py` — Wire new BFF router.
- **FILE-033**: `apps/api/app/raster/catalog_resolver.py` — Add best-observation resolver and source state integration.
- **FILE-034**: `apps/frontend/src/types/api.ts` — Add job/schedule/best-observation types if UI is built.
- **FILE-035**: `apps/frontend/src/lib/api.ts` — Add monitoring job/schedule clients if UI is built.
- **FILE-036**: `apps/frontend/src/lib/queries.ts` — Add TanStack Query hooks if UI is built.
- **FILE-037**: `apps/frontend/src/pages/monitoring/IngestionJobsList.tsx` — Optional job list UI.
- **FILE-038**: `apps/frontend/src/pages/monitoring/IngestionJobDetail.tsx` — Optional job detail UI.
- **FILE-039**: `apps/frontend/src/pages/MapPage.tsx` — Future best-available timeline mode wiring.
- **FILE-040**: `apps/frontend/src/components/timeline/TimelineBar.tsx` — Future best/source timeline affordance.
- **FILE-041**: `apps/frontend/src/components/timeline/DateChip.tsx` — Future observation provenance display.
- **FILE-042**: `tests/test_satellite_catalog_registry.py` — New catalogue/source registry consistency tests.
- **FILE-043**: `tests/test_provider_adapter_contract.py` — New provider adapter tests.
- **FILE-044**: `tests/test_generic_scheduler_orchestrator.py` — New scheduler tests.
- **FILE-045**: `tests/test_ingestion_scheduler_systemd_artifacts.py` — New systemd scheduler artifact tests.
- **FILE-046**: `apps/api/tests/test_ingestion_jobs_monitoring.py` — New BFF monitoring tests.
- **FILE-047**: `tests/test_resourcesat_scheduler_invariants.py` — New ResourceSat LISS-3 scheduler/validation parity tests.

> **Shipped test-file names:** the scheduler tests landed under different filenames than the aspirational FILE-044/046/047 above. The actual shipped equivalents are [tests/test_scheduler_observability.py](../../tests/test_scheduler_observability.py) and [tests/test_phase7_bhoonidhi_scheduler.py](../../tests/test_phase7_bhoonidhi_scheduler.py) (orchestrator/observability + LISS-3 dry-run parity), [tests/test_scheduler_phase0_contracts.py](../../tests/test_scheduler_phase0_contracts.py) (Phase 0 contract), [tests/test_satellite_catalog_registry.py](../../tests/test_satellite_catalog_registry.py) + [tests/test_provider_adapter_contract.py](../../tests/test_provider_adapter_contract.py) (registry + adapters), and [apps/api/tests/test_ingestion_jobs.py](../../apps/api/tests/test_ingestion_jobs.py) (BFF monitoring). Substitute these names when running the suites in section 6.

## 6. Testing

- **TEST-001**: Run `python -m pytest tests/test_satellite_catalog_registry.py -q`. Expected: all 20 catalogue entries have typed source-state fields or explicit exclusion, invalid state combinations fail closed, and `mvp_enabled` compatibility remains derived and non-authoritative.
- **TEST-002**: Run `python -m pytest tests/test_provider_adapter_contract.py -q`. Expected: Bhoonidhi adapter works, unknown providers fail closed, and adapter result types cover pagination, rate-limit/backoff, idempotency, and order lifecycle metadata.
- **TEST-003**: Run `python -m pytest tests/test_generic_scheduler_orchestrator.py -q`. Expected: due-source selection, first-run behavior, dry-run behavior, host affinity, commercial blocks, archive/on-demand behavior, AWiFS gating, approved-runtime preflights, stale-lock reclaim, and concurrency limits pass.
- **TEST-004**: Run `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py tests/test_resourcesat_scheduler_invariants.py -q`. Expected: existing ResourceSat registry and Bhoonidhi tests remain green, and LISS-3 band/mask/scale/FCC/key/STAC invariants are preserved.
- **TEST-005**: Run `python -m pytest tests/test_ingestion_scheduler_systemd_artifacts.py tests/test_bhoonidhi_systemd_artifacts.py -q`. Expected: scheduler and compatibility systemd artifacts pass staging-safety assertions.
- **TEST-006**: Run `cd apps/api && python -m pytest tests/test_ingestion_jobs_monitoring.py tests/test_source_monitoring.py -q`. Expected: monitoring endpoints expose schedules/jobs from redacted snapshots, redact secrets, avoid raw path leakage, support filters/pagination, and preserve existing source monitoring behavior.
- **TEST-007**: Run `ruff check services/ingestion scripts apps/api`. Expected: no lint regressions.
- **TEST-008**: Run `python scripts/staging_ingestion_job.py trigger --host akasha-staging --source resourcesat-2a-liss3-boa --aoi bangalore-60km --dry-run --wait` using the safe wrapper. Expected: job succeeds without download/prepare/composite and artifacts are inspectable.
- **TEST-009**: Run scheduler dry-run for LISS-3, LISS-4, and AWiFS. Expected: LISS-3/LISS-4 active state is visible; AWiFS remains background/gated if coverage is not validated.
- **TEST-010**: Run `python scripts/staging_ingestion_job.py job-inspect <job_id> --host akasha-staging --json`. Expected: redacted request, status, counts, artifact handles/operator paths, and next due fields are returned.
- **TEST-011**: Run `python scripts/staging_ingestion_job.py schedule-plan --host akasha-staging --source resourcesat-2a-awifs-boa --aoi bangalore-60km --json`. Expected: plan explains whether AWiFS is due and why it remains gated/product-inactive.
- **TEST-012**: After API endpoints exist, call `GET /api/monitoring/ingestion-schedules`, `GET /api/monitoring/ingestion-jobs?limit=20`, and `GET /api/monitoring/ingestion-jobs/{jobId}` through the authenticated BFF. Expected: no secrets, no raw server paths in frontend-safe payloads, complete bounded troubleshooting context, and correct typed source states.
- **TEST-013**: If frontend monitoring UI is implemented, run `cd apps/frontend && corepack yarn test IngestionJobs MonitoringGlobalView` and `corepack yarn build`. Expected: job UI renders source/job states and TypeScript build passes.
- **TEST-014**: For best-observation work, run backend and frontend tests proving backend-owned selection is used for tiles/stats/exports and source-specific mode is preserved.

## 7. Risks & Assumptions

- **RISK-001**: The scheduler can become too broad if provider onboarding and scheduler architecture are implemented together. Mitigation: implement ISRO/Bhoonidhi adapter and scheduler first; add providers in later phases.
- **RISK-002**: Provider secrets and internal paths can leak through job artifacts. Mitigation: central redaction utilities, opaque artifact handles for API/UI, CLI-only or role-gated raw path access, and tests before monitoring endpoints are exposed.
- **RISK-003**: Commercial APIs can incur cost accidentally. Mitigation: commercial sources default to `commercial_blocked`; paid calls require explicit `--allow-paid-order` plus readiness record.
- **RISK-004**: Staging can be overloaded by high-resolution raster processing. Mitigation: safe wrapper only, bounded windows, global scheduler lock, source/AOI worker locks, max-concurrent-source limits, `ionice`/`nice`, and `/srv/akasha` storage rules.
- **RISK-005**: Source-state drift can occur between docs, ingestion registry, BFF registry, and STAC seed metadata. Mitigation: typed source-state schema, redacted scheduler snapshots, registry consistency tests, and mandatory doc updates.
- **RISK-006**: Non-ISRO providers have different pagination/auth/rate-limit/order behavior. Mitigation: typed provider adapter result objects own those details; scheduler uses canonical manifests and lifecycle states.
- **RISK-007**: SAR/context/archive products can be accidentally treated as optical sources. Mitigation: validation profiles, source kinds, and index registry tests.
- **RISK-008**: Best-observation ranking can mislead users if AWiFS/regional data is selected for small fields. Mitigation: exclude coarse/regional sources from small-field decisions unless explicitly allowed and labelled.
- **RISK-009**: JSON job artifacts may become hard to query at scale. Mitigation: start with JSON + SQLite for speed; migrate to SQL job tables when retention/UI requirements stabilize.
- **RISK-010**: Scheduler and legacy timers can double-run the same source during migration. Mitigation: Phase 0 source-ownership matrix, disabled/dry-run scheduler install, canary source cutover, shared lock namespace, and documented rollback.
- **RISK-011**: A crashed job can wedge a source with a stale lock. Mitigation: PID/timestamp lock payloads, TTL/liveness reclaim policy, and explicit tests.
- **RISK-012**: Generic scheduler/validation work can regress current ResourceSat LISS-3 production semantics. Mitigation: ResourceSat invariant tests are release-blocking before scheduler enablement.
- **ASSUMPTION-001**: `docs/reference/satellite-catalog.md` remains the canonical 20-platform catalogue.
- **ASSUMPTION-002**: `docs/reference/satellite-ingestion-onboarding-matrix.md` remains the canonical provider/onboarding feasibility reference.
- **ASSUMPTION-003**: ResourceSat LISS-3 remains the production default while scheduler and future providers are developed.
- **ASSUMPTION-004**: The first operational AOI remains `bangalore-60km`.
- **ASSUMPTION-005**: CLI/API monitoring is acceptable before building a full operator UI.

## 8. Related Specifications / Further Reading

- [Satellite Catalog & Selection Guide](../reference/satellite-catalog.md)
- [Satellite Ingestion Onboarding Matrix](../reference/satellite-ingestion-onboarding-matrix.md)
- [Data Ingestion and Satellite Rules](../data-ingestion-and-satellite-rules.md)
- [Staging Ingestion Developer Guide](../staging-ingestion-developer-guide.md)
- [Multi-Source Ingestion Roadmap](data-multi-source-ingestion-roadmap-1.md)
- [ResourceSat LISS-4/AWiFS Productionization Plan](data-resourcesat-liss4-awifs-productionization-1.md)
- [ISRO Bhoonidhi Ingestion Phase Plan](isro-bhoonidhi-ingestion-phase-plan.md)
- [Architecture and Tech Stack](../architecture-tech-stack.md)
- [Engineering Do's and Don'ts](../engineering-dos-donts.md)
- [EOS-04 SAR MRS L2B COG Prep Runbook](../eos04-sar-mrs-l2b-cog-prep-runbook.md)
- [NISAR SSAR Beta GCOV COG Prep Runbook](../nisar-ssar-beta-gcov-cog-prep-runbook.md)
- Copernicus Data Space APIs: https://documentation.dataspace.copernicus.eu/APIs.html
- CDSE STAC endpoint: https://stac.dataspace.copernicus.eu/v1/
- CDSE OData endpoint: https://catalogue.dataspace.copernicus.eu/odata/v1/
- Landsat Collection 2 L2 STAC metadata: https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2
- MODIS MOD13Q1 v061 STAC metadata: https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13Q1-061
- Planet APIs: https://docs.planet.com/develop/apis/