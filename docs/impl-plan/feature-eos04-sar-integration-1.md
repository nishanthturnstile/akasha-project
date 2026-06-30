## Refactor Plan: EOS-04 SAR-MRS L2B Display-Only Integration

### Current State
Akasha's production raster path is ResourceSat-2A BOA optical imagery. The ResourceSat path is intentionally source-specific: LISS-3 uses four BOA bands `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`, FCC display `NIR,RED,GREEN`, reflectance correction `dn * 0.0001 + 0.0`, Akasha threshold mask v1, separate analytic/mask COGs, and BFF-computed optical index statistics.

EOS-04 SAR-MRS L2B already has partial, gated hooks: a prepare script, SAR validation profile, seed STAC collection, BFF SAR source metadata, grayscale SAR tile route, frontend SAR guards, and tests. The integration is not yet production-ready because the operational path is not validated against a real product, EOS-04 remains gated in the product-facing BFF registry, pipeline execution is not safely enabled for manual validation, and the current display token/label (`VV_GRAYSCALE` -> `VV`) is misleading for EOS-04 products that may be HH/HV or RH/RV.

Two important semantics must stay separate:

1. STAC collection availability means "loadable/catalogued raster collection".
2. BFF/source-registry product availability means "selectable/exposed product source".

The existing seed collection may be loadable while the product source remains gated. Do not collapse those states without updating tests and documentation deliberately.

### Target State
EOS-04 SAR-MRS L2B is integrated using the same architectural pattern as ResourceSat: explicit source registry rows, deterministic prepare/ingest outputs, STAC-backed BFF metadata, same-origin tile routes, frontend source controls, tests, and documentation. It is not treated as an optical source.

Phase 1 target is display-only SAR backscatter:

- Backscatter COG asset only: `backscatter.tif`.
- No optical vegetation indices: no NDVI, MSAVI, NDMI, NDWI, NDRE, or RECI.
- No cloud/SCL/ResourceSat threshold mask controls.
- No field index statistics or field-clipped index overlays.
- Radar date metrics use null optical metrics (`usablePixelPercent`, `cloudMaskedPercent`) and optional coverage.
- One scene per date can render through same-origin grayscale tiles.
- Multiple same-date SAR scenes fail closed until a mosaic backend exists.
- Real-product validation is required before any upload/pgSTAC load used for activation.
- Product exposure remains gated until one real EOS-04 product passes Step 0 inspection, COG validation, STAC validation, BFF tile validation, and frontend smoke validation.

### Reviewer Decisions Applied
| Decision | Resolution |
|---|---|
| STAC `akasha:availability_status` vs BFF `availabilityStatus` | Preserve the two-layer meaning. Do not blindly align seed STAC collection availability with product gating. Document and test the distinction. |
| Manual validation vs `mvp_enabled` | Avoid circular activation. Add an explicit manual/staging allow path for EOS-04 validation before product activation, rather than relying on public MVP source lists. |
| `VV_GRAYSCALE` token | Keep the existing public token for Phase 1 to avoid high-churn contract breakage, but change user-facing labels to "Backscatter" and fail closed on missing EOS-04 polarization metadata. Treat a future token migration as a separate compatibility refactor. |
| SAR statistics rejection | Verify the existing unsupported-index rejection path first. Only improve the SAR-specific error message if it preserves the standard error shape and expected code behavior. |
| Ingest validation | Add a hard pre-upload validation gate in the wrapper or `ingest-manifest` flow for EOS-04; do not rely only on operator discipline. |
| Phase ordering | Move real sample inspection and prepare-script hardening before live prepare/upload/pgSTAC operations. |

### Affected Files
| File | Change Type | Dependencies |
|------|-------------|--------------|
| `scripts/prepare_eos04_sar_mrs_l2b_cogs.py` | Modify | Blocks safe ingestion; depends on real Step 0 product inspection |
| `tests/test_prepare_eos04_sar_mrs_l2b_cogs.py` | Modify | Verifies prepare hardening and polarization fail-closed behavior |
| `services/ingestion/akasha_ingest/validation_profiles.py` | Modify/verify | Blocks validation gate; must keep SAR profile free of optical statistics |
| `tests/test_validation_profiles.py` | Modify | Verifies SAR manifests, missing polarizations, no optical stats, and validation gate assumptions |
| `services/ingestion/akasha_ingest/pipeline_registry.py` | Modify | Blocks manual staging path; must not expose EOS-04 as default MVP source prematurely |
| `tests/test_pipeline_registry.py` | Modify | Verifies EOS-04 search/download/prepare/manual validation metadata and no composite support |
| `services/ingestion/worker.py` | Modify/verify | Blocks safe operational path; must run validation before upload/load for EOS-04 manifests |
| `services/ingestion/akasha_ingest/sync.py` and staging wrapper scripts | Modify/verify | Ensure manual EOS-04 jobs can run through the safe wrapper without ResourceSat composite flow |
| `tests/test_bhoonidhi_ingestion.py` | Modify | Verifies EOS-04 source mapping and wrapper/prepare dispatch behavior |
| `tests/test_staging_ingestion_job.py` | Modify | Verifies dry-run/manual execution is allowed only through bounded staging path |
| `services/ingestion/akasha_ingest/catalog.py` | Verify/modify | Ensures SAR STAC item preserves `sar:polarizations`, raster band names, and backscatter asset |
| `services/ingestion/akasha_ingest/storage.py` | Verify/modify | Ensures backscatter COG upload and metadata verification are correct |
| `services/ingestion/akasha_ingest/scene.py` | Verify/modify | Ensures deterministic SAR object keys are reused, not reinvented |
| `data/seed/stac/eos-04-sar-mrs-l2b-collection.json` | Modify/verify | Keep loadable STAC semantics; ensure no optical fields and clear product-gating note |
| `apps/api/app/raster/catalog_resolver.py` | Modify | Source payload/date metadata must stay SAR-specific and product-gated |
| `apps/api/app/routers/product_router.py` | Modify/verify | SAR display route, same-date multi-scene rejection, unsupported statistics messaging |
| `apps/api/app/raster/tiles.py` | Modify/verify | Generic helper naming may be added while preserving existing `VV_GRAYSCALE` URL compatibility |
| `apps/api/tests/test_product_sources.py` | Modify | Verifies gated EOS-04 source, no indices, no mask options, SAR metadata |
| `apps/api/tests/test_slice2.py` | Modify/verify | Verifies seed STAC/BFF contracts without conflating collection and product availability |
| `apps/api/tests/test_best_observation_resolver.py` | Verify/modify | Ensures SAR is excluded from optical best-observation field analytics |
| `apps/frontend/src/lib/displayMode.ts` | Modify | User-facing SAR display label becomes "Backscatter" rather than "VV" |
| `apps/frontend/src/components/map/Legend.tsx` | Modify/verify | SAR ramp remains generic backscatter, not VV-specific |
| `apps/frontend/src/pages/MapPage.tsx` | Verify/modify | SAR disables analytics, cloud mask, export/index overlays, and marginal optical notices |
| `apps/frontend/src/components/layers/LayerControlBar.tsx` | Verify/modify | SAR mask/download controls stay disabled or explanatory |
| `apps/frontend/src/components/layers/SourceSelector.tsx` | Verify/modify | SAR source is clearly labelled radar without implying optical analytics |
| `apps/frontend/src/**/*.test.tsx`, `apps/frontend/src/**/*.test.ts` | Modify | Add SAR label/control/legend/timeline regression coverage |
| `docs/eos04-sar-mrs-l2b-cog-prep-runbook.md` | Modify | Add validation gate, activation criteria, and wrapper-only operational commands |
| `docs/platform-plan.md` | Modify | Add EOS-04 SAR phase status and display-only scope |
| `docs/data-ingestion-and-satellite-rules.md` | Modify | Add EOS-04 SAR guardrails and no-optical-index rule |
| `docs/engineering-dos-donts.md` | Modify | Add SAR do/don't checklist |
| `docs/satellite-ingestion-orchestration-and-scheduler.md` | Modify | Add manual EOS-04 validation path and scheduler state |
| `docs/reference/satellite-ingestion-scheduler-contracts.md` | Modify | Document EOS-04 state transitions and validation profile |
| `docs/reference/satellite-ingestion-onboarding-matrix.md` | Modify | Add/verify EOS-04 row |
| `docs/reference/satellite-catalog.md` | Modify/verify | Ensure `eos-04-risat` -> `eos-04-sar-mrs-l2b` mapping is accurate |
| `infra/selfhosted/README.md` | Modify only if needed | Document worker-pool/resource-limit changes if operationally changed |

### Execution Plan

#### Phase 1: Contract Lock and Real-Sample Gate
- [ ] Step 1.1: Record EOS-04 Phase 1 scope in `docs/data-ingestion-and-satellite-rules.md`: display-only SAR backscatter, no optical indices, no cloud masks, no SAR statistics yet, no SAR mosaic yet.
- [ ] Step 1.2: Document the two availability layers in `docs/eos04-sar-mrs-l2b-cog-prep-runbook.md` and `docs/reference/satellite-ingestion-scheduler-contracts.md`: STAC collection loadability is not the same as product exposure.
- [ ] Step 1.3: Add or tighten tests proving EOS-04 remains product-gated in `apps/api/tests/test_product_sources.py` while the seed STAC collection remains loadable in `apps/api/tests/test_slice2.py`.
- [ ] Step 1.4: Add regression tests proving EOS-04 is not in optical best-observation resolution and does not advertise any optical index/statistics roles.
- [ ] Verify: `cd apps/api && python -m pytest tests/test_product_sources.py tests/test_slice2.py tests/test_best_observation_resolver.py -q`; `python -m pytest tests/test_validation_profiles.py -q`.

#### Phase 2: Prepare Script Hardening Before Live Ingest
- [ ] Step 2.1: Perform Step 0 on one real EOS-04 SAR-MRS L2B product with `gdalinfo`: band count, polarization order, data units (`db`, `linear`, or `amplitude`), nodata, CRS/EPSG, geotransform, resolution, and file layout.
- [ ] Step 2.2: Update `scripts/prepare_eos04_sar_mrs_l2b_cogs.py` defaults and flags based on the real sample. Do not trust auto-detection if the sample shows ambiguous units.
- [ ] Step 2.3: Fail closed for EOS-04 when item-level polarization order cannot be inferred or provided. Do not default unknown EOS-04 bands to `VV`.
- [ ] Step 2.4: Ensure output `backscatter.tif` is Float32 dB with nodata, overviews, deterministic band descriptions, and no optical metadata.
- [ ] Step 2.5: Ensure `prepare_manifest.json` includes source id, scene identity, acquisition datetime/date, product type, `sar:polarizations`, backscatter path/summary, bbox/geometry, CRS, nodata, and band names.
- [ ] Step 2.6: Extend `tests/test_prepare_eos04_sar_mrs_l2b_cogs.py` for HH/HV, RH/RV, missing-polarization failure, explicit input-scale behavior, nodata, and manifest shape.
- [ ] Verify: `python -m pytest tests/test_prepare_eos04_sar_mrs_l2b_cogs.py -q`; run the prepare script against the inspected sample in local/container mode without upload.

#### Phase 3: Validation Gate Before Upload or pgSTAC Load
- [ ] Step 3.1: Update `services/ingestion/akasha_ingest/validation_profiles.py` so the `sar_backscatter` profile requires backscatter asset metadata and, for EOS-04, explicit SAR polarizations/band roles.
- [ ] Step 3.2: Update `tests/test_validation_profiles.py` to reject EOS-04 manifests missing `sar:polarizations`, advertising optical statistics, or missing `backscatter.tif`.
- [ ] Step 3.3: Add a hard pre-upload gate for EOS-04 in the safe wrapper or `worker.py ingest-manifest` path: `verify-raster-product --source eos-04-sar-mrs-l2b --manifest <path>` must pass before S3 upload and STAC load.
- [ ] Step 3.4: Ensure validation failures return actionable messages and do not upload partial objects or load STAC items.
- [ ] Step 3.5: Keep `worker.py verify-composite` and `bhoonidhi-sync` rejected for EOS-04; add explicit regression tests if absent.
- [ ] Verify: `python -m pytest tests/test_validation_profiles.py tests/test_bhoonidhi_ingestion.py -q`; dry-run a failing manifest and confirm no upload/load happens.

#### Phase 4: Manual Staging Execution Path Without Product Activation
- [ ] Step 4.1: Update `services/ingestion/akasha_ingest/pipeline_registry.py` so EOS-04 declares the real capabilities needed for manual validation (`search`, `download`, `prepare`, `validate`) while remaining non-composite and not part of default production/MVP source lists.
- [ ] Step 4.2: Add an explicit manual/staging allow path for `eos-04-sar-mrs-l2b` in `scripts/staging_ingestion_job.py` or the corresponding sync wrapper, avoiding circular dependency on final product activation.
- [ ] Step 4.3: Confirm `bhoonidhi-search` and `bhoonidhi-download` enforce source capability/support consistently rather than bypassing registry state.
- [ ] Step 4.4: Keep schedule state disabled/manual-only and product exposure hidden/gated until final activation.
- [ ] Step 4.5: Add tests for manual allow, unsupported direct composite/sync, and bounded dry-run behavior.
- [ ] Verify: `python -m pytest tests/test_pipeline_registry.py tests/test_staging_ingestion_job.py tests/test_bhoonidhi_ingestion.py -q`.

#### Phase 5: SAR STAC, Storage, and Object-Key Validation
- [ ] Step 5.1: Verify `services/ingestion/akasha_ingest/scene.py` already produces the canonical SAR object key for `backscatter.tif`; reuse it rather than introducing a parallel layout.
- [ ] Step 5.2: Verify `services/ingestion/akasha_ingest/storage.py` uploads and verifies SAR backscatter COGs with band count >= 1 and overviews.
- [ ] Step 5.3: Verify `services/ingestion/akasha_ingest/catalog.py` writes SAR STAC items with `sar:polarizations`, `sar:frequency_band`, raster bands, projection metadata, bbox/geometry, and `backscatter` asset href.
- [ ] Step 5.4: Update `data/seed/stac/eos-04-sar-mrs-l2b-collection.json` only for metadata correctness: no optical fields, clear SAR descriptions, correct item asset schema, and documented collection/product availability semantics.
- [ ] Step 5.5: Add/extend manifest-ingestion tests for EOS-04 backscatter asset metadata and no optical fields.
- [ ] Verify: `python -m pytest services/ingestion/tests/test_manifest_ingestion.py tests/test_canonical_manifests.py tests/test_validation_profiles.py -q`.

#### Phase 6: BFF SAR Source, Dates, Tiles, and Statistics Guard
- [ ] Step 6.1: Add explicit EOS-04 constants in `apps/api/app/raster/catalog_resolver.py` if absent, and keep source metadata SAR-specific: `kind="sar"`, `expectedAssets=["backscatter"]`, `supportedIndices=[]`, `maskAsset=None`, `dateMetricsKind="radar"`, `defaultRescale="-25,5"`, product `availabilityStatus="gated"` until activation.
- [ ] Step 6.2: Keep `VV_GRAYSCALE` as the compatible route token for Phase 1, but describe it in source metadata as generic backscatter display where possible. Do not expose "VV" as the user-facing EOS label.
- [ ] Step 6.3: Ensure `catalog_resolver.list_dates()` returns null optical metrics for radar dates and marks tiles unavailable for multiple same-date SAR scenes.
- [ ] Step 6.4: In `apps/api/app/routers/product_router.py`, verify the SAR route chooses VV when present but, for EOS-04, requires explicit band names/polarizations and otherwise fails instead of fabricating VV.
- [ ] Step 6.5: Verify `/api/indices/statistics` rejects EOS-04 through the standard unsupported-index/bad-request path; optionally improve the message without changing the standard error shape.
- [ ] Step 6.6: Add API tests for EOS-04 dates, tile route, same-date multi-scene rejection, no supported indices, no mask options, and SAR statistics rejection.
- [ ] Verify: `cd apps/api && python -m pytest tests/test_product_sources.py tests/test_slice2.py -q`; add targeted router tests if needed.

#### Phase 7: Frontend SAR UX
- [ ] Step 7.1: Update `apps/frontend/src/lib/displayMode.ts` so `VV_GRAYSCALE` renders as "Backscatter" or "Radar backscatter" for generic SAR UI instead of "VV".
- [ ] Step 7.2: Verify `apps/frontend/src/pages/MapPage.tsx` disables analytics, field overlays, field point lookup, marginal optical warnings, cloud mask controls, and analytics downloads for `source.kind === "sar"`.
- [ ] Step 7.3: Verify `LayerControlBar` and `DownloadMenu` communicate disabled SAR analytics clearly and do not send optical cloud-mask/index requests for EOS-04.
- [ ] Step 7.4: Verify `Legend` uses the SAR backscatter ramp for EOS-04 and does not imply vegetation or optical index values.
- [ ] Step 7.5: Add tests for EOS-04 source selection, label, legend, disabled cloud mask, disabled analytics/export, null optical metrics, and same-origin tile template.
- [ ] Verify: `cd apps/frontend && yarn test && yarn build`.

#### Phase 8: Documentation and Operational Runbooks
- [ ] Step 8.1: Update `docs/platform-plan.md` with EOS-04 SAR display-only phase status and explicit out-of-scope analytics.
- [ ] Step 8.2: Update `docs/data-ingestion-and-satellite-rules.md` with SAR guardrails: no optical indices, no cloud masks, no ResourceSat composite path, explicit polarizations, dB backscatter.
- [ ] Step 8.3: Update `docs/engineering-dos-donts.md` with "do not use ResourceSat BOA assumptions for SAR" and staging-wrapper-only ingestion rules.
- [ ] Step 8.4: Update scheduler/reference docs with EOS-04 state transitions: gated/manual validation -> validated display-only -> product active only after acceptance.
- [ ] Step 8.5: Update `docs/eos04-sar-mrs-l2b-cog-prep-runbook.md` with the hard validation-before-ingest gate, first-live-run limits, rollback, and activation checklist.
- [ ] Step 8.6: Update `infra/selfhosted/README.md` only if staging worker pool, resource limits, or wrapper commands change.
- [ ] Verify: Review docs for command accuracy, no secrets, and no direct unthrottled Docker ingestion commands.

#### Phase 9: Validation and Gated Activation
- [ ] Step 9.1: Run static/unit validation locally.
- [ ] Step 9.2: Run staging dry-run through the wrapper: `python scripts/staging_ingestion_job.py trigger --source eos-04-sar-mrs-l2b --dry-run`.
- [ ] Step 9.3: Run one bounded live staging job only after dry-run passes, with `--max-downloads 1` or equivalent wrapper limit.
- [ ] Step 9.4: Confirm `verify-raster-product` passes for the real prepared manifest before upload and pgSTAC load.
- [ ] Step 9.5: Confirm S3 contains the expected `backscatter.tif`, pgSTAC has a SAR item with explicit polarizations, `/api/sources/eos-04-sar-mrs-l2b/dates` returns the date, and the tile endpoint returns PNG for the selected tile.
- [ ] Step 9.6: Smoke-test the frontend: EOS-04 source renders grayscale backscatter, cloud/index controls are disabled/hidden, legend is SAR backscatter, no optical statistics calls are made.
- [ ] Step 9.7: Only after acceptance, make the activation diff: BFF `availabilityStatus` active, source registry product exposure/schedule/lifecycle advanced to the approved level, docs updated from gated to active display-only. Keep SAR analytics explicitly out of scope.
- [ ] Verify: Full validation command sequence below plus staging/API smoke checks.

### Validation Commands
Run from repo root unless noted.

```bash
ruff check apps/api services/ingestion scripts
cd apps/api && python -m pytest -q
python -m pytest tests/test_prepare_eos04_sar_mrs_l2b_cogs.py tests/test_validation_profiles.py tests/test_pipeline_registry.py tests/test_bhoonidhi_ingestion.py tests/test_staging_ingestion_job.py -q
python scripts/validate_slice0.py
python scripts/validate_slice1.py
python scripts/validate_slice2.py
cd apps/frontend && yarn test && yarn build
```

Staging validation must use the safe wrapper, not direct unthrottled container commands:

```bash
python scripts/staging_ingestion_job.py trigger --source eos-04-sar-mrs-l2b --dry-run
python scripts/staging_ingestion_job.py trigger --source eos-04-sar-mrs-l2b --max-downloads 1
python scripts/smoke-test.py http://localhost:8080
```

Manual endpoint checks after a real validated product is ingested:

```bash
curl -fsS http://localhost:8080/api/sources
curl -fsS http://localhost:8080/api/sources/eos-04-sar-mrs-l2b/dates
curl -fsS -o /tmp/eos04.png http://localhost:8080/api/tiles/eos-04-sar-mrs-l2b/<date>/VV_GRAYSCALE/<z>/<x>/<y>.png
```

### Rollback Plan
If something fails:

1. Revert only the latest phase's code/doc changes. Keep ResourceSat source IDs, masks, statistics, and display contracts untouched.
2. If activation was flipped, restore EOS-04 product state to gated/hidden/disabled/manual-only in the BFF registry and scheduler source registry.
3. If a bad EOS-04 COG was uploaded, delete only the EOS-04 S3 object/prefix for the affected scene and re-run ingest with `--force` after fixing the manifest.
4. If a bad STAC item was loaded, delete only the affected EOS-04 pgSTAC item, then re-run the validated manifest load.
5. If a staging job stalls, inspect wrapper state and process IDs first; clear only the EOS-04 source-specific lock after confirming no ingestion process is running.
6. Never recover by running direct unthrottled `docker run ... worker.py ...` or direct `docker compose run ... ingestion-worker ...` on staging.

### Risks
- EOS-04 product format may not match assumptions about band count, polarization naming, units, nodata, or georeferencing. Mitigation: Step 0 inspection and fail-closed prepare/validation before live ingest.
- `VV_GRAYSCALE` is semantically misleading for HH/HV EOS-04. Mitigation: preserve route compatibility for Phase 1 but fix user-facing labels to "Backscatter"; require explicit polarization metadata; defer token migration to a separate compatibility refactor.
- Manual validation could accidentally become product exposure. Mitigation: separate manual staging allow path from product-active BFF/source-registry flags.
- Upload/load could bypass validation. Mitigation: hard validation-before-ingest gate for EOS-04 manifests.
- Same-date SAR scenes need mosaicking. Mitigation: fail closed with clear `mosaic_tiles_unavailable` behavior until a SAR mosaic backend is designed.
- SAR statistics are tempting but out of scope. Mitigation: keep `allowed_statistics_roles` empty and reject optical index requests for SAR.
- STAC and product availability semantics can be confused. Mitigation: document and test collection loadability separately from BFF product exposure.

### Implementation Pause
This plan is ready for Phase 1 implementation after approval. Per the refactor workflow, implementation should not begin until the plan is confirmed.
