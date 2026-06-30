"""EOS-04 SAR-MRS L2B one-product validation pipeline.

This module owns the bounded manual validation path for EOS-04 SAR.  It is
intentionally separate from the ResourceSat BOA composite pipeline because SAR
is display-only backscatter and must never enter optical analytic/mask/composite
logic.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EOS04_SAR_SOURCE_ID = "eos-04-sar-mrs-l2b"


@dataclass
class Eos04ValidationParams:
    """Inputs for one bounded EOS-04 validation run."""

    source_id: str
    aoi: dict[str, Any]
    aoi_id: str
    window_start: str
    window_end: str
    datetime_range: str
    limit: int = 100
    max_downloads: int | None = 1
    method: str = "upsert"
    out_dir: str | Path | None = None
    raw_root: str | Path | None = None
    ledger_path: str | Path | None = None
    overwrite: bool = False
    keep_intermediate: bool = False
    force: bool = False
    retain_raw_downloads: bool = False
    input_scale: str = "auto"
    polarizations: str | None = None


@dataclass
class Eos04ValidationResult:
    """Outcome of one EOS-04 validation run."""

    source_id: str
    aoi_id: str
    window_start: str
    window_end: str
    verdict: str
    detail: str = ""
    found_count: int = 0
    selected_count: int = 0
    downloaded_count: int = 0
    deferred_count: int = 0
    deferred_product_ids: list[str] = field(default_factory=list)
    prepared: bool = False
    ingested: bool = False
    search_manifest_path: str | None = None
    download_manifest_path: str | None = None
    prepared_manifest_paths: list[str] = field(default_factory=list)
    uploaded: bool = False
    stac_loaded: bool = False
    verified: bool = False

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
            "downloadedCount": self.downloaded_count,
            "deferredCount": self.deferred_count,
            "deferredProductIds": list(self.deferred_product_ids),
            "prepared": self.prepared,
            "ingested": self.ingested,
            "searchManifestPath": self.search_manifest_path,
            "downloadManifestPath": self.download_manifest_path,
            "preparedManifestPaths": list(self.prepared_manifest_paths),
            "uploaded": self.uploaded,
            "stacLoaded": self.stac_loaded,
            "verified": self.verified,
        }


def _run_prepare(
    params: Eos04ValidationParams,
    download_manifest_path: Path,
    *,
    log: Callable[[str], None],
) -> None:
    """Invoke the EOS-04 prepare script as a subprocess."""
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
        "--input-scale",
        params.input_scale,
    ]
    if params.polarizations:
        command.extend(["--polarizations", params.polarizations])
    if params.overwrite:
        command.append("--overwrite")
    if params.keep_intermediate:
        command.append("--keep-intermediate")
    log("prepare command: " + " ".join(command))
    subprocess.run(command, check=True)


def _prepared_manifests_for_products(source_id: str, product_ids: set[str]) -> list[Path]:
    """Return prepared manifest paths matching the downloaded product IDs."""
    from akasha_ingest import config

    matches: list[Path] = []
    for path in config.prepared_manifest_files(source_id=source_id):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if str(data.get("product_id") or "") in product_ids:
            matches.append(path)
    return sorted(set(matches))


def _validate_prepared_manifest(path: Path, source_id: str) -> None:
    from akasha_ingest.validation_profiles import get_validation_profile, validate_manifest_metadata

    data = json.loads(path.read_text(encoding="utf-8"))
    result = validate_manifest_metadata(
        get_validation_profile(source_id), data, source_id=source_id
    )
    if not result.ok:
        raise SystemExit(f"EOS-04 prepared manifest validation failed for {path}: {result.detail}")


def run_eos04_validation(
    params: Eos04ValidationParams,
    *,
    log: Callable[[str], None] = print,
    prepare_fn: Callable[[Path], None] | None = None,
) -> Eos04ValidationResult:
    """Run one bounded EOS-04 search/download/prepare/verify/ingest validation.

    The caller owns scheduler locks and approved-runtime checks.  This function
    caps downloads to one product regardless of caller input.
    """
    from akasha_ingest import bhoonidhi, catalog, config, storage, sync
    from akasha_ingest.manifests import REDACTION_VERSION

    if params.source_id != EOS04_SAR_SOURCE_ID:
        raise SystemExit("EOS-04 validation pipeline only supports eos-04-sar-mrs-l2b")

    max_downloads = 1 if params.max_downloads is None else max(1, min(int(params.max_downloads), 1))
    collection = bhoonidhi.source_collection(params.source_id)
    out_dir = Path(params.out_dir or config.BHOONIDHI_TEMP_ROOT) / params.source_id / params.aoi_id
    search_manifest_path = out_dir / "coverage_manifest.json"
    selected_manifest_path = out_dir / "coverage_manifest.selected.json"
    download_manifest_path = out_dir / "download_manifest.json"
    raw_root = Path(params.raw_root or config.BHOONIDHI_RAW_ROOT) / params.source_id
    ledger_path = Path(params.ledger_path or config.BHOONIDHI_LEDGER_PATH)
    conn = sync.connect_ledger(ledger_path)
    client = bhoonidhi.BhoonidhiClient()
    downloaded: list[dict[str, object]] = []

    try:
        items = client.search(
            collection=collection,
            datetime_range=params.datetime_range,
            intersects=params.aoi["geometry"],
            limit=params.limit,
        )
        manifest = bhoonidhi.build_search_manifest(
            source_id=params.source_id,
            collection=collection,
            aoi=params.aoi,
            datetime_range=params.datetime_range,
            items=items,
        )
        bhoonidhi.write_manifest(manifest, search_manifest_path)
        selection = sync.filter_new_candidates(manifest, conn=conn, source_id=params.source_id)
        candidates = selection.manifest.get("candidates", [])
        deferred = candidates[max_downloads:]
        selection.manifest["candidates"] = candidates[:max_downloads]
        selection.manifest["selection"] = {
            "selected_product_ids": selection.selected_product_ids[:max_downloads]
        }
        deferred_product_ids = [str(candidate.get("item_id")) for candidate in deferred]
        selection.manifest.setdefault("sync", {})["deferred_product_ids"] = deferred_product_ids
        selection.manifest["sync"]["max_downloads_per_validation"] = max_downloads
        selection.manifest["sync"]["window_start"] = params.window_start
        selection.manifest["sync"]["window_end"] = params.window_end
        selection.manifest["sync"]["datetime_range"] = params.datetime_range
        bhoonidhi.write_manifest(selection.manifest, selected_manifest_path)

        found_count = len(items)
        selected_count = len(selection.manifest["selection"]["selected_product_ids"])
        log(f"found {found_count} EOS-04 Bhoonidhi item(s)")
        log(f"selected {selected_count} candidate(s) for validation")
        log(f"deferred {len(deferred_product_ids)} candidate(s)")
        log(f"manifest: {selected_manifest_path}")

        result = Eos04ValidationResult(
            source_id=params.source_id,
            aoi_id=params.aoi_id,
            window_start=params.window_start,
            window_end=params.window_end,
            verdict="succeeded",
            found_count=found_count,
            selected_count=selected_count,
            deferred_count=len(deferred_product_ids),
            deferred_product_ids=deferred_product_ids,
            search_manifest_path=str(search_manifest_path),
        )
        if selected_count == 0:
            result.verdict = "no_new_candidates"
            result.detail = "No new EOS-04 candidates selected for validation."
            return result

        for candidate in selection.manifest.get("candidates", []):
            product_id = str(candidate.get("item_id") or "")
            if not product_id:
                continue
            try:
                download = client.download_product(
                    product_id=product_id,
                    collection=collection,
                    destination=raw_root / f"{product_id}.zip",
                )
            except Exception as exc:  # noqa: BLE001
                sync.record_product(
                    conn,
                    source_id=params.source_id,
                    product_id=product_id,
                    status="failed",
                    error=f"download failed: {exc}",
                )
                raise
            candidate["download_status"] = download["status"]
            candidate["downloaded_path"] = download["path"]
            candidate["downloaded_bytes"] = download["bytes"]
            row = {
                **candidate,
                "item_id": product_id,
                **download,
                "downloaded_path": download["path"],
                "downloaded_bytes": download["bytes"],
                "itemId": product_id,
                "localPath": download["path"],
                "downloadedBytes": download["bytes"],
            }
            downloaded.append(row)
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=product_id,
                status="downloaded",
                bytes_count=int(download.get("bytes") or 0),
            )
            log(f"download {product_id}: {download['status']} ({download['bytes']} bytes)")

        download_manifest = dict(selection.manifest)
        download_manifest["downloaded"] = downloaded
        download_manifest["manifestType"] = "download"
        download_manifest.setdefault("jobId", None)
        download_manifest.setdefault("sourceId", params.source_id)
        download_manifest.setdefault("provider", "bhoonidhi")
        download_manifest.setdefault("adapter", "bhoonidhi")
        download_manifest.setdefault("redactionVersion", REDACTION_VERSION)
        bhoonidhi.write_manifest(download_manifest, download_manifest_path)
        result.downloaded_count = len(downloaded)
        result.download_manifest_path = str(download_manifest_path)
        log(f"download manifest: {download_manifest_path}")

        if prepare_fn is not None:
            prepare_fn(download_manifest_path)
        else:
            _run_prepare(params, download_manifest_path, log=log)
        result.prepared = True

        product_ids = {str(row["item_id"]) for row in downloaded}
        prepared_manifest_paths = _prepared_manifests_for_products(params.source_id, product_ids)
        if not prepared_manifest_paths:
            raise SystemExit("EOS-04 prepare did not produce a matching prepare_manifest.json")
        for manifest_path in prepared_manifest_paths:
            _validate_prepared_manifest(manifest_path, params.source_id)
        result.prepared_manifest_paths = [str(path) for path in prepared_manifest_paths]
        result.verified = True

        log(storage.ensure_bucket())
        for line in storage.seed_manifest_cogs(prepared_manifest_paths, force=params.force):
            log(line)
        result.uploaded = True
        log(catalog.load_collection(method=params.method, collection_id=params.source_id))
        log(catalog.load_manifest_items(prepared_manifest_paths, method=params.method))
        result.stac_loaded = True
        ok, detail = storage.verify_manifest_cogs(prepared_manifest_paths)
        if not ok:
            raise SystemExit(detail)
        log(detail)
        result.ingested = True
        result.detail = detail
        for row in downloaded:
            sync.record_product(
                conn,
                source_id=params.source_id,
                product_id=str(row["item_id"]),
                status="ingested",
                bytes_count=int(row.get("downloaded_bytes") or 0),
            )
        deleted = sync.cleanup_downloads(downloaded, audit_retention=params.retain_raw_downloads)
        if deleted:
            log(f"deleted raw downloads: {len(deleted)}")
        return result
    finally:
        try:
            client.logout(ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
        conn.close()
