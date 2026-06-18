"""Prepare ResourceSat-2A BOA analytic and mask COGs.

Inputs are Bhoonidhi ResourceSat-2A LISS-3/AWiFS BOA product ZIPs containing
``BAND2.tif``, ``BAND3.tif``, ``BAND4.tif``, ``BAND5.tif`` and
``BAND_META.txt``. Use ``--source`` to select the target source. Outputs are
written under the source-scoped raster layout:

    data/seed/rasters/<source>/scene/<date>/<sceneComponent>/analytic.tif
    data/seed/rasters/<source>/scene/<date>/<sceneComponent>/mask.tif

The generated mask is provisional because the validated BOA product did not
include a native quality/cloud/shadow raster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "resourcesat-2a-liss3-boa"
BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS3_BOA"
LISS4_SOURCE_ID = "resourcesat-2a-liss4-mx70-l2"
LISS4_BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS4-MX70_L2"
AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
AWIFS_BHOONIDHI_COLLECTION = "ResourceSat-2A_AWIFS_BOA"
LISS3_ANALYTIC_BANDS: tuple[tuple[str, str, str], ...] = (
    ("BAND2", "GREEN", "Green"),
    ("BAND3", "RED", "Red"),
    ("BAND4", "NIR", "Near infrared"),
    ("BAND5", "SWIR1", "Short-wave infrared 1"),
)
LISS4_ANALYTIC_BANDS: tuple[tuple[str, str, str], ...] = (
    ("BAND2", "GREEN", "Green"),
    ("BAND3", "RED", "Red"),
    ("BAND4", "NIR", "Near infrared"),
)
SOURCE_PROFILES = {
    SOURCE_ID: {
        "collection": BHOONIDHI_COLLECTION,
        "label": "LISS-3",
        "resolution_meters": 24,
        "analytic_bands": LISS3_ANALYTIC_BANDS,
        "reflectance_scale": 0.0001,
        "reflectance_offset": 0.0,
        "mask_builder": "4band",
        "mask_method": (
            "Akasha threshold mask v1 (no native quality layer found in validated "
            "LISS-3 BOA sample; provisional)."
        ),
    },
    LISS4_SOURCE_ID: {
        "collection": LISS4_BHOONIDHI_COLLECTION,
        "label": "LISS-4",
        "resolution_meters": 5.8,
        "analytic_bands": LISS4_ANALYTIC_BANDS,
        "reflectance_scale": 0.0001,
        "reflectance_offset": 0.0,
        "mask_builder": "3band",
        "mask_method": (
            "Akasha threshold mask v1 (LISS-4, no SWIR; provisional)."
        ),
    },
    AWIFS_SOURCE_ID: {
        "collection": AWIFS_BHOONIDHI_COLLECTION,
        "label": "AWiFS",
        "resolution_meters": 56,
        "analytic_bands": LISS3_ANALYTIC_BANDS,
        "reflectance_scale": 0.0001,
        "reflectance_offset": 0.0,
        "mask_builder": "4band",
        "mask_method": (
            "Akasha threshold mask v1 for ResourceSat-2A AWiFS BOA "
            "(pending AWiFS-specific native quality-layer validation; provisional)."
        ),
    },
}
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "bhoonidhi" / SOURCE_ID
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "work" / "bhoonidhi" / SOURCE_ID
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "seed" / "rasters" / SOURCE_ID
COG_BLOCKSIZE = 512
NODATA_DN = 0
REFLECTANCE_SCALE = 0.0001
REFLECTANCE_OFFSET = 0.0
MASK_METHOD = (
    "Akasha threshold mask v1 (no native quality layer found in validated "
    "LISS-3 BOA sample; provisional)."
)


def source_profile(source_id: str) -> dict[str, Any]:
    try:
        return SOURCE_PROFILES[source_id]
    except KeyError as exc:
        supported = ", ".join(sorted(SOURCE_PROFILES))
        raise SystemExit(
            f"Unsupported ResourceSat BOA source '{source_id}'. Supported: {supported}"
        ) from exc


def mask_method_for_source(source_id: str) -> str:
    method = source_profile(source_id).get("mask_method")
    return str(method or MASK_METHOD)


ANALYTIC_BANDS = LISS3_ANALYTIC_BANDS


def analytic_bands_for_source(source_id: str) -> tuple[tuple[str, str, str], ...]:
    return tuple(source_profile(source_id).get("analytic_bands") or ANALYTIC_BANDS)


def band_role_mapping_for_source(source_id: str) -> dict[str, str]:
    return {role: band for band, role, _description in analytic_bands_for_source(source_id)}


def reflectance_scale_for_source(source_id: str) -> float:
    return float(source_profile(source_id).get("reflectance_scale", REFLECTANCE_SCALE))


def reflectance_offset_for_source(source_id: str) -> float:
    return float(source_profile(source_id).get("reflectance_offset", REFLECTANCE_OFFSET))

MASK_CLASSES = [
    {"value": 0, "name": "nodata", "description": "No data / all-band gap", "nodata": True},
    {"value": 1, "name": "valid", "description": "Valid clear land or water pixel"},
    {"value": 2, "name": "cloud", "description": "Akasha threshold-derived cloud"},
    {"value": 3, "name": "shadow", "description": "Akasha threshold-derived shadow"},
    {"value": 4, "name": "water", "description": "Akasha threshold-derived water"},
]

MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


@dataclass(frozen=True)
class ResourceSatMeta:
    raw: dict[str, str]
    path: str | None = None
    row: str | None = None
    acquisition_datetime: str | None = None
    background_values: dict[str, int] = field(default_factory=dict)
    valid_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    scale: float = REFLECTANCE_SCALE
    offset: float = REFLECTANCE_OFFSET


@dataclass(frozen=True)
class SelectedProduct:
    product_id: str
    source_path: Path
    acquisition_datetime: str
    acquisition_date: str
    path: str | None
    row: str | None
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreparedPaths:
    product: SelectedProduct
    product_dir: Path
    output_dir: Path
    analytic_cog: Path
    mask_cog: Path
    manifest: Path


def require_raster_deps() -> dict[str, Any]:
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject, transform_bounds
        from rio_cogeo.cogeo import cog_translate, cog_validate
        from rio_cogeo.profiles import cog_profiles
    except ModuleNotFoundError as exc:
        missing = exc.name or "raster dependency"
        raise SystemExit(
            f"Missing {missing}. Run this via the ingestion container, or install "
            "services/ingestion/requirements.txt in a Python 3.11 environment."
        ) from exc
    return {
        "np": np,
        "rasterio": rasterio,
        "Resampling": Resampling,
        "reproject": reproject,
        "transform_bounds": transform_bounds,
        "cog_translate": cog_translate,
        "cog_validate": cog_validate,
        "cog_profiles": cog_profiles,
    }


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def product_id_from_name(value: str | Path) -> str:
    name = Path(value).name
    for suffix in (".SAFE.zip", ".zip", ".SAFE"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def acquisition_datetime_from_text(value: str) -> str | None:
    text = value.upper()
    bhoonidhi = re.search(
        r"(\d{1,2})[-_\s]?(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-_\s]?(\d{4})",
        text,
    )
    if bhoonidhi:
        day, month, year = bhoonidhi.groups()
        try:
            parsed = datetime(int(year), int(MONTHS[month]), int(day))
        except ValueError:
            return None
        return parsed.strftime("%Y-%m-%dT00:00:00Z")
    iso = re.search(r"(\d{4})-?(\d{2})-?(\d{2})(?:T(\d{2}):?(\d{2}):?(\d{2}))?", text)
    if iso:
        year, month, day, hour, minute, second = iso.groups()
        try:
            parsed = datetime(
                int(year),
                int(month),
                int(day),
                int(hour or "00"),
                int(minute or "00"),
                int(second or "00"),
            )
        except ValueError:
            return None
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def acquisition_date_from_datetime(value: str) -> str:
    return value[:10]


def parse_band_meta(path: Path, *, source_id: str = SOURCE_ID) -> ResourceSatMeta:
    raw: dict[str, str] = {}
    background_values: dict[str, int] = {}
    valid_ranges: dict[str, tuple[float, float]] = {}
    analytic_bands = analytic_bands_for_source(source_id)
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
        else:
            continue
        normalized_key = re.sub(r"[^A-Z0-9]+", "_", key.strip().upper()).strip("_")
        raw[normalized_key] = value.strip()

    for band, _role, _description in analytic_bands:
        for suffix in ("BACKGROUND", "BACKGROUND_VALUE", "FILL", "FILL_VALUE", "NODATA"):
            value = raw.get(f"{band}_{suffix}") or raw.get(f"{suffix}_{band}")
            if value is not None:
                try:
                    background_values[band] = int(float(value))
                except ValueError:
                    pass
        valid_range = _range_meta(
            raw,
            f"{band}_VALID_RANGE",
            f"{band}_RANGE",
            f"{band}_DN_RANGE",
        )
        if valid_range is None:
            valid_range = _paired_range_meta(
                raw,
                (f"{band}_VALID_MIN", f"{band}_MIN", f"{band}_DN_MIN"),
                (f"{band}_VALID_MAX", f"{band}_MAX", f"{band}_DN_MAX"),
            )
        if valid_range is not None:
            valid_ranges[band] = valid_range

    scale = _float_meta(raw, "SCALE", "REFLECTANCE_SCALE", "MULTIPLIER") or REFLECTANCE_SCALE
    offset = _float_meta(raw, "OFFSET", "REFLECTANCE_OFFSET", "ADD_OFFSET") or REFLECTANCE_OFFSET
    default_valid_range = _range_meta(raw, "VALID_RANGE", "RANGE", "DN_RANGE")
    if default_valid_range is None:
        default_valid_range = _paired_range_meta(
            raw,
            ("VALID_MIN", "MIN", "DN_MIN"),
            ("VALID_MAX", "MAX", "DN_MAX"),
        )
    if default_valid_range is not None:
        for band, _role, _description in analytic_bands:
            valid_ranges.setdefault(band, default_valid_range)
    acquisition_datetime = _first_meta(raw, "ACQUISITION_DATETIME", "DATETIME", "DATE")
    if acquisition_datetime:
        acquisition_datetime = acquisition_datetime_from_text(acquisition_datetime)
    return ResourceSatMeta(
        raw=raw,
        path=_first_meta(raw, "PATH", "PATH_NO", "PATH_NUMBER"),
        row=_first_meta(raw, "ROW", "ROW_NO", "ROW_NUMBER"),
        acquisition_datetime=acquisition_datetime,
        background_values=background_values,
        valid_ranges=valid_ranges,
        scale=float(scale),
        offset=float(offset),
    )


def _first_meta(raw: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _float_meta(raw: dict[str, str], *keys: str) -> float | None:
    value = _first_meta(raw, *keys)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _range_meta(raw: dict[str, str], *keys: str) -> tuple[float, float] | None:
    value = _first_meta(raw, *keys)
    if value is None:
        return None
    match = re.match(
        r"^\s*([-+]?\d+(?:\.\d+)?)\s*(?:-|,|:|\.\.|\bto\b)\s*([-+]?\d+(?:\.\d+)?)\s*$",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    lower, upper = float(match.group(1)), float(match.group(2))
    if lower > upper:
        lower, upper = upper, lower
    return (lower, upper)


def _paired_range_meta(
    raw: dict[str, str],
    lower_keys: tuple[str, ...],
    upper_keys: tuple[str, ...],
) -> tuple[float, float] | None:
    lower = _float_meta(raw, *lower_keys)
    upper = _float_meta(raw, *upper_keys)
    if lower is None or upper is None:
        return None
    if lower > upper:
        lower, upper = upper, lower
    return (lower, upper)


def _entry_value(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in entry and entry[key] not in (None, ""):
            return entry[key]
    props = entry.get("properties")
    if isinstance(props, dict):
        for key in keys:
            if key in props and props[key] not in (None, ""):
                return props[key]
    return None


def _looks_like_source_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return "/" in value or "\\" in value or lowered.endswith((".zip", ".safe", ".tif", ".tiff"))


def source_path_from_manifest_entry(entry: dict[str, Any], product_id: str, raw_dir: Path) -> Path:
    value = _entry_value(
        entry,
        "downloaded_path",
        "download_path",
        "downloadPath",
        "source_zip",
        "sourceZip",
        "local_path",
        "localPath",
    )
    if isinstance(value, str) and value:
        return resolve_repo_path(value)
    path_value = _entry_value(entry, "path")
    if _looks_like_source_path(path_value):
        return resolve_repo_path(str(path_value))
    return raw_dir / f"{product_id}.zip"


def path_row_from_manifest_entry(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    path = _entry_value(entry, "Path", "path_id", "pathId")
    if path in (None, ""):
        raw_path = _entry_value(entry, "path")
        if not _looks_like_source_path(raw_path):
            path = raw_path
    row = _entry_value(entry, "Row", "row_id", "rowId")
    if row in (None, ""):
        row = _entry_value(entry, "row")
    return (
        str(path) if path not in (None, "") else None,
        str(row) if row not in (None, "") else None,
    )


def merge_downloaded_entries_with_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates_by_id: dict[str, dict[str, Any]] = {}
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            product_id = str(
                _entry_value(candidate, "item_id", "product_id", "productId", "id", "name") or ""
            )
            if product_id:
                candidates_by_id[product_id_from_name(product_id)] = candidate

    downloaded = payload.get("downloaded")
    if not isinstance(downloaded, list) or not downloaded:
        return []

    entries: list[dict[str, Any]] = []
    for item in downloaded:
        if not isinstance(item, dict):
            continue
        product_id = str(
            _entry_value(item, "item_id", "product_id", "productId", "id", "name") or ""
        )
        base = dict(candidates_by_id.get(product_id_from_name(product_id), {}))
        merged = {**base, **item}
        if _looks_like_source_path(merged.get("path")) and "downloaded_path" not in merged:
            merged["downloaded_path"] = merged["path"]
        entries.append(merged)
    return entries


def selected_product_from_manifest_entry(
    entry: dict[str, Any],
    *,
    raw_dir: Path,
) -> SelectedProduct:
    product_id = product_id_from_name(
        str(_entry_value(entry, "item_id", "product_id", "productId", "id", "name") or "")
    )
    if not product_id:
        raise SystemExit(f"Selected ResourceSat entry is missing product id: {entry}")
    acquisition_datetime = _entry_value(
        entry, "acquisition_datetime", "acquisitionDatetime", "datetime"
    ) or acquisition_datetime_from_text(product_id)
    if not isinstance(acquisition_datetime, str) or not acquisition_datetime:
        raise SystemExit(f"Could not infer acquisition datetime for {product_id}")
    acquisition_datetime = (
        acquisition_datetime_from_text(acquisition_datetime) or acquisition_datetime
    )
    path, row = path_row_from_manifest_entry(entry)
    bbox = _entry_value(entry, "bbox")
    geometry = _entry_value(entry, "geometry")
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path_from_manifest_entry(entry, product_id, raw_dir),
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date_from_datetime(acquisition_datetime),
        path=path,
        row=row,
        bbox=bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
        geometry=geometry if isinstance(geometry, dict) else None,
    )


def load_selected_products(selection_manifest: Path, *, raw_dir: Path) -> list[SelectedProduct]:
    payload = json.loads(selection_manifest.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    entries.extend(merge_downloaded_entries_with_candidates(payload))
    for key in ("selected_products", "selectedProducts", "candidates"):
        value = payload.get(key)
        if not entries and isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    if not entries:
        selection = payload.get("selection")
        selected_ids = selection.get("selected_product_ids") if isinstance(selection, dict) else []
        entries = [{"item_id": item_id} for item_id in selected_ids or []]
    if not entries:
        raise SystemExit(
            f"Selection manifest contains no ResourceSat products: {selection_manifest}"
        )
    return [
        selected_product_from_manifest_entry(entry, raw_dir=raw_dir)
        for entry in entries
        if str(entry.get("download_status", "downloaded")) != "failed"
    ]


def extract_product(source_path: Path, work_dir: Path, *, overwrite: bool) -> Path:
    if source_path.is_dir():
        return source_path
    if not source_path.exists():
        raise SystemExit(f"ResourceSat ZIP not found: {source_path}")
    product_id = product_id_from_name(source_path)
    target = work_dir / product_id
    if target.exists() and overwrite:
        shutil.rmtree(target)
    if target.exists():
        return target
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as archive:
        bad_file = archive.testzip()
        if bad_file is not None:
            raise SystemExit(f"ZIP integrity check failed at {bad_file}")
        archive.extractall(target)
    return target


def find_band_asset(product_dir: Path, band_name: str) -> Path:
    matches = sorted(
        path
        for pattern in (f"*{band_name}*.tif", f"*{band_name}*.TIF")
        for path in product_dir.rglob(pattern)
        if path.is_file()
    )
    if len(matches) != 1:
        found = "none" if not matches else ", ".join(path.as_posix() for path in matches[:10])
        raise SystemExit(
            f"Expected exactly one {band_name} GeoTIFF under {product_dir}; found {found}"
        )
    return matches[0]


def find_band_meta(product_dir: Path) -> Path:
    matches = sorted(product_dir.rglob("BAND_META.txt"))
    if len(matches) != 1:
        found = "none" if not matches else ", ".join(path.as_posix() for path in matches[:10])
        raise SystemExit(f"Expected exactly one BAND_META.txt under {product_dir}; found {found}")
    return matches[0]


def same_grid(src: Any, reference: Any) -> bool:
    return (
        src.crs == reference.crs
        and src.transform == reference.transform
        and src.width == reference.width
        and src.height == reference.height
    )


def build_mask_array(
    np: Any,
    analytic: Any,
    *,
    background_values: dict[str, int] | None = None,
    valid_ranges: dict[str, tuple[float, float]] | None = None,
    scale: float = REFLECTANCE_SCALE,
    offset: float = REFLECTANCE_OFFSET,
    cloud_brightness_threshold: float = 0.32,
    cloud_swir_threshold: float = 0.20,
    shadow_nir_threshold: float = 0.08,
    shadow_swir_threshold: float = 0.08,
    water_ndwi_threshold: float = 0.20,
    water_nir_max: float = 0.20,
) -> Any:
    """Return ResourceSat mask codes: 0 gap, 1 valid, 2 cloud, 3 shadow, 4 water."""
    background_values = background_values or {}
    valid_ranges = valid_ranges or {}
    data = np.asarray(analytic)
    if data.shape[0] != len(ANALYTIC_BANDS):
        raise ValueError(f"expected {len(ANALYTIC_BANDS)} analytic bands, got {data.shape[0]}")
    gap_parts = []
    for index, (band_name, _role, _description) in enumerate(ANALYTIC_BANDS):
        band_gap = data[index] == background_values.get(band_name, NODATA_DN)
        valid_range = valid_ranges.get(band_name)
        if valid_range is not None:
            lower, upper = valid_range
            band_gap = band_gap | (data[index] < lower) | (data[index] > upper)
        gap_parts.append(band_gap)
    gap = np.logical_and.reduce(gap_parts)

    reflectance = data.astype("float32") * float(scale) + float(offset)
    green, red, nir, swir = reflectance
    denominator = green + nir
    ndwi = np.zeros_like(green, dtype="float32")
    np.divide(green - nir, denominator, out=ndwi, where=np.abs(denominator) > 1e-6)

    brightness = (green + red + nir) / 3.0
    water = (ndwi >= water_ndwi_threshold) & (nir <= water_nir_max) & ~gap
    cloud = (brightness >= cloud_brightness_threshold) & (swir >= cloud_swir_threshold) & ~gap
    shadow = (
        (nir <= shadow_nir_threshold)
        & (swir <= shadow_swir_threshold)
        & (red <= shadow_nir_threshold)
        & ~gap
        & ~water
    )

    mask = np.ones(data.shape[1:], dtype="uint8")
    mask[gap] = 0
    mask[cloud] = 2
    mask[shadow] = 3
    mask[water] = 4
    return mask


def build_mask_array_3band(
    np: Any,
    analytic: Any,
    *,
    background_values: dict[str, int] | None = None,
    valid_ranges: dict[str, tuple[float, float]] | None = None,
    scale: float = REFLECTANCE_SCALE,
    offset: float = REFLECTANCE_OFFSET,
    water_ndwi_threshold: float = 0.20,
    water_nir_max: float = 0.20,
    cloud_brightness_threshold: float = 0.32,
    cloud_ndvi_max: float = 0.20,
    shadow_threshold: float = 0.08,
) -> Any:
    """Return LISS-4 mask codes: 0 gap, 1 valid, 2 cloud, 3 shadow, 4 water."""
    background_values = background_values or {}
    valid_ranges = valid_ranges or {}
    data = np.asarray(analytic)
    expected_bands = LISS4_ANALYTIC_BANDS
    if data.shape[0] != len(expected_bands):
        raise ValueError(f"expected {len(expected_bands)} analytic bands, got {data.shape[0]}")
    gap_parts = []
    for index, (band_name, _role, _description) in enumerate(expected_bands):
        band_gap = data[index] == background_values.get(band_name, NODATA_DN)
        valid_range = valid_ranges.get(band_name)
        if valid_range is not None:
            lower, upper = valid_range
            band_gap = band_gap | (data[index] < lower) | (data[index] > upper)
        gap_parts.append(band_gap)
    gap = np.logical_and.reduce(gap_parts)

    reflectance = data.astype("float32") * float(scale) + float(offset)
    green, red, nir = reflectance
    ndwi_denominator = green + nir
    ndwi = np.zeros_like(green, dtype="float32")
    np.divide(
        green - nir,
        ndwi_denominator,
        out=ndwi,
        where=np.abs(ndwi_denominator) > 1e-6,
    )
    ndvi_denominator = nir + red
    ndvi = np.zeros_like(nir, dtype="float32")
    np.divide(
        nir - red,
        ndvi_denominator,
        out=ndvi,
        where=np.abs(ndvi_denominator) > 1e-6,
    )

    brightness = (green + red + nir) / 3.0
    water = (ndwi >= water_ndwi_threshold) & (nir <= water_nir_max) & ~gap
    cloud = (
        (brightness >= cloud_brightness_threshold)
        & (ndvi <= cloud_ndvi_max)
        & ~gap
        & ~water
    )
    shadow = (
        (green <= shadow_threshold)
        & (red <= shadow_threshold)
        & (nir <= shadow_threshold)
        & ~gap
        & ~water
        & ~cloud
    )

    mask = np.ones(data.shape[1:], dtype="uint8")
    mask[gap] = 0
    mask[water] = 4
    mask[cloud] = 2
    mask[shadow] = 3
    return mask


def build_mask_array_for_source(
    np: Any,
    analytic: Any,
    *,
    source_id: str,
    background_values: dict[str, int] | None = None,
    valid_ranges: dict[str, tuple[float, float]] | None = None,
    scale: float = REFLECTANCE_SCALE,
    offset: float = REFLECTANCE_OFFSET,
) -> Any:
    builder = source_profile(source_id).get("mask_builder", "4band")
    if builder == "3band":
        return build_mask_array_3band(
            np,
            analytic,
            background_values=background_values,
            valid_ranges=valid_ranges,
            scale=scale,
            offset=offset,
        )
    return build_mask_array(
        np,
        analytic,
        background_values=background_values,
        valid_ranges=valid_ranges,
        scale=scale,
        offset=offset,
    )


def build_analytic_intermediate(
    *,
    deps: dict[str, Any],
    product_dir: Path,
    output_path: Path,
    source_id: str,
    overwrite: bool,
) -> Path:
    np = deps["np"]
    rasterio = deps["rasterio"]
    Resampling = deps["Resampling"]
    reproject = deps["reproject"]
    analytic_bands = analytic_bands_for_source(source_id)

    if output_path.exists() and not overwrite:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    reference_path = find_band_asset(product_dir, analytic_bands[0][0])
    with rasterio.open(reference_path) as reference:
        profile = reference.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(analytic_bands),
            dtype="uint16",
            nodata=NODATA_DN,
            tiled=True,
            blockxsize=COG_BLOCKSIZE,
            blockysize=COG_BLOCKSIZE,
            compress="DEFLATE",
            predictor=2,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            for band_index, (band_name, role, description) in enumerate(analytic_bands, start=1):
                source_path = find_band_asset(product_dir, band_name)
                with rasterio.open(source_path) as src:
                    if same_grid(src, reference):
                        data = src.read(1)
                    else:
                        data = np.zeros((reference.height, reference.width), dtype="uint16")
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=data,
                            src_transform=src.transform,
                            src_crs=src.crs,
                            src_nodata=NODATA_DN,
                            dst_transform=reference.transform,
                            dst_crs=reference.crs,
                            dst_nodata=NODATA_DN,
                            resampling=Resampling.bilinear,
                        )
                    dst.write(data, band_index)
                    dst.set_band_description(band_index, band_name)
                    dst.update_tags(
                        band_index,
                        name=band_name,
                        role=role,
                        description=description,
                        source_asset=band_name,
                    )
            dst.update_tags(
                AKASHA_SOURCE_ID=source_id,
                AKASHA_BAND_ORDER=",".join(band for band, _role, _desc in analytic_bands),
                AKASHA_REFLECTANCE_SCALE=str(reflectance_scale_for_source(source_id)),
                AKASHA_REFLECTANCE_OFFSET=str(reflectance_offset_for_source(source_id)),
                AREA_OR_POINT="Area",
            )
    return output_path


def build_mask_intermediate(
    *,
    deps: dict[str, Any],
    analytic_path: Path,
    output_path: Path,
    meta: ResourceSatMeta,
    source_id: str,
    overwrite: bool,
) -> Path:
    np = deps["np"]
    rasterio = deps["rasterio"]
    if output_path.exists() and not overwrite:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with rasterio.open(analytic_path) as src:
        analytic = src.read()
        mask = build_mask_array_for_source(
            np,
            analytic,
            source_id=source_id,
            background_values=meta.background_values,
            valid_ranges=meta.valid_ranges,
            scale=meta.scale,
            offset=meta.offset,
        )
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="uint8",
            nodata=0,
            tiled=True,
            blockxsize=COG_BLOCKSIZE,
            blockysize=COG_BLOCKSIZE,
            compress="DEFLATE",
            predictor=1,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mask, 1)
            dst.set_band_description(1, "mask")
            mask_method = mask_method_for_source(source_id)
            dst.update_tags(
                1,
                name="mask",
                description=mask_method,
                classes=json.dumps(MASK_CLASSES),
            )
            dst.update_tags(AKASHA_MASK_METHOD=mask_method, AREA_OR_POINT="Area")
    return output_path


def translate_to_cog(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    overview_resampling: str,
    overwrite: bool,
) -> None:
    if output_path.exists() and not overwrite:
        print(f"keep existing {output_path}")
        return
    if output_path.exists():
        output_path.unlink()
    profile = deps["cog_profiles"].get("deflate")
    profile.update(
        {
            "blocksize": COG_BLOCKSIZE,
            "BIGTIFF": "IF_SAFER",
            "overview_resampling": overview_resampling,
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deps["cog_translate"](
        str(source_path),
        str(output_path),
        profile,
        nodata=NODATA_DN,
        overview_resampling=overview_resampling,
        quiet=False,
    )


def validate_cog(deps: dict[str, Any], path: Path) -> None:
    is_valid, errors, warnings = deps["cog_validate"](str(path), strict=True)
    for warning in warnings:
        print(f"warning {path.name}: {warning}")
    if not is_valid:
        for error in errors:
            print(f"error {path.name}: {error}")
        raise SystemExit(f"COG validation failed for {path}")


def validate_resourcesat_cogs(
    deps: dict[str, Any],
    analytic_path: Path,
    mask_path: Path,
    *,
    source_id: str = SOURCE_ID,
    resolution_tolerance: float = 0.25,
    require_overviews: bool = True,
) -> None:
    validate_cog(deps, analytic_path)
    validate_cog(deps, mask_path)

    expected_resolution = float(source_profile(source_id)["resolution_meters"])
    expected_band_count = len(analytic_bands_for_source(source_id))
    allowed_mask_values = {int(item["value"]) for item in MASK_CLASSES}
    problems: list[str] = []
    with deps["rasterio"].open(analytic_path) as analytic, deps["rasterio"].open(mask_path) as mask:
        if analytic.count != expected_band_count:
            problems.append(f"analytic band count {analytic.count} != {expected_band_count}")
        if mask.count != 1:
            problems.append(f"mask band count {mask.count} != 1")
        if analytic.crs is None or mask.crs is None:
            problems.append("analytic/mask CRS is missing")
        elif analytic.crs != mask.crs:
            problems.append(f"analytic/mask CRS mismatch: {analytic.crs} != {mask.crs}")
        if analytic.transform != mask.transform:
            problems.append("analytic/mask transform mismatch")
        if (analytic.width, analytic.height) != (mask.width, mask.height):
            problems.append(
                "analytic/mask dimension mismatch "
                f"{analytic.width}x{analytic.height} != {mask.width}x{mask.height}"
            )
        xres, yres = analytic.res
        if (
            abs(float(xres) - expected_resolution) > resolution_tolerance
            or abs(abs(float(yres)) - expected_resolution) > resolution_tolerance
        ):
            problems.append(
                f"analytic resolution {analytic.res} not within {resolution_tolerance} "
                f"of {expected_resolution}"
            )
        mask_xres, mask_yres = mask.res
        if (
            abs(float(mask_xres) - expected_resolution) > resolution_tolerance
            or abs(abs(float(mask_yres)) - expected_resolution) > resolution_tolerance
        ):
            problems.append(
                f"mask resolution {mask.res} not within {resolution_tolerance} "
                f"of {expected_resolution}"
            )
        if require_overviews:
            if not analytic.overviews(1):
                problems.append("analytic COG has no overviews")
            if not mask.overviews(1):
                problems.append("mask COG has no overviews")
        if mask.count:
            np = deps["np"]
            mask_values = {int(value) for value in np.unique(mask.read(1, masked=False)).tolist()}
            invalid_mask_values = sorted(mask_values - allowed_mask_values)
            if invalid_mask_values:
                problems.append(f"invalid mask class value(s): {invalid_mask_values}")
    if problems:
        raise SystemExit("; ".join(problems))


def geometry_from_bbox(bbox: list[float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def wgs84_bbox_from_dataset(deps: dict[str, Any], dataset: Any) -> list[float] | None:
    if not dataset.crs:
        return None
    west, south, east, north = deps["transform_bounds"](
        dataset.crs,
        "EPSG:4326",
        *dataset.bounds,
        densify_pts=21,
    )
    return [float(west), float(south), float(east), float(north)]


def raster_summary(deps: dict[str, Any], path: Path) -> dict[str, Any]:
    with deps["rasterio"].open(path) as dataset:
        summary = {
            "path": path.as_posix(),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "transform": [float(value) for value in dataset.transform],
            "bounds": [float(value) for value in dataset.bounds],
            "resolution": [float(value) for value in dataset.res],
            "width": dataset.width,
            "height": dataset.height,
            "dimensions": [dataset.width, dataset.height],
            "dtype": dataset.dtypes[0] if dataset.dtypes else None,
            "band_count": dataset.count,
            "nodata": dataset.nodata,
            "descriptions": list(dataset.descriptions),
            "band_descriptions": list(dataset.descriptions),
            "overviews": dataset.overviews(1) if dataset.count else [],
        }
        wgs84_bbox = wgs84_bbox_from_dataset(deps, dataset)
        if wgs84_bbox:
            summary["wgs84_bbox"] = wgs84_bbox
            summary["wgs84_bounds"] = wgs84_bbox
            summary["wgs84_geometry"] = geometry_from_bbox(wgs84_bbox)
        return summary


def write_manifest(
    *,
    deps: dict[str, Any],
    paths: PreparedPaths,
    meta: ResourceSatMeta,
    analytic_intermediate: Path,
    mask_intermediate: Path,
    source_id: str = SOURCE_ID,
    collection: str = BHOONIDHI_COLLECTION,
) -> None:
    analytic_summary = raster_summary(deps, paths.analytic_cog)
    mask_summary = raster_summary(deps, paths.mask_cog)
    mask_method = mask_method_for_source(source_id)
    analytic_bands = analytic_bands_for_source(source_id)
    band_role_mapping = band_role_mapping_for_source(source_id)
    payload: dict[str, Any] = {
        "source_id": source_id,
        "collection": collection,
        "product_id": paths.product.product_id,
        "platform": "resourcesat-2a",
        "product_level": "BOA",
        "acquisition_datetime": paths.product.acquisition_datetime,
        "acquisition_date": paths.product.acquisition_date,
        "path": paths.product.path,
        "row": paths.product.row,
        "source_zip": paths.product.source_path.as_posix(),
        "product_dir": paths.product_dir.as_posix(),
        "analytic_band_order": [band for band, _role, _description in analytic_bands],
        "band_role_mapping": band_role_mapping,
        "mask_method": mask_method,
        "classification_classes": MASK_CLASSES,
        "akasha:metrics_provisional": True,
        "intermediates": {
            "analytic": analytic_intermediate.as_posix(),
            "mask": mask_intermediate.as_posix(),
        },
        "band_meta": {
            "path": find_band_meta(paths.product_dir).as_posix(),
            "background_values": meta.background_values,
            "valid_ranges": meta.valid_ranges,
            "scale": meta.scale,
            "offset": meta.offset,
            "raw": meta.raw,
        },
        "outputs": {
            "analytic": analytic_summary,
            "mask": mask_summary,
        },
        "properties": {
            "akasha:mask_method": mask_method,
            "akasha:metrics_provisional": True,
            "akasha:band_role_mapping": band_role_mapping,
        },
    }
    if paths.product.bbox:
        payload["bbox"] = paths.product.bbox
        payload["geometry"] = paths.product.geometry or geometry_from_bbox(paths.product.bbox)
    elif analytic_summary.get("wgs84_bbox"):
        payload["bbox"] = analytic_summary["wgs84_bbox"]
        payload["geometry"] = analytic_summary.get("wgs84_geometry") or geometry_from_bbox(
            analytic_summary["wgs84_bbox"]
        )
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {paths.manifest}")


def selected_product_from_args(args: argparse.Namespace, source_path: Path) -> SelectedProduct:
    product_id = product_id_from_name(args.product_id or source_path)
    acquisition_datetime = args.acquisition_datetime or acquisition_datetime_from_text(product_id)
    if not acquisition_datetime:
        raise SystemExit("--acquisition-datetime is required when it cannot be inferred")
    path = args.path
    row = args.row
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path,
        acquisition_datetime=acquisition_datetime,
        acquisition_date=args.date or acquisition_date_from_datetime(acquisition_datetime),
        path=path,
        row=row,
    )


def output_dir_for_product(output_root: Path, product: SelectedProduct) -> Path:
    return output_root / "scene" / product.acquisition_date / scene_component(product)


def safe_component(value: str, default: str = "unknown") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", str(value).strip()).strip("-")
    return cleaned or default


def compact_datetime(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", value)


def product_id_hash(product_id: str) -> str:
    return hashlib.sha1(product_id.encode("utf-8")).hexdigest()[:12]


def scene_component(product: SelectedProduct) -> str:
    return (
        f"{compact_datetime(product.acquisition_datetime)}_"
        f"path-{safe_component(product.path or 'unknown')}_"
        f"row-{safe_component(product.row or 'unknown')}_{product_id_hash(product.product_id)}"
    )


def prepared_paths(
    product: SelectedProduct,
    product_dir: Path,
    output_root: Path,
) -> PreparedPaths:
    output_dir = output_dir_for_product(output_root, product)
    return PreparedPaths(
        product=product,
        product_dir=product_dir,
        output_dir=output_dir,
        analytic_cog=output_dir / "analytic.tif",
        mask_cog=output_dir / "mask.tif",
        manifest=output_dir / "prepare_manifest.json",
    )


def prepare_one(
    *,
    product: SelectedProduct,
    args: argparse.Namespace,
    deps: dict[str, Any],
) -> PreparedPaths:
    product_dir = extract_product(
        product.source_path,
        resolve_repo_path(args.work_dir),
        overwrite=args.reextract,
    )
    meta = parse_band_meta(find_band_meta(product_dir), source_id=args.source)
    path_value = product.path or meta.path
    row_value = product.row or meta.row
    if not path_value or not row_value:
        raise SystemExit(f"ResourceSat product {product.product_id} is missing path/row")
    product = SelectedProduct(
        product_id=product.product_id,
        source_path=product.source_path,
        acquisition_datetime=product.acquisition_datetime,
        acquisition_date=product.acquisition_date,
        path=path_value,
        row=row_value,
        bbox=product.bbox,
        geometry=product.geometry,
    )
    paths = prepared_paths(product, product_dir, resolve_repo_path(args.output_root))
    temp_dir = paths.output_dir / "_tmp"
    analytic_intermediate = temp_dir / "analytic_intermediate.tif"
    mask_intermediate = temp_dir / "mask_intermediate.tif"

    build_analytic_intermediate(
        deps=deps,
        product_dir=product_dir,
        output_path=analytic_intermediate,
        source_id=args.source,
        overwrite=args.overwrite,
    )
    build_mask_intermediate(
        deps=deps,
        analytic_path=analytic_intermediate,
        output_path=mask_intermediate,
        meta=meta,
        source_id=args.source,
        overwrite=args.overwrite,
    )
    translate_to_cog(
        deps=deps,
        source_path=analytic_intermediate,
        output_path=paths.analytic_cog,
        overview_resampling="average",
        overwrite=args.overwrite,
    )
    translate_to_cog(
        deps=deps,
        source_path=mask_intermediate,
        output_path=paths.mask_cog,
        overview_resampling="nearest",
        overwrite=args.overwrite,
    )
    if not args.skip_validation:
        validate_resourcesat_cogs(
            deps,
            paths.analytic_cog,
            paths.mask_cog,
            source_id=args.source,
        )
    write_manifest(
        deps=deps,
        paths=paths,
        meta=meta,
        analytic_intermediate=analytic_intermediate,
        mask_intermediate=mask_intermediate,
        source_id=args.source,
        collection=source_profile(args.source)["collection"],
    )
    if not args.keep_intermediate and temp_dir.exists():
        shutil.rmtree(temp_dir)
    return paths


def write_batch_manifest(
    *,
    output_root: Path,
    selection_manifest: Path,
    prepared: list[PreparedPaths],
    source_id: str,
) -> Path:
    path = output_root / f"{source_id}_batch_prepare_manifest.json"
    payload = {
        "source_id": source_id,
        "selection_manifest": selection_manifest.as_posix(),
        "product_count": len(prepared),
        "products": [
            {
                "product_id": item.product.product_id,
                "path": item.product.path,
                "row": item.product.row,
                "acquisition_datetime": item.product.acquisition_datetime,
                "acquisition_date": item.product.acquisition_date,
                "source_zip": item.product.source_path.as_posix(),
                "output_dir": item.output_dir.as_posix(),
                "analytic": item.analytic_cog.as_posix(),
                "mask": item.mask_cog.as_posix(),
                "prepare_manifest": item.manifest.as_posix(),
            }
            for item in prepared
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"batch manifest: {path}")
    return path


def latest_source_path(raw_dir: Path) -> Path:
    candidates = sorted(
        [*raw_dir.rglob("*.zip"), *raw_dir.rglob("*.SAFE")],
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(f"No ResourceSat ZIP/directory found under {raw_dir}. Pass --zip-path.")
    return candidates[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=SOURCE_ID,
        choices=sorted(SOURCE_PROFILES),
        help="ResourceSat BOA source id to prepare.",
    )
    parser.add_argument("--zip-path", help="Path to Bhoonidhi ResourceSat ZIP")
    parser.add_argument("--selection-manifest", help="Bhoonidhi download manifest")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--product-id", help="Override product id in single-product mode")
    parser.add_argument("--date", help="Acquisition date, e.g. 2026-03-19")
    parser.add_argument("--acquisition-datetime", help="Acquisition datetime")
    parser.add_argument("--path", help="ResourceSat path number")
    parser.add_argument("--row", help="ResourceSat row number")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--reextract", action="store_true", help="Re-extract source ZIP")
    parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate GTiffs")
    parser.add_argument("--skip-validation", action="store_true", help="Skip rio-cogeo validation")
    args = parser.parse_args(argv)

    if args.selection_manifest and args.zip_path:
        raise SystemExit("--zip-path cannot be combined with --selection-manifest")
    profile = source_profile(args.source)
    if args.raw_dir is None:
        args.raw_dir = str(
            (REPO_ROOT / "data" / "raw" / "bhoonidhi" / args.source).relative_to(REPO_ROOT)
        )
    if args.work_dir is None:
        args.work_dir = str(
            (REPO_ROOT / "data" / "work" / "bhoonidhi" / args.source).relative_to(REPO_ROOT)
        )
    if args.output_root is None:
        args.output_root = str(
            (REPO_ROOT / "data" / "seed" / "rasters" / args.source).relative_to(REPO_ROOT)
        )
    deps = require_raster_deps()
    raw_dir = resolve_repo_path(args.raw_dir)
    output_root = resolve_repo_path(args.output_root)
    if args.selection_manifest:
        selection_manifest = resolve_repo_path(args.selection_manifest)
        products = load_selected_products(selection_manifest, raw_dir=raw_dir)
        prepared = [prepare_one(product=product, args=args, deps=deps) for product in products]
        write_batch_manifest(
            output_root=output_root,
            selection_manifest=selection_manifest,
            prepared=prepared,
            source_id=args.source,
        )
    else:
        source_path = (
            resolve_repo_path(args.zip_path) if args.zip_path else latest_source_path(raw_dir)
        )
        product = selected_product_from_args(args, source_path)
        prepare_one(product=product, args=args, deps=deps)
    print(f"ResourceSat {profile['label']} BOA COG preparation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
