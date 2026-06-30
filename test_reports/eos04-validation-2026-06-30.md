# EOS-04 SAR-MRS L2B staging product validation — 2026-06-30

## Scope

One-product live validation of EOS-04 SAR-MRS L2B from the whitelisted staging VM.

- Source ID: `eos-04-sar-mrs-l2b`
- Bhoonidhi collection: `EOS-04_SAR-MRS_L2B`
- AOI: `bangalore-60km`
- Staging host: `akasha-staging`
- Validation job: `ingest-20260630T053925Z-a292779b`
- Inner scheduler job: `job_20260630T053928Z_f1b0a3e11249`
- Deployed image tag validated: `507f8ef1d92046bf316e42fdc7e2c03ff4ebe42e`

## Result

`PASS` — search, one-product download, prepare, upload, STAC load, COG verification, BFF date resolution, and BFF tile rendering all passed.

Job summary:

- `foundCount=10`
- `selectedCount=1`
- `downloadedCount=1`
- `deferredCount=9`
- `prepared=true`
- `uploaded=true`
- `stacLoaded=true`
- `verified=true`
- `ingested=true`

## Product validated

- ZIP: `E04_SAR_MRS_22JUN2026_173003537536_24023_STUC00ZTD_32682_22_DH_D_R_N12327_E078697.zip`
- Acquisition datetime: `2026-06-22T00:35:37Z`
- Inferred polarizations: `HH`, `HV`
- Input scale decision: `amplitude`
- Output CRS: `EPSG:32644`
- Output dtype: `Float32` dB
- Nodata: `-9999.0`

Prepared output:

- Asset key: `backscatter`
- Object: `s3://akasha-cogs/eos-04-sar-mrs-l2b/2026-06-22/unknown/20260622T003537Z_eos-04_MRS_EOS-04-SAR-MRS-L2B_eeb7d6ce0733/backscatter.tif`
- COG size: `1,366,884` bytes
- STAC item ID: `eos-04-sar-mrs-l2b_unknown_20260622T003537Z_eos-04_MRS_EOS-04-SAR-MRS-L2B_eeb7d6ce0733`

## Catalog/BFF verification

After ensuring the internal `stac-api` service was running, the BFF resolver returned:

- Date: `2026-06-22`
- `sceneCount=1`
- `dateMetricsKind=radar`
- `usablePixelPercent=null`
- `cloudMaskedPercent=null`
- `coveragePercent=null`
- `tileAvailable=true`
- `isLatestUsable=true`
- Bounds: `[77.73460866902437, 11.331284109434632, 79.50281669105564, 13.070336912916211]`

Resolved asset metadata:

- `backscatterHref` points to the expected MinIO object.
- `bandNames=["HH_dB", "HV_dB"]`
- `epsg=32644`
- `nodata=-9999.0`

Source exposure remains backend-only after validation:

- `availabilityStatus=gated`
- `supportedIndices=[]`
- `maskAsset=null`
- `displayModes=["VV_GRAYSCALE"]`
- No optical cloud-cover field was present on the STAC item.

## Tile smoke

BFF tile route rendered a PNG:

- Route: `/api/tiles/eos-04-sar-mrs-l2b/2026-06-22/VV_GRAYSCALE/8/183/119.png`
- Status: `200`
- Content-Type: `image/png`
- Dimensions: `256x256`
- Payload length: `334` bytes

## Operational note

During post-ingest verification, the internal `stac-api` container was not running. The API therefore fell back to seed STAC files and initially could not see the newly loaded pgSTAC item. Starting `stac-api` restored BFF catalog/date/tile visibility immediately.

Follow-up: staging deploy/reconcile procedures should include `stac-api` (and `titiler`) along with `web` and `api`, or explicitly verify all internal services after deploy.

## Decision

EOS-04 real-product pipeline is validated for a single product and should be used as backend SAR support for cloudy optical analytics. It remains manual-refresh/operator-controlled for ingestion; no direct user-selectable EOS-04 layer, optical index/statistics, or cloud-mask workflow is enabled yet.
