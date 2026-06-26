---
title: Satellite Ingestion Onboarding Matrix
status: reference
last_updated: 2026-06-25
owner: Akasha ingestion
related:
  - reference/satellite-catalog.md
  - reference/satellite-ingestion-scheduler-contracts.md
  - satellite-ingestion-orchestration-and-scheduler.md
  - data-ingestion-and-satellite-rules.md
  - impl-plan/data-multi-source-ingestion-roadmap-1.md
---

# Satellite Ingestion Onboarding Matrix

This document answers one question end-to-end: **can the ingestion pipeline we built for
ISRO ResourceSat-2A (Bhoonidhi → COG prep → composite → STAC → MinIO → BFF serving) be
reused for the other 19 satellites in [satellite-catalog.md](satellite-catalog.md)?**

The short answer: **the architecture is reusable, but the 20 platforms do not all ingest
the same way.** The work clusters by **data provider** (each needs its own search/download
client and authentication), not by individual satellite, and ~7 platforms are commercial —
no code can run until a licensing/tasking contract exists. This matrix captures, for every
platform: the official data-access method, authentication, product/band/mask structure,
India-AOI coverage, licensing, a feasibility verdict, and the exact code touchpoints to add it.

> Companion build plan: [data-multi-source-ingestion-roadmap-1.md](../impl-plan/data-multi-source-ingestion-roadmap-1.md).
> How the scheduler runs these sources and the add-a-satellite checklist:
> [satellite-ingestion-orchestration-and-scheduler.md](../satellite-ingestion-orchestration-and-scheduler.md).
> Hard rules that every new source must obey: [data-ingestion-and-satellite-rules.md](../data-ingestion-and-satellite-rules.md).

---

## 1. The reference pattern (how ResourceSat-2A works today)

Adding a satellite means satisfying the same nine layers that ResourceSat-2A already does.
A new platform is "ingestible the same way" only when each layer has an answer.

| # | Layer | File(s) | What it defines |
|---|---|---|---|
| 1 | Provider client | [services/ingestion/akasha_ingest/bhoonidhi.py](../../services/ingestion/akasha_ingest/bhoonidhi.py) | `search()` + `download_product()` + auth for one provider |
| 2 | Worker dispatch | [services/ingestion/worker.py](../../services/ingestion/worker.py) | Generic source/provider commands; **Bhoonidhi-specific today and must be generalized before non-ISRO onboarding** |
| 3 | Pipeline registry | [services/ingestion/akasha_ingest/pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) | `PipelineSource` capability row |
| 4 | Prepare script | [scripts/prepare_resourcesat_liss3_boa_cogs.py](../../scripts/prepare_resourcesat_liss3_boa_cogs.py) | raw product → `analytic.tif` + `mask.tif` + `prepare_manifest.json` |
| 5 | Scene/composite | [scene.py](../../services/ingestion/akasha_ingest/scene.py), [composite.py](../../services/ingestion/akasha_ingest/composite.py) | deterministic scene key + source-aware AOI composite profile or explicit no-composite policy |
| 6 | Catalog/STAC | [catalog.py](../../services/ingestion/akasha_ingest/catalog.py), [data/seed/stac/](../../data/seed/stac/) | STAC collection + item registration |
| 7 | Storage/verification | [storage.py](../../services/ingestion/akasha_ingest/storage.py), planned validation profiles | MinIO object upload + source-aware COG metadata validation (assets, band count, dtypes, mask classes, overviews) |
| 8 | BFF source registry | [apps/api/app/raster/catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) | `_SOURCE_REGISTRY` row: bands, display, mask, indices |
| 9 | Index registry | [apps/api/app/raster/indices.py](../../apps/api/app/raster/indices.py) | which indices the band roles support |

The frontend ([apps/frontend/](../../apps/frontend/)) is **fully data-driven** from `/api/sources`;
a standard optical/SAR source needs **zero** frontend code changes.

### 1.1 Scheduler source-state and provider-adapter model

The scheduler architecture in
[architecture-satellite-ingestion-scheduler-1.md](../impl-plan/architecture-satellite-ingestion-scheduler-1.md)
is the prerequisite for scaling this matrix beyond ResourceSat. The Phase 0 cross-service contract
is frozen in [satellite-ingestion-scheduler-contracts.md](satellite-ingestion-scheduler-contracts.md).
It introduces two hard contracts:

1. **Catalogue slug → source row mapping.** Every one of the 20 slugs in
  [satellite-catalog.md](satellite-catalog.md) must map to at least one source-state row or an
  explicit `out_of_aoi` / `reference_only` exclusion. One slug may map to multiple rows when
  products differ materially; ResourceSat-2A maps to LISS-3, LISS-4, and AWiFS.
2. **Provider adapters own provider behavior.** The scheduler decides due state, creates jobs,
  records artifacts, and dispatches pipeline stages. Provider adapters own auth, pagination,
  search, download/fetch, optional order/task, and provider-specific backoff.

Required source-state fields are `catalogSlug`, `catalogPlatform`, `sourceId`,
`providerAdapter`, `productFamily`, `instrumentMode`, `productVariant`, `analysisLevel`,
`lifecycleState`, `scheduleState`, `capabilities`, `productExposure`, `commercialState`,
`aoiScope`, `validationState`, `readinessReasons`, `validationProfile`, `cadence`, `hostPool`,
and `ownedBy`.

Invalid combinations fail closed. Examples: `commercial_blocked + order_enabled`,
`archive_only + routine schedule`, `background_only + product_active`, `out_of_aoi + selectable`,
and any executable row without a catalogue slug.

Phase 0 also defines job ownership, redacted snapshot paths, monitoring API boundaries, scheduler
ledger behavior, approved-runtime preflights, ResourceSat LISS-3 release-blocking invariants,
operator alert categories, and the legacy-timer versus scheduler ownership matrix. Later phases
must implement those contracts without changing frontend source ranking or mixed-source timelines.

| Provider adapter | Search | Download/fetch | Order/task | Runtime / gating |
|---|---:|---:|---:|---|
| `bhoonidhi` | ✅ | ✅ | ❌ | Staging safe-wrapper only for non-dry-run ISRO jobs. |
| `cdse` | ✅ | ✅ | ❌ | OAuth2/Keycloak; any approved worker host. |
| `usgs` | ✅ | ✅ cloud COG | ❌ | Prefer cloud-native STAC/COG; optional USGS/Earthdata auth. |
| `earthdata` / `asf` | ✅ | ✅ | ❌ | Earthdata token; source-specific DAAC access. |
| `planet` | ✅ | ✅ | ✅ | Commercial blocked until readiness + explicit paid-order flag. |
| `jaxa` | ✅/manual | ✅/manual | optional | Free mosaic possible; scenes commercial-gated. |
| `vendor` | provider-specific | provider-specific | ✅ | Commercial VHR disabled until contract/quota/readiness. |
| `usda`/`naip` | ✅ | ✅ | ❌ | Reference/out-of-AOI for India deployments. |

AWiFS is now the canonical regional/coarse ResourceSat product-active example: search/download/
prepare attempts run through the scheduler, validation uses a 60% minimum usable-coverage threshold,
and BFF exposure stays regional so field-level best-observation logic still prefers LISS-3/LISS-4.

**The single biggest blocker for non-ISRO platforms:** shared orchestration, not just a new
provider client. `worker.py` still instantiates `bhoonidhi.BhoonidhiClient()` directly in
its `bhoonidhi-*` subcommands, the sync path is ResourceSat-specific, `verify-composite`
validates ResourceSat mask/metadata assumptions, and the BFF currently prefers dated
composites only for ResourceSat BOA source IDs. Every non-ISRO provider (Copernicus,
USGS, NASA, Planet) therefore needs the shared enablement in the roadmap Phase 1–3:
source-state consistency, provider factory, canonical manifests, source-aware verification
profiles, fail-closed prepare dispatch, and generic composite/date serving.

### 1.2 Typed source-state field definitions

The table below is the canonical field set for every scheduler source row. Each field is
independent — do not overload any single field to cover multiple concerns such as
scheduling posture, product exposure, commercial readiness, and AOI applicability.
The authoritative contract for all fields is frozen in
[satellite-ingestion-scheduler-contracts.md](satellite-ingestion-scheduler-contracts.md).

| Field | Required values / shape | Contract |
|---|---|---|
| `catalogSlug` | `string` | Slug from [satellite-catalog.md](satellite-catalog.md). Required unless `internalLegacy=true`. |
| `catalogPlatform` | `string` | Human-readable platform name from the catalog. |
| `sourceId` | `string` | Akasha source id used by ingestion, STAC, and BFF source registries. |
| `providerAdapter` | `bhoonidhi`, `cdse`, `usgs`, `earthdata`, `asf`, `planet`, `jaxa`, `vendor`, `usda` | Adapter that owns provider auth, search, download, and order behavior. Unknown adapters fail closed. |
| `productFamily` | `optical_reflectance`, `sar_backscatter`, `precomputed_index`, `visual_context`, `archive_context` | Product family used to select prepare and validation profiles. |
| `instrumentMode` | `string` or `null` | Sensor/mode discriminator such as `LISS3`, `LISS4_MX70`, `AWIFS`, `IW_GRD`, or `OLI_TIRS`. |
| `productVariant` | `string` or `null` | Variant discriminator such as `BOA`, `L2A`, `L2B`, `GCOV`, `8DAY_NDVI`. |
| `analysisLevel` | `field`, `regional`, `context`, `archive`, `visual_only` | Tells product code how the source may be used. `field` is pixel-level analytics; `regional` is district/state scale; `context` is coarse reference; `archive` is historical backfill only; `visual_only` is display without per-band statistics. |
| `lifecycleState` | `catalogued`, `provider_configured`, `search_enabled`, `download_enabled`, `order_enabled`, `prepare_enabled`, `validate_enabled` | Highest lifecycle milestone reached. Does **not** by itself make a source schedulable or selectable. |
| `scheduleState` | `disabled`, `dry_run`, `manual_only`, `background_only`, `routine`, `archive_only` | Scheduler posture. `routine` means real recurring jobs are allowed after ownership cutover. `background_only` allows ingestion but keeps the source non-selectable. `archive_only` means on-demand/backfill only — never current-monitoring cadence. |
| `capabilities` | array of `search_enabled`, `download_enabled`, `order_enabled`, `prepare_enabled`, `validate_enabled` | Actions the scheduler may invoke for this source. Unsupported actions fail closed even if the provider adapter supports them. |
| `productExposure` | `hidden`, `background_only`, `product_active`, `reference_only` | Product/BFF exposure. `hidden` means not visible; `background_only` allows ingestion to run but the source is not user-selectable; `product_active` means the source appears in `/api/sources` and can be selected by users; `reference_only` means the source is documented and registry-mapped but never served as an active or background product for the deployment AOI. |
| `commercialState` | `free`, `approved`, `commercial_blocked` | Cost/licensing gate. Paid order paths additionally require an explicit operator `allowPaidOrder=true` flag. `commercial_blocked` is the default for all commercial/vendor sources. |
| `aoiScope` | `in_aoi`, `partial_aoi`, `out_of_aoi`, `reference_only` | Applicability to the deployment AOI. `out_of_aoi` means the platform does not cover the AOI at all. `reference_only` means the platform is documented for methodology reference but is not applicable or intended for this AOI deployment. Either value forces `productExposure=reference_only` and prevents routine scheduling. |
| `validationState` | `unvalidated`, `validation_pending`, `validation_failed`, `validation_passed` | Last accepted validation posture for the source/AOI/product profile. `validation_passed` is required before a source may enter `productExposure=product_active`. |
| `validationProfile` | `optical_composite`, `optical_scene`, `sar_backscatter`, `precomputed_context`, `archive_only`, `visual_only` | Validation rule set used by verification stages and release gates. SAR sources use `sar_backscatter`; precomputed-index sources use `precomputed_context`; archive sources use `archive_only`. `verify-composite` is only valid for `optical_composite` profiles. |
| `cadence` | object | Includes `intervalDays`, `lookbackDays`, `compositeWindowDays`, `maxDownloads`, rateLimitHints, and `firstRunPolicy`. Absence of a defined cadence, or a cadence with a routine interval, is invalid for `scheduleState=archive_only` rows. |
| `hostPool` | `staging_bhoonidhi`, `approved_worker`, `manual_only`, `none` | Runtime host class allowed for non-dry-run work. `staging_bhoonidhi` restricts execution to the IP-allow-listed staging VM. |
| `readinessReasons` | array of string codes | Machine-readable explanations for why a source is gated. Examples: `missing_credentials`, `coverage_below_threshold`, `commercial_approval_required`, `out_of_aoi`, `reference_only`, `awaiting_validation`, `data_not_yet_available`. |
| `ownedBy` | `legacy_timer`, `scheduler_dry_run`, `scheduler_active`, `manual_only` | Which entity currently owns scheduling for this source/AOI pair. Exactly one owner at a time per source/AOI. |

#### `reference_only` in detail

`reference_only` is a valid value in two independent fields with related but distinct meanings:

- **`aoiScope=reference_only`** — The platform is documented in the registry and maps to a catalog
  slug, but it does not apply to the current deployment AOI or is intentionally held as a reference
  methodology source only. For India (`bangalore-60km`) deployments this applies permanently to
  NAIP (US-only coverage). Setting `aoiScope=reference_only` **forces** `productExposure=reference_only`
  and blocks routine scheduling regardless of all other fields. The `readinessReasons` array must
  include `"out_of_aoi"` or `"reference_only"` to explain the exclusion.

- **`productExposure=reference_only`** — The product is never served as a selectable or
  background-ingested active product. Any source whose `aoiScope` is `out_of_aoi` or
  `reference_only` must also set `productExposure=reference_only`. A source may reach this
  state without `aoiScope=reference_only` when it is intentionally held back from product serving —
  for example, an experimental context-only source (such as MODIS NDVI) held as a coarse reference
  layer rather than an active field-analytics source.

The distinction matters for registry validation: a source with `aoiScope=in_aoi` but
`productExposure=reference_only` is valid (intentionally non-serving), while a source with
`aoiScope=reference_only` but `productExposure=product_active` is an **invalid combination** that
must be rejected at registry load time.

### 1.3 Source-state precedence and transition rules

The scheduler, BFF, and monitoring UI apply the following gates **in order**. Earlier gates are
never overridden by later gates.

1. **Unknown identifier fails closed.** Unknown `providerAdapter`, `sourceId`, or `catalogSlug`
   raises a registry error and the scheduler does not create a job. No fallback or default is applied.
2. **AOI scope gate.** `aoiScope=out_of_aoi` or `aoiScope=reference_only` forces
   `productExposure=reference_only` and prevents routine scheduling regardless of all other fields.
3. **Commercial gate.** `commercialState=commercial_blocked` disables `order_enabled` capabilities
   even when provider credentials exist. Credentials alone never make commercial actions executable.
4. **Validation gate.** `validationState != validation_passed` prevents promotion to
   `productExposure=product_active` for any user-selectable source.
5. **Schedule-disabled gate.** `scheduleState=disabled` wins over all capabilities — no provider
   actions run, no job records are created.
6. **Dry-run gate.** `scheduleState=dry_run` may create plans, job records, and redacted artifacts,
   but may **not** download, order, prepare COGs, composite, upload to MinIO, or register STAC items.
7. **Background-only gate.** `scheduleState=background_only` may run allowed non-commercial provider
   actions (search, download, prepare, validate), but the source remains non-selectable until a later
   validated product decision explicitly promotes `productExposure` to `product_active`.
8. **Archive-only gate.** `scheduleState=archive_only` only runs explicit backfill/on-demand windows;
   it **never** runs current-monitoring routine cadence jobs.

**Transition examples:**

- **AWiFS regional product-active path:**
  AWiFS now uses `scheduleState=routine`, `productExposure=product_active`, and
  `validationState=validation_passed` with a 60% regional usable-coverage threshold. It remains
  `analysisLevel=regional`, so it is selectable for regional/coarse context but is not a replacement
  for LISS-3/LISS-4 field-level monitoring.

- **New commercial source (e.g. PlanetScope) → approved path:**
  Default state is `commercialState=commercial_blocked` + `productExposure=hidden`. After a
  licence/quota approval, an operator sets `commercialState=approved`, adds `allowPaidOrder=true`,
  and promotes `scheduleState` from `disabled` to `background_only` or `routine` only once
  validation also passes.

- **Out-of-AOI reference source (NAIP) — permanent reference:**
  `aoiScope=reference_only` → `productExposure=reference_only` permanently for India deployments.
  No scheduler job is ever created for this source/AOI pair regardless of `scheduleState`.

- **Archive-only source (Landsat 5) → on-demand backfill:**
  `scheduleState=archive_only` + `analysisLevel=archive`. Only explicit operator-triggered backfill
  windows are allowed. No routine cadence interval is defined in `cadence`. The source never
  appears in current-monitoring timelines.

**Frontend note:** Source ranking, best-observation selection, and mixed-source timelines remain
unchanged by Phase 0/1 taxonomy work. The frontend derives all source/layer/date metadata from
`/api/sources` and the BFF. Multi-source best-observation selection and mixed-source trend
normalization are reserved for a later explicit phase as noted in the scheduler architecture plan.
Frontend source-specific timelines remain the serving source of truth until that phase.

### 1.4 Invalid state combinations

The following combinations are invalid and must be rejected by registry validation before any
scheduler job is created. A source row entering any of these states must be corrected by an
operator; the scheduler does not silently normalize or ignore them.

| Invalid combination | Why it fails |
|---|---|
| `commercialState=commercial_blocked` + `capabilities` containing `order_enabled` | Prevents accidental paid or commercial orders even when provider credentials are present. |
| `scheduleState=archive_only` + a routine cadence interval in `cadence` | Archive sources have no new acquisitions and must never run current-monitoring routine jobs. |
| `scheduleState=background_only` + `productExposure=product_active` | A background-only source cannot be user-selectable; product exposure must remain `background_only` or `hidden`. |
| `aoiScope=out_of_aoi` + `productExposure=product_active` | Out-of-AOI sources are reference-only for the deployment and cannot appear as selectable products. |
| `aoiScope=reference_only` + `productExposure=product_active` | `reference_only` AOI scope forces `productExposure=reference_only`; any `product_active` value on the same row is contradictory. |
| `validationState=validation_failed` + `productExposure=product_active` | A source with failed validation cannot be user-selectable; it must return to `background_only` or `hidden` until validation passes. |
| `scheduleState=routine` + `validationState=unvalidated` | Routine scheduling requires at least `validation_pending`; unvalidated sources must enter `background_only` or `manual_only` first. |
| `productExposure=background_only` + `scheduleState=disabled` | `background_only` implies ingestion may run; a fully disabled schedule must use `productExposure=hidden` instead. |
| Executable source row without `catalogSlug` and without `internalLegacy=true` | Every schedulable source must trace back to the satellite catalog; untraced rows fail closed. |
| `providerAdapter=vendor` + missing commercial readiness record | Commercial VHR vendor adapters are always `commercial_blocked` until a signed licence, quota, and readiness record are documented. |

**Key examples from the 20-platform catalog:**

- NAIP: `aoiScope=reference_only` → `productExposure=reference_only`. Invalid to set `productExposure=product_active` for any India deployment.
- Landsat 5 / Landsat 7: `scheduleState=archive_only`. Invalid to configure a routine cadence interval.
- PlanetScope / SkySat / VHR: `commercialState=commercial_blocked`. Invalid to include `order_enabled` in `capabilities`.
- AWiFS (pre-validation): `scheduleState=background_only` + `productExposure=background_only`. Invalid to set `productExposure=product_active` before `validationState=validation_passed`.

### 1.5 Provider adapter contract and responsibilities

Implemented by TASK-007 through TASK-012A in
[architecture-satellite-ingestion-scheduler-1.md](../impl-plan/architecture-satellite-ingestion-scheduler-1.md).
The canonical code lives in
[services/ingestion/akasha_ingest/providers/](../../services/ingestion/akasha_ingest/providers/).

#### 1.5.1 `ProviderAdapter` base contract

Every provider adapter must satisfy the `ProviderAdapter` protocol defined in
[providers/base.py](../../services/ingestion/akasha_ingest/providers/base.py).
The contract specifies:

| Method | Required | Responsibility |
|---|---|---|
| `search(request)` | **Required** | Execute a provider-specific STAC/API search; return a `SearchResult` with a page of `CandidateItem` objects, `PaginationMeta`, and `RateLimitMeta`. Must handle pagination, token-refresh hooks, and rate-limit/backoff metadata. |
| `normalize_candidate(item, source_id, request)` | **Required** | Translate a raw `CandidateItem` to a `NormalizedCandidate`. Derives the deterministic `item_id`, `acquisition_datetime`, `bbox`, AOI intersection flag, cloud cover, online status, cost estimate, and provider extra fields. |
| `download(request)` | **Required** | Download one product to `dest_dir`; return a `DownloadResult` with local path, bytes downloaded, `ResumableState` (idempotency, attempt count), and rate-limit metadata. Must honour `dry_run=True` without making network calls. |
| `order(request)` | Optional | Place a commercial tasking/order; return an `OrderResult` with `OrderState` lifecycle. **Must not be called unless `order_enabled` is in the source capabilities.** Non-order adapters must raise `ProviderActionUnsupported`. |
| `poll_order(provider_order_id)` | Optional | Poll the status of a placed order; return `OrderPollResult`. Adapters that do not support orders raise `ProviderActionUnsupported`. |
| `cancel_order(provider_order_id)` | Optional | Cancel a pending order; return `OrderCancelResult`. Adapters that do not support orders raise `ProviderActionUnsupported`. |
| `close()` | Optional | Release any held session/connection resources (idempotent). Called by the orchestrator after each job. |

The protocol is **synchronous-first** — all methods are blocking; async wrapping is the
responsibility of the orchestrator, not the adapter. No network calls may be made in `__init__`
or at import time.

#### 1.5.2 Provider-specific logic belongs entirely behind adapters

The scheduler, orchestrator, and worker dispatch layer must never contain provider-specific
auth, pagination, API URLs, credential handling, backoff algorithms, or product-download logic.
All of that belongs exclusively in the concrete adapter class:

- **Auth:** token acquisition, refresh, expiry, and credential-lookup from environment variables
  or secrets must be handled inside the adapter's `search`, `download`, or a lazy `_get_client()`
  helper. The orchestrator sees only `ProviderAuthError` when auth fails.
- **Pagination:** multi-page search results must be resolved inside `search()`; the return type is
  always a single `SearchResult` page with `PaginationMeta` (the orchestrator may call `search`
  again with a next-page token if needed, but the provider API pagination is transparent).
- **Download logic:** resume behaviour, size calculation, content-disposition parsing, checksum
  verification, and provider-specific download URLs are owned by `download()`.
- **Order lifecycle:** order submission, status polling, and cancellation are owned by `order()`,
  `poll_order()`, and `cancel_order()`. The orchestrator only interacts with `OrderState` enum
  values.

#### 1.5.3 Fail-closed contract for unknown providers and unsupported methods

Two complementary fail-closed mechanisms ensure the system never silently proceeds with an
unrecognised or unsupported action:

1. **Unknown provider** — `get_provider_adapter(provider)` in
   [providers/registry.py](../../services/ingestion/akasha_ingest/providers/registry.py)
   raises `UnknownProviderError` for any key not registered in `_PROVIDER_MAP`. There is no
   silent fallback or `None` return. The scheduler must not create a job for an unrecognised
   provider.

2. **Unsupported optional method** — When a concrete adapter does not implement an optional
   method (`order`, `poll_order`, `cancel_order`), the default stub inherited from
   `PlaceholderAdapterBase` (or the explicit override in the concrete class) raises
   `ProviderActionUnsupported(adapter_name, action)`. The source capabilities list must not
   advertise an action unless the adapter fully implements it.

Both exception classes inherit from `ProviderError` so callers can catch either specifically
or the base class for uniform error handling.

#### 1.5.4 Commercial paid-order preflight

Commercial `order` / `task` calls require **all three** of the following before any
cost-incurring API call is made:

1. `commercialState=approved` on the source-state row — `commercial_blocked` is the default
   for all commercial/vendor sources and must be explicitly flipped by an operator.
2. `allowPaidOrder=True` on the `OrderRequest` — an explicit per-call opt-in from the operator.
3. A valid `commercial_readiness_record_id` on the `OrderRequest` — a documented licence/quota
   reference that proves the commercial contract exists.

The helper `assert_commercial_ready(adapter_name, source_id, allow_paid_order,
commercial_readiness_record_id, commercial_state)` in `base.py` enforces this preflight and
raises `CommercialPreflightFailed` if any criterion is missing. All commercial placeholder
adapters (`CommercialPlaceholderAdapterBase`) call `assert_commercial_ready` inside `order()`
with `commercial_state="commercial_blocked"`, guaranteeing that paid orders fail closed even
before a real implementation exists.

#### 1.5.5 Bhoonidhi adapter — wraps existing client, preserves worker behaviour

[providers/bhoonidhi_adapter.py](../../services/ingestion/akasha_ingest/providers/bhoonidhi_adapter.py)
is a **thin wrapper** around the existing
[BhoonidhiClient](../../services/ingestion/akasha_ingest/bhoonidhi.py). It does not refactor
the underlying client; it only adapts its interface to the `ProviderAdapter` protocol:

- `search()` calls `BhoonidhiClient.search()` with the AOI geometry, datetime range, and
  collection derived from the `SearchRequest`, then converts each raw item through
  `candidate_from_item()` into `CandidateItem` objects.
- `normalize_candidate()` derives a deterministic `item_id` from the provider item ID (already
  encoded with satellite/date/tile in ISRO naming) and computes the AOI intersection flag.
- `download()` delegates to `BhoonidhiClient.download_product()`, maps `BhoonidhiAuthError` →
  `ProviderAuthError`, `BhoonidhiDownloadUnavailable` → a failed `DownloadResult` (not an
  exception, to allow per-item retry), and `BhoonidhiError` with `429`/`rate` → `ProviderRateLimitError`.
- `close()` calls `BhoonidhiClient.logout(ignore_errors=True)` idempotently.
- `order()`, `poll_order()`, `cancel_order()` all raise `ProviderActionUnsupported("bhoonidhi", …)` —
  Bhoonidhi is a free direct-download catalogue with no commercial order workflow.
- The constructor accepts an injected `BhoonidhiClient`-compatible stub for unit tests without
  hitting the real API.

Existing `worker.py` `bhoonidhi-*` subcommands continue to instantiate `BhoonidhiClient`
directly; the adapter is introduced for the **scheduler code path** only. There is no breakage
of existing worker behaviour until a later scheduler ownership cutover (Phase 7 parity tests
gate that transition; see TASK-026).

#### 1.5.6 Future provider placeholders

[providers/_placeholder.py](../../services/ingestion/akasha_ingest/providers/_placeholder.py)
provides two shared base classes:

- **`PlaceholderAdapterBase`** — for free/open data providers (`cdse`, `usgs`, `earthdata`,
  `asf`, `jaxa`, `usda`). Every required and optional method raises `ProviderActionUnsupported`
  until the provider phase begins and a real implementation replaces the placeholder. `close()`
  is a safe no-op.
- **`CommercialPlaceholderAdapterBase`** — for commercial providers (`planet`, `vendor`).
  Inherits `PlaceholderAdapterBase` and overrides `order()` to call `assert_commercial_ready`
  with `commercial_state="commercial_blocked"` before raising `ProviderActionUnsupported`.
  This guarantees `CommercialPreflightFailed` for any order attempt regardless of credentials.

The concrete placeholder files
(`cdse_adapter.py`, `usgs_adapter.py`, `earthdata_adapter.py`, `asf_adapter.py`,
`planet_adapter.py`, `jaxa_adapter.py`, `vendor_adapter.py`, `usda_adapter.py`)
each subclass the appropriate base with an `adapter_name` override. They exist so that
`get_provider_adapter()` can return a real (non-`None`) object for every registered provider
key and the fail-closed contract is uniform: unknown providers raise `UnknownProviderError`;
known-but-not-yet-implemented providers raise `ProviderActionUnsupported` on every call.

---

## 2. Feasibility tiers — all 20 at a glance

| Tier | Meaning | Platforms |
|---|---|---|
| **T1 — Free, buildable now** | Open API + free data; ingest like ResourceSat once the provider client exists | Sentinel-2, Sentinel-1, Landsat 8, Landsat 9, MODIS, EOS-04, EOS-06, NISAR, **ResourceSat-2A LISS-3 ✅ active baseline; LISS-4 ✅ active field enhancement; AWiFS ✅ active regional** |
| **T2 — Free, archive-only** | Free but no new acquisitions (history only) | Landsat 7, Landsat 5, IRS-1C |
| **T3 — Commercial / paid** | API exists but gated behind a licensing/tasking contract + cost | PlanetScope, SkySat, SuperView NEO-1, BlackSky Gen 3, KOMPSAT-3A, ALOS-2, Cartosat-3 |
| **T4 — Free but out-of-AOI** | Free + open but does not cover India | NAIP (US-only) |

**Count check:** T1 = 9, T2 = 3, T3 = 7, T4 = 1 → **20**.

### 2.1 Master matrix

| Platform | Provider | Access | Auth | Optical/SAR | India AOI | New client? | Verdict |
|---|---|---|---|---|---|---|---|
| ResourceSat-2A LISS-3 BOA | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | ✅ Active baseline |
| ResourceSat-2A LISS-4 MX70 L2 | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | ✅ Active field enhancement |
| ResourceSat-2A AWiFS BOA | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | ✅ Active regional/coarse |
| Sentinel-2 L2A | ESA CDSE | Free | OAuth2 (Keycloak) | Optical | ✅ | **cdse** | 🟢 Buildable |
| Sentinel-1 GRD | ESA CDSE | Free | OAuth2 (Keycloak) | SAR | ✅ | **cdse** | 🟢 Buildable |
| Landsat 8 | USGS/NASA | Free | ERS / Earthdata / none (cloud) | Optical | ✅ | **usgs** | 🟢 Buildable |
| Landsat 9 | USGS/NASA | Free | ERS / Earthdata / none (cloud) | Optical | ✅ | **usgs** | 🟢 Buildable |
| MODIS (Terra/Aqua) | NASA LP DAAC | Free | Earthdata Login | Optical (250 m) | ✅ regional | **earthdata** | 🟢 Buildable (context) |
| EOS-04 (RISAT) | ISRO Bhoonidhi | Free (MRS/CRS) | Password + IP allow-list | SAR | ✅ | reuse | 🟡 Gated (scaffolded) |
| EOS-06 (OceanSat-3) | ISRO Bhoonidhi | Free | Password + IP allow-list | Optical (360 m) | ✅ regional | reuse | 🟡 Gated (scaffolded) |
| NISAR | ISRO Bhoonidhi / NASA ASF | Free | Password + IP allow-list / Earthdata | SAR | ✅ | reuse / **asf** | 🟡 Data-gated (~Jul 2026) |
| Landsat 7 | USGS/NASA | Free | ERS / none (cloud) | Optical | ✅ archive | **usgs** | 🟤 Archive-only |
| Landsat 5 | USGS/NASA | Free | ERS / none (cloud) | Optical | ✅ archive | **usgs** | 🟤 Archive-only |
| IRS-1C | ISRO Bhoonidhi/NRSC | Free | Password + IP allow-list | Optical | ✅ archive | reuse | 🟤 Archive-only (scaffolded) |
| PlanetScope | Planet Labs | **Commercial** | API key | Optical | ✅ tasking/sub | **planet** | 🔴 Licensing-gated |
| SkySat | Planet Labs | **Commercial** | API key | Optical | ✅ tasking | **planet** | 🔴 Licensing-gated |
| SuperView NEO-1 | SIIS (China) | **Commercial** | reseller API | Optical | ✅ tasking | **vendor** | 🔴 Licensing-gated |
| BlackSky Gen 3 | BlackSky | **Commercial** | Spectra API key | Optical | ✅ tasking | **vendor** | 🔴 Licensing-gated |
| KOMPSAT-3A | KARI / SIIS | **Commercial** | reseller API | Optical | ✅ tasking | **vendor** | 🔴 Licensing-gated |
| ALOS-2 (PALSAR-2) | JAXA | Commercial scenes / free mosaic | G-Portal / reseller | SAR | ✅ | **jaxa** | 🔴 Scenes paid; mosaic free |
| Cartosat-3 | ISRO NSIL | GE free / NGE paid | NSIL licence | Optical | ✅ | n/a (no API) | 🔴 No catalog API path |
| NAIP | USDA | Free | none (cloud) | Optical | ❌ US-only | **usda** | ⚪ Out-of-AOI |

Legend: ✅ done · 🟢 free buildable · 🟡 gated (partly scaffolded) · 🟤 archive-only · 🔴 commercial/blocked · ⚪ not applicable to AOI.

---

## 3. Per-provider deep dives

Each section gives the provider's access model, then an exhaustive per-platform entry, then
the **code-touchpoint checklist** (the files to add/edit for that provider).

### A. ISRO / NRSC Bhoonidhi — client already exists

**Access model.** STAC-style API at `https://bhoonidhi-api.nrsc.gov.in`. Auth: `POST /auth/token`
(password grant, access token TTL ~20 min + refresh token; max-session cap). Search: `POST /data/search`
(STAC: `collections`, `datetime`, `bbox`, `intersects`, CQL2-JSON `filter` with `Online=Y`). Download:
`GET /download?id=&collection=` (Bearer). **IP allow-listed** — search/download run **only** from the
Akasha staging VM (egress `20.219.3.35`); see [staging-ingestion-developer-guide.md](../staging-ingestion-developer-guide.md).
Client + contract already implemented in [bhoonidhi.py](../../services/ingestion/akasha_ingest/bhoonidhi.py).

> Verified 2026-06-14: the Bhoonidhi catalog contains `ResourceSat-2A_LISS3_BOA` and the other
> ResourceSat/EOS collections, but **Cartosat-3 is absent** (only a CartoSat-1 DEM collection exists).

#### A.1 ResourceSat-2A variants — LISS-3, LISS-4, and AWiFS active

| Field | Value |
|---|---|
| Status / tier | LISS-3: active baseline · LISS-4: active field enhancement · AWiFS: active regional/coarse |
| Collections | `ResourceSat-2A_LISS3_BOA`, `ResourceSat-2A_LISS4-MX70_L2`, `ResourceSat-2A_AWIFS_BOA` |
| Product / format | Bottom-of-atmosphere reflectance; raw uint16 DN GeoTIFF (`BAND2/3/4/5.tif`) |
| Analytic bands | LISS-3/AWiFS: `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`; LISS-4: `[BAND2 Green, BAND3 Red, BAND4 NIR]` |
| Reflectance | `corrected = dn * 0.0001 + 0.0` (offset **0.0**, not Sentinel's −0.1) |
| Mask | **No native SCL** → Akasha threshold mask v1 (`0=nodata,1=valid,2=cloud,3=shadow,4=water`; keep `{1,4}`) |
| Resolution / revisit / swath | 23.5 m (LISS-3) / 5.8 m (LISS-4) / 56 m (AWiFS) · 5 d · 70–141 km |
| Display | **FCC** (NIR,RED,GREEN → `bidx=3,2,1`); LISS-4 FCC; AWiFS FCC |
| Indices | NDVI, MSAVI, NDMI, NDWI_GREEN_NIR (LISS-4: no NDMI — no SWIR; no NDRE — no red edge) |
| India AOI | ✅ `bangalore-60km` |
| Licensing | Redistribution approved by Bhoonidhi; attribute "ISRO-IRS, ISRO/NRSC, Bhoonidhi" |
| Verdict | Variant-specific: LISS-3 is the verified reference implementation; LISS-4 is active as a high-resolution field enhancement where verified coverage exists; AWiFS is active for regional/coarse analytics with a 60% minimum usable-coverage threshold. |

#### A.2 EOS-04 (RISAT) — 🟡 gated, scaffolded

| Field | Value |
|---|---|
| Status / tier | Live · **T1 SAR** (gated) |
| Collection | `EOS-04_SAR-MRS_L2B` (MRS/CRS modes free; **FRS-1 fine modes are not free**) |
| Product / format | C-band SAR, L2B geocoded/terrain-corrected backscatter GeoTIFF (no SNAP needed) |
| Bands | 1–2 pol backscatter (`HH`/`HV`/`VH`/`VV`/`RH`/`RV`); convert to dB |
| Mask | None (SAR) |
| Resolution / revisit / swath | 1–50 m (mode-dependent) · 12 d · 25–223 km |
| Display | `VV_GRAYSCALE` (SAR; never an optical index) |
| Indices | **None** (SAR is never an optical-index source) |
| India AOI | ✅ |
| Already in repo | [prepare_eos04_sar_mrs_l2b_cogs.py](../../scripts/prepare_eos04_sar_mrs_l2b_cogs.py), [eos-04-sar-mrs-l2b-collection.json](../../data/seed/stac/eos-04-sar-mrs-l2b-collection.json), pipeline-registry row (`mvp_enabled=False`) |
| Remaining work | Flip search/download on; sample a real product (`gdalinfo`) to confirm pol order/scale; staging dry-run → capped run → source-aware SAR verification (`verify-raster-product`, not `verify-composite`) |
| Verdict | **Gated** — prep script + STAC scaffolded; needs validation runs |

#### A.3 EOS-06 (OceanSat-3) — 🟡 gated, scaffolded

| Field | Value |
|---|---|
| Status / tier | Live · **T1 context** (gated) |
| Collection | EOS-06 OCM LAC NDVI (`eos-06-ocm-lac-ndvi-8day-360m`) |
| Product / format | OCM-3 **precomputed 8-day NDVI**, ~360 m |
| Bands | Precomputed NDVI grid (not raw reflectance → not Akasha band-stats) |
| Mask | Product quality flags |
| Resolution / revisit / swath | 360 m · 2 d · 1440 km |
| Display | NDVI context ramp (coarse) — **regional context only, not field-level stats** |
| Indices | Provider NDVI only (no per-band recompute) |
| India AOI | ✅ regional |
| Already in repo | [eos-06-ocm-lac-ndvi-8day-360m-collection.json](../../data/seed/stac/eos-06-ocm-lac-ndvi-8day-360m-collection.json) (gated) |
| Verdict | **Gated** — coarse precomputed NDVI context; not a field-analytics source |

#### A.4 NISAR — 🟡 data-gated (also via NASA ASF, see §D)

| Field | Value |
|---|---|
| Status / tier | Launched 2025-07-30 · **T1 SAR** (data-gated) |
| Collection | `NISAR_SSAR-Beta_GCOV` (Bhoonidhi) / ASF DAAC GCOV |
| Product / format | **GCOV** (Geocoded Polarimetric Covariance), gamma-0 power, terrain-corrected; HDF5/GeoTIFF |
| Bands | Covariance diagonal per polarization → dB |
| Mask | None (SAR) |
| Resolution / revisit / swath | 3–10 m · 12 d · 240 km · L+S band |
| Display | `VV_GRAYSCALE`-style SAR |
| Indices | **None** (SAR) |
| Data readiness | Pre-cal sample released Feb 2026; **full calibrated global release ~Jul 2026** |
| Already in repo | [prepare_nisar_ssar_beta_gcov_cogs.py](../../scripts/prepare_nisar_ssar_beta_gcov_cogs.py), [nisar-ssar-beta-gcov-collection.json](../../data/seed/stac/nisar-ssar-beta-gcov-collection.json) (gated) |
| Verdict | **Gated by data availability** — revisit once ARD ships (~Jul 2026) |

#### A.5 IRS-1C — 🟤 archive-only, scaffolded

| Field | Value |
|---|---|
| Status / tier | Archive 1995–2007 · **T2** |
| Collection | `irs-1c-liss3-archive` |
| Product / format | LISS-3 archive: Green, Red, NIR, SWIR (+ Pan 5.8 m) |
| Mask | None native (Akasha threshold mask if exposed) |
| Resolution / revisit | 23 m (LISS-3) / 5.8 m (Pan) · 24 d (historical) |
| Indices | NDVI, NDMI, NDWI (no red edge) |
| India AOI | ✅ historical baselines |
| Already in repo | [irs-1c-liss3-archive-collection.json](../../data/seed/stac/irs-1c-liss3-archive-collection.json) (gated) |
| Verdict | **Archive-only** — useful for 1995–2007 baselines; no new acquisitions |

#### A.6 Cartosat-3 — 🔴 no catalog API path

| Field | Value |
|---|---|
| Status / tier | Live · **T3 commercial/gated** |
| Access | **Absent from the Bhoonidhi search catalog.** Indian Space Policy 2023: **free for Government Entities on declaration; priced via NSIL for Non-Government Entities** |
| Product / format | 0.25 m Pan + 4-band (Blue, Green, Red, NIR) MS |
| Display | True-colour / pan-sharpened VHR **visual context only** |
| Indices | Pan-sharpened NDVI at best (no SWIR/red edge) |
| India AOI | ✅ (tasking/archive via NSIL licence) |
| Already in repo | [cartosat-3-gated-collection.json](../../data/seed/stac/cartosat-3-gated-collection.json) (gated placeholder) |
| Verdict | **Blocked** — no programmatic catalog/download path until NRSC/NSIL access + product format confirmed; treat as manual VHR context |

#### Provider A code checklist (per new Bhoonidhi source — EOS-04/06, NISAR, IRS-1C)
- [x] Provider client — **reuse** [bhoonidhi.py](../../services/ingestion/akasha_ingest/bhoonidhi.py) (`SOURCE_COLLECTIONS` already maps these)
- [ ] [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) — flip `supports_search/download/composite` + `mvp_enabled` when validated
- [x] Prepare script — exists for EOS-04 + NISAR; needed for EOS-06/IRS-1C if exposed as analytics
- [ ] [scene.py](../../services/ingestion/akasha_ingest/scene.py) — confirm collection alias + scene-key regex
- [ ] [composite.py](../../services/ingestion/akasha_ingest/composite.py) — SAR/context sources skip optical compositing (`supports_composite=False`); optical sources use source-specific composite profiles
- [x] STAC seed collection — exists for all four
- [ ] [catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) `_SOURCE_REGISTRY` — confirm display/mask/index row, `availabilityStatus`
- [ ] Validation: staging dry-run → `--max-downloads 1` → source-appropriate verification (`verify-raster-product` for SAR/context/archive, `verify-composite` only for optical composites)

---

### B. ESA Copernicus Data Space Ecosystem (CDSE) — new `cdse` client

**Access model.** **Free, open.** Multiple catalog APIs, all on one DB:
[OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html),
[STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html),
[S3](https://documentation.dataspace.copernicus.eu/APIs/S3.html) (parallel bulk),
plus Sentinel Hub / openEO processing APIs. Auth: **OAuth2 access token** (Keycloak,
`POST .../protocol/openid-connect/token`, normally using `client_id=cdse-public` with username/password
or an existing access/refresh token; generated S3 credentials are separate for EOData S3) — see
[Token docs](https://documentation.dataspace.copernicus.eu/APIs/Token.html). **No IP allow-list** —
can run from staging or any worker host with credentials. The repo already has legacy
download + prepare scripts ([download_sentinel2_l2a_product.py](../../scripts/download_sentinel2_l2a_product.py),
[prepare_sentinel2_l2a_cogs.py](../../scripts/prepare_sentinel2_l2a_cogs.py),
[prepare_sentinel1_grd_cogs.py](../../scripts/prepare_sentinel1_grd_cogs.py)).

#### B.1 Sentinel-2 L2A — 🟢 buildable (lowest lift)

| Field | Value |
|---|---|
| Status / tier | Live · **T1, full optical** |
| Collection / product | `SENTINEL-2` L2A (BOA, Sen2Cor); SAFE ZIP or COG (cloud STAC) |
| Bands (native) | B01 coastal 60 m · B02 blue 10 m · B03 green 10 m · B04 red 10 m · B05/B06/B07 red-edge 20 m · B08 NIR 10 m · B8A red-edge 20 m · B09 water-vapor 60 m · B11 SWIR1 20 m · B12 SWIR2 20 m |
| Akasha analytic order | Frozen 9-band `[B04, B08, B05, B06, B07, B11, B12, B03, B02]` (already in [indices.py](../../apps/api/app/raster/indices.py)) |
| Reflectance | `dn * 0.0001 - 0.1` (offset **−0.1**; baseline ≥ 04.00 carries `BOA_ADD_OFFSET`) |
| Mask | **Native SCL** (`scl` asset); exclude classes `[0,1,2,3,7,8,9,10,11]`, keep water 6 |
| Resolution / revisit / swath | 10 m · 2–5 d · 290 km |
| Display | RGB true-colour (`[B04,B03,B02]`) |
| Indices | NDVI, MSAVI, **NDRE**, NDMI, NDWI_GREEN_NIR (only source with a true red-edge) |
| India AOI | ✅ |
| Licensing | Free; "Copernicus Sentinel-2" attribution |
| Verdict | **Buildable** — registry row + legacy scripts already exist (`sentinel-2-l2a`); needs the `cdse` search/download client and operator validation, while remaining non-production-selectable by default |

#### B.2 Sentinel-1 GRD — 🟢 buildable (SAR)

| Field | Value |
|---|---|
| Status / tier | Live · **T1 SAR** |
| Collection / product | `SENTINEL-1` Level-1 **GRD** (detected amplitude, ground-range, WGS84) |
| Bands | C-band (5.405 GHz) backscatter, pol `VV+VH` (IW), also `HH/HV`; modes IW/EW/SM |
| Processing | GRD is **not terrain-corrected** → ESA SNAP GPT terrain+radiometric correction → σ⁰/γ⁰ dB ([prepare_sentinel1_grd_cogs.py](../../scripts/prepare_sentinel1_grd_cogs.py)) |
| Mask | None (SAR) |
| Resolution / revisit / swath | ~20 m (10 m pixel) · 6–12 d · 250 km |
| Display | `VV_GRAYSCALE` (`defaultRescale=-25,5`) |
| Indices | **None** (SAR); RVI/VV-VH ratio possible as a future SAR-only layer |
| India AOI | ✅ |
| Verdict | **Buildable** — registry row exists (`sentinel-1-grd`); needs `cdse` client + existing `ingestion-sar` SNAP runtime validation |

#### Provider B code checklist (`cdse`)
- [ ] **New client** `services/ingestion/akasha_ingest/cdse.py` — OAuth2 token + current OData/STAC `search()` + S3/OData `download_product()`; mirror the normalized provider contract; do not use deprecated OpenSearch or legacy STAC endpoints
- [ ] [worker.py](../../services/ingestion/worker.py) — shared orchestration so `--source sentinel-2-l2a` dispatches to `cdse` via provider factory, canonical manifests, and source-aware verification (shared enablement, see §4)
- [ ] [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) — set `provider="cdse"`, flip `supports_*`/`mvp_enabled` after validation
- [x] Prepare scripts — exist (S2 9-band+SCL; S1 SNAP+dB)
- [ ] [composite.py](../../services/ingestion/akasha_ingest/composite.py) — S2 optical composite profile; S1 `supports_composite=False`
- [x] STAC + BFF registry rows — exist (`sentinel-2-l2a`, `sentinel-1-grd`)
- [ ] Env/secrets — `CDSE_USERNAME`, `CDSE_PASSWORD`, optional `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID=cdse-public`, and optional `CDSE_S3_ACCESS_KEY`/`CDSE_S3_SECRET_KEY`; Sentinel-1 SNAP runs in `ingestion-sar`
- [ ] Validation: dry-run → capped run → `verify-composite` for Sentinel-2 composites; `verify-raster-product` for Sentinel-1 SAR backscatter

---

### C. USGS / NASA — Landsat Collection 2 Level-2 — new `usgs` client

**Access model.** **Free, public domain.** Three access paths:
1. **USGS M2M API** (`https://m2m.cr.usgs.gov/api/`) — JSON machine-to-machine; needs an
   ERS (EROS Registration System) login + M2M access grant.
2. **USGS EarthExplorer** portal (manual).
3. **Cloud-native STAC + COG** (recommended) — Landsat C2 L2 is **already COG**, queryable via
   Microsoft Planetary Computer (`landsat-c2-l2`), Element84 Earth Search, USGS Landsat STAC,
   or AWS. The cloud path needs **no SNAP/GDAL transform** — just clip + restack.

Surface-reflectance bands carry `scale=0.0000275, offset=-0.2, nodata=0` (uint16, 30 m);
`qa_pixel` is the bit-packed CFMask QA (cloud / cloud-shadow / snow / water / dilated-cloud).
One STAC collection (`landsat-c2-l2`) spans Landsat 4/5/7/8/9 (instruments TM, ETM+, OLI, TIRS).

#### C.1 Landsat 8 / C.2 Landsat 9 — 🟢 buildable

| Field | Value |
|---|---|
| Status / tier | Live · **T1 optical** |
| Product / format | Collection 2 Level-2 **Surface Reflectance** (+ Surface Temperature); **COG** |
| Bands (OLI) | `coastal(SR_B1) · blue(SR_B2) · green(SR_B3) · red(SR_B4) · nir08(SR_B5) · swir16(SR_B6) · swir22(SR_B7)`; thermal `lwir11(ST_B10)` |
| Akasha analytic order (proposed) | `[green, red, nir08, swir16]` to match the ResourceSat role layout (Green,Red,NIR,SWIR1) |
| Reflectance | `dn * 0.0000275 - 0.2` |
| Mask | **`qa_pixel`** bit-packed → derive Akasha categorical mask (cloud=bit3, shadow=bit4, snow=bit5, water=bit7, dilated=bit1) |
| Resolution / revisit / swath | 30 m · 16 d (8+9 paired ≈ 8 d) · 185 km |
| Display | RGB true-colour (`[red, green, blue]`) |
| Indices | NDVI, MSAVI, NDMI, NDWI_GREEN_NIR (**no NDRE** — no red edge) |
| India AOI | ✅ |
| Licensing | Public domain (USGS); "USGS/NASA Landsat" attribution |
| Verdict | **Buildable** — cloud STAC+COG path is low-friction; no SNAP |

#### C.3 Landsat 7 / C.4 Landsat 5 — 🟤 archive-only

| Field | Value |
|---|---|
| Status / tier | Archive (L7 1999–2024; L5 1984–2013) · **T2** |
| Product / format | C2 L2 SR, COG; TM/ETM+ bands `blue, green, red, nir08, swir16, swir22` (no coastal) |
| Caveat | **Landsat 7 SLC-off gaps after 2003-05-31** (striping); L5 ends 2013 |
| Mask / scale | Same `qa_pixel` + `0.0000275/−0.2` as §C.1 |
| Indices | NDVI, MSAVI, NDMI, NDWI (no NDRE) |
| Verdict | **Archive-only** — same `usgs` client + prep; decadal baselines (1984→2013 / 1999→2024) |

#### Provider C code checklist (`usgs`)
- [ ] **New client** `services/ingestion/akasha_ingest/usgs.py` — STAC search (Planetary Computer/Earth Search) + COG fetch; optional M2M auth path
- [ ] [worker.py](../../services/ingestion/worker.py) — generic provider dispatch (`provider="usgs"`) after shared source-state/manifest/verification enablement
- [ ] [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) — `landsat-8-c2-l2`, `landsat-9-c2-l2`, `landsat-7-c2-l2`, `landsat-5-c2-l2` rows
- [ ] **New prepare script** `scripts/prepare_landsat_c2_l2_cogs.py` — clip C2 L2 COGs to AOI, restack analytic, derive Akasha mask from `qa_pixel`
- [ ] [scene.py](../../services/ingestion/akasha_ingest/scene.py) — Landsat scene-id parsing (`LC08_L2SP_...`)
- [ ] [composite.py](../../services/ingestion/akasha_ingest/composite.py) — Landsat optical composite profile (30 m grid, `qa_pixel`-derived mask)
- [ ] STAC seed `data/seed/stac/landsat-8-c2-l2-collection.json` (+ 9/7/5)
- [ ] [catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) — `_SOURCE_REGISTRY` rows (optical, RGB display, NDVI/MSAVI/NDMI/NDWI)
- [ ] Env/secrets — `EARTHDATA_TOKEN` or `USGS_M2M_*` only if not using the open cloud path
- [ ] Validation: dry-run → capped run → `verify-composite` for Landsat optical composites

---

### D. NASA Earthdata — MODIS + NISAR(ASF) — new `earthdata` / `asf` client

**Access model.** **Free.** [Earthdata Login](https://urs.earthdata.nasa.gov/) (OAuth/token) gates
NASA DAACs. MODIS via LP DAAC (LAADS/AppEEARS, also Planetary Computer `modis-13Q1-061`).
NISAR via **ASF DAAC** (Vertex, `asf_search`, Earthdata Search). CMR is the common STAC/CMR catalog.

#### D.1 MODIS (Terra/Aqua) — 🟢 buildable (regional context)

| Field | Value |
|---|---|
| Status / tier | Live (2000→) · **T1 context** |
| Product | **MOD13Q1 / MYD13Q1 v061** — Vegetation Indices 16-Day 250 m (L3); also MOD09 surface reflectance |
| Format | HDF-EOS (native) + **COG** (cloud); convert HDF→COG if using DAAC source |
| Key assets | `250m_16_days_NDVI` + `_EVI` (scale **0.0001**, int16); red/NIR/blue/MIR reflectance; `pixel_reliability` (0 good,1 marginal,2 snow/ice,3 cloudy); `VI_Quality` bitmask |
| Mask | `pixel_reliability` / `VI_Quality` |
| Resolution / revisit / swath | 250 m · 16-day composite (daily overpass) · 2330 km |
| Display | NDVI/EVI context ramp — **regional, not field-level** (`analysisLevel="regional"`) |
| Indices | Provider NDVI/EVI (precomputed); raw bands allow NDVI recompute but at 250 m |
| India AOI | ✅ state/district scale |
| Verdict | **Buildable** as a regional context layer (drought/phenology), not field analytics |

#### D.2 NISAR (ASF path) — see §A.4
Same GCOV product, alternative free access via ASF DAAC (`asf_search` + Earthdata Login). Use
whichever (Bhoonidhi or ASF) ships calibrated ARD first (~Jul 2026).

#### Provider D code checklist (`earthdata`)
- [ ] **New client** `services/ingestion/akasha_ingest/earthdata.py` — Earthdata Login token; CMR/STAC search; granule download (+ `asf_search` for NISAR)
- [ ] [worker.py](../../services/ingestion/worker.py) — generic provider dispatch after shared source-state/manifest/verification enablement
- [ ] [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) — `modis-13q1-061` row (`supports_composite=False` — already a 16-day composite)
- [ ] **New prepare script** `scripts/prepare_modis_13q1_cogs.py` — HDF→COG (or fetch cloud COG), clip AOI, scale NDVI
- [ ] STAC seed + [catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) row (`kind="optical"`, `analysisLevel="regional"`, context display)
- [ ] Env/secrets — `EARTHDATA_TOKEN`
- [ ] Validation: dry-run → capped run → source-aware context verification (`verify-raster-product`/context profile), not optical `verify-composite`

---

### E. Planet Labs (PlanetScope, SkySat) — 🔴 commercial, new `planet` client

**Access model.** **Commercial — paid subscription + API key required before any code runs.**
APIs: [Data API](https://docs.planet.com/develop/apis/data/) (search),
[Orders API](https://docs.planet.com/develop/apis/orders/) (activate/download/deliver-to-cloud),
[Subscriptions API](https://docs.planet.com/develop/apis/subscriptions/),
[Tasking API](https://docs.planet.com/develop/apis/tasking/). Auth: API key. Quota-metered.
Delivery: analytic SR GeoTIFF/COG → fits the prepare→composite→STAC path **once licensed**.

| Platform | Bands | Res | Mask | Indices | Verdict |
|---|---|---|---|---|---|
| **PlanetScope** | Blue, Green, Red, Red-Edge, NIR (8-band SuperDove adds coastal/yellow/etc.) | 3–5 m · daily | UDM2 usable-data mask | NDVI, MSAVI, **NDRE**, NDWI (no SWIR → no NDMI) | 🔴 Licensing-gated; technically ingestible (UDM2 → Akasha mask) |
| **SkySat** | Pan, Blue, Green, Red, NIR | 0.5 m · multi/day | UDM2 | NDVI, MSAVI, NDWI (no red edge/SWIR) | 🔴 Licensing-gated; VHR tasking |

#### Provider E code checklist (`planet`)
- [ ] **New client** `services/ingestion/akasha_ingest/planet.py` — API-key auth; Data API search; Orders API order→poll→download
- [ ] Generic provider dispatch after shared enablement; `pipeline_registry.py` rows `planetscope`, `skysat`, all commercial-gated
- [ ] **New prepare scripts** — PlanetScope analytic SR + UDM2→Akasha mask; SkySat ortho
- [ ] STAC + BFF registry rows; env `PLANET_API_KEY`; **licensing/quota approval before enabling**
- [ ] Validation gate **plus** commercial sign-off

---

### F. JAXA — ALOS-2 (PALSAR-2) — 🔴 mostly commercial, new `jaxa` client

**Access model.** L-band SAR. **Scene-level archive/tasking is commercial** via JAXA G-Portal /
RESTEC / resellers. **Free** products: global annual **25 m SAR mosaic** + Forest/Non-Forest map
([JAXA EORC datasets](https://www.eorc.jaxa.jp/ALOS/en/dataset/fnf_e.htm)).

| Field | Value |
|---|---|
| Bands / product | L-band (HH/HV/VV/VH) σ⁰ backscatter; CEOS/GeoTIFF; free mosaic = 25 m annual COG |
| Processing | Geocode + dB (similar to EOS-04/NISAR SAR prep) |
| Mask / indices | None (SAR) |
| Res / revisit | 3–10 m scenes (14 d) · 25 m annual mosaic |
| Verdict | 🔴 **Scenes paid**; **free 25 m mosaic is buildable** as a coarse L-band context/biomass layer |

#### Provider F code checklist (`jaxa`)
- [ ] **New client** `services/ingestion/akasha_ingest/jaxa.py` — G-Portal auth/download (or static mosaic fetch for the free tier)
- [ ] `pipeline_registry.py` rows `alos2-palsar2` (scenes, gated) and/or `alos2-mosaic-25m` (free)
- [ ] **New prepare script** — geocode + dB backscatter (reuse SAR pattern)
- [ ] SAR registry row (`VV_GRAYSCALE`, no indices, `supports_composite=False`)

---

### G. Commercial VHR resellers (SuperView NEO-1, BlackSky Gen 3, KOMPSAT-3A) — 🔴 vendor APIs

**Access model.** **Commercial tasking/archive via reseller contracts.** No open/free catalog.
Each delivers ortho GeoTIFF/COG that *could* feed prepare→composite→STAC once licensed.

| Platform | Vendor / API | Bands | Res / revisit | India | Indices | Verdict |
|---|---|---|---|---|---|---|
| **SuperView NEO-1** | SIIS (China) tasking | Pan, B, G, R, NIR | 0.3 m · daily | ✅ tasking | Pan-sharpened NDVI | 🔴 Licensing-gated VHR |
| **BlackSky Gen 3** | BlackSky **Spectra** API | Pan, B, G, R, NIR | 0.35 m · up to 15×/day | ✅ tasking | Pan-sharpened NDVI | 🔴 Licensing-gated VHR (rapid revisit) |
| **KOMPSAT-3A** | KARI / SIIS | Pan, B, G, R, NIR + **MWIR** | 0.4 m · 1.5 d | ✅ tasking | Pan-sharpened NDVI; MWIR thermal | 🔴 Licensing-gated VHR |

#### Provider G code checklist (one `vendor` adapter per reseller, when contracted)
- [ ] **New client** per vendor (auth + tasking/archive order + download)
- [ ] `pipeline_registry.py` rows; **new prepare scripts** (ortho restack; pan-sharpen optional)
- [ ] VHR optical registry rows (RGB display; NDVI where bands allow); **contract + quota gating first**

---

### H. USDA — NAIP — ⚪ out-of-AOI

| Field | Value |
|---|---|
| Status / tier | Live (2010→, ~3-yr cadence) · **T4** |
| Access | **Free, public domain** — COG on Planetary Computer (`naip`) / AWS; no auth |
| Bands | 4-band **RGBIR** COG, 0.3–1.0 m |
| Coverage | **United States only** (CONUS + HI + PR + VI) — **does not cover India** |
| Indices | 4-band NDVI |
| Verdict | ⚪ **Not deployable over `bangalore-60km`.** Keep as a **methodology/reference** source only (ground-truth boundary workflows), never wired as a selectable AOI source |

---

## 4. Cross-cutting engineering concerns

### 4.1 Shared enablement (do once, before any non-ISRO source)
- **Source-state consistency.** Before provider clients are added, reconcile ingestion registry, BFF
  registry, and STAC seed metadata. Use explicit states for ingestion-enabled, operator-enabled,
  user-selectable, gated, context-only, archive-only, and commercial-blocked; do not overload
  `mvp_enabled` for all of those meanings.
- **Provider factory + generic worker orchestration.** Today `bhoonidhi-search/download/sync`
  hard-instantiate `BhoonidhiClient()` and the sync path assumes ResourceSat prepare/composite/verify.
  Introduce a `get_provider_client(provider)` factory keyed on `PipelineSource.provider`, canonical
  search/download manifests, and generic `search/download/prepare/ingest/verify-raster-product`
  commands so CDSE/USGS/NASA/Planet reuse the same orchestration. Keep `bhoonidhi-*` commands as
  backward-compatible aliases.
- **Fail-closed prepare dispatch.** Unknown sources must raise a clear error. Do not fall back to
  `prepare_resourcesat_liss3_boa_cogs.py` for unknown source IDs.
- **Source-aware verification profiles.** `verify-composite` is only for optical composites. SAR,
  context, archive, and precomputed-index sources need profile-driven validation of expected assets,
  band counts, dtypes, CRS/resolution, overviews, mask classes, and required STAC fields.
- **Generic BFF composite/date serving.** Any source with `supports_composite=True` must register dated
  `akasha:composite=true` STAC items, and the BFF must prefer those items for date-level tiles and
  statistics. Multi-scene non-composite dates remain unavailable until a composite or mosaic backend exists.
- **Client contract.** Every provider module must expose the normalized provider shape: search returns
  provider features, download returns `{status,path,bytes}`-style results, and provider-specific fields
  are normalized into canonical Akasha manifests before downstream prepare/ingest stages.

### 4.2 Authentication & secrets (per provider)
| Provider | Mechanism | Secrets | IP allow-list |
|---|---|---|---|
| Bhoonidhi | Password grant + refresh | `BHOONIDHI_USER_ID/PASSWORD` | **Yes — staging VM `20.219.3.35` only** |
| CDSE | OAuth2 (Keycloak) + optional EOData S3 credentials | `CDSE_USERNAME/PASSWORD`, optional `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID=cdse-public`, optional `CDSE_S3_ACCESS_KEY/SECRET_KEY` | No |
| USGS | ERS/M2M token (or none for cloud COG) | `USGS_M2M_*` / `EARTHDATA_TOKEN` | No |
| NASA Earthdata/ASF | Earthdata Login token | `EARTHDATA_TOKEN` | No |
| Planet | API key | `PLANET_API_KEY` | No (but paid quota) |
| JAXA / VHR resellers | Vendor key/contract | vendor-specific | No (paid) |

Store secrets as deployment env/secret-manager entries; never commit. Only ISRO must run from staging.

### 4.3 Optical vs SAR rules (enforced by the registry)
- **Optical** (S2, Landsat, ResourceSat, EOS-06, MODIS, Planet, VHR, NAIP): band-role mapping, a
  cloud/validity mask (SCL / `qa_pixel` / `pixel_reliability` / UDM2 / Akasha-threshold), RGB or FCC
  display, NDVI-family indices per available roles.
- **SAR** (S1, EOS-04, NISAR, ALOS-2): `bandRoleMapping={}`, `supportedIndices=[]`, `maskAsset=None`,
  grayscale display, `supports_composite=False`, dB calibration. **Never an optical-index source.**

### 4.4 Index support by available band roles
NDVI=(NIR,RED) · MSAVI=(NIR,RED) · NDRE=(NIR,RED_EDGE) · NDMI=(NIR,SWIR1) · NDWI_GREEN_NIR=(GREEN,NIR).
A source supports an index **iff** its `bandRoleMapping` contains both roles ([indices.py](../../apps/api/app/raster/indices.py)).
Only Sentinel-2 and PlanetScope carry a true red edge (→ NDRE).

### 4.5 Licensing, attribution & the gating rule
- Every new source stays **gated** until: registry row + prep/adapter + validation tests + staging
  dry-run + capped real run (`--max-downloads 1`) + source-appropriate verification
  ([data-ingestion-and-satellite-rules.md](../data-ingestion-and-satellite-rules.md) § New Satellite Source Onboarding Rule).
- Use `worker.py verify-composite` only for optical composite outputs. Use source-aware raster/context/SAR
  verification for display-only SAR, context, archive, and precomputed-index sources.
- Wire `attribution` per source; commercial sources additionally require a **signed licence/quota**
  before `mvp_enabled=True`.
- Default display is always the source's natural imagery (RGB/FCC/grayscale) — **never an index**.

---

## 5. Recommended onboarding order (feasibility × value)

1. **Source-state + verification readiness** — reconcile registries, add source-aware validation profiles, and split composite vs non-composite verification.
2. **Generic worker orchestration** — provider factory, canonical manifests, generic commands, fail-closed prepare dispatch.
3. **Generic optical composite/date serving** — source-specific composite profiles + BFF composite preference for any composite-enabled optical source.
4. **Sentinel-2 (CDSE)** — registry + scripts mostly exist; add `cdse` client and keep non-selectable by default until explicit rollout.
5. **Landsat 8/9 (USGS/cloud STAC)** — cloud STAC+COG, no SNAP; pairs with S2 for 8-day effective cadence.
6. **Sentinel-1 (CDSE)** — reuses `cdse` client; SAR prep runs in existing `ingestion-sar` image; verify as SAR backscatter, not composite.
7. **EOS-04 / EOS-06 / NISAR (Bhoonidhi)** — client + some prep/STAC already scaffolded; flip on after source-specific validation (NISAR waits for ARD ~Jul 2026).
8. **MODIS (Earthdata)** — regional context layer.
9. **Landsat 7/5, IRS-1C** — archive baselines (same clients, archive caveats).
10. **Commercial (Planet/JAXA/VHR/Cartosat)** — only after licensing/quota/readiness sign-off; technically possible, contractually blocked.
11. **NAIP** — not onboarded (US-only); reference methodology only.

Full task breakdown: [data-multi-source-ingestion-roadmap-1.md](../impl-plan/data-multi-source-ingestion-roadmap-1.md).

---

## 6. Sources

- Copernicus Data Space Ecosystem — APIs (OData/STAC/S3/Token): https://documentation.dataspace.copernicus.eu/APIs.html
- Sentinel-2 L2A STAC (bands/scale/SCL): https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a
- Sentinel-1 GRD STAC (C-band/pol/modes): https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-grd
- Landsat Collection 2 L2 STAC (bands/`qa_pixel`/scale): https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2
- USGS Landsat data access (M2M/EarthExplorer): https://www.usgs.gov/landsat-missions/landsat-data-access
- MODIS MOD13Q1 v061 STAC + User Guide: https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13Q1-061
- NISAR products + access (ASF DAAC): https://www.earthdata.nasa.gov/data/platforms/space-based-platforms/nisar
- Planet APIs (Data/Orders/Subscriptions/Tasking): https://docs.planet.com/develop/apis/
- JAXA ALOS-2 (PALSAR-2) + datasets: https://www.eorc.jaxa.jp/ALOS/en/alos-2/a2_about_e.htm
- NAIP STAC (RGBIR/US-only): https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip
- Akasha satellite catalog (specs/slugs): [satellite-catalog.md](satellite-catalog.md)
- Bhoonidhi/ISRO contract + staging constraints: [staging-ingestion-developer-guide.md](../staging-ingestion-developer-guide.md)

---

## 7. Future Provider Onboarding Sequence (Phase 12 — GOAL-012)

> **GOAL-012:** Add non-ISRO providers by adding adapters/source rows, not by rewriting the
> scheduler. This section implements TASK-073 through TASK-079 from
> [architecture-satellite-ingestion-scheduler-1.md](../impl-plan/architecture-satellite-ingestion-scheduler-1.md)
> Phase 12. For each future provider phase it specifies: entry prerequisites, allowed source-state
> transitions, adapter and source rows to add or replace, validation profile requirements,
> required tests and smoke checks, rollout gates, and explicit non-goals.
>
> The scheduler architecture and provider adapter contracts are already frozen in §1.1–§1.5
> and [satellite-ingestion-scheduler-contracts.md](satellite-ingestion-scheduler-contracts.md).
> **Do not rewrite the scheduler to add a new provider — add an adapter and source rows only.**

### 7.0 Universal prerequisites for all Phase 12 provider phases

Every provider phase below must wait for all of the following to be true:

1. **Phases 0–9 of the scheduler plan are complete, passing, and production-stable.** ISRO sources
   run through the orchestrator (`worker.py schedule-source`) with all parity tests green.
2. **`source_registry.py` is the single authoritative source-state registry.** `pipeline_registry.py`
   `mvp_enabled` is derived/backwards-compat only.
3. **`providers/base.py` `ProviderAdapter` protocol and `get_provider_adapter()` are frozen and
   tested.** Placeholders (`PlaceholderAdapterBase`, `CommercialPlaceholderAdapterBase`) are in
   place for every unimplemented adapter.
4. **`manifests.py` and `validation_profiles.py` are stable and tested.** All six validation
   profiles (`optical_composite`, `optical_scene`, `sar_backscatter`, `precomputed_context`,
   `archive_only`, `visual_only`) are defined.
5. **ResourceSat LISS-3 production invariants are preserved throughout.** `test_resourcesat_scheduler_invariants.py`
   passes at every commit of new provider work. Regressions in LISS-3 4-band order, FCC display,
   Akasha threshold mask v1, or deterministic keys are release-blockers.
6. **No new source may start at `product_active` or `routine`.** All new sources begin at
   `scheduleState=disabled` (or `dry_run`) + `productExposure=hidden`. Staged transitions below
   are the only valid promotion path.

---

### 7.1 Phase 12-A — CDSE: Sentinel-2 and Sentinel-1 (TASK-073)

**When:** After Phases 0–9 are stable and universal prerequisites (§7.0) are met.

#### 7.1.1 Entry prerequisites (CDSE-specific)

- `CDSE_USERNAME` and `CDSE_PASSWORD` are provisioned in deployment secrets (see §4.2 auth table).
  Optional: `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID=cdse-public`, `CDSE_S3_ACCESS_KEY`/`CDSE_S3_SECRET_KEY`.
- Sentinel-1 SAR prep requires the `ingestion-sar` container image (SNAP/GPT installed and healthy).
  Verify this image before Sentinel-1 work begins; it does not need to be healthy to start Sentinel-2.
- Legacy scripts `download_sentinel2_l2a_product.py` and `prepare_sentinel2_l2a_cogs.py` remain as
  reference artifacts; they must not be deleted or broken by the new provider path.
- Current source-state (confirm before touching any code):
  - `sentinel-2-l2a`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=provider_configured`
  - `sentinel-1-grd`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=provider_configured`

#### 7.1.2 Source rows — allowed state transitions

| Source ID | Starting state | After adapter + dry-run | After validation passed |
|-----------|---------------|-------------------------|------------------------|
| `sentinel-2-l2a` | `disabled` + `hidden` | `dry_run` + `hidden` → `background_only` + `background_only` | `routine` + `product_active` |
| `sentinel-1-grd` | `disabled` + `hidden` | `dry_run` + `hidden` → `background_only` + `background_only` | `background_only` (no `product_active` until SAR analytics path is defined) |

`sentinel-1-grd` **must not** reach `productExposure=product_active` until a dedicated SAR
display/analytics layer and user-facing description are explicitly designed and implemented.

#### 7.1.3 Adapter and files to create or modify

- **`services/ingestion/akasha_ingest/cdse.py`** — new `CDSEClient` with OAuth2/Keycloak token
  refresh, OData/STAC `search()`, and S3-or-OData `download_product()`.
- **`services/ingestion/akasha_ingest/providers/cdse_adapter.py`** — replace
  `PlaceholderAdapterBase` subclass with a real `CDSEAdapter` wrapping `CDSEClient` into the
  `ProviderAdapter` protocol. `order()`, `poll_order()`, `cancel_order()` raise
  `ProviderActionUnsupported` (CDSE has no order workflow).
- **`services/ingestion/akasha_ingest/composite.py`** — add Sentinel-2 optical composite profile:
  10 m grid, SCL mask exclude `[0,1,2,3,7,8,9,10,11]`, keep water class 6. Sentinel-1 must
  remain `supports_composite=False`.
- **`apps/api/app/raster/catalog_resolver.py`** — confirm `sentinel-2-l2a` `_SOURCE_REGISTRY` row:
  current 7-role `bandRoleMapping` `{BLUE: B02, GREEN: B03, RED: B04, NIR: B08, RED_EDGE: B05,
  SWIR1: B11, SWIR2: B12}`, SCL mask asset (`maskAsset="scl"`), `reflectanceScale=0.0001`,
  `reflectanceOffset=-0.1` (Sentinel-2 offset; do **not** apply to ResourceSat or Landsat rows).
  Note: B06 (red-edge 2) and B07 (red-edge 3) are **not** in the current registry — adding them
  requires a separate code change to `catalog_resolver.py` and `indices.py`. Confirm `sentinel-1-grd`
  row has `bandRoleMapping={}`, `supportedIndices=[]`, SAR grayscale display.
- **`source_registry.py`** — update `sentinel-2-l2a` and `sentinel-1-grd` rows by flipping
  `lifecycle_state` to `download_enabled` after client is wired; `schedule_state` to `dry_run`
  after first staging test; then `background_only` after dry-run validation passes.

#### 7.1.4 Validation profile requirements

| Source | Validation profile | Forbidden validator |
|--------|-------------------|---------------------|
| `sentinel-2-l2a` | `optical_composite` (composite output), `optical_scene` (per-scene) | none |
| `sentinel-1-grd` | `sar_backscatter` | **`verify-composite` is forbidden** (GEO-002, TASK-039) |

Running `verify-composite` on `sentinel-1-grd` must fail with an actionable error —
this is enforced by the existing `test_generic_scheduler_orchestrator.py` TASK-039 test.
Use `verify-raster-product --profile sar_backscatter` for Sentinel-1.

#### 7.1.5 Required tests and smoke checks

- **`tests/test_provider_adapter_contract.py`** — extend with `CDSEAdapter` mock-HTTP tests:
  search with OAuth2 mock, normalize candidates, download dry_run=True (no network call), token
  refresh failure raises `ProviderAuthError`, `order()` raises `ProviderActionUnsupported`.
- **`tests/test_satellite_catalog_registry.py`** — assert updated rows have valid state
  combinations at each transition; no contradictory combination is accepted.
- **`tests/test_generic_scheduler_orchestrator.py`** — dry-run for `sentinel-2-l2a` with mock
  CDSE returns plan without download/prepare/composite actions.
- **Staging smoke:** `worker.py schedule-source --source sentinel-2-l2a --aoi bangalore-60km --dry-run`
  through safe wrapper; confirm job artifacts are created and redacted.
- **Capped real run:** `--max-downloads 1` → `verify-composite` (S2) and
  `verify-raster-product --profile sar_backscatter` (S1); assert STAC item is registered.

#### 7.1.6 Rollout gates (in order; each gate must pass before the next)

1. Mock-backed unit tests green.
2. Staging dry-run passes through scheduler; no download/prepare/upload occurs.
3. Capped run (`--max-downloads 1`) produces a valid COG composite artifact for one MGRS tile.
4. `verify-composite` passes for Sentinel-2: SCL mask applied, 9-band order, `-0.1` offset.
5. `verify-raster-product --profile sar_backscatter` passes for Sentinel-1 scene.
6. Operator explicitly flips `scheduleState=background_only` in `source_registry.py`.
7. Three or more successful background composite runs covering `bangalore-60km` composite window.
8. `validationState=validation_passed` documented in registry and notes for `sentinel-2-l2a`.
9. Operator explicitly flips `scheduleState=routine` + `productExposure=product_active` for
   Sentinel-2 only. Sentinel-1 remains `background_only` until SAR analytics path is defined.

#### 7.1.7 Explicit non-goals for Phase 12-A

- Do NOT implement Sentinel Hub processing APIs, EOData S3 bulk, or openEO — OData/STAC is enough.
- Do NOT merge Sentinel-2 dates into the ResourceSat best-observation timeline; that requires
  Phase 11 multi-source resolver work.
- Do NOT expose `sentinel-1-grd` as a user-selectable product until a SAR layer is designed.
- Do NOT apply `-0.1` reflectance offset to ResourceSat or Landsat source rows — it is Sentinel-2 only.
- Do NOT run `bhoonidhi-*` commands for CDSE sources; CDSE uses the `cdse` adapter path.

---

### 7.2 Phase 12-B — USGS: Landsat 8 and Landsat 9 (TASK-074)

**When:** After universal prerequisites (§7.0) are met. CDSE phase (§7.1) does not need to be
complete; Landsat uses a separate adapter and client and can proceed in parallel with CDSE.

#### 7.2.1 Entry prerequisites (USGS-specific)

- Cloud STAC path (preferred): no special credentials needed. STAC queries go to Planetary
  Computer (`landsat-c2-l2` collection) or Element84 Earth Search. Confirm the endpoint returns
  Collection 2 L2 COG assets covering the Bangalore area before writing any client code.
- Optional M2M path: `USGS_M2M_USERNAME` + `USGS_M2M_API_KEY` (must be requested from USGS
  separately from ERS login). Cloud COG path is strongly preferred and does not require M2M.
- Optional: `EARTHDATA_TOKEN` (only if using Earthdata-gated download path).
- Current source-state:
  - `landsat-8-c2-l2`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=catalogued`
  - `landsat-9-c2-l2`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=catalogued`

#### 7.2.2 Source rows — allowed state transitions

| Source ID | Starting state | After adapter + dry-run | After validation passed |
|-----------|---------------|-------------------------|------------------------|
| `landsat-8-c2-l2` | `disabled` + `hidden` | `dry_run` → `background_only` | `routine` + `product_active` |
| `landsat-9-c2-l2` | `disabled` + `hidden` | `dry_run` → `background_only` | `routine` + `product_active` |

#### 7.2.3 Adapter and files to create or modify

- **`services/ingestion/akasha_ingest/usgs.py`** — new `USGSClient`: STAC search against
  Planetary Computer or Earth Search, COG fetch (HTTP range/signed URL), optional M2M auth.
- **`services/ingestion/akasha_ingest/providers/usgs_adapter.py`** — replace placeholder with
  `USGSAdapter` wrapping the new client.
- **`scripts/prepare_landsat_c2_l2_cogs.py`** — new prepare script: clip C2 L2 COG assets to
  AOI, restack to 4-role analytic order `[green(SR_B3), red(SR_B4), nir08(SR_B5), swir16(SR_B6)]`
  (matching the ResourceSat role layout for index compatibility), derive Akasha categorical mask
  from `qa_pixel` bit-packed field (cloud=bit3, shadow=bit4, snow=bit5, water=bit7, dilated=bit1).
- **`data/seed/stac/landsat-8-c2-l2-collection.json`** and `landsat-9-c2-l2-collection.json` —
  new STAC seed collections with `eo:bands` using roles `green`, `red`, `nir08`, `swir16`.
- **`services/ingestion/akasha_ingest/scene.py`** — add Landsat scene-ID parsing for
  `LC08_L2SP_...` and `LC09_L2SP_...` naming conventions.
- **`apps/api/app/raster/catalog_resolver.py`** — add `_SOURCE_REGISTRY` rows:
  `analysisLevel=field`, `reflectanceScale=0.0000275`, `reflectanceOffset=-0.2`, RGB display,
  NDVI/MSAVI/NDMI/NDWI_GREEN_NIR (no NDRE — Landsat has no red-edge band).
  `maskAsset=qa_pixel` with categorical derivation note.

#### 7.2.4 Validation profile requirements

| Source | Validation profile |
|--------|-------------------|
| `landsat-8-c2-l2` | `optical_composite` (AOI composite), `optical_scene` (per-scene check) |
| `landsat-9-c2-l2` | `optical_composite`, `optical_scene` |

Profiles must assert: `reflectanceScale=0.0000275`, `reflectanceOffset=-0.2`, 4-band analytic
order, `qa_pixel`-derived mask with Akasha threshold mask v1 class equivalents.

#### 7.2.5 Required tests and smoke checks

- **`tests/test_provider_adapter_contract.py`** — `USGSAdapter` with mock STAC HTTP: search
  returns expected candidates; dry_run=True does not fetch COG bytes; `qa_pixel` derivation test
  produces correct Akasha mask classes for known bit patterns.
- **`tests/test_satellite_catalog_registry.py`** — assert valid state combinations at each
  transition.
- **Staging smoke:** `worker.py schedule-source --source landsat-8-c2-l2 --aoi bangalore-60km --dry-run`.
- **Capped run:** `--max-downloads 1` → `verify-composite`; confirm `qa_pixel` mask applied,
  band order is `[green, red, nir08, swir16]`, and `reflectanceOffset=-0.2`.

#### 7.2.6 Rollout gates

1. Mock-backed unit tests for `USGSAdapter` + `qa_pixel` mask derivation pass.
2. Staging dry-run passes.
3. Capped run (`--max-downloads 1`) produces a valid composite for at least one MGRS tile.
4. `verify-composite` passes with correct Landsat scale/offset and 4-band role order.
5. Operator flips `scheduleState=background_only`.
6. Three or more successful background composite runs covering `bangalore-60km`.
7. `validationState=validation_passed` documented in registry.
8. Operator flips `scheduleState=routine` + `productExposure=product_active`.

#### 7.2.7 Explicit non-goals for Phase 12-B

- Do NOT implement Landsat 7 or Landsat 5 as routine sources — those are archive/on-demand only
  (see Phase 12-E, §7.5).
- Do NOT use USGS M2M as the only access path; cloud-native STAC+COG is preferred (SRC-003).
- Do NOT apply ResourceSat's `offset=0.0` or Sentinel-2's `offset=-0.1` to Landsat rows;
  Landsat C2 L2 uses `scale=0.0000275, offset=-0.2`.
- Do NOT merge Landsat dates into the best-observation timeline before Phase 11 work.

---

### 7.3 Phase 12-C — Earthdata/ASF: MODIS and NISAR (TASK-075)

**When:** After CDSE and USGS adapter patterns are established and tested (phases 12-A and 12-B
unit tests at minimum). NISAR specifically requires confirmed calibrated ARD product availability
at ASF DAAC (~Jul 2026) before any real data work begins.

#### 7.3.1 Entry prerequisites (Earthdata/ASF-specific)

- `EARTHDATA_TOKEN` provisioned in deployment secrets.
- **MODIS:** confirm that `modis-13Q1-061` collection on Planetary Computer or LP DAAC returns
  cloud COG granules covering Bangalore. Prefer cloud COG over HDF-EOS download.
- **NISAR:** confirm that at least one calibrated GCOV ARD product is available at ASF DAAC for
  a scene covering India. **Do not begin NISAR ingestion code until ARD is confirmed.**
  The `nisar-ssar-beta-gcov` source row carries this as a readiness reason.
- `asf_search` Python package is available in the ingestion container.
- Current source-state:
  - `modis-13q1-061`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=catalogued`
  - `nisar-ssar-beta-gcov`: `scheduleState=disabled`, `productExposure=hidden`, `lifecycleState=provider_configured`

#### 7.3.2 Source rows — allowed state transitions

| Source ID | Starting state | Target state | Constraint |
|-----------|---------------|-------------|------------|
| `modis-13q1-061` | `disabled` + `hidden` | `background_only` + `reference_only` | GEO-003: precomputed context; never `product_active` for field stats |
| `nisar-ssar-beta-gcov` | `disabled` + `hidden` | `background_only` + `background_only` | data-gated until ARD confirmed; SAR only |

MODIS **must not** reach `productExposure=product_active` for field-level statistics — it is
`analysisLevel=regional` context (GEO-003). Its precomputed NDVI grid is not raw-reflectance
field analytics; `productExposure=reference_only` is the maximum allowed exposure.

#### 7.3.3 Adapter and files to create or modify

- **`services/ingestion/akasha_ingest/earthdata.py`** — new `EarthdataClient`: Earthdata Login
  token auth; CMR/STAC search; LP DAAC download for MODIS; ASF DAAC download for NISAR GCOV
  (using `asf_search`).
- **`services/ingestion/akasha_ingest/providers/earthdata_adapter.py`** — replace placeholder
  `EarthdataAdapter` with real implementation wrapping `EarthdataClient`.
- **`services/ingestion/akasha_ingest/providers/asf_adapter.py`** — replace placeholder
  `ASFAdapter`; wraps `asf_search` + Earthdata token. Note: both adapters share `earthdata.py`
  for auth; the split is by catalog/DAAC endpoint.
- **`scripts/prepare_modis_13q1_cogs.py`** — new script: fetch cloud COG granule, clip to AOI,
  scale precomputed NDVI with `scale=0.0001` (int16 → float), produce context tile for display.
- **`apps/api/app/raster/catalog_resolver.py`** — add MODIS `_SOURCE_REGISTRY` row with
  `productFamily=precomputed_index`, `analysisLevel=regional`, NDVI context display (not field
  stats). NISAR row must have `bandRoleMapping={}`, `supportedIndices=[]` (GEO-002).

#### 7.3.4 Validation profile requirements

| Source | Validation profile |
|--------|-------------------|
| `modis-13q1-061` | `precomputed_context` — validates precomputed-index granule structure; must forbid field-level band-stats |
| `nisar-ssar-beta-gcov` | `sar_backscatter` — validates SAR GCOV; no optical indices; `verify-composite` forbidden |

#### 7.3.5 Required tests and smoke checks

- **`tests/test_provider_adapter_contract.py`** — `EarthdataAdapter` with mock CMR STAC;
  `ASFAdapter` with mock `asf_search`; prove NISAR GCOV source gets `sar_backscatter` profile;
  MODIS gets `precomputed_context` profile.
- **`tests/test_generic_scheduler_orchestrator.py`** — MODIS dry-run plan shows
  `analysisLevel=regional`; NISAR remains `disabled` when `readinessReasons` includes data-gate.
- **Staging smoke (MODIS):** `worker.py schedule-source --source modis-13q1-061 --aoi bangalore-60km --dry-run`.
- **Staging smoke (NISAR):** only after ARD is confirmed at ASF DAAC; same dry-run pattern.

#### 7.3.6 Rollout gates

1. `EARTHDATA_TOKEN` provisioned and validated against LP DAAC (MODIS) and ASF DAAC (NISAR test).
2. MODIS: mock tests pass → staging dry-run passes → capped run validates `precomputed_context`
   profile → operator flips to `background_only` + `productExposure=reference_only`.
3. NISAR: ARD product confirmed at ASF DAAC → mock tests pass → staging dry-run passes →
   SAR validation (`sar_backscatter`) passes → operator flips to `background_only`.
4. Neither MODIS nor NISAR may reach `product_active` without an explicit analytics design review.

#### 7.3.7 Explicit non-goals for Phase 12-C

- Do NOT implement MODIS as a field-level statistics source (GEO-003); it is `analysisLevel=regional`.
- Do NOT compute optical vegetation indices from NISAR (GEO-002); it is a SAR source.
- Do NOT start NISAR adapter work until calibrated ARD is confirmed; data-gating is not a code blocker.
- Do NOT use `EARTHDATA_TOKEN` for USGS/Landsat cloud COG paths where no auth is needed.
- Do NOT run `verify-composite` on MODIS or NISAR products; use `verify-raster-product`.

---

### 7.4 Phase 12-D — ISRO gated: EOS-04, EOS-06, NISAR Bhoonidhi, IRS-1C, Cartosat-3 (TASK-076)

**When:** For EOS-04, EOS-06, IRS-1C — after Phase 12-A or 12-B adapter patterns are established
(they reuse the existing Bhoonidhi adapter; no new provider client is required). For NISAR
Bhoonidhi path — same data-gate condition as Phase 12-C. For Cartosat-3 — only after a
programmatic catalog/download API from NRSC/NSIL is confirmed.

> **Key constraint (Bhoonidhi sources):** EOS-04, EOS-06, NISAR (Bhoonidhi path), and IRS-1C all
> reuse the **existing `bhoonidhi` provider adapter** — no new provider client is required.
> The adapter already calls `BhoonidhiClient.search()` / `download_product()`; only source
> collection IDs and prepare scripts differ.
>
> **Cartosat-3 exception:** `cartosat-3-gated` uses `provider_adapter="vendor"` (not Bhoonidhi)
> and has **no executable ingestion path** until NRSC/NSIL provides a programmatic catalog/download
> API. It is listed here for completeness only; the `vendor` placeholder adapter fails closed
> with `ProviderActionUnsupported` for unsupported provider actions and commercial preflight
> failures for order attempts.

#### 7.4.1 Source rows — allowed state transitions

| Source ID | Current state | Allowed next state | Trigger |
|-----------|--------------|-------------------|---------|
| `eos-04-sar-mrs-l2b` | `disabled` + `hidden` | `dry_run` → `background_only` | SAR scene confirmed downloadable + `gdalinfo`-validated |
| `eos-06-ocm-lac-ndvi-8day-360m` | `disabled` + `hidden` | `dry_run` → `background_only` + `reference_only` | Precomputed NDVI tile clip + context validation passes |
| `nisar-ssar-beta-gcov` (Bhoonidhi path) | `disabled` + `hidden` | same data-gate as Phase 12-C | ARD product confirmed via Bhoonidhi catalog |
| `irs-1c-liss3-archive` | `archive_only` + `hidden` | remains `archive_only` | See Phase 12-E (§7.5) |
| `cartosat-3-gated` | `manual_only` + `hidden` | remains `manual_only` | No programmatic API path yet; Bhoonidhi catalog confirms only CartoSat-1 DEM |

No source in this phase reaches `product_active`. EOS-06 maximum exposure is `reference_only`
(GEO-003 precomputed context). Cartosat-3 remains permanently blocked until NRSC/NSIL
programmatic catalog/download is confirmed.

#### 7.4.2 Adapter and files to create or modify

- **Provider:** reuse `bhoonidhi_adapter.py` unchanged. All Bhoonidhi sources share the same
  adapter; only source collection IDs differ (already in `bhoonidhi.py` `SOURCE_COLLECTIONS`).
- **`services/ingestion/akasha_ingest/scene.py`** — confirm collection aliases for
  `EOS-04_SAR-MRS_L2B`, `EOS-06_OCM_LAC_NDVI_8DAY_360M`, and `irs-1c-liss3-archive` map
  correctly in `SOURCE_COLLECTIONS`.
- **`services/ingestion/akasha_ingest/composite.py`** — EOS-04 and NISAR SAR sources must have
  `supports_composite=False`. EOS-06 precomputed context: `supports_composite=False`.
  IRS-1C archive optical: composite is optional but uses `archive_only` validation profile.
- **`scripts/`** — prepare scripts already exist for EOS-04 (`prepare_eos04_sar_mrs_l2b_cogs.py`)
  and NISAR (`prepare_nisar_ssar_beta_gcov_cogs.py`). EOS-06 needs a clip+scale script for the
  precomputed NDVI tile. IRS-1C can reuse a modified LISS-3 prepare script.
- **`source_registry.py`** — transition rows one at a time (not batch) as each source's test data
  is confirmed. Update `lifecycle_state`, `schedule_state`, and `readiness_reasons` per gate.
- **`apps/api/app/raster/catalog_resolver.py`** — EOS-04 SAR row: `bandRoleMapping={}`,
  `supportedIndices=[]`, VV grayscale display (GEO-002). EOS-06 row: `analysisLevel=regional`,
  precomputed NDVI context display only.

#### 7.4.3 Validation profile requirements

| Source | Validation profile |
|--------|-------------------|
| `eos-04-sar-mrs-l2b` | `sar_backscatter` — `verify-composite` forbidden |
| `eos-06-ocm-lac-ndvi-8day-360m` | `precomputed_context` |
| `nisar-ssar-beta-gcov` (Bhoonidhi) | `sar_backscatter` |
| `irs-1c-liss3-archive` | `archive_only` |
| `cartosat-3-gated` | `visual_only` (no validator until API path confirmed) |

#### 7.4.4 Required tests and smoke checks

- **`tests/test_satellite_catalog_registry.py`** — assert EOS-04/EOS-06 rows do not contain
  contradictory combinations (SAR + optical index, `background_only` + `product_active`).
- **`tests/test_provider_adapter_contract.py`** — assert Bhoonidhi adapter can search EOS-04
  and EOS-06 collections using mock provider items with correct collection IDs.
- **Staging smoke (per source, one at a time):**
  `worker.py schedule-source --source eos-04-sar-mrs-l2b --aoi bangalore-60km --dry-run`.
- **Capped EOS-04 run:** `--max-downloads 1` → `verify-raster-product --profile sar_backscatter`;
  confirm SAR band order, dB scale, no optical indices in STAC metadata.
- **Capped EOS-06 run:** `--max-downloads 1` → `verify-raster-product --profile precomputed_context`.

#### 7.4.5 Rollout gates

1. At least one test product confirmed downloadable via Bhoonidhi and `gdalinfo`-validated for
   each source before any state transition.
2. Prepare script produces correct COG + STAC item for the target source.
3. Source-appropriate validation profile passes.
4. Operator explicitly transitions each source from `disabled` to `dry_run` or `background_only`
   **one source at a time**. No batch promotion of all ISRO gated sources simultaneously.
5. Cartosat-3 remains permanently blocked until NRSC/NSIL provides a programmatic catalog API;
   this gate is external and cannot be resolved by code changes.

#### 7.4.6 Explicit non-goals for Phase 12-D

- Do NOT compute optical vegetation indices from EOS-04 or NISAR — they are SAR sources (GEO-002).
- Do NOT promote EOS-06 precomputed NDVI to `product_active` for field statistics (GEO-003).
- Do NOT treat Cartosat-3 as buildable; it has no confirmed programmatic API.
- Do NOT use `verify-composite` for SAR or precomputed-context sources.
- Do NOT run Bhoonidhi jobs from a second staging host; `staging_bhoonidhi` host pool is required.

---

### 7.5 Phase 12-E — Archive/backfill: Landsat 7/5 and IRS-1C (TASK-077)

**When:** After Phase 12-B (USGS `usgs` client) is complete and Landsat 8/9 are validated.
Archive sources reuse the same `usgs` client (Landsat 7/5) or `bhoonidhi` adapter (IRS-1C);
no new provider clients are needed. Do NOT add archive sources speculatively — require a
confirmed operational need for historical baselines.

#### 7.5.1 Source rows — enforced constraints

| Source ID | Allowed `scheduleState` | Allowed `productExposure` | Forbidden |
|-----------|------------------------|--------------------------|----------|
| `landsat-7-c2-l2` | `archive_only` | `reference_only` | `routine`, `product_active`, `background_only` |
| `landsat-5-c2-l2` | `archive_only` | `reference_only` | `routine`, `product_active`, `background_only` |
| `irs-1c-liss3-archive` | `archive_only` | `reference_only` | `routine`, `product_active`, `background_only` |

All three sources are already set to `scheduleState=archive_only` + `cadence=archive_on_demand`
in `source_registry.py`. The `_validate_row()` fail-closed guard rejects any attempt to configure
a routine cadence interval for these sources. Current-monitoring timelines must never include them.

#### 7.5.2 Adapter and files to create or modify

- **`services/ingestion/akasha_ingest/usgs.py`** — extend with a `backfill_search(date_range)`
  path that accepts explicit date ranges (e.g. `1984-01-01` to `2013-12-31` for Landsat 5) and
  documents Landsat 7 SLC-off stripes in job artifacts.
- **`scripts/prepare_landsat_c2_l2_cogs.py`** — extend with `--sensor ETM+` (L7) and
  `--sensor TM` (L5) modes; include SLC-off gap documentation in the job artifact for L7
  acquisitions post-2003-05-31.
- **`source_registry.py`** — rows already set to `archive_only`; update `lifecycle_state` and
  `readiness_reasons` when client is confirmed working for each sensor. Do not change `schedule_state`.
- **`apps/api/app/raster/catalog_resolver.py`** — add/confirm archive rows with
  `analysisLevel=archive`; ensure these rows never appear in current-monitoring date pickers
  or best-observation selection.

#### 7.5.3 Validation profile requirements

| Source | Validation profile |
|--------|-------------------|
| `landsat-7-c2-l2` | `archive_only` (plus `optical_scene` for per-scene asset checks) |
| `landsat-5-c2-l2` | `archive_only` |
| `irs-1c-liss3-archive` | `archive_only` |

#### 7.5.4 Required tests and smoke checks

- **`tests/test_satellite_catalog_registry.py`** — assert that `archive_only` + routine schedule
  combination is rejected by `_validate_row()`. This test already exists and must remain green.
- **`tests/test_generic_scheduler_orchestrator.py`** — confirm orchestrator rejects routine
  scheduling attempts for `archive_only` sources and only accepts explicit backfill/on-demand windows.
- **Backfill smoke:**
  `worker.py schedule-source --source landsat-7-c2-l2 --aoi bangalore-60km --mode backfill --window 2000-01-01:2000-03-31 --max-downloads 2`.

#### 7.5.5 Rollout gates

1. Explicit operator backfill request required; no automated scheduler trigger is created.
2. `verify-raster-product --profile archive_only` passes for at least one scene per sensor.
3. Landsat 7 SLC-off artifacts are documented in job artifact metadata.
4. Archive sources never appear in BFF `/api/sources` as selectable current-monitoring sources.

#### 7.5.6 Explicit non-goals for Phase 12-E

- Do NOT schedule routine current-monitoring jobs for archive sources (SRC-007).
- Do NOT include Landsat 7/5 or IRS-1C in best-available timeline or date-pickers.
- Do NOT treat Landsat 7 SLC-off gaps as a defect to fix; document them in job artifacts.
- IRS-1C archive depends on Bhoonidhi availability of the `irs-1c-liss3-archive` collection;
  do not provision a second staging host specifically for IRS-1C archive access.

---

### 7.6 Phase 12-F — Commercial: Planet/JAXA/VHR vendors (TASK-078)

**When:** ONLY after **all** of the following hard prerequisites are met for the specific
commercial provider. These are not code-solvable blockers — they require business decisions.

> **Hard prerequisites for any commercial provider phase:**
> 1. Signed contract or licence agreement is in place.
> 2. Quota/pricing confirmed and documented in a commercial readiness record.
> 3. Explicit operator `allowPaidOrder=True` flag set and `commercial_readiness_record_id`
>    available for inclusion in `OrderRequest` objects.
> 4. Engineering readiness checklist (below) signed off.
>
> No code path may place a paid order or subscription before all four conditions are confirmed.
> `CommercialPlaceholderAdapterBase.order()` fails closed with `CommercialPreflightFailed` by
> default regardless of credentials (SEC-007, implemented in `providers/_placeholder.py`).

#### 7.6.1 Commercial readiness checklist (required before any commercial provider phase begins)

- [ ] Signed contract/licence from provider (Planet, JAXA reseller, or VHR vendor).
- [ ] Documented quota policy, AOI coverage confirmation, and pricing acknowledgement.
- [ ] `commercial_readiness_record_id` created and referenced in the operator runbook.
- [ ] `allowPaidOrder=True` added to deployment configuration by an authorized operator.
- [ ] Security review: credentials in deployment secrets only; no commits; redacted from all job artifacts.
- [ ] Provider delivery method confirmed (API download, cloud bucket, or deliver-to S3).
- [ ] Product format confirmed and compatible with Akasha prepare/composite pipeline.
- [ ] First test limited to `--max-downloads 1` with operator present on-call.

#### 7.6.2 Source rows — state transitions per provider

**Planet Labs (PlanetScope and SkySat)** — `commercialState=commercial_blocked` by default:

| Source ID | Current state | Target after readiness checklist | Commercial path |
|-----------|--------------|----------------------------------|-----------------|
| `planetscope` | `disabled` + `commercial_blocked` | `dry_run` → `background_only` → `routine` + `product_active` | Orders API; `allowPaidOrder` required |
| `skysat` | `disabled` + `commercial_blocked` | same staged path; slower (VHR tasking, not mosaic) | same |

**JAXA ALOS-2 free mosaic** — `commercialState=free`; no commercial gate for the annual mosaic,
but `cadence=archive_on_demand` in `source_registry.py` means `_validate_row()` rejects
`background_only` and `routine` schedule states for this source. The mosaic is an on-demand fetch
only, never a background-polling or routine-cadence source:

| Source ID | Current state | Target | Notes |
|-----------|--------------|--------|-------|
| `alos2-mosaic-25m` | `disabled` + `hidden` | `dry_run` → `archive_only` (on-demand only) | Fetch on explicit operator request; **no `background_only` or `routine` scheduling** |
| `alos2-palsar2` (scenes) | `disabled` + `commercial_blocked` | remains `commercial_blocked` | Commercial scenes; no order until contract |

**VHR vendors** — all `commercialState=commercial_blocked` permanently until per-vendor checklist:

| Source ID | State |
|-----------|-------|
| `superview-neo-1` | `disabled` + `commercial_blocked` (permanent until checklist) |
| `blacksky-gen-3` | `disabled` + `commercial_blocked` (permanent until checklist) |
| `kompsat-3a` | `disabled` + `commercial_blocked` (permanent until checklist) |

#### 7.6.3 Adapter and files to create or modify

**Planet (`planet_adapter.py`):**
- **`services/ingestion/akasha_ingest/planet.py`** — new `PlanetClient`: API-key auth; Data API
  search; Orders API order→poll→download pipeline.
- **`services/ingestion/akasha_ingest/providers/planet_adapter.py`** — replace
  `CommercialPlaceholderAdapterBase` subclass with real `PlanetAdapter` that calls
  `assert_commercial_ready()` before any Orders API call.
- **New prepare scripts** — PlanetScope analytic SR + UDM2→Akasha mask; SkySat ortho clip.

**JAXA free mosaic (`jaxa_adapter.py`):**
- **`services/ingestion/akasha_ingest/jaxa.py`** — new `JAXAClient` for annual mosaic static
  download from JAXA EORC portal. Scene commercial path remains a placeholder.
- **`services/ingestion/akasha_ingest/providers/jaxa_adapter.py`** — replace placeholder; free
  mosaic path only; scene `order()` raises `ProviderActionUnsupported` (scenes not commercially ready).
- **New SAR prepare script** — geocode/dB calibration from JAXA mosaic GeoTIFF.

**VHR vendors (`vendor_adapter.py`):**
- Per-vendor `vendor_adapter.py` specialization only after the specific vendor's contract.
  Generic `vendor_adapter.py` remains `CommercialPlaceholderAdapterBase` raising
  `CommercialPreflightFailed`.

#### 7.6.4 Validation profile requirements

| Source | Validation profile |
|--------|-------------------|
| `planetscope` | `optical_composite` — UDM2-derived Akasha mask |
| `skysat` | `visual_only` — VHR; no per-band field stats until explicitly validated |
| `alos2-mosaic-25m` | `sar_backscatter` — annual mosaic; no optical indices (GEO-002) |
| `alos2-palsar2` (scenes) | `sar_backscatter` — commercial-gated |
| VHR (`superview-neo-1`, `blacksky-gen-3`, `kompsat-3a`) | `visual_only` — commercial-gated |

#### 7.6.5 Required tests and smoke checks

- **`tests/test_provider_adapter_contract.py`** — assert `PlanetAdapter.order()` raises
  `CommercialPreflightFailed` when `allowPaidOrder=False` (default); assert
  `commercialState=commercial_blocked` makes `order()` fail even when `PLANET_API_KEY` is present.
  This is the SEC-007 test (already specified in TASK-012A).
- **`tests/test_generic_scheduler_orchestrator.py`** — assert `commercial_blocked` sources never
  enter `order_enabled` capabilities; assert orchestrator requires `allowPaidOrder` flag at call site.
- **Dry-run smoke (before any commercial action):**
  `worker.py schedule-source --source planetscope --aoi bangalore-60km --dry-run`.
  Expected plan shows `commercialState=commercial_blocked` until readiness checklist passes.

#### 7.6.6 Rollout gates (commercial path)

1. All items in commercial readiness checklist signed off.
2. `commercialState` updated to `approved` by authorized operator in source registry.
3. `allowPaidOrder=True` set in deployment config.
4. Dry-run through scheduler passes; no order placed.
5. Search-only run (Data API for Planet; EORC catalog for JAXA mosaic) confirms item availability.
6. `--max-downloads 1` + `--allow-paid-order` test with operator present on-call.
7. Order cost and quota confirmed within approved budget.
8. `verify-composite` or `verify-raster-product` passes.
9. **Commercial/live optical sources only** (`planetscope`, `skysat`, VHR vendors): operator flips
   `scheduleState=background_only` after all gates above pass.
   **`alos2-mosaic-25m` only**: operator flips `scheduleState=archive_only` for on-demand fetch
   access. `background_only` and `routine` are **forbidden** for this source — `cadence=archive_on_demand`
   causes `_validate_row()` to reject those states at registry load time.

#### 7.6.7 Explicit non-goals for Phase 12-F

- Do NOT place any Planet/JAXA scene/VHR orders without explicit commercial readiness + operator flag.
- Do NOT enable ALOS-2 scene-level commercial tasking through the free-mosaic adapter path.
- Do NOT advertise optical NDVI/MSAVI/NDWI on ALOS-2 mosaic or scene SAR products (GEO-002).
- Do NOT implement commercial providers in parallel with free providers during early scheduler
  migration; commercial paths must come last to avoid accidental cost during development.
- Do NOT use the generic `vendor_adapter.py` for Planet or JAXA — each uses its own named adapter.

---

### 7.7 Phase 12-G — NAIP: documentation-only / reference-only (TASK-079)

**Policy:** NAIP (USDA National Agriculture Imagery Program) is **permanently out-of-AOI** for
the India/Bangalore deployment. It covers the continental United States only (SRC-006).

#### 7.7.1 Permanent source state

```
naip-reference-only:
  aoiScope=reference_only   → productExposure=reference_only (forced by _validate_row)
  scheduleState=disabled    (no scheduler job ever created for bangalore-60km)
  commercialState=free
  readinessReasons=["SRC-006: NAIP is USA-only; out-of-AOI for bangalore-60km and all India deployments.",
                    "No executable ingestion pipeline for India deployments."]
```

This combination is validated by `_validate_row()` in `source_registry.py`. Any attempt to set
`productExposure=product_active` for NAIP raises `ValueError` at registry load time. This gate
exists now and must not be removed.

#### 7.7.2 Condition for onboarding NAIP

NAIP onboarding is only in scope if Akasha explicitly adds support for **US AOIs** as a separate
product scope (separate deployment, separate AOI configuration). This requires:

1. A separate US-AOI deployment scope decision from product/engineering leads.
2. A separate source-state registry configuration for the US deployment — a new registry file,
   not a modification to the India deployment's `source_registry.py`.
3. The US deployment must not share source rows or registry configuration with the India deployment.

Until a US deployment scope is approved, NAIP requires:
- **No code changes.** Preserve the existing `naip-reference-only` registry row.
- **No STAC seed collections** for `bangalore-60km`.
- **No provider calls, no COG preparation, no STAC registration.**

#### 7.7.3 Existing code to preserve (do not modify)

- `source_registry.py` row for `naip-reference-only` with `aoi_scope=AoiScope.REFERENCE_ONLY`.
- `tests/test_satellite_catalog_registry.py` assertion that `naip-reference-only` is excluded for
  `bangalore-60km` (TASK-005/TASK-006 tests).
- `satellite-catalog.md` NAIP entry (US-only coverage, no India AOI).
- This document §H (NAIP ⚪ out-of-AOI section).

#### 7.7.4 Explicit non-goals for Phase 12-G

- Do NOT implement `usda_adapter.py` beyond the existing placeholder for the India deployment.
- Do NOT create NAIP STAC seed collections for `bangalore-60km`.
- Do NOT include NAIP in the best-observation resolver or any India AOI date-picker.
- Do NOT modify the `naip-reference-only` source row's `aoi_scope` or `product_exposure` for
  India deployment; if US AOI support is approved, create a **separate** source configuration.

---

### 7.8 Onboarding sequence summary

| Phase | Provider | Source IDs | Entry prerequisite | Starting state | Target max state |
|-------|----------|-----------|-------------------|----------------|-----------------|
| 12-A | CDSE | `sentinel-2-l2a`, `sentinel-1-grd` | Phases 0–9 stable; CDSE credentials | `disabled` + `hidden` | S2: `routine` + `product_active`; S1: `background_only` |
| 12-B | USGS | `landsat-8-c2-l2`, `landsat-9-c2-l2` | Cloud STAC accessible; 12-A unit tests | `disabled` + `hidden` | `routine` + `product_active` |
| 12-C | Earthdata/ASF | `modis-13q1-061`, `nisar-ssar-beta-gcov` | `EARTHDATA_TOKEN`; NISAR ARD confirmed | `disabled` + `hidden` | MODIS: `background_only` + `reference_only`; NISAR: `background_only` |
| 12-D | ISRO gated | `eos-04-sar-mrs-l2b`, `eos-06-ocm-lac-ndvi-8day-360m`, `nisar-ssar-beta-gcov` (Bhoonidhi), `irs-1c-liss3-archive`, `cartosat-3-gated` | Per-source test data confirmed; Bhoonidhi adapter working | `disabled`/`archive_only`/`manual_only` + `hidden` | `background_only`/`archive_only` per source; Cartosat-3 remains `manual_only` |
| 12-E | Archive/backfill | `landsat-7-c2-l2`, `landsat-5-c2-l2`, `irs-1c-liss3-archive` | USGS client from 12-B; confirmed operational need | `archive_only` + `hidden` | `archive_only` + `reference_only` (on-demand only) |
| 12-F | Commercial | `planetscope`, `skysat`, `alos2-mosaic-25m`, `alos2-palsar2`, VHR vendors | Commercial readiness checklist signed (per vendor) | `disabled` + `commercial_blocked` | ALOS-2 mosaic: `archive_only` (on-demand); others: `commercial_blocked` until contract |
| 12-G | NAIP/reference | `naip-reference-only` | US AOI scope decision (external) | `reference_only` (permanent) | `reference_only` (permanent; no change) |

**State transitions always proceed linearly:**
`disabled → dry_run → background_only → routine` (for active optical sources)
`disabled → archive_only` (for archive sources, once needed)
`disabled` / `commercial_blocked` → unchanged (commercial and permanently-gated sources)

No source in Phase 12 may skip a validation gate to reach `product_active`. The scheduler's
fail-closed validation in `source_registry._validate_row()` enforces this at registry load time.
Operator promotion is always explicit; there is no automatic promotion based on passing test results.
