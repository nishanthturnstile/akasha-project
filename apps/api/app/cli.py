"""Akasha BFF database CLI (Slice 1).

Applies the app-schema SQL migrations (plots, index_requests, app_settings).
This is operational tooling — NOT a product API endpoint. The api keeps owning
its own data model; catalog migrations (pgSTAC) are handled by the ingestion
worker.

Usage:
    python -m app.cli migrate        # apply apps/api/migrations/*.sql (idempotent)
    python -m app.cli check          # SELECT postgis_version() + plots table check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

STATEMENT_SEP = "\n--;;\n"


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def _split_statements(sql: str) -> List[str]:
    return [chunk.strip() for chunk in sql.split(STATEMENT_SEP) if chunk.strip()]


def cmd_migrate(_: argparse.Namespace) -> int:
    from .db import get_connection  # lazy (psycopg)

    files = sorted(_migrations_dir().glob("*.sql"))
    if not files:
        print(f"No migration files in {_migrations_dir()}", file=sys.stderr)
        return 1
    with get_connection() as conn:
        for f in files:
            statements = _split_statements(f.read_text())
            print(f"applying {f.name} ({len(statements)} statements)")
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            conn.commit()
    print("app-schema migrations complete")
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    from .db import get_connection  # lazy

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT postgis_version()")
        postgis = cur.fetchone()[0]
        cur.execute("SELECT to_regclass('akasha.plots') IS NOT NULL")
        plots_ok = cur.fetchone()[0]
    print(f"PostGIS: {postgis}")
    print(f"akasha.plots present: {plots_ok}")
    return 0 if plots_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Akasha BFF database CLI (Slice 1).")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("migrate", help="Apply app-schema SQL migrations.").set_defaults(func=cmd_migrate)
    sub.add_parser("check", help="Verify PostGIS + plots table.").set_defaults(func=cmd_check)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 1
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
