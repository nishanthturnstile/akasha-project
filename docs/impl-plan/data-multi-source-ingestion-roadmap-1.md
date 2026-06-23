---
goal: Extend the Akasha ingestion pipeline from ISRO ResourceSat-2A to the full multi-satellite catalog
version: 1.1
date_created: 2026-06-22
last_updated: 2026-06-23
owner: Akasha ingestion
tags: [data, architecture, ingestion, satellite, feature]
---

# Introduction

This plan operationalizes [satellite-ingestion-onboarding-matrix.md](../reference/satellite-ingestion-onboarding-matrix.md):
it sequences the work to onboard the remaining catalog satellites onto the ingestion pipeline
already proven for ISRO ResourceSat-2A. Work is grouped by **data provider** because each provider
requires its own search/download client, authentication model, rate limits, and licensing gates.

This v1.1 update incorporates the pre-implementation review completed on 2026-06-23. The main
change is that **shared enablement is larger than a provider factory**: the current worker,
verification commands, manifest discovery, source registry state, and BFF composite/date resolution
still contain ResourceSat-specific assumptions. Those cross-cutting blockers must be completed before
Sentinel, Landsat, MODIS, or commercial providers are implemented.

Every source stays gated until it passes the onboarding gate in
[data-ingestion-and-satellite-rules.md](../data-ingestion-and-satellite-rules.md): registry row +
adapter/prep + source-aware tests + staging dry-run + capped real run (`--max-downloads 1`) + the
correct source-aware verification command. Use `worker.py verify-composite` only for sources that
produce optical composites; use the new source-aware raster/context/SAR verification for
display-only SAR, context, and archive sources.

## 1. Requirements & Constraints

- **REQ-001**: Preserve all existing API/data contracts from Slices 0–3 and the ResourceSat production path; additive changes only.
- **REQ-002**: Each new source must define all 9 pipeline layers (client, worker dispatch, pipeline registry, prepare script, scene/composite or explicit no-composite policy, STAC, storage, BFF registry, indices) per the matrix §1.
- **REQ-003**: A new source is exposed to users only after staging dry-run → capped real run → the source's verification gate passes. Use `verify-composite` only for composite-capable optical sources; use `verify-raster-product`/context/SAR verification for non-composite sources.
- **REQ-004**: Frontend remains data-driven from `/api/sources`; no frontend code change is required for standard optical/SAR/context sources unless a new UX control is introduced.
- **REQ-005**: Optical sources declare band roles + mask + indices; SAR sources declare `supportedIndices=[]`, `maskAsset=None`, grayscale display, and `supports_composite=False`.
- **REQ-006**: Source status semantics must be explicit and consistent across ingestion registry, BFF registry, and STAC seed docs: `ingestionEnabled`, `operatorEnabled`, `userSelectable`, `availabilityStatus`, `gatedReason`, `analysisLevel`, and `mvp_enabled` must not contradict each other.
- **REQ-007**: Generic orchestration must support source-specific raw roots, work roots, output profiles, rate limits, and verification profiles. Do not reuse `BHOONIDHI_*` settings for non-Bhoonidhi providers.
- **REQ-008**: Composite/date serving must be source-agnostic. Any source with `supports_composite=True` must register dated STAC composite items with `akasha:composite=true`, and the BFF must prefer those composite items for date-level tiles/statistics.
- **REQ-009**: Sentinel-2/Sentinel-1 can become ingestion-enabled for operator validation, but they remain non-production-selectable unless a deliberate rollout flag enables them. Preserve the current `AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES` default behavior.
- **REQ-010**: Commercial sources must include cost/quota/order-state safeguards before any code path can place a paid order.
- **SEC-001**: Provider credentials are deployment env/secret-manager entries; never commit them. Redact secrets, bearer tokens, API keys, S3 signed URLs, provider order URLs, and provider usernames in logs/manifests/`command.txt`.
- **SEC-002**: ISRO/Bhoonidhi search/download run **only** from the staging VM with approved egress `20.219.3.35`; non-ISRO providers may run from any worker host with credentials.
- **SEC-003**: Local populated `.env` files must stay ignored and must not be copied into tickets, docs, prompts, or shared artifacts. Rotate any provider credential if it is ever pasted into a shared context.
- **CON-001**: Commercial sources (PlanetScope, SkySat, SuperView NEO-1, BlackSky Gen 3, KOMPSAT-3A, ALOS-2 scenes, Cartosat-3) require a signed licence/quota before `mvp_enabled=True` or `userSelectable=True`.
- **CON-002**: Cartosat-3 is absent from the validated Bhoonidhi API catalog — no programmatic catalog/download path exists; treat as manual VHR context only.
- **CON-003**: NISAR calibrated analysis-ready products are not globally available until ~Jul 2026; keep data-gated until then.
- **CON-004**: NAIP covers the US only and must never be wired as a selectable source over `bangalore-60km`.
- **CON-005**: Pinned GDAL/rasterio/rio-tiler/TiTiler versions must not float to `latest`.
- **CON-006**: CDSE integrations must use current supported endpoints only: `https://stac.dataspace.copernicus.eu/v1/` for STAC and `https://catalogue.dataspace.copernicus.eu/odata/v1/` for OData. Do not build new code on deprecated OpenSearch or legacy STAC endpoints.
- **CON-007**: CDSE and other catalog clients must split wide searches into bounded time windows and must not rely on deep skip/page pagination beyond provider limits.
- **CON-008**: Sentinel-1 SNAP preprocessing must run through the existing separate SAR image/service (`services/ingestion-sar/Dockerfile`, `ingestion-sar` compose service), not by bloating the normal `ingestion-worker` image.
- **GUD-001**: Reuse the [bhoonidhi.py](../../services/ingestion/akasha_ingest/bhoonidhi.py) client behavior shape (`search`, `download_product`, manifest builder) for every provider module, but normalize provider-specific responses into source-agnostic manifests.
- **GUD-002**: Prefer the cloud-native STAC+COG path (Planetary Computer / Element84 / USGS) for Landsat to avoid SNAP/GDAL product transforms.
- **GUD-003**: Default display is the source's natural imagery (RGB/FCC/grayscale/context), never an index.
- **GUD-004**: Fail closed for unknown sources. Remove any fallback that routes an unknown source to the ResourceSat prepare script.
- **PAT-001**: Band NAME→POSITION translation lives only in [indices.py](../../apps/api/app/raster/indices.py); never hard-code TiTiler positional bands elsewhere.
- **PAT-002**: Analytic COG and categorical mask COG stay as separate assets; nearest-neighbour resampling for masks, bilinear/cubic for reflectance.
- **PAT-003**: Verification is profile-driven. Expected assets, band counts, mask classes, dtype, scale/offset, CRS, resolution, overviews, and STAC metadata are declared per source/profile.

## 2. Implementation Steps

### Implementation Phase 1 — Source registry and verification readiness (blocking)

- GOAL-001: Make source state, validation profiles, and registry consistency explicit before adding any provider client.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Define source-state semantics in [services/ingestion/akasha_ingest/pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) and [apps/api/app/raster/catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py): distinguish `mvp_enabled`/ingestion-enabled, operator-enabled, user-selectable, `availabilityStatus`, `gatedReason`, and `analysisLevel`. | | |
| TASK-002 | Add registry consistency tests in `tests/test_source_registry_consistency.py` comparing `pipeline_registry.PIPELINE_SOURCES`, BFF `_SOURCE_REGISTRY`, and `data/seed/stac/*-collection.json` for matching source IDs, collection IDs, provider names, source kind, asset names, and gating state. | | |
| TASK-003 | Add source-aware validation profiles in a new `services/ingestion/akasha_ingest/validation_profiles.py` for ResourceSat LISS-3/LISS-4/AWiFS, Sentinel-2, Sentinel-1, EOS-04, NISAR, EOS-06 context, IRS-1C archive, Landsat C2 L2, MODIS, and future commercial placeholders. | | |
| TASK-004 | Refactor [storage.py](../../services/ingestion/akasha_ingest/storage.py) COG metadata verification to use validation profiles instead of hard-coding ResourceSat BOA analytic band count `4`; explicitly support LISS-4's 3-band analytic profile. | | |
| TASK-005 | Add `worker.py verify-raster-product --source <id> --manifest ...` for scene/context/SAR/archive manifests and keep `verify-composite` for optical composite manifests only. | | |
| TASK-006 | Add tests proving `verify-composite` rejects SAR/context sources with a clear error and `verify-raster-product` accepts valid SAR/context/archive fixtures. | | |
| TASK-007 | Recreate or add seed STAC collections only for sources being actively onboarded. If Sentinel-2/Sentinel-1 are re-enabled for ingestion, add `data/seed/stac/sentinel-2-l2a-collection.json` and `data/seed/stac/sentinel-1-grd-collection.json`; do not reintroduce user-selectability by default. | | |

### Implementation Phase 2 — Generic provider orchestration (blocking)

- GOAL-002: Break Bhoonidhi hardcoding in the worker and introduce source-agnostic search/download/prepare/ingest orchestration.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Define a `ProviderClient` protocol in `services/ingestion/akasha_ingest/providers/__init__.py` with `search(source: PipelineSource, aoi: dict, datetime_range: str, limit: int) -> list[dict]`, `download_product(source: PipelineSource, candidate: dict, destination: Path) -> dict`, and optional provider-specific manifest helpers. | | |
| TASK-009 | Add `services/ingestion/akasha_ingest/providers/factory.py` with `get_provider_client(provider: str)`. Supported initial providers: `bhoonidhi`; future providers: `cdse`, `usgs`, `earthdata`, `planet`, `jaxa`, `vendor`. Unknown providers must raise `KeyError` with a clear message. | | |
| TASK-010 | Make [bhoonidhi.py](../../services/ingestion/akasha_ingest/bhoonidhi.py) conform to the provider protocol while preserving the current `bhoonidhi-search`, `bhoonidhi-download`, and `bhoonidhi-sync` behavior as aliases. | | |
| TASK-011 | Define canonical normalized search and download manifest schemas in `services/ingestion/akasha_ingest/manifests.py`. Required fields: `type`, `version`, `source_id`, `provider`, `collection`, `aoi`, `search.datetime`, `candidates[].provider_item_id`, `candidates[].item_id`, `candidates[].datetime`, `candidates[].bbox`, `selection.selected_product_ids`, and redacted provider metadata. | | |
| TASK-012 | Add generic worker commands in [worker.py](../../services/ingestion/worker.py): `search --source <id>`, `download --source <id> --manifest ...`, `prepare --source <id> --download-manifest ...`, and `ingest --source <id> --manifest-glob ...`. | | |
| TASK-013 | Replace `sync.prepare_script_name()` unknown-source fallback with fail-closed behavior. Unknown source IDs must raise `KeyError`; no unknown source may route to `prepare_resourcesat_liss3_boa_cogs.py`. | | |
| TASK-014 | Generalize the SQLite ledger in [sync.py](../../services/ingestion/akasha_ingest/sync.py) to store `provider`, `source_id`, `provider_item_id`, `product_id`, `scene_key`, `status`, retry count, bytes, and redacted error. Preserve existing Bhoonidhi ledger compatibility. | | |
| TASK-015 | Add source-specific raw/work/output root settings in config/env examples. Use `AKASHA_RAW_ROOT`, `AKASHA_WORK_ROOT`, and provider-specific overrides (`BHOONIDHI_RAW_ROOT`, `CDSE_RAW_ROOT`, etc.) rather than applying `BHOONIDHI_*` paths to all providers. | | |
| TASK-016 | Add `tests/test_provider_factory.py`, `tests/test_generic_worker_commands.py`, and manifest schema tests proving dispatch by provider, backward-compatible Bhoonidhi aliases, secret redaction, and fail-closed unknown-source behavior. | | |

### Implementation Phase 3 — Generic optical composite and BFF date serving (blocking for Sentinel/Landsat)

- GOAL-003: Generalize composite creation and date-level serving so every composite-capable optical source resolves to one dated STAC item for tiles/statistics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Split ResourceSat-only composite constants in [composite.py](../../services/ingestion/akasha_ingest/composite.py) into reusable optical composite profiles keyed by `PipelineSource.output_profile`. Profiles must declare resolution, band order, band role mapping, mask keep/exclude classes, mask method, and output asset names. | | |
| TASK-018 | Add Sentinel-2 and Landsat optical composite profiles but keep them gated until provider clients and prepare scripts are validated. | | |
| TASK-019 | Generalize composite manifest writing so all optical composites include `akasha:composite=true`, `akasha:aoi_id`, `akasha:period_start`, `akasha:period_end`, `akasha:contributing_scenes`, `akasha:coverage_percent`, `akasha:usable_pixel_percent`, `akasha:cloud_masked_percent`, `akasha:mask_method`, and source-specific `akasha:band_role_mapping`. | | |
| TASK-020 | Update [catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) so `_servable_items_for_date()` prefers composite items for any source whose BFF registry marks composite serving enabled, not only `RESOURCESAT_BOA_SOURCE_IDS`. | | |
| TASK-021 | Add BFF tests proving `/api/sources/{id}/dates`, tile routes, and `/api/indices/statistics` resolve the dated composite item for Sentinel-2/Landsat-style sources and still preserve ResourceSat behavior. | | |
| TASK-022 | Add multi-scene non-composite tests proving optical tile/statistics routes continue to return explicit `MOSAIC_TILES_UNAVAILABLE` until a valid composite exists. | | |

### Implementation Phase 4 — Sentinel-2 L2A via CDSE

- GOAL-004: Onboard Sentinel-2 as the first non-ISRO optical source for operator validation, while keeping it non-production-selectable by default.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | New client `services/ingestion/akasha_ingest/cdse.py` using current CDSE OData/STAC endpoints. Search must use bounded date windows, current STAC endpoint `https://stac.dataspace.copernicus.eu/v1/`, and/or OData endpoint `https://catalogue.dataspace.copernicus.eu/odata/v1/`; do not use deprecated OpenSearch or legacy STAC endpoints. | | |
| TASK-024 | Implement CDSE token handling with `CDSE_USERNAME`, `CDSE_PASSWORD`, optional `CDSE_ACCESS_TOKEN`, optional refresh-token cache, and `CDSE_CLIENT_ID=cdse-public` by default. Do not require `CDSE_CLIENT_SECRET` unless a verified client-credentials grant is configured. | | |
| TASK-025 | Implement CDSE download support for OData `$value`/`$zip` and/or CDSE S3 using generated `CDSE_S3_ACCESS_KEY`/`CDSE_S3_SECRET_KEY`. Redact tokens and S3 keys in all logs/manifests. | | |
| TASK-026 | Set `provider="cdse"` and `supports_search=True`, `supports_download=True`, `supports_composite=True`, `mvp_enabled=False` for `sentinel-2-l2a` in [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) until staging validation passes. | | |
| TASK-027 | Verify [prepare_sentinel2_l2a_cogs.py](../../scripts/prepare_sentinel2_l2a_cogs.py) emits the 9-band `[B04,B08,B05,B06,B07,B11,B12,B03,B02]` analytic + `scl` mask + manifest with scale `0.0001`, offset `-0.1`, and excluded SCL classes `[0,1,2,3,7,8,9,10,11]`. | | |
| TASK-028 | Confirm BFF row in [catalog_resolver.py](../../apps/api/app/raster/catalog_resolver.py) remains non-selectable by default unless `AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES=true` or a new explicit rollout flag is enabled. | | |
| TASK-029 | Add env placeholders to `services/ingestion/.env.example`, `infra/docker/.env.example`, and `infra/selfhosted/env.example`: `CDSE_USERNAME`, `CDSE_PASSWORD`, `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID=cdse-public`, `CDSE_S3_ACCESS_KEY`, `CDSE_S3_SECRET_KEY`, `CDSE_RAW_ROOT`, `CDSE_WORK_ROOT`. | | |
| TASK-030 | Add unit tests for CDSE search pagination/date-window splitting, token refresh, OData/S3 download URL redaction, S2 prep manifest metadata, and composite verification. | | |
| TASK-031 | Staging gate: dry-run search → capped real download (`--max-downloads 1`) → prepare → composite → ingest → `worker.py verify-composite --source sentinel-2-l2a --aoi bangalore-60km`. | | |

### Implementation Phase 5 — Landsat 8 & 9 via cloud STAC+COG

- GOAL-005: Onboard Landsat 8/9 surface reflectance using cloud-native COG assets and a precise QA_PIXEL mask contract.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | New client `services/ingestion/akasha_ingest/usgs.py` using a cloud STAC provider selected by config (`USGS_STAC_PROVIDER=planetary-computer|earth-search|usgs`). Filter shared `landsat-c2-l2` results by `platform in [landsat-8, landsat-9]` for these sources. | | |
| TASK-033 | Add optional signing/auth support for the selected cloud catalog if required. Env placeholders: `USGS_M2M_USERNAME`, `USGS_M2M_TOKEN`, `EARTHDATA_TOKEN`, `USGS_STAC_PROVIDER`, `USGS_RAW_ROOT`, `USGS_WORK_ROOT`. | | |
| TASK-034 | New `scripts/prepare_landsat_c2_l2_cogs.py` — clip C2 L2 SR COGs to AOI, restack `[green,red,nir08,swir16]`, preserve scale `0.0000275`, offset `-0.2`, nodata `0`, and derive Akasha categorical mask from `qa_pixel`. | | |
| TASK-035 | Define exact Landsat QA mask mapping in the prepare script and tests: fill/nodata → `0`, clear valid → `1`, cloud/dilated cloud/cirrus where selected → `2`, cloud shadow → `3`, water → `4`, snow/ice either excluded as a new documented class or mapped to masked cloud-like class with explicit rationale. | | |
| TASK-036 | Add `landsat-8-c2-l2` and `landsat-9-c2-l2` rows in [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) with `provider="usgs"`, `supports_composite=True`, `mvp_enabled=False` until validation. | | |
| TASK-037 | Add Landsat scene-id parsing in [scene.py](../../services/ingestion/akasha_ingest/scene.py) for `LC08_L2SP_*` and `LC09_L2SP_*`, including path/row, acquisition datetime, processing level, and product hash. | | |
| TASK-038 | Add `data/seed/stac/landsat-8-c2-l2-collection.json` and `data/seed/stac/landsat-9-c2-l2-collection.json` with STAC item-assets matching the prepared analytic/mask assets. | | |
| TASK-039 | Add BFF `_SOURCE_REGISTRY` rows for Landsat 8/9 (RGB display, NDVI/MSAVI/NDMI/NDWI_GREEN_NIR, no NDRE, source-specific attribution, mask method, `analysisLevel="field"`). | | |
| TASK-040 | Add tests + staging dry-run → capped run → prepare → composite → ingest → `verify-composite` for `landsat-8-c2-l2` and `landsat-9-c2-l2`. | | |

### Implementation Phase 6 — Sentinel-1 GRD via CDSE SAR path

- GOAL-006: Add the first non-ISRO SAR source using the CDSE client and the existing separate SAR preprocessing image.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-041 | Reuse `cdse.py` for `sentinel-1-grd`; set `provider="cdse"`, `supports_search=True`, `supports_download=True`, `supports_composite=False`, and `mvp_enabled=False` in [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py). | | |
| TASK-042 | Verify the selected Sentinel-1 product has an accessible SAFE ZIP or equivalent native source before preprocessing. If no native product is accessible, fail before SNAP with a sanitized manifest warning. | | |
| TASK-043 | Run [prepare_sentinel1_grd_cogs.py](../../scripts/prepare_sentinel1_grd_cogs.py) only inside the existing `ingestion-sar` runtime (`services/ingestion-sar/Dockerfile`, `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml`). Do not add SNAP GPT to `services/ingestion/Dockerfile`. | | |
| TASK-044 | Confirm SAR BFF row uses grayscale display, no optical indices, `maskAsset=None`, `supportedIndices=[]`, and date metrics kind `radar`. | | |
| TASK-045 | Add tests + staging dry-run → capped run → SAR prep → ingest → `worker.py verify-raster-product --source sentinel-1-grd --manifest ...`. Do not call `verify-composite` for Sentinel-1. | | |

### Implementation Phase 7 — ISRO gated sources (EOS-04 SAR, EOS-06 context, NISAR)

- GOAL-007: Use the existing Bhoonidhi client for already-scaffolded non-ResourceSat ISRO sources, with source-appropriate verification.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-046 | Add or confirm `eos-06-ocm-lac-ndvi-8day-360m` in [pipeline_registry.py](../../services/ingestion/akasha_ingest/pipeline_registry.py) with `provider="bhoonidhi"`, `supports_search=True`, `supports_download=True`, `supports_composite=False`, `mvp_enabled=False`, and context output profile. | | |
| TASK-047 | Sample a real EOS-04 product (`gdalinfo`); confirm polarization order/scale in [prepare_eos04_sar_mrs_l2b_cogs.py](../../scripts/prepare_eos04_sar_mrs_l2b_cogs.py). | | |
| TASK-048 | Flip `supports_search/download` for `eos-04-sar-mrs-l2b` only after validation; keep `supports_composite=False`. Verify with `worker.py verify-raster-product`, not `verify-composite`. | | |
| TASK-049 | EOS-06: decide whether `prepare-context-cog` is sufficient for Bhoonidhi-downloaded NDVI products or whether a dedicated `scripts/prepare_eos06_ocm_lac_ndvi_cogs.py` is required. Keep `analysisLevel="regional"` and no field-level statistics. | | |
| TASK-050 | NISAR: keep `nisar-ssar-beta-gcov` data-gated; add a readiness check and revalidate [prepare_nisar_ssar_beta_gcov_cogs.py](../../scripts/prepare_nisar_ssar_beta_gcov_cogs.py) when calibrated ARD ships (~Jul 2026). | | |
| TASK-051 | Add staging gates for EOS-04/EOS-06/NISAR-Bhoonidhi: dry-run → capped run → source-specific prep/context prep → ingest → `verify-raster-product`. | | |

### Implementation Phase 8 — MODIS regional context via NASA Earthdata

- GOAL-008: Add coarse 250 m NDVI/EVI regional context, not field-level analytics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-052 | New client `services/ingestion/akasha_ingest/earthdata.py` — Earthdata Login token + CMR/STAC search + granule download. If NISAR ASF is implemented separately, add `services/ingestion/akasha_ingest/asf.py` or an ASF mode in `earthdata.py`. | | |
| TASK-053 | New `scripts/prepare_modis_13q1_cogs.py` — fetch/convert MOD13Q1/MYD13Q1 NDVI/EVI (scale `0.0001`) to COG, clip AOI, and carry `pixel_reliability`/`VI_Quality` metadata. | | |
| TASK-054 | Add `modis-13q1-061` row (`provider="earthdata"`, `supports_composite=False`) + STAC seed + BFF context row (`analysisLevel="regional"`, context display). | | |
| TASK-055 | Add `EARTHDATA_TOKEN`, `EARTHDATA_RAW_ROOT`, and `EARTHDATA_WORK_ROOT` to env templates; add tests; staging dry-run → capped run → context ingest → `verify-raster-product`. | | |

### Implementation Phase 9 — Free archives (Landsat 7/5, IRS-1C)

- GOAL-009: Onboard historical baselines using existing clients and source-specific archive caveats.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-056 | Add `landsat-7-c2-l2` and `landsat-5-c2-l2` rows (reuse `usgs.py` + `prepare_landsat_c2_l2_cogs.py`; TM/ETM+ band set, no coastal). | | |
| TASK-057 | Encode Landsat 7 SLC-off (post-2003-05-31) caveat in registry `limitations`; mark Landsat 7/5 `availabilityStatus="archive"` and not default-selectable. | | |
| TASK-058 | Flip `irs-1c-liss3-archive` on via Bhoonidhi only after prep and metadata validation; confirm [irs-1c-liss3-archive-collection.json](../../data/seed/stac/irs-1c-liss3-archive-collection.json) + archive verification profile. | | |
| TASK-059 | Tests + staging dry-run → capped run → source-specific prep → ingest → `verify-raster-product` for Landsat 7/5 and IRS-1C. | | |

### Implementation Phase 10 — Commercial sources (gated; no paid action without contract)

- GOAL-010: Document and scaffold commercial adapters safely, with explicit cost/quota controls before any order can be placed.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-060 | Before `planet.py`, create `docs/reference/commercial-provider-readiness-checklist.md` covering contract/product bundle, allowed item types/assets, quota, pricing preview, order-state model, delivery target, cancellation policy, and sign-off owner. | | |
| TASK-061 | New `services/ingestion/akasha_ingest/planet.py` may search Planet Data API, but any Orders/Subscriptions/Tasking call that can consume quota or incur cost must require an explicit operator flag such as `--allow-paid-order` and a signed readiness record. | | |
| TASK-062 | Planet rows `planetscope` and `skysat` stay `mvp_enabled=False`, `userSelectable=False`, and `availabilityStatus="commercial-gated"` until contract and validation sign-off. | | |
| TASK-063 | New `services/ingestion/akasha_ingest/jaxa.py`; rows `alos2-palsar2` (commercial scenes, gated) and/or `alos2-mosaic-25m` (free annual mosaic, SAR/context). | | |
| TASK-064 | Per-vendor adapters for SuperView NEO-1 (SIIS), BlackSky Gen 3 (Spectra), KOMPSAT-3A (KARI/SIIS); all rows gated, with no paid order code path enabled without sign-off. | | |
| TASK-065 | Cartosat-3: document NSIL/GE access; keep [cartosat-3-gated-collection.json](../../data/seed/stac/cartosat-3-gated-collection.json) as a manual-context placeholder (no API path). | | |

### Implementation Phase 11 — NAIP (documentation only, out of scope)

- GOAL-011: Keep NAIP as a methodology/reference source only.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-066 | Document NAIP (US-only) in the matrix as reference/methodology only; add no pipeline registry row, BFF row, or AOI-selectable source. | | |

## 3. Alternatives

- **ALT-001**: Per-provider worker subcommands (`cdse-sync`, `usgs-sync`) instead of a generic factory. Rejected — duplicates orchestration and re-creates the Bhoonidhi hardcoding for every provider.
- **ALT-002**: Download Landsat via the USGS M2M ESPA order API instead of cloud COG. Rejected for the default path — cloud C2 L2 is already COG and needs no order/transform; M2M kept as an optional auth fallback.
- **ALT-003**: Use Sentinel Hub / openEO processing APIs to compute indices server-side instead of local COG prep. Rejected — breaks the "statistics computed in the BFF from masked COGs" contract and the single-COG serving model.
- **ALT-004**: Add SNAP GPT directly to the existing ingestion-worker image. Rejected — the repo already has a separate `ingestion-sar` image/service, which avoids bloating ResourceSat/Sentinel-2/Landsat ingestion.
- **ALT-005**: Onboard commercial VHR (Planet/BlackSky) before free sources for resolution. Rejected — contractually blocked and high cost; free Sentinel/Landsat deliver the AOI first.
- **ALT-006**: Treat NISAR as immediately buildable. Rejected — calibrated ARD is not globally available until ~Jul 2026; kept data-gated.
- **ALT-007**: Implement provider clients before registry/verification cleanup. Rejected — current verification and serving code still contains ResourceSat-specific assumptions that would cause rework.

## 4. Dependencies

- **DEP-001**: Phases 1–3 block Phases 4–10. Do not implement provider-specific onboarding before source-state consistency, generic orchestration, source-aware verification, and generic composite/date serving are complete.
- **DEP-002**: CDSE credentials for Sentinel-1/2: `CDSE_USERNAME`, `CDSE_PASSWORD`, optional `CDSE_ACCESS_TOKEN`, `CDSE_CLIENT_ID=cdse-public`, and optional CDSE S3 credentials (`CDSE_S3_ACCESS_KEY`, `CDSE_S3_SECRET_KEY`).
- **DEP-003**: Existing `ingestion-sar` image/service with ESA SNAP GPT for Sentinel-1 GRD terrain correction.
- **DEP-004**: NASA Earthdata Login token (`EARTHDATA_TOKEN`) for MODIS and the NISAR ASF path.
- **DEP-005**: Commercial credentials/contracts — `PLANET_API_KEY`, Planet product bundle/order permissions, JAXA/RESTEC, SIIS/BlackSky/KARI, NRSC/NSIL (Cartosat-3) — before enabling any Phase 10 source.
- **DEP-006**: Bhoonidhi staging VM (egress `20.219.3.35`) for all ISRO search/download (ResourceSat, EOS-04/06, NISAR-Bhoonidhi, IRS-1C).
- **DEP-007**: Pinned geospatial stack (GDAL/rasterio/rio-tiler/TiTiler) unchanged; rasterio HDF driver or cloud COG path for MODIS.
- **DEP-008**: NISAR calibrated ARD availability (~Jul 2026) for NISAR enablement.
- **DEP-009**: Provider rate limits and pagination constraints: CDSE bounded time windows, Bhoonidhi auth/search/download limits, Planet order/subscription rate and quota limits.

## 5. Files

- **FILE-001**: `docs/impl-plan/data-multi-source-ingestion-roadmap-1.md` — This implementation roadmap.
- **FILE-002**: `docs/reference/satellite-ingestion-onboarding-matrix.md` — Provider/source feasibility matrix and code touchpoint checklist.
- **FILE-003**: `services/ingestion/worker.py` — Generic provider dispatch, source-aware commands, and backward-compatible Bhoonidhi aliases.
- **FILE-004**: `services/ingestion/akasha_ingest/providers/__init__.py` — `ProviderClient` protocol.
- **FILE-005**: `services/ingestion/akasha_ingest/providers/factory.py` — Provider factory.
- **FILE-006**: `services/ingestion/akasha_ingest/manifests.py` — Canonical normalized search/download manifest schemas and redaction helpers.
- **FILE-007**: `services/ingestion/akasha_ingest/validation_profiles.py` — Source-aware raster/STAC verification profiles.
- **FILE-008**: `services/ingestion/akasha_ingest/pipeline_registry.py` — Pipeline source rows and source-state metadata.
- **FILE-009**: `services/ingestion/akasha_ingest/sync.py` — Generic ledger and fail-closed prepare script dispatch.
- **FILE-010**: `services/ingestion/akasha_ingest/storage.py` — Source-aware COG upload and verification.
- **FILE-011**: `services/ingestion/akasha_ingest/composite.py` — Generic optical composite profiles and ResourceSat compatibility.
- **FILE-012**: `services/ingestion/akasha_ingest/catalog.py` — STAC item generation for new sources.
- **FILE-013**: `services/ingestion/akasha_ingest/scene.py` — Scene identity parsing for new source families.
- **FILE-014**: `apps/api/app/raster/catalog_resolver.py` — BFF source registry, date serving, composite item preference, source status payloads.
- **FILE-015**: `apps/api/app/raster/indices.py` — Central index role/formula registry.
- **FILE-016**: `scripts/prepare_sentinel2_l2a_cogs.py` — Sentinel-2 prep validation and manifest contract.
- **FILE-017**: `scripts/prepare_sentinel1_grd_cogs.py` — Sentinel-1 SAR prep in `ingestion-sar` runtime.
- **FILE-018**: `scripts/prepare_landsat_c2_l2_cogs.py` — New Landsat C2 L2 prep script.
- **FILE-019**: `scripts/prepare_modis_13q1_cogs.py` — New MODIS context prep script.
- **FILE-020**: `data/seed/stac/*-collection.json` — STAC collection seeds for onboarded sources.
- **FILE-021**: `services/ingestion/.env.example`, `infra/docker/.env.example`, `infra/selfhosted/env.example` — Provider env placeholders and non-secret runtime knobs.
- **FILE-022**: `services/ingestion-sar/Dockerfile`, `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml` — Existing SAR runtime that must be used for Sentinel-1 SNAP preprocessing.

## 6. Testing

- **TEST-001**: `tests/test_source_registry_consistency.py` validates source IDs, collection IDs, provider names, gating state, asset names, and user-selectability consistency across registries and STAC seeds.
- **TEST-002**: `tests/test_provider_factory.py` validates provider dispatch, unknown-provider failure, and Bhoonidhi compatibility.
- **TEST-003**: `tests/test_generic_worker_commands.py` validates generic `search`, `download`, `prepare`, `ingest`, and verification command routing.
- **TEST-004**: Manifest schema tests validate normalized search/download manifests and secret redaction.
- **TEST-005**: Validation profile tests verify source-specific band counts, dtypes, scales, offsets, mask classes, and expected assets, including LISS-4 3-band support.
- **TEST-006**: Composite profile tests verify ResourceSat behavior remains unchanged and Sentinel-2/Landsat profiles write source-correct composite manifests.
- **TEST-007**: BFF tests verify composite item preference for any composite-enabled source and explicit `MOSAIC_TILES_UNAVAILABLE` for multi-scene non-composite dates.
- **TEST-008**: CDSE tests verify bounded date-window search, supported endpoints only, token refresh, OData/S3 download behavior, and redaction.
- **TEST-009**: Sentinel-2 prep tests verify 9-band order, SCL mask, scale/offset, STAC metadata, supported indices, and non-selectable default behavior.
- **TEST-010**: Landsat tests verify platform filtering, C2 L2 asset selection, QA_PIXEL mask mapping, scale/offset, STAC metadata, and unsupported NDRE.
- **TEST-011**: Sentinel-1/EOS-04/NISAR SAR tests verify no optical indices, grayscale display, backscatter asset metadata, and `verify-raster-product` instead of `verify-composite`.
- **TEST-012**: MODIS/EOS-06 context tests verify regional/context classification, no field-level statistics, and correct context tile metadata.
- **TEST-013**: Commercial source tests verify no paid order can run without explicit operator flag and readiness/sign-off metadata.
- **TEST-014**: Run existing repo tests relevant to changed areas: `python -m pytest tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py services/ingestion/tests/test_manifest_ingestion.py -q` plus BFF tests under `apps/api/tests` for source/date/tile/statistics behavior.

## 7. Risks & Assumptions

- **RISK-001**: Implementing provider clients before Phases 1–3 will compound ResourceSat-specific assumptions and create rework in verification, date serving, and composite logic.
- **RISK-002**: Provider APIs can change endpoint behavior, pagination limits, auth flows, or rate limits. CDSE release notes already deprecate older endpoints and impose pagination constraints.
- **RISK-003**: Local `.env` files may contain real credentials. They are ignored by git, but copied logs/prompts/screenshots can still leak secrets.
- **RISK-004**: Landsat cloud COG access may require signing depending on the selected catalog host.
- **RISK-005**: SAR preprocessing is compute-heavy and may fail due to SNAP memory/cache/disk limits; keep it isolated in `ingestion-sar`.
- **RISK-006**: Commercial provider APIs can incur cost through orders/tasking/subscriptions. Paid actions must be impossible without explicit operator confirmation and contract sign-off.
- **RISK-007**: Multi-scene optical sources will not serve correct date-level tiles/statistics unless composites are created and the BFF resolves them.
- **ASSUMPTION-001**: ResourceSat production path remains the user-facing default while new sources are validated.
- **ASSUMPTION-002**: The frontend can consume new standard source rows from `/api/sources` without code changes when source metadata is complete.
- **ASSUMPTION-003**: The Bangalore 60 km AOI remains the first validation AOI for all field/regional sources unless a source-specific AOI is explicitly selected.
- **ASSUMPTION-004**: Free/open sources are prioritized over commercial sources until licensing and quota are confirmed.

## 8. Related Specifications / Further Reading

- [Satellite Ingestion Onboarding Matrix](../reference/satellite-ingestion-onboarding-matrix.md)
- [Data Ingestion and Satellite Rules](../data-ingestion-and-satellite-rules.md)
- [Engineering Do's and Don'ts](../engineering-dos-donts.md)
- [Architecture and Tech Stack](../architecture-tech-stack.md)
- [Staging Ingestion Developer Guide](../staging-ingestion-developer-guide.md)
- [Sentinel-1 GRD COG Prep Runbook](../sentinel-1-grd-cog-prep-runbook.md)
- [EOS-04 SAR MRS L2B COG Prep Runbook](../eos04-sar-mrs-l2b-cog-prep-runbook.md)
- [NISAR SSAR Beta GCOV COG Prep Runbook](../nisar-ssar-beta-gcov-cog-prep-runbook.md)
- Copernicus Data Space Ecosystem APIs: https://documentation.dataspace.copernicus.eu/APIs.html
- Copernicus STAC endpoint: https://stac.dataspace.copernicus.eu/v1/
- Copernicus OData endpoint: https://catalogue.dataspace.copernicus.eu/odata/v1/
- Copernicus API release notes: https://documentation.dataspace.copernicus.eu/APIs/Others/ReleaseNotes.html
- Landsat Collection 2 L2 STAC metadata: https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2
- MODIS MOD13Q1 v061 STAC metadata: https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13Q1-061
- Planet APIs: https://docs.planet.com/develop/apis/
