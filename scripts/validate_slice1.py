#!/usr/bin/env python3
"""Slice 1 artifact validator for the Akasha Railway MVP.

Static validation (no Docker / no running services) of the storage + catalog
foundation: the PostGIS app schema, the seeded STAC collection + item (frozen
band order, scale/offset, SCL classes, proj), the GeoJSON seeds, the
deterministic bucket/key + idempotency-key contracts, and the ingestion/api
tooling wiring.

Run:  python scripts/validate_slice1.py
Exit: 0 if everything passes, 1 otherwise.
"""
# ruff: noqa: E501
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "ingestion"))

# Import the dependency-free scene module (idempotency contract source of truth).
from akasha_ingest.scene import SAMPLE_SCENE  # noqa: E402

FROZEN_BANDS = ["B04", "B08", "B05", "B06", "B07", "B11", "B12", "B03", "B02"]
RGB_POSITIONS = [1, 8, 9]
EXCLUDED_SCL = [0, 1, 2, 3, 7, 8, 9, 10, 11]
SCALE = 0.0001
OFFSET = -0.1

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
    "data/seed/bangalore-aoi.geojson",
    "data/seed/sample-plot.geojson",
    "data/seed/stac/sentinel-2-l2a-collection.json",
    "data/seed/stac/sentinel-2-l2a-sample-item.json",
    "data/seed/README.md",
]:
    check((REPO / rel).exists(), f"exists: {rel}")

aoi = load_json("data/seed/bangalore-aoi.geojson")
plot = load_json("data/seed/sample-plot.geojson")
coll = load_json("data/seed/stac/sentinel-2-l2a-collection.json")
item = load_json("data/seed/stac/sentinel-2-l2a-sample-item.json")

if aoi:
    check(aoi.get("type") == "Feature" and aoi["geometry"]["type"] == "Polygon", "AOI is a Polygon Feature")
    check(aoi.get("bbox") == [77.4, 12.8, 77.8, 13.2], "AOI bbox == Bangalore [77.4,12.8,77.8,13.2]")
if plot:
    check(plot.get("type") == "Feature" and plot["geometry"]["type"] == "Polygon", "sample-plot is a Polygon Feature")

# --------------------------------------------------------------------------
section("STAC collection contract")
if coll:
    check(coll.get("id") == "sentinel-2-l2a", "collection id == sentinel-2-l2a")
    exts = " ".join(coll.get("stac_extensions", []))
    for ext in ["eo/", "raster/", "projection/", "item-assets/", "classification/"]:
        check(ext in exts, f"collection declares extension: {ext.rstrip('/')}")
    analytic = (coll.get("item_assets") or {}).get("analytic", {})
    eo = [b.get("name") for b in analytic.get("eo:bands", [])]
    check(eo == FROZEN_BANDS, f"analytic eo:bands frozen order == {FROZEN_BANDS} (got {eo})")
    rb = analytic.get("raster:bands", [])
    check(len(rb) == 9, f"analytic raster:bands count == 9 (got {len(rb)})")
    check(all(b.get("scale") == SCALE for b in rb), "analytic raster:bands scale == 0.0001")
    check(all(b.get("offset") == OFFSET for b in rb), "analytic raster:bands offset == -0.1 (not -1000)")
    check(all(b.get("data_type") == "uint16" for b in rb), "analytic raster:bands data_type == uint16 (raw DN)")
    scl = (coll.get("item_assets") or {}).get("scl", {})
    scl_rb = scl.get("raster:bands", [])
    check(len(scl_rb) == 1 and scl_rb[0].get("data_type") == "uint8", "SCL raster:band == single uint8")
    classes = [c.get("value") for c in scl.get("classification:classes", [])]
    check(classes == list(range(12)), "SCL classification:classes == 0..11")
    check(coll.get("akasha:rgb_band_positions") == RGB_POSITIONS, "true-colour RGB positions == [1,8,9]")
    check(coll.get("akasha:default_excluded_scl_classes") == EXCLUDED_SCL, "default excluded SCL classes == [0,1,2,3,7,8,9,10,11]")
    refl = coll.get("akasha:reflectance", {})
    check(refl.get("offset") == OFFSET and refl.get("scale") == SCALE, "akasha:reflectance scale/offset correct")

# --------------------------------------------------------------------------
section("STAC item contract + idempotency")
if item:
    check(item.get("id") == SAMPLE_SCENE.item_id, f"item id == {SAMPLE_SCENE.item_id}")
    check(item.get("collection") == "sentinel-2-l2a", "item collection == sentinel-2-l2a")
    props = item.get("properties", {})
    check(props.get("datetime") == SAMPLE_SCENE.acquisition_datetime, "item datetime matches sample scene")
    check(props.get("akasha:scene_key") == SAMPLE_SCENE.scene_key, f"item scene_key == {SAMPLE_SCENE.scene_key}")
    check(props.get("proj:epsg") == 32643, "item proj:epsg == 32643 (UTM 43N)")
    assets = item.get("assets", {})
    a_href = assets.get("analytic", {}).get("href", "")
    s_href = assets.get("scl", {}).get("href", "")
    check(a_href == f"s3://akasha-cogs/{SAMPLE_SCENE.analytic_key}", f"analytic href == s3://akasha-cogs/{SAMPLE_SCENE.analytic_key}")
    check(s_href == f"s3://akasha-cogs/{SAMPLE_SCENE.scl_key}", f"scl href == s3://akasha-cogs/{SAMPLE_SCENE.scl_key}")
    a_eo = [b.get("name") for b in assets.get("analytic", {}).get("eo:bands", [])]
    check(a_eo == FROZEN_BANDS, "item analytic eo:bands frozen order")
    a_rb = assets.get("analytic", {}).get("raster:bands", [])
    check(len(a_rb) == 9 and all(b.get("offset") == OFFSET for b in a_rb), "item analytic raster:bands scale/offset")

# --------------------------------------------------------------------------
section("Idempotency key (scene module)")
check(
    SAMPLE_SCENE.scene_key == "sentinel-2-l2a:L2A:43PHP:2025-09-14T05:06:49.024000Z:05.11",
    f"scene_key == {SAMPLE_SCENE.scene_key}",
)
check(SAMPLE_SCENE.item_id == "sentinel-2-l2a_43PHP_20250914_0511", f"item_id == {SAMPLE_SCENE.item_id}")
check(SAMPLE_SCENE.analytic_key == "sentinel-2-l2a/2025-09-14/analytic.tif", "analytic_key layout")
check(SAMPLE_SCENE.scl_key == "sentinel-2-l2a/2025-09-14/scl.tif", "scl_key layout")

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
    "services/ingestion/akasha_ingest/scene.py",
    "services/ingestion/akasha_ingest/catalog.py",
    "services/ingestion/akasha_ingest/storage.py",
    "services/ingestion/akasha_ingest/seed.py",
    "services/ingestion/akasha_ingest/verify.py",
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

compose = (REPO / "infra/docker/docker-compose.yml").read_text()
check("context: ../.." in compose, "compose ingestion build context is repo root")
check("AKASHA_COG_BUCKET" in compose, "compose wires AKASHA_COG_BUCKET")
check('S3_ENDPOINT_URL: "http://minio:9000"' in compose, "compose wires S3_ENDPOINT_URL into api")

storage_py = (REPO / "services/ingestion/akasha_ingest/storage.py").read_text()
check("missing expected key" in storage_py, "MinIO verify fails if deterministic keys are missing")

# --------------------------------------------------------------------------
section("Secret hygiene (ingestion .env.example)")
env_raw = (REPO / "services/ingestion/.env.example").read_text()
for required in ["S3_REGION", "AKASHA_COG_BUCKET", "SEED_DATA_DIR"]:
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
print(" Akasha — Slice 1 artifact validation")
print("=" * 64)
passed = failed = 0
for ok, msg in results:
    if ok is None:
        print(f"\n▸ {msg}")
        continue
    print(f"  [{'✓' if ok else '✗'}] {msg}")
    passed += 1 if ok else 0
    failed += 0 if ok else 1
print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)
if failed:
    print("\nSlice 1 validation FAILED — fix the items above.")
    sys.exit(1)
print("\nSlice 1 validation PASSED — storage/catalog artifacts are Railway-ready.")
sys.exit(0)
