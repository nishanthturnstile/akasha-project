"""Configuration + canonical constants for Akasha ingestion (Slice 1).

Stdlib only — safe to import without pypgstac/boto3 installed.
"""
from __future__ import annotations

import os
from pathlib import Path

COLLECTION_ID = "sentinel-2-l2a"

# Object storage (MinIO / S3-compatible). Internal-only; placeholders in env.
BUCKET = os.environ.get("AKASHA_COG_BUCKET", "akasha-cogs")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

# Database (pgSTAC) + STAC API.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
STAC_API_URL = os.environ.get("STAC_API_URL", "")


def find_seed_dir() -> Path:
    """Locate the repo `data/seed` directory (container: /app/data/seed)."""
    env = os.environ.get("SEED_DATA_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for base in [Path("/app"), *here.parents]:
        cand = base / "data" / "seed"
        if cand.is_dir():
            return cand
    return Path("/app/data/seed")


def collection_file() -> Path:
    return find_seed_dir() / "stac" / "sentinel-2-l2a-collection.json"


def item_file() -> Path:
    return find_seed_dir() / "stac" / "sentinel-2-l2a-sample-item.json"


def raster_source_dir(acquisition_date: str) -> Path:
    """Operator-provided rasters (large; NOT committed). Used if present."""
    env = os.environ.get("RASTER_SOURCE_DIR")
    base = Path(env) if env else (find_seed_dir() / "rasters")
    return base / acquisition_date
