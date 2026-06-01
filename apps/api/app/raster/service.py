"""Index-statistics orchestration (Slice 2 — Phase 2).

Glues catalog resolution + geometry validation + the rasterio window reader +
the pure-numpy statistics engine into one normalized response. This is the only
place that wires the pieces together; each piece stays independently testable.
"""
from __future__ import annotations

from typing import Any

from . import catalog_resolver as catalog
from .errors import bad_request, invalid_geometry, multi_scene_statistics_unavailable
from .geo_validate import validate_polygon
from .indices import band_name_to_position, get_index
from .raster_reader import read_index_windows
from .statistics_core import compute_index_statistics


def compute_statistics(
    *,
    geometry: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
    max_area_ha: float | None = None,
    max_vertices: int | None = None,
    excluded_scl_classes: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """Compute masked, offset-corrected index statistics for a polygon.

    Raises AkashaError for unsupported index/source/date, invalid/oversized
    geometry, geometries outside the scene footprint, or an unavailable raster
    backend.
    """
    index_type = (index_type or "").upper()
    supported = catalog.supported_indices(source_id)
    if index_type not in supported:
        raise bad_request(
            f"Unsupported index '{index_type}' for source '{source_id}'.",
            code="UNSUPPORTED_INDEX",
            sourceId=source_id,
            indexType=index_type,
            supported=supported,
        )
    index_def = get_index(index_type)

    # Validate geometry early (422/413/400 before any raster I/O).
    geom_facts = validate_polygon(
        geometry, max_area_ha=max_area_ha, max_vertices=max_vertices
    )

    # Resolve all scene/date assets (latest usable date if no date supplied).
    if not acquisition_date:
        acquisition_date = catalog.latest_item(source_id)["properties"][
            "akasha:acquisition_date"
        ]
    assets_for_date = catalog.resolve_assets_for_date(source_id, acquisition_date)
    candidate_assets = _candidate_assets_for_geometry(
        assets_for_date=assets_for_date,
        geometry_bounds=geom_facts.get("bounds"),
    )
    if not candidate_assets:
        raise invalid_geometry(
            "Geometry does not intersect any scene footprint for this source/date.",
            sourceId=source_id,
            acquisitionDate=acquisition_date,
        )

    excluded = excluded_scl_classes
    if excluded is None:
        from .indices import DEFAULT_EXCLUDED_SCL_CLASSES

        excluded = DEFAULT_EXCLUDED_SCL_CLASSES

    intersecting_results: list[tuple[dict[str, Any], Any, int, int]] = []
    for assets in candidate_assets:
        pos_a, pos_b = _index_band_positions(assets, index_def, index_type)
        read = read_index_windows(
            analytic_href=assets["analyticHref"],
            scl_href=assets["sclHref"],
            geometry=geometry,
            positions=[pos_a, pos_b],
        )
        if read.intersects:
            intersecting_results.append((assets, read, pos_a, pos_b))

    if not intersecting_results:
        raise invalid_geometry(
            "Geometry does not intersect the scene footprint for this source/date.",
            sourceId=source_id,
            acquisitionDate=acquisition_date,
        )

    if len(intersecting_results) > 1:
        raise multi_scene_statistics_unavailable(
            "Index statistics for polygons intersecting multiple same-date scenes "
            "require a configured mosaic statistics backend.",
            sceneCount=len(assets_for_date),
            intersectingSceneCount=len(intersecting_results),
            supportedSceneCount=1,
        )

    assets, read, pos_a, pos_b = intersecting_results[0]

    stats = compute_index_statistics(
        index_type=index_type,
        band_a_dn=read.band_arrays[pos_a],
        band_b_dn=read.band_arrays[pos_b],
        scl=read.scl,
        geometry_mask=read.geometry_mask,
        scale=assets["scale"],
        offset=assets["offset"],
        nodata=read.nodata,
        excluded_scl_classes=tuple(excluded),
    )

    return build_response(
        stats=stats.as_dict(),
        index_def=index_def,
        source_id=source_id,
        acquisition_date=acquisition_date,
        assets=assets,
        geom_facts=geom_facts,
        excluded=tuple(excluded),
    )


def _index_band_positions(
    assets: dict[str, Any],
    index_def: Any,
    index_type: str,
) -> tuple[int, int]:
    band_names: list[str] = assets["bandNames"]
    name_to_pos = band_name_to_position(band_names)
    for band in index_def.required_bands:
        if band not in name_to_pos:
            raise bad_request(
                f"Band '{band}' required by {index_type} is not present in the analytic asset.",
                code="BAND_NOT_AVAILABLE",
                band=band,
                available=band_names,
            )
    return name_to_pos[index_def.band_a], name_to_pos[index_def.band_b]


def _candidate_assets_for_geometry(
    *,
    assets_for_date: list[dict[str, Any]],
    geometry_bounds: list[float] | tuple[float, float, float, float] | None,
) -> list[dict[str, Any]]:
    if len(assets_for_date) <= 1 or not geometry_bounds:
        return assets_for_date

    candidates = [
        assets
        for assets in assets_for_date
        if _bbox_intersects_geometry(assets.get("bbox"), geometry_bounds)
    ]
    return candidates


def _bbox_intersects_geometry(
    bbox: Any,
    geometry_bounds: list[float] | tuple[float, float, float, float],
) -> bool:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return True
    try:
        minx, miny, maxx, maxy = (float(value) for value in bbox)
        geom_minx, geom_miny, geom_maxx, geom_maxy = (
            float(value) for value in geometry_bounds
        )
    except (TypeError, ValueError):
        return True
    return not (
        maxx < geom_minx
        or geom_maxx < minx
        or maxy < geom_miny
        or geom_maxy < miny
    )


def build_response(
    *,
    stats: dict[str, Any],
    index_def: Any,
    source_id: str,
    acquisition_date: str,
    assets: dict[str, Any],
    geom_facts: dict[str, Any],
    excluded: tuple[int, ...],
) -> dict[str, Any]:
    """Assemble the normalized statistics response (architecture contract shape)."""
    return {
        "indexType": stats["indexType"],
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "statistics": {
            "min": stats["min"],
            "max": stats["max"],
            "mean": stats["mean"],
            "stddev": stats["stddev"],
            "validPixelPercent": stats["validPixelPercent"],
            "cloudMaskedPercent": stats["cloudMaskedPercent"],
            "coveragePercent": stats["coveragePercent"],
        },
        "pixelCounts": {
            "totalPixels": stats["totalPixels"],
            "nodataPixels": stats["nodataPixels"],
            "coveragePixels": stats["coveragePixels"],
            "sclExcludedPixels": stats["sclExcludedPixels"],
            "validPixels": stats["validPixels"],
        },
        "metadata": {
            "formula": index_def.formula,
            "bands": list(index_def.required_bands),
            "cloudMask": f"SCL classes excluded: {list(excluded)}",
            "reflectanceCorrection": (
                f"corrected = dn * {assets['scale']} + ({assets['offset']})"
            ),
            "itemId": assets.get("itemId"),
            "areaHa": geom_facts.get("areaHa"),
            "vertices": geom_facts.get("vertices"),
            "warnings": stats.get("warnings", []),
        },
    }
