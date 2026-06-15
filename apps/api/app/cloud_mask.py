"""Cloud-mask mapping for Akasha native Sentinel-2 SCL statistics."""

from __future__ import annotations

from .api_models import CloudMaskMapping, CloudMaskOptions

_NATIVE_HARD_EXCLUDES = {0, 1, 2, 11}
_NATIVE_CLOUD_SHADOWS = {3}
_NATIVE_CLOUDS = {7, 8, 9}
_NATIVE_CIRRUS = {10}


def native_scl_excluded_classes(mask: CloudMaskOptions) -> tuple[int, ...]:
    """Map public cloud-mask toggles to Sentinel-2 SCL excluded classes."""
    excluded = set(_NATIVE_HARD_EXCLUDES)
    if mask.clouds:
        excluded.update(_NATIVE_CLOUDS)
    if mask.cloud_shadows:
        excluded.update(_NATIVE_CLOUD_SHADOWS)
    if mask.cirrus:
        excluded.update(_NATIVE_CIRRUS)
    return tuple(sorted(excluded))


def cloud_mask_mapping(mask: CloudMaskOptions) -> CloudMaskMapping:
    return CloudMaskMapping(
        native_excluded_mask_classes=list(native_scl_excluded_classes(mask)),
    )
