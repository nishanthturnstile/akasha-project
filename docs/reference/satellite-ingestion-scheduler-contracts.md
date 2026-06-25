---
title: Satellite Ingestion Scheduler Contracts
status: reference
last_updated: 2026-06-24
owner: Akasha ingestion
related:
  - impl-plan/architecture-satellite-ingestion-scheduler-1.md
  - reference/satellite-ingestion-onboarding-matrix.md
  - reference/satellite-catalog.md
  - data-ingestion-and-satellite-rules.md
  - staging-ingestion-developer-guide.md
---

# Satellite Ingestion Scheduler Contracts

This is the Phase 0 contract for the provider-agnostic satellite ingestion scheduler. It freezes
the cross-service vocabulary and rollout gates that must stay stable before runtime scheduler code
is enabled.

Phase 0 does **not** replace the existing Bhoonidhi timers, frontend source ranking, or
source-specific product timelines. It defines the contracts that later scheduler phases must
implement and test.

## 1. Typed source-state schema

Every scheduler source row must keep source readiness concerns orthogonal. Do not overload
`mvp_enabled`, `availabilityStatus`, or one `state` string to mean scheduling, product exposure,
commercial readiness, AOI applicability, and validation status.

| Field | Required values / shape | Contract |
|---|---|---|
| `catalogSlug` | `string` | Slug from `docs/reference/satellite-catalog.md`. Required unless `internalLegacy=true` / `internal_legacy=true`. |
| `catalogPlatform` | `string` | Human-readable platform name from the catalog. |
| `sourceId` | `string` | Akasha source id used by ingestion, STAC, and BFF source registries. |
| `providerAdapter` | `bhoonidhi`, `cdse`, `usgs`, `earthdata`, `asf`, `planet`, `jaxa`, `vendor`, `usda` | Adapter that owns provider auth/search/download/order behavior. Unknown adapters fail closed. |
| `productFamily` | `optical_reflectance`, `sar_backscatter`, `precomputed_index`, `visual_context`, `archive_context` | Product family used to choose prepare and validation profiles. |
| `instrumentMode` | `string` or `null` | Sensor/mode discriminator such as `LISS3`, `LISS4_MX70`, `AWIFS`, `IW_GRD`, or `OLI_TIRS`. |
| `productVariant` | `string` or `null` | Variant discriminator such as `BOA`, `L2A`, `L2B`, `GCOV`, `8DAY_NDVI`. |
| `analysisLevel` | `field`, `regional`, `context`, `archive`, `visual_only` | Tells product code how the source may be used. |
| `lifecycleState` | `catalogued`, `provider_configured`, `search_enabled`, `download_enabled`, `order_enabled`, `prepare_enabled`, `validate_enabled` | Highest lifecycle milestone reached. It does not by itself make a source selectable. |
| `scheduleState` | `disabled`, `dry_run`, `manual_only`, `background_only`, `routine`, `archive_only` | Scheduler posture. `routine` means real recurring jobs are allowed after cutover. |
| `capabilities` | array containing any of `search_enabled`, `download_enabled`, `order_enabled`, `prepare_enabled`, `validate_enabled` | Actions the scheduler may invoke. Unsupported actions fail closed. |
| `productExposure` | `hidden`, `background_only`, `product_active`, `reference_only` | Product/BFF exposure. `background_only` may run ingestion but remains non-selectable. |
| `commercialState` | `free`, `approved`, `commercial_blocked` | Cost/licensing gate. Paid order paths additionally require an explicit operator flag. |
| `aoiScope` | `in_aoi`, `partial_aoi`, `out_of_aoi`, `reference_only` | Applicability to the deployment AOI. |
| `validationState` | `unvalidated`, `validation_pending`, `validation_failed`, `validation_passed` | Last accepted validation posture for the source/AOI/product profile. |
| `validationProfile` | `optical_composite`, `optical_scene`, `sar_backscatter`, `precomputed_context`, `archive_only`, `visual_only` | Profile used by verification and release gates. |
| `cadence` | object | Includes interval, lookback window, composite window, max downloads, rate limit hints, and first-run policy. |
| `hostPool` | `staging_bhoonidhi`, `approved_worker`, `manual_only`, `none` | Runtime host class allowed for non-dry-run work. |
| `readinessReasons` | array of string codes | Machine-readable explanations such as `missing_credentials`, `coverage_below_threshold`, `commercial_approval_required`, `out_of_aoi`, `reference_only`, or `awaiting_validation`. |

### 1.1 Precedence rules

The scheduler, BFF, and monitoring UI must apply these gates in order:

1. Unknown `providerAdapter`, `sourceId`, or `catalogSlug` fails closed.
2. `aoiScope=out_of_aoi` or `aoiScope=reference_only` forces `productExposure=reference_only` and prevents routine scheduling.
3. `commercialState=commercial_blocked` disables `order_enabled` actions even when credentials exist.
4. `validationState != validation_passed` prevents `productExposure=product_active` for user-selectable sources.
5. `scheduleState=disabled` wins over all capabilities.
6. `scheduleState=dry_run` may create plans, job records, and redacted artifacts, but may not download, order, prepare, composite, upload, or register STAC.
7. `scheduleState=background_only` may run allowed non-commercial actions, but the source remains non-selectable unless a later validated product decision changes `productExposure`.
8. `scheduleState=archive_only` only runs explicit backfill/on-demand windows, never current-monitoring routine cadence.

### 1.2 Invalid combinations

These combinations are invalid and must be rejected by registry validation before any job runs:

| Invalid combination | Why it fails |
|---|---|
| `commercialState=commercial_blocked` plus `capabilities` containing `order_enabled` | Prevents accidental paid/commercial orders. |
| `scheduleState=archive_only` plus routine cadence | Archive sources have no new acquisitions and must not run current monitoring. |
| `scheduleState=background_only` plus `productExposure=product_active` | A background-only scheduled source cannot be product-selectable. |
| `aoiScope=out_of_aoi` plus `productExposure=product_active` | Out-of-AOI rows are reference-only for India deployments. |
| `validationState=validation_failed` plus `productExposure=product_active` | Failed validation cannot be user-selectable. |
| Executable row without `catalogSlug` and without `internalLegacy=true` | Every source must trace back to the satellite catalog. |
| `providerAdapter=vendor` plus missing commercial readiness record | Vendor/commercial adapters are disabled until licensing is documented. |

## 2. Catalogue slug to source mapping contract

Every source-state row must trace to exactly one catalog slug, except explicitly marked
`internalLegacy` / `internal_legacy` rows. One catalog platform may map to many source rows when
instrument modes or product variants have different validation, cadence, or product behavior.

Required mapping fields are:

```json
{
  "catalogSlug": "resourcesat-2a",
  "catalogPlatform": "ResourceSat-2A",
  "sourceId": "resourcesat-2a-liss3-boa",
  "providerAdapter": "bhoonidhi",
  "productFamily": "optical_reflectance",
  "instrumentMode": "LISS3",
  "productVariant": "BOA",
  "analysisLevel": "field",
  "validationProfile": "optical_composite",
  "productExposure": "product_active"
}
```

Initial one-to-many ResourceSat mapping:

| `catalogSlug` | `sourceId` | `instrumentMode` | `productVariant` | `analysisLevel` | `validationProfile` | Initial `productExposure` |
|---|---|---|---|---|---|---|
| `resourcesat-2a` | `resourcesat-2a-liss3-boa` | `LISS3` | `BOA` | `field` | `optical_composite` | `product_active` |
| `resourcesat-2a` | `resourcesat-2a-liss4-mx70-l2` | `LISS4_MX70` | `L2` | `field` | `optical_composite` | `product_active` |
| `resourcesat-2a` | `resourcesat-2a-awifs-boa` | `AWIFS` | `BOA` | `regional` | `optical_composite` | `background_only` |

Rows for `sentinel-2`, `sentinel-1`, `landsat-8`, `landsat-9`, `modis`,
`eos-04-risat`, `eos-06-oceansat-3`, `nisar`, `landsat-7`, `landsat-5`, `irs-1c`,
`planetscope`, `skysat`, `superview-neo-1`, `blacksky-gen-3`, `kompsat-3a`,
`alos-2-palsar-2`, `cartosat-3`, and `naip` must be added in the source-state
registry before those sources can be scheduled. Commercial and out-of-AOI rows may be present as
`commercial_blocked`, `reference_only`, or `out_of_aoi`; they still count as mapped.

## 3. Job-state ownership and redacted artifacts

Ingestion owns scheduler raw state:

- SQLite job ledger under `/srv/akasha/ingestion/scheduler/scheduler.sqlite`.
- Raw provider request/response archives under `/srv/akasha/ingestion/scheduler/artifacts/raw`.
- Redacted job artifacts under `/srv/akasha/ingestion/scheduler/artifacts/redacted`.
- Redacted scheduler snapshot at `/srv/akasha/ingestion/scheduler/schedule_state.json`.
- Redacted per-job summary snapshots under `/srv/akasha/ingestion/scheduler/jobs/<jobId>/summary.json`.

The BFF reads only redacted snapshots through explicit read-only configuration. It must not read
raw provider archives, unrestricted job directories, provider credential files, MinIO internals, or
arbitrary filesystem paths. If later phases require API-owned job history tables, those tables must
be SQLAlchemy ORM models in `apps/api/app/models.py` and Alembic revisions under
`apps/api/alembic/`; do not add raw SQL migrations under `apps/api/migrations`.

Artifacts must answer these questions without exposing secrets:

- What source/AOI/window was scheduled?
- What provider input was sent, after redaction?
- What was found, selected, downloaded, rejected, prepared, uploaded, and registered?
- Why did validation pass or fail?
- What lock/runtime/cutover owner was used?
- When is the next run due?

## 4. Scheduler job ledger contract

The scheduler ledger is the source of truth for scheduling decisions. It is separate from the
existing ingestion/product ledger and must calculate `nextDueAt` from scheduler job history, not
from frontend product availability alone.

Required job fields:

| Field | Contract |
|---|---|
| `jobId` | Opaque id; never derived from raw path names. |
| `sourceId`, `aoiId` | Scheduler work unit. Locks are scoped by provider/source/AOI. |
| `providerAdapter` | Adapter invoked for this run. |
| `windowStart`, `windowEnd`, `lookbackDays`, `compositeWindowDays` | Exact temporal scope used for due decision and search. |
| `scheduleMode` | `dry_run`, `manual`, `background`, `routine`, or `backfill`. |
| `status` | `planned`, `queued`, `running`, `succeeded`, `failed`, `validation_failed`, `blocked_by_lock`, `cancelled`, `skipped_not_due`, `skipped_gated`. |
| `failureKind` | One of the alert/runbook categories in section 9, or `null`. |
| `counts` | Found, selected, downloaded, rejected, prepared, uploaded, registered, validation failures. |
| `artifactHandles` | Opaque redacted handles, not raw filesystem paths. |
| `startedAt`, `finishedAt`, `createdBy`, `runtimeHost` | Audit fields. |
| `lastSuccessfulRunAt`, `nextDueAt` | Due-state fields derived by the scheduler. |

Ledger runtime rules:

- SQLite must run with WAL mode and a busy timeout of at least 5000 ms.
- First run is due immediately when there is no previous terminal job for the same source/AOI and
  the source is schedulable.
- Failed runs keep the normal cadence unless a source-specific retry/backoff policy is configured.
- `nextDueAt` is based on the latest terminal scheduler job for the same source/AOI plus cadence;
  manual/backfill runs may update validation history but do not shorten routine cadence unless
  explicitly marked as cadence-affecting.
- Retain redacted summaries for at least 90 days or 1000 jobs, whichever is larger.
- Raw provider artifacts are pruned earlier according to provider policy, but never before a
  redacted summary is written.
- Stale locks may be reclaimed only when the owning process is gone and the lock age exceeds the
  configured stale-lock threshold.
- Scheduler runs fail closed when disk free space under `/srv/akasha` is below the configured
  pressure threshold.

## 5. Monitoring API boundary

Monitoring APIs are BFF-owned read APIs over redacted scheduler snapshots. They are operational
visibility endpoints, not a raw artifact browser.

Initial API shape:

| Endpoint | Contract |
|---|---|
| `GET /api/monitoring/ingestion-schedules` | Paginated source/AOI schedule rows with filters for source, AOI, provider, owner, schedule state, validation state, and due status. |
| `GET /api/monitoring/ingestion-jobs` | Paginated job summaries with filters for source, AOI, provider, status, failure kind, date range, and schedule mode. |
| `GET /api/monitoring/ingestion-jobs/{jobId}` | Capped job detail payload with redacted inputs, counts, validation summary, errors, next-due data, and opaque artifact handles. |

API rules:

- Default page size is capped at 50; max page size is 200.
- Job detail is capped; full logs and raw artifacts are CLI/operator-only unless a later elevated
  role flow is explicitly designed.
- Frontend responses must not expose raw server paths, signed provider URLs, object-store
  credentials, provider usernames, tokens, internal hostnames, or full logs.
- `artifactHandles` are opaque ids. A handle may identify a redacted artifact category, but not a
  filesystem path.
- All errors use the existing Akasha error shape `{ "error": { "code", "message", "details" } }`.
- Operator-only artifact access, if added later, requires owner/admin or a dedicated elevated
  operator role and must still return redacted content by default.

## 6. Ownership and rollback

Install the scheduler disabled or dry-run first. A source/AOI must have exactly one active owner.
ResourceSat/Bhoonidhi production ownership has now moved to the provider-agnostic scheduler; the
old source-specific Bhoonidhi timers were removed and are not rollback targets.

Ownership fields:

| Field | Contract |
|---|---|
| `sourceId` | Akasha source id. |
| `aoiId` | AOI id, initially `bangalore-60km`. |
| `ownedBy` | `scheduler_dry_run`, `scheduler_active`, or `manual_only`. `legacy_timer` remains a historical enum value only; no current ResourceSat source uses it. |
| `schedulerEnabled` | Boolean; true only for `scheduler_dry_run` or `scheduler_active`. |
| `cutoverDate` | ISO date or `null`. |
| `rollbackCommand` | Operator command or runbook reference for pausing scheduler ownership and using bounded manual scheduler runs. |

Current ownership matrix:

| `sourceId` | `aoiId` | `ownedBy` | `schedulerEnabled` | `cutoverDate` | Rollback command |
|---|---|---|---:|---|---|
| `resourcesat-2a-liss3-boa` | `bangalore-60km` | `scheduler_active` | `true` | `2026-06-25` | Disable scheduler timer; use `scripts/staging_ingestion_job.py trigger --source resourcesat-2a-liss3-boa ...` for bounded manual runs. |
| `resourcesat-2a-liss4-mx70-l2` | `bangalore-60km` | `scheduler_active` | `true` | `2026-06-25` | Disable scheduler timer; use `scripts/staging_ingestion_job.py trigger --source resourcesat-2a-liss4-mx70-l2 ...` for bounded manual runs. |
| `resourcesat-2a-awifs-boa` | `bangalore-60km` | `scheduler_active` | `true` | `2026-06-25` | Disable scheduler timer; use `scripts/staging_ingestion_job.py trigger --source resourcesat-2a-awifs-boa ...` for bounded manual runs. |

Canary sequence:

1. Install scheduler in `dry_run` mode and verify redacted snapshots.
2. Select one canary source/AOI, initially `resourcesat-2a-liss3-boa` + `bangalore-60km`.
3. Confirm automatic and ad hoc scheduler paths use the same canonical worker lock directory.
4. Enable scheduler active mode with `maxConcurrentSources=1`.
5. Verify one dry-run and one capped real run before widening the run budget.
6. Record `cutoverDate`, owner, and rollback command in the ownership matrix.

Rollback sequence:

1. Stop scheduler active mode; stop and disable `akasha-ingestion-scheduler.timer`.
2. Confirm no queued/running scheduler job owns the source/AOI.
3. Disable scheduler ownership for the source/AOI in the registry.
4. Use `scripts/staging_ingestion_job.py trigger` for bounded manual runs while the timer is paused.
5. Run monitoring/doctor checks before re-enabling the scheduler timer.

## 7. Approved-runtime preflights

Providers that require restricted network/runtime conditions must fail closed before non-dry-run
work starts.

Bhoonidhi rules:

- Non-dry-run Bhoonidhi jobs may run only through the scheduler wrapper
  (`/opt/akasha/bin/akasha-ingestion-scheduler.sh`) or the restricted ad hoc wrapper
  (`/opt/akasha/bin/akasha-ingestion-job.sh`) on an approved host.
- Direct `worker.py schedule-*`, future scheduler commands, or direct Docker Compose invocations
  must fail closed unless the run is `dry_run` or an explicit local-test mode is enabled.
- Approved-host checks must validate the host pool, `/srv/akasha` data root, source/AOI lock path,
  compose discovery, and required Bhoonidhi environment without printing secrets.
- Dry-run/local-test modes may validate source state, due decisions, and redacted artifacts, but may
  not download provider archives, prepare COGs, upload to MinIO, or register STAC.

Commercial provider rules:

- Paid order/task/subscription methods require all of `commercialState != commercial_blocked`,
  `allowPaidOrder=true`, an explicit operator command flag, and a documented readiness record.
- Credentials alone never make commercial actions executable.

## 8. ResourceSat LISS-3 release-blocking invariants

Scheduler work must not regress the current ResourceSat LISS-3 production semantics. These
invariants are release-blocking:

| Area | Required invariant |
|---|---|
| Analytic bands | Four bands in order `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`. |
| Display | Default display is ResourceSat FCC, role order `NIR,RED,GREEN`, resolving to `bidx=3,2,1`. |
| Mask | No Sentinel SCL. Use Akasha threshold mask v1: `0=nodata`, `1=valid`, `2=cloud`, `3=shadow`, `4=water`; keep `{1,4}` by default. |
| Reflectance | `corrected = dn * 0.0001 + 0.0`; do not apply Sentinel's `-0.1` offset. |
| Resampling | Nearest-neighbour for categorical masks; bilinear/cubic for continuous reflectance. |
| Assets | Analytic COG and mask COG remain separate assets. |
| Keys | Scene/composite object keys remain deterministic and idempotent. |
| STAC | `eo:bands`, `raster:bands`, `akasha:band_role_mapping`, `akasha:mask_asset`, excluded mask classes, coverage/usable metrics, and `akasha:composite=true` for composites are preserved. |
| Upsert | STAC load remains upsert/idempotent. |
| Indices | LISS-3 supports NDVI, MSAVI, NDMI, NDWI_GREEN_NIR; never NDRE/RECI. |

Parity tests for scheduler phases must cover source payloads, prepare manifests, STAC seed/output
metadata, object-key construction, mask-class handling, and date/tile serving before any scheduler
source can be product-active.

## 9. Alerts and runbooks

Scheduler monitoring must classify failures into a small set of operator-actionable categories.

| Alert/failure kind | Trigger | First response |
|---|---|---|
| `missed_due_run` | `nextDueAt` is older than grace window and no job is running. | Check scheduler timer, ownership matrix, and locks. |
| `repeated_failures` | Same source/AOI fails N consecutive runs. | Inspect redacted job detail and latest run logs through operator CLI. |
| `stale_search` | No successful search within source freshness SLA. | Check provider auth, egress, and source availability. |
| `failed_validation` | Job produced output but validation failed. | Use source-specific validation report; keep product exposure gated. |
| `low_coverage` | Coverage below source threshold. | Widen window/backfill or keep source gated; do not lower threshold silently. |
| `disk_pressure` | `/srv/akasha` free space below configured threshold. | Stop new non-dry-run jobs and prune approved old artifacts. |
| `minio_upload_failed` | Upload or object verification failed. | Check MinIO health/credentials and retry idempotently. |
| `stac_registration_failed` | STAC upsert failed. | Check STAC API/pgSTAC health, then retry manifest ingest. |
| `provider_auth_or_rate_limit` | Provider auth, 401/403/429, session cap, or rate-limit response. | Back off; rotate/check secrets only through deployment secret store. |
| `stale_lock` | Lock older than stale-lock threshold with no owning process. | Reclaim only after confirming process death. |
| `rollback_required` | Scheduler run fails release gate. | Pause scheduler ownership and use bounded manual scheduler runs per section 6. |

Runbooks must preserve the staging guardrails: keep raster data under `/srv/akasha`, use wrappers,
avoid direct heavy Docker commands on staging, and redact secrets in every copied artifact.
