"""Configuration + canonical constants for Akasha ingestion (Slice 1).

Stdlib only — safe to import without pypgstac/boto3 installed.
"""
from __future__ import annotations

import glob as globlib
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

# Prepared COG manifest discovery.
PREPARED_MANIFEST_GLOB_ENV = "AKASHA_PREPARED_MANIFEST_GLOB"
DEFAULT_PREPARED_MANIFEST_PATTERN = "*/*/prepare_manifest.json"
DEFAULT_PREPARED_MANIFEST_PATTERNS = (
    "*/prepare_manifest.json",
    DEFAULT_PREPARED_MANIFEST_PATTERN,
)


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


def raster_source_root() -> Path:
    env = os.environ.get("RASTER_SOURCE_DIR")
    return Path(env) if env else (find_seed_dir() / "rasters")


def raster_source_dir(acquisition_date: str) -> Path:
    """Operator-provided rasters (large; NOT committed). Used if present."""
    return raster_source_root() / acquisition_date


def prepared_manifest_glob(root: Path | None = None) -> str:
    pattern = os.environ.get(PREPARED_MANIFEST_GLOB_ENV)
    if pattern:
        return pattern
    return str((root or raster_source_root()) / "*" / "*" / "prepare_manifest.json")


def prepared_manifest_files(root: Path | None = None, pattern: str | None = None) -> list[Path]:
    """Find prepared COG manifests under legacy and tile-scoped raster layouts."""
    if pattern is None:
        env_pattern = os.environ.get(PREPARED_MANIFEST_GLOB_ENV)
        if env_pattern:
            matches = [Path(path).resolve() for path in globlib.glob(env_pattern, recursive=True)]
            return sorted({path for path in matches if path.is_file()})
        base = root or raster_source_root()
        matches = {
            path.resolve()
            for manifest_pattern in DEFAULT_PREPARED_MANIFEST_PATTERNS
            for path in base.glob(manifest_pattern)
            if path.is_file()
        }
        return sorted(matches)

    matches = [Path(path).resolve() for path in globlib.glob(pattern, recursive=True)]
    if matches:
        return sorted({path for path in matches if path.is_file()})
    if Path(pattern).is_absolute():
        return []

    base = root or raster_source_root()
    return sorted({path.resolve() for path in base.glob(pattern) if path.is_file()})
