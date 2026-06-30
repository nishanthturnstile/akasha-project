"""Prepare Akasha EOS-04 (RISAT-class C-band) SAR-MRS L2B backscatter COGs.

EOS-04 SAR-MRS **L2B** products downloaded from ISRO Bhoonidhi are already
geocoded / terrain-corrected, so — unlike Sentinel-1 GRD — no ESA SNAP step is
required. This script extracts the product, reads the calibrated backscatter
band(s), converts to a dB scale when needed, and writes a deterministic
single-/dual-pol ``backscatter.tif`` COG plus a ``prepare_manifest.json`` that
matches the SAR ingestion contract consumed by
``akasha_ingest.scene.SceneIdentity`` and ``akasha_ingest.catalog`` /
``akasha_ingest.storage``.

Outputs are written under:

    data/seed/rasters/eos-04-sar-mrs-l2b/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif
    data/seed/rasters/eos-04-sar-mrs-l2b/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/prepare_manifest.json

Batch mode accepts downloader manifests with ``selected_products`` or
``selection.selected_product_ids`` entries (the shape emitted by
``worker.py bhoonidhi-download``), analogous to the ResourceSat / Sentinel-1
prep scripts.

Step 0 (format validation): before trusting the defaults, inspect a real sample
with ``gdalinfo`` and confirm band count, polarization order, data type, nodata,
and whether pixel values are linear power (small positives), amplitude (DN), or
already dB (negatives). Set ``--input-scale`` and ``--polarizations`` to match.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "eos-04-sar-mrs-l2b"
BHOONIDHI_COLLECTION = "EOS-04_SAR-MRS_L2B"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "bhoonidhi" / SOURCE_ID
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "work" / "bhoonidhi" / SOURCE_ID
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "seed" / "rasters" / SOURCE_ID
RUNBOOK_PATH = "docs/eos04-sar-mrs-l2b-cog-prep-runbook.md"
PROCESSING_VERSION = "akasha-eos04-sar-mrs-l2b-v1"
DEFAULT_NODATA = -9999.0
DB_EPSILON = 1e-8
COG_BLOCKSIZE = 512
DEFAULT_VV_RESCALE = "-25,5"

# EOS-04 SAR-MRS is C-band ScanSAR; products are commonly single- or dual-pol.
# Accept the full set of plausible polarization tokens (RISAT circular RH/RV plus
# linear HH/HV/VH/VV) rather than restricting to Sentinel-1's {VV,VH,HH,HV}.
KNOWN_POLARIZATIONS = ("HH", "HV", "VH", "VV", "RH", "RV")
# Stable display order so band 1 (what VV_GRAYSCALE renders) is deterministic.
POL_DISPLAY_ORDER = {pol: index for index, pol in enumerate(KNOWN_POLARIZATIONS)}


@dataclass(frozen=True)
class SelectedProduct:
    product_id: str
    source_path: Path
    acquisition_datetime: str
    acquisition_date: str
    platform: str | None
    relative_orbit: str | None
    orbit_state: str | None
    instrument_mode: str | None
    product_type: str
    polarizations: list[str]
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    scene_component: str | None = None


@dataclass(frozen=True)
class PreparedPaths:
    product: SelectedProduct
    output_dir: Path
    extract_dir: Path
    db_intermediate_tif: Path
    backscatter_cog: Path
    manifest: Path


def require_raster_deps() -> dict[str, Any]:
    try:
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
        from rio_cogeo.cogeo import cog_translate, cog_validate
        from rio_cogeo.profiles import cog_profiles
    except ModuleNotFoundError as exc:
        missing = exc.name or "raster dependency"
        raise SystemExit(
            f"Missing {missing}. Run inside the ingestion container or install "
            f"numpy, rasterio, and rio-cogeo in Python 3.11. See {RUNBOOK_PATH}."
        ) from exc
    return {
        "np": np,
        "rasterio": rasterio,
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
    for suffix in (".zip", ".ZIP"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def acquisition_datetime_from_product_id(product_id: str) -> str | None:
    """Best-effort YYYYMMDD[THHMMSS] extraction from an EOS-04 product id."""
    match = re.search(r"(\d{8})[T_](\d{6})", product_id)
    if match:
        date_value, time_value = match.groups()
        return (
            f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}T"
            f"{time_value[:2]}:{time_value[2:4]}:{time_value[4:6]}Z"
        )
    date_only = re.search(r"(\d{4})(\d{2})(\d{2})", product_id)
    if date_only:
        year, month, day = date_only.groups()
        return f"{year}-{month}-{day}T00:00:00Z"
    return None


def acquisition_date_from_datetime(value: str) -> str:
    match = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", value)
    if not match:
        raise SystemExit(f"Could not infer acquisition date from datetime {value!r}")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def normalize_polarizations(value: Any) -> list[str]:
    raw: list[Any]
    if isinstance(value, str):
        raw = re.split(r"[,;\s]+", value.strip())
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    seen: list[str] = []
    for item in raw:
        pol = str(item).strip().upper()
        if pol in KNOWN_POLARIZATIONS and pol not in seen:
            seen.append(pol)
    return seen


def sort_polarizations(pols: list[str]) -> list[str]:
    return sorted(pols, key=lambda pol: POL_DISPLAY_ORDER.get(pol, len(POL_DISPLAY_ORDER)))


def normalize_relative_orbit(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def relative_orbit_folder(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()) if value else "unknown"


def scene_component(product: SelectedProduct) -> str:
    value = product.scene_component or product.product_id
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())


def _entry_value(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in entry and entry[key] not in (None, ""):
            return entry[key]
    properties = entry.get("properties")
    if isinstance(properties, dict):
        for key in keys:
            if key in properties and properties[key] not in (None, ""):
                return properties[key]
    return None


def _candidate_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("selected_products", "selectedProducts", "candidates", "downloaded"):
        value = payload.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    return entries


def _selected_manifest_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("selected_products", "selectedProducts"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    candidates = _candidate_entries(payload)
    selection = payload.get("selection")
    if isinstance(selection, dict):
        selected_ids = selection.get("selected_product_ids") or selection.get("selectedProductIds")
        if isinstance(selected_ids, list):
            candidates_by_id = {
                product_id_from_name(product_id_from_manifest_entry(candidate)): candidate
                for candidate in candidates
            }
            return [
                dict(
                    candidates_by_id.get(
                        product_id_from_name(str(selected_id)),
                        {"product_id": str(selected_id)},
                    )
                )
                for selected_id in selected_ids
            ]

    if candidates:
        return candidates
    selected = payload.get("selected")
    if isinstance(selected, dict):
        return [selected]
    return []


def product_id_from_manifest_entry(entry: dict[str, Any]) -> str:
    value = _entry_value(entry, "product_id", "productId", "item_id", "id", "name")
    if not isinstance(value, str) or not value:
        raise SystemExit(f"Selected product entry is missing a product id: {entry}")
    return product_id_from_name(value)


def source_path_from_manifest_entry(entry: dict[str, Any], product_id: str, raw_dir: Path) -> Path:
    value = _entry_value(
        entry,
        "zip_path",
        "zipPath",
        "downloaded_path",
        "downloadedPath",
        "download_path",
        "local_path",
        "localPath",
        "path",
    )
    if isinstance(value, str) and value:
        resolved = resolve_repo_path(value)
        if resolved.exists():
            return resolved
    return raw_dir / f"{product_id}.zip"


def selected_product_from_manifest_entry(
    entry: dict[str, Any], *, raw_dir: Path, default_polarizations: list[str]
) -> SelectedProduct:
    product_id = product_id_from_manifest_entry(entry)
    acquisition_datetime = _entry_value(
        entry, "acquisition_datetime", "acquisitionDatetime", "datetime", "acquired"
    )
    if not isinstance(acquisition_datetime, str) or not acquisition_datetime:
        acquisition_datetime = acquisition_datetime_from_product_id(product_id)
    if not acquisition_datetime:
        raise SystemExit(
            f"Could not infer acquisition datetime for {product_id}; pass --acquisition-datetime."
        )

    acquisition_date = _entry_value(entry, "acquisition_date", "acquisitionDate")
    acquisition_date_value = (
        acquisition_date_from_datetime(acquisition_date)
        if isinstance(acquisition_date, str) and acquisition_date
        else acquisition_date_from_datetime(acquisition_datetime)
    )

    polarizations = normalize_polarizations(
        _entry_value(entry, "polarizations", "sar:polarizations")
    ) or list(default_polarizations)
    bbox = _entry_value(entry, "bbox")
    geometry = _entry_value(entry, "geometry")
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path_from_manifest_entry(entry, product_id, raw_dir),
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date_value,
        platform=_entry_value(entry, "platform") or "eos-04",
        relative_orbit=normalize_relative_orbit(
            _entry_value(entry, "relative_orbit", "relativeOrbit", "sat:relative_orbit")
        ),
        orbit_state=_entry_value(
            entry,
            "orbit_state",
            "orbitState",
            "orbit_direction",
            "orbitDirection",
            "sat:orbit_state",
        ),
        instrument_mode=_entry_value(
            entry, "instrument_mode", "instrumentMode", "sar:instrument_mode"
        )
        or "MRS",
        product_type=str(
            _entry_value(entry, "product_type", "productType", "product:type")
            or BHOONIDHI_COLLECTION
        ),
        polarizations=sort_polarizations(polarizations),
        bbox=bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
        geometry=geometry if isinstance(geometry, dict) else None,
        scene_component=_entry_value(entry, "scene_component", "sceneComponent"),
    )


def load_selected_products(
    selection_manifest: Path, *, raw_dir: Path, default_polarizations: list[str]
) -> list[SelectedProduct]:
    payload = json.loads(selection_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Selection manifest must contain a JSON object: {selection_manifest}")
    entries = _selected_manifest_entries(payload)
    if not entries:
        raise SystemExit(f"Selection manifest contains no selected products: {selection_manifest}")
    return [
        selected_product_from_manifest_entry(
            entry, raw_dir=raw_dir, default_polarizations=default_polarizations
        )
        for entry in entries
    ]


def latest_source_path(raw_dir: Path) -> Path:
    candidates = sorted(
        [*raw_dir.rglob("*.zip"), *raw_dir.rglob("*.ZIP")],
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(f"No EOS-04 product ZIP found under {raw_dir}. Pass --zip-path.")
    return candidates[-1].resolve()


def selected_product_from_args(args: argparse.Namespace) -> SelectedProduct:
    source_path = (
        resolve_repo_path(args.zip_path)
        if args.zip_path
        else latest_source_path(resolve_repo_path(args.raw_dir))
    )
    product_id = product_id_from_name(args.product_id or source_path)
    acquisition_datetime = args.acquisition_datetime or acquisition_datetime_from_product_id(
        product_id
    )
    if not acquisition_datetime:
        raise SystemExit(
            f"Could not infer acquisition datetime from {product_id}; pass --acquisition-datetime."
        )
    acquisition_date = args.date or acquisition_date_from_datetime(acquisition_datetime)
    polarizations = sort_polarizations(normalize_polarizations(args.polarizations))
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path,
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date,
        platform=args.platform or "eos-04",
        relative_orbit=normalize_relative_orbit(args.relative_orbit),
        orbit_state=args.orbit_state,
        instrument_mode=args.instrument_mode or "MRS",
        product_type=args.product_type or BHOONIDHI_COLLECTION,
        polarizations=polarizations,
        bbox=None,
        geometry=None,
        scene_component=args.scene_component,
    )


def extract_product(source_path: Path, extract_dir: Path, *, overwrite: bool) -> Path:
    """Return a directory containing the product's GeoTIFF band(s)."""
    if source_path.is_dir():
        return source_path
    if not source_path.exists():
        raise SystemExit(f"EOS-04 product not found: {source_path}. See {RUNBOOK_PATH}.")
    if source_path.suffix.lower() not in {".zip"}:
        # A bare GeoTIFF was provided; treat its parent as the product dir.
        return source_path.parent
    if extract_dir.exists() and overwrite:
        shutil.rmtree(extract_dir)
    if extract_dir.exists():
        return extract_dir
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise SystemExit(f"ZIP integrity check failed at {bad} in {source_path}")
        archive.extractall(extract_dir)
    return extract_dir


def _polarization_from_filename(name: str) -> str | None:
    upper = name.upper()
    # Prefer explicit, delimited tokens (e.g. *_HH.tif, *-RV-*) over substrings.
    for pol in KNOWN_POLARIZATIONS:
        if re.search(rf"(?:^|[^A-Z])({pol})(?:[^A-Z]|$)", upper):
            return pol
    return None


def find_backscatter_bands(
    product_dir: Path, polarizations: list[str], explicit_band: Path | None
) -> list[tuple[str, Path]]:
    """Map polarization -> band GeoTIFF.

    Resolution order: an explicit ``--band-path`` wins; otherwise match
    polarization tokens in filenames; otherwise fall back to sorted TIFFs.
    """
    if explicit_band is not None:
        if not polarizations:
            raise SystemExit(
                "EOS-04 explicit --band-path requires --polarizations so the "
                "backscatter band is not mislabelled."
            )
        pol = polarizations[0]
        return [(pol, explicit_band)]

    tifs = sorted(
        path
        for pattern in ("*.tif", "*.tiff", "*.TIF", "*.TIFF")
        for path in product_dir.rglob(pattern)
        if path.is_file()
    )
    if not tifs:
        raise SystemExit(
            f"No GeoTIFF band found under {product_dir}. Pass --band-path. See {RUNBOOK_PATH}."
        )

    by_pol: dict[str, Path] = {}
    for path in tifs:
        pol = _polarization_from_filename(path.name)
        if pol and pol not in by_pol:
            by_pol[pol] = path

    if by_pol:
        wanted = [pol for pol in polarizations if pol in by_pol] or sort_polarizations(list(by_pol))
        return [(pol, by_pol[pol]) for pol in wanted]

    if not polarizations:
        raise SystemExit(
            "Could not infer EOS-04 SAR polarizations from filenames. Pass "
            "--polarizations (for example HH,HV or RH,RV) instead of relying on a default."
        )

    # No polarization tokens in filenames: assign explicitly declared pols to sorted TIFFs.
    pols = polarizations
    pairs: list[tuple[str, Path]] = []
    for index, path in enumerate(tifs[: len(pols)]):
        pairs.append((pols[index], path))
    return pairs


def detect_input_scale(np: Any, sample: Any, requested: str) -> str:
    """Resolve --input-scale auto into linear|amplitude|db using a value heuristic."""
    if requested != "auto":
        return requested
    finite = sample[np.isfinite(sample)]
    finite = finite[finite != 0]
    if finite.size == 0:
        return "linear"
    median = float(np.median(finite))
    minimum = float(np.min(finite))
    # Already-dB SAR backscatter is dominated by negative values (~ -30..+5 dB).
    if minimum < 0 and median < 0:
        return "db"
    # Large positive integers/floats look like uncalibrated amplitude (DN).
    if median > 100:
        return "amplitude"
    # Small positive sigma0 power values.
    return "linear"


def to_db(np: Any, values: Any, scale: str) -> Any:
    if scale == "db":
        return values.astype("float32")
    if scale == "amplitude":
        return (20.0 * np.log10(np.maximum(values, DB_EPSILON))).astype("float32")
    # linear power -> dB
    return (10.0 * np.log10(np.maximum(values, DB_EPSILON))).astype("float32")


def masked_band_to_float64(np: Any, raw: Any) -> Any:
    """Return a float64 ndarray from a rasterio masked band.

    Rasterio often returns integer masked arrays for SAR products.  Integer
    masked arrays cannot be filled with NaN directly, so cast first.
    """
    if hasattr(raw, "filled"):
        return np.asarray(raw.astype("float64").filled(np.nan), dtype="float64")
    return np.asarray(raw, dtype="float64")


def write_backscatter_db_intermediate(
    *,
    deps: dict[str, Any],
    bands: list[tuple[str, Path]],
    output_path: Path,
    input_scale: str,
    overwrite: bool,
) -> tuple[list[str], str]:
    np = deps["np"]
    rasterio = deps["rasterio"]
    if output_path.exists() and not overwrite:
        print(f"keep existing dB intermediate {output_path}")
        with rasterio.open(output_path) as dataset:
            pols = [str(desc).replace("_dB", "") for desc in dataset.descriptions if desc]
        return pols, input_scale

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    reference_path = bands[0][1]
    resolved_scale = input_scale
    with rasterio.open(reference_path) as ref:
        profile = ref.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(bands),
            dtype="float32",
            nodata=DEFAULT_NODATA,
            tiled=True,
            blockxsize=COG_BLOCKSIZE,
            blockysize=COG_BLOCKSIZE,
            compress="DEFLATE",
            predictor=3,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            for dst_index, (pol, band_path) in enumerate(bands, start=1):
                with rasterio.open(band_path) as src:
                    if (src.width, src.height) != (ref.width, ref.height):
                        raise SystemExit(
                            f"Band {band_path.name} grid {(src.width, src.height)} does not match "
                            f"reference {(ref.width, ref.height)}; "
                            "all polarizations must share a grid."
                        )
                    raw = src.read(1, masked=True)
                    source_nodata = src.nodata
                values = masked_band_to_float64(np, raw)
                valid = np.isfinite(values)
                if source_nodata is not None:
                    valid &= values != float(source_nodata)
                if dst_index == 1:
                    resolved_scale = detect_input_scale(np, values[valid], input_scale)
                    print(f"input scale for {reference_path.name}: {resolved_scale}")
                db = np.full(values.shape, DEFAULT_NODATA, dtype="float32")
                db[valid] = to_db(np, values[valid], resolved_scale)
                dst.write(db, dst_index)
                dst.set_band_description(dst_index, f"{pol}_dB")
                dst.update_tags(
                    dst_index,
                    name=f"{pol}_dB",
                    source_band=band_path.name,
                    input_scale=resolved_scale,
                    formula={
                        "db": "passthrough (already dB)",
                        "linear": f"10*log10(max(sigma0,{DB_EPSILON}))",
                        "amplitude": f"20*log10(max(DN,{DB_EPSILON}))",
                    }[resolved_scale],
                )
            dst.update_tags(
                AKASHA_PROCESSING_VERSION=PROCESSING_VERSION,
                AKASHA_BACKSCATTER_SCALE="dB",
                AKASHA_INPUT_SCALE=resolved_scale,
                AKASHA_NODATA=str(DEFAULT_NODATA),
                AREA_OR_POINT="Area",
            )
    return [pol for pol, _ in bands], resolved_scale


def translate_to_cog(
    *, deps: dict[str, Any], source_path: Path, output_path: Path, overwrite: bool
) -> None:
    if output_path.exists() and not overwrite:
        print(f"keep existing {output_path}")
        return
    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile = deps["cog_profiles"].get("deflate")
    profile.update({"blocksize": COG_BLOCKSIZE, "BIGTIFF": "IF_SAFER"})
    print(f"COG translate {source_path.name} -> {output_path}")
    deps["cog_translate"](
        str(source_path),
        str(output_path),
        profile,
        nodata=DEFAULT_NODATA,
        overview_resampling="average",
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
    print(f"valid COG: {path}")


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
        dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21
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
            "band_descriptions": list(dataset.descriptions),
            "overviews": dataset.overviews(1) if dataset.count else [],
        }
        wgs84_bbox = wgs84_bbox_from_dataset(deps, dataset)
        if wgs84_bbox:
            summary["wgs84_bbox"] = wgs84_bbox
            summary["wgs84_geometry"] = geometry_from_bbox(wgs84_bbox)
        return summary


def parse_rescale(value: str | None, default: tuple[float, float]) -> list[float]:
    if not value:
        return [default[0], default[1]]
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise SystemExit(f"Rescale must be 'min,max', got {value!r}")
    return [float(parts[0]), float(parts[1])]


def prepared_paths(product: SelectedProduct, args: argparse.Namespace) -> PreparedPaths:
    output_root = resolve_repo_path(args.output_root)
    output_dir = (
        output_root
        / product.acquisition_date
        / relative_orbit_folder(product.relative_orbit)
        / scene_component(product)
    )
    work_dir = resolve_repo_path(args.work_dir)
    return PreparedPaths(
        product=product,
        output_dir=output_dir,
        extract_dir=work_dir / product.product_id,
        db_intermediate_tif=output_dir / "_tmp" / "backscatter_db_intermediate.tif",
        backscatter_cog=output_dir / "backscatter.tif",
        manifest=output_dir / "prepare_manifest.json",
    )


def write_manifest(
    *,
    deps: dict[str, Any],
    paths: PreparedPaths,
    actual_polarizations: list[str],
    input_scale: str,
    band_sources: list[str],
    args: argparse.Namespace,
) -> None:
    summary = raster_summary(deps, paths.backscatter_cog)
    vv_rescale = parse_rescale(args.vv_rescale, (-25.0, 5.0))
    product = paths.product
    payload: dict[str, Any] = {
        "source_id": SOURCE_ID,
        "collection": BHOONIDHI_COLLECTION,
        "product_id": product.product_id,
        "product_level": "L2B",
        "platform": product.platform,
        "acquisition_datetime": product.acquisition_datetime,
        "acquisition_date": product.acquisition_date,
        "instrument_mode": product.instrument_mode,
        "sar:instrument_mode": product.instrument_mode,
        "product_type": product.product_type,
        "product:type": product.product_type,
        "relative_orbit": product.relative_orbit,
        "sat:relative_orbit": product.relative_orbit,
        "orbit_state": product.orbit_state,
        "sat:orbit_state": product.orbit_state,
        "polarizations": actual_polarizations,
        "sar:polarizations": actual_polarizations,
        "sar:frequency_band": "C",
        "source_zip": product.source_path.as_posix(),
        "processing_version": PROCESSING_VERSION,
        "processing": {
            "engine": "rasterio + rio-cogeo (no SNAP; L2B is pre-geocoded)",
            "steps": [
                "Extract Bhoonidhi EOS-04 SAR-MRS L2B product",
                "Read calibrated backscatter band(s)",
                f"Convert to dB (input scale: {input_scale})",
                "COG creation with average overviews",
            ],
            "input_scale": input_scale,
            "band_sources": band_sources,
            "nodata": DEFAULT_NODATA,
            "db_epsilon": DB_EPSILON,
        },
        "output_cog_path": paths.backscatter_cog.as_posix(),
        "crs": summary.get("crs"),
        "transform": summary.get("transform"),
        "dimensions": summary.get("dimensions"),
        "nodata": summary.get("nodata"),
        "display_rescale_defaults": {"VV_GRAYSCALE": vv_rescale},
        "outputs": {"backscatter": summary},
    }
    if summary.get("wgs84_bbox"):
        payload["bbox"] = summary["wgs84_bbox"]
        payload["geometry"] = summary["wgs84_geometry"]
    elif product.bbox:
        payload["bbox"] = product.bbox
        payload["geometry"] = product.geometry or geometry_from_bbox(product.bbox)

    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {paths.manifest}")


def prepare_one(
    *, product: SelectedProduct, args: argparse.Namespace, deps: dict[str, Any]
) -> PreparedPaths:
    paths = prepared_paths(product, args)
    print(f"source: {product.source_path}")
    print(f"output: {paths.output_dir}")

    product_dir = extract_product(product.source_path, paths.extract_dir, overwrite=args.reextract)
    explicit_band = resolve_repo_path(args.band_path) if args.band_path else None
    bands = find_backscatter_bands(product_dir, product.polarizations, explicit_band)
    print("bands: " + ", ".join(f"{pol}->{path.name}" for pol, path in bands))

    actual_polarizations, resolved_scale = write_backscatter_db_intermediate(
        deps=deps,
        bands=bands,
        output_path=paths.db_intermediate_tif,
        input_scale=args.input_scale,
        overwrite=args.overwrite,
    )
    translate_to_cog(
        deps=deps,
        source_path=paths.db_intermediate_tif,
        output_path=paths.backscatter_cog,
        overwrite=args.overwrite,
    )
    if not args.skip_validation:
        validate_cog(deps, paths.backscatter_cog)
    write_manifest(
        deps=deps,
        paths=paths,
        actual_polarizations=actual_polarizations,
        input_scale=resolved_scale,
        band_sources=[path.name for _, path in bands],
        args=args,
    )
    if not args.keep_intermediate and (paths.output_dir / "_tmp").exists():
        shutil.rmtree(paths.output_dir / "_tmp")
        print(f"removed temporary files: {paths.output_dir / '_tmp'}")
    return paths


def write_batch_manifest(
    *, output_root: Path, selection_manifest: Path, prepared: list[PreparedPaths]
) -> Path:
    batch_manifest = output_root / "batch_prepare_manifest.json"
    payload = {
        "source_id": SOURCE_ID,
        "selection_manifest": selection_manifest.as_posix(),
        "product_count": len(prepared),
        "processing_version": PROCESSING_VERSION,
        "products": [
            {
                "product_id": item.product.product_id,
                "platform": item.product.platform,
                "acquisition_datetime": item.product.acquisition_datetime,
                "acquisition_date": item.product.acquisition_date,
                "relative_orbit": item.product.relative_orbit,
                "orbit_state": item.product.orbit_state,
                "polarizations": item.product.polarizations,
                "source_zip": item.product.source_path.as_posix(),
                "output_dir": item.output_dir.as_posix(),
                "backscatter": item.backscatter_cog.as_posix(),
                "prepare_manifest": item.manifest.as_posix(),
            }
            for item in prepared
        ],
    }
    batch_manifest.parent.mkdir(parents=True, exist_ok=True)
    batch_manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"batch manifest: {batch_manifest}")
    return batch_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=SOURCE_ID,
        help=f"Source id (uniform with the worker prepare contract); must be {SOURCE_ID}.",
    )
    parser.add_argument("--zip-path", help="Path to a single EOS-04 SAR-MRS L2B product ZIP/dir")
    parser.add_argument("--selection-manifest", help="Downloader selection manifest for batch mode")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT.relative_to(REPO_ROOT)))
    parser.add_argument("--product-id", help="Override product id for single-product mode")
    parser.add_argument("--date", help="Output acquisition date folder, e.g. 2026-06-15")
    parser.add_argument(
        "--acquisition-datetime", help="Acquisition datetime, e.g. 2026-06-15T05:30:00Z"
    )
    parser.add_argument("--platform", help="Platform, default eos-04")
    parser.add_argument("--relative-orbit", help="Relative orbit number for output path/manifest")
    parser.add_argument("--orbit-state", help="Orbit state/direction, e.g. ascending")
    parser.add_argument("--instrument-mode", help="SAR instrument mode, default MRS")
    parser.add_argument("--product-type", help=f"Product type, default {BHOONIDHI_COLLECTION}")
    parser.add_argument(
        "--polarizations",
        help="Comma-separated polarizations (e.g. HH,HV). Inferred from filenames when omitted.",
    )
    parser.add_argument(
        "--band-path", help="Explicit single backscatter GeoTIFF (overrides discovery)"
    )
    parser.add_argument(
        "--input-scale",
        choices=("auto", "linear", "amplitude", "db"),
        default="auto",
        help="Calibration scale of the source pixels; 'auto' uses a value heuristic.",
    )
    parser.add_argument(
        "--scene-component", help="Collision-safe output component; default product id"
    )
    parser.add_argument(
        "--vv-rescale", default=DEFAULT_VV_RESCALE, help="Display dB rescale min,max"
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--reextract", action="store_true", help="Re-extract the source ZIP")
    parser.add_argument(
        "--keep-intermediate", action="store_true", help="Keep dB intermediate TIFF"
    )
    parser.add_argument("--skip-validation", action="store_true", help="Skip rio-cogeo validation")
    args = parser.parse_args(argv)

    if args.source != SOURCE_ID:
        raise SystemExit(f"This script only prepares {SOURCE_ID}; got --source {args.source!r}.")
    if args.selection_manifest and args.zip_path:
        raise SystemExit("--zip-path cannot be combined with --selection-manifest")
    if args.selection_manifest and args.date:
        raise SystemExit("--date cannot be combined with --selection-manifest")

    deps = require_raster_deps()
    output_root = resolve_repo_path(args.output_root)
    default_polarizations = sort_polarizations(normalize_polarizations(args.polarizations))

    if args.selection_manifest:
        selection_manifest = resolve_repo_path(args.selection_manifest)
        selected_products = load_selected_products(
            selection_manifest,
            raw_dir=resolve_repo_path(args.raw_dir),
            default_polarizations=default_polarizations,
        )
        prepared = [
            prepare_one(product=product, args=args, deps=deps) for product in selected_products
        ]
        write_batch_manifest(
            output_root=output_root,
            selection_manifest=selection_manifest,
            prepared=prepared,
        )
    else:
        product = selected_product_from_args(args)
        prepare_one(product=product, args=args, deps=deps)

    print("EOS-04 SAR-MRS L2B COG preparation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
