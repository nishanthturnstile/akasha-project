"""Prepare Akasha Sentinel-1 GRD backscatter COGs from native SAFE ZIPs.

The first implementation uses ESA SNAP GPT for SAR preprocessing and rasterio /
rio-cogeo for deterministic dB conversion and COG creation.

Outputs are written under:

    data/seed/rasters/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/backscatter.tif
    data/seed/rasters/sentinel-1-grd/{acquisitionDate}/{relativeOrbitOrUnknown}/{sceneComponent}/prepare_manifest.json

Batch mode accepts downloader manifests with ``selected_products`` or
``selection.selected_product_ids`` entries, analogous to the Sentinel-2 prep
script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "sentinel-1-grd"
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "work" / "sentinel-1-grd"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "seed" / "rasters" / "sentinel-1-grd"
RUNBOOK_PATH = "docs/archive/sentinel-1-grd-cog-prep-runbook.md"
PROCESSING_GRAPH_VERSION = "akasha-s1-grd-snap-v1"
COG_SAFE_FALLBACK_GRAPH_VERSION = "akasha-s1-grd-cog-safe-display-fallback-v1"
DEFAULT_DEM_SOURCE = "Copernicus 30m Global DEM"
DEFAULT_FALLBACK_DEM_SOURCE = "SRTM 1Sec HGT"
DEFAULT_TARGET_CRS = "EPSG:4326"
DEFAULT_PIXEL_SPACING_METERS = 10.0
DEFAULT_NODATA = -9999.0
DB_EPSILON = 1e-8
COG_BLOCKSIZE = 512


@dataclass(frozen=True)
class SelectedProduct:
    product_id: str
    source_path: Path
    acquisition_datetime: str
    acquisition_date: str
    platform: str | None
    relative_orbit: str | None
    orbit_direction: str | None
    polarizations: list[str]
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    scene_component: str | None = None


@dataclass(frozen=True)
class PreparedPaths:
    product: SelectedProduct
    output_dir: Path
    snap_linear_tif: Path
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
            f"Missing {missing}. Build/run the ingestion-sar container or install "
            "numpy, rasterio, and rio-cogeo in Python 3.11. See "
            f"{RUNBOOK_PATH}."
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
    for suffix in (".SAFE.zip", ".zip", ".SAFE"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def acquisition_datetime_from_product_id(product_id: str) -> str | None:
    match = re.search(r"_(\d{8})T(\d{6})_", product_id)
    if not match:
        return None
    date_value, time_value = match.groups()
    return (
        f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}T"
        f"{time_value[:2]}:{time_value[2:4]}:{time_value[4:6]}Z"
    )


def acquisition_date_from_datetime(value: str) -> str:
    match = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", value)
    if not match:
        raise SystemExit(f"Could not infer acquisition date from datetime {value!r}")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def platform_from_product_id(product_id: str) -> str | None:
    prefix = product_id.upper().split("_", 1)[0]
    if prefix == "S1A":
        return "sentinel-1a"
    if prefix == "S1B":
        return "sentinel-1b"
    if prefix == "S1C":
        return "sentinel-1c"
    return None


def polarizations_from_product_id(product_id: str) -> list[str]:
    parts = product_id.upper().split("_")
    if len(parts) >= 4:
        pol_code = parts[3][-2:]
        mapping = {
            "DV": ["VV", "VH"],
            "SV": ["VV"],
            "DH": ["HH", "HV"],
            "SH": ["HH"],
        }
        if pol_code in mapping:
            return mapping[pol_code]
    return ["VV", "VH"]


def normalize_polarizations(value: Any, fallback_product_id: str) -> list[str]:
    raw: list[Any]
    if isinstance(value, str):
        raw = re.split(r"[,;\s]+", value.strip())
    elif isinstance(value, list):
        raw = value
    else:
        raw = polarizations_from_product_id(fallback_product_id)
    seen: list[str] = []
    for item in raw:
        pol = str(item).strip().upper()
        if pol in {"VV", "VH", "HH", "HV"} and pol not in seen:
            seen.append(pol)
    return seen or polarizations_from_product_id(fallback_product_id)


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
    for key in ("selected_products", "selectedProducts", "candidates", "inspected_products"):
        value = payload.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    return entries


def _selected_manifest_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("selected_products", "selectedProducts"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    selection = payload.get("selection")
    if isinstance(selection, dict):
        for key in ("selected_products", "selectedProducts", "products"):
            value = selection.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        selected_ids = selection.get("selected_product_ids") or selection.get("selectedProductIds")
        if isinstance(selected_ids, list):
            candidates_by_id = {
                product_id_from_manifest_entry(candidate): candidate
                for candidate in _candidate_entries(payload)
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

    selected = payload.get("selected")
    if isinstance(selected, dict):
        return [selected]
    return []


def product_id_from_manifest_entry(entry: dict[str, Any]) -> str:
    value = _entry_value(
        entry,
        "product_id",
        "productId",
        "item_id",
        "id",
        "safe_name",
        "name",
    )
    if not isinstance(value, str) or not value:
        raise SystemExit(f"Selected product entry is missing a product id: {entry}")
    return product_id_from_name(value)


def source_path_from_manifest_entry(entry: dict[str, Any], product_id: str, raw_dir: Path) -> Path:
    value = _entry_value(
        entry,
        "zip_path",
        "zipPath",
        "source_zip",
        "sourceZip",
        "download_path",
        "downloadPath",
        "local_path",
        "localPath",
        "path",
    )
    if isinstance(value, str) and value:
        resolved = resolve_repo_path(value)
        if resolved.exists():
            return resolved
    safe_name = _entry_value(entry, "safe_name", "safeName")
    if isinstance(safe_name, str) and safe_name:
        return raw_dir / safe_name / f"{safe_name}.zip"
    return raw_dir / product_id / f"{product_id}.SAFE.zip"


def selected_product_from_manifest_entry(
    entry: dict[str, Any], *, raw_dir: Path
) -> SelectedProduct:
    product_id = product_id_from_manifest_entry(entry)
    acquisition_datetime = _entry_value(
        entry,
        "acquisition_datetime",
        "acquisitionDatetime",
        "datetime",
        "acquired",
    )
    if not isinstance(acquisition_datetime, str) or not acquisition_datetime:
        acquisition_datetime = acquisition_datetime_from_product_id(product_id)
    if not acquisition_datetime:
        raise SystemExit(f"Could not infer acquisition datetime for selected product {product_id}")

    acquisition_date = _entry_value(entry, "acquisition_date", "acquisitionDate")
    acquisition_date_value = (
        acquisition_date_from_datetime(acquisition_date)
        if isinstance(acquisition_date, str) and acquisition_date
        else acquisition_date_from_datetime(acquisition_datetime)
    )

    polarizations = normalize_polarizations(
        _entry_value(entry, "polarizations", "sar:polarizations"),
        product_id,
    )
    bbox = _entry_value(entry, "bbox")
    geometry = _entry_value(entry, "geometry")
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path_from_manifest_entry(entry, product_id, raw_dir),
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date_value,
        platform=_entry_value(entry, "platform") or platform_from_product_id(product_id),
        relative_orbit=normalize_relative_orbit(
            _entry_value(entry, "relative_orbit", "relativeOrbit", "sat:relative_orbit")
        ),
        orbit_direction=_entry_value(
            entry,
            "orbit_state",
            "orbitState",
            "orbit_direction",
            "orbitDirection",
            "sat:orbit_state",
        ),
        polarizations=polarizations,
        bbox=bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
        geometry=geometry if isinstance(geometry, dict) else None,
        scene_component=_entry_value(entry, "scene_component", "sceneComponent"),
    )


def load_selected_products(selection_manifest: Path, *, raw_dir: Path) -> list[SelectedProduct]:
    payload = json.loads(selection_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Selection manifest must contain a JSON object: {selection_manifest}")
    entries = _selected_manifest_entries(payload)
    if not entries:
        raise SystemExit(f"Selection manifest contains no selected products: {selection_manifest}")
    return [selected_product_from_manifest_entry(entry, raw_dir=raw_dir) for entry in entries]


def latest_source_path(raw_dir: Path) -> Path:
    candidates = sorted(
        [*raw_dir.rglob("*.SAFE.zip"), *raw_dir.rglob("*.zip"), *raw_dir.rglob("*.SAFE")],
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(
            f"No Sentinel-1 SAFE ZIP or SAFE directory found under {raw_dir}. Pass --zip-path."
        )
    return candidates[-1].resolve()


def selected_product_from_args(args: argparse.Namespace) -> SelectedProduct:
    source_path = (
        resolve_repo_path(args.zip_path)
        if args.zip_path
        else latest_source_path(resolve_repo_path(args.raw_dir))
    )
    product_id = product_id_from_name(args.product_id or source_path)
    acquisition_datetime = (
        args.acquisition_datetime or acquisition_datetime_from_product_id(product_id)
    )
    if not acquisition_datetime:
        raise SystemExit(
            f"Could not infer acquisition datetime from {product_id}; pass --acquisition-datetime."
        )
    acquisition_date = args.date or acquisition_date_from_datetime(acquisition_datetime)
    polarizations = normalize_polarizations(args.polarizations, product_id)
    return SelectedProduct(
        product_id=product_id,
        source_path=source_path,
        acquisition_datetime=acquisition_datetime,
        acquisition_date=acquisition_date,
        platform=args.platform or platform_from_product_id(product_id),
        relative_orbit=normalize_relative_orbit(args.relative_orbit),
        orbit_direction=args.orbit_direction,
        polarizations=polarizations,
        bbox=None,
        geometry=None,
        scene_component=args.scene_component,
    )


def find_gpt(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("SNAP_GPT"):
        candidates.append(os.environ["SNAP_GPT"])
    candidates.extend(["gpt", "/opt/snap/bin/gpt"])
    for candidate in candidates:
        resolved = shutil.which(candidate) or candidate
        path = Path(resolved)
        if path.exists() or shutil.which(str(path)):
            return path
    raise SystemExit(
        "ESA SNAP GPT executable was not found. Build/run the ingestion-sar "
        f"container or install SNAP locally, then retry. See {RUNBOOK_PATH}."
    )


def gpt_operator_available(gpt: Path, operator: str) -> bool:
    try:
        result = subprocess.run(
            [str(gpt), "-h", operator],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def graph_xml(
    *,
    source_path: Path,
    target_path: Path,
    dem_source: str,
    target_crs: str,
    pixel_spacing_meters: float,
    polarizations: list[str],
    include_border_noise: bool,
    include_speckle_filter: bool,
) -> str:
    pols = [pol for pol in polarizations if pol in {"VV", "VH"}] or ["VV"]
    pol_csv = ",".join(pols)
    sigma_bands = ",".join(f"Sigma0_{pol}" for pol in pols)
    snap_projection = snap_map_projection(target_crs)
    nodes: list[tuple[str, str, str, str | None]] = []
    nodes.append(
        (
            "Read",
            "Read",
            f"<file>{xml_escape(str(source_path))}</file>",
            None,
        )
    )
    nodes.append(
        (
            "Apply-Orbit-File",
            "Apply-Orbit-File",
            "<orbitType>Sentinel Precise (Auto Download)</orbitType>"
            "<polyDegree>3</polyDegree><continueOnFail>false</continueOnFail>",
            "Read",
        )
    )
    nodes.append(
        (
            "ThermalNoiseRemoval",
            "ThermalNoiseRemoval",
            f"<selectedPolarisations>{xml_escape(pol_csv)}</selectedPolarisations>"
            "<removeThermalNoise>true</removeThermalNoise>",
            "Apply-Orbit-File",
        )
    )
    previous = "ThermalNoiseRemoval"
    if include_border_noise:
        nodes.append(
            (
                "Remove-GRD-Border-Noise",
                "Remove-GRD-Border-Noise",
                "<borderLimit>500</borderLimit><trimThreshold>0.5</trimThreshold>",
                previous,
            )
        )
        previous = "Remove-GRD-Border-Noise"
    nodes.append(
        (
            "Calibration",
            "Calibration",
            f"<selectedPolarisations>{xml_escape(pol_csv)}</selectedPolarisations>"
            "<outputSigmaBand>true</outputSigmaBand>"
            "<outputGammaBand>false</outputGammaBand>"
            "<outputBetaBand>false</outputBetaBand>"
            "<outputImageScaleInDb>false</outputImageScaleInDb>",
            previous,
        )
    )
    previous = "Calibration"
    if include_speckle_filter:
        nodes.append(
            (
                "Speckle-Filter",
                "Speckle-Filter",
                (
                    "<filter>Lee Sigma</filter>"
                    "<filterSizeX>3</filterSizeX>"
                    "<filterSizeY>3</filterSizeY>"
                ),
                previous,
            )
        )
        previous = "Speckle-Filter"
    nodes.append(
        (
            "Terrain-Correction",
            "Terrain-Correction",
            f"<sourceBands>{xml_escape(sigma_bands)}</sourceBands>"
            f"<demName>{xml_escape(dem_source)}</demName>"
            "<externalDEMNoDataValue>0.0</externalDEMNoDataValue>"
            "<externalDEMApplyEGM>true</externalDEMApplyEGM>"
            "<demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>"
            "<imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>"
            f"<pixelSpacingInMeter>{pixel_spacing_meters}</pixelSpacingInMeter>"
            f"<mapProjection>{xml_escape(snap_projection)}</mapProjection>"
            "<nodataValueAtSea>false</nodataValueAtSea>"
            "<saveSelectedSourceBand>true</saveSelectedSourceBand>",
            previous,
        )
    )
    nodes.append(
        (
            "Write",
            "Write",
            f"<file>{xml_escape(str(target_path))}</file><formatName>GeoTIFF-BigTIFF</formatName>",
            "Terrain-Correction",
        )
    )

    rendered = [
        '<graph id="AkashaSentinel1GrdBackscatter">',
        "  <version>1.0</version>",
    ]
    for node_id, operator, parameters, source_ref in nodes:
        rendered.append(f'  <node id="{xml_escape(node_id)}">')
        rendered.append(f"    <operator>{xml_escape(operator)}</operator>")
        if source_ref:
            rendered.append(
                f'    <sources><sourceProduct refid="{xml_escape(source_ref)}"/></sources>'
            )
        rendered.append(f"    <parameters>{parameters}</parameters>")
        rendered.append("  </node>")
    rendered.append("</graph>")
    return "\n".join(rendered) + "\n"


def snap_map_projection(target_crs: str) -> str:
    """Return a SNAP Terrain-Correction mapProjection value.

    SNAP accepts WKT reliably; bare EPSG strings can produce operator
    initialization failures in some versions. Keep a safe fallback so help/tests
    do not require pyproj on import-only paths.
    """
    try:
        from pyproj import CRS

        return CRS.from_user_input(target_crs).to_wkt(version="WKT1_GDAL")
    except Exception:  # noqa: BLE001 - fall back to the operator input value
        return target_crs


def _safe_xml_float(node: ET.Element, tag: str) -> float:
    value = node.findtext(tag)
    if value is None:
        raise SystemExit(f"Missing {tag} in Sentinel-1 SAFE annotation metadata")
    return float(value)


def _safe_xml_int(node: ET.Element, tag: str) -> int:
    return int(round(_safe_xml_float(node, tag)))


def measurement_path_for_pol(safe_dir: Path, pol: str) -> Path:
    matches = sorted((safe_dir / "measurement").glob(f"*{pol.lower()}*.tif*"))
    if not matches:
        raise SystemExit(f"COG_SAFE fallback could not find {pol} measurement TIFF in {safe_dir}")
    return matches[0]


def annotation_path_for_pol(safe_dir: Path, pol: str) -> Path:
    matches = sorted((safe_dir / "annotation").glob(f"*{pol.lower()}*.xml"))
    matches = [
        path
        for path in matches
        if "calibration" not in path.parts and "rfi" not in path.parts
    ]
    if not matches:
        raise SystemExit(f"COG_SAFE fallback could not find {pol} annotation XML in {safe_dir}")
    return matches[0]


def calibration_path_for_pol(safe_dir: Path, pol: str) -> Path:
    matches = sorted(
        (safe_dir / "annotation" / "calibration").glob(f"calibration-*{pol.lower()}*.xml")
    )
    if not matches:
        raise SystemExit(f"COG_SAFE fallback could not find {pol} calibration XML in {safe_dir}")
    return matches[0]


def transform_from_annotation_gcps(deps: dict[str, Any], annotation_xml: Path) -> Any:
    from rasterio.control import GroundControlPoint
    from rasterio.transform import from_gcps

    doc = ET.parse(annotation_xml).getroot()
    gcps = []
    for point in doc.findall(".//geolocationGridPoint"):
        gcps.append(
            GroundControlPoint(
                row=_safe_xml_float(point, "line"),
                col=_safe_xml_float(point, "pixel"),
                x=_safe_xml_float(point, "longitude"),
                y=_safe_xml_float(point, "latitude"),
                z=_safe_xml_float(point, "height"),
            )
        )
    if len(gcps) < 3:
        raise SystemExit(f"COG_SAFE fallback found too few geolocation GCPs in {annotation_xml}")
    return from_gcps(gcps)


def load_sigma_calibration(calibration_xml: Path) -> dict[str, Any]:
    doc = ET.parse(calibration_xml).getroot()
    vectors = doc.findall(".//calibrationVector")
    if not vectors:
        raise SystemExit(f"COG_SAFE fallback found no calibration vectors in {calibration_xml}")
    lines: list[int] = []
    pixels: list[float] | None = None
    sigma_rows: list[list[float]] = []
    for vector in vectors:
        lines.append(_safe_xml_int(vector, "line"))
        vector_pixels = [float(value) for value in (vector.findtext("pixel") or "").split()]
        sigma = [float(value) for value in (vector.findtext("sigmaNought") or "").split()]
        if not vector_pixels or not sigma or len(vector_pixels) != len(sigma):
            raise SystemExit(f"Invalid sigma calibration vector in {calibration_xml}")
        if pixels is None:
            pixels = vector_pixels
        sigma_rows.append(sigma)
    deps_np = __import__("numpy")
    return {
        "lines": deps_np.asarray(lines, dtype="float64"),
        "pixels": deps_np.asarray(pixels, dtype="float64"),
        "sigma": deps_np.asarray(sigma_rows, dtype="float64"),
    }


def sigma_lut_for_window(deps: dict[str, Any], calibration: dict[str, Any], window: Any) -> Any:
    np = deps["np"]
    row_start = int(window.row_off)
    row_stop = row_start + int(window.height)
    col_start = int(window.col_off)
    col_stop = col_start + int(window.width)
    rows = np.arange(row_start, row_stop, dtype="float64")
    cols = np.arange(col_start, col_stop, dtype="float64")
    line_positions = calibration["lines"]
    pixel_positions = calibration["pixels"]
    sigma_vectors = calibration["sigma"]

    lut = np.empty((len(rows), len(cols)), dtype="float32")
    for row_index, row in enumerate(rows):
        upper = int(np.searchsorted(line_positions, row, side="right"))
        lower = max(0, upper - 1)
        upper = min(upper, len(line_positions) - 1)
        if upper == lower or line_positions[upper] == line_positions[lower]:
            sigma_line = sigma_vectors[lower]
        else:
            weight = (row - line_positions[lower]) / (line_positions[upper] - line_positions[lower])
            sigma_line = sigma_vectors[lower] * (1.0 - weight) + sigma_vectors[upper] * weight
        lut[row_index, :] = np.interp(cols, pixel_positions, sigma_line).astype("float32")
    return lut


def write_cog_safe_display_db_intermediate(
    *,
    deps: dict[str, Any],
    product: SelectedProduct,
    output_path: Path,
    overwrite: bool,
) -> list[str]:
    if output_path.exists() and not overwrite:
        print(f"keep existing COG_SAFE dB intermediate {output_path}")
        with deps["rasterio"].open(output_path) as dataset:
            return [str(desc).replace("_dB", "") for desc in dataset.descriptions if desc]

    safe_dir = product.source_path
    if not safe_dir.is_dir() or safe_dir.suffix != ".SAFE":
        raise SystemExit(
            "COG_SAFE display fallback requires an extracted .SAFE directory. "
            "Extract the downloaded SAFE ZIP first or run the SNAP path."
        )

    np = deps["np"]
    rasterio = deps["rasterio"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    display_pols = [pol for pol in product.polarizations if pol in {"VV", "VH"}]
    if "VV" not in display_pols:
        raise SystemExit("COG_SAFE display fallback requires VV polarization.")
    display_pols = [pol for pol in ["VV", "VH"] if pol in display_pols]

    measurement_paths = {pol: measurement_path_for_pol(safe_dir, pol) for pol in display_pols}
    calibration = {
        pol: load_sigma_calibration(calibration_path_for_pol(safe_dir, pol))
        for pol in display_pols
    }
    transform = transform_from_annotation_gcps(deps, annotation_path_for_pol(safe_dir, "VV"))

    with rasterio.open(measurement_paths["VV"]) as src0:
        profile = src0.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(display_pols),
            dtype="float32",
            nodata=DEFAULT_NODATA,
            crs="EPSG:4326",
            transform=transform,
            tiled=True,
            blockxsize=COG_BLOCKSIZE,
            blockysize=COG_BLOCKSIZE,
            compress="DEFLATE",
            predictor=3,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            for dst_index, pol in enumerate(display_pols, start=1):
                with rasterio.open(measurement_paths[pol]) as src:
                    for _, window in src.block_windows(1):
                        dn = src.read(1, window=window, masked=True).astype("float32")
                        sigma_lut = sigma_lut_for_window(deps, calibration[pol], window)
                        values = np.asarray(dn.filled(0), dtype="float32")
                        valid = values > 0
                        sigma0 = np.zeros(values.shape, dtype="float32")
                        sigma0[valid] = (values[valid] ** 2) / np.maximum(
                            sigma_lut[valid] ** 2,
                            DB_EPSILON,
                        )
                        db = np.full(values.shape, DEFAULT_NODATA, dtype="float32")
                        db[valid] = (
                            10.0 * np.log10(np.maximum(sigma0[valid], DB_EPSILON))
                        ).astype("float32")
                        dst.write(db, dst_index, window=window)
                dst.set_band_description(dst_index, f"{pol}_dB")
                dst.update_tags(
                    dst_index,
                    name=f"{pol}_dB",
                    source="CDSE COG_SAFE measurement + SAFE sigmaNought calibration LUT",
                    formula="10*log10(max(DN^2/sigmaNought^2,1e-8))",
                )
            dst.update_tags(
                AKASHA_PROCESSING_GRAPH_VERSION=COG_SAFE_FALLBACK_GRAPH_VERSION,
                AKASHA_BACKSCATTER_SCALE="dB",
                AKASHA_NODATA=str(DEFAULT_NODATA),
                AKASHA_PROCESSING_WARNING=(
                    "Display fallback georeferenced from SAFE geolocation grid; "
                    "SNAP terrain-corrected output remains preferred for production."
                ),
                AREA_OR_POINT="Area",
            )
    return display_pols


def resolve_border_noise_mode(args: argparse.Namespace, gpt: Path) -> bool:
    if args.border_noise == "off":
        return False
    available = gpt_operator_available(gpt, "Remove-GRD-Border-Noise")
    if args.border_noise == "on" and not available:
        raise SystemExit(
            "SNAP operator Remove-GRD-Border-Noise is unavailable in this SNAP installation. "
            f"Use --border-noise off or update SNAP. See {RUNBOOK_PATH}."
        )
    return available


def run_gpt(
    *,
    gpt: Path,
    graph_path: Path,
    snap_user_dir: Path | None,
    cache_size: str,
    parallelism: int,
) -> subprocess.CompletedProcess[str]:
    command = [str(gpt)]
    if snap_user_dir:
        command.append(f"-Dsnap.userdir={snap_user_dir}")
    command.extend([str(graph_path), "-e", "-c", cache_size, "-q", str(parallelism)])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def tail_text(value: str, max_chars: int = 4000) -> str:
    return value[-max_chars:] if len(value) > max_chars else value


def execute_snap_graph(
    *,
    paths: PreparedPaths,
    args: argparse.Namespace,
    gpt: Path,
    include_border_noise: bool,
) -> str:
    if paths.snap_linear_tif.exists() and not args.overwrite:
        print(f"keep existing SNAP output {paths.snap_linear_tif}")
        return args.dem_source

    paths.snap_linear_tif.parent.mkdir(parents=True, exist_ok=True)
    dem_candidates = [args.dem_source]
    if args.fallback_dem_source and args.fallback_dem_source not in dem_candidates:
        dem_candidates.append(args.fallback_dem_source)

    last_result: subprocess.CompletedProcess[str] | None = None
    last_graph: Path | None = None
    for dem_source in dem_candidates:
        if paths.snap_linear_tif.exists():
            paths.snap_linear_tif.unlink()
        dem_slug = re.sub(r"[^A-Za-z0-9]+", "_", dem_source).strip("_").lower()
        graph_path = paths.output_dir / "_tmp" / f"snap_{dem_slug}.xml"
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(
            graph_xml(
                source_path=paths.product.source_path,
                target_path=paths.snap_linear_tif,
                dem_source=dem_source,
                target_crs=args.target_crs,
                pixel_spacing_meters=args.pixel_spacing_meters,
                polarizations=paths.product.polarizations,
                include_border_noise=include_border_noise,
                include_speckle_filter=args.speckle_filter,
            ),
            encoding="utf-8",
        )
        last_graph = graph_path
        print(f"SNAP GPT graph ({dem_source}): {graph_path}")
        result = run_gpt(
            gpt=gpt,
            graph_path=graph_path,
            snap_user_dir=resolve_repo_path(args.snap_user_dir) if args.snap_user_dir else None,
            cache_size=args.snap_cache_size,
            parallelism=args.snap_parallelism,
        )
        last_result = result
        if result.returncode == 0 and paths.snap_linear_tif.exists():
            return dem_source
        if dem_source != dem_candidates[-1]:
            print(f"SNAP GPT failed with DEM {dem_source}; trying fallback.")

    stdout = tail_text(last_result.stdout if last_result else "")
    stderr = tail_text(last_result.stderr if last_result else "")
    raise SystemExit(
        "SNAP GPT preprocessing failed. Review SNAP input availability, DEM/orbit cache, "
        f"and container resources. See {RUNBOOK_PATH}.\n"
        f"Last graph: {last_graph}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    )


def band_polarization(dataset: Any, band_index: int, fallback: list[str]) -> str | None:
    candidates: list[str] = []
    description = dataset.descriptions[band_index - 1] if dataset.descriptions else None
    if description:
        candidates.append(description)
    tags = dataset.tags(band_index)
    candidates.extend(str(value) for value in tags.values())
    for candidate in candidates:
        upper = candidate.upper()
        if "VV" in upper:
            return "VV"
        if "VH" in upper:
            return "VH"
    fallback_vv_vh = [pol for pol in fallback if pol in {"VV", "VH"}]
    if band_index <= len(fallback_vv_vh):
        return fallback_vv_vh[band_index - 1]
    return None


def convert_linear_sigma0_to_db(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    polarizations: list[str],
    overwrite: bool,
) -> list[str]:
    if output_path.exists() and not overwrite:
        print(f"keep existing dB intermediate {output_path}")
        with deps["rasterio"].open(output_path) as dataset:
            return [str(desc).replace("_dB", "") for desc in dataset.descriptions if desc]

    np = deps["np"]
    rasterio = deps["rasterio"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with rasterio.open(source_path) as src:
        band_map: list[tuple[int, str]] = []
        for band_index in range(1, src.count + 1):
            pol = band_polarization(src, band_index, polarizations)
            if pol in {"VV", "VH"} and pol not in [existing for _, existing in band_map]:
                band_map.append((band_index, pol))
        band_map.sort(key=lambda item: {"VV": 0, "VH": 1}[item[1]])
        if not band_map or band_map[0][1] != "VV":
            raise SystemExit(
                "SNAP output did not contain a VV sigma0 band. Sentinel-1 GRD "
                f"VV is required for Akasha VV_GRAYSCALE. See {RUNBOOK_PATH}."
            )

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(band_map),
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
            for dst_index, (src_index, pol) in enumerate(band_map, start=1):
                linear = src.read(src_index, masked=True).astype("float32")
                data = np.full(linear.shape, DEFAULT_NODATA, dtype="float32")
                values = np.asarray(linear.filled(np.nan), dtype="float32")
                valid = np.isfinite(values)
                data[valid] = (
                    10.0 * np.log10(np.maximum(values[valid], DB_EPSILON))
                ).astype("float32")
                dst.write(data, dst_index)
                dst.set_band_description(dst_index, f"{pol}_dB")
                dst.update_tags(
                    dst_index,
                    name=f"{pol}_dB",
                    source_band=src.descriptions[src_index - 1] or f"band_{src_index}",
                    formula=f"10*log10(max(sigma0,{DB_EPSILON}))",
                )
            dst.update_tags(
                AKASHA_PROCESSING_GRAPH_VERSION=PROCESSING_GRAPH_VERSION,
                AKASHA_BACKSCATTER_SCALE="dB",
                AKASHA_NODATA=str(DEFAULT_NODATA),
                AREA_OR_POINT="Area",
            )
    return [pol for _, pol in band_map]


def translate_to_cog(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    overwrite: bool,
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
        dataset.crs,
        "EPSG:4326",
        *dataset.bounds,
        densify_pts=21,
    )
    return [float(west), float(south), float(east), float(north)]


def raster_summary(deps: dict[str, Any], path: Path) -> dict[str, Any]:
    with deps["rasterio"].open(path) as dataset:
        transform = [float(value) for value in dataset.transform]
        summary = {
            "path": path.as_posix(),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "transform": transform,
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


def write_manifest(
    *,
    deps: dict[str, Any],
    paths: PreparedPaths,
    dem_source: str,
    actual_polarizations: list[str],
    include_border_noise: bool,
    args: argparse.Namespace,
) -> None:
    summary = raster_summary(deps, paths.backscatter_cog)
    vv_rescale = parse_rescale(args.vv_rescale, (-25.0, 0.0))
    vh_rescale = parse_rescale(args.vh_rescale, (-30.0, -5.0))
    if args.display_fallback_from_cog_safe:
        graph_version = COG_SAFE_FALLBACK_GRAPH_VERSION
        engine = "CDSE COG_SAFE display fallback"
        processing_steps = [
            "Read CDSE COG_SAFE VV/VH measurement GeoTIFFs",
            "Apply SAFE sigmaNought calibration LUT to DN values",
            "Approximate georeferencing from SAFE geolocation grid",
            "10*log10(max(sigma0, 1e-8)) dB conversion",
            "COG creation with average overviews",
        ]
    else:
        graph_version = PROCESSING_GRAPH_VERSION
        engine = "ESA SNAP GPT"
        processing_steps = [
            "Apply-Orbit-File",
            "ThermalNoiseRemoval",
        ]
        if include_border_noise:
            processing_steps.append("Remove-GRD-Border-Noise")
        processing_steps.append("Calibration sigma0 linear")
        if args.speckle_filter:
            processing_steps.append("Speckle-Filter")
        processing_steps.extend(
            [
                "Terrain-Correction",
                "10*log10(max(sigma0, 1e-8)) dB conversion",
                "COG creation with average overviews",
            ]
        )
    payload: dict[str, Any] = {
        "source_id": "sentinel-1-grd",
        "product_id": paths.product.product_id,
        "platform": paths.product.platform,
        "acquisition_datetime": paths.product.acquisition_datetime,
        "acquisition_date": paths.product.acquisition_date,
        "relative_orbit": paths.product.relative_orbit,
        "sat:relative_orbit": paths.product.relative_orbit,
        "orbit_state": paths.product.orbit_direction,
        "sat:orbit_state": paths.product.orbit_direction,
        "orbit_direction": paths.product.orbit_direction,
        "polarizations": actual_polarizations,
        "source_zip": paths.product.source_path.as_posix(),
        "processing_graph_version": graph_version,
        "processing": {
            "engine": engine,
            "steps": processing_steps,
            "target_crs": args.target_crs,
            "pixel_spacing_meters": args.pixel_spacing_meters,
            "dem_source": dem_source,
            "fallback_dem_source": args.fallback_dem_source,
            "speckle_filter": bool(args.speckle_filter),
            "border_noise_removal": bool(include_border_noise),
            "nodata": DEFAULT_NODATA,
            "db_epsilon": DB_EPSILON,
        },
        "dem_source": dem_source,
        "output_cog_path": paths.backscatter_cog.as_posix(),
        "crs": summary.get("crs"),
        "transform": summary.get("transform"),
        "dimensions": summary.get("dimensions"),
        "nodata": summary.get("nodata"),
        "display_rescale_defaults": {
            "VV_GRAYSCALE": vv_rescale,
            "VH_GRAYSCALE": vh_rescale,
        },
        "outputs": {"backscatter": summary},
    }
    if args.display_fallback_from_cog_safe:
        payload["warnings"] = [
            "Display fallback uses CDSE COG_SAFE geolocation-grid approximation; "
            "validated SNAP terrain correction remains preferred for production."
        ]
    if summary.get("wgs84_bbox"):
        payload["bbox"] = summary["wgs84_bbox"]
        payload["geometry"] = summary["wgs84_geometry"]
    elif paths.product.bbox:
        payload["bbox"] = paths.product.bbox
        payload["geometry"] = paths.product.geometry or geometry_from_bbox(paths.product.bbox)

    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {paths.manifest}")


def prepared_paths(product: SelectedProduct, args: argparse.Namespace) -> PreparedPaths:
    output_root = resolve_repo_path(args.output_root)
    output_dir = (
        output_root
        / product.acquisition_date
        / relative_orbit_folder(product.relative_orbit)
        / scene_component(product)
    )
    temp_dir = output_dir / "_tmp"
    return PreparedPaths(
        product=product,
        output_dir=output_dir,
        snap_linear_tif=temp_dir / "snap_sigma0_linear_tc.tif",
        db_intermediate_tif=temp_dir / "backscatter_db_intermediate.tif",
        backscatter_cog=output_dir / "backscatter.tif",
        manifest=output_dir / "prepare_manifest.json",
    )


def ensure_source_exists(path: Path) -> None:
    if not path.exists():
        raise SystemExit(
            f"Source SAFE ZIP/directory not found: {path}. Download the native Sentinel-1 "
            f"SAFE ZIP first. See {RUNBOOK_PATH}."
        )


def prepare_one(
    *,
    product: SelectedProduct,
    args: argparse.Namespace,
    deps: dict[str, Any],
    gpt: Path,
    include_border_noise: bool,
) -> PreparedPaths:
    if "VV" not in product.polarizations:
        raise SystemExit(f"Product {product.product_id} does not advertise VV polarization.")
    ensure_source_exists(product.source_path)
    paths = prepared_paths(product, args)
    print(f"source: {product.source_path}")
    print(f"output: {paths.output_dir}")

    if args.display_fallback_from_cog_safe:
        actual_polarizations = write_cog_safe_display_db_intermediate(
            deps=deps,
            product=product,
            output_path=paths.db_intermediate_tif,
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
            dem_source="CDSE COG_SAFE geolocation grid",
            actual_polarizations=actual_polarizations,
            include_border_noise=False,
            args=args,
        )
        return paths

    dem_source = execute_snap_graph(
        paths=paths,
        args=args,
        gpt=gpt,
        include_border_noise=include_border_noise,
    )
    actual_polarizations = convert_linear_sigma0_to_db(
        deps=deps,
        source_path=paths.snap_linear_tif,
        output_path=paths.db_intermediate_tif,
        polarizations=product.polarizations,
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
        dem_source=dem_source,
        actual_polarizations=actual_polarizations,
        include_border_noise=include_border_noise,
        args=args,
    )
    if not args.keep_intermediate and (paths.output_dir / "_tmp").exists():
        shutil.rmtree(paths.output_dir / "_tmp")
        print(f"removed temporary files: {paths.output_dir / '_tmp'}")
    return paths


def write_batch_manifest(
    *,
    output_root: Path,
    selection_manifest: Path,
    prepared: list[PreparedPaths],
) -> Path:
    batch_manifest = output_root / "batch_prepare_manifest.json"
    payload = {
        "selection_manifest": selection_manifest.as_posix(),
        "product_count": len(prepared),
        "processing_graph_version": PROCESSING_GRAPH_VERSION,
        "products": [
            {
                "product_id": item.product.product_id,
                "platform": item.product.platform,
                "acquisition_datetime": item.product.acquisition_datetime,
                "acquisition_date": item.product.acquisition_date,
                "relative_orbit": item.product.relative_orbit,
                "sat:relative_orbit": item.product.relative_orbit,
                "orbit_state": item.product.orbit_direction,
                "sat:orbit_state": item.product.orbit_direction,
                "orbit_direction": item.product.orbit_direction,
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
        "--zip-path",
        help="Path to native Sentinel-1 .SAFE.zip or extracted .SAFE directory",
    )
    parser.add_argument(
        "--selection-manifest",
        help="Downloader selection manifest for batch preparation",
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT.relative_to(REPO_ROOT)))
    parser.add_argument("--product-id", help="Override product id for single-product mode")
    parser.add_argument("--date", help="Output acquisition date folder, e.g. 2026-04-27")
    parser.add_argument(
        "--acquisition-datetime",
        help="Acquisition datetime, e.g. 2026-04-27T00:00:00Z",
    )
    parser.add_argument("--platform", help="Platform, e.g. sentinel-1a")
    parser.add_argument("--relative-orbit", help="Relative orbit number for output path/manifest")
    parser.add_argument("--orbit-direction", help="Orbit direction/state, e.g. ascending")
    parser.add_argument(
        "--polarizations",
        help="Comma-separated polarizations; default inferred from product id",
    )
    parser.add_argument(
        "--scene-component",
        help="Collision-safe output component; default product id",
    )
    parser.add_argument(
        "--gpt",
        help="Path to ESA SNAP GPT executable; defaults to SNAP_GPT or PATH",
    )
    parser.add_argument(
        "--snap-user-dir",
        default=os.environ.get("SNAP_USER_DIR") or os.environ.get("SNAP_CACHE_DIR"),
    )
    parser.add_argument("--snap-cache-size", default=os.environ.get("SNAP_CACHE_SIZE", "8G"))
    parser.add_argument(
        "--snap-parallelism",
        type=int,
        default=int(os.environ.get("SNAP_PARALLELISM", "4")),
    )
    parser.add_argument(
        "--target-crs",
        default=os.environ.get("AKASHA_S1_TARGET_CRS", DEFAULT_TARGET_CRS),
    )
    parser.add_argument(
        "--pixel-spacing-meters",
        type=float,
        default=float(
            os.environ.get("AKASHA_S1_PIXEL_SPACING_METERS", DEFAULT_PIXEL_SPACING_METERS)
        ),
    )
    parser.add_argument(
        "--dem-source",
        default=os.environ.get("AKASHA_S1_DEM_SOURCE", DEFAULT_DEM_SOURCE),
    )
    parser.add_argument(
        "--fallback-dem-source",
        default=os.environ.get("AKASHA_S1_FALLBACK_DEM_SOURCE", DEFAULT_FALLBACK_DEM_SOURCE),
    )
    parser.add_argument(
        "--border-noise",
        choices=("auto", "on", "off"),
        default=os.environ.get("AKASHA_S1_BORDER_NOISE", "auto"),
        help="Use Remove-GRD-Border-Noise when available by default.",
    )
    parser.add_argument(
        "--speckle-filter",
        action="store_true",
        help="Enable SNAP Speckle-Filter; disabled by default",
    )
    parser.add_argument(
        "--display-fallback-from-cog-safe",
        action="store_true",
        help=(
            "Create a display-only calibrated dB COG directly from extracted CDSE COG_SAFE "
            "measurement TIFFs when SNAP terrain correction is unavailable."
        ),
    )
    parser.add_argument("--vv-rescale", default=os.environ.get("AKASHA_S1_VV_RESCALE", "-25,5"))
    parser.add_argument("--vh-rescale", default=os.environ.get("AKASHA_S1_VH_RESCALE", "-30,-5"))
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep SNAP and dB intermediate GeoTIFFs",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Skip rio-cogeo validation")
    args = parser.parse_args(argv)

    if args.selection_manifest and args.zip_path:
        raise SystemExit("--zip-path cannot be combined with --selection-manifest")
    if args.selection_manifest and args.date:
        raise SystemExit("--date cannot be combined with --selection-manifest")

    gpt = find_gpt(args.gpt)
    include_border_noise = resolve_border_noise_mode(args, gpt)
    deps = require_raster_deps()
    output_root = resolve_repo_path(args.output_root)

    if args.selection_manifest:
        selection_manifest = resolve_repo_path(args.selection_manifest)
        selected_products = load_selected_products(
            selection_manifest,
            raw_dir=resolve_repo_path(args.raw_dir),
        )
        prepared = [
            prepare_one(
                product=product,
                args=args,
                deps=deps,
                gpt=gpt,
                include_border_noise=include_border_noise,
            )
            for product in selected_products
        ]
        write_batch_manifest(
            output_root=output_root,
            selection_manifest=selection_manifest,
            prepared=prepared,
        )
    else:
        product = selected_product_from_args(args)
        prepare_one(
            product=product,
            args=args,
            deps=deps,
            gpt=gpt,
            include_border_noise=include_border_noise,
        )

    print("Sentinel-1 GRD COG preparation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
