"""Scheduled Bhoonidhi sync helpers.

The sync command is the Phase 3 operator entrypoint. This module keeps the
SQLite ledger and command planning independently testable.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TERMINAL_PRODUCT_STATUSES = {"downloaded", "prepared", "ingested", "composited", "skipped"}


@dataclass(frozen=True)
class SyncSelection:
    selected_product_ids: list[str]
    skipped_product_ids: list[str]
    manifest: dict[str, Any]


@dataclass(frozen=True)
class SyncLock:
    path: Path
    fd: int


class SyncLockError(RuntimeError):
    """Raised when another scheduled sync already owns the lock."""


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def acquire_lock(path: str | Path) -> SyncLock:
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SyncLockError(f"sync lock already held: {lock_path}") from exc
    try:
        payload = f"pid={os.getpid()} acquired_at={utc_timestamp()}\n"
        os.write(fd, payload.encode("utf-8"))
    except Exception:
        os.close(fd)
        lock_path.unlink(missing_ok=True)
        raise
    return SyncLock(path=lock_path, fd=fd)


def release_lock(lock: SyncLock) -> None:
    try:
        os.close(lock.fd)
    finally:
        lock.path.unlink(missing_ok=True)


def connect_ledger(path: str | Path) -> sqlite3.Connection:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_path)
    conn.execute(
        """
        create table if not exists ingestion_ledger (
            product_id text not null,
            source_id text not null,
            scene_key text,
            status text not null,
            retries integer not null default 0,
            bytes integer not null default 0,
            error text,
            created_at text not null,
            updated_at text not null,
            primary key (product_id, source_id)
        )
        """
    )
    conn.commit()
    return conn


def product_statuses(conn: sqlite3.Connection, source_id: str) -> dict[str, str]:
    rows = conn.execute(
        "select product_id, status from ingestion_ledger where source_id = ?",
        (source_id,),
    ).fetchall()
    return {str(product_id): str(status) for product_id, status in rows}


def record_product(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    product_id: str,
    status: str,
    scene_key: str | None = None,
    bytes_count: int = 0,
    error: str | None = None,
) -> None:
    now = utc_timestamp()
    initial_retries = 1 if status == "failed" else 0
    stored_error = error if status == "failed" else None
    conn.execute(
        """
        insert into ingestion_ledger (
            product_id, source_id, scene_key, status, retries, bytes, error, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(product_id, source_id) do update set
            scene_key = coalesce(excluded.scene_key, ingestion_ledger.scene_key),
            status = excluded.status,
            retries = case
                when excluded.status = 'failed' then ingestion_ledger.retries + 1
                else ingestion_ledger.retries
            end,
            bytes = case
                when excluded.bytes > 0 then excluded.bytes
                else ingestion_ledger.bytes
            end,
            error = excluded.error,
            updated_at = excluded.updated_at
        """,
        (
            product_id,
            source_id,
            scene_key,
            status,
            initial_retries,
            int(bytes_count),
            stored_error,
            now,
            now,
        ),
    )
    conn.commit()


def filter_new_candidates(
    manifest: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    source_id: str,
) -> SyncSelection:
    statuses = product_statuses(conn, source_id)
    selected: list[dict[str, Any]] = []
    skipped_ids: list[str] = []
    for candidate in manifest.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        product_id = str(candidate.get("item_id") or "")
        if not product_id:
            continue
        if statuses.get(product_id) in TERMINAL_PRODUCT_STATUSES:
            skipped_ids.append(product_id)
            continue
        selected.append(candidate)

    selected_ids = [str(candidate["item_id"]) for candidate in selected]
    filtered = dict(manifest)
    filtered["candidates"] = selected
    filtered["selection"] = {"selected_product_ids": selected_ids}
    filtered["sync"] = {
        "skipped_existing_product_ids": skipped_ids,
        "selected_new_product_ids": selected_ids,
    }
    return SyncSelection(
        selected_product_ids=selected_ids,
        skipped_product_ids=skipped_ids,
        manifest=filtered,
    )


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "scripts" / "prepare_resourcesat_liss3_boa_cogs.py").is_file():
            return candidate
    # Container layout: worker.py and scripts/ are both under /app.
    return Path("/app")


def prepare_script_path(start: Path) -> Path:
    return find_repo_root(start) / "scripts" / "prepare_resourcesat_liss3_boa_cogs.py"


def cleanup_downloads(downloaded: list[dict[str, Any]], *, audit_retention: bool) -> list[Path]:
    if audit_retention:
        return []
    deleted: list[Path] = []
    for row in downloaded:
        raw_path = row.get("path") or row.get("downloaded_path")
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if path.is_file():
            path.unlink()
            deleted.append(path)
    return deleted
