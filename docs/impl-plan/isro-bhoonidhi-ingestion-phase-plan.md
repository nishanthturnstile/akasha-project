---
goal: ISRO/Bhoonidhi Satellite Ingestion and Crop Analytics Pipeline
version: 2.0
date_created: 2026-06-14
last_updated: 2026-06-14
owner: Akasha Engineering
tags: data, ingestion, satellite, isro, bhoonidhi, resourcesat, cartosat, eos, nisar, cog, stac, minio, titiler, arcgis, composite, mosaic
---

# ISRO/Bhoonidhi Satellite Ingestion and Crop Analytics Pipeline

> **v2.0 rewrite note.** This revision folds in six locked decisions (Q1–Q6, see §3),
> a new launch AOI, and a major architectural change: full 60 km coverage is now produced
> by an **ingestion-time cloud-free composite** (one merged analytic COG + one merged mask
> COG per dated composite), not by query-time mosaicking. The mosaic work therefore moves
> from the old "Phase 8" to **Phase 2b/Phase 3**. All AOI coordinates, display-mode, field-name,
> and operational-host details are updated. This document describes the target implementation
> state; §4 intentionally audits the Sentinel/SCL defaults that still exist in the codebase and
> the later phases retire or rewrite them.

## 1. Introduction

This plan moves Akasha from a Copernicus Sentinel proof/test overlay to an India-specific
production satellite pipeline using ISRO/NRSC data from Bhoonidhi.

The target product behavior is:

- ArcGIS satellite imagery remains the global **true-colour** visual basemap.
- Akasha downloads and owns the operational crop-analysis imagery from Bhoonidhi.
- Bhoonidhi imagery is converted to Cloud Optimized GeoTIFFs (COGs); **multiple scenes are
  merged at ingestion time into one cloud-free composite per dated period** so the **entire
  60 km AOI is fully covered**. Composites are uploaded to MinIO, registered in STAC/pgSTAC,
  and served through the existing BFF/TiTiler path.
- The ISRO overlay is rendered as a **False-Colour Composite (FCC: NIR-Red-Green)** because
  ResourceSat LISS-3 has no blue band and cannot produce true colour. ArcGIS stays the
  true-colour layer underneath.
- The browser continues to use same-origin `/api/*` and `/api/tiles/*` routes only.
- The frontend shows the ISRO overlay only where Akasha has processed coverage — at launch,
  Bangalore plus a 60 km radius, fully covered by the composite.
- Each composite is a **dated** catalog item. The future timeline view lists available
  composite dates for the past three months; the user selects a date and, for a drawn plot,
  receives **cloud-free** index statistics for that date's composite.
- User-drawn polygons compute only indices that are scientifically supported by the selected
  satellite source.

This is not a basemap replacement plan. ArcGIS satellite basemap stays in place. This is an
owned-data ingestion, compositing, cataloging, serving, and analytics plan.

## 2. Research Basis

Reviewed sources:

- Bhoonidhi API specification: <https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/>
- ResourceSat-2A mission page: <https://www.isro.gov.in/RESOURCESAT_2A.html>
- ResourceSat-2A BOA product guide: <https://bhoonidhi.nrsc.gov.in/bhoonidhi_resources/help/docs/User-Guide-Surface_reflectance_from_Resourcesat-2A.pdf>
- EOS-06 mission page: <https://www.isro.gov.in/EOS_06.html>
- Cartosat-3 mission page: <https://www.isro.gov.in/Cartosat_3.html>
- Bhoonidhi satellite data policy summary: <https://bhoonidhi.nrsc.gov.in/bhoonidhi_resources/help/UIM2024/4-UIM2024-Bhoonidhi_SpacePolicy_Implementation.pdf>
- IRS-1C product document: <https://bhoonidhi.nrsc.gov.in/bhoonidhi_resources/help/docs/IRS%201C.pdf>
- NISAR Bhoonidhi product page: <https://bhoonidhi.nrsc.gov.in/NISAR/NisarProducts.html>

Important research findings:

- Bhoonidhi API supports authentication, STAC collection/item access, search, and download.
- Bhoonidhi API access is IP-whitelisted. The ingestion job must run from the approved static
  public IPv4 address (see §3 / §12: the **Akasha staging VM**, IP `20.219.3.35`).
- Bhoonidhi API download automation should use products with `Online = Y`; `Online = N`
  products are not suitable for direct API download automation (they require Browse&Order).
- Bhoonidhi rate limits include 3 search requests per second per IP and 3 concurrent downloads
  per user/IP. Authentication is limited to 20 requests per hour per IP.
- Bhoonidhi EULA language allows free/open use for remote-sensing data with GSD 5 m and higher
  for registered users, but original data must not be commercialized in original form by default;
  acknowledgements should include the required `ISRO-IRS` credit. Akasha's Q2 approval covers the
  current derived-tile/statistics use, but attribution text should include `ISRO-IRS`,
  `ISRO/NRSC`, and `Bhoonidhi` to avoid ambiguity.
- **Staging diagnostic validation completed 2026-06-14:** from the running Akasha staging API
  container, Bhoonidhi auth/search/download succeeded through egress IP `20.219.3.35`; a real
  `ResourceSat-2A_LISS3_BOA` `Online=Y` product was downloaded and inspected. The product contains
  four single-band GeoTIFFs named `BAND2.tif`, `BAND3.tif`, `BAND4.tif`, `BAND5.tif` plus
  `BAND_META.txt`; all four rasters are readable as `uint16`, `EPSG:32643`, `7657 x 7230`, with no
  native GeoTIFF nodata tag. No obvious quality/cloud/shadow/mask raster was present in that
  product archive, so the v1 LISS-3 mask must be Akasha-generated and explicitly provisional.

### 2.1 Confirmed Bhoonidhi API contract (verified against the SIS, 2026-06-14)

The published API spec confirms the full **access** contract the pipeline depends on. It does
**not** describe per-product asset/band/quality-layer structure (see §13 — that remains a
real-download dependency, P0-005).

| Aspect | Confirmed detail |
| --- | --- |
| Base URL | `https://bhoonidhi-api.nrsc.gov.in` (note the `bhoonidhi-api` subdomain) |
| Auth | `POST /auth/token` with `{userId, password, grant_type:"password"}` → JWT `access_token` (`expires_in: 1200` = **20 min**) + longer-lived `refresh_token`; refresh via `grant_type:"refresh_token"`; `POST /auth/logout` revokes a session |
| Collections | `GET /data/collections`, `/data/collections/{id}`, `/data/collections/{id}/items`, `/data/collections/{id}/items/{item_id}` |
| Search | `POST /data/search` (STAC); params: `collections[]`, `datetime` (RFC 3339 range), `bbox`, `intersects` (GeoJSON incl. **Polygon**), `filter` (cql2-json, e.g. `Online=Y`), `limit` (≤ **500**), `sortby`; pagination via `rel:next` links |
| Download | `GET /download?id=<id>&collection=<name>` + Bearer token; only `Online=Y` products |
| Error shape | `{ "ErrorCode", "Description", "Action" }`; download `404`=not online, `412`=concurrency exceeded, `504`=interrupted (retry with wait, not immediate) |

Confirmed collection IDs relevant to this plan (exact strings): `ResourceSat-2A_LISS3_BOA`,
`ResourceSat-2A_AWIFS_BOA`, `ResourceSat-2A_LISS4-MX70_L2`, `EOS-06_OCM-LAC_NDVI_8day_360m`,
`EOS-04_SAR-MRS_L2B`, `NISAR_SSAR-Beta_GCOV`. **Cartosat-3 is absent from the catalog** (only
`CartoSat-1_PAN_CartoDEM_30m` exists) — this validates keeping Cartosat-3 gated (§Phase 7).

Newly surfaced operational constraints (fold into §12 / Phase 3):

- **Auth `403` = "Max sessions already active"** — there is a session-concurrency cap; the client
  must reuse a live session / `logout` stale ones, not merely reuse the bearer token.
- **Daily download limit** beyond concurrency: once reached, downloads are throttled to **1
  concurrent + reduced bandwidth**. The ~90-day backfill (P3-003) must be spread across days.
- Access-token TTL is **20 minutes**; cache and refresh, never fetch per request (auth is the
  tightest limit at 20/hr).
- `intersects` accepts a Polygon, so search can use the real 60 km AOI polygon (not only the bbox).
- ResourceSat-2A LISS-3 BOA provides 4 GeoTIFF bands, approximately 23.5–24 m spatial resolution
  (ISRO mission material states 23.5 m; Bhoonidhi BOA material may round to 24 m), WGS84/UTM,
  16-bit unsigned integer pixels, scale factor `0.0001`, valid range `0-10000`, and image
  background `0`. Phase 0/2a must confirm the actual pixel size from the downloaded BOA GeoTIFF
  metadata before freezing the composite grid resolution.
- **ResourceSat-2A LISS-3 has no blue band.** Its four bands are Green, Red, NIR, and SWIR1.
  Natural/true colour is physically impossible; the standard visualization is a False-Colour
  Composite (NIR→Red, Red→Green, Green→Blue) where healthy vegetation appears bright red.
- ResourceSat-2A BOA products are generated with about a 5 day lag after acquisition.
- ResourceSat-2A LISS-3/AWiFS BOA documentation discusses threshold-based cloud/shadow handling
  with about 50-60 percent accuracy, but the validated LISS-3 BOA product did **not** include an
  obvious delivered quality/cloud/shadow raster. Akasha must expose this limitation, must not call
  it Sentinel-style SCL masking, and must label the first mask as an Akasha threshold-derived
  provisional product.
- ResourceSat-2A LISS-3 and AWiFS have the red, NIR, and SWIR bands needed for NDVI, MSAVI, and
  NDMI. Green + NIR also support NDWI (McFeeters water index).
- ResourceSat-2A LISS-3/AWiFS do not have a true red-edge band. NDRE and RECI are not supported
  accurately for field-level ResourceSat analytics.
- **Coverage geometry:** a 60 km radius AOI is ~120 km across. LISS-3's swath is ~141 km, so a
  single scene only *sometimes* covers the AOI, and over Bangalore (near a path boundary) plus
  monsoon cloud, reliable full single-date coverage is not achievable. Full coverage requires
  compositing multiple scenes/dates — done at ingestion time (§7.4).
- LISS-3 revisit is ~24 days per path; daily full-coverage cloud-free imagery over the AOI is
  not physically possible. The timeline therefore shows available composite dates, not every day.
- EOS-06 OCM products are useful as coarse regional context, not field-level plot analytics, and
  are delivered as pre-computed NDVI composites (single-band display, not raw reflectance).
- EOS-04 and NISAR are SAR sources. They can support radar/backscatter context and future
  moisture/flood/structure products, but they are not optical vegetation-index sources.
- Cartosat-3 is high-resolution visual/context imagery. Bhoonidhi public pages mention Cartosat-3
  FCC/NCC products as orderable, but Cartosat-3 is absent from the Bhoonidhi API collection list;
  it remains gated until direct API collection availability or manual order workflow, licensing,
  radiometry, and band metadata are confirmed.
- IRS-1C is archive/historical. It should not be part of a scheduled current-monitoring refresh.

### 2.2 Real ResourceSat-2A LISS-3 BOA product diagnostic (staging, 2026-06-14)

Diagnostic context:

- Runtime: Akasha staging API container on `akasha-staging`.
- Egress IP observed from inside the API container: `20.219.3.35` (matches the Bhoonidhi whitelist).
- Bhoonidhi auth: password grant succeeded, `expires_in = 1200` seconds.
- Search: `POST /data/search` against `ResourceSat-2A_LISS3_BOA`, `Online=Y`, Bangalore 60 km AOI
  polygon, 120 day lookback returned 5 products.
- Inspected item: `RA319MAR2026048153009900065PSANSTUCSRHTDF`, acquisition datetime
  `2026-03-19T00:00:00Z`, `Online=Y`.

Observed archive/product layout:

| Finding | Observed value |
| --- | --- |
| Green band | `BAND2.tif` |
| Red band | `BAND3.tif` |
| NIR band | `BAND4.tif` |
| SWIR1 band | `BAND5.tif` |
| Metadata sidecar | `BAND_META.txt` |
| Raster count sampled/readable | 4 / 4 |
| Raster size | `7657 x 7230` pixels for each band |
| CRS | `EPSG:32643` |
| Data type | `uint16` |
| Native GeoTIFF nodata tag | `None` |
| Obvious quality/cloud/shadow/mask raster | **Not present** |

Implementation consequences:

- The spectral role mapping in §7.2 is confirmed for the inspected product.
- `BAND_META.txt` becomes a required parser input for scale, valid range, background, acquisition,
  path/row, and product metadata; do not rely only on filename heuristics.
- The first LISS-3 pipeline must generate `mask.tif` itself. The mask method string must be explicit,
  for example `Akasha threshold mask v1 (no native quality layer found; provisional)`.
- Since the input rasters have no native nodata tag, do not blindly treat every single-band DN `0`
  as invalid. Use an all-band/background rule and AOI/footprint warp gaps for mask code `0`, then
  keep cloud/shadow/water classification in the generated mask COG.
- The original P0-005 quality-layer question is resolved for the validated sample: no quality-layer
  asset/class semantics were found. Continue sampling more products during P2a/P3, but do not block
  P2a on a native quality layer; proceed with the Akasha-generated provisional mask fallback.

## 3. Locked Decisions

Operational and infrastructure (validated 2026-06-14):

- **(Q1) Ingestion host = the Akasha staging VM** (`akasha-staging`, `rg-akasha-selfhosted`,
  centralindia). The IP registered and approved with the Bhoonidhi/Bhuvan team is `20.219.3.35`.
  All scheduled Bhoonidhi search/download/sync jobs run here. `akasha-control` is **not**
  whitelisted.
  - Verified: `20.219.3.35` is a Standard-SKU **static** instance IP; the subnet has **no NAT
    gateway**, so the VM's **egress** equals the whitelisted IP (in-guest `curl api.ipify.org`
    returned `20.219.3.35`).
  - Verified resources: `Standard_D4s_v4` (4 vCPU / 15 GiB RAM), 512 GiB Premium data disk at
    `/srv/akasha` (~478 GiB free). The full Akasha stack (web/api/stac-api/titiler/postgis/minio)
    already runs on this VM via Coolify, so the ingestion worker can reach MinIO/STAC/PostGIS
    locally.
  - **Disk caveat:** Docker's data-root is `/var/lib/docker` on the 30 GiB OS disk `/` (~15 GiB
    free), **not** on the 512 GiB disk. Ingestion raw downloads and COG-prep temp **must** be
    bind-mounted to `/srv/akasha`; do not let raw SAFE/ZIP or temp land on `/`.
  - Future move risk: whitelisting is IP-bound; moving ingestion later requires NRSC to
    re-whitelist the new egress IP.

- **(Q2) Redistribution/serving rights are approved.** Serving ResourceSat-2A LISS-3 BOA-derived
  composite tiles and statistics to app users is approved together with the IP whitelist. No
  separate written-confirmation gate is required for the current phase. Obligation: do not expose
  or commercialize original Bhoonidhi downloads as raw source data; render proper
  `ISRO-IRS` / ISRO/NRSC/Bhoonidhi **attribution** on served layers; and test the end-to-end path
  properly.

Product and architecture:

- **(Q3) ISRO overlay default display = False-Colour Composite (FCC), NIR-Red-Green** (vegetation
  red). ArcGIS stays the true-colour basemap. FCC is real multi-band imagery, not an index ramp,
  so it does not violate the "default layer is true-colour, never an index" guardrail. Rejected:
  faking a blue band to approximate natural colour.
- **(Q4) Full 60 km coverage is a hard launch requirement** (including during testing), produced
  by an **ingestion-time cloud-free composite**: all scenes overlapping the AOI within a
  compositing window are merged into **one analytic COG + one mask COG** on a fixed AOI grid
  (UTM 43N). Because the served product is a single pair of COGs, the public tile/statistics route
  shape stays single-item and does not need query-time pixel mosaicking, but Phase 1 still must
  generalize Sentinel `scl` assumptions to source-neutral `mask` assets and add FCC tile handling.
  Each composite is a **dated** catalog item (anchor date = most recent contributing scene date)
  carrying period/provenance/metrics metadata, so the future timeline ("past 3 months, pick a
  date, get cloud-free stats for a drawn plot") drops onto the existing `acquisitionDate` contract
  with no API rename.
- **(Q5) Keep NDWI (`NDWI_GREEN_NIR`)** as a supported/computable index for ResourceSat LISS-3
  (Green + NIR available), but non-default and visually secondary, as today.
- **(Q6) Rename SCL-specific output fields to source-neutral names now** (a deliberate breaking
  change, cheaper pre-launch): `pixelCounts.sclExcludedPixels` → `maskedPixels`;
  `metadata.cloudMask` → `metadata.maskMethod` (per-source description string);
  `cloudMaskedPercent` is kept (already generic); the internal
  `statistics_core.excluded_scl_classes` parameter → `excluded_mask_classes` (source-driven).
  The frontend "Cloud" metric is relabeled to reflect mask provenance and provisional accuracy.

Process discipline (unchanged from v1):

- Plan all requested Indian satellite sources, but phase production value by readiness; implement
  ResourceSat-2A LISS-3 BOA first.
- Remove Sentinel from production **only after** the first ISRO source passes an end-to-end smoke
  test, never before, to avoid a broken intermediate state.
- Mark NDRE and RECI unsupported unless a source provides a true field-scale red-edge band.
- Treat Cartosat-3 as gated until direct API/order access is confirmed.
- Keep frontend tile access same-origin only; the browser never sees Bhoonidhi, MinIO, STAC,
  TiTiler, PostGIS, or object-storage credentials.

## 4. Current Repository State

Relevant current behavior:

- Frontend ArcGIS basemap integration is already separate from Akasha satellite overlays.
- Current production-style overlay code is Sentinel-oriented and lives behind the BFF.
- `apps/api/app/raster/catalog_resolver.py` registers `sentinel-2-l2a` and `sentinel-1-grd`, and
  uses `COLLECTION_ID = "sentinel-2-l2a"` as the default across many resolver helpers
  (`get_source`, display-mode helpers, collection/item/date helpers, latest-item helpers,
  supported/default-index helpers) plus the ultimate fallback in `/api/layers/default`. These
  defaults must be replaced during Sentinel removal.
- `apps/api/app/raster/indices.py` uses Sentinel-2 band names, a frozen Sentinel-2 analytic band
  order, `RGB_BAND_NAMES = [B04,B03,B02]`, and `rgb_band_positions()` for true-colour display.
  The position resolver is reusable, but the current band-name constants assume a blue band and
  cannot be called for ResourceSat FCC sources.
- `apps/api/app/raster/statistics_core.py` assumes an SCL-style categorical mask with class 0 =
  nodata and a hard-coded excluded-class set, and currently only computes normalized-difference
  indices. `_evaluate_index()` receives `formula_kind` but does not dispatch on it yet; it
  unconditionally computes `(a-b)/(a+b)`.
- `apps/api/app/cloud_mask.py`, `apps/api/app/api_models.py`, `field_analytics.py`,
  `field_exports.py`, related API tests, and frontend types/tests still contain SCL-specific names
  such as `nativeExcludedSclClasses`, `sclExcludedPixels`, and Sentinel cloud/cirrus class mapping.
- `apps/api/app/raster/service.py` raises `MULTI_SCENE_STATISTICS_UNAVAILABLE` for statistics when
  a date resolves to more than one intersecting item; `product.py` raises `MOSAIC_TILES_UNAVAILABLE`
  for display tiles in the same condition. The composite approach (§7.4) avoids triggering these by
  serving a single merged COG pair for a composite date.
- `apps/api/app/raster/catalog_resolver._resolve_item_assets` requires asset keys literally named
  `analytic` and `scl`; the service/reader pass `sclHref`/`scl_href` and return `read.scl`. This
  must be generalized to a source-declared mask asset (`mask`) while keeping Sentinel compatibility
  during coexistence.
- The product API still hard-codes the AOI in the `_AOI` constant in `product.py`; the old
  `DEFAULT_AOI_ID=bangalore` setting is propagated through env files; and `AOI_CONFIG_PATH` already
  exists in deployment configuration but is not yet wired into `/api/config` route logic.
- The ingestion worker (`services/ingestion/worker.py`) already supports `info`, `scene-key`,
  `migrate-catalog`, `seed-stac`, `seed-minio`, `seed`, `ingest-manifest`, `verify`,
  `verify-cogs`, `verify-manifest-cogs`, `healthcheck`. New Bhoonidhi subcommands extend this CLI,
  but `SceneIdentity`, STAC item builders, storage verification, and phase validators are currently
  Sentinel/SCL/MGRS-shaped and require ResourceSat-specific paths.
- Sentinel references to retire/rewrite during Phase 8 exist in: `apps/api/.env.example`,
  `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml`, `infra/selfhosted/env.example`,
  `infra/selfhosted/README.md`, `infra/gateway/.env.example`,
  `docs/architecture-tech-stack.md`, `docs/data-ingestion-and-satellite-rules.md`,
  `docs/engineering-dos-donts.md`, `docs/emergent-context.md`, `docs/platform-plan.md`,
  `docs/sentinel-2-l2a-cog-prep-runbook.md`, `docs/sentinel-1-grd-cog-prep-runbook.md`,
  `data/seed/README.md`, `data/seed/stac/sentinel-*`, `scripts/*sentinel*`, repo-root
  `tests/test_*sentinel*`, frontend test fixtures/types referencing Sentinel or SCL fields, and
  `AGENTS.md` / `CLAUDE.md`.
- Current `data/seed/bangalore-aoi.geojson` is a small box (`center [77.59, 12.97]`,
  `bbox [77.4, 12.8, 77.8, 13.2]`) — replaced by the new 60 km AOI (§5), and all env references to
  the old file must be updated or deliberately retained as legacy-only.

Important existing guardrails to preserve:

- Only the web gateway is public.
- Browser calls stay same-origin; the frontend never hard-codes COG/object URLs.
- STAC/pgSTAC owns satellite metadata; MinIO owns COG object storage.
- The BFF computes masked statistics; TiTiler serves display tiles.
- Large rasters and raw downloads stay out of git.
- Categorical masks resample with nearest-neighbour; continuous reflectance with bilinear/cubic.

## 5. Target AOI

Canonical launch AOI (recomputed 2026-06-14 for the confirmed center):

| Field | Value |
| --- | --- |
| AOI id | `bangalore-60km` |
| Display name | `Bangalore 60 km` |
| Center lon/lat | `[77.5776037099731, 13.076858177177233]` |
| 60 km search bbox `[minLon, minLat, maxLon, maxLat]` | `[77.023647, 12.537266, 78.131561, 13.616450]` |
| Approx box size | ~120 km (E-W) × ~119 km (N-S) |
| Operational geometry | A real 60 km radius polygon generated around the center |
| Composite grid CRS | UTM zone 43N (EPSG:32643) — Bangalore longitude 77.58°E is in zone 43 |
| Native resolution | ~23.5–24 m (LISS-3; confirm from downloaded BOA GeoTIFF metadata before freezing grid) |

Implementation requirement:

- Prefer the real 60 km polygon (`intersects`) for Bhoonidhi search when accepted; use the bbox as
  a fallback or precomputed convenience value. Do not send both `bbox` and `intersects` in the same
  STAC search request if the API follows STAC Item Search semantics that reject both together.
- Use the real 60 km polygon for coverage filtering, clipping, and AOI metrics.
- Snap the composite output grid to a fixed UTM 43N extent covering the 60 km polygon (with a
  small padding for tile/stat windows) so every composite shares identical pixel geometry. The
  target pixel size is source-configured and must be set from confirmed BOA metadata (expected
  around 23.5–24 m), not blindly hard-coded.
- Load AOI from `AOI_CONFIG_PATH`; do not hard-code it in API routes or React components.
  `AOI_CONFIG_PATH` already exists in deployment configuration, but it must become the actual
  `/api/config` source of truth. Retire the `_AOI` constant immediately; keep `DEFAULT_AOI_ID` only
  as a legacy env field until Phase 8 cleanup removes or rewrites remaining references.

## 6. Source Capability Matrix

| Source id | Bhoonidhi collection/product target | Role | Resolution | Refresh | Display | Supported analytics |
| --- | --- | --- | --- | --- | --- | --- |
| `resourcesat-2a-liss3-boa` | `ResourceSat-2A_LISS3_BOA` | Primary crop analytics | ~23.5–24 m | Daily search, BOA lag-aware | FCC (NIR-R-G) | NDVI, MSAVI, NDMI, NDWI |
| `resourcesat-2a-awifs-boa` | `ResourceSat-2A_AWIFS_BOA` | Regional crop/context | 56 m | Daily or every 3 days | FCC (NIR-R-G) | NDVI, MSAVI, NDMI, NDWI |
| `resourcesat-2a-liss4-mx70-l2` | `ResourceSat-2A_LISS4-MX70_L2` | Higher-resolution optical context | 5.8 m class | Access/product dependent | FCC | NDVI/MSAVI only if calibrated red/NIR confirmed |
| `eos-06-ocm-lac-ndvi` | `EOS-06_OCM-LAC_NDVI_8day_360m` or related OCM product | Coarse regional context | 360 m or coarser | 8 day/product dependent | Single-band NDVI ramp (context) | Display/context only, not field-level analytics |
| `eos-04-sar-mrs-l2b` | `EOS-04_SAR-MRS_L2B` or related ARD product | SAR context | product dependent | product dependent | Backscatter grayscale | Radar summaries, no optical indices |
| `nisar-ssar-gcov` | `NISAR_SSAR-Beta_GCOV`, later routine S-SAR GCOV | SAR context | product dependent | 12 day nominal repeat when routine | Backscatter grayscale | Radar summaries, no optical indices |
| `cartosat-3-mx` | Gated until access confirmed | High-resolution visual/context | 1.1 m class MX / finer | order/access dependent | Visual | None by default |
| `irs-1c-liss3-archive` | IRS-1C archive products | Historical archive | 23.5 m VNIR, 70.5 m SWIR | no scheduled refresh | FCC | Archive/context, optional NDVI/NDMI after calibration validation |

Unsupported for current India-only field-level v1: **NDRE**, **RECI** (require a true red-edge band
none of the planned field-level ISRO sources provide).

## 7. Target Data Model

### 7.1 Source registry

Each source must declare:

- `sourceId`, `provider`, `kind` (`optical` | `sar` | `context` | `archive`)
- `bhoonidhiCollectionId`, `expectedAssets`
- `bandRoleMapping` (spectral role → product band)
- `scale`, `offset`, `backgroundValue`, `nodataPolicy`
- `maskAsset` (asset key for the mask/quality COG), `maskMethod` (human description; identifies
  product-quality-layer vs Akasha-threshold and accuracy caveat), `maskClassMap`
  (mask integer codes), `excludedMaskClasses`
- `supportedIndices`, `displayModes`, `defaultDisplayMode`, tile expression/rescale defaults
- `resolutionMeters`, `refreshPolicy`, `limitations`, `attribution`
- `compositePolicy` (window length, selection rule) for sources served as composites

### 7.2 Spectral roles

Replace Sentinel-specific index calculations with source-aware spectral roles resolved from STAC
asset metadata (never hard-coded positions):

`BLUE`, `GREEN`, `RED`, `NIR`, `SWIR1`, `SWIR2`, `RED_EDGE`

ResourceSat-2A LISS-3 BOA mapping (no blue):

| Spectral role | Product band |
| --- | --- |
| `GREEN` | `BAND2` |
| `RED` | `BAND3` |
| `NIR` | `BAND4` |
| `SWIR1` | `BAND5` |

Display composites are also defined by roles:

- **FCC (default ISRO overlay):** `[NIR, RED, GREEN]` → display R,G,B. Implemented via a new `FCC`
  display mode and `tileRouteMode: "fcc"`, mirroring how `rgb_band_positions()` resolves
  true-colour positions today.
- **RGB (true colour):** `[RED, GREEN, BLUE]` — only for sources that have a blue band (e.g.
  Sentinel during coexistence).

### 7.3 Index registry

The index engine is generalized from "normalized-difference only" to a small set of formula kinds
keyed by spectral roles:

| Index | Formula | Required roles | v1 status |
| --- | --- | --- | --- |
| NDVI | `(NIR - RED) / (NIR + RED)` | `NIR`, `RED` | Supported (LISS-3/AWiFS) |
| NDMI | `(NIR - SWIR1) / (NIR + SWIR1)` | `NIR`, `SWIR1` | Supported (LISS-3/AWiFS) |
| NDWI (`NDWI_GREEN_NIR`) | `(GREEN - NIR) / (GREEN + NIR)` | `GREEN`, `NIR` | Supported, **non-default**, secondary |
| MSAVI | `(2·NIR + 1 − sqrt((2·NIR + 1)² − 8·(NIR − RED))) / 2` | `NIR`, `RED` | Supported (LISS-3/AWiFS) — **new non-ND formula kind** |
| NDRE | `(NIR - RED_EDGE) / (NIR + RED_EDGE)` | `NIR`, `RED_EDGE` | Unsupported until a true red-edge source exists |
| RECI | `(NIR / RED_EDGE) - 1` | `NIR`, `RED_EDGE` | Unsupported until a true red-edge source exists |

Engine notes:

- `IndexDef.formula_kind` becomes an explicit dispatch value (`normalized_difference`, `msavi`,
  `simple_ratio_minus_1`, …). Current code passes `formula_kind` through but ignores it, so Phase 1
  must add the actual dispatch path in `statistics_core._evaluate_index()` and keep pure-numpy tests
  for every formula kind.
- MSAVI still uses two bands (`NIR`, `RED`) but is not a normalized difference. Clamp small negative
  radicands caused by floating-point noise to zero; real negative radicands beyond numerical noise
  should become masked/invalid rather than producing NaNs silently.
- API behavior: if the source lacks the required roles, return `UNSUPPORTED_INDEX`; never
  approximate NDRE/RECI from red bands.

### 7.4 Cloud-free composite (the coverage mechanism)

The launch product is an **ingestion-time best-available-pixel composite**:

1. **Inputs:** all LISS-3 BOA scenes whose footprint overlaps the 60 km AOI within a compositing
   window (default ~30–45 days, ≥ one LISS-3 revisit; configurable).
2. **Reproject & align:** warp each scene's analytic bands (continuous → bilinear/cubic) and its
    mask (categorical → nearest-neighbour) to the fixed AOI grid (UTM 43N, source-confirmed LISS-3
    pixel size, fixed extent).
3. **Per-pixel selection:** prefer a `valid` pixel (non-cloud, non-shadow, non-nodata per the mask);
   among valid candidates choose the **most recent** acquisition; if no valid candidate exists,
   keep the least-bad pixel and mark it masked in the output mask.
4. **Outputs:** one merged **analytic COG** (4 bands, frozen role order) + one merged **mask COG**
   covering the entire AOI, both with overviews and correct CRS/transform/nodata.
5. **Provenance (optional band/metadata):** record contributing scene ids/dates; optionally a
   per-pixel source-date band for audit.

Because the served product is a single analytic+mask COG pair, the existing statistics flow can be
reused **after** Phase 1 generalizes `scl` to a source-declared `mask` asset. The request still
resolves one dated STAC item, so query-time pixel mosaicking is not needed and
`MULTI_SCENE_STATISTICS_UNAVAILABLE` / `MOSAIC_TILES_UNAVAILABLE` are never triggered for the
composite source.

### 7.5 Source-neutral mask encoding

ResourceSat composites use an Akasha-neutral categorical mask (not SCL). For the validated LISS-3
BOA product (§2.2), no native quality/cloud/shadow/mask raster was delivered, so the launch LISS-3
mask is generated by Akasha and remains provisional until validated against more scenes or an NRSC
quality product is supplied separately.

| Code | Meaning | Default handling |
| --- | --- | --- |
| 0 | nodata / gap (outside coverage) | counted as nodata |
| 1 | valid | kept |
| 2 | cloud | excluded (counts toward `cloudMaskedPercent`) |
| 3 | shadow | excluded |
| 4 | water | kept by default |

`excludedMaskClasses = {0, 2, 3}` for ResourceSat (Sentinel keeps its SCL set during coexistence).

Fallback mask policy for LISS-3 v1:

- **Inputs:** the four BOA bands (`BAND2`, `BAND3`, `BAND4`, `BAND5`) plus `BAND_META.txt`.
- **Gap/nodata (code 0):** pixels outside the AOI/scene footprint after reprojection, and pixels
  matching the product background rule from `BAND_META.txt`. Until the metadata parser proves a
  stricter rule, classify a pixel as gap only when all four bands are background/zero; do **not**
  invalidate a pixel just because one band has DN `0`.
- **Valid (code 1):** pixels not classified as gap/cloud/shadow/water by the configured rules.
- **Cloud (code 2):** Akasha threshold heuristic over reflectance/brightness, configured per source
  and validated on sampled scenes before production acceptance.
- **Shadow (code 3):** Akasha dark-pixel heuristic, explicitly provisional and tuned with field
  review; avoid over-masking dark soil/water by checking spectral context.
- **Water (code 4):** optional NDWI/low-NIR rule; water is kept by default for statistics.

The generated mask's `maskMethod` must state `Akasha threshold mask v1 (no native quality layer
found; provisional)` or an equally explicit source-neutral description. Set
`akasha:metrics_provisional = true` for all LISS-3 products until the threshold rules are validated
or replaced by a confirmed NRSC quality layer.

Implementation note: the inspected input GeoTIFFs have no native nodata tag. If output analytic COGs
set a `nodata` tag for interoperability, the statistics engine must still use the generated mask
code `0` as the ResourceSat gap authority; never apply Sentinel's single-band nodata behavior to
ResourceSat without source-specific tests.

### 7.6 Dated composite catalog item

Each composite is registered as one **dated** STAC item:

- `datetime` / `akasha:acquisition_date` = anchor date (most recent contributing scene date).
- `akasha:composite = true`, `akasha:period_start`, `akasha:period_end`,
  `akasha:contributing_scenes` (ids + dates for provenance).
- `akasha:coverage_percent`, `akasha:usable_pixel_percent`, `akasha:cloud_masked_percent`,
  `akasha:mask_method`, `akasha:metrics_provisional`.
- Assets: `analytic` (composite analytic COG) and `mask` (composite mask COG).

This keeps the public `acquisitionDate` contract intact: the timeline lists composite dates, and
selecting one resolves to that composite COG for both tiles and statistics.

## 8. Object Storage and STAC Layout

Composite (served) keys:

```text
s3://akasha-cogs/{sourceId}/composite/{aoiId}/{compositeDate}/analytic.tif
s3://akasha-cogs/{sourceId}/composite/{aoiId}/{compositeDate}/mask.tif
```

Per-scene (provenance, not served) keys:

```text
s3://akasha-cogs/{sourceId}/scene/{acquisitionDate}/{sceneComponent}/analytic.tif
s3://akasha-cogs/{sourceId}/scene/{acquisitionDate}/{sceneComponent}/mask.tif
```

For SAR sources: `…/{sceneComponent}/backscatter.tif`. For context-only/Cartosat:
`…/{sceneComponent}/visual.tif`.

STAC requirements:

- One collection per source/product family; one item per served composite (and per scene for
  provenance).
- Composite items carry the §7.6 fields. SAR items use SAR-safe metrics (no optical cloud metrics,
  no optical indices).
- `akasha:metrics_provisional = true` whenever the mask is threshold-derived or unvalidated.
- `akasha:mask_method` identifies product-quality-layer vs Akasha-threshold provenance.

Determinism / idempotency:

- ResourceSat scene key = `{satellite}:{product_level}:{path}:{row}:{acquisition_datetime}`
  (Path/Row, **not** MGRS; no processing baseline). Composite key =
  `{sourceId}:composite:{aoiId}:{compositeDate}:{windowStart}:{windowEnd}`.
- `upsert` is the normal STAC load mode; uploads skip existing keys unless `--force`.
- Re-running ingestion for the same window is idempotent: it rebuilds/replaces the same composite
  key and re-upserts the same dated item.

## 9. Phase Plan

### Phase 0: Baseline, AOI, and Bhoonidhi Access Check

Goal: confirm Bhoonidhi access from the whitelisted staging VM and prepare the app for an
India-only AOI/source model.

| Task | Description |
| --- | --- |
| P0-001 | Add `data/seed/bangalore-60km-aoi.geojson` with the §5 center, bbox, and a real 60 km polygon; update development/staging `AOI_CONFIG_PATH` references to this file for the ISRO path. |
| P0-002 | Wire the existing `AOI_CONFIG_PATH` setting into `/api/config`; validate missing/malformed AOI files with a clear startup or route error; remove the `_AOI` route constant; deprecate `DEFAULT_AOI_ID` as selection logic. |
| P0-003 | Document ingestion-only Bhoonidhi env: `BHOONIDHI_USER_ID`, `BHOONIDHI_PASSWORD`, `BHOONIDHI_API_BASE` (`https://bhoonidhi-api.nrsc.gov.in`), search RPS, download concurrency, raw/temp roots under `/srv/akasha`. Secrets live only on the staging VM / ingestion worker env, never browser-visible. |
| P0-004 | From the staging VM (egress `20.219.3.35`): `POST /auth/token`; `GET /data/collections` (confirm `ResourceSat-2A_LISS3_BOA`); `POST /data/search` over the AOI (use `intersects` polygon or `bbox`) with `Online=Y` cql2-json filter; `GET /download?id=&collection=` for one small `Online=Y` product. **Completed for one real LISS-3 BOA product on 2026-06-14; keep as a repeatable smoke check.** |
| P0-005 | Record confirmed Bhoonidhi response shapes and real product layout in a runbook. **Updated from staging diagnostic:** the inspected product contains `BAND2/3/4/5.tif` + `BAND_META.txt`, has no obvious quality/cloud/shadow/mask raster, and therefore requires the §7.5 Akasha-generated provisional mask fallback. |
| P0-006 | Ensure ingestion raw/temp paths bind-mount to `/srv/akasha` (not `/`); confirm disk headroom. |
| P0-007 | Do not change Sentinel production defaults yet. |
| P0-008 | Add ResourceSat STAC seed scaffolding (`data/seed/stac/resourcesat-2a-liss3-boa-collection.json` and a minimal sample/composite item shape) so `seed-stac` and resolver tests have source-controlled contracts before real downloads arrive. |

Exit criteria: staging VM can call Bhoonidhi from the whitelisted egress IP; AOI config is
source-controlled; the real quality-layer semantics are captured (download-confirmed, not assumed
from the spec); no browser-visible secrets or internal URLs introduced.

### Phase 1: Source-Aware BFF and Analytics Registry

Goal: make the backend handle non-Sentinel optical sources, role-based indices, source-neutral
masks/fields, and unsupported-index decisions.

| Task | Description |
| --- | --- |
| P1-001 | Refactor the index registry from Sentinel band names to **spectral roles**. |
| P1-002 | Add formula-kind dispatch in the pure statistics engine; implement **MSAVI** (non-ND) with radicand handling, metadata formula generation, and unit tests for ND formulas + MSAVI edge cases. |
| P1-003 | Resolve role→band-position per source from STAC asset metadata. |
| P1-004 | Add source-specific `scale`, `offset`, `backgroundValue`, `nodataPolicy`, **mask asset key**, mask class map, and `excludedMaskClasses`. Generalize the resolver's `analytic`/`scl` coupling to a declared `maskAsset` (`mask` for ResourceSat, `scl` for Sentinel coexistence); propagate `maskHref` through `service.py` and rename `raster_reader` inputs/outputs (`scl_href`/`read.scl` → `mask_href`/`read.mask`). |
| P1-005 | **(Q6)** Rename output fields to source-neutral across backend and frontend: `sclExcludedPixels` → `maskedPixels`; `nativeExcludedSclClasses` → `nativeExcludedMaskClasses`; `metadata.cloudMask` → `metadata.maskMethod`; engine/API args `excluded_scl_classes` → `excluded_mask_classes`. Include `cloud_mask.py`, `api_models.py`, `field_analytics.py`, `field_exports.py`, `reports.py`, `risk.py`, frontend `types/api.ts`, API/frontend fixtures, and tests. |
| P1-006 | Add the `resourcesat-2a-liss3-boa` source registry entry and STAC collection contract: FCC default display, NDVI/MSAVI/NDMI/NDWI, expected assets `analytic` + generated `mask`, §7.5 mask encoding, scale `0.0001`, offset `0` unless `BAND_META.txt` proves otherwise, background/all-band-gap policy, and `metricsProvisional=true`. |
| P1-007 | Add the **FCC** display mode + `tileRouteMode: "fcc"`; implement a role-based FCC position resolver, TiTiler URL builder (`bidx`/expression `[NIR, RED, GREEN]`, LISS-3 positions `[3,2,1]` after role resolution), and ResourceSat-appropriate display rescale defaults. |
| P1-008 | Add placeholder/gated registry entries for AWiFS, LISS-4, EOS-06, EOS-04, NISAR, Cartosat-3, IRS-1C. |
| P1-009 | Update `/api/sources` to expose source-specific indices, display modes, resolution, refresh policy, limitations, `maskMethod`, attribution, available mask options (for example hide/disable `cirrus` for ResourceSat), and display rescale hints. |
| P1-010 | Handle "registered-but-empty" sources gracefully (a source with zero composites must not 500; return an empty/clear state). |
| P1-011 | Update API tests for source-specific supported indices, unsupported NDRE/RECI, FCC display, renamed fields, field analytics/export propagation, source-aware mask options, and registered-but-empty source behavior. |

Exit criteria: API advertises ResourceSat-2A LISS-3 BOA (FCC, NDVI/MSAVI/NDMI/NDWI); NDRE/RECI
return clean `UNSUPPORTED_INDEX`; output uses source-neutral field names; a registered source with
no data is handled cleanly.

### Phase 2a: ResourceSat Single-Scene Pipeline Proof

Goal: de-risk the raster path on one real scene before building the composite.

| Task | Description |
| --- | --- |
| P2a-001 | Add a Bhoonidhi client module (auth, token refresh/reuse, search, download) with rate-limit/backoff. Base `https://bhoonidhi-api.nrsc.gov.in`; cache the 20-min access token + refresh; persist/reuse one live session per worker run; handle auth `403` (max sessions — reuse or explicit `/auth/logout` of the known session), search `429`, download `404`/`412`/`504` with wait-not-immediate-retry. |
| P2a-002 | `worker.py bhoonidhi-search --source resourcesat-2a-liss3-boa --aoi bangalore-60km --lookback-days 45`; filter to `Online=Y`, positive AOI overlap, expected collection; write a dry-run coverage manifest. |
| P2a-003 | `worker.py bhoonidhi-download --manifest …` with resume + backoff; raw lands in `/srv/akasha`. |
| P2a-004 | `prepare_resourcesat_liss3_boa_cogs.py`: parse `BAND_META.txt`; stack `BAND2,BAND3,BAND4,BAND5` into one analytic COG (role order); build an Akasha-generated provisional `mask.tif` using §7.5 gap/cloud/shadow/water rules because the validated product has no native quality raster; validate COGs (overviews, CRS, transform, band count, mask classes, source-confirmed pixel size). |
| P2a-005 | Add ResourceSat ingestion identity/STAC plumbing: `_resourcesat_from_prepare_manifest` in `services/ingestion/akasha_ingest/scene.py`, the ResourceSat scene-key formula (§8), ResourceSat STAC item builder using `analytic` + `mask`, and then ingest via `worker.py ingest-manifest --method upsert`. |
| P2a-006 | Verify: one scene renders as an FCC tile through `/api/tiles/…`; a drawn polygon within the scene returns NDVI/MSAVI/NDMI/NDWI with `maskedPixels`/`maskMethod`/provisional fields. |
| P2a-007 | Add `tests/test_prepare_resourcesat_liss3_boa_cogs.py` and ingestion unit tests mirroring the Sentinel prep-script patterns, but asserting 4-band ResourceSat order, `BAND_META.txt` parsing, generated `mask.tif`, all-band-zero/background gap handling, ResourceSat scene identity, and provisional mask class semantics. |
| P2a-008 | Run the diagnostic on at least two additional `Online=Y` LISS-3 BOA products from different dates/path-row candidates. If any product includes a native quality layer, document it and add source-registry support; otherwise keep Akasha threshold mask v1 as the launch path. |

Exit criteria: end-to-end raster path proven on one real LISS-3 scene (download → COG → MinIO →
STAC → FCC tile → polygon stats), with honest source-neutral mask reporting.

### Phase 2b: Full 60 km Cloud-Free Composite (launch coverage)

Goal: cover the **entire** 60 km AOI with a single cloud-free composite (the hard launch
requirement).

| Task | Description |
| --- | --- |
| P2b-001 | Define the fixed AOI composite grid (UTM 43N, source-confirmed LISS-3 pixel size around 23.5–24 m, snapped extent + padding). |
| P2b-002 | Implement the §7.4 best-available-pixel compositor as bite-sized units: fixed-grid helper, per-scene reprojection/alignment (continuous vs categorical resampling), candidate validity scoring, recency tie-break, output writer, and provenance/metrics collector. |
| P2b-003 | Compute composite metrics (coverage %, usable %, cloud-masked %) and the §7.6 dated composite item (anchor date, period, contributing scenes, provisional flag). |
| P2b-004 | Upload composite COGs to MinIO (composite keys, §8) and register the dated composite item; keep per-scene items for provenance. |
| P2b-005 | `worker.py build-composite --source … --aoi bangalore-60km --window-start … --window-end …` (idempotent rebuild/replace). |
| P2b-006 | Add `worker.py verify-composite`: full-AOI coverage above a configurable threshold, valid ResourceSat mask classes, 4-band analytic COG validity, 1-band mask COG validity, UTM 43N/source-confirmed pixel-size alignment, overviews, dated item present. |
| P2b-007 | Verify: the composite FCC overlay fills the whole 60 km AOI; polygons anywhere in the AOI return cloud-free stats; no `MULTI_SCENE`/`MOSAIC` errors. |
| P2b-008 | Add synthetic compositor tests for overlapping scenes: valid-first selection, most-recent valid tie-break, all-invalid fallback, nodata/mask-code 0 accounting, and deterministic output transform. |
| P2b-009 | Add composite manifest/config discovery support for the new object layout (`{sourceId}/composite/{aoiId}/{date}/...`); do not rely on Sentinel `data/seed/rasters/{date}/{mgrsTile}` globs. |

Exit criteria: a single dated composite covers the entire 60 km AOI; FCC overlay and polygon stats
work across the whole AOI from one analytic+mask COG pair.

### Phase 3: Static-IP Scheduled Sync & Composite Refresh

Goal: automate discovery, download, and composite rebuild on the staging VM; seed ~90 days of
history for the future 3-month timeline.

| Task | Description |
| --- | --- |
| P3-001 | `worker.py bhoonidhi-sync --source <id> --aoi bangalore-60km`: search → download new `Online=Y` scenes → rebuild affected composite(s). |
| P3-002 | Configure the staging VM with a cron/systemd timer, non-overlap lock (`flock`/systemd single-instance), and raw/temp/ledger paths on `/srv/akasha`. |
| P3-003 | Run ResourceSat-2A LISS-3 BOA search daily; **backfill ~90 days at launch** so the timeline has 3 months of composite dates; ongoing compositing window ~30–45 days (both configurable). |
| P3-004 | Skip already-ingested product ids; idempotent composite rebuild per window. |
| P3-005 | Respect Bhoonidhi auth/search/download rate limits (reuse tokens; ≤3 search/s; ≤3 concurrent downloads; back off on 412/429). |
| P3-006 | Retry/backoff for 401, 412, 429, 500, 504. |
| P3-007 | Maintain a worker-local SQLite ingestion ledger at `/srv/akasha/ingestion/ledger.sqlite` (product id, source id, scene/composite key, status, retries, bytes, errors, timestamps). STAC/MinIO remain the durable catalog/storage source of truth. |
| P3-008 | Delete raw downloads after successful COG/composite validation unless audit retention is enabled. |
| P3-009 | Emit operator-friendly logs for monitoring and failure triage. |

Exit criteria: re-running sync is idempotent; new scenes are discovered, downloaded, and folded
into rebuilt composites without duplicates; ~3 months of composite dates exist; failures are
visible and retryable.

### Phase 4: Frontend Source, AOI, Composite & Timeline Behavior

Goal: make the UI accurately represent ArcGIS basemap + ISRO composite coverage, and add the
date/timeline experience.

| Task | Description |
| --- | --- |
| P4-001 | Keep ArcGIS satellite basemap unchanged (true-colour). |
| P4-002 | Center/constrain the launch experience on the 60 km AOI via `/api/config`. |
| P4-003 | Render the ISRO **FCC** composite overlay on top of ArcGIS; render the required ISRO/NRSC/Bhoonidhi **attribution** string. |
| P4-004 | Drive supported indices from `/api/sources`; show NDVI default, NDMI/MSAVI, and NDWI as a secondary/non-default option; hide NDRE/RECI when the source lacks `RED_EDGE`. |
| P4-005 | Relabel the stats panel mask metric to reflect provenance + provisional accuracy (no "SCL"); read `maskedPixels`/`maskMethod`/`metricsProvisional`; hide or disable unsupported mask toggles such as ResourceSat `cirrus`. |
| P4-006 | **Timeline (launch: minimal; full scrubber: this phase's deliverable):** list available composite dates for the past 3 months from `/api/sources/{id}/dates`; default to the latest cloud-free composite; let the user select a date; for a drawn plot + selected date, request cloud-free stats via the existing `acquisitionDate` flow. |
| P4-007 | Show no-data/stale/processing/error states where composite coverage is missing; ensure ArcGIS stays visible outside ISRO coverage. |
| P4-008 | Keep opacity/visibility/date/polygon analytics driven by BFF metadata only; same-origin tile URLs only. |

Exit criteria: UI renders ArcGIS globally and the ISRO FCC composite over the full 60 km AOI with
attribution; the timeline lists 3 months of composite dates; selecting a date returns cloud-free
polygon stats; no object/internal URLs exposed.

### Phase 8a (partial, after Phase 2b smoke test): Production Default Switch & Sentinel Removal

> Pulled in early per the locked sequencing: switch and remove Sentinel **only after** ResourceSat
> passes the Phase 2b end-to-end smoke test. Phase 8 is intentionally split: **8a** performs the
> default switch and Sentinel cleanup needed for production launch; **8b** handles later hardening.

| Task | Description |
| --- | --- |
| P8-001 | Switch the production default source to `resourcesat-2a-liss3-boa` (`DEFAULT_SOURCE_ID` in `apps/api/.env.example`, `infra/docker/docker-compose.yml`, `infra/selfhosted/coolify-compose.yml`, `infra/selfhosted/env.example`, and deployment docs). |
| P8-002 | Replace every `COLLECTION_ID = "sentinel-2-l2a"` resolver default/fallback in `catalog_resolver.py`, `/api/layers/default`, and `StatisticsRequest.sourceId` defaults. |
| P8-003 | Remove Sentinel seed COGs/STAC from production deployments. |
| P8-004 | Remove or rewrite Sentinel scripts, tests, validators, smoke-test defaults, frontend fixtures, and docs (`scripts/*sentinel*`, repo-root `tests/test_*sentinel*`, `docs/sentinel-*-runbook.md`, `docs/emergent-context.md`, `docs/platform-plan.md`, `data/seed/README.md`, `data/seed/stac/sentinel-*`, `infra/selfhosted/README.md`, Sentinel sections of `architecture-tech-stack.md` / `data-ingestion-and-satellite-rules.md` / `engineering-dos-donts.md`, `AGENTS.md` / `CLAUDE.md`, and frontend tests/types referencing Sentinel source ids or SCL fields). Preserve the index-agnostic pure-numpy statistics tests. |
| P8-005 | Update deployment env examples and self-hosted/Coolify docs to ISRO defaults; remove or clearly mark legacy `DEFAULT_AOI_ID=bangalore` and old `bangalore-aoi.geojson` references after `AOI_CONFIG_PATH` is authoritative. |

Exit criteria: production has no Sentinel selectable/default source; ResourceSat is the default;
smoke tests use ISRO data.

### Phase 5: Additional Optical and Context Sources

| Task | Description |
| --- | --- |
| P5-001 | ResourceSat-2A AWiFS BOA adapter (same BOA assumptions, 56 m, NDVI/MSAVI/NDMI/NDWI), composited like LISS-3. |
| P5-002 | ResourceSat-2A LISS-4 adapter only after band/radiometry metadata confirms calibrated red/NIR. |
| P5-003 | EOS-06 OCM NDVI as coarse **single-band context** (separate display path; not field-level analytics; no reflectance-correction/2-band stats flow). |
| P5-004 | IRS-1C archive import as a one-time historical path; no scheduled refresh. |
| P5-005 | Keep each source's limitations visible via `/api/sources`. |

Exit criteria: each added source can be listed, ingested, registered, and rendered or explicitly
marked context-only; the UI only enables analytics matching source capabilities.

### Phase 6: SAR Sources

| Task | Description |
| --- | --- |
| P6-001 | EOS-04 SAR-MRS L2B/ARD adapter after confirming product format and polarization metadata. |
| P6-002 | Convert selected backscatter/polarization layers to COG. |
| P6-003 | Register SAR STAC items with SAR-safe metrics (no optical cloud metrics, no optical indices). |
| P6-004 | NISAR S-SAR GCOV adapter after routine product availability and HDF5 layer structure are confirmed. |
| P6-005 | Expose SAR display modes and future radar statistics separately from optical indices. |

Exit criteria: SAR layers render as context; the API rejects NDVI/MSAVI/NDMI/NDWI/NDRE/RECI for SAR
sources; SAR processing stays separate from optical.

### Phase 7: Cartosat-3 Gated Visual Adapter

| Task | Description |
| --- | --- |
| P7-001 | Confirm Cartosat-3 API/order workflow, licensing, pricing, redistribution rights, product format. |
| P7-002 | If no direct API access, implement operator-upload/manual import of delivered GeoTIFFs. |
| P7-003 | Convert to visual COGs and register as context-only STAC items. |
| P7-004 | Do not enable crop indices unless calibrated band metadata and allowed use are confirmed. |

Exit criteria: Cartosat is either a context-only manual/import path or remains explicitly gated; no
unverified automation promised.

### Phase 8b (remaining): Hardening & Monitoring

| Task | Description |
| --- | --- |
| P8-101 | Multi-AOI composite support (parameterize the fixed-grid compositor beyond Bangalore). |
| P8-102 | Optional advanced cross-date statistics refinements beyond the composite (only if a product need emerges). |
| P8-103 | Monitoring: latest successful/available composite date per source, Bhoonidhi auth/search/download failures, conversion/composite failures, MinIO usage, stale latest date, STAC registration failures. |

Exit criteria: operators can diagnose failed refreshes; coverage/freshness/storage are monitored.

## 10. Public API and UI Changes

### `/api/config`
- Return the AOI loaded from `AOI_CONFIG_PATH` (`bangalore-60km`, §5 center/bbox/polygon).
- Return ResourceSat as production default after the Phase 2b smoke test.

### `/api/sources`
Per source: `resolutionMeters`, `analysisLevel`, `supportedIndices`, `displayModes`,
`defaultDisplayMode` (FCC for ResourceSat), `refreshPolicy`, `limitations`, `maskMethod`,
`attribution`.

### `/api/sources/{sourceId}/dates`
- Return available **composite** dates from STAC (anchor dates), newest first.
- Add composite-specific fields to the current date payload: coverage %, usable %, cloud-masked %,
  `metricsProvisional`, period start/end, contributing scene count. SAR uses SAR-safe nulls for
  optical metrics.
- Timeline consumes this filtered to the last 3 months.

### `/api/layers/default`
- Default to the latest cloud-free composite for the source; same-origin FCC tile template.

### `/api/tiles/{sourceId}/{acquisitionDate}/{displayMode}/{z}/{x}/{y}.png`
- Support `FCC` (ResourceSat default), keep `RGB` (Sentinel coexistence) and `VV_GRAYSCALE` (SAR).
- `acquisitionDate` resolves to the composite COG for composite sources.
- FCC tile URLs are built from source role metadata and source display-rescale defaults; do not
  reuse Sentinel true-colour `[1,8,9]` or Sentinel raw-DN rescale values for ResourceSat.

### `/api/indices/statistics`
- Validate the index against source spectral-role support; return `UNSUPPORTED_INDEX` otherwise.
- `acquisitionDate` resolves to the dated composite; stats are computed on the merged analytic+mask
  COG (cloud-free).
- Response uses source-neutral fields: `pixelCounts.maskedPixels`, `metadata.maskMethod`,
  `metadata.nativeExcludedMaskClasses`, `cloudMaskedPercent`, plus `metricsProvisional` and warnings.

### Frontend
- ArcGIS basemap globally; ISRO FCC composite overlay only where coverage exists; required
  attribution rendered.
- Index availability from `/api/sources`; NDWI secondary/non-default; NDRE/RECI hidden for
  ResourceSat/SAR/Cartosat.
- Timeline of last-3-months composite dates; select a date → cloud-free stats for a drawn plot.
- Stale/missing/processing states shown; never call Bhoonidhi/MinIO/STAC/TiTiler directly.

## 11. Test Plan

### Unit tests
- Spectral-role mapping for ResourceSat bands.
- NDVI, NDMI, NDWI (ND) and **MSAVI** (non-ND) formulas.
- MSAVI radicand handling and `formula_kind` dispatch (prove normalized-difference behavior did not regress).
- NDRE/RECI unsupported without `RED_EDGE`.
- Source registry payloads; FCC display-mode resolution from roles.
- Source-neutral field names (`maskedPixels`, `maskMethod`, `nativeExcludedMaskClasses`) and
  `excluded_mask_classes`, including `cloud_mask.py`, field analytics/export, and frontend type fixtures.
- §7.5 mask encoding (exclude {0,2,3}; keep {1,4}).
- Bhoonidhi token reuse/refresh and rate-limit/backoff behavior.
- AOI bbox + 60 km polygon loading from `AOI_CONFIG_PATH`.
- ResourceSat scene identity parsing and STAC collection/item construction.

### COG / composite tests
- ResourceSat analytic COG: expected band count/order, scale `0.0001`, offset from `BAND_META.txt`,
  background/all-band-gap behavior, and recorded pixel size matching the source registry/composite
  grid policy.
- ResourceSat generated mask: code `0` from all-band background or warp gaps, code `1` valid, codes
  `2/3` from provisional cloud/shadow thresholds, code `4` water kept by default, and
  `maskMethod`/`metricsProvisional` populated.
- Mask COG aligns with analytic COG; nearest-neighbour resampling for the categorical mask.
- COGs have overviews and valid CRS (UTM 43N).
- **Composite:** full-AOI coverage above threshold; valid-first + recency selection; per-pixel
  selection correctness on synthetic overlapping scenes; all-invalid fallback; deterministic grid;
  dated item period/provenance/metrics.
- STAC item bbox/geometry matches the processed raster.

### API tests
- `/api/config` returns the Bangalore 60 km AOI.
- `/api/sources` lists ISRO sources, FCC default, source-specific indices.
- `/api/sources/{id}/dates` returns dated composites with coverage/provisional metrics.
- `/api/layers/default` returns ResourceSat after the default switch.
- `/api/tiles/.../FCC/...` uses ResourceSat role positions/rescale and same-origin URLs.
- `/api/indices/statistics` computes NDVI/MSAVI/NDMI/NDWI for ResourceSat and rejects NDRE/RECI.
- SAR sources reject optical indices.
- Browser-facing tile URLs remain same-origin.

### Integration smoke tests
- Authenticate to Bhoonidhi from the staging VM (egress `20.219.3.35`).
- Search the 60 km AOI; download `Online=Y` LISS-3 BOA products; confirm the product layout matches
  §2.2 or record any variant before ingestion.
- Build the full-AOI cloud-free composite (analytic + mask COG).
- Upload to MinIO; register the dated composite item.
- Query composite dates; render an FCC tile covering the whole AOI.
- Draw polygons across the AOI; compute cloud-free NDVI/MSAVI/NDMI/NDWI.

### Production acceptance checks
- ArcGIS basemap renders globally; ISRO FCC composite covers the full 60 km AOI with attribution.
- Latest cloud-free composite date appears; timeline lists 3 months of dates.
- Drawn-plot analytics work for supported indices; unsupported indices hidden/rejected.
- No browser request exposes internal URLs or credentials.
- Re-running ingestion does not duplicate scenes/composites.

## 12. Operational Notes

Ingestion host — **Akasha staging VM** (`akasha-staging`, `rg-akasha-selfhosted`, centralindia):

- Whitelisted egress IP `20.219.3.35` (Standard static, no NAT gateway → egress == instance IP).
  It is the only system permitted to call the Bhoonidhi API unless more IPs are whitelisted.
- `Standard_D4s_v4`; 512 GiB Premium disk at `/srv/akasha` (~478 GiB free). Bind-mount ingestion
  raw downloads + COG/composite temp to `/srv/akasha`. **Do not** let raw/temp land on `/`
  (Docker data-root is on the 30 GiB OS disk, ~15 GiB free).
- The full Akasha stack already runs here (Coolify), so the worker reaches MinIO/STAC/PostGIS
  locally.

Rate limits (confirmed against the SIS, §2.1): reuse the 20-min access token (never fetch per
request — auth is capped at 20/hr); ≤3 search/s; ≤3 concurrent downloads; back off on `412`
(concurrency) / `429`; retry interrupted downloads (`504`) after a wait, not immediately. Handle auth
`403` "max sessions active" by reusing a live session or calling `/auth/logout`. A **daily download
limit** also applies: once hit, throttled to 1 concurrent download + reduced bandwidth — so the
~90-day backfill (P3-003) is spread across days, not run in one burst.

Retention: delete raw ZIPs after successful COG/composite validation unless audit retention is on;
COGs (composites) + STAC items are the durable assets; keep enough recent composites for the
3-month timeline and crop-season comparison.

Monitoring: latest successful/available composite date per source; Bhoonidhi auth/search/download
failures; conversion/composite failures; MinIO usage; STAC registration failures; stale latest
composite date.

## 13. Assumptions and External Gates

Confirmed by the published Bhoonidhi SIS (§2.1), no longer open risks:

- The auth/search/download **access contract** (endpoints, token model, `Online=Y` filter, STAC
  search, error codes) is verified.
- `ResourceSat-2A_LISS3_BOA` (and the AWiFS/LISS-4/EOS/NISAR collections) exist in the catalog with
  the exact IDs in §6.
- Cartosat-3 is **absent** from the API catalog — confirms it stays a gated/manual path (§Phase 7).
- Real ResourceSat-2A LISS-3 BOA product access from staging is verified (§2.2): auth/search/download
  worked from egress `20.219.3.35`; the inspected product contained the expected four band GeoTIFFs
  plus `BAND_META.txt`; no obvious native quality/cloud/shadow/mask raster was present.

Still assumptions / external gates:

- Bhoonidhi credentials and staging-VM static-IP (`20.219.3.35`) access remain valid; egress stays
  pinned to that IP.
- ResourceSat-2A LISS-3 BOA `Online=Y` products are available for the 60 km AOI with enough
  temporal density to build a full-coverage cloud-free composite per window. (Density is a data
  reality, not guaranteed by the spec; validate during P0/P2b.)
- Additional ResourceSat samples should be inspected during P2a/P3 to confirm the same no-quality-layer
  layout across dates/path-row variants. This is now a confidence-building check, not a blocker for
  P2a, because the v1 path uses an Akasha-generated provisional mask.
- `BAND_META.txt` field semantics must be parsed and recorded in P2a before COG writing finalizes
  scale, valid range, background/no-data handling, path/row, and acquisition metadata.
- Redistribution/serving rights are approved (Q2); attribution text is applied as required.
- NISAR readiness depends on routine Bhoonidhi S-SAR GCOV availability and format validation.
- Sentinel removal occurs only after the Phase 2b ResourceSat smoke test succeeds.

## 14. Recommended Implementation Order

1. **Phase 0** — AOI config + Bhoonidhi staging-VM validation (+ real product layout diagnostic;
  first sample confirms no native quality layer and requires Akasha mask fallback).
2. **Phase 1** — source-aware BFF, role-based indices, MSAVI, FCC, source-neutral mask/fields.
3. **Phase 2a** — ResourceSat single-scene pipeline proof.
4. **Phase 2b** — full 60 km cloud-free composite (launch coverage).
5. **Phase 3** — scheduled static-IP sync + composite refresh + 90-day backfill.
6. **Phase 4** — UI source/index/AOI behavior, FCC overlay, attribution, 3-month timeline.
7. **Phase 8a (partial)** — switch production default to ResourceSat and remove Sentinel (after the
   Phase 2b smoke test).
8. **Phase 5** — AWiFS, LISS-4, EOS-06, IRS-1C as applicable.
9. **Phase 6** — EOS-04 and NISAR SAR layers.
10. **Phase 7** — Cartosat-3 after access/order workflow confirmation.
11. **Phase 8b (remaining)** — multi-AOI compositing, statistics hardening, monitoring.
