"""SQLite job ledger for scheduler observability.

Implements TASK-029 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Responsibilities
----------------
- Persist one row per scheduler job, recording lifecycle state, timing,
  per-run counts, failure metadata, and a pointer to the rich
  ``observability.json`` artifact.
- Provide upsert/update/query/prune helpers for use by the orchestrator.
- Configure SQLite WAL mode and a sensible busy timeout so concurrent
  scheduler/CLI reads do not fail with "database is locked" errors.
- Prune rows older than a configurable retention window (default 90 days)
  to keep the database file bounded in size.

Design constraints
------------------
- stdlib only (``sqlite3``, ``pathlib``, ``datetime``).
- No circular imports: this module imports nothing from ``akasha_ingest``.
- Callers must pass an explicit ``db_path``; tests use temporary directories.
  Production default is ``/srv/akasha/ingestion/scheduler/job_ledger.db``.
- The ledger is separate from the lightweight JSON scheduler ledger in
  ``orchestrator.py`` (which tracks only last-succeeded-at for due decisions).
  The two can coexist; this module does not replace or modify the JSON ledger.

Schema
------
``scheduler_jobs`` table — one row per scheduler job:

    job_id TEXT PRIMARY KEY
    source_id TEXT NOT NULL
    provider TEXT NOT NULL
    aoi_id TEXT NOT NULL
    state TEXT NOT NULL                     — current JobStatus string
    scheduled_at TEXT                       — ISO-8601 UTC
    started_at TEXT                         — ISO-8601 UTC, NULL if not started
    finished_at TEXT                        — ISO-8601 UTC, NULL if not finished
    window_start TEXT                       — ISO-8601 date
    window_end TEXT                         — ISO-8601 date
    found_count INTEGER                     — provider search results found
    selected_count INTEGER                  — candidates selected for download
    downloaded_count INTEGER                — assets successfully downloaded
    rejected_count INTEGER                  — candidates rejected/filtered
    failed_count INTEGER                    — candidates that failed download
    failure_kind TEXT                       — machine-readable failure category
    schedule_decision TEXT                  — why job was triggered
    next_due_at TEXT                        — ISO-8601 UTC next run estimate
    artifact_summary_path TEXT              — path to observability.json on disk

Retention
---------
``prune_old_jobs()`` deletes rows whose ``scheduled_at`` is older than
``retention_days`` (default 90).  Callers may invoke this at the end of each
scheduler pass or on a maintenance schedule.  The method returns the number
of deleted rows so callers can log it.

WAL / busy timeout
------------------
Every connection opens with ``PRAGMA journal_mode=WAL`` and
``PRAGMA busy_timeout=<ms>`` so concurrent reads (e.g. a CLI inspect while
a scheduler run is writing) do not immediately error with "database is locked".
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Production default SQLite database path.
DEFAULT_LEDGER_DB: str = "/srv/akasha/ingestion/scheduler/job_ledger.db"

#: SQLite busy_timeout in milliseconds (5 s).
BUSY_TIMEOUT_MS: int = 5_000

#: Default row retention window in days.
DEFAULT_RETENTION_DAYS: int = 90

#: Schema version stored in ``user_version`` PRAGMA.  Bump when the
#: ``scheduler_jobs`` table structure changes in a backwards-incompatible way.
SCHEMA_VERSION: int = 1

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scheduler_jobs (
    job_id               TEXT    PRIMARY KEY,
    source_id            TEXT    NOT NULL,
    provider             TEXT    NOT NULL,
    aoi_id               TEXT    NOT NULL,
    state                TEXT    NOT NULL,
    scheduled_at         TEXT,
    started_at           TEXT,
    finished_at          TEXT,
    window_start         TEXT,
    window_end           TEXT,
    found_count          INTEGER,
    selected_count       INTEGER,
    downloaded_count     INTEGER,
    rejected_count       INTEGER,
    failed_count         INTEGER,
    failure_kind         TEXT,
    schedule_decision    TEXT,
    next_due_at          TEXT,
    artifact_summary_path TEXT
);
"""

_CREATE_IDX_SOURCE_AOI_SQL = """
CREATE INDEX IF NOT EXISTS idx_sj_source_aoi
    ON scheduler_jobs (source_id, aoi_id);
"""

_CREATE_IDX_SCHEDULED_AT_SQL = """
CREATE INDEX IF NOT EXISTS idx_sj_scheduled_at
    ON scheduler_jobs (scheduled_at);
"""

_CREATE_IDX_STATE_SQL = """
CREATE INDEX IF NOT EXISTS idx_sj_state
    ON scheduler_jobs (state);
"""

# Column names in insertion order (must match _CREATE_TABLE_SQL).
_COLUMNS: tuple[str, ...] = (
    "job_id",
    "source_id",
    "provider",
    "aoi_id",
    "state",
    "scheduled_at",
    "started_at",
    "finished_at",
    "window_start",
    "window_end",
    "found_count",
    "selected_count",
    "downloaded_count",
    "rejected_count",
    "failed_count",
    "failure_kind",
    "schedule_decision",
    "next_due_at",
    "artifact_summary_path",
)


# ---------------------------------------------------------------------------
# JobLedger
# ---------------------------------------------------------------------------


class JobLedger:
    """SQLite-backed job ledger for scheduler observability.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  The parent directory is created
        automatically on first use.  Pass a different path in tests to avoid
        writing to production storage.
    retention_days:
        Rows whose ``scheduled_at`` is older than this many days are deleted
        by :meth:`prune_old_jobs`.  Set to ``0`` to keep all rows.

    Thread safety
    -------------
    Each :meth:`_connect` call opens a new connection.  WAL mode allows
    concurrent reads from multiple connections; writes are serialised by
    SQLite's write-lock.  This is sufficient for the scheduler's sequential
    Phase 4 execution model.  Callers that need higher concurrency should
    wrap writes in their own retry logic.
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_LEDGER_DB,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        self._db_path = Path(db_path)
        self._retention_days = retention_days
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Connection factory
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open and configure a new SQLite connection.

        WAL mode and busy_timeout are applied on every connection so that
        concurrent CLI reads do not fail with "database is locked".
        """
        conn = sqlite3.connect(str(self._db_path), timeout=BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
        return conn

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the table and indexes if they do not already exist."""
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_IDX_SOURCE_AOI_SQL)
            conn.execute(_CREATE_IDX_SCHEDULED_AT_SQL)
            conn.execute(_CREATE_IDX_STATE_SQL)
            # Record the schema version so future migrations can detect it.
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def upsert_job(
        self,
        job_id: str,
        source_id: str,
        provider: str,
        aoi_id: str,
        state: str,
        *,
        scheduled_at: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        found_count: int | None = None,
        selected_count: int | None = None,
        downloaded_count: int | None = None,
        rejected_count: int | None = None,
        failed_count: int | None = None,
        failure_kind: str | None = None,
        schedule_decision: str | None = None,
        next_due_at: str | None = None,
        artifact_summary_path: str | None = None,
    ) -> None:
        """Insert or replace the ledger row for *job_id*.

        This is an ``INSERT OR REPLACE`` so it is safe to call both at job
        creation (initial insert) and later as a full refresh.  Prefer
        :meth:`update_job` for partial updates to existing rows.
        """
        row = (
            job_id,
            source_id,
            provider,
            aoi_id,
            state,
            scheduled_at,
            started_at,
            finished_at,
            window_start,
            window_end,
            found_count,
            selected_count,
            downloaded_count,
            rejected_count,
            failed_count,
            failure_kind,
            schedule_decision,
            next_due_at,
            artifact_summary_path,
        )
        placeholders = ", ".join("?" * len(_COLUMNS))
        cols = ", ".join(_COLUMNS)
        sql = f"INSERT OR REPLACE INTO scheduler_jobs ({cols}) VALUES ({placeholders});"
        with self._connect() as conn:
            conn.execute(sql, row)

    def update_job(
        self,
        job_id: str,
        **kwargs: Any,
    ) -> None:
        """Update specific columns on an existing ledger row.

        Only columns listed in *kwargs* are updated; all others are left
        unchanged.  Raises ``KeyError`` if an unknown column name is passed.

        Parameters
        ----------
        job_id:
            Primary key of the row to update.
        **kwargs:
            Column name → new value pairs.  Accepted column names are the
            same as the ``upsert_job`` keyword parameters (minus ``job_id``).

        Raises
        ------
        KeyError
            If any key in *kwargs* is not a valid column name.
        ValueError
            If no columns are provided (nothing to update).
        """
        if not kwargs:
            raise ValueError("update_job requires at least one column to update.")

        valid_update_cols = set(_COLUMNS) - {"job_id"}
        unknown = set(kwargs) - valid_update_cols
        if unknown:
            raise KeyError(
                f"Unknown column(s) for scheduler_jobs update: {sorted(unknown)}"
            )

        set_clause = ", ".join(f"{col} = ?" for col in kwargs)
        values = list(kwargs.values())
        values.append(job_id)
        sql = f"UPDATE scheduler_jobs SET {set_clause} WHERE job_id = ?;"
        with self._connect() as conn:
            conn.execute(sql, values)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return the ledger row for *job_id*, or ``None`` if not found.

        The returned dict has the same keys as the table column names.
        """
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = ? LIMIT 1;"
        with self._connect() as conn:
            row = conn.execute(sql, (job_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_jobs(
        self,
        *,
        source_id: str | None = None,
        aoi_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
        order_desc: bool = True,
    ) -> list[dict[str, Any]]:
        """Return ledger rows matching the given filters.

        Parameters
        ----------
        source_id:
            Filter by source ID (exact match).
        aoi_id:
            Filter by AOI ID (exact match).
        state:
            Filter by job state string (exact match).
        limit:
            Maximum number of rows to return (default 100).
        order_desc:
            If ``True`` (default), return newest jobs first (by
            ``scheduled_at`` descending).

        Returns
        -------
        list[dict[str, Any]]
            Matching rows as plain dicts.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if source_id is not None:
            conditions.append("source_id = ?")
            params.append(source_id)
        if aoi_id is not None:
            conditions.append("aoi_id = ?")
            params.append(aoi_id)
        if state is not None:
            conditions.append("state = ?")
            params.append(state)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        direction = "DESC" if order_desc else "ASC"
        sql = (
            f"SELECT * FROM scheduler_jobs {where} "
            f"ORDER BY scheduled_at {direction} LIMIT ?;"
        )
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def last_successful_job(
        self, source_id: str, aoi_id: str
    ) -> dict[str, Any] | None:
        """Return the most recent ``succeeded`` row for a source/AOI, or ``None``."""
        sql = (
            "SELECT * FROM scheduler_jobs "
            "WHERE source_id = ? AND aoi_id = ? AND state = 'succeeded' "
            "ORDER BY scheduled_at DESC LIMIT 1;"
        )
        with self._connect() as conn:
            row = conn.execute(sql, (source_id, aoi_id)).fetchone()
        if row is None:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # Retention / prune
    # ------------------------------------------------------------------

    def prune_old_jobs(
        self,
        now: datetime | None = None,
        retention_days: int | None = None,
    ) -> int:
        """Delete rows older than *retention_days*.

        Rows whose ``scheduled_at`` is older than the cutoff are deleted.
        Rows with a ``NULL`` ``scheduled_at`` are never pruned.

        Parameters
        ----------
        now:
            Reference datetime (defaults to ``datetime.now(UTC)``).
        retention_days:
            Override the instance-level default for this call only.

        Returns
        -------
        int
            Number of rows deleted.
        """
        days = retention_days if retention_days is not None else self._retention_days
        if days <= 0:
            return 0
        _now = now if now is not None else datetime.now(UTC)
        cutoff = (_now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        sql = (
            "DELETE FROM scheduler_jobs "
            "WHERE scheduled_at IS NOT NULL AND scheduled_at < ?;"
        )
        with self._connect() as conn:
            cursor = conn.execute(sql, (cutoff,))
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def row_count(self) -> int:
        """Return the total number of rows in ``scheduler_jobs``."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM scheduler_jobs;").fetchone()
        return int(row[0]) if row else 0

    def db_path(self) -> Path:
        """Return the absolute path to the SQLite database file."""
        return self._db_path
