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
    python worker.py bhoonidhi-sync --source resourcesat-2a-liss3-boa --aoi bangalore-60km
    python worker.py build-composite --source resourcesat-2a-liss3-boa --aoi bangalore-60km ...
    python worker.py verify                    # Slice 1 exit criteria
    python worker.py verify-cogs               # Phase 2: + non-empty real COGs
    python worker.py verify-manifest-cogs [--manifest-glob ...]
    python worker.py verify-composite [--manifest ...]
    python worker.py healthcheck               # required env vars present
"""

from __future__ import annotations

import argparse
import os
import subprocess
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
        downloaded.append(
            {
                **candidate,
                "item_id": item_id,
                **result,
                "downloaded_path": result["path"],
                "downloaded_bytes": result["bytes"],
            }
        )
    output = dict(manifest)
    output["downloaded"] = downloaded
    output_path = manifest_path.parent / "download_manifest.json"
    bhoonidhi.write_manifest(output, output_path)
    print(f"downloaded {len(downloaded)} product(s)")
    print(f"manifest: {output_path}")
    return 0


def cmd_build_composite(args: argparse.Namespace) -> int:
    from akasha_ingest import bhoonidhi, composite, config

    if args.source not in config.RESOURCESAT_BOA_COLLECTION_IDS:
        raise SystemExit("build-composite currently supports ResourceSat-2A BOA sources only")
    aoi = bhoonidhi.load_aoi(args.aoi_path or config.AOI_CONFIG_PATH)
    if args.aoi and args.aoi != aoi.get("id"):
        raise SystemExit(f"AOI '{args.aoi}' not found; loaded '{aoi.get('id')}'")
    manifest_paths = composite.scene_manifest_paths_for_window(
        _manifest_paths(args.manifest_glob, args.source),
        window_start=args.window_start,
        window_end=args.window_end,
        source_id=args.source,
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
        source_id=args.source,
        resolution=args.resolution or composite.default_resolution(args.source),
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


def _latest_composite_manifest(source: str, aoi: str):
    from akasha_ingest import config

    root = config.raster_source_root() / source / "composite" / aoi
    manifests = sorted(root.glob("*/prepare_manifest.json"))
    if not manifests:
        raise SystemExit(f"no composite prepare_manifest.json files found under {root}")
    return manifests[-1]


def cmd_verify_composite(args: argparse.Namespace) -> int:
    from akasha_ingest import composite, config

    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else _latest_composite_manifest(
            args.source,
            args.aoi,
        )
    )
    deps = composite.require_raster_deps()
    result = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        source_id=args.source,
        min_coverage_percent=args.min_coverage_percent,
        expected_crs=args.expected_crs,
        expected_resolution=args.expected_resolution,
        resolution_tolerance=args.resolution_tolerance,
        require_overviews=not args.allow_missing_overviews,
        require_catalog_item=args.require_catalog_item,
        stac_api_url=args.stac_api_url or config.STAC_API_URL,
    )
    for check in result.checks:
        print(f"[PASS] {check}")
    for problem in result.problems:
        print(f"[FAIL] {problem}")
    print(result.detail)
    return 0 if result.ok else 1


def _run_prepare_script(args: argparse.Namespace, download_manifest: Path) -> None:
    from akasha_ingest import config, sync

    script = sync.prepare_script_path(Path(__file__).resolve())
    output_root = config.raster_source_root() / args.source
    raw_root = Path(args.raw_root or config.BHOONIDHI_RAW_ROOT) / args.source
    command = [
        sys.executable,
        str(script),
        "--source",
        args.source,
        "--selection-manifest",
        str(download_manifest),
        "--raw-dir",
        str(raw_root),
        "--output-root",
        str(output_root),
        "--skip-validation" if args.skip_prepare_validation else "",
    ]
    command = [part for part in command if part]
    if args.overwrite:
        command.append("--overwrite")
    if args.keep_intermediate:
        command.append("--keep-intermediate")
    print("prepare command: " + " ".join(command))
    subprocess.run(command, check=True)


def cmd_bhoonidhi_sync(args: argparse.Namespace) -> int:
    from akasha_ingest import bhoonidhi, catalog, composite, config, storage, sync

    if args.source not in config.RESOURCESAT_BOA_COLLECTION_IDS:
        raise SystemExit("bhoonidhi-sync currently supports ResourceSat-2A BOA sources only")
    collection = bhoonidhi.source_collection(args.source)
    aoi = bhoonidhi.load_aoi(args.aoi_path or config.AOI_CONFIG_PATH)
    if args.aoi and args.aoi != aoi.get("id"):
        raise SystemExit(f"AOI '{args.aoi}' not found; loaded '{aoi.get('id')}'")
    datetime_range = args.datetime or bhoonidhi.lookback_datetime_range(args.lookback_days)
    out_dir = Path(args.out_dir or config.BHOONIDHI_TEMP_ROOT) / args.source
    search_manifest_path = out_dir / "coverage_manifest.json"
    new_manifest_path = out_dir / "coverage_manifest.new.json"
    download_manifest_path = out_dir / "download_manifest.json"
    ledger_path = Path(args.ledger_path or config.BHOONIDHI_LEDGER_PATH)
    lock_path = (
        Path(args.lock_path)
        if args.lock_path
        else ledger_path.with_suffix(ledger_path.suffix + ".lock")
    )

    lock = None
    try:
        if not args.no_lock:
            try:
                lock = sync.acquire_lock(lock_path)
            except sync.SyncLockError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"sync lock: {lock.path}")

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
        bhoonidhi.write_manifest(manifest, search_manifest_path)

        conn = sync.connect_ledger(ledger_path)
        selection = sync.filter_new_candidates(manifest, conn=conn, source_id=args.source)
        bhoonidhi.write_manifest(selection.manifest, new_manifest_path)
        print(f"found {len(items)} Bhoonidhi item(s)")
        print(f"selected {len(manifest['selection']['selected_product_ids'])} candidate(s)")
        print(f"skipped existing {len(selection.skipped_product_ids)} product(s)")
        print(f"new products {len(selection.selected_product_ids)}")
        print(f"manifest: {new_manifest_path}")
        if args.dry_run:
            print("dry-run: stopping before download/prepare/composite/ingest")
            return 0

        raw_root = Path(args.raw_root or config.BHOONIDHI_RAW_ROOT) / args.source
        downloaded: list[dict[str, object]] = []
        for candidate in selection.manifest.get("candidates", []):
            product_id = candidate.get("item_id")
            if not product_id:
                continue
            try:
                result = client.download_product(
                    product_id=str(product_id),
                    collection=collection,
                    destination=raw_root / f"{product_id}.zip",
                )
                candidate["download_status"] = result["status"]
                candidate["downloaded_path"] = result["path"]
                candidate["downloaded_bytes"] = result["bytes"]
                downloaded.append(
                    {
                        **candidate,
                        "item_id": product_id,
                        **result,
                        "downloaded_path": result["path"],
                        "downloaded_bytes": result["bytes"],
                    }
                )
                sync.record_product(
                    conn,
                    source_id=args.source,
                    product_id=str(product_id),
                    status="downloaded",
                    bytes_count=int(result.get("bytes") or 0),
                )
                print(f"download {product_id}: {result['status']} ({result['bytes']} bytes)")
            except Exception as exc:  # noqa: BLE001
                sync.record_product(
                    conn,
                    source_id=args.source,
                    product_id=str(product_id),
                    status="failed",
                    error=str(exc),
                )
                raise
        download_manifest = dict(selection.manifest)
        download_manifest["downloaded"] = downloaded
        bhoonidhi.write_manifest(download_manifest, download_manifest_path)
        print(f"download manifest: {download_manifest_path}")

        if args.skip_prepare:
            print("skip prepare requested")
            return 0
        if downloaded:
            _run_prepare_script(args, download_manifest_path)
            for row in downloaded:
                sync.record_product(
                    conn,
                    source_id=args.source,
                    product_id=str(row["item_id"]),
                    status="prepared",
                    bytes_count=int(row.get("bytes") or 0),
                )
        else:
            print("no new downloads; using existing prepared manifests for composite rebuild")

        if args.skip_composite:
            print("skip composite requested")
            return 0
        manifest_paths = composite.scene_manifest_paths_for_window(
            config.prepared_manifest_files(source_id=args.source),
            window_start=args.window_start,
            window_end=args.window_end,
            source_id=args.source,
        )
        if not manifest_paths:
            raise SystemExit("no prepared scene manifests found for composite window")
        deps = composite.require_raster_deps()
        build = composite.build_resource_sat_composite(
            deps=deps,
            manifest_paths=manifest_paths,
            aoi=aoi,
            output_root=config.raster_source_root(),
            window_start=args.window_start,
            window_end=args.window_end,
            source_id=args.source,
            resolution=args.resolution or composite.default_resolution(args.source),
            padding_pixels=args.padding_pixels,
            overwrite=args.overwrite,
            skip_validation=args.skip_composite_validation,
            keep_intermediate=args.keep_intermediate,
        )
        verify = composite.verify_composite_manifest(
            deps=deps,
            manifest_path=build.manifest,
            source_id=args.source,
            min_coverage_percent=args.min_coverage_percent,
            require_overviews=not args.allow_missing_overviews,
        )
        if not verify.ok:
            raise SystemExit(verify.detail)
        print(verify.detail)

        if args.skip_ingest:
            print("skip ingest requested")
            return 0
        print(storage.ensure_bucket())
        for line in storage.seed_manifest_cogs([build.manifest], force=args.force):
            print(line)
        print(catalog.load_manifest_items([build.manifest], method=args.method))
        post_ingest = composite.verify_composite_manifest(
            deps=deps,
            manifest_path=build.manifest,
            source_id=args.source,
            min_coverage_percent=args.min_coverage_percent,
            require_overviews=not args.allow_missing_overviews,
            require_catalog_item=True,
            stac_api_url=config.STAC_API_URL,
        )
        if not post_ingest.ok:
            raise SystemExit(post_ingest.detail)
        print(post_ingest.detail)
        sync.record_product(
            conn,
            source_id=args.source,
            product_id=f"composite:{args.aoi}:{build.manifest.parent.name}",
            status="composited",
        )
        deleted = sync.cleanup_downloads(downloaded, audit_retention=args.retain_raw_downloads)
        if deleted:
            print(f"deleted raw downloads: {len(deleted)}")
        return 0
    finally:
        if lock is not None:
            sync.release_lock(lock)


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
    p_sync = sub.add_parser(
        "bhoonidhi-sync",
        help="Search, download, prepare, composite, verify, and ingest ResourceSat scenes.",
    )
    p_sync.add_argument("--source", default="resourcesat-2a-liss3-boa")
    p_sync.add_argument("--aoi", default="bangalore-60km")
    p_sync.add_argument("--aoi-path", default=None)
    p_sync.add_argument("--lookback-days", type=int, default=45)
    p_sync.add_argument("--datetime", default=None)
    p_sync.add_argument("--limit", type=int, default=100)
    p_sync.add_argument("--window-start", required=True)
    p_sync.add_argument("--window-end", required=True)
    p_sync.add_argument("--out-dir", default=None)
    p_sync.add_argument("--raw-root", default=None)
    p_sync.add_argument("--ledger-path", default=None)
    p_sync.add_argument("--lock-path", default=None)
    p_sync.add_argument(
        "--resolution",
        type=float,
        default=None,
        help="Composite grid resolution in meters; defaults from the source profile.",
    )
    p_sync.add_argument("--padding-pixels", type=int, default=0)
    p_sync.add_argument("--min-coverage-percent", type=float, default=95.0)
    p_sync.add_argument("--method", default="upsert", choices=["upsert", "insert_ignore"])
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--overwrite", action="store_true")
    p_sync.add_argument("--force", action="store_true")
    p_sync.add_argument("--no-lock", action="store_true")
    p_sync.add_argument("--retain-raw-downloads", action="store_true")
    p_sync.add_argument("--keep-intermediate", action="store_true")
    p_sync.add_argument("--skip-prepare", action="store_true")
    p_sync.add_argument("--skip-composite", action="store_true")
    p_sync.add_argument("--skip-ingest", action="store_true")
    p_sync.add_argument("--skip-prepare-validation", action="store_true")
    p_sync.add_argument("--skip-composite-validation", action="store_true")
    p_sync.add_argument("--allow-missing-overviews", action="store_true")
    p_sync.set_defaults(func=cmd_bhoonidhi_sync)
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
    p_composite.add_argument(
        "--resolution",
        type=float,
        default=None,
        help="Composite grid resolution in meters; defaults from the source profile.",
    )
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
    p_verify_composite = sub.add_parser(
        "verify-composite",
        help="Verify a ResourceSat full-AOI composite manifest and COGs.",
    )
    p_verify_composite.add_argument(
        "--source",
        default="resourcesat-2a-liss3-boa",
        help="Akasha source id.",
    )
    p_verify_composite.add_argument(
        "--aoi",
        default="bangalore-60km",
        help="AOI id used in the composite layout.",
    )
    p_verify_composite.add_argument("--manifest", help="Composite prepare_manifest.json path.")
    p_verify_composite.add_argument("--min-coverage-percent", type=float, default=95.0)
    p_verify_composite.add_argument("--expected-crs", default="EPSG:32643")
    p_verify_composite.add_argument(
        "--expected-resolution",
        type=float,
        default=None,
        help="Expected output resolution in meters; defaults from the source profile.",
    )
    p_verify_composite.add_argument("--resolution-tolerance", type=float, default=0.25)
    p_verify_composite.add_argument("--allow-missing-overviews", action="store_true")
    p_verify_composite.add_argument(
        "--require-catalog-item",
        action="store_true",
        help="Also require the dated composite item to be present in STAC API.",
    )
    p_verify_composite.add_argument("--stac-api-url", default=None)
    p_verify_composite.set_defaults(func=cmd_verify_composite)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_info(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
