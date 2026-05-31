#!/usr/bin/env python3
"""Akasha Slice 2 (Phase 2 — raster de-risk) static + synthetic validator.

No Docker / MinIO / TiTiler required. This script statically validates the
Phase 2 artifacts (scene/catalog metadata, BFF raster package, deps, infra)
AND genuinely de-risks the index math:

  * pure-numpy NDVI reference (offset/scale + SCL masking + pixel accounting)
  * in-process FastAPI TestClient contract checks for the product endpoints
  * (if rasterio is importable) a full synthetic dual-COG read -> mask -> stat
    pipeline proving NDVI end-to-end without the real 2.24 GiB scene

Runtime checks that DO require operator COGs in MinIO + a running TiTiler
(real RGB tile PNG, real masked NDVI vs a QGIS/notebook reference) are listed
at the end as BLOCKED and must be validated on Railway / local Docker.

Usage:  python scripts/validate_slice2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "services" / "ingestion"))

passed = failed = 0


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def check(cond: bool, label: str) -> None:
    global passed, failed
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def read(path: str) -> str:
    return (REPO / path).read_text()


print("=" * 64)
print(" Akasha Slice 2 (Phase 2) — raster de-risk validation")
print("=" * 64)

# ---------------------------------------------------------------- scene
section("Scene identity (real 2025-09-14 / 43PHP scene)")
from akasha_ingest.scene import SAMPLE_SCENE as SC  # noqa: E402

check(SC.mgrs_tile == "43PHP", f"mgrs_tile == {SC.mgrs_tile}")
check(SC.processing_baseline == "05.11", f"processing_baseline == {SC.processing_baseline}")
check(SC.acquisition_date == "2025-09-14", f"acquisition_date == {SC.acquisition_date}")
check(
    SC.scene_key == "sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11",
    f"scene_key == {SC.scene_key}",
)
check(SC.item_id == "sentinel-2-l2a_43PHP_20250914_0511", f"item_id == {SC.item_id}")
check(SC.analytic_key == "sentinel-2-l2a/2025-09-14/analytic.tif", "analytic_key layout")
check(SC.scl_key == "sentinel-2-l2a/2025-09-14/scl.tif", "scl_key layout")

# ---------------------------------------------------------------- STAC item
section("STAC sample item metadata")
item = json.loads(read("data/seed/stac/sentinel-2-l2a-sample-item.json"))
props = item["properties"]
check(item["id"] == SC.item_id, "item id matches scene")
check(props["datetime"] == "2025-09-14T05:06:49.024000Z", "datetime")
check(props["platform"] == "sentinel-2b", "platform sentinel-2b")
check(abs(props["eo:cloud_cover"] - 17.153746) < 1e-6, "eo:cloud_cover 17.153746")
check(props["proj:epsg"] == 32643, "proj:epsg 32643")
check(props["proj:shape"] == [10980, 10980], "proj:shape 10980x10980")
check(props["proj:transform"] == [10, 0, 799980, 0, -10, 1400040, 0, 0, 1], "proj:transform")
check(props["akasha:scene_key"] == SC.scene_key, "akasha:scene_key matches")
check(bool(props.get("akasha:metrics_provisional")), "metrics flagged provisional (no SCL yet)")
analytic = item["assets"]["analytic"]
scl = item["assets"]["scl"]
check(analytic["href"] == f"s3://akasha-cogs/{SC.analytic_key}", "analytic href")
check(scl["href"] == f"s3://akasha-cogs/{SC.scl_key}", "scl href")
band_names = [b["name"] for b in analytic["eo:bands"]]
check(
    band_names == ["B04", "B08", "B05", "B06", "B07", "B11", "B12", "B03", "B02"],
    "analytic eo:bands frozen 9-band order",
)
rb0 = analytic["raster:bands"][0]
check(rb0["scale"] == 0.0001 and rb0["offset"] == -0.1, "raster:bands scale 0.0001 / offset -0.1")
check(rb0["nodata"] == 0, "analytic nodata == 0")
check(len(scl["classification:classes"]) == 12, "SCL has 12 classification classes")

section("Collection extent contains the scene footprint")
coll = json.loads(read("data/seed/stac/sentinel-2-l2a-collection.json"))
cbbox = coll["extent"]["spatial"]["bbox"][0]
ibbox = item["bbox"]
contains = (
    cbbox[0] <= ibbox[0] and cbbox[1] <= ibbox[1] and cbbox[2] >= ibbox[2] and cbbox[3] >= ibbox[3]
)
check(contains, f"collection bbox {cbbox} contains item bbox")

section("Phase 2 NDVI reference polygon fixture")
poly_doc = json.loads(read("data/seed/phase2-ndvi-sample-polygon.geojson"))
poly = poly_doc["geometry"]
check(poly["type"] == "Polygon", "fixture is a Polygon")
xs = [c[0] for c in poly["coordinates"][0]]
ys = [c[1] for c in poly["coordinates"][0]]
in_fp = min(xs) >= ibbox[0] and max(xs) <= ibbox[2] and min(ys) >= ibbox[1] and max(ys) <= ibbox[3]
check(in_fp, "reference polygon lies inside the scene footprint")

# ---------------------------------------------------------------- BFF package
section("BFF raster package modules")
for mod in [
    "indices", "statistics_core", "catalog_resolver", "raster_reader",
    "tiles", "geo_validate", "errors", "models", "service",
]:
    check((REPO / "apps/api/app/raster" / f"{mod}.py").is_file(), f"app/raster/{mod}.py exists")

from app.raster import indices  # noqa: E402

check(set(indices.INDEX_REGISTRY) == {"NDVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"}, "4 supported indices")
ndvi = indices.get_index("NDVI")
check(ndvi.band_a == "B08" and ndvi.band_b == "B04", "NDVI = (B08 - B04)/(B08 + B04)")
check(indices.rgb_band_positions(indices.FROZEN_ANALYTIC_BANDS) == [1, 8, 9], "RGB positions [1,8,9]")
check(indices.DEFAULT_SCALE == 0.0001 and indices.DEFAULT_OFFSET == -0.1, "default scale/offset")
check(
    indices.DEFAULT_EXCLUDED_SCL_CLASSES == (0, 1, 2, 3, 7, 8, 9, 10, 11),
    "default excluded SCL classes (water class 6 kept)",
)

# ---------------------------------------------------------------- numeric de-risk
section("Statistics engine numeric de-risk (pure numpy)")
import numpy as np  # noqa: E402

from app.raster.statistics_core import compute_index_statistics  # noqa: E402

nir = np.full((3, 3), 4000, dtype="uint16")
red = np.full((3, 3), 2000, dtype="uint16")
sclv = np.full((3, 3), 4, dtype="uint8")
geom = np.ones((3, 3), dtype=bool)
sclv[0, 0] = 9
red[0, 1] = 0
geom[0, 2] = False
s = compute_index_statistics(
    index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=sclv, geometry_mask=geom,
    scale=0.0001, offset=-0.1, nodata=0,
).as_dict()
check(s["mean"] == 0.5, f"NDVI mean == 0.5 (offset applied) [{s['mean']}]")
check(s["totalPixels"] == 8 and s["validPixels"] == 6, "pixel accounting total=8 valid=6")
check(s["nodataPixels"] == 1 and s["sclExcludedPixels"] == 1, "nodata=1 sclExcluded=1")
check(s["validPixelPercent"] == 75.0, "validPixelPercent == 75.0")
no_off = compute_index_statistics(
    index_type="NDVI", band_a_dn=nir, band_b_dn=red, scl=sclv, geometry_mask=geom,
    scale=0.0001, offset=0.0, nodata=0,
).mean
check(abs(0.5 - no_off) > 0.1, f"offset materially changes NDVI (no-offset={round(no_off,4)})")

# ---------------------------------------------------------------- endpoints
section("Product endpoints (in-process TestClient)")
try:
    from fastapi.testclient import TestClient

    from app.main import app

    tc = TestClient(app)
    cfg = tc.get("/api/config")
    check(cfg.status_code == 200, "GET /api/config -> 200")
    check(cfg.json()["supportedIndices"] == indices.SUPPORTED_INDICES, "config supportedIndices")
    check(cfg.json()["defaultIndex"] == "NDVI", "config defaultIndex NDVI")
    src = tc.get("/api/sources")
    check(src.status_code == 200 and src.json()[0]["id"] == "sentinel-2-l2a", "GET /api/sources")
    dts = tc.get("/api/sources/sentinel-2-l2a/dates")
    check(
        dts.status_code == 200 and any(d["acquisitionDate"] == "2025-09-14" for d in dts.json()),
        "GET dates contains 2025-09-14",
    )
    lay = tc.get("/api/layers/default")
    check(
        lay.status_code == 200
        and lay.json()["tileUrlTemplate"]
        == "/api/tiles/sentinel-2-l2a/2025-09-14/rgb/{z}/{x}/{y}.png",
        "GET /api/layers/default tile template (same-origin /api route)",
    )
    bad = tc.post(
        "/api/indices/statistics",
        json={"geometry": {"type": "Point", "coordinates": [78.2, 12.1]}, "indexType": "NDVI"},
    )
    check(
        bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_GEOMETRY",
        "POST statistics invalid geometry -> 422 INVALID_GEOMETRY",
    )
    nope = tc.post(
        "/api/indices/statistics",
        json={"geometry": poly, "indexType": "NOPE"},
    )
    check(
        nope.status_code == 400 and nope.json()["error"]["code"] == "UNSUPPORTED_INDEX",
        "POST statistics unsupported index -> 400 UNSUPPORTED_INDEX",
    )
except Exception as exc:  # noqa: BLE001
    check(False, f"TestClient endpoint checks raised: {exc}")

# ---------------------------------------------------------------- tile url
section("TiTiler RGB tile URL builder")
from app.raster.tiles import build_rgb_tile_url  # noqa: E402

url = build_rgb_tile_url(
    analytic_href="s3://akasha-cogs/sentinel-2-l2a/2025-09-14/analytic.tif",
    rgb_positions=[1, 8, 9], z=12, x=2937, y=1881, titiler_url="http://titiler:8000",
)
check("/cog/tiles/WebMercatorQuad/12/2937/1881.png" in url, "TiTiler 1.0 COG tile route")
check(url.count("bidx=1") == 1 and "bidx=8" in url and "bidx=9" in url, "bidx for RGB [1,8,9]")
check("rescale=" in url and "url=" in url, "rescale + url query params present")

# ---------------------------------------------------------------- deps & infra
section("Dependencies & infrastructure")
reqs = read("apps/api/requirements.txt")
for dep in ["rasterio", "rio-tiler", "shapely", "pyproj", "numpy"]:
    check(dep in reqs, f"apps/api/requirements.txt declares {dep}")
check("libexpat1" in read("apps/api/Dockerfile"), "api Dockerfile installs libexpat1 (GDAL runtime)")
compose = read("infra/docker/docker-compose.yml")
check('PORT: "8000"' in compose, "docker-compose titiler PORT=8000 (image defaults to 80 otherwise)")
check("AWS_ACCESS_KEY_ID:" in compose, "docker-compose api has AWS_ACCESS_KEY_ID")
check("AWS_S3_ENDPOINT:" in compose, "docker-compose api has AWS_S3_ENDPOINT")
check("GDAL_DISABLE_READDIR_ON_OPEN:" in compose, "docker-compose api has GDAL_DISABLE_READDIR_ON_OPEN")
check("PORT=8000" in read("services/titiler/.env.example"), "titiler .env.example PORT=8000")
api_env = read("apps/api/.env.example")
check("AWS_ACCESS_KEY_ID=" in api_env and "AKASHA_RGB_RESCALE=" in api_env, "api .env.example S3/RGB vars")
check("AWS_S3_ENDPOINT" in read("infra/railway/ENV_MATRIX.md"), "ENV_MATRIX api S3 vars")

# ---------------------------------------------------------------- storage Phase 2
section("Storage / ingestion Phase 2 helpers")
from akasha_ingest import storage, verify  # noqa: E402

check(hasattr(storage, "verify_real_cogs"), "storage.verify_real_cogs exists")
check(hasattr(storage, "object_status"), "storage.object_status exists")
check(hasattr(verify, "run_phase2"), "verify.run_phase2 exists")
worker_src = read("services/ingestion/worker.py")
check("verify-cogs" in worker_src, "worker.py exposes verify-cogs command")
storage_src = read("services/ingestion/akasha_ingest/storage.py")
check('"akasha-placeholder": "false"' in storage_src, "seed_keys tags real uploads (placeholder=false)")

# ---------------------------------------------------------------- synthetic E2E
section("Synthetic dual-COG E2E (rasterio)")
try:
    import rasterio  # noqa: F401
    from pyproj import Transformer
    from rasterio.transform import from_origin

    from app.raster import catalog_resolver as catalog
    from app.raster.service import compute_statistics

    import tempfile

    tmp = Path(tempfile.mkdtemp())
    crs = "EPSG:32643"
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    pr = [tf.transform(x, y) for x, y in poly["coordinates"][0]]
    minx = min(p[0] for p in pr) - 100
    maxx = max(p[0] for p in pr) + 100
    miny = min(p[1] for p in pr) - 100
    maxy = max(p[1] for p in pr) + 100
    w = int((maxx - minx) / 10)
    h = int((maxy - miny) / 10)
    transform = from_origin(minx, maxy, 10, 10)
    analytic_arr = np.zeros((9, h, w), dtype="uint16")
    analytic_arr[0, :, :] = 2000
    analytic_arr[1, :, :] = 4000
    scl_arr = np.full((h, w), 4, dtype="uint8")
    a_path = tmp / "analytic.tif"
    s_path = tmp / "scl.tif"
    prof = dict(driver="GTiff", width=w, height=h, count=9, dtype="uint16",
                crs=crs, transform=transform, nodata=0)
    with rasterio.open(a_path, "w", **prof) as dst:
        dst.write(analytic_arr)
    with rasterio.open(s_path, "w", **dict(prof, count=1, dtype="uint8")) as dst:
        dst.write(scl_arr, 1)
    catalog.resolve_assets = lambda source_id, acquisition_date: {
        "itemId": "synthetic", "analyticHref": str(a_path), "sclHref": str(s_path),
        "bandNames": indices.FROZEN_ANALYTIC_BANDS, "scale": 0.0001, "offset": -0.1,
        "nodata": 0, "epsg": 32643, "bbox": None,
    }
    catalog.supported_indices = lambda source_id="sentinel-2-l2a": list(indices.SUPPORTED_INDICES)
    resp = compute_statistics(
        geometry=poly, source_id="sentinel-2-l2a", acquisition_date="2025-09-14",
        index_type="NDVI", max_area_ha=50, max_vertices=5000,
    )
    check(abs(resp["statistics"]["mean"] - 0.5) < 1e-6, f"synthetic E2E NDVI mean 0.5 [{resp['statistics']['mean']}]")
    check(resp["pixelCounts"]["validPixels"] > 0, "synthetic E2E has valid pixels")
    check(resp["statistics"]["validPixelPercent"] == 100.0, "synthetic E2E validPixelPercent 100")
except ImportError:
    print("  [SKIP] rasterio/pyproj not installed in this environment (E2E covered on Railway).")

# ---------------------------------------------------------------- blocked
section("BLOCKED until operator COGs are in MinIO (Railway / local Docker)")
print("  [BLOCKED] Real RGB PNG tile rendered by TiTiler through the gateway.")
print("  [BLOCKED] Real cloud-masked NDVI statistic for the reference polygon,")
print("            compared against a QGIS/notebook reference (data-ingestion rules).")
print("  -> Upload analytic.tif + scl.tif to s3://akasha-cogs/sentinel-2-l2a/2025-09-14/")
print("     then run: python services/ingestion/worker.py verify-cogs")

print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)
if failed:
    print("Slice 2 validation FAILED.")
    sys.exit(1)
print("Slice 2 (Phase 2) validation PASSED — raster de-risk artifacts are Railway-ready.")
sys.exit(0)
