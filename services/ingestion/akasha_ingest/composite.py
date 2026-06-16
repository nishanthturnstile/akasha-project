"""ResourceSat LISS-3 composite helpers.

This module keeps the Phase 2b core deterministic and testable. Raster IO and
reprojection are wired in later; the pixel-selection rules here operate on
already aligned analytic and mask arrays.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

RESOURCE_SAT_VALID_MASK_CLASSES = frozenset({1, 4})
RESOURCE_SAT_EXCLUDED_MASK_CLASSES = frozenset({0, 2, 3})
SOURCE_ID = "resourcesat-2a-liss3-boa"
BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS3_BOA"
AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
AWIFS_BHOONIDHI_COLLECTION = "ResourceSat-2A_AWIFS_BOA"
SOURCE_PROFILES = {
    SOURCE_ID: {
        "collection": BHOONIDHI_COLLECTION,
        "label": "ResourceSat LISS-3",
        "resolution": 24.0,
        "mask_method": (
            "Akasha threshold mask v1 (no native quality layer found in validated "
            "LISS-3 BOA sample; provisional)."
        ),
    },
    AWIFS_SOURCE_ID: {
        "collection": AWIFS_BHOONIDHI_COLLECTION,
        "label": "ResourceSat AWiFS",
        "resolution": 56.0,
        "mask_method": (
            "Akasha threshold mask v1 for ResourceSat-2A AWiFS BOA "
            "(pending AWiFS-specific native quality-layer validation; provisional)."
        ),
    },
}
SOURCE_ALIASES = {
    SOURCE_ID: SOURCE_ID,
    BHOONIDHI_COLLECTION: SOURCE_ID,
    AWIFS_SOURCE_ID: AWIFS_SOURCE_ID,
    AWIFS_BHOONIDHI_COLLECTION: AWIFS_SOURCE_ID,
}
COG_BLOCKSIZE = 512
NODATA_DN = 0
MASK_METHOD = (
    "Akasha threshold mask v1 (no native quality layer found in validated "
    "LISS-3 BOA sample; provisional)."
)
MASK_CLASSES = [
    {"value": 0, "name": "nodata", "description": "No data / all-band gap", "nodata": True},
    {"value": 1, "name": "valid", "description": "Valid clear land or water pixel"},
    {"value": 2, "name": "cloud", "description": "Akasha threshold-derived cloud"},
    {"value": 3, "name": "shadow", "description": "Akasha threshold-derived shadow"},
    {"value": 4, "name": "water", "description": "Akasha threshold-derived water"},
]
ANALYTIC_BAND_ORDER = ["BAND2", "BAND3", "BAND4", "BAND5"]
BAND_ROLE_MAPPING = {
    "GREEN": "BAND2",
    "RED": "BAND3",
    "NIR": "BAND4",
    "SWIR1": "BAND5",
}
AOI_COMPOSITE_GRID_CRS_KEYS = (
    "compositeGridCrs",
    "composite_grid_crs",
    "akasha:composite_grid_crs",
)


def source_id_from_manifest(manifest: dict[str, Any]) -> str:
    raw = str(manifest.get("source_id") or manifest.get("collection") or SOURCE_ID)
    return SOURCE_ALIASES.get(raw, raw)


def source_profile(source_id: str) -> dict[str, Any]:
    try:
        return SOURCE_PROFILES[source_id]
    except KeyError as exc:
        supported = ", ".join(sorted(SOURCE_PROFILES))
        raise ValueError(
            f"unsupported ResourceSat BOA source '{source_id}'. " f"Supported: {supported}"
        ) from exc


def default_resolution(source_id: str) -> float:
    return float(source_profile(source_id)["resolution"])


def mask_method_for_source(source_id: str) -> str:
    method = source_profile(source_id).get("mask_method")
    return str(method or MASK_METHOD)


def aoi_composite_grid_crs(aoi: dict[str, Any] | None, default: str = "EPSG:32643") -> str:
    if not aoi:
        return default
    containers = [aoi]
    props = aoi.get("properties")
    if isinstance(props, dict):
        containers.insert(0, props)
    for container in containers:
        for key in AOI_COMPOSITE_GRID_CRS_KEYS:
            value = container.get(key)
            if value:
                return str(value)
    return default


@dataclass(frozen=True)
class CompositeGrid:
    crs: str
    bounds: tuple[float, float, float, float]
    resolution: float
    width: int
    height: int
    transform: tuple[float, float, float, float, float, float, float, float, float]

    @classmethod
    def from_projected_bounds(
        cls,
        bounds: tuple[float, float, float, float] | list[float],
        *,
        crs: str = "EPSG:32643",
        resolution: float = 24.0,
        padding_pixels: int = 0,
    ) -> CompositeGrid:
        if len(bounds) != 4:
            raise ValueError("grid bounds must contain west, south, east, north")
        west, south, east, north = [float(value) for value in bounds]
        if west >= east or south >= north:
            raise ValueError(f"invalid projected bounds: {bounds}")
        if resolution <= 0:
            raise ValueError("grid resolution must be positive")
        pad = max(0, int(padding_pixels)) * resolution
        west = math.floor((west - pad) / resolution) * resolution
        south = math.floor((south - pad) / resolution) * resolution
        east = math.ceil((east + pad) / resolution) * resolution
        north = math.ceil((north + pad) / resolution) * resolution
        width = int(round((east - west) / resolution))
        height = int(round((north - south) / resolution))
        return cls(
            crs=crs,
            bounds=(west, south, east, north),
            resolution=resolution,
            width=width,
            height=height,
            transform=(resolution, 0.0, west, 0.0, -resolution, north, 0.0, 0.0, 1.0),
        )


@dataclass(frozen=True)
class AlignedScene:
    scene_id: str
    acquisition_datetime: str
    analytic: Any
    mask: Any

    @property
    def timestamp(self) -> datetime:
        value = self.acquisition_datetime
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)


@dataclass(frozen=True)
class CompositeBuildResult:
    output_dir: Path
    analytic_cog: Path
    mask_cog: Path
    manifest: Path
    metrics: dict[str, Any]


@dataclass(frozen=True)
class CompositeVerifyResult:
    ok: bool
    detail: str
    checks: list[str]
    problems: list[str]


def require_raster_deps() -> dict[str, Any]:
    try:
        import rasterio
        from affine import Affine
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
        "rasterio": rasterio,
        "Affine": Affine,
        "Resampling": Resampling,
        "reproject": reproject,
        "transform_bounds": transform_bounds,
        "cog_translate": cog_translate,
        "cog_validate": cog_validate,
        "cog_profiles": cog_profiles,
    }


def _as_scene_arrays(scene: AlignedScene) -> tuple[np.ndarray, np.ndarray]:
    analytic = np.asarray(scene.analytic)
    mask = np.asarray(scene.mask)
    if analytic.ndim != 3:
        raise ValueError(f"{scene.scene_id}: analytic array must be band,height,width")
    if analytic.shape[0] != 4:
        raise ValueError(f"{scene.scene_id}: ResourceSat analytic array must have 4 bands")
    if mask.ndim != 2:
        raise ValueError(f"{scene.scene_id}: mask array must be height,width")
    if analytic.shape[1:] != mask.shape:
        raise ValueError(
            f"{scene.scene_id}: analytic/mask shape mismatch "
            f"{analytic.shape[1:]} != {mask.shape}"
        )
    return analytic, mask


def _valid_pixels(mask: np.ndarray) -> np.ndarray:
    return np.isin(mask, list(RESOURCE_SAT_VALID_MASK_CLASSES))


def build_best_available_composite(scenes: list[AlignedScene]) -> dict[str, Any]:
    """Merge aligned scenes using Phase 2b's most-recent valid-pixel rule."""
    if not scenes:
        raise ValueError("at least one aligned scene is required")

    ordered = sorted(scenes, key=lambda scene: scene.timestamp)
    first_analytic, first_mask = _as_scene_arrays(ordered[0])
    output_analytic = np.zeros_like(first_analytic)
    output_mask = np.zeros_like(first_mask, dtype=np.uint8)
    output_scene_index = np.full(first_mask.shape, -1, dtype=np.int16)
    has_any = np.zeros(first_mask.shape, dtype=bool)
    has_valid = np.zeros(first_mask.shape, dtype=bool)

    for index, scene in enumerate(ordered):
        analytic, mask = _as_scene_arrays(scene)
        if analytic.shape != first_analytic.shape:
            raise ValueError(f"{scene.scene_id}: shape does not match first scene")
        valid = _valid_pixels(mask)
        any_coverage = mask != 0

        fallback_take = any_coverage & ~has_any
        valid_take = valid
        take = fallback_take | valid_take
        if not np.any(take):
            continue

        output_analytic[:, take] = analytic[:, take]
        output_scene_index[take] = index
        output_mask[fallback_take & ~valid] = mask[fallback_take & ~valid]
        output_mask[valid_take] = mask[valid_take]
        has_any |= any_coverage
        has_valid |= valid

    output_mask[~has_any] = 0
    invalid_output = has_any & ~has_valid
    output_mask[invalid_output] = np.where(
        output_mask[invalid_output] == 0,
        2,
        output_mask[invalid_output],
    )

    total_pixels = output_mask.size
    coverage_pixels = int(np.count_nonzero(has_any))
    usable_pixels = int(np.count_nonzero(_valid_pixels(output_mask)))
    cloud_pixels = int(np.count_nonzero(output_mask == 2))
    metrics = {
        "coverage_percent": round(coverage_pixels * 100.0 / total_pixels, 4),
        "usable_pixel_percent": round(usable_pixels * 100.0 / total_pixels, 4),
        "cloud_masked_percent": round(cloud_pixels * 100.0 / total_pixels, 4),
        "contributing_scenes": [
            {"id": scene.scene_id, "datetime": scene.acquisition_datetime} for scene in ordered
        ],
    }
    return {
        "analytic": output_analytic,
        "mask": output_mask,
        "source_scene_index": output_scene_index,
        "metrics": metrics,
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_asset_path(manifest_path: Path, manifest: dict[str, Any], asset: str) -> Path:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    value = outputs.get(asset)
    if isinstance(value, dict):
        value = value.get("path") or value.get("href")
    if not value:
        value = manifest.get(f"{asset}_path") or manifest.get(f"{asset}Path")
    path = Path(str(value)) if value else manifest_path.parent / f"{asset}.tif"
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def _manifest_asset_path_from_outputs(
    manifest_path: Path,
    manifest: dict[str, Any],
    asset: str,
) -> Path:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    value = outputs.get(asset)
    if isinstance(value, dict):
        value = value.get("path") or value.get("href")
    path = Path(str(value)) if value else manifest_path.parent / f"{asset}.tif"
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def _manifest_datetime(manifest: dict[str, Any]) -> str:
    value = (
        manifest.get("acquisition_datetime")
        or manifest.get("acquisitionDateTime")
        or manifest.get("datetime")
    )
    if not value:
        raise ValueError("scene manifest is missing acquisition datetime")
    text = str(value)
    return text if "T" in text else f"{text}T00:00:00Z"


def _manifest_aoi_id(manifest: dict[str, Any]) -> str | None:
    props = manifest.get("properties") if isinstance(manifest.get("properties"), dict) else {}
    value = (
        manifest.get("aoi_id")
        or manifest.get("aoiId")
        or manifest.get("akasha:aoi_id")
        or props.get("akasha:aoi_id")
        or props.get("aoi_id")
        or props.get("aoiId")
    )
    return str(value) if value else None


def scene_manifest_paths_for_window(
    manifest_paths: list[Path],
    *,
    window_start: str,
    window_end: str,
    source_id: str = SOURCE_ID,
    aoi_id: str | None = None,
) -> list[Path]:
    source_id = SOURCE_ALIASES.get(source_id, source_id)
    selected: list[Path] = []
    for manifest_path in manifest_paths:
        manifest = _read_manifest(manifest_path)
        if bool(
            manifest.get("composite")
            or manifest.get("akasha:composite")
            or (
                isinstance(manifest.get("properties"), dict)
                and manifest["properties"].get("akasha:composite")
            )
        ):
            continue
        if source_id_from_manifest(manifest) != source_id:
            continue
        manifest_aoi_id = _manifest_aoi_id(manifest)
        if aoi_id and manifest_aoi_id and manifest_aoi_id != aoi_id:
            continue
        acquisition_date = _manifest_datetime(manifest)[:10]
        if window_start <= acquisition_date <= window_end:
            selected.append(manifest_path)
    return sorted(selected)


def _manifest_scene_id(manifest: dict[str, Any], manifest_path: Path) -> str:
    return str(
        manifest.get("product_id")
        or manifest.get("id")
        or manifest.get("source_product_id")
        or manifest_path.parent.name
    )


def _positions(coords: Any) -> list[tuple[float, float]]:
    if (
        isinstance(coords, list | tuple)
        and len(coords) >= 2
        and isinstance(coords[0], int | float)
        and isinstance(coords[1], int | float)
    ):
        return [(float(coords[0]), float(coords[1]))]
    points: list[tuple[float, float]] = []
    if isinstance(coords, list | tuple):
        for child in coords:
            points.extend(_positions(child))
    return points


def _aoi_wgs84_bbox(aoi: dict[str, Any]) -> tuple[float, float, float, float]:
    geometry = aoi.get("geometry") if isinstance(aoi.get("geometry"), dict) else aoi
    points = _positions(geometry.get("coordinates") if isinstance(geometry, dict) else None)
    if not points:
        raise ValueError("AOI geometry has no coordinates")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def grid_from_aoi(
    *,
    deps: dict[str, Any],
    aoi: dict[str, Any],
    crs: str = "EPSG:32643",
    resolution: float = 24.0,
    padding_pixels: int = 0,
) -> CompositeGrid:
    west, south, east, north = _aoi_wgs84_bbox(aoi)
    projected = deps["transform_bounds"](
        "EPSG:4326",
        crs,
        west,
        south,
        east,
        north,
        densify_pts=21,
    )
    return CompositeGrid.from_projected_bounds(
        projected,
        crs=crs,
        resolution=resolution,
        padding_pixels=padding_pixels,
    )


def _grid_affine(deps: dict[str, Any], grid: CompositeGrid) -> Any:
    return deps["Affine"](*grid.transform[:6])


def align_manifest_scene(
    *,
    deps: dict[str, Any],
    manifest_path: Path,
    grid: CompositeGrid,
) -> AlignedScene:
    manifest = _read_manifest(manifest_path)
    analytic_path = _manifest_asset_path(manifest_path, manifest, "analytic")
    mask_path = _manifest_asset_path(manifest_path, manifest, "mask")
    rasterio = deps["rasterio"]
    reproject = deps["reproject"]
    Resampling = deps["Resampling"]
    dst_transform = _grid_affine(deps, grid)

    analytic_out = np.zeros((4, grid.height, grid.width), dtype=np.uint16)
    mask_out = np.zeros((grid.height, grid.width), dtype=np.uint8)
    with rasterio.open(analytic_path) as analytic:
        if analytic.count != 4:
            raise ValueError(f"{analytic_path}: expected 4 ResourceSat analytic bands")
        for band_index in range(1, 5):
            reproject(
                source=rasterio.band(analytic, band_index),
                destination=analytic_out[band_index - 1],
                src_transform=analytic.transform,
                src_crs=analytic.crs,
                src_nodata=NODATA_DN,
                dst_transform=dst_transform,
                dst_crs=grid.crs,
                dst_nodata=NODATA_DN,
                resampling=Resampling.bilinear,
            )
    with rasterio.open(mask_path) as mask:
        if mask.count != 1:
            raise ValueError(f"{mask_path}: expected 1 ResourceSat mask band")
        reproject(
            source=rasterio.band(mask, 1),
            destination=mask_out,
            src_transform=mask.transform,
            src_crs=mask.crs,
            src_nodata=0,
            dst_transform=dst_transform,
            dst_crs=grid.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
    return AlignedScene(
        scene_id=_manifest_scene_id(manifest, manifest_path),
        acquisition_datetime=_manifest_datetime(manifest),
        analytic=analytic_out,
        mask=mask_out,
    )


def _write_intermediate_rasters(
    *,
    deps: dict[str, Any],
    grid: CompositeGrid,
    analytic: np.ndarray,
    mask: np.ndarray,
    analytic_path: Path,
    mask_path: Path,
    source_id: str,
    overwrite: bool,
) -> None:
    if analytic_path.exists() and not overwrite and mask_path.exists():
        return
    if analytic_path.exists():
        analytic_path.unlink()
    if mask_path.exists():
        mask_path.unlink()
    analytic_path.parent.mkdir(parents=True, exist_ok=True)
    rasterio = deps["rasterio"]
    transform = _grid_affine(deps, grid)
    profile = {
        "driver": "GTiff",
        "crs": grid.crs,
        "transform": transform,
        "width": grid.width,
        "height": grid.height,
        "tiled": True,
        "blockxsize": COG_BLOCKSIZE,
        "blockysize": COG_BLOCKSIZE,
        "compress": "DEFLATE",
        "BIGTIFF": "IF_SAFER",
    }
    analytic_profile = dict(
        profile,
        count=4,
        dtype="uint16",
        nodata=NODATA_DN,
        predictor=2,
    )
    with rasterio.open(analytic_path, "w", **analytic_profile) as dst:
        dst.write(analytic)
        for band_index, band_name in enumerate(ANALYTIC_BAND_ORDER, start=1):
            dst.set_band_description(band_index, band_name)
        dst.update_tags(
            AKASHA_SOURCE_ID=source_id,
            AKASHA_COMPOSITE="true",
            AKASHA_BAND_ORDER=",".join(ANALYTIC_BAND_ORDER),
            AKASHA_REFLECTANCE_SCALE="0.0001",
            AKASHA_REFLECTANCE_OFFSET="0",
            AREA_OR_POINT="Area",
        )
    mask_profile = dict(profile, count=1, dtype="uint8", nodata=0, predictor=1)
    with rasterio.open(mask_path, "w", **mask_profile) as dst:
        dst.write(mask, 1)
        dst.set_band_description(1, "mask")
        mask_method = mask_method_for_source(source_id)
        dst.update_tags(1, name="mask", description=mask_method, classes=json.dumps(MASK_CLASSES))
        dst.update_tags(AKASHA_MASK_METHOD=mask_method, AKASHA_COMPOSITE="true")


def _translate_to_cog(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    overview_resampling: str,
    overwrite: bool,
) -> None:
    if output_path.exists() and not overwrite:
        return
    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile = deps["cog_profiles"].get("deflate")
    profile.update(
        {
            "blocksize": COG_BLOCKSIZE,
            "BIGTIFF": "IF_SAFER",
            "overview_resampling": overview_resampling,
        }
    )
    deps["cog_translate"](
        str(source_path),
        str(output_path),
        profile,
        nodata=NODATA_DN,
        overview_resampling=overview_resampling,
        quiet=False,
    )


def _validate_cog(deps: dict[str, Any], path: Path) -> None:
    is_valid, errors, warnings = deps["cog_validate"](str(path), strict=True)
    for warning in warnings:
        print(f"warning {path.name}: {warning}")
    if not is_valid:
        for error in errors:
            print(f"error {path.name}: {error}")
        raise SystemExit(f"COG validation failed for {path}")


def _geometry_from_bbox(bbox: list[float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def _raster_summary(deps: dict[str, Any], path: Path) -> dict[str, Any]:
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
        if dataset.crs:
            west, south, east, north = deps["transform_bounds"](
                dataset.crs,
                "EPSG:4326",
                *dataset.bounds,
                densify_pts=21,
            )
            bbox = [float(west), float(south), float(east), float(north)]
            summary["wgs84_bbox"] = bbox
            summary["wgs84_bounds"] = bbox
            summary["wgs84_geometry"] = _geometry_from_bbox(bbox)
        return summary


def _unique_mask_values(mask_dataset: Any) -> set[int]:
    values = np.unique(mask_dataset.read(1, masked=False))
    return {int(value) for value in values.tolist()}


def _percent(part: int, total: int) -> float:
    return round(part * 100.0 / total, 4) if total else 0.0


def _stac_item_exists(
    *,
    stac_api_url: str,
    collection_id: str,
    item_id: str,
    timeout: int = 10,
) -> tuple[bool, str]:
    if not stac_api_url:
        return False, "STAC_API_URL is not configured"
    url = f"{stac_api_url.rstrip('/')}/collections/" f"{collection_id}/items/{item_id}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            if response.status == 200:
                return True, f"catalog item present: {item_id}"
            return False, f"unexpected STAC status {response.status} for {item_id}"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, f"catalog item missing: {item_id}"
        return False, f"STAC API returned HTTP {exc.code} for {item_id}"
    except Exception as exc:  # noqa: BLE001
        return False, f"STAC API check failed for {item_id}: {exc}"


def verify_composite_manifest(
    *,
    deps: dict[str, Any],
    manifest_path: Path,
    source_id: str = SOURCE_ID,
    expected_aoi_id: str | None = None,
    min_coverage_percent: float = 95.0,
    expected_crs: str = "EPSG:32643",
    expected_resolution: float | None = None,
    resolution_tolerance: float = 0.25,
    require_overviews: bool = True,
    require_catalog_item: bool = False,
    stac_api_url: str = "",
) -> CompositeVerifyResult:
    manifest_path = Path(manifest_path)
    source_id = SOURCE_ALIASES.get(source_id, source_id)
    problems: list[str] = []
    checks: list[str] = []
    if not manifest_path.is_file():
        return CompositeVerifyResult(
            ok=False,
            detail=f"composite manifest not found: {manifest_path}",
            checks=[],
            problems=[f"missing manifest {manifest_path}"],
        )
    manifest = _read_manifest(manifest_path)
    expected_resolution = (
        default_resolution(source_id) if expected_resolution is None else expected_resolution
    )
    profile = source_profile(source_id)
    props = manifest.get("properties") if isinstance(manifest.get("properties"), dict) else {}
    if not bool(manifest.get("composite") or props.get("akasha:composite")):
        problems.append("manifest is not marked as a composite")
    else:
        checks.append("manifest is marked composite")
    if source_id_from_manifest(manifest) != source_id:
        problems.append(f"manifest source is not {profile['label']}")
    else:
        checks.append(f"manifest source is {profile['label']}")
    for key in ("aoi_id", "composite_date", "period_start", "period_end"):
        if not manifest.get(key):
            problems.append(f"manifest missing {key}")
        else:
            checks.append(f"manifest has {key}")
    if expected_aoi_id and manifest.get("aoi_id") != expected_aoi_id:
        problems.append(
            f"manifest aoi_id {manifest.get('aoi_id')!r} does not match expected "
            f"{expected_aoi_id!r}"
        )
    elif expected_aoi_id:
        checks.append(f"manifest aoi_id matches {expected_aoi_id}")
    contributing = manifest.get("contributing_scenes") or props.get("akasha:contributing_scenes")
    if not isinstance(contributing, list) or not contributing:
        problems.append("manifest has no contributing scenes")
    else:
        checks.append(f"manifest has {len(contributing)} contributing scene(s)")
    mask_method = manifest.get("mask_method") or props.get("akasha:mask_method")
    if not isinstance(mask_method, str) or "Akasha threshold mask v1" not in mask_method:
        problems.append("manifest missing ResourceSat provisional mask method")
    else:
        checks.append("manifest records ResourceSat provisional mask method")
    metrics_provisional = manifest.get("akasha:metrics_provisional")
    if metrics_provisional is None:
        metrics_provisional = props.get("akasha:metrics_provisional")
    if metrics_provisional is not True:
        problems.append("manifest does not mark ResourceSat metrics as provisional")
    else:
        checks.append("manifest marks metrics provisional")
    class_values = {
        item.get("value")
        for item in manifest.get("classification_classes", [])
        if isinstance(item, dict)
    }
    expected_class_values = {item["value"] for item in MASK_CLASSES}
    if class_values != expected_class_values:
        problems.append("manifest classification classes do not match ResourceSat mask classes")
    else:
        checks.append("manifest records ResourceSat mask classes")

    analytic_path = _manifest_asset_path_from_outputs(manifest_path, manifest, "analytic")
    mask_path = _manifest_asset_path_from_outputs(manifest_path, manifest, "mask")
    if not analytic_path.is_file():
        problems.append(f"missing analytic COG: {analytic_path}")
    if not mask_path.is_file():
        problems.append(f"missing mask COG: {mask_path}")
    if problems:
        return CompositeVerifyResult(
            ok=False,
            detail="; ".join(problems),
            checks=checks,
            problems=problems,
        )

    rasterio = deps["rasterio"]
    with rasterio.open(analytic_path) as analytic, rasterio.open(mask_path) as mask:
        if analytic.count != 4:
            problems.append(f"analytic band count {analytic.count} != 4")
        else:
            checks.append("analytic has 4 bands")
        if mask.count != 1:
            problems.append(f"mask band count {mask.count} != 1")
        else:
            checks.append("mask has 1 band")
        if analytic.crs != mask.crs:
            problems.append(f"CRS mismatch analytic={analytic.crs} mask={mask.crs}")
        elif analytic.crs is None:
            problems.append("analytic/mask CRS is missing")
        elif analytic.crs.to_string() != expected_crs:
            problems.append(f"CRS {analytic.crs.to_string()} != {expected_crs}")
        else:
            checks.append(f"CRS is {expected_crs}")
        if analytic.transform != mask.transform:
            problems.append("analytic/mask transform mismatch")
        else:
            checks.append("analytic/mask transform aligned")
        if (analytic.width, analytic.height) != (mask.width, mask.height):
            problems.append(
                "analytic/mask shape mismatch "
                f"{analytic.width}x{analytic.height} != {mask.width}x{mask.height}"
            )
        else:
            checks.append(f"shape aligned {analytic.width}x{analytic.height}")
        xres, yres = analytic.res
        if abs(float(xres) - expected_resolution) > resolution_tolerance or (
            abs(abs(float(yres)) - expected_resolution) > resolution_tolerance
        ):
            problems.append(
                f"resolution {analytic.res} not within {resolution_tolerance} "
                f"of {expected_resolution}"
            )
        else:
            checks.append(f"resolution near {expected_resolution}m")
        if require_overviews:
            if not analytic.overviews(1):
                problems.append("analytic COG has no overviews")
            else:
                checks.append("analytic has overviews")
            if not mask.overviews(1):
                problems.append("mask COG has no overviews")
            else:
                checks.append("mask has overviews")
        mask_values = _unique_mask_values(mask)
        allowed = {klass["value"] for klass in MASK_CLASSES}
        invalid_mask_values = sorted(mask_values - allowed)
        if invalid_mask_values:
            problems.append(f"invalid mask class value(s): {invalid_mask_values}")
        else:
            checks.append(f"mask classes valid: {sorted(mask_values)}")
        mask_array = mask.read(1, masked=False)
        coverage_percent = _percent(int(np.count_nonzero(mask_array != 0)), mask_array.size)
        if coverage_percent < min_coverage_percent:
            problems.append(f"coverage {coverage_percent}% below threshold {min_coverage_percent}%")
        else:
            checks.append(f"coverage {coverage_percent}% >= {min_coverage_percent}%")

    try:
        from . import catalog

        item = catalog.build_stac_item_from_prepare_manifest(manifest)
        expected_item_id = (
            f"{source_id}_composite_" f"{manifest.get('aoi_id')}_{manifest.get('composite_date')}"
        )
        if item["id"] != expected_item_id:
            problems.append(f"unexpected composite STAC item id: {item['id']}")
        elif not item["properties"].get("akasha:composite"):
            problems.append("STAC item is not marked composite")
        else:
            checks.append(f"dated composite STAC item buildable: {item['id']}")
        if require_catalog_item:
            exists, detail = _stac_item_exists(
                stac_api_url=stac_api_url,
                collection_id=str(item["collection"]),
                item_id=str(item["id"]),
            )
            if exists:
                checks.append(detail)
            else:
                problems.append(detail)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"could not build composite STAC item: {exc}")

    ok = not problems
    detail = (
        f"composite verification passed ({len(checks)} checks)"
        if ok
        else "composite verification failed -> " + "; ".join(problems)
    )
    return CompositeVerifyResult(ok=ok, detail=detail, checks=checks, problems=problems)


def _composite_output_dir(
    output_root: Path, source_id: str, aoi_id: str, composite_date: str
) -> Path:
    return output_root / source_id / "composite" / aoi_id / composite_date


def _write_composite_manifest(
    *,
    deps: dict[str, Any],
    manifest_path: Path,
    aoi_id: str,
    grid: CompositeGrid,
    composite_datetime: str,
    period_start: str,
    period_end: str,
    source_manifest_paths: list[Path],
    analytic_cog: Path,
    mask_cog: Path,
    metrics: dict[str, Any],
    source_id: str,
) -> None:
    analytic_summary = _raster_summary(deps, analytic_cog)
    mask_summary = _raster_summary(deps, mask_cog)
    composite_date = composite_datetime[:10]
    profile = source_profile(source_id)
    mask_method = mask_method_for_source(source_id)
    payload: dict[str, Any] = {
        "source_id": source_id,
        "collection": profile["collection"],
        "product_id": f"{source_id}-composite-{aoi_id}-{composite_date}",
        "platform": "resourcesat-2a",
        "product_level": "BOA-COMPOSITE",
        "composite": True,
        "aoi_id": aoi_id,
        "composite_grid_crs": grid.crs,
        "composite_resolution_meters": grid.resolution,
        "composite_grid_bounds": list(grid.bounds),
        "composite_grid_dimensions": [grid.width, grid.height],
        "composite_grid_transform": list(grid.transform),
        "composite_date": composite_date,
        "acquisition_datetime": composite_datetime,
        "acquisition_date": composite_date,
        "period_start": period_start,
        "period_end": period_end,
        "source_manifests": [path.as_posix() for path in source_manifest_paths],
        "contributing_scenes": metrics["contributing_scenes"],
        "analytic_band_order": ANALYTIC_BAND_ORDER,
        "band_role_mapping": BAND_ROLE_MAPPING,
        "mask_method": mask_method,
        "classification_classes": MASK_CLASSES,
        "outputs": {
            "analytic": analytic_summary,
            "mask": mask_summary,
        },
        "properties": {
            "akasha:composite": True,
            "akasha:aoi_id": aoi_id,
            "akasha:composite_grid_crs": grid.crs,
            "akasha:composite_resolution_meters": grid.resolution,
            "akasha:composite_grid_bounds": list(grid.bounds),
            "akasha:composite_grid_dimensions": [grid.width, grid.height],
            "akasha:period_start": period_start,
            "akasha:period_end": period_end,
            "akasha:contributing_scenes": metrics["contributing_scenes"],
            "akasha:coverage_percent": metrics["coverage_percent"],
            "akasha:usable_pixel_percent": metrics["usable_pixel_percent"],
            "akasha:cloud_masked_percent": metrics["cloud_masked_percent"],
            "akasha:mask_method": mask_method,
            "akasha:metrics_provisional": True,
            "akasha:band_role_mapping": BAND_ROLE_MAPPING,
        },
    }
    if analytic_summary.get("wgs84_bbox"):
        payload["bbox"] = analytic_summary["wgs84_bbox"]
        payload["geometry"] = analytic_summary.get("wgs84_geometry") or _geometry_from_bbox(
            analytic_summary["wgs84_bbox"]
        )
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_resource_sat_composite(
    *,
    deps: dict[str, Any],
    manifest_paths: list[Path],
    aoi: dict[str, Any],
    output_root: Path,
    window_start: str,
    window_end: str,
    source_id: str = SOURCE_ID,
    resolution: float | None = None,
    padding_pixels: int = 0,
    overwrite: bool = False,
    skip_validation: bool = False,
    keep_intermediate: bool = False,
) -> CompositeBuildResult:
    if not manifest_paths:
        raise ValueError("no ResourceSat scene manifests supplied")
    source_id = SOURCE_ALIASES.get(source_id, source_id)
    source_profile(source_id)
    resolution = default_resolution(source_id) if resolution is None else resolution
    aoi_id = str(aoi.get("id") or aoi.get("properties", {}).get("id") or "unknown-aoi")
    crs = aoi_composite_grid_crs(aoi)
    grid = grid_from_aoi(
        deps=deps,
        aoi=aoi,
        crs=crs,
        resolution=resolution,
        padding_pixels=padding_pixels,
    )
    aligned = [
        align_manifest_scene(deps=deps, manifest_path=path, grid=grid) for path in manifest_paths
    ]
    result = build_best_available_composite(aligned)
    composite_datetime = max(scene.acquisition_datetime for scene in aligned)
    composite_date = composite_datetime[:10]
    output_dir = _composite_output_dir(output_root, source_id, aoi_id, composite_date)
    temp_dir = output_dir / "_tmp"
    analytic_intermediate = temp_dir / "analytic_intermediate.tif"
    mask_intermediate = temp_dir / "mask_intermediate.tif"
    analytic_cog = output_dir / "analytic.tif"
    mask_cog = output_dir / "mask.tif"
    manifest = output_dir / "prepare_manifest.json"
    _write_intermediate_rasters(
        deps=deps,
        grid=grid,
        analytic=result["analytic"],
        mask=result["mask"],
        analytic_path=analytic_intermediate,
        mask_path=mask_intermediate,
        source_id=source_id,
        overwrite=overwrite,
    )
    _translate_to_cog(
        deps=deps,
        source_path=analytic_intermediate,
        output_path=analytic_cog,
        overview_resampling="average",
        overwrite=overwrite,
    )
    _translate_to_cog(
        deps=deps,
        source_path=mask_intermediate,
        output_path=mask_cog,
        overview_resampling="nearest",
        overwrite=overwrite,
    )
    if not skip_validation:
        _validate_cog(deps, analytic_cog)
        _validate_cog(deps, mask_cog)
    _write_composite_manifest(
        deps=deps,
        manifest_path=manifest,
        aoi_id=aoi_id,
        grid=grid,
        composite_datetime=composite_datetime,
        period_start=window_start,
        period_end=window_end,
        source_manifest_paths=manifest_paths,
        analytic_cog=analytic_cog,
        mask_cog=mask_cog,
        metrics=result["metrics"],
        source_id=source_id,
    )
    if not keep_intermediate:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
    return CompositeBuildResult(
        output_dir=output_dir,
        analytic_cog=analytic_cog,
        mask_cog=mask_cog,
        manifest=manifest,
        metrics=result["metrics"],
    )
