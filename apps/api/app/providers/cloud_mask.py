"""Cloud-mask mapping shared by native and provider-backed routes."""
from __future__ import annotations

from .models import CloudMaskMapping, CloudMaskOptions

_NATIVE_HARD_EXCLUDES = {0, 1, 2, 11}
_NATIVE_CLOUD_SHADOWS = {3}
_NATIVE_CLOUDS = {7, 8, 9}
_NATIVE_CIRRUS = {10}
_EOS_APPROXIMATION_WARNING = "EOS_CLOUD_MASK_APPROXIMATION"


def native_scl_excluded_classes(mask: CloudMaskOptions) -> tuple[int, ...]:
    """Map public cloud-mask toggles to Akasha's native Sentinel-2 SCL exclusions."""
    excluded = set(_NATIVE_HARD_EXCLUDES)
    if mask.clouds:
        excluded.update(_NATIVE_CLOUDS)
    if mask.cloud_shadows:
        excluded.update(_NATIVE_CLOUD_SHADOWS)
    if mask.cirrus:
        excluded.update(_NATIVE_CIRRUS)
    return tuple(sorted(excluded))


def eos_cloud_masking_level(mask: CloudMaskOptions) -> tuple[int | None, bool, list[str]]:
    """Map public toggles to EOS cloud_masking_level with explicit approximation metadata."""
    if not mask.clouds and not mask.cloud_shadows and not mask.cirrus:
        return None, True, []
    if mask.clouds and not mask.cloud_shadows and not mask.cirrus:
        return 2, True, []
    if mask.clouds and not mask.cloud_shadows and mask.cirrus:
        return 4, True, []
    if mask.clouds and mask.cloud_shadows and mask.cirrus:
        return 3, True, []
    return 3, False, [_EOS_APPROXIMATION_WARNING]


def cloud_mask_mapping(mask: CloudMaskOptions) -> CloudMaskMapping:
    level, exact, warnings = eos_cloud_masking_level(mask)
    return CloudMaskMapping(
        native_excluded_scl_classes=list(native_scl_excluded_classes(mask)),
        eos_cloud_masking_level=level,
        eos_exact=exact,
        warnings=warnings,
    )


def eos_request_params(mask: CloudMaskOptions) -> dict[str, bool | int]:
    """Return provider params only when cloud masking is active."""
    level, _, _ = eos_cloud_masking_level(mask)
    if level is None:
        return {}
    return {
        "exclude_cover_pixels": True,
        "cloud_masking_level": level,
    }
