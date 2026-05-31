"""Geometry validation + area computation for index requests (Slice 2).

shapely + pyproj are imported lazily so importing the FastAPI app never
requires these wheels (keeps the live Emergent preview healthy even if the
geospatial stack is not installed).

Area is computed geodesically on the WGS84 ellipsoid (pyproj.Geod), which is
CRS-agnostic and accurate enough for hectare-scale plot guardrails.
"""
from __future__ import annotations

from typing import Any

from .errors import bad_request, invalid_geometry, polygon_too_large

_ACCEPTED_TYPES = ("Polygon", "MultiPolygon")


def _count_vertices(geometry: dict[str, Any]) -> int:
    coords = geometry.get("coordinates") or []
    total = 0
    stack = [coords]
    while stack:
        node = stack.pop()
        if (
            isinstance(node, (list, tuple))
            and len(node) == 2
            and all(isinstance(c, (int, float)) for c in node)
        ):
            total += 1
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return total


def geodesic_area_ha(geometry: dict[str, Any]) -> float:
    """Return the geodesic area of a (Multi)Polygon GeoJSON geometry in hectares."""
    from pyproj import Geod  # lazy
    from shapely.geometry import shape  # lazy

    geom = shape(geometry)
    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.geometry_area_perimeter(geom)
    return abs(area_m2) / 10_000.0


def validate_polygon(
    geometry: dict[str, Any],
    *,
    max_area_ha: float | None = None,
    max_vertices: int | None = None,
) -> dict[str, Any]:
    """Validate a request geometry and return derived facts.

    Raises AkashaError (422/413/400) for invalid, oversized, or too-detailed
    polygons. Returns {"areaHa": float, "vertices": int, "bounds": [...]}.
    """
    if not isinstance(geometry, dict):
        raise invalid_geometry("geometry must be a GeoJSON geometry object.")
    geom_type = geometry.get("type")
    if geom_type not in _ACCEPTED_TYPES:
        raise invalid_geometry(
            f"Unsupported geometry type '{geom_type}'. Expected one of {list(_ACCEPTED_TYPES)}.",
            received=geom_type,
        )
    if not geometry.get("coordinates"):
        raise invalid_geometry("geometry has no coordinates.")

    # Topological validity + bounds via shapely (lazy).
    try:
        from shapely.geometry import shape  # lazy
    except ImportError as exc:  # pragma: no cover - environment guard
        raise bad_request(
            "Server geospatial stack unavailable (shapely not installed).",
            code="GEO_STACK_UNAVAILABLE",
        ) from exc

    try:
        geom = shape(geometry)
    except Exception as exc:  # noqa: BLE001
        raise invalid_geometry(f"geometry could not be parsed: {exc}") from exc
    if geom.is_empty:
        raise invalid_geometry("geometry is empty.")
    if not geom.is_valid:
        raise invalid_geometry("geometry is not a valid polygon (self-intersection?).")

    vertices = _count_vertices(geometry)
    if max_vertices is not None and vertices > max_vertices:
        raise bad_request(
            f"Polygon has too many vertices ({vertices} > {max_vertices}).",
            code="TOO_MANY_VERTICES",
            vertices=vertices,
            maxVertices=max_vertices,
        )

    area_ha = geodesic_area_ha(geometry)
    if max_area_ha is not None and area_ha > max_area_ha:
        raise polygon_too_large(
            f"Polygon exceeds maximum area of {max_area_ha} ha (got {round(area_ha, 3)} ha).",
            areaHa=round(area_ha, 3),
            maxAreaHa=max_area_ha,
        )

    return {
        "areaHa": round(area_ha, 4),
        "vertices": vertices,
        "bounds": list(geom.bounds),
    }
