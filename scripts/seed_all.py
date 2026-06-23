#!/usr/bin/env python3
"""Seed all reference/lookup data from JSON files.

Usage:
    cd apps/api
    python ../../scripts/seed_all.py

Requires DATABASE_URL env var.  Each entity type commits in its own
transaction so a failure in varieties doesn't lose crops.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.bulk_creation import generate_all


def main() -> None:
    counts = generate_all()
    print("Seeding complete:")
    for name, count in counts.items():
        print(f"  {name}: {count} new rows")


if __name__ == "__main__":
    main()
