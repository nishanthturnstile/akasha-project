"""AOI configuration loading for product API responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .raster.errors import AkashaError


def _resolve_aoi_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        if path.is_file():
            return path
        packaged = Path(__file__).resolve().parent / "defaults" / path.name
        return packaged if packaged.is_file() else path
    candidates = [Path.cwd(), *Path.cwd().resolve().parents, Path("/app")]
    for base in candidates:
        candidate = base / path
        if candidate.is_file():
            return candidate
    packaged = Path(__file__).resolve().parent / "defaults" / path.name
    if packaged.is_file():
        return packaged
    return Path.cwd() / path


def _as_number_list(value: Any, *, length: int, field_name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{field_name} must be a {length}-number list")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain only numbers") from exc


def _validate_geometry(geometry: Any) -> dict[str, Any]:
    if not isinstance(geometry, dict):
        raise ValueError("geometry must be a GeoJSON object")
    if geometry.get("type") != "Polygon":
        raise ValueError("geometry must be a GeoJSON Polygon")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("geometry.coordinates must contain at least one ring")
    ring = coordinates[0]
    if not isinstance(ring, list) or len(ring) < 4:
        raise ValueError("geometry outer ring must contain at least four positions")
    if ring[0] != ring[-1]:
        raise ValueError("geometry outer ring must be closed")
    for position in ring:
        _as_number_list(position, length=2, field_name="geometry position")
    return geometry


def load_aoi_config() -> dict[str, Any]:
    """Load the configured AOI as the public `/api/config` shape.

    The source file is a GeoJSON Feature with AOI metadata in properties. The
    public contract keeps the historical `bounds` key and adds the full polygon
    for Bhoonidhi search/composite workflows.
    """
    raw_path = settings.aoi_config_path.strip()
    if not raw_path:
        raise AkashaError(
            "AOI_CONFIG_MISSING",
            "AOI_CONFIG_PATH is not configured.",
            500,
        )

    path = _resolve_aoi_path(raw_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AkashaError(
            "AOI_CONFIG_NOT_FOUND",
            "Configured AOI file was not found.",
            500,
            {"path": raw_path},
        ) from exc
    except json.JSONDecodeError as exc:
        raise AkashaError(
            "AOI_CONFIG_INVALID",
            "Configured AOI file is not valid JSON.",
            500,
            {"path": raw_path},
        ) from exc

    try:
        if payload.get("type") != "Feature":
            raise ValueError("AOI file must be a GeoJSON Feature")
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("AOI Feature properties must be an object")
        aoi_id = str(properties["id"])
        name = str(properties["name"])
        center = _as_number_list(properties.get("center"), length=2, field_name="center")
        zoom = int(properties.get("zoom", 11))
        bounds = _as_number_list(payload.get("bbox"), length=4, field_name="bbox")
        geometry = _validate_geometry(payload.get("geometry"))
    except (KeyError, TypeError, ValueError) as exc:
        raise AkashaError(
            "AOI_CONFIG_INVALID",
            "Configured AOI file is malformed.",
            500,
            {"path": raw_path, "reason": str(exc)},
        ) from exc

    return {
        "id": aoi_id,
        "name": name,
        "center": center,
        "zoom": zoom,
        "bounds": bounds,
        "bbox": bounds,
        "geometry": geometry,
        "radiusMeters": properties.get("radiusMeters"),
        "compositeGridCrs": properties.get("compositeGridCrs"),
    }
