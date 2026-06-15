"""Akasha ingestion worker CLI.

Slice 0: skeleton (info/healthcheck).
Slice 1: storage/catalog foundation — pgSTAC migrate, idempotent STAC + MinIO
seeding, and exit-criteria verification.

Usage:
    python worker.py info
    python worker.py scene-key
    python worker.py migrate-catalog          # pgSTAC schema migration
    python worker.py seed-stac [--method upsert|insert_ignore]
    python worker.py seed-minio [--force]
    python worker.py seed [--method ...] [--force]   # full idempotent seed
    python worker.py ingest-manifest [--manifest-glob ...] [--method ...] [--force]
    python worker.py bhoonidhi-search --source resourcesat-2a-liss3-boa --aoi bangalore-60km
    python worker.py bhoonidhi-download --manifest ...
    python worker.py build-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km ...
    python worker.py verify                    # Slice 1 exit criteria
    python worker.py verify-cogs               # Phase 2: + non-empty real COGs
    python worker.py verify-manifest-cogs [--manifest-glob ...]
    python worker.py healthcheck               # required env vars present
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REQUIRED_ENV: list[str] = [
    "DATABASE_URL",
    "STAC_API_URL",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
]


def _redact(name: str, value: str) -> str:
    if not value:
        return "<unset>"
    if any(tok in name for tok in ("SECRET", "KEY", "PASSWORD", "URL", "USER_ID")):
        return f"<set:{len(value)} chars>"
    return value


def _manifest_paths(manifest_glob: str | None, collection_id: str | None = None):
    from akasha_ingest import config

    paths = (
        config.prepared_manifest_files(pattern=manifest_glob)
        if manifest_glob
        else config.prepared_manifest_files(source_id=collection_id)
    )
    if not paths:
        raise SystemExit("no prepare_manifest.json files found")
    return paths


def cmd_info(_: argparse.Namespace) -> int:
    from akasha_ingest import config
    from akasha_ingest.scene import SAMPLE_SCENE

    print("Akasha ingestion worker — Slice 1 (storage/catalog foundation).")
    print(f"  collection: {config.COLLECTION_ID}")
    print(f"  bucket:     {config.BUCKET}")
    print(f"  seed dir:   {config.find_seed_dir()}")
    print("  sample scene:")
    print(f"    scene_key:    {SAMPLE_SCENE.scene_key}")
    print(f"    item_id:      {SAMPLE_SCENE.item_id}")
    print(f"    analytic key: {SAMPLE_SCENE.analytic_key}")
    print(f"    scl key:      {SAMPLE_SCENE.scl_key}")
    print("  resolved env (secrets redacted):")
    for name in REQUIRED_ENV + [
        "AKASHA_COG_BUCKET",
        "AOI_CONFIG_PATH",
        "BHOONIDHI_API_BASE",
        "BHOONIDHI_USER_ID",
        "BHOONIDHI_SEARCH_RPS",
        "BHOONIDHI_DOWNLOAD_CONCURRENCY",
        "BHOONIDHI_RAW_ROOT",
        "BHOONIDHI_TEMP_ROOT",
        "BHOONIDHI_LEDGER_PATH",
    ]:
        print(f"    - {name}: {_redact(name, os.environ.get(name, ''))}")
    return 0


def cmd_scene_key(_: argparse.Namespace) -> int:
    from akasha_ingest.scene import SAMPLE_SCENE

    print(SAMPLE_SCENE.scene_key)
    print(f"item_id={SAMPLE_SCENE.item_id}")
    print(f"analytic={SAMPLE_SCENE.analytic_key}")
    print(f"scl={SAMPLE_SCENE.scl_key}")
    return 0


def cmd_healthcheck(_: argparse.Namespace) -> int:
    missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
    if missing:
        print(f"UNHEALTHY: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("HEALTHY: required env vars present.")
    return 0


def cmd_migrate_catalog(_: argparse.Namespace) -> int:
    from akasha_ingest import catalog

    print(catalog.migrate_catalog())
    return 0


def cmd_seed_stac(args: argparse.Namespace) -> int:
    from akasha_ingest import seed

    for line in seed.seed_stac(method=args.method, collection_id=args.collection_id):
        print(line)
    return 0


def cmd_seed_minio(args: argparse.Namespace) -> int:
    from akasha_ingest import seed

    for line in seed.seed_minio(force=args.force):
        print(line)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from akasha_ingest import seed

    for line in seed.seed_all(
        method=args.method,
        force=args.force,
        collection_id=args.collection_id,
    ):
        print(line)
    return 0


def cmd_ingest_manifest(args: argparse.Namespace) -> int:
    from akasha_ingest import catalog, storage

    manifest_paths = _manifest_paths(args.manifest_glob, args.collection_id)
    print(f"found {len(manifest_paths)} prepared manifest(s)")
    print(storage.ensure_bucket())
    for line in storage.seed_manifest_cogs(manifest_paths, force=args.force):
        print(line)
    print(catalog.load_manifest_items(manifest_paths, method=args.method))
    return 0


def cmd_bhoonidhi_search(args: argparse.Namespace) -> int:
    from pathlib import Path

    from akasha_ingest import bhoonidhi, config

    collection = bhoonidhi.source_collection(args.source)
    aoi = bhoonidhi.load_aoi(args.aoi_path or config.AOI_CONFIG_PATH)
    if args.aoi and args.aoi != aoi.get("id"):
        raise SystemExit(f"AOI '{args.aoi}' not found; loaded '{aoi.get('id')}'")
    datetime_range = args.datetime or bhoonidhi.lookback_datetime_range(args.lookback_days)
    client = bhoonidhi.BhoonidhiClient()
    items = client.search(
        collection=collection,
        datetime_range=datetime_range,
        intersects=aoi["geometry"],
        limit=args.limit,
    )
    manifest = bhoonidhi.build_search_manifest(
        source_id=args.source,
        collection=collection,
        aoi=aoi,
        datetime_range=datetime_range,
        items=items,
    )
    out_dir = Path(args.out_dir or config.BHOONIDHI_TEMP_ROOT) / args.source
    path = out_dir / "coverage_manifest.json"
    bhoonidhi.write_manifest(manifest, path)
    print(f"found {len(items)} Bhoonidhi item(s)")
    print(f"selected {len(manifest['selection']['selected_product_ids'])} candidate(s)")
    print(f"manifest: {path}")
    return 0


def cmd_bhoonidhi_download(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from akasha_ingest import bhoonidhi, config

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_id = str(manifest.get("source_id") or args.source or "")
    collection = str(manifest.get("collection") or bhoonidhi.source_collection(source_id))
    raw_root = Path(args.raw_root or config.BHOONIDHI_RAW_ROOT) / source_id
    client = bhoonidhi.BhoonidhiClient()
    downloaded: list[dict[str, object]] = []
    for candidate in manifest.get("candidates", []):
        item_id = candidate.get("item_id")
        if not item_id:
            continue
        dest = raw_root / f"{item_id}.zip"
        result = client.download_product(
            product_id=str(item_id),
            collection=collection,
            destination=dest,
        )
        candidate["download_status"] = result["status"]
        candidate["downloaded_path"] = result["path"]
        candidate["downloaded_bytes"] = result["bytes"]
        downloaded.append({"item_id": item_id, **result})
    output = dict(manifest)
    output["downloaded"] = downloaded
    output_path = manifest_path.parent / "download_manifest.json"
    bhoonidhi.write_manifest(output, output_path)
    print(f"downloaded {len(downloaded)} product(s)")
    print(f"manifest: {output_path}")
    return 0


def cmd_build_composite(args: argparse.Namespace) -> int:
    from akasha_ingest import bhoonidhi, composite, config

    if args.source != config.RESOURCESAT_LISS3_COLLECTION_ID:
        raise SystemExit("build-composite currently supports resourcesat-2a-liss3-boa only")
    aoi = bhoonidhi.load_aoi(args.aoi_path or config.AOI_CONFIG_PATH)
    if args.aoi and args.aoi != aoi.get("id"):
        raise SystemExit(f"AOI '{args.aoi}' not found; loaded '{aoi.get('id')}'")
    manifest_paths = composite.scene_manifest_paths_for_window(
        _manifest_paths(args.manifest_glob, args.source),
        window_start=args.window_start,
        window_end=args.window_end,
    )
    if not manifest_paths:
        raise SystemExit("no ResourceSat scene manifests found for the requested window")
    deps = composite.require_raster_deps()
    result = composite.build_resource_sat_composite(
        deps=deps,
        manifest_paths=manifest_paths,
        aoi=aoi,
        output_root=args.output_root or config.raster_source_root(),
        window_start=args.window_start,
        window_end=args.window_end,
        resolution=args.resolution,
        padding_pixels=args.padding_pixels,
        overwrite=args.overwrite,
        skip_validation=args.skip_validation,
        keep_intermediate=args.keep_intermediate,
    )
    print(f"composite output: {result.output_dir}")
    print(f"analytic: {result.analytic_cog}")
    print(f"mask: {result.mask_cog}")
    print(f"manifest: {result.manifest}")
    print(
        "metrics: "
        f"coverage={result.metrics['coverage_percent']} "
        f"usable={result.metrics['usable_pixel_percent']} "
        f"cloudMasked={result.metrics['cloud_masked_percent']}"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from akasha_ingest import verify

    return verify.run(collection_id=args.collection_id)


def cmd_verify_cogs(args: argparse.Namespace) -> int:
    from akasha_ingest import verify

    return verify.run_phase2(collection_id=args.collection_id)


def cmd_verify_manifest_cogs(args: argparse.Namespace) -> int:
    from akasha_ingest import storage

    manifest_paths = _manifest_paths(args.manifest_glob, args.collection_id)
    ok, detail = storage.verify_manifest_cogs(manifest_paths)
    print(f"[{'PASS' if ok else 'FAIL'}] manifest COGs -> {detail}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Akasha ingestion worker.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info", help="Print resolved config + sample scene.").set_defaults(func=cmd_info)
    sub.add_parser("scene-key", help="Print the deterministic scene key.").set_defaults(
        func=cmd_scene_key
    )
    sub.add_parser("healthcheck", help="Exit 0 if required env vars present.").set_defaults(
        func=cmd_healthcheck
    )
    sub.add_parser("migrate-catalog", help="Run pgSTAC migrations.").set_defaults(
        func=cmd_migrate_catalog
    )
    p_stac = sub.add_parser("seed-stac", help="Load collection + item (idempotent).")
    p_stac.add_argument("--method", default="upsert", choices=["upsert", "insert_ignore"])
    p_stac.add_argument("--collection-id", default=None, help="Collection/source id to seed.")
    p_stac.set_defaults(func=cmd_seed_stac)
    p_minio = sub.add_parser("seed-minio", help="Create bucket + deterministic keys.")
    p_minio.add_argument("--force", action="store_true")
    p_minio.set_defaults(func=cmd_seed_minio)
    p_seed = sub.add_parser("seed", help="Full idempotent seed (catalog + storage).")
    p_seed.add_argument("--method", default="upsert", choices=["upsert", "insert_ignore"])
    p_seed.add_argument("--force", action="store_true")
    p_seed.add_argument("--collection-id", default=None, help="Collection/source id to seed.")
    p_seed.set_defaults(func=cmd_seed)
    p_manifest = sub.add_parser("ingest-manifest", help="Upload prepared COGs + load STAC items.")
    p_manifest.add_argument("--manifest-glob", help="Glob for prepare_manifest.json files.")
    p_manifest.add_argument(
        "--collection-id",
        default=None,
        help="Source-scoped manifest collection id.",
    )
    p_manifest.add_argument("--method", default="upsert", choices=["upsert", "insert_ignore"])
    p_manifest.add_argument("--force", action="store_true")
    p_manifest.set_defaults(func=cmd_ingest_manifest)
    p_bhoonidhi_search = sub.add_parser(
        "bhoonidhi-search",
        help="Search Bhoonidhi and write a dry-run coverage manifest.",
    )
    p_bhoonidhi_search.add_argument(
        "--source",
        default="resourcesat-2a-liss3-boa",
        help="Akasha source id to search.",
    )
    p_bhoonidhi_search.add_argument(
        "--aoi",
        default="bangalore-60km",
        help="AOI id expected in the AOI config.",
    )
    p_bhoonidhi_search.add_argument("--aoi-path", default=None, help="AOI GeoJSON path.")
    p_bhoonidhi_search.add_argument("--lookback-days", type=int, default=45)
    p_bhoonidhi_search.add_argument("--datetime", default=None, help="RFC3339 interval override.")
    p_bhoonidhi_search.add_argument("--limit", type=int, default=100)
    p_bhoonidhi_search.add_argument("--out-dir", default=None)
    p_bhoonidhi_search.set_defaults(func=cmd_bhoonidhi_search)
    p_bhoonidhi_download = sub.add_parser(
        "bhoonidhi-download",
        help="Download Bhoonidhi products from a search manifest.",
    )
    p_bhoonidhi_download.add_argument("--manifest", required=True)
    p_bhoonidhi_download.add_argument("--source", default=None)
    p_bhoonidhi_download.add_argument("--raw-root", default=None)
    p_bhoonidhi_download.set_defaults(func=cmd_bhoonidhi_download)
    p_composite = sub.add_parser(
        "build-composite",
        help="Build a ResourceSat full-AOI composite from prepared scene manifests.",
    )
    p_composite.add_argument(
        "--source",
        default="resourcesat-2a-liss3-boa",
        help="Akasha source id to composite.",
    )
    p_composite.add_argument(
        "--aoi",
        default="bangalore-60km",
        help="AOI id expected in the AOI config.",
    )
    p_composite.add_argument("--aoi-path", default=None, help="AOI GeoJSON path.")
    p_composite.add_argument("--manifest-glob", help="Glob for scene prepare_manifest.json files.")
    p_composite.add_argument("--output-root", type=Path, default=None)
    p_composite.add_argument("--window-start", required=True, help="Composite period start date.")
    p_composite.add_argument("--window-end", required=True, help="Composite period end date.")
    p_composite.add_argument("--resolution", type=float, default=24.0)
    p_composite.add_argument("--padding-pixels", type=int, default=0)
    p_composite.add_argument("--overwrite", action="store_true")
    p_composite.add_argument("--keep-intermediate", action="store_true")
    p_composite.add_argument("--skip-validation", action="store_true")
    p_composite.set_defaults(func=cmd_build_composite)
    p_verify = sub.add_parser("verify", help="Verify Slice 1 exit criteria.")
    p_verify.add_argument("--collection-id", default=None, help="Collection/source id to verify.")
    p_verify.set_defaults(func=cmd_verify)
    p_verify_cogs = sub.add_parser(
        "verify-cogs",
        help="Verify Phase 2 raster de-risk: Slice 1 criteria + non-empty real COGs.",
    )
    p_verify_cogs.add_argument(
        "--collection-id",
        default=None,
        help="Collection/source id to verify.",
    )
    p_verify_cogs.set_defaults(func=cmd_verify_cogs)
    p_verify_manifest = sub.add_parser(
        "verify-manifest-cogs",
        help="Verify non-empty real COGs for all prepared manifest scenes.",
    )
    p_verify_manifest.add_argument("--manifest-glob", help="Glob for prepare_manifest.json files.")
    p_verify_manifest.add_argument(
        "--collection-id",
        default=None,
        help="Source-scoped manifest collection id.",
    )
    p_verify_manifest.set_defaults(func=cmd_verify_manifest_cogs)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_info(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
