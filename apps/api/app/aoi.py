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


def _resolve_aoi_dir(raw_dir: str) -> Path:
    path = Path(raw_dir).expanduser()
    if path.is_absolute():
        return path
    candidates = [Path.cwd(), *Path.cwd().resolve().parents, Path("/app")]
    for base in candidates:
        candidate = base / path
        if candidate.is_dir():
            return candidate
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


def _public_aoi_from_feature(feature: dict[str, Any], *, raw_path: str) -> dict[str, Any]:
    try:
        if feature.get("type") != "Feature":
            raise ValueError("AOI must be a GeoJSON Feature")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("AOI Feature properties must be an object")
        aoi_id = str(properties["id"])
        name = str(properties["name"])
        center = _as_number_list(properties.get("center"), length=2, field_name="center")
        zoom = int(properties.get("zoom", 11))
        bounds = _as_number_list(feature.get("bbox"), length=4, field_name="bbox")
        geometry = _validate_geometry(feature.get("geometry"))
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


def _load_aoi_payload(path: Path, *, raw_path: str) -> list[dict[str, Any]]:
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

    if payload.get("type") == "Feature":
        return [_public_aoi_from_feature(payload, raw_path=raw_path)]
    if payload.get("type") == "FeatureCollection":
        features = [item for item in payload.get("features", []) if isinstance(item, dict)]
        if not features:
            raise AkashaError(
                "AOI_CONFIG_INVALID",
                "Configured AOI FeatureCollection has no features.",
                500,
                {"path": raw_path},
            )
        return [_public_aoi_from_feature(feature, raw_path=raw_path) for feature in features]
    raise AkashaError(
        "AOI_CONFIG_INVALID",
        "AOI file must be a GeoJSON Feature or FeatureCollection.",
        500,
        {"path": raw_path},
    )


def _dedupe_aois(aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for aoi in aois:
        by_id.setdefault(str(aoi["id"]), aoi)
    return list(by_id.values())


def load_aoi_configs() -> list[dict[str, Any]]:
    """Load all configured AOIs as public `/api/config.aois` entries."""
    raw_path = settings.aoi_config_path.strip()
    if not raw_path:
        raise AkashaError(
            "AOI_CONFIG_MISSING",
            "AOI_CONFIG_PATH is not configured.",
            500,
        )

    aois = _load_aoi_payload(_resolve_aoi_path(raw_path), raw_path=raw_path)
    raw_dir = settings.aoi_config_dir.strip()
    if raw_dir:
        directory = _resolve_aoi_dir(raw_dir)
        if not directory.is_dir():
            return _dedupe_aois(aois)
        for path in sorted(
            item
            for pattern in ("*.geojson", "*.json")
            for item in directory.glob(pattern)
            if item.is_file()
        ):
            aois.extend(_load_aoi_payload(path, raw_path=path.as_posix()))
    return _dedupe_aois(aois)


def select_default_aoi(aois: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the backward-compatible singular AOI from loaded AOI config."""
    default_id = settings.default_aoi_id.strip()
    if default_id:
        match = next((aoi for aoi in aois if aoi["id"] == default_id), None)
        if match:
            return match
    return aois[0]


def load_aoi_config() -> dict[str, Any]:
    """Load the selected AOI as the public `/api/config.aoi` shape.

    The backward-compatible `aoi` field remains singular. If multiple AOIs are
    configured, `DEFAULT_AOI_ID` selects one; otherwise the first AOI from
    `AOI_CONFIG_PATH` remains the default.
    """
    return select_default_aoi(load_aoi_configs())
