"""Index-statistics orchestration (Slice 2 — Phase 2).

Glues catalog resolution + geometry validation + the rasterio window reader +
the pure-numpy statistics engine into one normalized response. This is the only
place that wires the pieces together; each piece stays independently testable.
"""
from __future__ import annotations

from typing import Any

from . import catalog_resolver as catalog
from .errors import bad_request, invalid_geometry
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
            f"Unsupported index '{index_type}'. Supported: {supported}.",
            code="UNSUPPORTED_INDEX",
            indexType=index_type,
            supported=supported,
        )
    index_def = get_index(index_type)

    # Validate geometry early (422/413/400 before any raster I/O).
    geom_facts = validate_polygon(
        geometry, max_area_ha=max_area_ha, max_vertices=max_vertices
    )

    # Resolve the scene/date assets (latest usable if no date supplied).
    if not acquisition_date:
        acquisition_date = catalog.latest_item(source_id)["properties"]["akasha:acquisition_date"]
    assets = catalog.resolve_assets(source_id, acquisition_date)

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
    pos_a = name_to_pos[index_def.band_a]
    pos_b = name_to_pos[index_def.band_b]

    read = read_index_windows(
        analytic_href=assets["analyticHref"],
        scl_href=assets["sclHref"],
        geometry=geometry,
        positions=[pos_a, pos_b],
    )
    if not read.intersects:
        raise invalid_geometry(
            "Geometry does not intersect the scene footprint for this source/date.",
            sourceId=source_id,
            acquisitionDate=acquisition_date,
        )

    excluded = excluded_scl_classes
    if excluded is None:
        from .indices import DEFAULT_EXCLUDED_SCL_CLASSES

        excluded = DEFAULT_EXCLUDED_SCL_CLASSES

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
