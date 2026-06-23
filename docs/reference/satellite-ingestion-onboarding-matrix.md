---
title: Satellite Ingestion Onboarding Matrix
status: reference
last_updated: 2026-06-23
owner: Akasha ingestion
related:
  - reference/satellite-catalog.md
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

**The single biggest blocker for non-ISRO platforms:** shared orchestration, not just a new
provider client. `worker.py` still instantiates `bhoonidhi.BhoonidhiClient()` directly in
its `bhoonidhi-*` subcommands, the sync path is ResourceSat-specific, `verify-composite`
validates ResourceSat mask/metadata assumptions, and the BFF currently prefers dated
composites only for ResourceSat BOA source IDs. Every non-ISRO provider (Copernicus,
USGS, NASA, Planet) therefore needs the shared enablement in the roadmap Phase 1–3:
source-state consistency, provider factory, canonical manifests, source-aware verification
profiles, fail-closed prepare dispatch, and generic composite/date serving.

---

## 2. Feasibility tiers — all 20 at a glance

| Tier | Meaning | Platforms |
|---|---|---|
| **T1 — Free, buildable now** | Open API + free data; ingest like ResourceSat once the provider client exists | Sentinel-2, Sentinel-1, Landsat 8, Landsat 9, MODIS, EOS-04, EOS-06, NISAR, **ResourceSat-2A LISS-3 ✅ active baseline; LISS-4 🟡 productionization in progress; AWiFS 🟡 gated** |
| **T2 — Free, archive-only** | Free but no new acquisitions (history only) | Landsat 7, Landsat 5, IRS-1C |
| **T3 — Commercial / paid** | API exists but gated behind a licensing/tasking contract + cost | PlanetScope, SkySat, SuperView NEO-1, BlackSky Gen 3, KOMPSAT-3A, ALOS-2, Cartosat-3 |
| **T4 — Free but out-of-AOI** | Free + open but does not cover India | NAIP (US-only) |

**Count check:** T1 = 9, T2 = 3, T3 = 7, T4 = 1 → **20**.

### 2.1 Master matrix

| Platform | Provider | Access | Auth | Optical/SAR | India AOI | New client? | Verdict |
|---|---|---|---|---|---|---|---|
| ResourceSat-2A LISS-3 BOA | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | ✅ Active baseline |
| ResourceSat-2A LISS-4 MX70 L2 | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | 🟡 Productionization in progress until TASK-030 |
| ResourceSat-2A AWiFS BOA | ISRO Bhoonidhi | Free | Password + **IP allow-list** | Optical | ✅ | reuse | 🟡 Gated until TASK-049 |
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

#### A.1 ResourceSat-2A variants — LISS-3 active, LISS-4/AWiFS gated

| Field | Value |
|---|---|
| Status / tier | LISS-3: active baseline · LISS-4: productionization in progress until TASK-030 · AWiFS: gated until TASK-049 |
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
| Verdict | Variant-specific: LISS-3 is the verified reference implementation; LISS-4 remains gated until staging composite verification and activation evidence; AWiFS remains gated until BOA composite validation and activation evidence. |

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
