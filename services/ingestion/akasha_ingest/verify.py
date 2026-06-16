"""Exit-criteria verification for Slice 1 (run on the deployment / local Docker).

Checks:
  1. PostGIS reachable via SELECT postgis_version().
  2. STAC API returns the configured collection.
  3. MinIO bucket reachable from this (ingestion/api) container.

All heavy drivers are imported lazily. Prints results and returns an exit code.
"""
from __future__ import annotations

import json
import urllib.request

from . import config, storage


def check_postgis() -> tuple[bool, str]:
    try:
        import psycopg  # lazy

        with psycopg.connect(config.DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT postgis_version()")
            version = cur.fetchone()[0]
        return True, f"PostGIS version: {version}"
    except Exception as exc:  # noqa: BLE001
        return False, f"PostGIS check failed: {exc}"


def check_stac_collection(collection_id: str | None = None) -> tuple[bool, str]:
    try:
        source_id = collection_id or config.COLLECTION_ID
        url = config.STAC_API_URL.rstrip("/") + f"/collections/{source_id}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("id") == source_id:
            return True, f"STAC API returns collection '{source_id}'"
        return False, f"STAC API returned unexpected id: {data.get('id')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"STAC collection check failed: {exc}"


def check_minio(collection_id: str | None = None) -> tuple[bool, str]:
    return storage.bucket_reachable(collection_id=collection_id)


def check_real_cogs() -> tuple[bool, str]:
    """Phase 2: deterministic COG objects exist AND are non-empty real COGs."""
    return storage.verify_real_cogs()


def run(collection_id: str | None = None) -> int:
    source_id = collection_id or config.COLLECTION_ID
    checks = [
        ("PostGIS (SELECT postgis_version())", check_postgis),
        (f"STAC API collection '{source_id}'", lambda: check_stac_collection(source_id)),
        (f"MinIO bucket '{config.BUCKET}' reachable", lambda: check_minio(source_id)),
    ]
    return _run_checks("Akasha Slice 1 — exit-criteria verification", checks)


def run_phase2(collection_id: str | None = None) -> int:
    """Phase 2 verification: Slice 1 criteria PLUS non-empty real COG objects."""
    source_id = collection_id or config.COLLECTION_ID
    checks = [
        ("PostGIS (SELECT postgis_version())", check_postgis),
        (f"STAC API collection '{source_id}'", lambda: check_stac_collection(source_id)),
        (f"MinIO bucket '{config.BUCKET}' reachable", lambda: check_minio(source_id)),
    ]
    if source_id == config.SENTINEL2_COLLECTION_ID:
        checks.append(("MinIO real (non-empty) COG objects", check_real_cogs))
    return _run_checks("Akasha Slice 2 (Phase 2) — raster de-risk verification", checks)


def _run_checks(title: str, checks) -> int:
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)
    failed = 0
    for label, fn in checks:
        ok, detail = fn()
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}\n         -> {detail}")
        if not ok:
            failed += 1
    print("-" * 60)
    print(f" {len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0
