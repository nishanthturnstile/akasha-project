"""Database connection helper for the Akasha BFF (Slice 1).

DB access is used ONLY by the migration CLI in Slice 1 (no product endpoints
touch the database yet). `psycopg` is imported lazily so importing `app.main`
(the live preview / runtime) never requires a database driver.
"""
from __future__ import annotations

import os


def get_database_url() -> str:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set (required for migrations).")
    return dsn


def get_connection():
    """Return a new psycopg connection. Lazy import keeps runtime imports light."""
    import psycopg  # noqa: PLC0415  (intentional lazy import)

    return psycopg.connect(get_database_url())
