#!/usr/bin/env python3
"""Akasha Slice 2 raster de-risk static + synthetic validator.

No Docker / MinIO / TiTiler required. This script validates the ResourceSat
LISS-3 catalog contract, BFF raster package, deps/infra, source-aware index
math, in-process product endpoints, and a synthetic dual-COG read-to-stat
pipeline when rasterio is installed.

Runtime checks that require operator COGs in MinIO plus a running TiTiler are
listed at the end as blocked and must be validated on staging or local Docker.

Usage:  python scripts/validate_slice2.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "services" / "ingestion"))

SOURCE_ID = "resourcesat-2a-liss3-boa"
AOI_ID = "bangalore-60km"
BANDS = ["BAND2", "BAND3", "BAND4", "BAND5"]
BAND_ROLE_MAPPING = {
    "GREEN": "BAND2",
    "RED": "BAND3",
    "NIR": "BAND4",
    "SWIR1": "BAND5",
}
SUPPORTED_RESOURCE_INDICES = ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
EXCLUDED_MASK_CLASSES = [0, 2, 3]
VALID_MASK_CLASS = 1
SCALE = 0.0001
OFFSET = 0.0
SAMPLE_DATE = "2026-03-19"
ITEM_ID = f"{SOURCE_ID}_{AOI_ID}_{SAMPLE_DATE}_composite"
ANALYTIC_HREF = f"s3://akasha-cogs/{SOURCE_ID}/composite/{AOI_ID}/{SAMPLE_DATE}/analytic.tif"
MASK_HREF = f"s3://akasha-cogs/{SOURCE_ID}/composite/{AOI_ID}/{SAMPLE_DATE}/mask.tif"

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
print(" Akasha Slice 2 - raster de-risk validation")
print("=" * 64)

# ---------------------------------------------------------------- STAC item
section("ResourceSat sample composite metadata")
item = json.loads(read("data/seed/stac/resourcesat-2a-liss3-boa-sample-item.json"))
props = item["properties"]
check(item["id"] == ITEM_ID, "item id matches ResourceSat sample composite")
check(item["collection"] == SOURCE_ID, f"item collection == {SOURCE_ID}")
check(props["datetime"] == f"{SAMPLE_DATE}T00:00:00Z", "datetime")
check(props["platform"] == "resourcesat-2a", "platform resourcesat-2a")
check(props["akasha:aoi_id"] == AOI_ID, f"AOI id == {AOI_ID}")
check(props["akasha:item_kind"] == "composite", "item kind == composite")
check(bool(props["akasha:composite"]), "item marked composite")
check(props.get("akasha:composite_grid_crs") == "EPSG:32643", "item composite grid CRS EPSG:32643")
check(props.get("akasha:composite_resolution_meters") == 24, "item composite resolution 24m")
check(props["proj:epsg"] == 32643, "proj:epsg 32643")
check(bool(props.get("akasha:metrics_provisional")), "metrics flagged provisional")
analytic = item["assets"]["analytic"]
mask = item["assets"]["mask"]
check(analytic["href"] == ANALYTIC_HREF, "analytic href")
check(mask["href"] == MASK_HREF, "mask href")
band_names = [b["name"] for b in analytic["eo:bands"]]
check(band_names == BANDS, "analytic eo:bands ResourceSat 4-band order")
rb0 = analytic["raster:bands"][0]
check(rb0["scale"] == SCALE and rb0["offset"] == OFFSET, "raster:bands scale 0.0001 / offset 0")
check(len(analytic["raster:bands"]) == 4, "analytic has 4 raster bands")
mask_classes = [c["value"] for c in mask["classification:classes"]]
check(mask_classes == [0, 1, 2, 3, 4], "provisional mask classes 0..4")

section("Collection extent contains the sample composite")
coll = json.loads(read("data/seed/stac/resourcesat-2a-liss3-boa-collection.json"))
cbbox = coll["extent"]["spatial"]["bbox"][0]
ibbox = item["bbox"]
contains = (
    cbbox[0] <= ibbox[0] and cbbox[1] <= ibbox[1] and cbbox[2] >= ibbox[2] and cbbox[3] >= ibbox[3]
)
check(contains, f"collection bbox {cbbox} contains item bbox")
check(coll["akasha:source_kind"] == "optical", "collection source kind optical")
check(
    coll["akasha:supported_indices"] == SUPPORTED_RESOURCE_INDICES,
    "ResourceSat supported indices",
)
check(
    coll["akasha:unsupported_indices"] == ["NDRE", "RECI"],
    "ResourceSat red-edge indices unsupported",
)
check(coll["akasha:default_display_mode"] == "FCC", "ResourceSat default display mode FCC")
check(coll["akasha:fcc_role_order"] == ["NIR", "RED", "GREEN"], "FCC role order NIR/RED/GREEN")
check(coll["akasha:band_role_mapping"] == BAND_ROLE_MAPPING, "collection band-role mapping")
check(
    coll["akasha:default_excluded_mask_classes"] == EXCLUDED_MASK_CLASSES,
    "excluded mask classes",
)
reflectance = coll["akasha:reflectance"]
check(
    reflectance["scale"] == SCALE and reflectance["offset"] == OFFSET,
    "ResourceSat reflectance scale/offset",
)

section("Sample plot lies inside ResourceSat AOI")
plot_doc = json.loads(read("data/seed/sample-plot.geojson"))
poly = plot_doc["geometry"]
check(poly["type"] == "Polygon", "fixture is a Polygon")
xs = [c[0] for c in poly["coordinates"][0]]
ys = [c[1] for c in poly["coordinates"][0]]
in_fp = min(xs) >= ibbox[0] and max(xs) <= ibbox[2] and min(ys) >= ibbox[1] and max(ys) <= ibbox[3]
check(in_fp, "sample plot lies inside the ResourceSat composite footprint")
stat_poly = {
    "type": "Polygon",
    "coordinates": [
        [
            [77.585, 12.965],
            [77.587, 12.965],
            [77.587, 12.967],
            [77.585, 12.967],
            [77.585, 12.965],
        ]
    ],
}

# ---------------------------------------------------------------- BFF package
section("BFF raster package modules")
for mod in [
    "indices",
    "statistics_core",
    "catalog_resolver",
    "raster_reader",
    "tiles",
    "geo_validate",
    "errors",
    "models",
    "service",
]:
    check((REPO / "apps/api/app/raster" / f"{mod}.py").is_file(), f"app/raster/{mod}.py exists")

from app.raster import indices  # noqa: E402

core_indices = {"NDVI", "MSAVI", "NDRE", "NDMI", "NDWI_GREEN_NIR"}
check(core_indices.issubset(indices.INDEX_REGISTRY), "core index registry remains available")
ndvi = indices.get_index("NDVI")
check(ndvi.required_roles == ("NIR", "RED"), "NDVI = (NIR - RED)/(NIR + RED)")
check(indices.get_index("MSAVI").formula_kind == "msavi", "MSAVI formula registered")
check(
    indices.fcc_band_positions(BANDS, BAND_ROLE_MAPPING) == [3, 2, 1],
    "ResourceSat FCC positions [3,2,1]",
)

# ---------------------------------------------------------------- numeric de-risk
section("Statistics engine numeric de-risk (pure numpy)")
import numpy as np  # noqa: E402,I001

from app.raster.statistics_core import compute_index_statistics  # noqa: E402

nir = np.full((3, 3), 4000, dtype="uint16")
red = np.full((3, 3), 2000, dtype="uint16")
maskv = np.full((3, 3), VALID_MASK_CLASS, dtype="uint8")
geom = np.ones((3, 3), dtype=bool)
maskv[0, 0] = 2
red[0, 1] = 0
geom[0, 2] = False
s = compute_index_statistics(
    index_type="NDVI",
    band_a_dn=nir,
    band_b_dn=red,
    mask=maskv,
    geometry_mask=geom,
    scale=SCALE,
    offset=OFFSET,
    nodata=0,
    excluded_mask_classes=tuple(EXCLUDED_MASK_CLASSES),
).as_dict()
check(
    round(s["mean"], 6) == 0.333333,
    f"NDVI mean == 0.333333 (ResourceSat offset 0) [{s['mean']}]",
)
check(s["totalPixels"] == 8 and s["validPixels"] == 6, "pixel accounting total=8 valid=6")
check(s["nodataPixels"] == 1 and s["maskedPixels"] == 1, "nodata=1 masked=1")
check(s["validPixelPercent"] == 75.0, "validPixelPercent == 75.0")

# ---------------------------------------------------------------- endpoints
section("Product endpoints (in-process TestClient)")
try:
    from fastapi.testclient import TestClient  # noqa: I001

    from app.config import settings
    from app.main import app

    settings.auth_mode = "disabled"
    settings.auth_allow_disabled = True
    settings.app_env = "test"

    tc = TestClient(app)
    cfg = tc.get("/api/config")
    check(cfg.status_code == 200, "GET /api/config -> 200")
    cfg_body = cfg.json()
    check(cfg_body["defaultIndex"] == "NDVI", "config defaultIndex NDVI")
    check(
        any(aoi.get("id") == AOI_ID for aoi in cfg_body.get("aois", [])),
        "config lists configured AOIs",
    )
    src = tc.get("/api/sources")
    body = src.json()
    check(src.status_code == 200 and body[0]["id"] == SOURCE_ID, "GET /api/sources")
    check("sentinel-2-l2a" not in {source["id"] for source in body}, "Sentinel-2 hidden by default")
    check(body[0]["defaultDisplayMode"] == "FCC", "ResourceSat source defaultDisplayMode FCC")
    check("NDRE" not in body[0]["supportedIndices"], "ResourceSat source hides unsupported NDRE")
    dts = tc.get(f"/api/sources/{SOURCE_ID}/dates")
    check(
        dts.status_code == 200 and any(d["acquisitionDate"] == SAMPLE_DATE for d in dts.json()),
        f"GET dates contains {SAMPLE_DATE}",
    )
    lay = tc.get("/api/layers/default")
    check(
        lay.status_code == 200
        and lay.json()["tileUrlTemplate"]
        == f"/api/tiles/{SOURCE_ID}/{SAMPLE_DATE}/FCC/{{z}}/{{x}}/{{y}}.png",
        "GET /api/layers/default tile template (same-origin /api route)",
    )
    bad = tc.post(
        "/api/indices/statistics",
        json={"geometry": {"type": "Point", "coordinates": [77.58, 12.96]}, "indexType": "NDVI"},
    )
    check(
        bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_GEOMETRY",
        "POST statistics invalid geometry -> 422 INVALID_GEOMETRY",
    )
    nope = tc.post(
        "/api/indices/statistics",
        json={"geometry": stat_poly, "indexType": "NDRE"},
    )
    check(
        nope.status_code == 400 and nope.json()["error"]["code"] == "UNSUPPORTED_INDEX",
        "POST ResourceSat unsupported NDRE -> 400 UNSUPPORTED_INDEX",
    )
    openapi = tc.get("/api/openapi.json").json()
    stats_meta = openapi["components"]["schemas"]["StatisticsMetadata"]["properties"]
    check("maskMethod" in stats_meta, "OpenAPI documents statistics metadata maskMethod")
    check(
        "nativeExcludedMaskClasses" in stats_meta,
        "OpenAPI documents nativeExcludedMaskClasses",
    )
    check("metricsProvisional" in stats_meta, "OpenAPI documents metricsProvisional")
except Exception as exc:  # noqa: BLE001
    check(False, f"TestClient endpoint checks raised: {exc}")

# ---------------------------------------------------------------- tile url
section("TiTiler FCC tile URL builder")
from app.raster.tiles import build_rgb_tile_url  # noqa: E402

url = build_rgb_tile_url(
    analytic_href=ANALYTIC_HREF,
    rgb_positions=[3, 2, 1],
    z=12,
    x=2937,
    y=1909,
    titiler_url="http://titiler:8000",
)
check("/cog/tiles/WebMercatorQuad/12/2937/1909.png" in url, "TiTiler 1.0 COG tile route")
check(url.count("bidx=3") == 1 and "bidx=2" in url and "bidx=1" in url, "bidx for FCC [3,2,1]")
check(
    "bidx=8" not in url and "bidx=9" not in url,
    "ResourceSat FCC does not use Sentinel RGB bands",
)
check("rescale=" in url and "url=" in url, "rescale + url query params present")

# ---------------------------------------------------------------- deps & infra
section("Dependencies & infrastructure")
reqs = read("apps/api/requirements.txt")
for dep in ["rasterio", "rio-tiler", "shapely", "pyproj", "numpy"]:
    check(dep in reqs, f"apps/api/requirements.txt declares {dep}")
check(
    "libexpat1" in read("apps/api/Dockerfile"),
    "api Dockerfile installs libexpat1 (GDAL runtime)",
)
compose = read("infra/docker/docker-compose.yml")
check('PORT: "8000"' in compose, "docker-compose titiler PORT=8000")
check("AWS_ACCESS_KEY_ID:" in compose, "docker-compose api has AWS_ACCESS_KEY_ID")
check("AWS_S3_ENDPOINT:" in compose, "docker-compose api has AWS_S3_ENDPOINT")
check(
    "GDAL_DISABLE_READDIR_ON_OPEN:" in compose,
    "docker-compose api has GDAL_DISABLE_READDIR_ON_OPEN",
)
check("PORT=8000" in read("services/titiler/.env.example"), "titiler .env.example PORT=8000")
api_env = read("apps/api/.env.example")
check(
    "DEFAULT_SOURCE_ID=resourcesat-2a-liss3-boa" in api_env,
    "api .env.example ResourceSat default",
)
check("AKASHA_RGB_RESCALE=" in api_env, "api .env.example display rescale vars")
selfhosted_env = read("infra/selfhosted/env.example")
selfhosted_compose = read("infra/selfhosted/coolify-compose.yml")
check(
    "AWS_REGION=" in selfhosted_env and "AKASHA_COG_BUCKET=" in selfhosted_env,
    "self-hosted env S3 bucket settings",
)
check(
    "AWS_S3_ENDPOINT:" in selfhosted_compose and "AKASHA_COG_BUCKET:" in selfhosted_compose,
    "self-hosted compose wires S3 bucket vars",
)

# ---------------------------------------------------------------- storage Phase 2
section("Storage / ingestion Phase 2 helpers")
from akasha_ingest import storage, verify  # noqa: E402

check(hasattr(storage, "verify_real_cogs"), "storage.verify_real_cogs exists")
check(hasattr(storage, "object_status"), "storage.object_status exists")
check(hasattr(verify, "run_phase2"), "verify.run_phase2 exists")
worker_src = read("services/ingestion/worker.py")
check("verify-cogs" in worker_src, "worker.py exposes verify-cogs command")
storage_src = read("services/ingestion/akasha_ingest/storage.py")
check(
    '"akasha-placeholder": "false"' in storage_src,
    "seed_keys tags real uploads (placeholder=false)",
)

# ---------------------------------------------------------------- synthetic E2E
section("Synthetic ResourceSat dual-COG E2E (rasterio)")
try:
    import rasterio  # noqa: F401,I001
    from pyproj import Transformer
    from rasterio.transform import from_origin

    from app.raster import catalog_resolver as catalog
    from app.raster.service import compute_statistics

    tmp = Path(tempfile.mkdtemp())
    crs = "EPSG:32643"
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    pr = [tf.transform(x, y) for x, y in stat_poly["coordinates"][0]]
    minx = min(p[0] for p in pr) - 100
    maxx = max(p[0] for p in pr) + 100
    miny = min(p[1] for p in pr) - 100
    maxy = max(p[1] for p in pr) + 100
    w = int((maxx - minx) / 24)
    h = int((maxy - miny) / 24)
    transform = from_origin(minx, maxy, 24, 24)
    analytic_arr = np.zeros((4, h, w), dtype="uint16")
    analytic_arr[1, :, :] = 2000
    analytic_arr[2, :, :] = 4000
    mask_arr = np.full((h, w), VALID_MASK_CLASS, dtype="uint8")
    a_path = tmp / "analytic.tif"
    m_path = tmp / "mask.tif"
    prof = dict(
        driver="GTiff",
        width=w,
        height=h,
        count=4,
        dtype="uint16",
        crs=crs,
        transform=transform,
        nodata=0,
    )
    with rasterio.open(a_path, "w", **prof) as dst:
        dst.write(analytic_arr)
    with rasterio.open(m_path, "w", **dict(prof, count=1, dtype="uint8")) as dst:
        dst.write(mask_arr, 1)
    synthetic_assets = {
        "itemId": "synthetic-resourcesat",
        "analyticHref": str(a_path),
        "sclHref": str(m_path),
        "maskHref": str(m_path),
        "maskAsset": "mask",
        "bandNames": BANDS,
        "scale": SCALE,
        "offset": OFFSET,
        "bandRoleMapping": BAND_ROLE_MAPPING,
        "excludedMaskClasses": EXCLUDED_MASK_CLASSES,
        "nodata": 0,
        "epsg": 32643,
        "bbox": None,
    }
    catalog.resolve_assets = lambda source_id, acquisition_date: synthetic_assets
    catalog.resolve_assets_for_date = lambda source_id, acquisition_date: [synthetic_assets]
    catalog.supported_indices = lambda source_id=SOURCE_ID: SUPPORTED_RESOURCE_INDICES
    resp = compute_statistics(
        geometry=stat_poly,
        source_id=SOURCE_ID,
        acquisition_date=SAMPLE_DATE,
        index_type="NDVI",
        max_area_ha=50,
        max_vertices=5000,
    )
    check(
        abs(resp["statistics"]["mean"] - 0.333333) < 1e-6,
        f"synthetic E2E NDVI mean 0.333333 [{resp['statistics']['mean']}]",
    )
    check(resp["pixelCounts"]["validPixels"] > 0, "synthetic E2E has valid pixels")
    check(resp["statistics"]["validPixelPercent"] == 100.0, "synthetic E2E validPixelPercent 100")
except ImportError:
    print("  [SKIP] rasterio/pyproj not installed in this environment (E2E covered on staging).")

# ---------------------------------------------------------------- blocked
section("BLOCKED until ResourceSat composite COGs are in MinIO (staging / local Docker)")
print("  [BLOCKED] Real ResourceSat FCC PNG tile rendered by TiTiler through the gateway.")
print("  [BLOCKED] Real mask-aware NDVI statistic for the reference polygon,")
print("            compared against a QGIS/notebook reference (data-ingestion rules).")
print("  -> Build/ingest the ResourceSat composite COGs, then run:")
print(
    "     python services/ingestion/worker.py verify-composite "
    "--source resourcesat-2a-liss3-boa --aoi bangalore-60km --require-catalog-item"
)

print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)
if failed:
    print("Slice 2 validation FAILED.")
    sys.exit(1)
print("Slice 2 validation PASSED - raster de-risk artifacts are deployment-ready.")
sys.exit(0)
