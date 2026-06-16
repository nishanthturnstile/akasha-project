"""Prepare operator-provided context GeoTIFFs as COGs + ingest manifests.

This is the manual Phase 7 path for gated visual/context sources such as
Cartosat-3. It does not automate Bhoonidhi search/download and does not enable
field analytics. The output layout is source-scoped and can be ingested with:

    python services/ingestion/worker.py ingest-manifest --collection-id cartosat-3-gated
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest.scene import SceneIdentity  # noqa: E402

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "seed" / "rasters"
COG_BLOCKSIZE = 512


@dataclass(frozen=True)
class ContextSourceProfile:
    source_id: str
    asset_key: str
    platform: str
    product_level: str
    product_type: str
    gsd: float | None = None


SOURCE_PROFILES = {
    "cartosat-3-gated": ContextSourceProfile(
        source_id="cartosat-3-gated",
        asset_key="visual",
        platform="cartosat-3",
        product_level="VISUAL-CONTEXT",
        product_type="operator-upload-visual",
    ),
    "eos-06-ocm-lac-ndvi-8day-360m": ContextSourceProfile(
        source_id="eos-06-ocm-lac-ndvi-8day-360m",
        asset_key="ndvi",
        platform="eos-06",
        product_level="NDVI-CONTEXT",
        product_type="precomputed-ndvi-context",
        gsd=360.0,
    ),
}


def source_profile(source_id: str) -> ContextSourceProfile:
    try:
        return SOURCE_PROFILES[source_id]
    except KeyError as exc:
        supported = ", ".join(sorted(SOURCE_PROFILES))
        raise SystemExit(
            f"Unsupported context source '{source_id}'. Supported: {supported}"
        ) from exc


def require_raster_deps() -> dict[str, Any]:
    try:
        import rasterio
        from rasterio.warp import transform_bounds
        from rio_cogeo.cogeo import cog_translate, cog_validate
        from rio_cogeo.profiles import cog_profiles
    except ModuleNotFoundError as exc:
        missing = exc.name or "raster dependency"
        raise SystemExit(
            f"Missing {missing}. Run this inside the ingestion image or install rasterio "
            "and rio-cogeo."
        ) from exc
    return {
        "rasterio": rasterio,
        "transform_bounds": transform_bounds,
        "cog_translate": cog_translate,
        "cog_validate": cog_validate,
        "cog_profiles": cog_profiles,
    }


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def normalize_datetime(value: str) -> str:
    if value.endswith("Z"):
        return value
    if value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value if "T" in value else f"{value}T00:00:00Z"


def _initial_manifest(
    *,
    profile: ContextSourceProfile,
    product_id: str,
    acquisition_datetime: str,
) -> dict[str, Any]:
    return {
        "source_id": profile.source_id,
        "product_id": product_id,
        "platform": profile.platform,
        "product_level": profile.product_level,
        "product:type": profile.product_type,
        "acquisition_datetime": normalize_datetime(acquisition_datetime),
        "properties": {
            "akasha:coverage_percent": 100.0,
            "akasha:metrics_provisional": True,
        },
    }


def _cog_profile(deps: dict[str, Any]) -> dict[str, Any]:
    profile = deps["cog_profiles"].get("deflate")
    profile.update({"blocksize": COG_BLOCKSIZE, "bigtiff": "IF_SAFER"})
    return profile


def write_cog(
    *,
    deps: dict[str, Any],
    source_path: Path,
    output_path: Path,
    overwrite: bool = False,
) -> None:
    if output_path.exists() and not overwrite:
        raise SystemExit(f"{output_path} already exists; pass --overwrite to replace it.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deps["cog_translate"](
        str(source_path),
        str(output_path),
        _cog_profile(deps),
        quiet=True,
    )


def raster_metadata(
    *,
    deps: dict[str, Any],
    cog_path: Path,
    fallback_gsd: float | None = None,
) -> dict[str, Any]:
    with deps["rasterio"].open(cog_path) as dataset:
        bounds = [float(v) for v in dataset.bounds]
        crs = dataset.crs
        if crs:
            west, south, east, north = deps["transform_bounds"](
                crs,
                "EPSG:4326",
                *bounds,
                densify_pts=21,
            )
            bbox = [float(west), float(south), float(east), float(north)]
            crs_text = crs.to_string()
        else:
            bbox = bounds
            crs_text = None
        transform = [float(v) for v in dataset.transform.to_gdal()]
        descriptions = [
            str(desc) if desc else f"band_{index}"
            for index, desc in enumerate(dataset.descriptions, start=1)
        ]
        meta: dict[str, Any] = {
            "path": cog_path.name,
            "crs": crs_text,
            "bounds": bounds,
            "bbox": bbox,
            "resolution": [abs(float(dataset.transform.a)), abs(float(dataset.transform.e))],
            "width": dataset.width,
            "height": dataset.height,
            "shape": [dataset.height, dataset.width],
            "transform": transform,
            "dtype": dataset.dtypes[0],
            "band_count": dataset.count,
            "descriptions": descriptions,
        }
        if fallback_gsd is not None:
            meta["gsd"] = fallback_gsd
        return {key: value for key, value in meta.items() if value is not None}


def validate_cog(deps: dict[str, Any], cog_path: Path) -> None:
    valid, errors, warnings = deps["cog_validate"](str(cog_path), strict=True)
    if not valid:
        detail = "; ".join([*errors, *warnings])
        raise SystemExit(f"COG validation failed for {cog_path}: {detail}")


def prepare_context_cog(args: argparse.Namespace) -> Path:
    deps = require_raster_deps()
    profile = source_profile(args.source)
    source_path = resolve_path(args.input)
    if not source_path.is_file():
        raise SystemExit(f"Input GeoTIFF not found: {source_path}")

    manifest = _initial_manifest(
        profile=profile,
        product_id=args.product_id,
        acquisition_datetime=args.acquisition_datetime,
    )
    if args.gsd is not None:
        manifest["gsd"] = float(args.gsd)
    elif profile.gsd is not None:
        manifest["gsd"] = profile.gsd

    scene = SceneIdentity.from_prepare_manifest(manifest)
    output_root = resolve_path(args.output_root)
    output_dir = output_root / scene.source_id / scene.acquisition_date / scene.scene_component
    cog_path = output_dir / f"{profile.asset_key}.tif"

    write_cog(deps=deps, source_path=source_path, output_path=cog_path, overwrite=args.overwrite)
    if not args.skip_validation:
        validate_cog(deps, cog_path)

    asset_meta = raster_metadata(
        deps=deps,
        cog_path=cog_path,
        fallback_gsd=args.gsd if args.gsd is not None else profile.gsd,
    )
    manifest["bbox"] = asset_meta["bbox"]
    manifest["outputs"] = {profile.asset_key: asset_meta}

    manifest_path = output_dir / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Operator-provided GeoTIFF.")
    parser.add_argument("--product-id", required=True, help="Stable licensed product/order id.")
    parser.add_argument(
        "--acquisition-datetime",
        required=True,
        help="Acquisition datetime/date, e.g. 2026-04-16T05:30:00Z.",
    )
    parser.add_argument("--source", default="cartosat-3-gated", choices=sorted(SOURCE_PROFILES))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--gsd", type=float, default=None, help="Optional ground sample distance.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = prepare_context_cog(args)
    print(f"manifest: {manifest}")
    print(f"asset: {manifest.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
