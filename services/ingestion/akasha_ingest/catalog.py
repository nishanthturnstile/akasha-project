"""pgSTAC catalog operations (Slice 1).

Wraps pypgstac for: schema migration, and idempotent (upsert) loading of the
Sentinel-2 L2A collection + sample item. pypgstac is imported lazily so this
module imports cleanly without it installed (static validation / `info`).

pypgstac 0.9.x matches the stac-fastapi-pgstac:5.0.2 runtime (>=0.8,<0.10).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import config
from .scene import SceneIdentity

STAC_EXTENSIONS = [
    "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
    "https://stac-extensions.github.io/classification/v1.1.0/schema.json",
]
SENTINEL1_STAC_EXTENSIONS = [
    "https://stac-extensions.github.io/sar/v1.0.0/schema.json",
    "https://stac-extensions.github.io/sat/v1.0.0/schema.json",
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
]

ANALYTIC_EO_BANDS = [
    {
        "name": "B04",
        "common_name": "red",
        "center_wavelength": 0.665,
        "full_width_half_max": 0.038,
    },
    {
        "name": "B08",
        "common_name": "nir",
        "center_wavelength": 0.842,
        "full_width_half_max": 0.145,
    },
    {
        "name": "B05",
        "common_name": "rededge",
        "center_wavelength": 0.704,
        "full_width_half_max": 0.019,
    },
    {
        "name": "B06",
        "common_name": "rededge",
        "center_wavelength": 0.740,
        "full_width_half_max": 0.018,
    },
    {
        "name": "B07",
        "common_name": "rededge",
        "center_wavelength": 0.783,
        "full_width_half_max": 0.028,
    },
    {
        "name": "B11",
        "common_name": "swir16",
        "center_wavelength": 1.610,
        "full_width_half_max": 0.143,
    },
    {
        "name": "B12",
        "common_name": "swir22",
        "center_wavelength": 2.190,
        "full_width_half_max": 0.242,
    },
    {
        "name": "B03",
        "common_name": "green",
        "center_wavelength": 0.560,
        "full_width_half_max": 0.045,
    },
    {
        "name": "B02",
        "common_name": "blue",
        "center_wavelength": 0.490,
        "full_width_half_max": 0.098,
    },
]

SCL_CLASSES = [
    {"value": 0, "name": "no_data", "description": "No data", "nodata": True},
    {"value": 1, "name": "saturated_defective", "description": "Saturated or defective"},
    {"value": 2, "name": "dark_area", "description": "Dark area / cast & topographic shadow"},
    {"value": 3, "name": "cloud_shadow", "description": "Cloud shadow"},
    {"value": 4, "name": "vegetation", "description": "Vegetation"},
    {"value": 5, "name": "not_vegetated", "description": "Bare soils / not vegetated"},
    {"value": 6, "name": "water", "description": "Water"},
    {"value": 7, "name": "unclassified", "description": "Unclassified"},
    {"value": 8, "name": "cloud_medium_probability", "description": "Cloud medium probability"},
    {"value": 9, "name": "cloud_high_probability", "description": "Cloud high probability"},
    {"value": 10, "name": "thin_cirrus", "description": "Thin cirrus"},
    {"value": 11, "name": "snow_ice", "description": "Snow or ice"},
]

RESOURCESAT_LISS3_EO_BANDS = [
    {
        "name": "BAND2",
        "common_name": "green",
        "center_wavelength": 0.555,
        "full_width_half_max": 0.07,
    },
    {
        "name": "BAND3",
        "common_name": "red",
        "center_wavelength": 0.655,
        "full_width_half_max": 0.07,
    },
    {
        "name": "BAND4",
        "common_name": "nir",
        "center_wavelength": 0.815,
        "full_width_half_max": 0.11,
    },
    {
        "name": "BAND5",
        "common_name": "swir16",
        "center_wavelength": 1.650,
        "full_width_half_max": 0.20,
    },
]

RESOURCESAT_MASK_CLASSES = [
    {"value": 0, "name": "nodata", "description": "No data / outside scene", "nodata": True},
    {"value": 1, "name": "valid", "description": "Valid clear land or water pixel"},
    {"value": 2, "name": "cloud", "description": "Akasha threshold-derived cloud"},
    {"value": 3, "name": "cloud_shadow", "description": "Akasha threshold-derived shadow"},
    {"value": 4, "name": "all_band_gap", "description": "All analytic bands are empty or invalid"},
]

RESOURCESAT_BAND_ROLE_MAPPING = {
    "GREEN": "BAND2",
    "RED": "BAND3",
    "NIR": "BAND4",
    "SWIR1": "BAND5",
}

RESOURCESAT_MASK_METHOD = (
    "Akasha threshold mask v1 (no native quality layer found in validated "
    "LISS-3 BOA sample; provisional)."
)


def _require_dsn() -> str:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (required for pgSTAC).")
    return config.DATABASE_URL


def migrate_catalog() -> str:
    """Run pgSTAC migrations to the pypgstac-bundled schema version (idempotent)."""
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.migrate import Migrate  # lazy

    with PgstacDB(dsn=_require_dsn()) as db:
        version = Migrate(db).run_migration()
    return f"pgSTAC migrated to {version}"


def _write_ndjson(records: Iterable[dict]) -> Path:
    out_dir = config.find_seed_dir() / "stac"
    out_dir.mkdir(parents=True, exist_ok=True)
    ndjson = out_dir / f".akasha-items-{uuid.uuid4().hex}.ndjson"
    with ndjson.open("w", encoding="utf-8") as tmp:
        for rec in records:
            tmp.write(json.dumps(rec) + "\n")
    return ndjson


def load_collection(method: str = "upsert", collection_id: str | None = None) -> str:
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.load import Loader, Methods  # lazy

    collection = json.loads(config.collection_file(collection_id).read_text())
    ndjson = _write_ndjson([collection])
    try:
        with PgstacDB(dsn=_require_dsn()) as db:
            Loader(db=db).load_collections(str(ndjson), insert_mode=Methods(method))
    finally:
        ndjson.unlink(missing_ok=True)
    return f"loaded collection {collection.get('id')} (method={method})"


def load_items(method: str = "upsert", collection_id: str | None = None) -> str:
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.load import Loader, Methods  # lazy

    item_paths = config.item_files(collection_id)
    if not item_paths:
        source_id = collection_id or config.COLLECTION_ID
        return f"loaded 0 seed item(s) for {source_id} (method={method})"
    items = [json.loads(path.read_text(encoding="utf-8")) for path in item_paths]
    ndjson = _write_ndjson(items)
    try:
        with PgstacDB(dsn=_require_dsn()) as db:
            Loader(db=db).load_items(str(ndjson), insert_mode=Methods(method))
    finally:
        ndjson.unlink(missing_ok=True)
    return f"loaded {len(items)} seed item(s) (method={method})"


def _read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _output_meta(manifest: dict[str, Any], asset: str) -> dict[str, Any]:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    meta = outputs.get(asset, {})
    return meta if isinstance(meta, dict) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _epsg(crs: Any) -> int | None:
    if crs is None:
        return None
    text = str(crs).upper()
    if "EPSG:" in text:
        return int(text.rsplit("EPSG:", 1)[1].split()[0])
    if text.isdigit():
        return int(text)
    return None


def _shape(meta: dict[str, Any]) -> list[int] | None:
    value = _first(meta.get("shape"), meta.get("proj:shape"))
    if value:
        return list(value)
    height = meta.get("height")
    width = meta.get("width")
    if height and width:
        return [int(height), int(width)]
    return None


def _transform(meta: dict[str, Any]) -> list[float] | None:
    value = _first(meta.get("transform"), meta.get("proj:transform"))
    if value:
        return list(value)
    bounds = meta.get("bounds")
    resolution = meta.get("resolution")
    if bounds and resolution and len(bounds) == 4 and len(resolution) >= 2:
        left, _bottom, _right, top = bounds
        xres, yres = resolution[:2]
        return [xres, 0, left, 0, -abs(yres), top, 0, 0, 1]
    return None


def _as_bbox(value: Any) -> list[float] | None:
    if value is None or value == "":
        return None
    try:
        if len(value) != 4:
            return None
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _is_wgs84_bbox(bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
        and west <= east
        and south <= north
    )


def _positions(coords: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(coords, list | tuple)
        and len(coords) >= 2
        and isinstance(coords[0], int | float)
        and isinstance(coords[1], int | float)
    ):
        yield float(coords[0]), float(coords[1])
        return
    if isinstance(coords, list | tuple):
        for child in coords:
            yield from _positions(child)


def _is_wgs84_geometry(geometry: Any) -> bool:
    if not isinstance(geometry, dict):
        return False
    positions = list(_positions(geometry.get("coordinates")))
    return bool(positions) and all(
        -180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in positions
    )


def _crs_for_transform(crs: Any) -> Any:
    epsg = _epsg(crs)
    return f"EPSG:{epsg}" if epsg is not None else crs


def _bounds_to_wgs84(bounds: Any, crs: Any) -> list[float] | None:
    bbox = _as_bbox(bounds)
    if not bbox:
        return None
    if crs in (None, ""):
        return bbox if _is_wgs84_bbox(bbox) else None
    if _epsg(crs) == 4326:
        return bbox if _is_wgs84_bbox(bbox) else None
    try:
        from rasterio.warp import transform_bounds  # lazy optional import for static validation
    except ModuleNotFoundError as exc:
        raise ValueError(
            "prepare manifest has projected raster bounds but rasterio is unavailable "
            "to transform them to EPSG:4326"
        ) from exc
    west, south, east, north = transform_bounds(
        _crs_for_transform(crs),
        "EPSG:4326",
        *bbox,
        densify_pts=21,
    )
    transformed = [float(west), float(south), float(east), float(north)]
    if not _is_wgs84_bbox(transformed):
        raise ValueError(f"transformed raster bounds are not a valid WGS84 bbox: {transformed}")
    return transformed


def _bbox_from_manifest(manifest: dict[str, Any], analytic_meta: dict[str, Any]) -> list[float]:
    for value in (
        manifest.get("bbox"),
        manifest.get("wgs84_bbox"),
        manifest.get("wgs84_bounds"),
        analytic_meta.get("bbox"),
        analytic_meta.get("wgs84_bbox"),
        analytic_meta.get("wgs84_bounds"),
    ):
        bbox = _as_bbox(value)
        if bbox and _is_wgs84_bbox(bbox):
            return bbox

    props = _properties(manifest)
    transformed = _bounds_to_wgs84(
        _first(analytic_meta.get("bounds"), analytic_meta.get("proj:bbox")),
        _first(
            analytic_meta.get("crs"),
            analytic_meta.get("proj:epsg"),
            manifest.get("crs"),
            manifest.get("proj:epsg"),
            props.get("proj:epsg"),
        ),
    )
    if transformed:
        return transformed
    raise ValueError("prepare manifest is missing WGS84 bbox or transformable raster bounds/crs")


def _geometry_from_bbox(bbox: list[float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def _geometry_from_manifest(
    manifest: dict[str, Any],
    analytic_meta: dict[str, Any],
    bbox: list[float],
) -> dict[str, Any]:
    for geometry in (
        manifest.get("geometry"),
        manifest.get("wgs84_geometry"),
        analytic_meta.get("geometry"),
        analytic_meta.get("wgs84_geometry"),
    ):
        if _is_wgs84_geometry(geometry):
            return geometry
    return _geometry_from_bbox(bbox)


def _raster_bands(meta: dict[str, Any], default_count: int, asset: str) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    dtype = meta.get("dtype") or ("uint8" if asset == "scl" else "uint16")
    nodata = meta.get("nodata", 0)
    resolution = meta.get("resolution") or [10]
    spatial_resolution = resolution[0] if isinstance(resolution, list) and resolution else 10
    count = int(meta.get("band_count") or default_count)
    band = {
        "data_type": dtype,
        "nodata": nodata,
        "spatial_resolution": spatial_resolution,
    }
    if asset == "analytic":
        band.update({"bits_per_sample": 16, "unit": "reflectance", "scale": 0.0001, "offset": -0.1})
    return [dict(band) for _ in range(count)]


def _platform_from_manifest(manifest: dict[str, Any]) -> str | None:
    text = " ".join(str(v) for v in (manifest.get("product_id"), manifest.get("source_zip")) if v)
    if "S2A" in text:
        return "sentinel-2a"
    if "S2B" in text:
        return "sentinel-2b"
    return manifest.get("platform")


def _properties(manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest.get("properties") if isinstance(manifest.get("properties"), dict) else {}


def build_stac_item_from_prepare_manifest(manifest: dict[str, Any]) -> dict:
    """Create a STAC item for one prepared manifest using dynamic object keys."""
    scene = SceneIdentity.from_prepare_manifest(manifest)
    if scene.source_id == config.SENTINEL1_COLLECTION_ID:
        return _build_sentinel1_stac_item(manifest, scene)
    if scene.source_id == config.RESOURCESAT_LISS3_COLLECTION_ID:
        return _build_resourcesat_liss3_stac_item(manifest, scene)
    return _build_sentinel2_stac_item(manifest, scene)


def _build_sentinel2_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    props = _properties(manifest)
    analytic = _output_meta(manifest, "analytic")
    scl = _output_meta(manifest, "scl")
    bbox = _bbox_from_manifest(manifest, analytic)
    geometry = _geometry_from_manifest(manifest, analytic, bbox)
    epsg = _epsg(_first(analytic.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(analytic)
    transform = _transform(analytic)
    proj_bbox = list(_first(analytic.get("proj:bbox"), analytic.get("bounds"), bbox))
    gsd = _first(manifest.get("gsd"), props.get("gsd"), 10)
    cloud_cover = _first(manifest.get("eo:cloud_cover"), props.get("eo:cloud_cover"), 0)

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": _platform_from_manifest(manifest),
        "constellation": "sentinel-2",
        "instruments": ["msi"],
        "gsd": gsd,
        "eo:cloud_cover": cloud_cover,
        "s2:product_level": scene.product_level,
        "s2:mgrs_tile": scene.mgrs_tile,
        "s2:processing_baseline": scene.processing_baseline,
        "akasha:scene_key": scene.scene_key,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:usable_pixel_percent": _first(
            props.get("akasha:usable_pixel_percent"), 100 - float(cloud_cover)
        ),
        "akasha:cloud_masked_percent": _first(
            props.get("akasha:cloud_masked_percent"), cloud_cover
        ),
        "akasha:coverage_percent": _first(props.get("akasha:coverage_percent"), 100.0),
        "akasha:is_latest_usable": _first(props.get("akasha:is_latest_usable"), True),
        "akasha:metrics_provisional": _first(props.get("akasha:metrics_provisional"), True),
    }
    if epsg is not None:
        item_props["proj:epsg"] = epsg
    if shape:
        item_props["proj:shape"] = shape
    if transform:
        item_props["proj:transform"] = transform
    if proj_bbox:
        item_props["proj:bbox"] = proj_bbox
    if manifest.get("created") or props.get("created"):
        item_props["created"] = manifest.get("created") or props.get("created")

    analytic_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.analytic_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Analytic reflectance COG (raw uint16 DN, frozen 9-band order)",
        "roles": ["data", "reflectance"],
        "gsd": gsd,
        "eo:bands": manifest.get("eo_bands") or analytic.get("eo:bands") or ANALYTIC_EO_BANDS,
        "raster:bands": _raster_bands(analytic, 9, "analytic"),
    }
    scl_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.scl_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Scene Classification Layer COG (categorical, nearest resampling)",
        "roles": ["metadata", "data-mask"],
        "gsd": gsd,
        "raster:bands": _raster_bands(scl, 1, "scl"),
        "classification:classes": (
            manifest.get("classification_classes")
            or scl.get("classification:classes")
            or SCL_CLASSES
        ),
    }
    for asset in (analytic_asset, scl_asset):
        if epsg is not None:
            asset["proj:epsg"] = epsg
        if shape:
            asset["proj:shape"] = shape
        if transform:
            asset["proj:transform"] = transform
        if proj_bbox:
            asset["proj:bbox"] = proj_bbox

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": STAC_EXTENSIONS,
        "id": scene.item_id,
        "collection": scene.source_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": item_props,
        "assets": {"analytic": analytic_asset, "scl": scl_asset},
        "links": [
            {
                "rel": "collection",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
        ],
    }


def _resourcesat_raster_bands(
    meta: dict[str, Any],
    default_count: int,
    asset: str,
) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    resolution = meta.get("resolution") or [24]
    spatial_resolution = resolution[0] if isinstance(resolution, list) and resolution else 24
    if asset == "analytic":
        return [
            {
                "data_type": meta.get("dtype") or "uint16",
                "nodata": meta.get("nodata", 0),
                "bits_per_sample": 16,
                "unit": "reflectance",
                "scale": 0.0001,
                "offset": 0,
                "spatial_resolution": spatial_resolution,
            }
            for _ in range(int(meta.get("band_count") or default_count))
        ]
    return [
        {
            "data_type": meta.get("dtype") or "uint8",
            "nodata": meta.get("nodata", 0),
            "spatial_resolution": spatial_resolution,
        }
        for _ in range(int(meta.get("band_count") or default_count))
    ]


def _build_resourcesat_liss3_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    props = _properties(manifest)
    analytic = _output_meta(manifest, "analytic")
    mask = _output_meta(manifest, "mask")
    bbox = _bbox_from_manifest(manifest, analytic)
    geometry = _geometry_from_manifest(manifest, analytic, bbox)
    epsg = _epsg(_first(analytic.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(analytic)
    transform = _transform(analytic)
    proj_bbox = list(_first(analytic.get("proj:bbox"), analytic.get("bounds"), bbox))
    gsd = _first(manifest.get("gsd"), props.get("gsd"), analytic.get("gsd"), 24)
    cloud_cover = _first(manifest.get("eo:cloud_cover"), props.get("eo:cloud_cover"))

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform or "resourcesat-2a",
        "constellation": "resourcesat",
        "instruments": ["liss-3"],
        "gsd": gsd,
        "product:type": scene.product_type or "BOA",
        "akasha:scene_key": scene.scene_key,
        "akasha:source_id": scene.source_id,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:scene_component": scene.scene_component,
        "akasha:product_id_hash": scene.product_id_hash,
        "akasha:path": scene.path_or_unknown,
        "akasha:row": scene.row_or_unknown,
        "akasha:band_role_mapping": dict(RESOURCESAT_BAND_ROLE_MAPPING),
        "akasha:mask_asset": "mask",
        "akasha:mask_method": RESOURCESAT_MASK_METHOD,
        "akasha:date_metrics_kind": "optical",
        "akasha:usable_pixel_percent": _first(
            props.get("akasha:usable_pixel_percent"),
            100 - float(cloud_cover) if cloud_cover is not None else None,
        ),
        "akasha:cloud_masked_percent": _first(
            props.get("akasha:cloud_masked_percent"),
            cloud_cover,
        ),
        "akasha:coverage_percent": _first(props.get("akasha:coverage_percent"), 100.0),
        "akasha:is_latest_usable": _first(props.get("akasha:is_latest_usable"), True),
        "akasha:metrics_provisional": _first(props.get("akasha:metrics_provisional"), True),
    }
    if cloud_cover is not None:
        item_props["eo:cloud_cover"] = cloud_cover
    if epsg is not None:
        item_props["proj:epsg"] = epsg
    if shape:
        item_props["proj:shape"] = shape
    if transform:
        item_props["proj:transform"] = transform
    if proj_bbox:
        item_props["proj:bbox"] = proj_bbox
    if manifest.get("created") or props.get("created"):
        item_props["created"] = manifest.get("created") or props.get("created")
    item_props = {key: value for key, value in item_props.items() if value is not None}

    analytic_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.analytic_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "ResourceSat-2A LISS-3 BOA analytic COG (BAND2/BAND3/BAND4/BAND5)",
        "roles": ["data", "reflectance"],
        "gsd": gsd,
        "eo:bands": (
            manifest.get("eo_bands")
            or analytic.get("eo:bands")
            or RESOURCESAT_LISS3_EO_BANDS
        ),
        "raster:bands": _resourcesat_raster_bands(analytic, 4, "analytic"),
    }
    mask_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.mask_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Akasha-generated provisional ResourceSat mask COG",
        "roles": ["metadata", "data-mask"],
        "gsd": gsd,
        "raster:bands": _resourcesat_raster_bands(mask, 1, "mask"),
        "classification:classes": (
            manifest.get("classification_classes")
            or mask.get("classification:classes")
            or RESOURCESAT_MASK_CLASSES
        ),
    }
    for asset in (analytic_asset, mask_asset):
        if epsg is not None:
            asset["proj:epsg"] = epsg
        if shape:
            asset["proj:shape"] = shape
        if transform:
            asset["proj:transform"] = transform
        if proj_bbox:
            asset["proj:bbox"] = proj_bbox

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": STAC_EXTENSIONS,
        "id": scene.item_id,
        "collection": scene.source_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": item_props,
        "assets": {"analytic": analytic_asset, "mask": mask_asset},
        "links": [
            {
                "rel": "collection",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
        ],
    }


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list | tuple):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _sentinel1_polarizations(manifest: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    props = _properties(manifest)
    value = _first(
        manifest.get("sar:polarizations"),
        manifest.get("polarizations"),
        props.get("sar:polarizations"),
        meta.get("sar:polarizations"),
        meta.get("polarizations"),
    )
    polarizations = [str(pol).upper() for pol in _as_list(value)]
    return polarizations or ["VV"]


def _backscatter_raster_bands(
    meta: dict[str, Any],
    polarizations: list[str],
) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    resolution = meta.get("resolution") or [10]
    spatial_resolution = resolution[0] if isinstance(resolution, list) and resolution else 10
    nodata = meta.get("nodata")
    bands: list[dict[str, Any]] = []
    for pol in polarizations:
        band = {
            "data_type": meta.get("dtype") or "float32",
            "spatial_resolution": spatial_resolution,
            "unit": "dB",
            "name": f"{pol}_dB",
        }
        if nodata is not None:
            band["nodata"] = nodata
        bands.append(band)
    return bands


def _build_sentinel1_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    props = _properties(manifest)
    backscatter = _output_meta(manifest, "backscatter")
    bbox = _bbox_from_manifest(manifest, backscatter)
    geometry = _geometry_from_manifest(manifest, backscatter, bbox)
    epsg = _epsg(_first(backscatter.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(backscatter)
    transform = _transform(backscatter)
    proj_bbox = list(_first(backscatter.get("proj:bbox"), backscatter.get("bounds"), bbox))
    gsd = _first(manifest.get("gsd"), props.get("gsd"), backscatter.get("gsd"), 10)
    polarizations = _sentinel1_polarizations(manifest, backscatter)

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform,
        "constellation": "sentinel-1",
        "instruments": ["c-sar"],
        "gsd": gsd,
        "sar:instrument_mode": scene.instrument_mode,
        "sar:frequency_band": _first(props.get("sar:frequency_band"), "C"),
        "sar:polarizations": polarizations,
        "sar:product_type": scene.product_type,
        "product:type": scene.product_type,
        "sat:orbit_state": None if scene.orbit_state_or_unknown == "unknown" else scene.orbit_state,
        "akasha:scene_key": scene.scene_key,
        "akasha:source_id": scene.source_id,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:scene_component": scene.scene_component,
        "akasha:product_id_hash": scene.product_id_hash,
        "akasha:date_metrics_kind": "radar",
        "akasha:metrics_provisional": _first(props.get("akasha:metrics_provisional"), True),
    }
    if scene.relative_orbit not in (None, ""):
        item_props["sat:relative_orbit"] = (
            int(scene.relative_orbit)
            if str(scene.relative_orbit).isdigit()
            else scene.relative_orbit
        )
    if props.get("sat:absolute_orbit") not in (None, ""):
        item_props["sat:absolute_orbit"] = props.get("sat:absolute_orbit")
    if epsg is not None:
        item_props["proj:epsg"] = epsg
    if shape:
        item_props["proj:shape"] = shape
    if transform:
        item_props["proj:transform"] = transform
    if proj_bbox:
        item_props["proj:bbox"] = proj_bbox
    if manifest.get("created") or props.get("created"):
        item_props["created"] = manifest.get("created") or props.get("created")
    item_props = {key: value for key, value in item_props.items() if value is not None}

    backscatter_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.backscatter_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Calibrated terrain-corrected SAR backscatter COG (dB)",
        "roles": ["data", "backscatter"],
        "gsd": gsd,
        "sar:polarizations": polarizations,
        "raster:bands": _backscatter_raster_bands(backscatter, polarizations),
    }
    if epsg is not None:
        backscatter_asset["proj:epsg"] = epsg
    if shape:
        backscatter_asset["proj:shape"] = shape
    if transform:
        backscatter_asset["proj:transform"] = transform
    if proj_bbox:
        backscatter_asset["proj:bbox"] = proj_bbox

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": SENTINEL1_STAC_EXTENSIONS,
        "id": scene.item_id,
        "collection": scene.source_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": item_props,
        "assets": {"backscatter": backscatter_asset},
        "links": [
            {
                "rel": "collection",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": f"./{scene.source_id}-collection.json",
                "type": "application/json",
            },
        ],
    }


def build_stac_items_from_prepare_manifests(manifest_paths: list[Path]) -> list[dict]:
    return [
        build_stac_item_from_prepare_manifest(_read_manifest(Path(path)))
        for path in manifest_paths
    ]


def load_manifest_items(manifest_paths: list[Path], method: str = "upsert") -> str:
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.load import Loader, Methods  # lazy

    items = build_stac_items_from_prepare_manifests(manifest_paths)
    ndjson = _write_ndjson(items)
    try:
        with PgstacDB(dsn=_require_dsn()) as db:
            Loader(db=db).load_items(str(ndjson), insert_mode=Methods(method))
    finally:
        ndjson.unlink(missing_ok=True)
    return f"loaded {len(items)} manifest item(s) (method={method})"


# Compatibility alias for plan wording.
load_items_from_manifests = load_manifest_items
