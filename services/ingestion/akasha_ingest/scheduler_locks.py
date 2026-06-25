"""Centralized lock helpers for the Akasha ingestion scheduler.

Provides a global scheduler lock plus per-provider/source/AOI worker locks.
All locks use the same exclusive-lock-file semantics as ``sync.acquire_lock``:

- ``os.O_CREAT | os.O_EXCL`` ensures at most one writer creates the file.
- The payload written is ``pid=<n> acquired_at=<iso8601>\\n``.
- :func:`release_lock` unlinks the file.

Stale-lock reclaim
------------------
When a lock file already exists, the module checks whether it is stale before
raising :class:`SchedulerLockError`.  A lock is stale when:

- The PID it records is no longer alive (checked portably — no signals sent)
  **and** the lock age exceeds ``stale_ttl_seconds``.

An unparseable payload is treated as live (fail-closed), so a corrupt lock file
is NOT silently reclaimed.

Testing without sleeps
----------------------
The module exposes a module-level ``_now`` hook (a callable ``() -> datetime``)
that tests can monkey-patch to inject an arbitrary "current time" without
sleeping.  Production code must not replace it.

Legacy Bhoonidhi compatibility
-------------------------------
Worker lock files use the canonical ``{source_id}.{aoi_id}.worker.lock`` name.

Stdlib only; no live provider calls.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GLOBAL_LOCK_NAME = "scheduler.lock"

#: Default TTL for stale-lock reclaim (seconds).  A lock older than this is
#: considered stale only when its recorded PID is no longer alive.
DEFAULT_STALE_TTL_SECONDS: int = 7200  # 2 hours

# ---------------------------------------------------------------------------
# Injectable clock (for unit tests — do not replace in production)
# ---------------------------------------------------------------------------

#: Returns the current UTC time.  Tests may monkey-patch this to avoid sleeps.
_now: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


# ---------------------------------------------------------------------------
# Public exceptions and data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulerLock:
    """Handle for an acquired scheduler or worker lock file.

    Compatible with :class:`~akasha_ingest.sync.SyncLock`; pass to
    :func:`release_lock` when the critical section is complete.
    """

    path: Path
    fd: int
    payload: str = ""


class SchedulerLockError(RuntimeError):
    """Raised when a live, non-stale lock is already held.

    Fail-closed: callers must not proceed when this is raised.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_timestamp() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _parse_lock_payload(text: str) -> tuple[int | None, datetime | None]:
    """Parse ``pid=<n> acquired_at=<iso>`` tokens from a lock file payload.

    Returns ``(None, None)`` on any parse failure so callers can distinguish
    an unreadable lock from a well-formed one.
    """
    pid: int | None = None
    acquired_at: datetime | None = None
    for token in text.split():
        if token.startswith("pid="):
            try:
                pid = int(token[4:])
            except ValueError:
                pass
        elif token.startswith("acquired_at="):
            raw = token[len("acquired_at=") :]
            try:
                acquired_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
    return pid, acquired_at


def _pid_is_alive(pid: int) -> bool:
    """Return True if the process *pid* exists (best-effort, no signals sent).

    Platform notes
    --------------
    On **Windows**, ``os.kill(pid, 0)`` sends ``CTRL_C_EVENT`` rather than
    probing liveness, which can raise ``KeyboardInterrupt`` in the calling
    process.  We use ``ctypes.windll.kernel32`` (OpenProcess / GetExitCodeProcess)
    for a non-destructive check instead.

    On **POSIX**, ``os.kill(pid, 0)`` is the conventional no-op signal probe.
    """
    if sys.platform == "win32":
        import ctypes  # stdlib; safe on Windows

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259  # GetExitCodeProcess returns this for a live process
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            if ctypes.windll.kernel32.GetExitCodeProcess(  # type: ignore[attr-defined]
                handle, ctypes.byref(exit_code)
            ):
                return exit_code.value == STILL_ACTIVE
            return False
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission to signal it — treat as alive.
            return True
        except OSError:
            return False


def _is_stale(lock_path: Path, *, stale_ttl_seconds: int) -> bool:
    """Return True when the lock at *lock_path* is safe to reclaim.

    Decision rules (in order):
    1. If the file cannot be read it has already vanished → stale (True).
    2. If the payload cannot be parsed → live (False) — fail-closed.
    3. If age ≥ ``stale_ttl_seconds`` AND the recorded PID is no longer alive
       → stale (True).
    4. If the recorded PID is still alive, the lock is live regardless of age.
    5. Otherwise → live (False).
    """
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # File vanished between check and read.

    pid, acquired_at = _parse_lock_payload(text)
    if pid is None or acquired_at is None:
        return False  # Unreadable payload — do not reclaim.

    age_seconds = (_now() - acquired_at).total_seconds()
    return age_seconds >= stale_ttl_seconds and not _pid_is_alive(pid)


def _try_reclaim(lock_path: Path, *, stale_ttl_seconds: int) -> bool:
    """Attempt to remove a stale lock.  Returns True if the file was removed."""
    if not _is_stale(lock_path, stale_ttl_seconds=stale_ttl_seconds):
        return False
    lock_path.unlink(missing_ok=True)
    return True


# ---------------------------------------------------------------------------
# Lock path construction
# ---------------------------------------------------------------------------


def global_lock_path(lock_dir: str | Path) -> Path:
    """Return the path to the global scheduler lock file under *lock_dir*."""
    return Path(lock_dir) / GLOBAL_LOCK_NAME


def worker_lock_name(source_id: str, aoi_id: str) -> str:
    """Return the canonical ``{source_id}.{aoi_id}.worker.lock`` filename."""
    return f"{source_id}.{aoi_id}.worker.lock"


def worker_lock_path(lock_dir: str | Path, source_id: str, aoi_id: str) -> Path:
    """Return the absolute path to the worker lock file for *source_id*/*aoi_id*."""
    return Path(lock_dir) / worker_lock_name(source_id, aoi_id)


# ---------------------------------------------------------------------------
# Core acquire / release
# ---------------------------------------------------------------------------


def acquire_lock(
    path: str | Path,
    *,
    stale_ttl_seconds: int = DEFAULT_STALE_TTL_SECONDS,
) -> SchedulerLock:
    """Acquire an exclusive lock file at *path*.

    On success the file is created and its PID/timestamp payload is written.
    On failure :class:`SchedulerLockError` is raised without side effects.

    If the lock file already exists the module first attempts a stale reclaim.
    A lock is reclaimed when the PID is dead or the file age exceeds
    ``stale_ttl_seconds``.  If the lock is live, :class:`SchedulerLockError`
    is raised immediately (fail-closed).

    Parameters
    ----------
    path:
        Absolute or relative path for the lock file.
    stale_ttl_seconds:
        Age threshold in seconds after which a lock is considered stale.

    Returns
    -------
    :class:`SchedulerLock`
        Handle for the acquired lock; pass to :func:`release_lock` when done.

    Raises
    ------
    :class:`SchedulerLockError`
        When a live lock is already held, or when a stale reclaim succeeded but
        re-acquisition immediately failed (e.g. another process raced in).
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    for _attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _try_reclaim(lock_path, stale_ttl_seconds=stale_ttl_seconds):
                continue  # Reclaimed — retry once.
            raise SchedulerLockError(f"lock already held (live): {lock_path}") from None

        # File created exclusively — write PID/timestamp payload.
        try:
            payload = f"pid={os.getpid()} acquired_at={_utc_timestamp()}\n"
            os.write(fd, payload.encode("utf-8"))
        except Exception:
            os.close(fd)
            lock_path.unlink(missing_ok=True)
            raise
        return SchedulerLock(path=lock_path, fd=fd, payload=payload)

    raise SchedulerLockError(
        f"lock could not be acquired after stale reclaim: {lock_path}"
    )


def release_lock(lock: SchedulerLock) -> None:
    """Release and remove the lock file held by *lock*.

    Safe to call even if the file was already removed (e.g. by an operator).
    """
    try:
        os.close(lock.fd)
    except OSError:
        pass
    finally:
        try:
            current_payload = lock.path.read_text(encoding="utf-8")
        except OSError:
            return
        if current_payload == lock.payload:
            lock.path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


def acquire_global_lock(
    lock_dir: str | Path,
    *,
    stale_ttl_seconds: int = DEFAULT_STALE_TTL_SECONDS,
) -> SchedulerLock:
    """Acquire the global scheduler singleton lock under *lock_dir*.

    Only one scheduler run may hold this lock at a time across the entire
    system.  Use :func:`release_lock` in a ``finally`` block.
    """
    return acquire_lock(
        global_lock_path(lock_dir),
        stale_ttl_seconds=stale_ttl_seconds,
    )


def acquire_worker_lock(
    lock_dir: str | Path,
    source_id: str,
    aoi_id: str,
    *,
    stale_ttl_seconds: int = DEFAULT_STALE_TTL_SECONDS,
) -> SchedulerLock:
    """Acquire the per-source/AOI worker lock under *lock_dir*.

    Prevents two concurrent jobs from running the same source/AOI pair.
    Lock-file name follows the legacy Bhoonidhi convention where applicable
    (see :func:`worker_lock_name`).
    """
    return acquire_lock(
        worker_lock_path(lock_dir, source_id, aoi_id),
        stale_ttl_seconds=stale_ttl_seconds,
    )
