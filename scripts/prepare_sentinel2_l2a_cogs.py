"""Prepare Akasha Slice 2 analytic and SCL COGs from a Sentinel-2 L2A SAFE ZIP.

Inputs
------
A complete Copernicus Sentinel-2 L2A SAFE ZIP downloaded by
``scripts/download_sentinel2_l2a_product.py``.

Outputs
-------
``data/seed/rasters/<acquisition-date>/analytic.tif``
    9-band uint16 COG in the frozen Akasha order:
    [B04, B08, B05, B06, B07, B11, B12, B03, B02]

``data/seed/rasters/<acquisition-date>/scl.tif``
    1-band uint8 categorical SCL COG resampled to the analytic 10 m grid with
    nearest-neighbour resampling.

Run inside the ingestion container for the least GDAL friction on Windows:

    docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
        python scripts/prepare_sentinel2_l2a_cogs.py --overwrite
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
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "sentinel-2-l2a"
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "work" / "sentinel-2-l2a"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "seed" / "rasters"

ANALYTIC_BANDS: tuple[tuple[str, str, str], ...] = (
    ("B04", "B04_10m", "Red"),
    ("B08", "B08_10m", "NIR"),
    ("B05", "B05_20m", "Red edge 1"),
    ("B06", "B06_20m", "Red edge 2"),
    ("B07", "B07_20m", "Red edge 3"),
    ("B11", "B11_20m", "SWIR 1"),
    ("B12", "B12_20m", "SWIR 2"),
    ("B03", "B03_10m", "Green"),
    ("B02", "B02_10m", "Blue"),
)
SCL_ASSET = "SCL_20m"
NODATA_DN = 0
COG_BLOCKSIZE = 512


@dataclass(frozen=True)
class PreparedPaths:
    zip_path: Path
    safe_dir: Path
    output_dir: Path
    analytic_cog: Path
    scl_cog: Path
    manifest: Path


def require_raster_deps() -> dict[str, Any]:
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject
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
        "cog_translate": cog_translate,
        "cog_validate": cog_validate,
        "cog_profiles": cog_profiles,
    }


def resolve_zip_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    candidates = sorted(DEFAULT_RAW_DIR.rglob("*.SAFE.zip"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise SystemExit(
            f"No SAFE ZIP found under {DEFAULT_RAW_DIR}. Pass --zip-path explicitly."
        )
    return candidates[-1].resolve()


def acquisition_date_from_name(name: str) -> str:
    match = re.search(r"MSIL2A_(\d{8})T", name)
    if not match:
        raise SystemExit(f"Could not infer acquisition date from {name}; pass --date YYYY-MM-DD")
    value = match.group(1)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def safe_name_from_zip(zip_path: Path) -> str:
    name = zip_path.name
    if name.endswith(".SAFE.zip"):
        return name[: -len(".zip")]
    if name.endswith(".zip"):
        return name[: -len(".zip")]
    return zip_path.stem


def extract_safe(zip_path: Path, work_dir: Path, *, overwrite: bool) -> Path:
    safe_name = safe_name_from_zip(zip_path)
    target = work_dir / safe_name
    if target.exists() and overwrite:
        shutil.rmtree(target)
    if target.exists():
        return target

    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"extract {zip_path} -> {work_dir}")
    with zipfile.ZipFile(zip_path) as archive:
        bad_file = archive.testzip()
        if bad_file is not None:
            raise SystemExit(f"ZIP integrity check failed at {bad_file}")
        archive.extractall(work_dir)

    if target.exists():
        return target

    safe_dirs = sorted(work_dir.glob("*.SAFE"))
    if len(safe_dirs) == 1:
        return safe_dirs[0]
    raise SystemExit(f"Could not find extracted SAFE directory in {work_dir}")


def find_asset(safe_dir: Path, asset_token: str) -> Path:
    matches = sorted(safe_dir.rglob(f"*_{asset_token}.jp2"))
    if not matches:
        matches = sorted(safe_dir.rglob(f"*{asset_token}.jp2"))
    if len(matches) != 1:
        found = "none" if not matches else ", ".join(p.as_posix() for p in matches[:10])
        raise SystemExit(f"Expected exactly one {asset_token}.jp2 under {safe_dir}; found {found}")
    return matches[0]


def same_grid(src: Any, reference: Any) -> bool:
    return (
        src.crs == reference.crs
        and src.transform == reference.transform
        and src.width == reference.width
        and src.height == reference.height
    )


def build_analytic_intermediate(
    *,
    deps: dict[str, Any],
    safe_dir: Path,
    intermediate_path: Path,
    overwrite: bool,
) -> Path:
    np = deps["np"]
    rasterio = deps["rasterio"]
    Resampling = deps["Resampling"]
    reproject = deps["reproject"]

    if intermediate_path.exists() and not overwrite:
        return intermediate_path
    intermediate_path.parent.mkdir(parents=True, exist_ok=True)
    if intermediate_path.exists():
        intermediate_path.unlink()

    reference_path = find_asset(safe_dir, "B04_10m")
    print(f"reference grid: {reference_path}")
    with rasterio.open(reference_path) as reference:
        profile = reference.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(ANALYTIC_BANDS),
            dtype="uint16",
            nodata=NODATA_DN,
            tiled=True,
            blockxsize=COG_BLOCKSIZE,
            blockysize=COG_BLOCKSIZE,
            compress="DEFLATE",
            predictor=2,
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(intermediate_path, "w", **profile) as dst:
            for band_index, (band_name, asset_token, description) in enumerate(
                ANALYTIC_BANDS, start=1
            ):
                source_path = find_asset(safe_dir, asset_token)
                print(f"analytic b{band_index}: {band_name} <- {source_path.name}")
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
                        description=description,
                        source_asset=asset_token,
                    )
            dst.update_tags(
                AKASHA_BAND_ORDER=",".join(band for band, _, _ in ANALYTIC_BANDS),
                AKASHA_REFLECTANCE_SCALE="0.0001",
                AKASHA_REFLECTANCE_OFFSET="-0.1",
                AREA_OR_POINT="Area",
            )
    return intermediate_path


def build_scl_intermediate(
    *,
    deps: dict[str, Any],
    safe_dir: Path,
    reference_path: Path,
    intermediate_path: Path,
    overwrite: bool,
) -> Path:
    np = deps["np"]
    rasterio = deps["rasterio"]
    Resampling = deps["Resampling"]
    reproject = deps["reproject"]

    if intermediate_path.exists() and not overwrite:
        return intermediate_path
    intermediate_path.parent.mkdir(parents=True, exist_ok=True)
    if intermediate_path.exists():
        intermediate_path.unlink()

    scl_path = find_asset(safe_dir, SCL_ASSET)
    print(f"scl <- {scl_path.name}")
    with rasterio.open(reference_path) as reference, rasterio.open(scl_path) as src:
        profile = reference.profile.copy()
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
        data = np.zeros((reference.height, reference.width), dtype="uint8")
        reproject(
            source=rasterio.band(src, 1),
            destination=data,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        with rasterio.open(intermediate_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.set_band_description(1, "SCL")
            dst.update_tags(1, name="SCL", description="Scene Classification Layer")
            dst.update_tags(AKASHA_SOURCE_ASSET=SCL_ASSET, AREA_OR_POINT="Area")
    return intermediate_path


def translate_to_cog(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    overview_resampling: str,
    overwrite: bool,
) -> None:
    cog_translate = deps["cog_translate"]
    cog_profiles = deps["cog_profiles"]

    if output_path.exists() and not overwrite:
        print(f"keep existing {output_path}")
        return
    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile = cog_profiles.get("deflate")
    profile.update(
        {
            "blocksize": COG_BLOCKSIZE,
            "BIGTIFF": "IF_SAFER",
            "overview_resampling": overview_resampling,
        }
    )
    print(f"cog translate {source_path.name} -> {output_path}")
    cog_translate(
        str(source_path),
        str(output_path),
        profile,
        nodata=NODATA_DN,
        overview_resampling=overview_resampling,
        quiet=False,
    )


def validate_cog(deps: dict[str, Any], path: Path) -> None:
    cog_validate = deps["cog_validate"]
    is_valid, errors, warnings = cog_validate(str(path), strict=True)
    for warning in warnings:
        print(f"warning {path.name}: {warning}")
    if not is_valid:
        for error in errors:
            print(f"error {path.name}: {error}")
        raise SystemExit(f"COG validation failed for {path}")
    print(f"valid COG: {path}")


def raster_summary(deps: dict[str, Any], path: Path) -> dict[str, Any]:
    rasterio = deps["rasterio"]
    with rasterio.open(path) as dataset:
        return {
            "path": path.as_posix(),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "bounds": list(dataset.bounds),
            "resolution": list(dataset.res),
            "width": dataset.width,
            "height": dataset.height,
            "dtype": dataset.dtypes[0] if dataset.dtypes else None,
            "band_count": dataset.count,
            "nodata": dataset.nodata,
            "descriptions": list(dataset.descriptions),
        }


def write_manifest(
    *,
    deps: dict[str, Any],
    paths: PreparedPaths,
    analytic_intermediate: Path,
    scl_intermediate: Path,
) -> None:
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_zip": paths.zip_path.as_posix(),
        "safe_dir": paths.safe_dir.as_posix(),
        "analytic_band_order": [band for band, _, _ in ANALYTIC_BANDS],
        "analytic_source_assets": [asset for _, asset, _ in ANALYTIC_BANDS],
        "scl_source_asset": SCL_ASSET,
        "intermediates": {
            "analytic": analytic_intermediate.as_posix(),
            "scl": scl_intermediate.as_posix(),
        },
        "outputs": {
            "analytic": raster_summary(deps, paths.analytic_cog),
            "scl": raster_summary(deps, paths.scl_cog),
        },
    }
    paths.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {paths.manifest}")


def prepare_paths(args: argparse.Namespace) -> PreparedPaths:
    zip_path = resolve_zip_path(args.zip_path)
    date = args.date or acquisition_date_from_name(zip_path.name)
    work_dir = Path(args.work_dir)
    if not work_dir.is_absolute():
        work_dir = (REPO_ROOT / work_dir).resolve()
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (REPO_ROOT / output_root).resolve()

    safe_dir = extract_safe(zip_path, work_dir, overwrite=args.reextract)
    output_dir = output_root / date
    return PreparedPaths(
        zip_path=zip_path,
        safe_dir=safe_dir,
        output_dir=output_dir,
        analytic_cog=output_dir / "analytic.tif",
        scl_cog=output_dir / "scl.tif",
        manifest=output_dir / "prepare_manifest.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip-path", help="Path to the downloaded .SAFE.zip")
    parser.add_argument("--date", help="Output acquisition date folder, e.g. 2025-09-14")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT.relative_to(REPO_ROOT)))
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing COG outputs")
    parser.add_argument("--reextract", action="store_true", help="Re-extract the SAFE ZIP")
    parser.add_argument("--keep-intermediate", action="store_true", help="Keep temporary GTiff files")
    parser.add_argument("--skip-validation", action="store_true", help="Skip rio-cogeo validation")
    args = parser.parse_args(argv)

    deps = require_raster_deps()
    paths = prepare_paths(args)
    temp_dir = paths.output_dir / "_tmp"
    analytic_intermediate = temp_dir / "analytic_intermediate.tif"
    scl_intermediate = temp_dir / "scl_intermediate.tif"

    print(f"source zip: {paths.zip_path}")
    print(f"safe dir: {paths.safe_dir}")
    print(f"output dir: {paths.output_dir}")

    reference_path = find_asset(paths.safe_dir, "B04_10m")
    build_analytic_intermediate(
        deps=deps,
        safe_dir=paths.safe_dir,
        intermediate_path=analytic_intermediate,
        overwrite=args.overwrite,
    )
    build_scl_intermediate(
        deps=deps,
        safe_dir=paths.safe_dir,
        reference_path=reference_path,
        intermediate_path=scl_intermediate,
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
        source_path=scl_intermediate,
        output_path=paths.scl_cog,
        overview_resampling="nearest",
        overwrite=args.overwrite,
    )

    if not args.skip_validation:
        validate_cog(deps, paths.analytic_cog)
        validate_cog(deps, paths.scl_cog)

    write_manifest(
        deps=deps,
        paths=paths,
        analytic_intermediate=analytic_intermediate,
        scl_intermediate=scl_intermediate,
    )

    if not args.keep_intermediate and temp_dir.exists():
        shutil.rmtree(temp_dir)
        print(f"removed temporary files: {temp_dir}")

    print("COG preparation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
