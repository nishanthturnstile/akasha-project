"""Configuration + canonical constants for Akasha ingestion (Slice 1).

Stdlib only — safe to import without pypgstac/boto3 installed.
"""

from __future__ import annotations

import glob as globlib
import os
from pathlib import Path

SENTINEL2_COLLECTION_ID = "sentinel-2-l2a"
SENTINEL1_COLLECTION_ID = "sentinel-1-grd"
EOS04_SAR_COLLECTION_ID = "eos-04-sar-mrs-l2b"
NISAR_GCOV_COLLECTION_ID = "nisar-ssar-beta-gcov"
SAR_COLLECTION_IDS = {
    SENTINEL1_COLLECTION_ID,
    EOS04_SAR_COLLECTION_ID,
    NISAR_GCOV_COLLECTION_ID,
}
CARTOSAT3_CONTEXT_COLLECTION_ID = "cartosat-3-gated"
EOS06_CONTEXT_COLLECTION_ID = "eos-06-ocm-lac-ndvi-8day-360m"
CONTEXT_COLLECTION_IDS = {
    CARTOSAT3_CONTEXT_COLLECTION_ID,
    EOS06_CONTEXT_COLLECTION_ID,
}
IRS1C_ARCHIVE_COLLECTION_ID = "irs-1c-liss3-archive"
ARCHIVE_COLLECTION_IDS = {
    IRS1C_ARCHIVE_COLLECTION_ID,
}
RESOURCESAT_LISS3_COLLECTION_ID = "resourcesat-2a-liss3-boa"
RESOURCESAT_LISS4_COLLECTION_ID = "resourcesat-2a-liss4-mx70-l2"
RESOURCESAT_AWIFS_COLLECTION_ID = "resourcesat-2a-awifs-boa"
RESOURCESAT_BOA_COLLECTION_IDS = {
    RESOURCESAT_LISS3_COLLECTION_ID,
    RESOURCESAT_LISS4_COLLECTION_ID,
    RESOURCESAT_AWIFS_COLLECTION_ID,
}
COLLECTION_ID = os.environ.get("AKASHA_COLLECTION_ID", RESOURCESAT_LISS3_COLLECTION_ID)

# Object storage (MinIO / S3-compatible). Internal-only; placeholders in env.
BUCKET = os.environ.get("AKASHA_COG_BUCKET", "akasha-cogs")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

# Database (pgSTAC) + STAC API.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
STAC_API_URL = os.environ.get("STAC_API_URL", "")

# AOI and Bhoonidhi ingestion settings. Bhoonidhi credentials are worker/API
# server-side only; never expose them through the browser.
AOI_CONFIG_PATH = os.environ.get("AOI_CONFIG_PATH", "/app/data/seed/bangalore-60km-aoi.geojson")
AOI_CONFIG_DIR = os.environ.get("AOI_CONFIG_DIR", "")
BHOONIDHI_API_BASE = os.environ.get("BHOONIDHI_API_BASE", "https://bhoonidhi-api.nrsc.gov.in")
BHOONIDHI_USER_ID = os.environ.get("BHOONIDHI_USER_ID", "")
BHOONIDHI_PASSWORD = os.environ.get("BHOONIDHI_PASSWORD", "")
BHOONIDHI_SEARCH_RPS = os.environ.get("BHOONIDHI_SEARCH_RPS", "3")
BHOONIDHI_DOWNLOAD_CONCURRENCY = os.environ.get("BHOONIDHI_DOWNLOAD_CONCURRENCY", "3")
BHOONIDHI_MAX_DOWNLOADS_PER_SYNC = os.environ.get("BHOONIDHI_MAX_DOWNLOADS_PER_SYNC", "3")
BHOONIDHI_RAW_ROOT = os.environ.get("BHOONIDHI_RAW_ROOT", "/srv/akasha/data/raw/bhoonidhi")
BHOONIDHI_TEMP_ROOT = os.environ.get("BHOONIDHI_TEMP_ROOT", "/srv/akasha/data/work/bhoonidhi")
BHOONIDHI_LEDGER_PATH = os.environ.get(
    "BHOONIDHI_LEDGER_PATH",
    "/srv/akasha/ingestion/ledger.sqlite",
)

# Prepared COG manifest discovery.
PREPARED_MANIFEST_GLOB_ENV = "AKASHA_PREPARED_MANIFEST_GLOB"
DEFAULT_PREPARED_MANIFEST_PATTERN = "*/*/prepare_manifest.json"
DEFAULT_PREPARED_MANIFEST_PATTERNS = (
    "*/prepare_manifest.json",
    DEFAULT_PREPARED_MANIFEST_PATTERN,
)
SOURCE_SCOPED_PREPARED_MANIFEST_PATTERNS = (
    "*/*/prepare_manifest.json",
    "*/*/*/prepare_manifest.json",
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


def collection_file(collection_id: str | None = None) -> Path:
    source_id = collection_id or COLLECTION_ID
    return find_seed_dir() / "stac" / f"{source_id}-collection.json"


def item_file(collection_id: str | None = None) -> Path:
    source_id = collection_id or COLLECTION_ID
    return find_seed_dir() / "stac" / f"{source_id}-sample-item.json"


def item_files(collection_id: str | None = None) -> list[Path]:
    source_id = collection_id or COLLECTION_ID
    stac_dir = find_seed_dir() / "stac"
    files: list[Path] = []
    sample = item_file(source_id)
    # ResourceSat's sample item is a schema/contract scaffold only. Loading it
    # into pgSTAC creates a placeholder same-date item that can mask real
    # manifest-ingested scenes during date resolution.
    if sample.is_file() and source_id == SENTINEL2_COLLECTION_ID:
        files.append(sample)
    item_dir = stac_dir / "items" / source_id
    if item_dir.is_dir():
        files.extend(sorted(path for path in item_dir.glob("*.json") if path.is_file()))
    return sorted({path.resolve() for path in files})


def raster_source_root() -> Path:
    env = os.environ.get("RASTER_SOURCE_DIR")
    return Path(env) if env else (find_seed_dir() / "rasters")


def raster_source_dir(acquisition_date: str) -> Path:
    """Operator-provided rasters (large; NOT committed). Used if present."""
    return raster_source_root() / acquisition_date


def prepared_manifest_glob(root: Path | None = None, source_id: str | None = None) -> str:
    pattern = os.environ.get(PREPARED_MANIFEST_GLOB_ENV)
    if pattern:
        return pattern
    base = root or raster_source_root()
    if source_id:
        return str(base / source_id / "*" / "*" / "*" / "prepare_manifest.json")
    return str(base / "*" / "*" / "prepare_manifest.json")


def prepared_manifest_files(
    root: Path | None = None,
    pattern: str | None = None,
    source_id: str | None = None,
) -> list[Path]:
    """Find prepared COG manifests under legacy and source-scoped raster layouts."""
    if pattern is None:
        env_pattern = os.environ.get(PREPARED_MANIFEST_GLOB_ENV)
        if env_pattern:
            matches = [Path(path).resolve() for path in globlib.glob(env_pattern, recursive=True)]
            return sorted({path for path in matches if path.is_file()})
        base = root or raster_source_root()
        if source_id:
            source_root = base / source_id
            matches = {
                path.resolve()
                for manifest_pattern in SOURCE_SCOPED_PREPARED_MANIFEST_PATTERNS
                for path in source_root.glob(manifest_pattern)
                if path.is_file()
            }
            if source_id == SENTINEL2_COLLECTION_ID:
                matches.update(
                    path.resolve()
                    for manifest_pattern in DEFAULT_PREPARED_MANIFEST_PATTERNS
                    for path in base.glob(manifest_pattern)
                    if path.is_file()
                )
            return sorted(matches)
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
