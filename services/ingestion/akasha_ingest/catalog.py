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
CONTEXT_STAC_EXTENSIONS = [
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

RESOURCESAT_LISS4_EO_BANDS = [
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
]

RESOURCESAT_MASK_CLASSES = [
    {"value": 0, "name": "nodata", "description": "No data / outside scene", "nodata": True},
    {"value": 1, "name": "valid", "description": "Valid clear land or water pixel"},
    {"value": 2, "name": "cloud", "description": "Akasha threshold-derived cloud"},
    {"value": 3, "name": "cloud_shadow", "description": "Akasha threshold-derived shadow"},
    {"value": 4, "name": "water", "description": "Akasha threshold-derived water"},
]

RESOURCESAT_BAND_ROLE_MAPPING = {
    "GREEN": "BAND2",
    "RED": "BAND3",
    "NIR": "BAND4",
    "SWIR1": "BAND5",
}
RESOURCESAT_BAND_ROLE_MAPPING_BY_SOURCE = {
    config.RESOURCESAT_LISS3_COLLECTION_ID: RESOURCESAT_BAND_ROLE_MAPPING,
    config.RESOURCESAT_LISS4_COLLECTION_ID: {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
    },
    config.RESOURCESAT_AWIFS_COLLECTION_ID: RESOURCESAT_BAND_ROLE_MAPPING,
}
RESOURCESAT_EO_BANDS_BY_SOURCE = {
    config.RESOURCESAT_LISS3_COLLECTION_ID: RESOURCESAT_LISS3_EO_BANDS,
    config.RESOURCESAT_LISS4_COLLECTION_ID: RESOURCESAT_LISS4_EO_BANDS,
    config.RESOURCESAT_AWIFS_COLLECTION_ID: RESOURCESAT_LISS3_EO_BANDS,
}

RESOURCESAT_MASK_METHOD = (
    "Akasha threshold mask v1 (no native quality layer found in validated "
    "ResourceSat BOA sample; provisional)."
)
RESOURCESAT_MASK_METHOD_BY_SOURCE = {
    config.RESOURCESAT_LISS3_COLLECTION_ID: (
        "Akasha threshold mask v1 (no native quality layer found in validated "
        "LISS-3 BOA sample; provisional)."
    ),
    config.RESOURCESAT_AWIFS_COLLECTION_ID: (
        "Akasha threshold mask v1 for ResourceSat-2A AWiFS BOA "
        "(pending AWiFS-specific native quality-layer validation; provisional)."
    ),
    config.RESOURCESAT_LISS4_COLLECTION_ID: (
        "Akasha threshold mask v1 (LISS-4, no SWIR; provisional)."
    ),
}

RESOURCESAT_BOA_SOURCE_META = {
    config.RESOURCESAT_LISS3_COLLECTION_ID: {
        "instrument": "liss-3",
        "label": "LISS-3",
        "default_gsd": 24,
    },
    config.RESOURCESAT_AWIFS_COLLECTION_ID: {
        "instrument": "awifs",
        "label": "AWiFS",
        "default_gsd": 56,
    },
    config.RESOURCESAT_LISS4_COLLECTION_ID: {
        "instrument": "liss-4",
        "label": "LISS-4",
        "default_gsd": 5.8,
    },
}

SAR_SOURCE_META = {
    config.SENTINEL1_COLLECTION_ID: {
        "constellation": "sentinel-1",
        "instruments": ["c-sar"],
        "frequency_band": "C",
        "default_gsd": 10,
        "title": "Calibrated terrain-corrected SAR backscatter COG (dB)",
    },
    config.EOS04_SAR_COLLECTION_ID: {
        "constellation": "eos-04",
        "instruments": ["sar"],
        "frequency_band": "C",
        "default_gsd": None,
        "title": "EOS-04 SAR backscatter COG (dB)",
    },
    config.NISAR_GCOV_COLLECTION_ID: {
        "constellation": "nisar",
        "instruments": ["s-sar"],
        "frequency_band": "S",
        "default_gsd": None,
        "title": "NISAR S-SAR GCOV backscatter COG (dB)",
    },
}

CONTEXT_SOURCE_META = {
    config.CARTOSAT3_CONTEXT_COLLECTION_ID: {
        "constellation": "cartosat",
        "instruments": ["optical"],
        "default_gsd": None,
        "title": "Operator-provided visual context COG",
        "platform": "cartosat-3",
        "asset_key": "visual",
        "asset_roles": ["data", "visual"],
    },
    config.EOS06_CONTEXT_COLLECTION_ID: {
        "constellation": "eos-06",
        "instruments": ["ocm"],
        "default_gsd": 360,
        "title": "EOS-06 OCM-LAC precomputed NDVI context COG",
        "platform": "eos-06",
        "asset_key": "ndvi",
        "asset_roles": ["data", "index", "ndvi"],
    },
}


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
    if scene.source_id in config.SAR_COLLECTION_IDS:
        return _build_sar_stac_item(manifest, scene)
    if scene.source_id in config.CONTEXT_COLLECTION_IDS:
        return _build_context_stac_item(manifest, scene)
    if scene.source_id in config.ARCHIVE_COLLECTION_IDS:
        return _build_archive_stac_item(manifest, scene)
    if scene.source_id in config.RESOURCESAT_BOA_COLLECTION_IDS:
        return _build_resourcesat_boa_stac_item(manifest, scene)
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
    default_spatial_resolution: float = 24,
) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    resolution = meta.get("resolution") or [default_spatial_resolution]
    spatial_resolution = (
        resolution[0] if isinstance(resolution, list) and resolution else default_spatial_resolution
    )
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


def _build_resourcesat_boa_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    source_meta = RESOURCESAT_BOA_SOURCE_META.get(
        scene.source_id,
        {"instrument": "unknown", "label": "BOA", "default_gsd": 24},
    )
    props = _properties(manifest)
    analytic = _output_meta(manifest, "analytic")
    mask = _output_meta(manifest, "mask")
    bbox = _bbox_from_manifest(manifest, analytic)
    geometry = _geometry_from_manifest(manifest, analytic, bbox)
    epsg = _epsg(_first(analytic.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(analytic)
    transform = _transform(analytic)
    proj_bbox = list(_first(analytic.get("proj:bbox"), analytic.get("bounds"), bbox))
    gsd = _first(
        manifest.get("gsd"),
        props.get("gsd"),
        analytic.get("gsd"),
        source_meta["default_gsd"],
    )
    cloud_cover = _first(manifest.get("eo:cloud_cover"), props.get("eo:cloud_cover"))
    mask_method = _first(
        manifest.get("mask_method"),
        manifest.get("akasha:mask_method"),
        props.get("akasha:mask_method"),
        RESOURCESAT_MASK_METHOD_BY_SOURCE.get(scene.source_id, RESOURCESAT_MASK_METHOD),
    )
    source_band_role_mapping = RESOURCESAT_BAND_ROLE_MAPPING_BY_SOURCE.get(
        scene.source_id, RESOURCESAT_BAND_ROLE_MAPPING
    )
    band_role_mapping = dict(
        _first(
            manifest.get("band_role_mapping"),
            props.get("akasha:band_role_mapping"),
            source_band_role_mapping,
        )
    )
    eo_bands = RESOURCESAT_EO_BANDS_BY_SOURCE.get(
        scene.source_id, RESOURCESAT_LISS3_EO_BANDS
    )

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform or "resourcesat-2a",
        "constellation": "resourcesat",
        "instruments": [source_meta["instrument"]],
        "gsd": gsd,
        "product:type": scene.product_type or "BOA",
        "akasha:scene_key": scene.scene_key,
        "akasha:source_id": scene.source_id,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:scene_component": None if scene.composite else scene.scene_component,
        "akasha:product_id_hash": scene.product_id_hash,
        "akasha:path": None if scene.composite else scene.path_or_unknown,
        "akasha:row": None if scene.composite else scene.row_or_unknown,
        "akasha:composite": True if scene.composite else None,
        "akasha:aoi_id": scene.aoi_id if scene.composite else None,
        "akasha:composite_grid_crs": _first(
            manifest.get("composite_grid_crs"),
            props.get("akasha:composite_grid_crs"),
        ),
        "akasha:composite_resolution_meters": _first(
            manifest.get("composite_resolution_meters"),
            props.get("akasha:composite_resolution_meters"),
        ),
        "akasha:composite_grid_bounds": _first(
            manifest.get("composite_grid_bounds"),
            props.get("akasha:composite_grid_bounds"),
        ),
        "akasha:composite_grid_dimensions": _first(
            manifest.get("composite_grid_dimensions"),
            props.get("akasha:composite_grid_dimensions"),
        ),
        "akasha:period_start": _first(
            manifest.get("period_start"),
            manifest.get("window_start"),
            props.get("akasha:period_start"),
        ),
        "akasha:period_end": _first(
            manifest.get("period_end"),
            manifest.get("window_end"),
            props.get("akasha:period_end"),
        ),
        "akasha:contributing_scenes": _first(
            manifest.get("contributing_scenes"),
            props.get("akasha:contributing_scenes"),
        ),
        "akasha:band_role_mapping": band_role_mapping,
        "akasha:mask_asset": "mask",
        "akasha:mask_method": mask_method,
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
        "title": (
            f"ResourceSat-2A {source_meta['label']} BOA analytic COG "
            f"({('/'.join(band['name'] for band in eo_bands))})"
        ),
        "roles": ["data", "reflectance"],
        "gsd": gsd,
        "eo:bands": (
            manifest.get("eo_bands") or analytic.get("eo:bands") or eo_bands
        ),
        "raster:bands": _resourcesat_raster_bands(
            analytic,
            len(eo_bands),
            "analytic",
            default_spatial_resolution=float(gsd),
        ),
    }
    mask_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.mask_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Akasha-generated provisional ResourceSat mask COG",
        "roles": ["metadata", "data-mask"],
        "gsd": gsd,
        "raster:bands": _resourcesat_raster_bands(
            mask,
            1,
            "mask",
            default_spatial_resolution=float(gsd),
        ),
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


def _sar_polarizations(manifest: dict[str, Any], meta: dict[str, Any]) -> list[str]:
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


def _visual_raster_bands(meta: dict[str, Any]) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    resolution = meta.get("resolution") or []
    spatial_resolution = resolution[0] if isinstance(resolution, list) and resolution else None
    count = int(meta.get("band_count") or 3)
    nodata = meta.get("nodata")
    names = _as_list(meta.get("descriptions") or meta.get("band_names"))
    bands: list[dict[str, Any]] = []
    for index in range(count):
        band: dict[str, Any] = {
            "data_type": meta.get("dtype") or "uint16",
        }
        if index < len(names):
            band["name"] = str(names[index])
        if nodata is not None:
            band["nodata"] = nodata
        if spatial_resolution is not None:
            band["spatial_resolution"] = spatial_resolution
        bands.append(band)
    return bands


def _build_context_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    source_meta = CONTEXT_SOURCE_META.get(
        scene.source_id,
        {
            "constellation": scene.source_id,
            "instruments": ["optical"],
            "default_gsd": None,
            "title": "Visual context COG",
            "platform": scene.source_id,
            "asset_key": "visual",
            "asset_roles": ["data", "visual"],
        },
    )
    props = _properties(manifest)
    asset_key = str(source_meta.get("asset_key") or scene.context_asset_key)
    asset_meta = _output_meta(manifest, asset_key)
    bbox = _bbox_from_manifest(manifest, asset_meta)
    geometry = _geometry_from_manifest(manifest, asset_meta, bbox)
    epsg = _epsg(_first(asset_meta.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(asset_meta)
    transform = _transform(asset_meta)
    proj_bbox = list(_first(asset_meta.get("proj:bbox"), asset_meta.get("bounds"), bbox))
    gsd = _first(
        manifest.get("gsd"),
        props.get("gsd"),
        asset_meta.get("gsd"),
        source_meta["default_gsd"],
    )

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform or source_meta["platform"],
        "constellation": source_meta["constellation"],
        "instruments": _first(props.get("instruments"), source_meta["instruments"]),
        "gsd": gsd,
        "product:type": scene.product_type,
        "akasha:scene_key": scene.scene_key,
        "akasha:source_id": scene.source_id,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:scene_component": scene.scene_component,
        "akasha:product_id_hash": scene.product_id_hash,
        "akasha:date_metrics_kind": "context",
        "akasha:crop_indices_enabled": False,
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
    item_props = {key: value for key, value in item_props.items() if value is not None}

    context_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.context_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": source_meta["title"],
        "roles": list(source_meta.get("asset_roles") or ["data", asset_key]),
        "raster:bands": _visual_raster_bands(asset_meta),
    }
    if gsd is not None:
        context_asset["gsd"] = gsd
    if epsg is not None:
        context_asset["proj:epsg"] = epsg
    if shape:
        context_asset["proj:shape"] = shape
    if transform:
        context_asset["proj:transform"] = transform
    if proj_bbox:
        context_asset["proj:bbox"] = proj_bbox

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": CONTEXT_STAC_EXTENSIONS,
        "id": scene.item_id,
        "collection": scene.source_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": item_props,
        "assets": {asset_key: context_asset},
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


def _archive_raster_bands(
    meta: dict[str, Any],
    default_count: int,
    asset: str,
) -> list[dict[str, Any]]:
    existing = _first(meta.get("raster:bands"), meta.get("raster_bands"))
    if existing:
        return list(existing)
    resolution = meta.get("resolution") or []
    spatial_resolution = resolution[0] if isinstance(resolution, list) and resolution else None
    count = int(meta.get("band_count") or default_count)
    nodata = meta.get("nodata", 0)
    dtype = meta.get("dtype") or ("uint8" if asset == "mask" else "uint16")
    bands: list[dict[str, Any]] = []
    for _index in range(count):
        band: dict[str, Any] = {
            "data_type": dtype,
            "nodata": nodata,
        }
        if spatial_resolution is not None:
            band["spatial_resolution"] = spatial_resolution
        if asset == "analytic":
            band["unit"] = meta.get("unit") or "reflectance"
            if "scale" in meta:
                band["scale"] = meta["scale"]
            if "offset" in meta:
                band["offset"] = meta["offset"]
        bands.append(band)
    return bands


def _build_archive_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    props = _properties(manifest)
    analytic = _output_meta(manifest, "analytic")
    mask = _output_meta(manifest, "mask")
    bbox = _bbox_from_manifest(manifest, analytic)
    geometry = _geometry_from_manifest(manifest, analytic, bbox)
    epsg = _epsg(_first(analytic.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(analytic)
    transform = _transform(analytic)
    proj_bbox = list(_first(analytic.get("proj:bbox"), analytic.get("bounds"), bbox))
    gsd = _first(manifest.get("gsd"), props.get("gsd"), analytic.get("gsd"))
    band_role_mapping = _first(
        manifest.get("band_role_mapping"),
        manifest.get("akasha:band_role_mapping"),
        props.get("akasha:band_role_mapping"),
    )

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform or "irs-1c",
        "constellation": _first(props.get("constellation"), "irs"),
        "instruments": _first(props.get("instruments"), ["liss-3"]),
        "gsd": gsd,
        "product:type": scene.product_type or "archive",
        "akasha:scene_key": scene.scene_key,
        "akasha:source_id": scene.source_id,
        "akasha:acquisition_date": scene.acquisition_date,
        "akasha:scene_component": scene.scene_component,
        "akasha:product_id_hash": scene.product_id_hash,
        "akasha:date_metrics_kind": "archive",
        "akasha:crop_indices_enabled": False,
        "akasha:band_role_mapping": band_role_mapping,
        "akasha:mask_asset": "mask",
        "akasha:mask_method": _first(
            manifest.get("mask_method"),
            manifest.get("akasha:mask_method"),
            props.get("akasha:mask_method"),
            "Pending archive mask validation.",
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
    item_props = {key: value for key, value in item_props.items() if value is not None}

    analytic_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.analytic_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "IRS-1C LISS-3 archive analytic COG",
        "roles": ["data", "reflectance", "archive"],
        "eo:bands": manifest.get("eo_bands") or analytic.get("eo:bands") or [],
        "raster:bands": _archive_raster_bands(analytic, 4, "analytic"),
    }
    mask_asset: dict[str, Any] = {
        "href": f"s3://{config.BUCKET}/{scene.mask_key}",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": "Archive validity mask COG",
        "roles": ["metadata", "data-mask", "archive"],
        "raster:bands": _archive_raster_bands(mask, 1, "mask"),
        "classification:classes": (
            manifest.get("classification_classes") or mask.get("classification:classes") or []
        ),
    }
    if gsd is not None:
        analytic_asset["gsd"] = gsd
        mask_asset["gsd"] = gsd
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


def _build_sar_stac_item(manifest: dict[str, Any], scene: SceneIdentity) -> dict:
    source_meta = SAR_SOURCE_META.get(
        scene.source_id,
        {
            "constellation": scene.source_id,
            "instruments": ["sar"],
            "frequency_band": "unknown",
            "default_gsd": None,
            "title": "SAR backscatter COG (dB)",
        },
    )
    props = _properties(manifest)
    backscatter = _output_meta(manifest, "backscatter")
    bbox = _bbox_from_manifest(manifest, backscatter)
    geometry = _geometry_from_manifest(manifest, backscatter, bbox)
    epsg = _epsg(_first(backscatter.get("crs"), manifest.get("crs"), props.get("proj:epsg")))
    shape = _shape(backscatter)
    transform = _transform(backscatter)
    proj_bbox = list(_first(backscatter.get("proj:bbox"), backscatter.get("bounds"), bbox))
    gsd = _first(
        manifest.get("gsd"),
        props.get("gsd"),
        backscatter.get("gsd"),
        source_meta["default_gsd"],
    )
    polarizations = _sar_polarizations(manifest, backscatter)

    item_props: dict[str, Any] = {
        "datetime": scene.acquisition_datetime,
        "platform": scene.platform,
        "constellation": source_meta["constellation"],
        "instruments": _first(props.get("instruments"), source_meta["instruments"]),
        "gsd": gsd,
        "sar:instrument_mode": scene.instrument_mode,
        "sar:frequency_band": _first(
            props.get("sar:frequency_band"),
            source_meta["frequency_band"],
        ),
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
        "title": source_meta["title"],
        "roles": ["data", "backscatter"],
        "sar:polarizations": polarizations,
        "raster:bands": _backscatter_raster_bands(backscatter, polarizations),
    }
    if gsd is not None:
        backscatter_asset["gsd"] = gsd
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
        build_stac_item_from_prepare_manifest(_read_manifest(Path(path))) for path in manifest_paths
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
