#!/usr/bin/env python3
"""Slice 1 artifact validator for the Akasha MVP.

Static validation (no Docker / no running services) of the storage + catalog
foundation: the PostGIS app schema, the ResourceSat LISS-3 seed STAC contract,
the AOI/plot GeoJSON seeds, deterministic object-key expectations, and the
ingestion/api tooling wiring.

Run:  python scripts/validate_slice1.py
Exit: 0 if everything passes, 1 otherwise.
"""
# ruff: noqa: E501
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SOURCE_ID = "resourcesat-2a-liss3-boa"
AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
AOI_ID = "bangalore-60km"
BANDS = ["BAND2", "BAND3", "BAND4", "BAND5"]
SUPPORTED_INDICES = ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
UNSUPPORTED_INDICES = ["NDRE", "RECI"]
FCC_ROLE_ORDER = ["NIR", "RED", "GREEN"]
EXCLUDED_MASK_CLASSES = [0, 2, 3]
MASK_CLASS_VALUES = [0, 1, 2, 3, 4]
SCALE = 0.0001
OFFSET = 0
ITEM_ID = "resourcesat-2a-liss3-boa_bangalore-60km_2026-03-19_composite"
ANALYTIC_KEY = f"{SOURCE_ID}/composite/{AOI_ID}/2026-03-19/analytic.tif"
MASK_KEY = f"{SOURCE_ID}/composite/{AOI_ID}/2026-03-19/mask.tif"
EOS06_SOURCE_ID = "eos-06-ocm-lac-ndvi-8day-360m"
IRS1C_SOURCE_ID = "irs-1c-liss3-archive"
CARTOSAT_SOURCE_ID = "cartosat-3-gated"
SAR_SOURCE_IDS = ["eos-04-sar-mrs-l2b", "nisar-ssar-beta-gcov"]

results = []


def check(ok, msg):
    results.append((bool(ok), msg))


def section(title):
    results.append((None, title))


def load_json(rel):
    p = REPO / rel
    if not p.exists():
        check(False, f"missing {rel}")
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        check(False, f"{rel} invalid JSON: {exc}")
        return None


# --------------------------------------------------------------------------
section("Seed files present + valid JSON/GeoJSON")
for rel in [
    "data/seed/bangalore-60km-aoi.geojson",
    "data/seed/sample-plot.geojson",
    "data/seed/stac/resourcesat-2a-liss3-boa-collection.json",
    "data/seed/stac/resourcesat-2a-liss3-boa-sample-item.json",
    "data/seed/stac/resourcesat-2a-awifs-boa-collection.json",
    "data/seed/stac/eos-06-ocm-lac-ndvi-8day-360m-collection.json",
    "data/seed/stac/irs-1c-liss3-archive-collection.json",
    "data/seed/stac/cartosat-3-gated-collection.json",
    "data/seed/stac/eos-04-sar-mrs-l2b-collection.json",
    "data/seed/stac/nisar-ssar-beta-gcov-collection.json",
    "data/seed/README.md",
]:
    check((REPO / rel).exists(), f"exists: {rel}")
check(
    not (REPO / "data/seed/bangalore-aoi.geojson").exists(),
    "legacy small-box bangalore-aoi.geojson removed",
)
sentinel_seed_files = sorted((REPO / "data/seed/stac").glob("sentinel-*"))
check(not sentinel_seed_files, "legacy Sentinel seed STAC files removed from production seed")

aoi = load_json("data/seed/bangalore-60km-aoi.geojson")
plot = load_json("data/seed/sample-plot.geojson")
coll = load_json("data/seed/stac/resourcesat-2a-liss3-boa-collection.json")
item = load_json("data/seed/stac/resourcesat-2a-liss3-boa-sample-item.json")
awifs_coll = load_json("data/seed/stac/resourcesat-2a-awifs-boa-collection.json")
eos06_coll = load_json("data/seed/stac/eos-06-ocm-lac-ndvi-8day-360m-collection.json")
irs1c_coll = load_json("data/seed/stac/irs-1c-liss3-archive-collection.json")
cartosat_coll = load_json("data/seed/stac/cartosat-3-gated-collection.json")
sar_colls = {
    source_id: load_json(f"data/seed/stac/{source_id}-collection.json")
    for source_id in SAR_SOURCE_IDS
}

if aoi:
    props = aoi.get("properties", {})
    check(aoi.get("type") == "Feature" and aoi["geometry"]["type"] == "Polygon", "AOI is a Polygon Feature")
    check(props.get("id") == AOI_ID, f"AOI id == {AOI_ID}")
    check(aoi.get("bbox") == [77.023647, 12.537266, 78.131561, 13.61645], "AOI bbox == Bangalore 60 km extent")
    check(props.get("compositeGridCrs") == "EPSG:32643", "AOI composite grid CRS == EPSG:32643")
if plot:
    check(plot.get("type") == "Feature" and plot["geometry"]["type"] == "Polygon", "sample-plot is a Polygon Feature")

# --------------------------------------------------------------------------
section("ResourceSat STAC collection contract")
if coll:
    check(coll.get("id") == SOURCE_ID, f"collection id == {SOURCE_ID}")
    exts = " ".join(coll.get("stac_extensions", []))
    for ext in ["eo/", "raster/", "projection/", "item-assets/", "classification/"]:
        check(ext in exts, f"collection declares extension: {ext.rstrip('/')}")
    check(coll.get("license") == "proprietary", "collection license is proprietary")
    check(coll.get("akasha:aoi_id") == AOI_ID, f"collection AOI id == {AOI_ID}")
    check(coll.get("akasha:supported_indices") == SUPPORTED_INDICES, "collection supported indices are ResourceSat-safe")
    check(coll.get("akasha:unsupported_indices") == UNSUPPORTED_INDICES, "collection records unsupported red-edge indices")
    check(coll.get("akasha:display_modes") == ["FCC"], "collection display mode == FCC")
    check(coll.get("akasha:default_display_mode") == "FCC", "collection default display mode == FCC")
    check(coll.get("akasha:fcc_role_order") == FCC_ROLE_ORDER, "collection FCC role order == NIR/RED/GREEN")
    check(coll.get("akasha:expected_assets") == ["analytic", "mask"], "collection expects analytic + mask assets")
    check(coll.get("akasha:mask_asset") == "mask", "collection mask asset == mask")
    check(coll.get("akasha:default_excluded_mask_classes") == EXCLUDED_MASK_CLASSES, "collection excludes provisional gap/cloud/shadow classes")
    check(bool(coll.get("akasha:metrics_provisional")), "collection metrics are marked provisional")
    refl = coll.get("akasha:reflectance", {})
    check(refl.get("offset") == OFFSET and refl.get("scale") == SCALE, "ResourceSat reflectance scale/offset correct")

    analytic = (coll.get("item_assets") or {}).get("analytic", {})
    eo = [b.get("name") for b in analytic.get("eo:bands", [])]
    check(eo == BANDS, f"analytic eo:bands order == {BANDS} (got {eo})")
    rb = analytic.get("raster:bands", [])
    check(len(rb) == 4, f"analytic raster:bands count == 4 (got {len(rb)})")
    check(all(b.get("scale") == SCALE for b in rb), "analytic raster:bands scale == 0.0001")
    check(all(b.get("offset") == OFFSET for b in rb), "analytic raster:bands offset == 0")
    check(all(b.get("data_type") == "uint16" for b in rb), "analytic raster:bands data_type == uint16")
    mask = (coll.get("item_assets") or {}).get("mask", {})
    mask_rb = mask.get("raster:bands", [])
    check(len(mask_rb) == 1 and mask_rb[0].get("data_type") == "uint8", "mask raster:band == single uint8")
    classes = [c.get("value") for c in mask.get("classification:classes", [])]
    check(classes == MASK_CLASS_VALUES, "mask classification classes == 0..4")

# --------------------------------------------------------------------------
section("ResourceSat STAC item contract + object keys")
if item:
    check(item.get("id") == ITEM_ID, f"item id == {ITEM_ID}")
    check(item.get("collection") == SOURCE_ID, f"item collection == {SOURCE_ID}")
    props = item.get("properties", {})
    check(props.get("datetime") == "2026-03-19T00:00:00Z", "item datetime is the sample composite anchor")
    check(props.get("akasha:aoi_id") == AOI_ID, f"item AOI id == {AOI_ID}")
    check(props.get("akasha:item_kind") == "composite", "item kind == composite")
    check(bool(props.get("akasha:composite")), "item is marked as a composite")
    check(props.get("akasha:composite_grid_crs") == "EPSG:32643", "item composite grid CRS == EPSG:32643")
    check(props.get("akasha:composite_resolution_meters") == 24, "item composite resolution == 24m")
    check(props.get("akasha:contributing_scene_count") == 1, "item contributing scene count == 1")
    check(props.get("proj:epsg") == 32643, "item proj:epsg == 32643")
    check(bool(props.get("akasha:metrics_provisional")), "item metrics are marked provisional")
    assets = item.get("assets", {})
    a_href = assets.get("analytic", {}).get("href", "")
    m_href = assets.get("mask", {}).get("href", "")
    check(a_href == f"s3://akasha-cogs/{ANALYTIC_KEY}", f"analytic href == s3://akasha-cogs/{ANALYTIC_KEY}")
    check(m_href == f"s3://akasha-cogs/{MASK_KEY}", f"mask href == s3://akasha-cogs/{MASK_KEY}")
    a_eo = [b.get("name") for b in assets.get("analytic", {}).get("eo:bands", [])]
    check(a_eo == BANDS, "item analytic eo:bands order")
    a_rb = assets.get("analytic", {}).get("raster:bands", [])
    check(len(a_rb) == 4 and all(b.get("offset") == OFFSET for b in a_rb), "item analytic raster:bands scale/offset")

# --------------------------------------------------------------------------
section("ResourceSat AWiFS Phase 5 collection contract")
if awifs_coll:
    check(awifs_coll.get("id") == AWIFS_SOURCE_ID, f"AWiFS collection id == {AWIFS_SOURCE_ID}")
    check(awifs_coll.get("akasha:source_kind") == "optical", "AWiFS source kind == optical")
    check(awifs_coll.get("akasha:analysis_level") == "regional", "AWiFS analysis level == regional")
    check(awifs_coll.get("akasha:availability_status") == "gated", "AWiFS remains gated before validation")
    check(awifs_coll.get("akasha:supported_indices") == SUPPORTED_INDICES, "AWiFS supported indices mirror ResourceSat-safe optical indices")
    check(awifs_coll.get("akasha:display_modes") == ["FCC"], "AWiFS display mode == FCC")
    check("AWiFS" in str(awifs_coll.get("akasha:mask_method", "")), "AWiFS mask method is source-specific")
    check(
        "LISS-3 BOA sample" not in str(awifs_coll.get("akasha:mask_method", "")),
        "AWiFS mask method does not claim LISS-3 sample validation",
    )

# --------------------------------------------------------------------------
section("EOS-06 context collection contract")
if eos06_coll:
    check(eos06_coll.get("id") == EOS06_SOURCE_ID, f"EOS-06 collection id == {EOS06_SOURCE_ID}")
    check(eos06_coll.get("akasha:source_kind") == "context", "EOS-06 source kind == context")
    check(eos06_coll.get("akasha:expected_assets") == ["ndvi"], "EOS-06 expects only an NDVI context asset")
    check(eos06_coll.get("akasha:supported_indices") == [], "EOS-06 field analytics disabled")
    check(eos06_coll.get("akasha:display_modes") == ["NDVI_CONTEXT"], "EOS-06 display mode == NDVI_CONTEXT")
    ndvi_asset = (eos06_coll.get("item_assets") or {}).get("ndvi", {})
    check(ndvi_asset.get("roles") == ["data", "index", "context"], "EOS-06 NDVI asset roles are context-safe")
    ndvi_bands = ndvi_asset.get("raster:bands", [])
    check(
        len(ndvi_bands) == 1 and ndvi_bands[0].get("unit") == "ndvi",
        "EOS-06 NDVI asset is single-band precomputed NDVI",
    )

# --------------------------------------------------------------------------
section("IRS-1C archive collection contract")
if irs1c_coll:
    check(irs1c_coll.get("id") == IRS1C_SOURCE_ID, f"IRS-1C collection id == {IRS1C_SOURCE_ID}")
    check(irs1c_coll.get("akasha:source_kind") == "archive", "IRS-1C source kind == archive")
    check(irs1c_coll.get("akasha:expected_assets") == ["analytic", "mask"], "IRS-1C expects analytic + mask assets")
    check(irs1c_coll.get("akasha:supported_indices") == [], "IRS-1C analytics disabled until validation")
    check(irs1c_coll.get("akasha:refresh_policy") == "Archive only; no scheduled refresh.", "IRS-1C is archive-only")
    irs_assets = irs1c_coll.get("item_assets") or {}
    check(set(irs_assets) == {"analytic", "mask"}, "IRS-1C item_assets declare analytic + mask")
    check(irs_assets.get("analytic", {}).get("roles") == ["data", "reflectance", "archive"], "IRS-1C analytic asset is archive reflectance")
    check(irs_assets.get("mask", {}).get("roles") == ["metadata", "data-mask", "archive"], "IRS-1C mask asset is archive data-mask")

# --------------------------------------------------------------------------
section("Cartosat-3 gated visual collection contract")
if cartosat_coll:
    check(cartosat_coll.get("id") == CARTOSAT_SOURCE_ID, f"Cartosat collection id == {CARTOSAT_SOURCE_ID}")
    check(cartosat_coll.get("akasha:source_kind") == "context", "Cartosat source kind == context")
    check(cartosat_coll.get("akasha:analysis_level") == "context", "Cartosat analysis level == context")
    check(cartosat_coll.get("akasha:availability_status") == "gated", "Cartosat availability is gated")
    check(cartosat_coll.get("akasha:expected_assets") == ["visual"], "Cartosat expects only visual assets")
    check(cartosat_coll.get("akasha:supported_indices") == [], "Cartosat field analytics disabled")
    check(cartosat_coll.get("akasha:crop_indices_enabled") is False, "Cartosat crop indices disabled")
    check(cartosat_coll.get("akasha:display_modes") == ["CONTEXT"], "Cartosat display mode == CONTEXT")
    check(cartosat_coll.get("akasha:default_display_mode") == "CONTEXT", "Cartosat default display mode == CONTEXT")
    check(
        "Manual/order workflow" in str(cartosat_coll.get("akasha:refresh_policy")),
        "Cartosat refresh policy stays manual/order",
    )
    visual_asset = (cartosat_coll.get("item_assets") or {}).get("visual", {})
    check(visual_asset.get("roles") == ["data", "visual"], "Cartosat visual asset roles match ingestion STAC")
    visual_bands = visual_asset.get("raster:bands", [])
    check(
        len(visual_bands) == 1 and visual_bands[0].get("unit") == "dn",
        "Cartosat visual asset remains raw-DN context",
    )

# --------------------------------------------------------------------------
section("SAR context collection contracts")
for source_id, sar_coll in sar_colls.items():
    if not sar_coll:
        continue
    check(sar_coll.get("id") == source_id, f"{source_id} collection id")
    exts = " ".join(sar_coll.get("stac_extensions", []))
    for ext in ["sar/", "raster/", "projection/", "item-assets/"]:
        check(ext in exts, f"{source_id} declares extension: {ext.rstrip('/')}")
    check(sar_coll.get("akasha:source_kind") == "sar", f"{source_id} source kind == sar")
    check(sar_coll.get("akasha:supported_indices") == [], f"{source_id} analytics disabled")
    check(sar_coll.get("akasha:expected_assets") is None, f"{source_id} does not advertise optical asset expectations")
    check(sar_coll.get("akasha:display_modes") == ["VV_GRAYSCALE"], f"{source_id} display mode == VV_GRAYSCALE")
    check(sar_coll.get("akasha:default_display_mode") == "VV_GRAYSCALE", f"{source_id} default display mode == VV_GRAYSCALE")
    check(sar_coll.get("akasha:date_metrics_kind") == "radar", f"{source_id} date metrics kind == radar")
    check(sar_coll.get("akasha:analysis_level") == "context", f"{source_id} analysis level == context")
    sar_assets = sar_coll.get("item_assets") or {}
    check(set(sar_assets) == {"backscatter"}, f"{source_id} item_assets declare only backscatter")
    backscatter = sar_assets.get("backscatter", {})
    check(backscatter.get("roles") == ["data", "backscatter"], f"{source_id} backscatter roles")
    backscatter_bands = backscatter.get("raster:bands", [])
    check(
        len(backscatter_bands) == 1 and backscatter_bands[0].get("unit") == "dB",
        f"{source_id} backscatter is single dB raster band",
    )

# --------------------------------------------------------------------------
section("PostGIS app schema")
models_path = REPO / "apps/api/app/models.py"
baseline_path = REPO / "apps/api/alembic/versions/20260609_0001_fresh_orm_baseline.py"
if models_path.exists() and baseline_path.exists():
    models = models_path.read_text()
    baseline = baseline_path.read_text()
    check("CREATE EXTENSION IF NOT EXISTS postgis" in baseline, "schema enables PostGIS extension")
    check("CREATE EXTENSION IF NOT EXISTS pgcrypto" in baseline, "schema enables pgcrypto extension")
    check("Base.metadata.create_all" in baseline, "Alembic baseline creates ORM metadata")
    check("set_updated_at" in baseline, "updated_at trigger present")
    check("class Plot" in models and '__tablename__ = "plots"' in models, "ORM defines akasha.plots")
    check("Geometry(" in models and "srid=4326" in models, "ORM geometry uses SRID 4326")
    check("plots_geometry_gix" in models and 'postgresql_using="gist"' in models, "spatial GIST index present")
    check("class AppSetting" in models and '__tablename__ = "app_settings"' in models, "ORM defines app_settings")
    check("class IndexRequest" in models and '__tablename__ = "index_requests"' in models, "ORM defines index_requests")
else:
    check(False, "missing ORM models or Alembic baseline")

# --------------------------------------------------------------------------
section("Tooling wiring")
for rel in [
    "apps/api/app/cli.py",
    "apps/api/app/db.py",
    "services/ingestion/akasha_ingest/config.py",
    "services/ingestion/akasha_ingest/bhoonidhi.py",
    "services/ingestion/akasha_ingest/catalog.py",
    "services/ingestion/akasha_ingest/storage.py",
    "services/ingestion/akasha_ingest/seed.py",
    "services/ingestion/akasha_ingest/verify.py",
    "scripts/prepare_context_cog.py",
    "scripts/validate_slice1.py",
]:
    check((REPO / rel).exists(), f"exists: {rel}")

api_req = (REPO / "apps/api/requirements.txt").read_text()
check("psycopg" in api_req, "api requirements include psycopg")
check("SQLAlchemy" in api_req, "api requirements include SQLAlchemy")
check("alembic" in api_req, "api requirements include Alembic")
check("GeoAlchemy2" in api_req, "api requirements include GeoAlchemy2")
api_docker = (REPO / "apps/api/Dockerfile").read_text()
check("COPY alembic.ini" in api_docker and "COPY alembic" in api_docker, "api Dockerfile copies Alembic baseline")
api_cli = (REPO / "apps/api/app/cli.py").read_text()
check("S3_ENDPOINT_URL" in api_cli and "minio/health/live" in api_cli, "api check verifies API -> MinIO liveness")

ing_req = (REPO / "services/ingestion/requirements.txt").read_text()
check("pypgstac" in ing_req, "ingestion requirements include pypgstac")
check("boto3" in ing_req, "ingestion requirements include boto3")
ing_docker = (REPO / "services/ingestion/Dockerfile").read_text()
check("COPY data/seed" in ing_docker, "ingestion Dockerfile copies data/seed")

ing_config = (REPO / "services/ingestion/akasha_ingest/config.py").read_text()
ing_scene = (REPO / "services/ingestion/akasha_ingest/scene.py").read_text()
ing_catalog = (REPO / "services/ingestion/akasha_ingest/catalog.py").read_text()
ing_worker = (REPO / "services/ingestion/worker.py").read_text()
check("EOS06_CONTEXT_COLLECTION_ID" in ing_config, "ingestion config registers EOS-06 context collection")
check('"ndvi"' in ing_scene and "context_asset_key" in ing_scene, "scene identity maps EOS-06 context to ndvi.tif")
check("EOS06_CONTEXT_COLLECTION_ID" in ing_catalog and '"asset_key": "ndvi"' in ing_catalog, "catalog builder emits EOS-06 ndvi asset")
check("CARTOSAT3_CONTEXT_COLLECTION_ID" in ing_config, "ingestion config registers Cartosat gated context collection")
check("cartosat-3-gated" in ing_scene and "visual_key" in ing_scene, "scene identity maps Cartosat to visual object layout")
check("prepare-context-cog" in ing_worker, "worker exposes manual context COG preparation")
check("IRS1C_ARCHIVE_COLLECTION_ID" in ing_config, "ingestion config registers IRS-1C archive collection")
check("_ARCHIVE_SOURCE_IDS" in ing_scene and "/archive/" in ing_scene, "scene identity maps IRS-1C to archive object layout")
check("_build_archive_stac_item" in ing_catalog, "catalog builder emits IRS-1C archive STAC items")
check("EOS04_SAR_COLLECTION_ID" in ing_config, "ingestion config registers EOS-04 SAR collection")
check("NISAR_GCOV_COLLECTION_ID" in ing_config, "ingestion config registers NISAR GCOV collection")
check("SAR_COLLECTION_IDS" in ing_config, "ingestion config groups SAR collection ids")
check("_SAR_SOURCE_IDS" in ing_scene and "backscatter_key" in ing_scene, "scene identity maps SAR to backscatter layout")
check("SAR_SOURCE_META" in ing_catalog and "_build_sar_stac_item" in ing_catalog, "catalog builder emits SAR STAC items")

compose = (REPO / "infra/docker/docker-compose.yml").read_text()
check("context: ../.." in compose, "compose ingestion build context is repo root")
check("AKASHA_COG_BUCKET" in compose, "compose wires AKASHA_COG_BUCKET")
check('S3_ENDPOINT_URL: "http://minio:9000"' in compose, "compose wires S3_ENDPOINT_URL into api")

storage_py = (REPO / "services/ingestion/akasha_ingest/storage.py").read_text()
check("missing expected key" in storage_py, "MinIO verify fails if deterministic keys are missing")

systemd_dir = REPO / "infra/selfhosted/systemd"
sync_service = systemd_dir / "akasha-bhoonidhi-sync.service"
sync_timer = systemd_dir / "akasha-bhoonidhi-sync.timer"
sync_script = systemd_dir / "akasha-bhoonidhi-sync.sh"
sync_env = systemd_dir / "akasha-bhoonidhi-sync.env.example"
sync_installer = systemd_dir / "install-akasha-bhoonidhi-sync.sh"
staging_validator = REPO / "scripts/validate_selfhosted_staging_bhoonidhi.py"
check(sync_service.is_file(), "self-hosted systemd Bhoonidhi sync service exists")
check(sync_timer.is_file(), "self-hosted systemd Bhoonidhi sync timer exists")
check(sync_script.is_file(), "self-hosted Bhoonidhi sync wrapper exists")
check(sync_env.is_file(), "self-hosted Bhoonidhi sync env template exists")
check(sync_installer.is_file(), "self-hosted Bhoonidhi sync installer exists")
check(staging_validator.is_file(), "self-hosted staging Bhoonidhi validator exists")
if sync_service.is_file():
    service_raw = sync_service.read_text()
    check("flock -n /srv/akasha/ingestion/bhoonidhi-sync.systemd.lock" in service_raw, "systemd sync uses host non-overlap lock")
    check("/srv/akasha/data/raw/bhoonidhi" in service_raw and "/srv/akasha/data/work/bhoonidhi" in service_raw, "systemd sync prepares /srv/akasha raw/work paths")
if sync_timer.is_file():
    timer_raw = sync_timer.read_text()
    check("OnCalendar=" in timer_raw and "Persistent=true" in timer_raw, "systemd timer is scheduled and persistent")
if sync_script.is_file():
    script_raw = sync_script.read_text()
    check("bhoonidhi-sync" in script_raw and "--window-days" in script_raw, "sync wrapper runs rolling-window bhoonidhi-sync")
    check("--backfill-days" in script_raw and "AKASHA_SYNC_BACKFILL_DAYS" in script_raw, "sync wrapper supports spread-out launch backfill")
    check("--raw-root" in script_raw and "--ledger-path" in script_raw, "sync wrapper passes /srv raw and ledger paths")
    check("--pull" in script_raw and "AKASHA_SYNC_PULL_POLICY" in script_raw, "sync wrapper avoids private registry pulls by default")
if sync_installer.is_file():
    installer_raw = sync_installer.read_text()
    check("install_with_mode 0755" in installer_raw and "akasha-bhoonidhi-sync.sh" in installer_raw, "sync installer installs wrapper")
    check("systemctl daemon-reload" in installer_raw, "sync installer reloads systemd")
    check("AKASHA_SYNC_DRY_RUN=true" in installer_raw, "sync installer documents dry-run first run")
if staging_validator.is_file():
    validator_raw = staging_validator.read_text()
    check("docker compose" in validator_raw and "worker.py verify-cogs" in validator_raw, "staging validator runs worker COG checks")
    check("bhoonidhi-search" in validator_raw and "lookback-days 45" in validator_raw, "staging validator checks current Bhoonidhi window")
    check("org.opencontainers.image.revision" in validator_raw, "staging validator checks running image revision")
    check("stop_on_failure" in validator_raw and "--continue-after-failure" in validator_raw, "staging validator fails fast on image mismatch")
    check("smoke-test.py" in validator_raw and "--public-origin" in validator_raw, "staging validator can run public gateway smoke")

deploy_staging = (REPO / ".github/workflows/deploy-staging.yml").read_text()
deploy_production = (REPO / ".github/workflows/deploy-production.yml").read_text()
for workflow_name, workflow_raw in [
    ("staging", deploy_staging),
    ("production", deploy_production),
]:
    check("docker/login-action@v3" in workflow_raw, f"{workflow_name} deploy logs into GHCR before image verification")
    check("docker manifest inspect" in workflow_raw, f"{workflow_name} deploy verifies immutable image tags before Coolify patch")
    for image in ["akasha-web", "akasha-api", "akasha-ingestion-worker", "akasha-ingestion-sar"]:
        check(image in workflow_raw, f"{workflow_name} deploy verifies {image} image tag")

api_env = (REPO / "apps/api/.env.example").read_text()
selfhosted_env = (REPO / "infra/selfhosted/env.example").read_text()
docker_compose = (REPO / "infra/docker/docker-compose.yml").read_text()
coolify_compose = (REPO / "infra/selfhosted/coolify-compose.yml").read_text()
for name, raw in [
    ("api env", api_env),
    ("self-hosted env", selfhosted_env),
    ("docker compose", docker_compose),
    ("coolify compose", coolify_compose),
]:
    check("DEFAULT_AOI_ID=bangalore" not in raw, f"{name} does not default to legacy bangalore AOI id")
    check(
        "bangalore-60km-aoi.geojson" in raw,
        f"{name} uses bangalore-60km AOI config path",
    )

# --------------------------------------------------------------------------
section("Production documentation defaults")
readme_raw = (REPO / "README.md").read_text(encoding="utf-8")
engineering_raw = (REPO / "docs/engineering-dos-donts.md").read_text(encoding="utf-8")
emergent_raw = (REPO / "docs/emergent-context.md").read_text(encoding="utf-8")
data_rules_raw = (REPO / "docs/data-ingestion-and-satellite-rules.md").read_text(encoding="utf-8")
check(
    "ResourceSat LISS-3 FCC composites" in readme_raw,
    "README describes ResourceSat FCC as the production browsing default",
)
check(
    "RGB display tiles" not in readme_raw,
    "README does not describe TiTiler as RGB-only",
)
check(
    "TiTiler serves display tiles only" in engineering_raw,
    "engineering guardrails describe source-neutral display tiles",
)
check(
    "TiTiler serves RGB display tiles only" not in engineering_raw,
    "engineering guardrails do not retain RGB-only TiTiler wording",
)
check(
    "Cloud/SCL-masked" not in emergent_raw,
    "emergent handoff avoids active SCL-only statistics wording",
)
check(
    "s3://akasha-cogs/sentinel-2-l2a/{date}" not in emergent_raw,
    "emergent runtime gates do not point operators at Sentinel production keys",
)
check(
    "resourcesat-2a-liss3-boa/composite/{aoiId}/{date}/analytic.tif|mask.tif"
    in emergent_raw,
    "emergent runtime gates point at ResourceSat composite keys",
)
check(
    "AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES=true" in data_rules_raw,
    "data rules mark Sentinel support as explicit opt-in legacy",
)

# --------------------------------------------------------------------------
section("Secret hygiene (ingestion .env.example)")
env_raw = (REPO / "services/ingestion/.env.example").read_text()
for required in [
    "S3_REGION",
    "AKASHA_COG_BUCKET",
    "SEED_DATA_DIR",
    "AOI_CONFIG_PATH",
    "AOI_CONFIG_DIR",
    "BHOONIDHI_MAX_DOWNLOADS_PER_SYNC",
]:
    check(required in env_raw, f"ingestion .env.example documents {required}")
bad = []
for line in env_raw.splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    if any(t in k.upper() for t in ("SECRET", "KEY", "PASSWORD")) and v.strip():
        if "<" not in v and "CHANGE_ME" not in v:
            bad.append(k.strip())
check(not bad, f"ingestion .env.example secret-like vars are placeholders {bad or ''}")

# --------------------------------------------------------------------------
print("\n" + "=" * 64)
print(" Akasha - Slice 1 artifact validation")
print("=" * 64)
passed = failed = 0
for ok, msg in results:
    if ok is None:
        print(f"\n> {msg}")
        continue
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    passed += 1 if ok else 0
    failed += 0 if ok else 1
print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)
if failed:
    print("\nSlice 1 validation FAILED - fix the items above.")
    sys.exit(1)
print("\nSlice 1 validation PASSED - storage/catalog artifacts are deployment-ready.")
sys.exit(0)
