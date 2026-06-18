# LISS-4 5m Staging Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the staging LISS-4 ingestion blocker by accepting real 5.0 m Bhoonidhi LISS-4 native scenes while keeping the operational 5.8 m AOI composite grid, then rerun staging sync through prepare/composite/ingest.

**Architecture:** LISS-4 remains a separate ResourceSat source layered on top of LISS-3 through the existing best-resolution resolver. The fix splits native-scene validation from composite analytics metadata: prepare validation accepts the staging-confirmed 5.0 m downloaded products, while composite generation, STAC collection metadata, BFF source payloads, and frontend provenance continue to use the 5.8 m operational grid that fits staging memory. Operational validation reruns the Jan 30 staging sync that already downloaded two LISS-4 products.

**Tech Stack:** Python 3.11, pytest, FastAPI/Pydantic, STAC JSON, React 18/Vite/Vitest, Docker Compose on Coolify staging, systemd artifacts.

---

### Task 1: Split native-scene and composite-grid resolution metadata

**Files:**
- Modify: `scripts/prepare_resourcesat_liss3_boa_cogs.py`
- Modify: `services/ingestion/akasha_ingest/catalog.py`
- Modify: `apps/api/app/raster/catalog_resolver.py`
- Modify: `data/seed/stac/resourcesat-2a-liss4-mx70-l2-collection.json`
- Modify: `data/seed/stac/resourcesat-2a-liss4-mx70-l2-sample-item.json`

- [ ] **Step 1: Update prepare profile**

Set `SOURCE_PROFILES[LISS4_SOURCE_ID]["resolution_meters"]` to `5.0`.

- [ ] **Step 2: Update catalog metadata**

Keep `RESOURCESAT_BOA_SOURCE_META[config.RESOURCESAT_LISS4_COLLECTION_ID]["default_gsd"]` at `5.8` for composite defaults. Scene STAC items still inherit `5.0` from prepare manifests.

- [ ] **Step 3: Update BFF source metadata**

Keep the LISS-4 registry `resolutionMeters` at `5.8` because the BFF reads composite assets.

- [ ] **Step 4: Update STAC seed JSON**

Keep LISS-4 collection/sample composite `gsd`, `akasha:composite_resolution_meters`, analytic `raster:bands[].spatial_resolution`, and mask `raster:bands[].spatial_resolution` at `5.8`.

### Task 2: Update tests and docs

**Files:**
- Modify: `tests/test_prepare_resourcesat_liss3_boa_cogs.py`
- Modify: `tests/test_resourcesat_composite.py`
- Modify: `tests/test_bhoonidhi_ingestion.py`
- Modify: `apps/api/tests/test_slice2.py`
- Modify: `apps/api/tests/test_best_resolution_resolver.py`
- Modify: `apps/frontend/src/components/scaffold/IndexPanel.test.tsx`
- Modify: `apps/frontend/src/components/map/Legend.test.tsx`
- Modify: `apps/frontend/src/components/map/Legend.tsx`
- Modify: `docs/impl-plan/feature-resourcesat-liss4-best-resolution-1.md`
- Modify: `docs/reference/satellite-catalog.md`

- [ ] **Step 1: Update Python expectations**

Change LISS-4 prepare/native scene assertions to `5.0`; keep composite, catalog seed, resolver, and UI assertions at `5.8`.

- [ ] **Step 2: Update frontend expectations**

Keep enhanced badge and legend tests at `5.8 m`, preserving dynamic rendering from `resolutionMeters`.

- [ ] **Step 3: Update docs**

Document `5.0 m native scenes / 5.8 m operational composites` so the two resolutions are not conflated.

### Task 3: Validate locally

**Files:**
- No additional edits.

- [ ] **Step 1: Run ingestion-focused tests**

Run from repository root:

```powershell
python -m pytest tests\test_prepare_resourcesat_liss3_boa_cogs.py tests\test_resourcesat_composite.py tests\test_bhoonidhi_ingestion.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run BFF source/resolver tests**

Run:

```powershell
Set-Location apps\api
python -m pytest tests\test_slice2.py::test_sources_endpoint_contract tests\test_slice2.py::test_liss4_seed_collection_and_sample_item_contracts_are_loadable tests\test_best_resolution_resolver.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run frontend provenance tests**

Run:

```powershell
Set-Location apps\frontend
corepack yarn test src\components\scaffold\IndexPanel.test.tsx src\components\map\Legend.test.tsx --run
```

Expected: all selected tests pass.

### Task 4: Validate on staging

**Files:**
- No repository edits; commands run on `akasha-staging`.

- [ ] **Step 1: Deploy the code changes to staging**

Ensure the updated image or checked-out code on `akasha-staging` includes the 5.0 m prepare profile, the 5.8 m composite profile, and the LISS-4 10% coverage threshold before rerunning sync.

- [ ] **Step 2: Rerun Jan 30 LISS-4 sync**

Run on the VM through the Coolify compose file:

```bash
sudo bash -lc 'cd /data/coolify/services/s6f7s03fv8dhnxx8ld6a8nuh && docker compose -f docker-compose.yml run --rm --pull never ingestion-worker python worker.py bhoonidhi-sync --source resourcesat-2a-liss4-mx70-l2 --aoi bangalore-60km --datetime 2026-01-30T00:00:00Z/2026-01-30T23:59:59Z --lookback-days 365 --limit 20 --window-start 2026-01-30 --window-end 2026-01-30 --window-days 1 --raw-root /srv/akasha/data/raw/bhoonidhi --out-dir /srv/akasha/data/work/bhoonidhi --ledger-path /srv/akasha/ingestion/ledger.sqlite --lock-path /srv/akasha/ingestion/bhoonidhi-liss4-sync.bangalore-60km.worker.lock --max-downloads 2 --min-coverage-percent 10'
```

Expected: prepare validation no longer fails on `5.0` native scene resolution; the partial-AOI LISS-4 composite builds at `5.8` m, passes the field-enhancement coverage threshold, and proceeds to ingest.

- [ ] **Step 3: Verify API date availability**

Check:

```bash
curl -fsS http://127.0.0.1:8080/api/sources/resourcesat-2a-liss4-mx70-l2/dates | head
```

Expected: the response includes a LISS-4 composite date once ingest completes.

### Task 5: Install automatic LISS-4 sync units on staging

**Files:**
- Modify only VM system paths via installer: `/opt/akasha/bin`, `/etc/systemd/system`, `/etc/akasha`.

- [ ] **Step 1: Install units**

Run the LISS-4 systemd installer from the deployed repository once available on staging:

```bash
sudo ./infra/selfhosted/systemd/install-akasha-bhoonidhi-liss4-sync.sh --start
```

Expected: `akasha-bhoonidhi-liss4-sync.timer` exists and is enabled.

- [ ] **Step 2: Verify timer**

Run:

```bash
systemctl list-timers akasha-bhoonidhi-liss4-sync.timer --no-pager
```

Expected: next scheduled run is shown for the LISS-4 timer.
