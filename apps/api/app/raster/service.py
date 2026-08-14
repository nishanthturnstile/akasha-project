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
from .indices import get_index, index_band_positions
from .raster_reader import read_index_windows
from .sar_support import compute_sar_support
from .statistics_core import compute_index_statistics


def compute_statistics(
    *,
    geometry: dict[str, Any],
    source_id: str,
    acquisition_date: str | None,
    index_type: str,
    max_area_ha: float | None = None,
    max_vertices: int | None = None,
    excluded_mask_classes: tuple[int, ...] | None = None,
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
    geom_facts = validate_polygon(geometry, max_area_ha=max_area_ha, max_vertices=max_vertices)

    # Resolve all scene/date assets (latest usable date if no date supplied).
    if not acquisition_date:
        acquisition_date = catalog.latest_item(source_id)["properties"]["akasha:acquisition_date"]
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

    intersecting_results: list[tuple[dict[str, Any], Any, int, int, tuple[str, str]]] = []
    for assets in candidate_assets:
        pos_a, pos_b, resolved_bands = _index_band_positions(assets, index_def, index_type)
        read = read_index_windows(
            analytic_href=assets["analyticHref"],
            mask_href=assets["maskHref"],
            geometry=geometry,
            positions=[pos_a, pos_b],
        )
        if read.intersects:
            intersecting_results.append((assets, read, pos_a, pos_b, resolved_bands))

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

    assets, read, pos_a, pos_b, resolved_bands = intersecting_results[0]
    excluded = _excluded_mask_classes_for_assets(
        assets=assets,
        override=excluded_mask_classes,
    )

    stats = compute_index_statistics(
        index_type=index_type,
        band_a_dn=read.band_arrays[pos_a],
        band_b_dn=read.band_arrays[pos_b],
        mask=read.mask,
        geometry_mask=read.geometry_mask,
        scale=assets["scale"],
        offset=assets["offset"],
        nodata=read.nodata,
        excluded_mask_classes=tuple(excluded),
        analytic_nodata_policy=str(assets.get("nodataPolicy") or "selected_band_or_mask"),
    )

    stats_dict = stats.as_dict()
    sar_support = compute_sar_support(
        geometry=geometry,
        optical_source_id=source_id,
        optical_acquisition_date=acquisition_date,
        optical_cloud_masked_percent=stats_dict.get("cloudMaskedPercent"),
        optical_masked_pixels=stats_dict.get("maskedPixels"),
        geometry_bounds=geom_facts.get("bounds"),
    )

    return build_response(
        stats=stats_dict,
        index_def=index_def,
        source_id=source_id,
        acquisition_date=acquisition_date,
        assets=assets,
        geom_facts=geom_facts,
        excluded=tuple(excluded),
        resolved_bands=resolved_bands,
        sar_support=sar_support,
    )


def _index_band_positions(
    assets: dict[str, Any],
    index_def: Any,
    index_type: str,
) -> tuple[int, int, tuple[str, str]]:
    band_names: list[str] = assets["bandNames"]
    band_role_mapping: dict[str, str] = assets.get("bandRoleMapping", {})
    required_roles = tuple(index_def.required_roles)
    for role in required_roles:
        band = band_role_mapping.get(role)
        if not band or band not in band_names:
            raise bad_request(
                (
                    f"Spectral role '{role}' required by {index_type} is not present "
                    "in the analytic asset."
                ),
                code="BAND_NOT_AVAILABLE",
                role=role,
                band=band,
                available=band_names,
                bandRoleMapping=band_role_mapping,
            )
    if len(required_roles) != 2:  # pragma: no cover - current registry is two-band only
        raise bad_request(
            f"Index '{index_type}' requires an unsupported number of bands.",
            code="UNSUPPORTED_INDEX_FORMULA",
            indexType=index_type,
            requiredRoles=list(required_roles),
        )
    return index_band_positions(band_names, band_role_mapping, index_def)


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
        geom_minx, geom_miny, geom_maxx, geom_maxy = (float(value) for value in geometry_bounds)
    except (TypeError, ValueError):
        return True
    return not (maxx < geom_minx or geom_maxx < minx or maxy < geom_miny or geom_maxy < miny)


def _excluded_mask_classes_for_assets(
    *,
    assets: dict[str, Any],
    override: tuple[int, ...] | None,
) -> tuple[int, ...]:
    if override is not None:
        return tuple(override)
    configured = assets.get("excludedMaskClasses")
    if isinstance(configured, (list, tuple)):
        try:
            return tuple(int(value) for value in configured)
        except (TypeError, ValueError):
            pass
    from .indices import DEFAULT_EXCLUDED_SCL_CLASSES

    return DEFAULT_EXCLUDED_SCL_CLASSES


def build_response(
    *,
    stats: dict[str, Any],
    index_def: Any,
    source_id: str,
    acquisition_date: str,
    assets: dict[str, Any],
    geom_facts: dict[str, Any],
    excluded: tuple[int, ...],
    resolved_bands: tuple[str, str],
    sar_support: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the normalized statistics response (architecture contract shape)."""
    response = {
        "indexType": stats["indexType"],
        "sourceId": source_id,
        "acquisitionDate": acquisition_date,
        "valueSplit": stats.get("valueSplit"),
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
            "maskedPixels": stats["maskedPixels"],
            "validPixels": stats["validPixels"],
        },
        "metadata": {
            "formula": index_def.formula,
            "bands": list(resolved_bands),
            "spectralRoles": list(index_def.required_roles),
            "maskMethod": assets.get("maskMethod") or f"Mask classes excluded: {list(excluded)}",
            "nativeExcludedMaskClasses": list(excluded),
            "metricsProvisional": bool(assets.get("metricsProvisional", False)),
            "reflectanceCorrection": (f"corrected = dn * {assets['scale']} + ({assets['offset']})"),
            "itemId": assets.get("itemId"),
            "areaHa": geom_facts.get("areaHa"),
            "vertices": geom_facts.get("vertices"),
            "warnings": stats.get("warnings", []),
        },
    }
    if sar_support is not None:
        response["sarSupport"] = sar_support
    return response
