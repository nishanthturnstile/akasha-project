"""Akasha BFF database CLI.

The API-owned app schema is managed by Alembic from SQLAlchemy ORM metadata.
Catalog/pgSTAC migrations remain owned by the ingestion worker.

Usage:
    python -m app.cli db upgrade     # apply API ORM baseline/revisions
    python -m app.cli migrate        # compatibility alias for db upgrade
    python -m app.cli check          # SELECT postgis_version() + app table check
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alembic import command

from .config import settings
from .ingestion_client import get_readiness, is_ingestion_configured
from .raster.catalog_resolver import SENTINEL_2_SOURCE_ID
from .raster.errors import AkashaError

ALEMBIC_ADVISORY_LOCK_ID = 2_026_060_900


def _api_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _alembic_config():
    from alembic.config import Config

    return Config(str(_api_root() / "alembic.ini"))


def _migration_lock_engine():
    from .db import get_engine

    return get_engine()


def _run_with_migration_lock(action: Callable[[], None]) -> None:
    from sqlalchemy import text

    with _migration_lock_engine().connect() as conn:
        conn.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": ALEMBIC_ADVISORY_LOCK_ID},
        )
        try:
            action()
        finally:
            conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": ALEMBIC_ADVISORY_LOCK_ID},
            )


def _script_heads() -> tuple[str, ...]:
    from alembic.script import ScriptDirectory

    return tuple(ScriptDirectory.from_config(_alembic_config()).get_heads())


def _database_current_heads() -> tuple[str, ...]:
    from alembic.runtime.migration import MigrationContext

    with _migration_lock_engine().connect() as conn:
        return tuple(MigrationContext.configure(conn).get_current_heads())


def _format_heads(heads: tuple[str, ...]) -> str:
    return ", ".join(heads) if heads else "<none>"


def cmd_db_upgrade(_: argparse.Namespace) -> int:
    _run_with_migration_lock(lambda: command.upgrade(_alembic_config(), "head"))
    print("app-schema Alembic upgrade complete")
    return 0


def cmd_db_current(_: argparse.Namespace) -> int:
    command.current(_alembic_config())
    return 0


def cmd_db_heads(_: argparse.Namespace) -> int:
    heads = _script_heads()
    if len(heads) == 1:
        print(f"Alembic head: {heads[0]}")
        return 0
    if not heads:
        print("Alembic has no heads")
        return 1
    print(f"Alembic has multiple heads: {_format_heads(heads)}")
    return 1


def cmd_db_verify_current(_: argparse.Namespace) -> int:
    heads = set(_script_heads())
    current = set(_database_current_heads())
    if current == heads:
        print(f"Database schema is at Alembic head: {_format_heads(tuple(sorted(heads)))}")
        return 0

    print("Database schema is not at Alembic head")
    print(f"current: {_format_heads(tuple(sorted(current)))}")
    print(f"head: {_format_heads(tuple(sorted(heads)))}")
    return 1


def cmd_db_downgrade_base(_: argparse.Namespace) -> int:
    command.downgrade(_alembic_config(), "base")
    print("app-schema Alembic downgrade to base complete")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    return cmd_db_upgrade(args)


def cmd_check(_: argparse.Namespace) -> int:
    from sqlalchemy import text

    from .db import get_engine

    with get_engine().connect() as conn:
        postgis = conn.execute(text("SELECT postgis_version()")).scalar_one()
        plots_ok = conn.execute(text("SELECT to_regclass('akasha.plots') IS NOT NULL")).scalar_one()
        alembic_ok = conn.execute(
            text("SELECT to_regclass('alembic_version') IS NOT NULL")
        ).scalar_one()
    minio_ok = _check_minio_liveness()
    print(f"PostGIS: {postgis}")
    print(f"akasha.plots present: {plots_ok}")
    print(f"Alembic version table present: {alembic_ok}")
    print(f"MinIO reachable from api: {minio_ok}")
    return 0 if plots_ok and alembic_ok and minio_ok else 1


def _bool_label(value: bool) -> str:
    return "true" if value else "false"


def _check_ingestion_health() -> tuple[bool, str]:
    endpoint = settings.ingestion_api_url.rstrip("/")
    if not endpoint:
        return False, "not configured"
    request = urllib.request.Request(
        f"{endpoint}/health",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - configured private ingestion URL
            request,
            timeout=settings.ingestion_request_timeout_seconds,
        ) as response:
            return response.status == 200, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, type(exc).__name__


def _readiness_count(readiness: dict[str, Any] | None) -> int:
    if not readiness:
        return 0
    dates = readiness.get("availableDates")
    return len(dates) if isinstance(dates, list) else 0


def cmd_ingestion_check(_: argparse.Namespace) -> int:
    """Preflight the local remote-ingestion bridge without printing secrets."""
    configured = is_ingestion_configured(settings)
    # The resolved setting falls back to INGESTION_API_URL, so check the EXPLICIT env var:
    # the deployed signed-URL prefix (AKASHA_PUBLIC_BASE_URL) usually differs from the tunnel
    # URL, and relying on the fallback would let signed fetches fail later (plan TASK-001).
    allowed_prefix_configured = bool(
        os.environ.get("INGESTION_SIGNED_URL_ALLOWED_PREFIX", "").strip()
    )
    fetch_prefix_configured = bool(settings.ingestion_signed_url_fetch_prefix.strip())

    print(f"Ingestion API configured: {_bool_label(configured)}")
    print("Ingestion readiness enabled: " f"{_bool_label(settings.ingestion_readiness_enabled)}")
    print(
        "Ingestion field-index enabled: " f"{_bool_label(settings.ingestion_field_index_enabled)}"
    )
    print(f"Signed URL allowed prefix configured: {_bool_label(allowed_prefix_configured)}")
    print(f"Signed URL fetch prefix configured: {_bool_label(fetch_prefix_configured)}")

    if not configured or not allowed_prefix_configured:
        print("Bridge configuration is incomplete.")
        return 1

    health_ok, health_status = _check_ingestion_health()
    print(f"Ingestion health: {'ok' if health_ok else 'failed'} ({health_status})")
    if not health_ok:
        return 1

    try:
        readiness = get_readiness(
            settings,
            source_id=SENTINEL_2_SOURCE_ID,
            aoi_id=settings.ingestion_aoi_id,
        )
    except AkashaError as exc:
        print(f"Readiness check failed: {exc.code}")
        return 1

    available_count = _readiness_count(readiness)
    print(f"Sentinel-2 readiness dates: {available_count}")
    if available_count <= 0:
        print("Readiness check failed: no available dates.")
        return 1

    print("Remote ingestion bridge check passed.")
    return 0


def _check_minio_liveness() -> bool:
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").rstrip("/")
    if not endpoint:
        print(
            "S3_ENDPOINT_URL is not set; cannot verify API -> MinIO reachability",
            file=sys.stderr,
        )
        return False
    try:
        with urllib.request.urlopen(f"{endpoint}/minio/health/live", timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"MinIO liveness check failed: {exc}", file=sys.stderr)
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Akasha BFF database CLI.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("migrate", help="Compatibility alias for `db upgrade`.").set_defaults(
        func=cmd_migrate
    )
    sub.add_parser("check", help="Verify PostGIS + API app schema.").set_defaults(func=cmd_check)
    sub.add_parser(
        "ingestion-check",
        help="Verify local remote-ingestion bridge configuration.",
    ).set_defaults(func=cmd_ingestion_check)

    db = sub.add_parser("db", help="Alembic-backed app-schema commands.")
    db_sub = db.add_subparsers(dest="db_command")
    db_sub.add_parser("upgrade", help="Apply API app-schema revisions.").set_defaults(
        func=cmd_db_upgrade
    )
    db_sub.add_parser("current", help="Show current Alembic revision.").set_defaults(
        func=cmd_db_current
    )
    db_sub.add_parser(
        "heads",
        help="Show Alembic script heads and fail on branching.",
    ).set_defaults(func=cmd_db_heads)
    db_sub.add_parser(
        "verify-current",
        help="Verify the live database is upgraded to this code's Alembic head.",
    ).set_defaults(func=cmd_db_verify_current)
    db_sub.add_parser(
        "downgrade-base",
        help="Drop API app-schema objects managed by the Alembic baseline.",
    ).set_defaults(func=cmd_db_downgrade_base)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 1
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
