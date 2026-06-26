"""Reusable ResourceSat/Bhoonidhi ingestion pipeline.

This module owns the *data pipeline* for ISRO ResourceSat BOA sources
(LISS-3 / LISS-4 / AWiFS): search -> filter -> download -> prepare -> composite
-> verify -> upload -> STAC load -> post-verify -> cleanup.

It is provider/runtime-agnostic about *orchestration*:

* It does **not** acquire scheduler/worker locks (the caller owns locking).
* It does **not** resolve the AOI or the time window (the caller passes them).
* It does **not** decide cadence or due-state.

Callers:

* The generic scheduler orchestrator (:mod:`akasha_ingest.orchestrator`) wraps a
  worker lock around this function and maps the :class:`IngestResult` /
  exceptions onto the scheduler job lifecycle.

Failure behaviour is preserved from the original ``worker.py bhoonidhi-sync``
command: each stage records the failing product into the SQLite product ledger
and then **re-raises the original exception** so callers see the true error.

Heavy geospatial dependencies (rasterio via ``composite``) are imported lazily
inside :func:`run_resourcesat_ingest` so importing this module stays cheap.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["IngestParams", "IngestResult", "run_resourcesat_ingest"]


@dataclass
class IngestParams:
    """Inputs for one ResourceSat ingestion run over a resolved AOI/window."""

    source_id: str
    aoi: dict[str, Any]
    aoi_id: str
    window_start: str
    window_end: str
    datetime_range: str
    limit: int = 100
    max_downloads: int | None = None
    min_coverage_percent: float = 95.0
    resolution: float | None = None
    padding_pixels: int = 0
    method: str = "upsert"
    out_dir: str | Path | None = None
    raw_root: str | Path | None = None
    ledger_path: str | Path | None = None
    overwrite: bool = False
    keep_intermediate: bool = False
    force: bool = False
    skip_prepare: bool = False
    skip_prepare_validation: bool = False
    skip_composite: bool = False
    skip_composite_validation: bool = False
    skip_ingest: bool = False
    allow_missing_overviews: bool = False
    retain_raw_downloads: bool = False
    dry_run: bool = False
    backfill_index: int | None = None
    backfill_total: int | None = None


@dataclass
class IngestResult:
    """Outcome of a ResourceSat ingestion run (success / early-exit only).

    Stage failures re-raise the original exception rather than returning.
    """

    source_id: str
    aoi_id: str
    window_start: str
    window_end: str
    verdict: str
    detail: str = ""
    found_count: int = 0
    selected_count: int = 0
    skipped_count: int = 0
    downloaded_count: int = 0
    deferred_count: int = 0
    deferred_product_ids: list[str] = field(default_factory=list)
    prepared: bool = False
    composite_built: bool = False
    composite_manifest_path: str | None = None
    ingested: bool = False
    coverage_met: bool = False
    search_manifest_path: str | None = None
    download_manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "aoiId": self.aoi_id,
            "windowStart": self.window_start,
            "windowEnd": self.window_end,
            "verdict": self.verdict,
            "detail": self.detail,
            "foundCount": self.found_count,
            "selectedCount": self.selected_count,
            "skippedCount": self.skipped_count,
            "downloadedCount": self.downloaded_count,
            "deferredCount": self.deferred_count,
            "deferredProductIds": list(self.deferred_product_ids),
            "prepared": self.prepared,
            "compositeBuilt": self.composite_built,
            "compositeManifestPath": self.composite_manifest_path,
            "ingested": self.ingested,
            "coverageMet": self.coverage_met,
            "searchManifestPath": self.search_manifest_path,
            "downloadManifestPath": self.download_manifest_path,
        }


def _composite_ledger_product_id(
    aoi_id: str, window_start: str | None, window_end: str | None, suffix: str = "pending"
) -> str:
    ws = window_start or "latest"
    we = window_end or "latest"
    return f"composite:{aoi_id}:{ws}:{we}:{suffix}"


def _run_prepare(
    params: IngestParams,
    download_manifest_path: Path,
    *,
    log: Callable[[str], None],
) -> None:
    """Invoke the source-specific prepare script as a subprocess (SAFE/JP2 -> COGs)."""
    from akasha_ingest import config, sync

    script = sync.prepare_script_path(params.source_id, Path(__file__).resolve())
    output_root = config.raster_source_root() / params.source_id
    raw_root = Path(params.raw_root or config.BHOONIDHI_RAW_ROOT) / params.source_id
    work_dir = (
        Path(params.out_dir or config.BHOONIDHI_TEMP_ROOT)
        / params.source_id
        / params.aoi_id
        / "prepare"
    )
    command = [
        sys.executable,
        str(script),
        "--source",
        params.source_id,
        "--selection-manifest",
        str(download_manifest_path),
        "--raw-dir",
        str(raw_root),
        "--work-dir",
        str(work_dir),
        "--output-root",
        str(output_root),
    ]
    if params.skip_prepare_validation:
        command.append("--skip-validation")
    if params.overwrite:
        command.append("--overwrite")
    if params.keep_intermediate:
        command.append("--keep-intermediate")
    log("prepare command: " + " ".join(command))
    subprocess.run(command, check=True)


def run_resourcesat_ingest(
    params: IngestParams,
    *,
    log: Callable[[str], None] = print,
    prepare_fn: Callable[[Path], None] | None = None,
) -> IngestResult:
    """Run the full ResourceSat ingestion pipeline for one AOI/window.

    The caller is responsible for locking, AOI loading, and window resolution.
    On stage failure the failing product is recorded in the product ledger and
    the original exception is re-raised.

    ``prepare_fn`` optionally overrides the SAFE/JP2 -> COG prepare step with a
    caller-supplied callable taking the download-manifest path; when ``None``
    the module-internal :func:`_run_prepare` subprocess is used.
    """
    from akasha_ingest import bhoonidhi, catalog, composite, config, storage, sync
    from akasha_ingest.manifests import REDACTION_VERSION

    if params.source_id not in config.RESOURCESAT_BOA_COLLECTION_IDS:
        raise SystemExit(
            "resourcesat ingestion currently supports ResourceSat-2A BOA sources only"
        )

    collection = bhoonidhi.source_collection(params.source_id)
    aoi = params.aoi
    aoi_id = params.aoi_id
    out_dir = Path(params.out_dir or config.BHOONIDHI_TEMP_ROOT) / params.source_id / aoi_id
    search_manifest_path = out_dir / "coverage_manifest.json"
    new_manifest_path = out_dir / "coverage_manifest.new.json"
    download_manifest_path = out_dir / "download_manifest.json"
    ledger_path = Path(params.ledger_path or config.BHOONIDHI_LEDGER_PATH)
    datetime_range = params.datetime_range

    client = bhoonidhi.BhoonidhiClient()
    conn = sync.connect_ledger(ledger_path)
    search_product_id = f"sync:{aoi_id}:{datetime_range}"
    try:
        items = client.search(
            collection=collection,
            datetime_range=datetime_range,
            intersects=aoi["geometry"],
            limit=params.limit,
        )
    except Exception as exc:  # noqa: BLE001
        sync.record_product(
            conn,
            source_id=params.source_id,
            product_id=search_product_id,
            status="failed",
            error=f"Bhoonidhi search failed: {exc}",
        )
        raise
    sync.record_product(
        conn,
        source_id=params.source_id,
        product_id=search_product_id,
        status="searched",
    )
    manifest = bhoonidhi.build_search_manifest(
        source_id=params.source_id,
        collection=collection,
        aoi=aoi,
        datetime_range=datetime_range,
        items=items,
    )
    bhoonidhi.write_manifest(manifest, search_manifest_path)

    selection = sync.filter_new_candidates(manifest, conn=conn, source_id=params.source_id)
    sync_meta = selection.manifest.setdefault("sync", {})
    sync_meta["window_start"] = params.window_start
    sync_meta["window_end"] = params.window_end
    sync_meta["datetime_range"] = datetime_range
    if params.backfill_index and params.backfill_total:
        sync_meta["backfill_index"] = params.backfill_index
        sync_meta["backfill_total"] = params.backfill_total
    max_downloads = params.max_downloads
    deferred_product_ids: list[str] = []
    if max_downloads is not None and len(selection.selected_product_ids) > max_downloads:
        candidates = selection.manifest.get("candidates", [])
        deferred_candidates = candidates[max_downloads:]
        deferred_product_ids = [
            str(candidate.get("item_id")) for candidate in deferred_candidates
        ]
        selection.manifest["candidates"] = candidates[:max_downloads]
        selection.manifest["selection"] = {
            "selected_product_ids": selection.selected_product_ids[:max_downloads]
        }
        sync_meta["deferred_product_ids"] = deferred_product_ids
        sync_meta["max_downloads_per_sync"] = max_downloads
    bhoonidhi.write_manifest(selection.manifest, new_manifest_path)
    selected_count = len(manifest["selection"]["selected_product_ids"])
    log(f"found {len(items)} Bhoonidhi item(s)")
    log(f"selected {selected_count} candidate(s)")
    log(f"skipped existing {len(selection.skipped_product_ids)} product(s)")
    log(f"new products {len(selection.selected_product_ids)}")
    log(f"sync window: {params.window_start}..{params.window_end}")
    if params.backfill_index and params.backfill_total:
        log(f"backfill window {params.backfill_index}/{params.backfill_total}")
    if deferred_product_ids:
        log(
            f"deferred {len(deferred_product_ids)} product(s) due to max downloads per sync "
            f"({max_downloads})"
        )
    log(f"manifest: {new_manifest_path}")

    base_result = IngestResult(
        source_id=params.source_id,
        aoi_id=aoi_id,
        window_start=params.window_start,
        window_end=params.window_end,
        verdict="succeeded",
        found_count=len(items),
        selected_count=selected_count,
        skipped_count=len(selection.skipped_product_ids),
        deferred_count=len(deferred_product_ids),
        deferred_product_ids=deferred_product_ids,
        search_manifest_path=str(search_manifest_path),
    )

    if params.dry_run:
        log("dry-run: stopping before download/prepare/composite/ingest")
        base_result.verdict = "dry_run"
        base_result.detail = "dry-run: stopped before download/prepare/composite/ingest"
        return base_result

    raw_root = Path(params.raw_root or config.BHOONIDHI_RAW_ROOT) / params.source_id
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
                    "itemId": product_id,
                    "localPath": result["path"],
                    "downloadedBytes": result["bytes"],
                }
            )
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=str(product_id),
                status="downloaded",
                bytes_count=int(result.get("bytes") or 0),
            )
            log(f"download {product_id}: {result['status']} ({result['bytes']} bytes)")
        except Exception as exc:  # noqa: BLE001
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=str(product_id),
                status="failed",
                error=f"download failed: {exc}",
            )
            raise
    download_manifest = dict(selection.manifest)
    download_manifest["downloaded"] = downloaded
    download_manifest["manifestType"] = "download"
    download_manifest.setdefault("jobId", None)
    download_manifest.setdefault("sourceId", params.source_id)
    download_manifest.setdefault("provider", "bhoonidhi")
    download_manifest.setdefault("adapter", "bhoonidhi")
    download_manifest.setdefault("redactionVersion", REDACTION_VERSION)
    bhoonidhi.write_manifest(download_manifest, download_manifest_path)
    log(f"download manifest: {download_manifest_path}")
    base_result.downloaded_count = len(downloaded)
    base_result.download_manifest_path = str(download_manifest_path)

    if params.skip_prepare:
        log("skip prepare requested")
        base_result.verdict = "skipped_prepare"
        return base_result
    if downloaded:
        try:
            if prepare_fn is not None:
                prepare_fn(download_manifest_path)
            else:
                _run_prepare(params, download_manifest_path, log=log)
        except Exception as exc:  # noqa: BLE001
            for row in downloaded:
                sync.record_product(
                    conn,
                    source_id=params.source_id,
                    product_id=str(row["item_id"]),
                    status="failed",
                    bytes_count=int(row.get("bytes") or 0),
                    error=f"conversion failed: {exc}",
                )
            raise
        for row in downloaded:
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=str(row["item_id"]),
                status="prepared",
                bytes_count=int(row.get("bytes") or 0),
            )
        base_result.prepared = True
    else:
        log("no new downloads; using existing prepared manifests for composite rebuild")

    if params.skip_composite:
        log("skip composite requested")
        base_result.verdict = "skipped_composite"
        return base_result
    composite_product_id = _composite_ledger_product_id(
        aoi_id, params.window_start, params.window_end
    )
    try:
        manifest_paths = composite.scene_manifest_paths_for_window(
            config.prepared_manifest_files(source_id=params.source_id),
            window_start=params.window_start,
            window_end=params.window_end,
            source_id=params.source_id,
            aoi_id=aoi_id,
        )
        if not manifest_paths:
            detail = "no prepared scene manifests found for composite window"
            if not selection.manifest.get("candidates"):
                log(f"{detail}; no new candidates found, skipping composite rebuild")
                base_result.verdict = "no_new_candidates"
                base_result.detail = detail
                return base_result
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=composite_product_id,
                status="failed",
                error=f"composite failed: {detail}",
            )
            raise SystemExit(detail)
        deps = composite.require_raster_deps()
        build = composite.build_resource_sat_composite(
            deps=deps,
            manifest_paths=manifest_paths,
            aoi=aoi,
            output_root=config.raster_source_root(),
            window_start=params.window_start,
            window_end=params.window_end,
            source_id=params.source_id,
            resolution=params.resolution or composite.default_resolution(params.source_id),
            padding_pixels=params.padding_pixels,
            overwrite=params.overwrite,
            skip_validation=params.skip_composite_validation,
            keep_intermediate=params.keep_intermediate,
        )
        composite_product_id = f"composite:{aoi_id}:{build.manifest.parent.name}"
        verify = composite.verify_composite_manifest(
            deps=deps,
            manifest_path=build.manifest,
            source_id=params.source_id,
            expected_aoi_id=aoi_id,
            min_coverage_percent=params.min_coverage_percent,
            require_overviews=not params.allow_missing_overviews,
        )
        if not verify.ok:
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=composite_product_id,
                status="failed",
                error=f"composite failed: {verify.detail}",
            )
            raise SystemExit(verify.detail)
    except Exception as exc:  # noqa: BLE001
        sync.record_product(
            conn,
            source_id=params.source_id,
            product_id=composite_product_id,
            status="failed",
            error=f"composite failed: {exc}",
        )
        raise
    log(verify.detail)
    base_result.composite_built = True
    base_result.composite_manifest_path = str(build.manifest)
    base_result.coverage_met = True

    if params.skip_ingest:
        log("skip ingest requested")
        base_result.verdict = "skipped_ingest"
        return base_result
    try:
        log(storage.ensure_bucket())
        for line in storage.seed_manifest_cogs([build.manifest], force=params.force):
            log(line)
    except Exception as exc:  # noqa: BLE001
        sync.record_product(
            conn,
            source_id=params.source_id,
            product_id=composite_product_id,
            status="failed",
            error=f"storage upload failed: {exc}",
        )
        raise
    try:
        log(catalog.load_manifest_items([build.manifest], method=params.method))
    except Exception as exc:  # noqa: BLE001
        sync.record_product(
            conn,
            source_id=params.source_id,
            product_id=composite_product_id,
            status="failed",
            error=f"STAC registration failed: {exc}",
        )
        raise
    post_ingest = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=build.manifest,
        source_id=params.source_id,
        expected_aoi_id=aoi_id,
        min_coverage_percent=params.min_coverage_percent,
        require_overviews=not params.allow_missing_overviews,
        require_catalog_item=True,
        stac_api_url=config.STAC_API_URL,
    )
    if not post_ingest.ok:
        sync.record_product(
            conn,
            source_id=params.source_id,
            product_id=composite_product_id,
            status="failed",
            error=f"STAC registration failed: {post_ingest.detail}",
        )
        raise SystemExit(post_ingest.detail)
    log(post_ingest.detail)
    sync.record_product(
        conn,
        source_id=params.source_id,
        product_id=composite_product_id,
        status="composited",
    )
    deleted = sync.cleanup_downloads(downloaded, audit_retention=params.retain_raw_downloads)
    if deleted:
        log(f"deleted raw downloads: {len(deleted)}")
    base_result.ingested = True
    base_result.verdict = "succeeded"
    base_result.detail = post_ingest.detail
    return base_result
