"""Akasha ingestion worker — Slice 0 skeleton.

This is a placeholder CLI. It performs NO ingestion yet. Real subcommands
(SAFE/JP2/TIF -> validated COG, SCL COG, STAC item registration, MinIO upload)
are implemented from Slice 1 onward.

Usage:
    python worker.py info          # print resolved (non-secret) configuration
    python worker.py healthcheck   # exit 0 if required env vars are present
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

REQUIRED_ENV: List[str] = [
    "DATABASE_URL",
    "STAC_API_URL",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
]


def _redact(name: str, value: str) -> str:
    """Never print secret values; show only presence/length."""
    if not value:
        return "<unset>"
    if any(tok in name for tok in ("SECRET", "KEY", "PASSWORD", "URL")):
        return f"<set:{len(value)} chars>"
    return value


def _collect() -> List[Tuple[str, str]]:
    names = REQUIRED_ENV + ["AOI_CONFIG_PATH"]
    return [(n, _redact(n, os.environ.get(n, ""))) for n in names]


def cmd_info(_: argparse.Namespace) -> int:
    print("Akasha ingestion worker — Slice 0 skeleton (no-op).")
    print("Resolved configuration (secrets redacted):")
    for name, shown in _collect():
        print(f"  - {name}: {shown}")
    print("Status: ready. Ingestion subcommands arrive in Slice 1+.")
    return 0


def cmd_healthcheck(_: argparse.Namespace) -> int:
    missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
    if missing:
        print(f"UNHEALTHY: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("HEALTHY: required env vars present.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Akasha ingestion worker (Slice 0 skeleton).")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info", help="Print resolved configuration and exit.").set_defaults(func=cmd_info)
    sub.add_parser("healthcheck", help="Exit 0 if required env vars are present.").set_defaults(
        func=cmd_healthcheck
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_info(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
