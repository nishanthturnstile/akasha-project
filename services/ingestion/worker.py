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
    python worker.py prepare-context-cog --source cartosat-3-gated --input visual.tif ...
    python worker.py verify                    # configured collection + storage reachability
    python worker.py verify-cogs               # legacy Sentinel sample COG check
    python worker.py verify-manifest-cogs [--manifest-glob ...]
    python worker.py verify-composite [--manifest ...]  # ResourceSat launch acceptance
    python worker.py verify-raster-product --source <sourceId> --manifest <path>
    python worker.py healthcheck               # required env vars present
    python worker.py schedule-plan [--source ...] [--aoi ...] [--json]
    python worker.py schedule-due-sources [--source ...] [--aoi ...]
        [--max-concurrent-source N] [--dry-run]
    python worker.py schedule-source --source <sourceId> --aoi <aoiId>
        [--dry-run] [--approved-runtime]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REQUIRED_ENV: list[str] = [
    "DATABASE_URL",
    "STAC_API_URL",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
]


def _runtime_root() -> Path:
    """Find the repo/container root that contains copied seed data and scripts."""
    here = Path(__file__).resolve()
    for base in (Path.cwd(), *here.parents, Path("/app")):
        if (base / "data" / "seed").is_dir() or (base / "scripts").is_dir():
            return base
    return here.parent


def _default_raster_output_root() -> Path:
    return _runtime_root() / "data" / "seed" / "rasters"


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


def _load_requested_aoi(args: argparse.Namespace) -> dict:
    from akasha_ingest import bhoonidhi, config

    try:
        return bhoonidhi.load_aoi(
            args.aoi_path,
            aoi_id=getattr(args, "aoi", None),
            aoi_dir=getattr(args, "aoi_dir", None) or config.AOI_CONFIG_DIR,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _aoi_id(aoi: dict | None, fallback: str = "unknown-aoi") -> str:
    if not aoi:
        return fallback
    value = aoi.get("id")
    props = aoi.get("properties") if isinstance(aoi.get("properties"), dict) else {}
    return str(value or props.get("id") or fallback)


def _aoi_composite_crs(aoi: dict | None, default: str = "EPSG:32643") -> str:
    from akasha_ingest import composite

    return composite.aoi_composite_grid_crs(aoi, default=default)


def _should_load_aoi_for_verify(args: argparse.Namespace) -> bool:
    from akasha_ingest import config

    return bool(
        getattr(args, "aoi_path", None)
        or getattr(args, "aoi_dir", None)
        or config.AOI_CONFIG_DIR
        or Path(config.AOI_CONFIG_PATH).is_file()
    )


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
        "AOI_CONFIG_DIR",
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
    aoi = _load_requested_aoi(args)
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
    from akasha_ingest.manifests import REDACTION_VERSION
    from akasha_ingest.manifests import redact_value as _redact

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_id = str(manifest.get("source_id") or args.source or "")
    collection = str(manifest.get("collection") or bhoonidhi.source_collection(source_id))
    raw_root = Path(args.raw_root or config.BHOONIDHI_RAW_ROOT) / source_id
    client = bhoonidhi.BhoonidhiClient()
    downloaded: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    candidates = [
        candidate for candidate in manifest.get("candidates", []) if isinstance(candidate, dict)
    ]
    max_downloads = getattr(args, "max_downloads", None)
    if max_downloads is not None and max_downloads > 0:
        deferred_candidates = candidates[max_downloads:]
        candidates = candidates[:max_downloads]
        manifest.setdefault("download", {})["deferred_product_ids"] = [
            str(candidate.get("item_id")) for candidate in deferred_candidates
        ]
        manifest["download"]["max_downloads"] = max_downloads

    output_path = manifest_path.parent / "download_manifest.json"
    try:
        for candidate in candidates:
            item_id = candidate.get("item_id")
            if not item_id:
                continue
            dest = raw_root / f"{item_id}.zip"
            try:
                result = client.download_product(
                    product_id=str(item_id),
                    collection=collection,
                    destination=dest,
                )
            except Exception as exc:  # noqa: BLE001
                candidate["download_status"] = "failed"
                candidate["download_error"] = str(exc)
                failed.append(
                    {
                        "item_id": item_id,
                        **candidate,
                        # canonical fields alongside legacy
                        "itemId": item_id,
                        "errorKind": "unknown",
                        "redactedError": _redact(str(exc)),
                    }
                )
                raise
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
                    # canonical fields alongside legacy
                    "itemId": item_id,
                    "localPath": result["path"],
                    "downloadedBytes": result["bytes"],
                }
            )
    finally:
        output = dict(manifest)
        output["candidates"] = candidates
        output["downloaded"] = downloaded
        output["failed"] = failed
        # Canonical download manifest top-level keys (alongside legacy shape)
        output.setdefault("manifestType", "download")
        output.setdefault("jobId", None)
        output.setdefault("sourceId", source_id)
        output.setdefault("provider", "bhoonidhi")
        output.setdefault("adapter", "bhoonidhi")
        output.setdefault("redactionVersion", REDACTION_VERSION)
        bhoonidhi.write_manifest(output, output_path)
    print(f"downloaded {len(downloaded)} product(s)")
    if failed:
        print(f"failed {len(failed)} product(s)")
    print(f"manifest: {output_path}")
    return 0


def cmd_build_composite(args: argparse.Namespace) -> int:
    from akasha_ingest import composite, config

    if args.source not in config.RESOURCESAT_BOA_COLLECTION_IDS:
        raise SystemExit("build-composite currently supports ResourceSat-2A BOA sources only")
    aoi = _load_requested_aoi(args)
    manifest_paths = composite.scene_manifest_paths_for_window(
        _manifest_paths(args.manifest_glob, args.source),
        window_start=args.window_start,
        window_end=args.window_end,
        source_id=args.source,
        aoi_id=_aoi_id(aoi, args.aoi),
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


def cmd_prepare_context_cog(args: argparse.Namespace) -> int:
    script = _runtime_root() / "scripts" / "prepare_context_cog.py"
    command = [
        sys.executable,
        str(script),
        "--source",
        args.source,
        "--input",
        args.input,
        "--product-id",
        args.product_id,
        "--acquisition-datetime",
        args.acquisition_datetime,
        "--output-root",
        args.output_root,
    ]
    if args.gsd is not None:
        command.extend(["--gsd", str(args.gsd)])
    if args.overwrite:
        command.append("--overwrite")
    if args.skip_validation:
        command.append("--skip-validation")
    subprocess.run(command, check=True)
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


def cmd_verify_raster_product(args: argparse.Namespace) -> int:
    """Validate a prepare_manifest.json against its source/profile constraints.

    TASK-037: source-aware non-composite validation. Validates manifest metadata
    and declared assets against the ValidationProfileSpec — no live provider calls,
    no rasterio required for metadata checks.  If rasterio is available and the
    declared COG files exist on disk, raster-level checks are also run.
    """
    import json

    from akasha_ingest.validation_profiles import (
        ManifestValidationResult,
        get_validation_profile,
        validate_manifest_metadata,
    )

    source_id: str | None = getattr(args, "source", None) or None
    profile_key: str | None = getattr(args, "profile", None) or None

    if not source_id and not profile_key:
        print(
            "ERROR: at least one of --source or --profile is required.",
            file=sys.stderr,
        )
        return 1

    # Source-specific override takes precedence; profile used as fallback.
    lookup_key = source_id or profile_key
    try:
        spec = get_validation_profile(lookup_key)  # type: ignore[arg-type]
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"[FAIL] manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest_data: dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] cannot read manifest: {exc}", file=sys.stderr)
        return 1

    result: ManifestValidationResult = validate_manifest_metadata(
        spec,
        manifest_data,
        source_id=source_id,
    )

    for check in result.checks:
        print(f"[PASS] {check}")
    for problem in result.problems:
        print(f"[FAIL] {problem}")
    print(result.detail)

    if result.ok and not getattr(args, "metadata_only", False):
        # Optional rasterio-based COG validation when files exist locally
        _try_raster_checks(spec, manifest_path, manifest_data)

    return 0 if result.ok else 1


def _try_raster_checks(
    spec,
    manifest_path: Path,
    manifest_data: dict,
) -> None:
    """Run optional rasterio band/CRS/overview checks when deps are available.

    Silently skipped if rasterio is not installed or COG files are not on disk.
    Does NOT raise — failures are printed but do not affect the exit code of
    cmd_verify_raster_product (the metadata check result is authoritative).
    """
    try:
        import rasterio  # noqa: PLC0415
    except ImportError:
        return

    outputs = manifest_data.get("outputs") or {}
    if not isinstance(outputs, dict):
        return

    for asset_key, asset_data in outputs.items():
        if not isinstance(asset_data, dict):
            continue
        rel_path = asset_data.get("path") or asset_data.get("href") or ""
        if not rel_path:
            continue
        cog_path = manifest_path.parent / rel_path
        if not cog_path.is_file():
            continue
        try:
            with rasterio.open(cog_path) as ds:
                print(
                    f"[RASTER] {asset_key}: bands={ds.count} "
                    f"crs={ds.crs} dtype={ds.dtypes[0] if ds.dtypes else 'unknown'}"
                )
                if spec.band_count is not None and "analytic" in asset_key.lower():
                    if ds.count == spec.band_count:
                        print(f"[PASS] raster band count {spec.band_count} matches spec")
                    else:
                        print(
                            f"[WARN] raster band count {ds.count} != spec {spec.band_count}",
                            file=sys.stderr,
                        )
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] rasterio check skipped for {cog_path.name}: {exc}", file=sys.stderr)


def _latest_composite_manifest(source: str, aoi: str):
    from akasha_ingest import config

    root = config.raster_source_root() / source / "composite" / aoi
    manifests = sorted(root.glob("*/prepare_manifest.json"))
    if not manifests:
        raise SystemExit(f"no composite prepare_manifest.json files found under {root}")
    return manifests[-1]


def cmd_verify_composite(args: argparse.Namespace) -> int:
    from akasha_ingest import composite, config
    from akasha_ingest.validation_profiles import profile_for_source

    # TASK-038: verify-composite is a specialisation of optical_composite validation.
    # Reject non-optical-composite sources with an actionable error.
    try:
        spec = profile_for_source(args.source)
    except (KeyError, ValueError):
        spec = None
    if spec is not None and spec.profile_id != "optical_composite":
        print(
            f"ERROR: verify-composite only supports optical_composite sources. "
            f"Source {args.source!r} has profile {spec.profile_id!r}. "
            f"Use 'verify-raster-product --source {args.source} --manifest <path>' instead.",
            file=sys.stderr,
        )
        return 1

    aoi = _load_requested_aoi(args) if _should_load_aoi_for_verify(args) else None
    expected_crs = args.expected_crs or _aoi_composite_crs(aoi)
    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else _latest_composite_manifest(
            args.source,
            _aoi_id(aoi, args.aoi),
        )
    )
    deps = composite.require_raster_deps()
    result = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        source_id=args.source,
        expected_aoi_id=_aoi_id(aoi, args.aoi),
        min_coverage_percent=args.min_coverage_percent,
        expected_crs=expected_crs,
        expected_resolution=args.expected_resolution,
        resolution_tolerance=args.resolution_tolerance,
        require_overviews=not args.allow_missing_overviews,
        require_catalog_item=not args.local_only,
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

    script = sync.prepare_script_path(args.source, Path(__file__).resolve())
    output_root = config.raster_source_root() / args.source
    raw_root = Path(args.raw_root or config.BHOONIDHI_RAW_ROOT) / args.source
    work_dir = (
        Path(args.out_dir or config.BHOONIDHI_TEMP_ROOT)
        / args.source
        / _aoi_id(None, args.aoi)
        / "prepare"
    )
    command = [
        sys.executable,
        str(script),
        "--source",
        args.source,
        "--selection-manifest",
        str(download_manifest),
        "--raw-dir",
        str(raw_root),
        "--work-dir",
        str(work_dir),
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


def _composite_ledger_product_id(
    args: argparse.Namespace, aoi: dict | None = None, suffix: str = "pending"
) -> str:
    window_start = args.window_start or "latest"
    window_end = args.window_end or "latest"
    return f"composite:{_aoi_id(aoi, args.aoi)}:{window_start}:{window_end}:{suffix}"


def _max_downloads_per_sync(args: argparse.Namespace) -> int | None:
    from akasha_ingest import config as ingest_config

    raw = getattr(args, "max_downloads", None)
    if raw is None:
        raw = ingest_config.BHOONIDHI_MAX_DOWNLOADS_PER_SYNC
    if raw in (None, ""):
        return None
    value = int(raw)
    return value if value > 0 else None


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _resolve_sync_window(args: argparse.Namespace, *, aoi_id: str, ledger_path: Path):
    from akasha_ingest import sync

    if getattr(args, "backfill_days", 0) and int(args.backfill_days) > 0:
        anchor = (
            _parse_date(args.backfill_anchor_date)
            if args.backfill_anchor_date
            else datetime.now(UTC).date()
        )
        window_days = int(args.window_days)
        step_days = int(args.backfill_step_days or args.window_days)
        state_path = Path(args.backfill_state_path or ledger_path.with_suffix(".backfill.json"))
        return sync.next_backfill_window(
            state_path,
            source_id=args.source,
            aoi_id=aoi_id,
            anchor_date=anchor,
            history_days=int(args.backfill_days),
            window_days=window_days,
            step_days=step_days,
            advance=not args.dry_run,
        )

    window_end = args.window_end or datetime.now(UTC).date().isoformat()
    window_start = args.window_start or (
        _parse_date(window_end) - timedelta(days=int(args.window_days) - 1)
    ).isoformat()
    return sync.SyncWindow(
        window_start=window_start,
        window_end=window_end,
        datetime_range=sync.datetime_range_for_window(window_start, window_end),
    )


def cmd_bhoonidhi_sync(args: argparse.Namespace) -> int:
    from akasha_ingest import config, sync
    from akasha_ingest import resourcesat_pipeline as rp

    if args.source not in config.RESOURCESAT_BOA_COLLECTION_IDS:
        raise SystemExit("bhoonidhi-sync currently supports ResourceSat-2A BOA sources only")
    aoi = _load_requested_aoi(args)
    aoi_id = _aoi_id(aoi, args.aoi)
    ledger_path = Path(args.ledger_path or config.BHOONIDHI_LEDGER_PATH)
    sync_window = _resolve_sync_window(args, aoi_id=aoi_id, ledger_path=ledger_path)
    datetime_range = args.datetime or sync_window.datetime_range
    lock_path = (
        Path(args.lock_path)
        if args.lock_path
        else ledger_path.with_suffix(ledger_path.suffix + ".lock")
    )
    params = rp.IngestParams(
        source_id=args.source,
        aoi=aoi,
        aoi_id=aoi_id,
        window_start=sync_window.window_start,
        window_end=sync_window.window_end,
        datetime_range=datetime_range,
        limit=args.limit,
        max_downloads=_max_downloads_per_sync(args),
        min_coverage_percent=args.min_coverage_percent,
        resolution=args.resolution,
        padding_pixels=args.padding_pixels,
        method=args.method,
        out_dir=args.out_dir,
        raw_root=args.raw_root,
        ledger_path=ledger_path,
        overwrite=args.overwrite,
        keep_intermediate=args.keep_intermediate,
        force=args.force,
        skip_prepare=args.skip_prepare,
        skip_prepare_validation=args.skip_prepare_validation,
        skip_composite=args.skip_composite,
        skip_composite_validation=args.skip_composite_validation,
        skip_ingest=args.skip_ingest,
        allow_missing_overviews=args.allow_missing_overviews,
        retain_raw_downloads=args.retain_raw_downloads,
        dry_run=args.dry_run,
        backfill_index=sync_window.backfill_index,
        backfill_total=sync_window.backfill_total,
    )

    lock = None
    try:
        if not args.no_lock:
            try:
                lock = sync.acquire_lock(lock_path)
            except sync.SyncLockError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"sync lock: {lock.path}")

        rp.run_resourcesat_ingest(
            params,
            log=print,
            prepare_fn=lambda dm: _run_prepare_script(args, dm),
        )
        return 0
    finally:
        if lock is not None:
            sync.release_lock(lock)


def cmd_schedule_plan(args: argparse.Namespace) -> int:
    import json as _json

    from akasha_ingest.jobs import DEFAULT_JOB_BASE_DIR
    from akasha_ingest.orchestrator import plan_due_sources

    source_ids = [args.source] if getattr(args, "source", None) else None
    aoi_ids = [args.aoi] if getattr(args, "aoi", None) else None
    base_dir = getattr(args, "base_dir", None) or DEFAULT_JOB_BASE_DIR
    lookback_days = int(getattr(args, "window_days", None) or 12)

    decisions = plan_due_sources(
        source_ids=source_ids,
        aoi_ids=aoi_ids,
        base_dir=base_dir,
        lookback_days=lookback_days,
    )

    if getattr(args, "json", False):
        print(_json.dumps([d.to_dict() for d in decisions], indent=2))
        return 0

    due = [d for d in decisions if d.is_due]
    skipped = [d for d in decisions if not d.is_due]
    print(f"schedule-plan: {len(decisions)} source/AOI pair(s) evaluated.")
    print(f"  due:     {len(due)}")
    print(f"  skipped: {len(skipped)}")
    for d in due:
        print(f"  [DUE]  {d.source_id}/{d.aoi_id}  window={d.window_start}..{d.window_end}")
    for d in skipped:
        print(f"  [SKIP] {d.source_id}/{d.aoi_id}  reason={d.skip_reason}")
    return 0


def cmd_schedule_due_sources(args: argparse.Namespace) -> int:
    import json as _json

    from akasha_ingest.job_ledger import DEFAULT_LEDGER_DB
    from akasha_ingest.jobs import DEFAULT_JOB_BASE_DIR
    from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR, plan_due_sources, run_due_sources

    source_ids = [args.source] if getattr(args, "source", None) else None
    aoi_ids = [args.aoi] if getattr(args, "aoi", None) else None
    base_dir = getattr(args, "base_dir", None) or DEFAULT_JOB_BASE_DIR
    lock_dir = getattr(args, "lock_dir", None) or DEFAULT_LOCK_DIR
    ledger_db_path = getattr(args, "ledger_db_path", None) or DEFAULT_LEDGER_DB
    lookback_days = int(getattr(args, "window_days", None) or 12)
    max_sources = int(getattr(args, "max_concurrent_source", None) or 5)
    dry_run = bool(getattr(args, "dry_run", False))
    local_test = bool(getattr(args, "local_test", False))
    approved_runtime = bool(getattr(args, "approved_runtime", False))

    decisions = plan_due_sources(
        source_ids=source_ids,
        aoi_ids=aoi_ids,
        base_dir=base_dir,
        lookback_days=lookback_days,
    )

    results = run_due_sources(
        decisions,
        dry_run=dry_run,
        local_test=local_test,
        approved_runtime=approved_runtime,
        max_sources=max_sources,
        base_dir=base_dir,
        lock_dir=lock_dir,
        lookback_days=lookback_days,
        use_global_lock=True,
        ledger_db_path=ledger_db_path,
    )

    if getattr(args, "json", False):
        print(_json.dumps([r.to_dict() for r in results], indent=2))
    else:
        due_count = sum(1 for d in decisions if d.is_due)
        print(
            f"schedule-due-sources: {due_count} due / {len(decisions)} evaluated; "
            f"{len(results)} job(s) attempted."
        )
        for r in results:
            info = f"  [{r.status.upper()}] {r.source_id}/{r.aoi_id}"
            if r.failure_kind:
                info += f"  failureKind={r.failure_kind}"
            print(info)

    failed = [r for r in results if r.status in ("failed", "validation_failed")]
    return 1 if failed else 0


def cmd_schedule_source(args: argparse.Namespace) -> int:
    import json as _json

    from akasha_ingest.job_ledger import DEFAULT_LEDGER_DB
    from akasha_ingest.jobs import DEFAULT_JOB_BASE_DIR
    from akasha_ingest.orchestrator import DEFAULT_LOCK_DIR, run_source_job

    source_id = args.source
    aoi_id = args.aoi
    base_dir = getattr(args, "base_dir", None) or DEFAULT_JOB_BASE_DIR
    lock_dir = getattr(args, "lock_dir", None) or DEFAULT_LOCK_DIR
    ledger_db_path = getattr(args, "ledger_db_path", None) or DEFAULT_LEDGER_DB
    lookback_days = int(getattr(args, "window_days", None) or 12)
    dry_run = bool(getattr(args, "dry_run", False))
    local_test = bool(getattr(args, "local_test", False))
    approved_runtime = bool(getattr(args, "approved_runtime", False))
    trigger = "manual" if getattr(args, "manual", False) else "scheduler"

    try:
        result = run_source_job(
            source_id,
            aoi_id,
            dry_run=dry_run,
            local_test=local_test,
            approved_runtime=approved_runtime,
            trigger=trigger,
            base_dir=base_dir,
            lock_dir=lock_dir,
            lookback_days=lookback_days,
            ledger_db_path=ledger_db_path,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(_json.dumps(result.to_dict(), indent=2))
    else:
        print(f"schedule-source: {source_id}/{aoi_id}")
        print(f"  job_id: {result.job_id}")
        print(f"  status: {result.status}")
        if result.failure_kind:
            print(f"  failureKind: {result.failure_kind}")
        if result.failure_message:
            print(f"  failureMessage: {result.failure_message}")

    # Fail closed: non-dry-run staging-only execution without approval → exit 1
    if result.failure_kind == "approved_runtime_required":
        print(f"ERROR: {result.failure_message}", file=sys.stderr)
        return 1

    return 0 if result.status not in ("failed", "validation_failed") else 1


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
    p_bhoonidhi_search.add_argument(
        "--aoi-dir",
        default=None,
        help="Directory of AOI GeoJSON files.",
    )
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
    p_bhoonidhi_download.add_argument(
        "--max-downloads",
        type=int,
        default=None,
        help="Maximum products to download from this manifest in one run.",
    )
    p_bhoonidhi_download.set_defaults(func=cmd_bhoonidhi_download)
    p_sync = sub.add_parser(
        "bhoonidhi-sync",
        help="Search, download, prepare, composite, verify, and ingest ResourceSat scenes.",
    )
    p_sync.add_argument("--source", default="resourcesat-2a-liss3-boa")
    p_sync.add_argument("--aoi", default="bangalore-60km")
    p_sync.add_argument("--aoi-path", default=None)
    p_sync.add_argument("--aoi-dir", default=None)
    p_sync.add_argument("--lookback-days", type=int, default=45)
    p_sync.add_argument("--datetime", default=None)
    p_sync.add_argument("--limit", type=int, default=100)
    p_sync.add_argument("--window-start", default=None)
    p_sync.add_argument("--window-end", default=None)
    p_sync.add_argument(
        "--window-days",
        type=int,
        default=45,
        help="Rolling composite window size when window-start/window-end are omitted.",
    )
    p_sync.add_argument(
        "--backfill-days",
        type=int,
        default=0,
        help="Rotate through this many historical days, one bounded window per run.",
    )
    p_sync.add_argument(
        "--backfill-step-days",
        type=int,
        default=None,
        help="Days to advance between backfill windows; defaults to window-days.",
    )
    p_sync.add_argument(
        "--backfill-anchor-date",
        default=None,
        help="YYYY-MM-DD anchor date for deterministic launch backfills; defaults to today UTC.",
    )
    p_sync.add_argument(
        "--backfill-state-path",
        default=None,
        help="JSON state file tracking the next scheduled backfill window.",
    )
    p_sync.add_argument("--out-dir", default=None)
    p_sync.add_argument("--raw-root", default=None)
    p_sync.add_argument("--ledger-path", default=None)
    p_sync.add_argument("--lock-path", default=None)
    p_sync.add_argument(
        "--max-downloads",
        type=int,
        default=None,
        help=(
            "Maximum new products to download in one sync run; defaults to "
            "BHOONIDHI_MAX_DOWNLOADS_PER_SYNC. Use 0 for no cap."
        ),
    )
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
    p_composite.add_argument("--aoi-dir", default=None, help="Directory of AOI GeoJSON files.")
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
    p_context = sub.add_parser(
        "prepare-context-cog",
        help="Prepare an operator-provided context GeoTIFF as a COG + manifest.",
    )
    p_context.add_argument(
        "--source",
        default="cartosat-3-gated",
        choices=["cartosat-3-gated", "eos-06-ocm-lac-ndvi-8day-360m"],
    )
    p_context.add_argument("--input", required=True, help="Operator-provided GeoTIFF.")
    p_context.add_argument("--product-id", required=True, help="Stable product/order id.")
    p_context.add_argument("--acquisition-datetime", required=True)
    p_context.add_argument(
        "--output-root",
        default=str(_default_raster_output_root()),
    )
    p_context.add_argument("--gsd", type=float, default=None)
    p_context.add_argument("--overwrite", action="store_true")
    p_context.add_argument("--skip-validation", action="store_true")
    p_context.set_defaults(func=cmd_prepare_context_cog)
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
    p_verify_raster = sub.add_parser(
        "verify-raster-product",
        help=(
            "Validate a prepare_manifest.json against source/profile constraints "
            "(TASK-037). No live provider calls; rasterio optional."
        ),
    )
    p_verify_raster.add_argument(
        "--source",
        default=None,
        help=(
            "Akasha source id (e.g. resourcesat-2a-liss3-boa, eos-04-sar-mrs-l2b). "
            "Uses source-specific profile override when available. "
            "At least one of --source or --profile is required."
        ),
    )
    p_verify_raster.add_argument(
        "--profile",
        default=None,
        help=(
            "Validation profile id or plan-doc alias "
            "(optical_composite, optical_scene, sar_backscatter, "
            "precomputed_context, archive_only, visual_only, "
            "context_raster, archive_optical, vhr_visual). "
            "Used as fallback when --source is not given."
        ),
    )
    p_verify_raster.add_argument(
        "--manifest",
        required=True,
        help="Path to prepare_manifest.json to validate.",
    )
    p_verify_raster.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip optional rasterio COG checks even when rasterio is available.",
    )
    p_verify_raster.set_defaults(func=cmd_verify_raster_product)
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
    p_verify_composite.add_argument("--aoi-path", default=None, help="AOI GeoJSON path.")
    p_verify_composite.add_argument(
        "--aoi-dir",
        default=None,
        help="Directory of AOI GeoJSON files.",
    )
    p_verify_composite.add_argument("--manifest", help="Composite prepare_manifest.json path.")
    p_verify_composite.add_argument("--min-coverage-percent", type=float, default=95.0)
    p_verify_composite.add_argument(
        "--expected-crs",
        default=None,
        help="Expected output CRS; defaults to the selected AOI compositeGridCrs or EPSG:32643.",
    )
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
        help="Deprecated: catalog item verification is required unless --local-only is set.",
    )
    p_verify_composite.add_argument(
        "--local-only",
        action="store_true",
        help="Only verify local composite files; skip the default STAC catalog item check.",
    )
    p_verify_composite.add_argument("--stac-api-url", default=None)
    p_verify_composite.set_defaults(func=cmd_verify_composite)

    # ── Scheduler / orchestrator commands (TASK-023, TASK-024, TASK-025) ─────
    p_sched_plan = sub.add_parser(
        "schedule-plan",
        help="Print due-source decisions without making any provider calls.",
    )
    p_sched_plan.add_argument(
        "--source",
        default=None,
        help="Restrict plan to this source ID (default: all sources).",
    )
    p_sched_plan.add_argument(
        "--aoi",
        default=None,
        help="Restrict plan to this AOI ID (default: each source's default AOIs).",
    )
    p_sched_plan.add_argument(
        "--window-days",
        type=int,
        default=12,
        help="Lookback window width in days for the proposed search window (default: 12).",
    )
    p_sched_plan.add_argument(
        "--base-dir",
        default=None,
        help="Root directory for job artifacts and the scheduler ledger.",
    )
    p_sched_plan.add_argument(
        "--json",
        action="store_true",
        help="Emit decisions as a JSON array (deterministic for tests).",
    )
    p_sched_plan.set_defaults(func=cmd_schedule_plan)

    p_sched_due = sub.add_parser(
        "schedule-due-sources",
        help="Execute all due sources from the registry with concurrency and budget limits.",
    )
    p_sched_due.add_argument(
        "--source",
        default=None,
        help="Restrict execution to this source ID (default: all due sources).",
    )
    p_sched_due.add_argument(
        "--aoi",
        default=None,
        help="Restrict execution to this AOI ID.",
    )
    p_sched_due.add_argument(
        "--window-days",
        type=int,
        default=12,
        help="Lookback window width in days (default: 12).",
    )
    p_sched_due.add_argument(
        "--base-dir",
        default=None,
        help="Root directory for job artifacts and the scheduler ledger.",
    )
    p_sched_due.add_argument(
        "--lock-dir",
        default=None,
        help="Directory for scheduler and worker lock files.",
    )
    p_sched_due.add_argument(
        "--ledger-db-path",
        default=None,
        help="SQLite job ledger path used by BFF monitoring.",
    )
    p_sched_due.add_argument(
        "--max-concurrent-source",
        type=int,
        default=5,
        dest="max_concurrent_source",
        help="Maximum due sources to run in one scheduler pass (default: 5).",
    )
    p_sched_due.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only — create job artifacts but make no provider calls.",
    )
    p_sched_due.add_argument(
        "--approved-runtime",
        action="store_true",
        help="Explicitly approve non-dry-run execution for staging-only providers.",
    )
    p_sched_due.add_argument(
        "--local-test",
        action="store_true",
        help="Alias for --dry-run; intended for test harnesses.",
    )
    p_sched_due.add_argument(
        "--json",
        action="store_true",
        help="Emit job results as a JSON array.",
    )
    p_sched_due.set_defaults(func=cmd_schedule_due_sources)

    p_sched_src = sub.add_parser(
        "schedule-source",
        help="Run a single source/AOI through the orchestrator.",
    )
    p_sched_src.add_argument(
        "--source",
        required=True,
        help="Source ID from the source registry (e.g. resourcesat-2a-liss3-boa).",
    )
    p_sched_src.add_argument(
        "--aoi",
        required=True,
        help="AOI ID (e.g. bangalore-60km).",
    )
    p_sched_src.add_argument(
        "--window-days",
        type=int,
        default=12,
        help="Lookback window width in days (default: 12).",
    )
    p_sched_src.add_argument(
        "--base-dir",
        default=None,
        help="Root directory for job artifacts and the scheduler ledger.",
    )
    p_sched_src.add_argument(
        "--lock-dir",
        default=None,
        help="Directory for scheduler and worker lock files.",
    )
    p_sched_src.add_argument(
        "--ledger-db-path",
        default=None,
        help="SQLite job ledger path used by BFF monitoring.",
    )
    p_sched_src.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only — create job artifacts but make no provider calls.",
    )
    p_sched_src.add_argument(
        "--manual",
        action="store_true",
        help="Record trigger as 'manual' (vs 'scheduler') in job artifacts.",
    )
    p_sched_src.add_argument(
        "--approved-runtime",
        action="store_true",
        help="Explicitly approve non-dry-run execution for staging-only providers.",
    )
    p_sched_src.add_argument(
        "--local-test",
        action="store_true",
        help="Alias for --dry-run; intended for test harnesses.",
    )
    p_sched_src.add_argument(
        "--json",
        action="store_true",
        help="Emit job result as a JSON object.",
    )
    p_sched_src.set_defaults(func=cmd_schedule_source)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_info(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
