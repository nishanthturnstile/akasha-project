"""Source-specific cloud/mask toggle mapping for native raster statistics."""

from __future__ import annotations

from typing import Any

from .api_models import CloudMaskMapping, CloudMaskOptions

_SENTINEL_HARD_EXCLUDES = {0, 1, 2, 11}
_SENTINEL_CLOUD_SHADOWS = {3}
_SENTINEL_CLOUDS = {7, 8, 9}
_SENTINEL_CIRRUS = {10}

_AKASHA_MASK_NODATA = 0
_AKASHA_MASK_CLOUD = 2
_AKASHA_MASK_SHADOW = 3


def native_scl_excluded_classes(mask: CloudMaskOptions) -> tuple[int, ...]:
    """Map public cloud-mask toggles to Sentinel-2 SCL excluded classes."""
    excluded = set(_SENTINEL_HARD_EXCLUDES)
    if mask.clouds:
        excluded.update(_SENTINEL_CLOUDS)
    if mask.cloud_shadows:
        excluded.update(_SENTINEL_CLOUD_SHADOWS)
    if mask.cirrus:
        excluded.update(_SENTINEL_CIRRUS)
    return tuple(sorted(excluded))


def source_excluded_mask_classes(source: dict[str, Any], mask: CloudMaskOptions) -> tuple[int, ...]:
    """Map public mask toggles to source-native categorical classes."""
    if str(source.get("maskAsset") or "").lower() == "scl":
        return native_scl_excluded_classes(mask)

    configured = {
        int(value)
        for value in source.get("excludedMaskClasses", [])
        if isinstance(value, int) and not isinstance(value, bool)
    }
    if not configured:
        return ()

    excluded = set(configured)
    excluded.add(_AKASHA_MASK_NODATA)
    if not mask.clouds:
        excluded.discard(_AKASHA_MASK_CLOUD)
    if not mask.cloud_shadows:
        excluded.discard(_AKASHA_MASK_SHADOW)
    return tuple(sorted(excluded))


def source_cloud_mask_mapping(source: dict[str, Any], mask: CloudMaskOptions) -> CloudMaskMapping:
    warnings: list[str] = []
    available_options = set(source.get("availableMaskOptions") or [])
    if mask.cirrus and available_options and "cirrus" not in available_options:
        warnings.append(f"Cirrus masking is not supported for source '{source.get('id')}'.")
    return CloudMaskMapping(
        native_excluded_mask_classes=list(source_excluded_mask_classes(source, mask)),
        warnings=warnings,
    )


def cloud_mask_mapping(mask: CloudMaskOptions) -> CloudMaskMapping:
    """Legacy Sentinel-2 mapping retained for callers/tests without source metadata."""
    return CloudMaskMapping(native_excluded_mask_classes=list(native_scl_excluded_classes(mask)))
