"""Source-aware validation profiles for Akasha raster products.

Implements TASK-035, TASK-036, TASK-037, and TASK-038 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Profile IDs mirror the ValidationProfile enum values in source_registry.py:
  optical_composite   – cloud-masked AOI composite from BOA optical source
  optical_scene       – individual optical scene (pre-composite)
  sar_backscatter     – SAR gamma-nought / sigma-nought backscatter
  precomputed_context – pre-computed index / context raster (e.g. MODIS NDVI)
  archive_only        – decommissioned / on-demand archive source
  visual_only         – VHR or aerial visual product (display only)

Plan-doc aliases are also accepted by all public helpers:
  context_raster  → precomputed_context
  archive_optical → archive_only
  vhr_visual      → visual_only

Stdlib only — no rasterio / GDAL imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Plan-doc alias map (plan name -> canonical profile_id)
# ---------------------------------------------------------------------------

_ALIAS_MAP: dict[str, str] = {
    "context_raster": "precomputed_context",
    "archive_optical": "archive_only",
    "vhr_visual": "visual_only",
}

_CANONICAL_PROFILE_IDS: frozenset[str] = frozenset(
    {
        "optical_composite",
        "optical_scene",
        "sar_backscatter",
        "precomputed_context",
        "archive_only",
        "visual_only",
    }
)


# ---------------------------------------------------------------------------
# ValidationProfileSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationProfileSpec:
    """Full specification for one validation profile.

    All collection-typed fields use immutable types (tuple, frozenset) so
    the dataclass is hashable.  ``None`` means "unconstrained / not applicable".
    """

    profile_id: str

    # Asset expectations
    expected_assets: tuple[str, ...] = ()
    optional_assets: tuple[str, ...] = ()

    # Raster geometry / radiometry
    band_count: int | None = None
    allowed_dtypes: frozenset[str] = frozenset()
    scale: float | None = None
    offset: float | None = None
    nodata: float | None = None

    # CRS rules (informational; enforced by raster_reader at runtime)
    crs_rules: tuple[str, ...] = ()

    # Resolution tolerance in metres (None = unconstrained)
    resolution_tolerance_m: float | None = None

    # COG overview requirement
    overview_required: bool = True

    # Cloud / validity mask
    mask_asset: str | None = None
    mask_valid_classes: frozenset[int] | None = None
    mask_excluded_classes: frozenset[int] | None = None
    # ((class_int, label_str), ...) in ascending class order
    mask_class_labels: tuple[tuple[int, str], ...] = ()

    # Expected band role labels in ascending band order (index 0 == band 1)
    band_roles: tuple[str, ...] = ()

    # STAC item fields that must be present on every matching item
    stac_required_fields: tuple[str, ...] = ()

    # Roles permitted for display tiles and statistics computation
    allowed_display_roles: frozenset[str] = frozenset()
    allowed_statistics_roles: frozenset[str] = frozenset()

    notes: str = ""


# ---------------------------------------------------------------------------
# Akasha threshold mask v1 constants (shared by all ISRO optical profiles)
# ---------------------------------------------------------------------------

_AKASHA_MASK_V1_LABELS: tuple[tuple[int, str], ...] = (
    (0, "nodata"),
    (1, "valid"),
    (2, "cloud"),
    (3, "shadow"),
    (4, "water"),
)
_AKASHA_MASK_V1_VALID: frozenset[int] = frozenset({1, 4})
_AKASHA_MASK_V1_EXCLUDED: frozenset[int] = frozenset({0, 2, 3})

# Reflectance correction common to ResourceSat-2A BOA products
_ISRO_BOA_SCALE: float = 0.0001
_ISRO_BOA_OFFSET: float = 0.0

# Band role tuples
_LISS3_BAND_ROLES: tuple[str, ...] = ("GREEN", "RED", "NIR", "SWIR1")
_LISS4_MX_BAND_ROLES: tuple[str, ...] = ("GREEN", "RED", "NIR")

# CRS rules for ISRO/Bhoonidhi optical products
_ISRO_CRS_RULES: tuple[str, ...] = (
    "WGS84 geographic (EPSG:4326) or UTM projected (standard zones)",
    "STAC registration uses EPSG:4326 bbox and geometry",
)

# STAC base fields
_OPTICAL_STAC_BASE: tuple[str, ...] = (
    "datetime",
    "eo:bands",
    "raster:bands",
    "akasha:source_id",
)
_OPTICAL_COMPOSITE_STAC: tuple[str, ...] = _OPTICAL_STAC_BASE + (
    "akasha:composite",
    "akasha:coverage_percent",
)
_OPTICAL_SCENE_STAC: tuple[str, ...] = _OPTICAL_STAC_BASE

# Display and statistics role sets
_FCC_DISPLAY_ROLES: frozenset[str] = frozenset({"NIR", "RED", "GREEN"})
_LISS3_STATS_ROLES: frozenset[str] = frozenset({"NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"})
_LISS4_STATS_ROLES: frozenset[str] = frozenset({"NDVI", "MSAVI", "NDWI_GREEN_NIR"})


# ---------------------------------------------------------------------------
# Named LISS-3 invariant constants (REQ-017 / TASK-000E)
# Exposed as module-level public constants for use in tests and validators.
# ---------------------------------------------------------------------------

LISS3_EXPECTED_ASSETS: tuple[str, ...] = ("analytic.tif", "mask.tif")
LISS3_BAND_COUNT: int = 4
LISS3_BAND_ROLES: tuple[str, ...] = ("GREEN", "RED", "NIR", "SWIR1")
LISS3_SCALE: float = 0.0001
LISS3_OFFSET: float = 0.0
LISS3_NODATA: float = 0.0
LISS3_MASK_VALID_CLASSES: frozenset[int] = frozenset({1, 4})
LISS3_MASK_EXCLUDED_CLASSES: frozenset[int] = frozenset({0, 2, 3})
LISS3_FCC_DISPLAY_ROLES: frozenset[str] = frozenset({"NIR", "RED", "GREEN"})
LISS3_SUPPORTED_STATS: frozenset[str] = frozenset({"NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"})


# ---------------------------------------------------------------------------
# Base profile definitions (one per canonical profile_id)
# ---------------------------------------------------------------------------

_OPTICAL_COMPOSITE_BASE = ValidationProfileSpec(
    profile_id="optical_composite",
    expected_assets=("analytic.tif", "mask.tif"),
    band_count=None,  # source overrides set exact count
    allowed_dtypes=frozenset({"uint16", "int16"}),
    scale=_ISRO_BOA_SCALE,
    offset=_ISRO_BOA_OFFSET,
    nodata=0.0,
    crs_rules=_ISRO_CRS_RULES,
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset="mask.tif",
    mask_valid_classes=_AKASHA_MASK_V1_VALID,
    mask_excluded_classes=_AKASHA_MASK_V1_EXCLUDED,
    mask_class_labels=_AKASHA_MASK_V1_LABELS,
    band_roles=(),
    stac_required_fields=_OPTICAL_COMPOSITE_STAC,
    allowed_display_roles=_FCC_DISPLAY_ROLES,
    allowed_statistics_roles=_LISS3_STATS_ROLES,
    notes=(
        "Generic cloud-masked AOI composite from a BOA optical source. "
        "Akasha threshold mask v1 (no SCL); separate analytic and mask COG assets. "
        "Source-specific overrides (band count, resolution) take precedence."
    ),
)

_OPTICAL_SCENE_BASE = ValidationProfileSpec(
    profile_id="optical_scene",
    expected_assets=("analytic.tif", "mask.tif"),
    band_count=None,
    allowed_dtypes=frozenset({"uint16", "int16"}),
    scale=_ISRO_BOA_SCALE,
    offset=_ISRO_BOA_OFFSET,
    nodata=0.0,
    crs_rules=_ISRO_CRS_RULES,
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset="mask.tif",
    mask_valid_classes=_AKASHA_MASK_V1_VALID,
    mask_excluded_classes=_AKASHA_MASK_V1_EXCLUDED,
    mask_class_labels=_AKASHA_MASK_V1_LABELS,
    band_roles=(),
    stac_required_fields=_OPTICAL_SCENE_STAC,
    allowed_display_roles=_FCC_DISPLAY_ROLES,
    allowed_statistics_roles=_LISS3_STATS_ROLES,
    notes=(
        "Individual optical scene (pre-composite). Requires analytic and mask COG assets. "
        "Akasha threshold mask v1. Source overrides specify exact band count and roles."
    ),
)

_SAR_BACKSCATTER_BASE = ValidationProfileSpec(
    profile_id="sar_backscatter",
    expected_assets=("backscatter.tif",),
    optional_assets=("backscatter_vv.tif", "backscatter_vh.tif"),
    band_count=None,
    allowed_dtypes=frozenset({"float32", "uint16"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=(
        "WGS84 geographic (EPSG:4326) or UTM projected",
        "STAC registration uses EPSG:4326 bbox and geometry",
    ),
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "raster:bands",
        "sar:polarizations",
        "akasha:source_id",
    ),
    # GEO-002: SAR sources must not advertise optical vegetation indices
    allowed_display_roles=frozenset({"SAR_VV", "SAR_VH", "SAR_VV_VH_RATIO"}),
    allowed_statistics_roles=frozenset(),
    notes=(
        "SAR gamma-nought / sigma-nought backscatter. "
        "GEO-002: SAR sources must not advertise optical vegetation indices "
        "(NDVI, NDMI, NDWI, MSAVI, etc.). allowed_statistics_roles is empty; "
        "SAR-specific analytics require a dedicated profile extension."
    ),
)

_PRECOMPUTED_CONTEXT_BASE = ValidationProfileSpec(
    profile_id="precomputed_context",
    expected_assets=("context.tif",),
    optional_assets=("ndvi.tif", "composite.tif"),
    band_count=None,
    allowed_dtypes=frozenset({"float32", "float64", "int16", "uint8"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=("WGS84 geographic (EPSG:4326) or UTM projected",),
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "raster:bands",
        "akasha:source_id",
    ),
    # GEO-003: context rasters are display-only; no raw-band field statistics
    allowed_display_roles=frozenset({"CONTEXT_NDVI", "CONTEXT_COMPOSITE", "DISPLAY_ONLY"}),
    allowed_statistics_roles=frozenset(),
    notes=(
        "Pre-computed index or context raster (e.g. MODIS MOD13Q1 NDVI, EOS-06 OCM NDVI). "
        "GEO-003: not a raw-reflectance field-statistics source. "
        "Display-only; no field-level band statistics permitted."
    ),
)

_ARCHIVE_ONLY_BASE = ValidationProfileSpec(
    profile_id="archive_only",
    expected_assets=("analytic.tif",),
    optional_assets=("mask.tif",),
    band_count=None,
    allowed_dtypes=frozenset({"uint16", "uint8", "int16", "float32"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=("WGS84 geographic (EPSG:4326) or projected",),
    resolution_tolerance_m=None,
    overview_required=False,  # archive products may lack current overviews
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "akasha:source_id",
    ),
    allowed_display_roles=frozenset({"FCC", "TRUE_COLOR", "DISPLAY_ONLY"}),
    allowed_statistics_roles=frozenset({"NDVI"}),  # limited historical baseline stats
    notes=(
        "Decommissioned or archive-only / on-demand optical source "
        "(e.g. Landsat 5/7, IRS-1C). Not a routine current-monitoring source (SRC-007). "
        "Mask asset is optional — archive products may not have Akasha mask v1. "
        "Limited statistics for historical baseline analysis only."
    ),
)

_VISUAL_ONLY_BASE = ValidationProfileSpec(
    profile_id="visual_only",
    expected_assets=("visual.tif",),
    optional_assets=("pan.tif", "ms.tif"),
    band_count=None,
    allowed_dtypes=frozenset({"uint8", "uint16"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=("WGS84 geographic (EPSG:4326) or projected",),
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "akasha:source_id",
    ),
    allowed_display_roles=frozenset({"TRUE_COLOR", "PAN", "DISPLAY_ONLY"}),
    allowed_statistics_roles=frozenset(),
    notes=(
        "VHR or aerial visual product (display only). "
        "No optical vegetation index statistics. "
        "Commercial products require a commercial_readiness record before any analytics use."
    ),
)


# ---------------------------------------------------------------------------
# Profile registry (canonical profile_id -> spec)
# ---------------------------------------------------------------------------

_PROFILES: dict[str, ValidationProfileSpec] = {
    "optical_composite": _OPTICAL_COMPOSITE_BASE,
    "optical_scene": _OPTICAL_SCENE_BASE,
    "sar_backscatter": _SAR_BACKSCATTER_BASE,
    "precomputed_context": _PRECOMPUTED_CONTEXT_BASE,
    "archive_only": _ARCHIVE_ONLY_BASE,
    "visual_only": _VISUAL_ONLY_BASE,
}


# ---------------------------------------------------------------------------
# Source-specific profile overrides
# These encode exact per-source invariants that are stricter than the base profile.
# ---------------------------------------------------------------------------

_LISS3_BOA_SPEC = ValidationProfileSpec(
    profile_id="optical_composite",
    expected_assets=LISS3_EXPECTED_ASSETS,
    band_count=LISS3_BAND_COUNT,
    allowed_dtypes=frozenset({"uint16"}),
    scale=LISS3_SCALE,
    offset=LISS3_OFFSET,
    nodata=LISS3_NODATA,
    crs_rules=_ISRO_CRS_RULES,
    resolution_tolerance_m=2.0,  # LISS-3 nominal 23.5 m; ±2 m tolerance
    overview_required=True,
    mask_asset="mask.tif",
    mask_valid_classes=LISS3_MASK_VALID_CLASSES,
    mask_excluded_classes=LISS3_MASK_EXCLUDED_CLASSES,
    mask_class_labels=_AKASHA_MASK_V1_LABELS,
    band_roles=LISS3_BAND_ROLES,
    stac_required_fields=_OPTICAL_COMPOSITE_STAC,
    allowed_display_roles=LISS3_FCC_DISPLAY_ROLES,
    allowed_statistics_roles=LISS3_SUPPORTED_STATS,
    notes=(
        "ResourceSat-2A LISS-3 BOA cloud-masked composite. "
        "4 analytic bands [BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]. "
        "FCC display NIR/RED/GREEN (no true-colour; no blue band). "
        "Akasha threshold mask v1; no SCL. Separate analytic and mask COG assets. "
        "Reflectance: scale 0.0001, offset 0.0 (do NOT apply Sentinel-2 -0.1 offset). "
        "TiTiler FCC bidx: NIR=b3, RED=b2, GREEN=b1. "
        "Supported statistics: NDVI, MSAVI, NDMI, NDWI_GREEN_NIR."
    ),
)

_AWIFS_BOA_SPEC = ValidationProfileSpec(
    profile_id="optical_composite",
    expected_assets=("analytic.tif", "mask.tif"),
    band_count=4,
    allowed_dtypes=frozenset({"uint16"}),
    scale=_ISRO_BOA_SCALE,
    offset=_ISRO_BOA_OFFSET,
    nodata=0.0,
    crs_rules=_ISRO_CRS_RULES,
    resolution_tolerance_m=5.0,  # AWiFS nominal 56 m; ±5 m tolerance
    overview_required=True,
    mask_asset="mask.tif",
    mask_valid_classes=_AKASHA_MASK_V1_VALID,
    mask_excluded_classes=_AKASHA_MASK_V1_EXCLUDED,
    mask_class_labels=_AKASHA_MASK_V1_LABELS,
    band_roles=_LISS3_BAND_ROLES,
    stac_required_fields=_OPTICAL_COMPOSITE_STAC,
    allowed_display_roles=_FCC_DISPLAY_ROLES,
    allowed_statistics_roles=_LISS3_STATS_ROLES,
    notes=(
        "ResourceSat-2A AWiFS BOA cloud-masked composite. "
        "4 analytic bands [BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]. "
        "FCC display NIR/RED/GREEN. Akasha threshold mask v1; no SCL. "
        "Reflectance: scale 0.0001, offset 0.0. "
        "Product-active for regional/coarse analytics with a 60% minimum usable-coverage threshold."
    ),
)

_LISS4_MX70_SPEC = ValidationProfileSpec(
    profile_id="optical_scene",
    expected_assets=("analytic.tif", "mask.tif"),
    band_count=3,  # LISS-4 MX: BAND2 Green, BAND3 Red, BAND4 NIR; no SWIR1
    allowed_dtypes=frozenset({"uint16"}),
    scale=_ISRO_BOA_SCALE,
    offset=_ISRO_BOA_OFFSET,
    nodata=0.0,
    crs_rules=_ISRO_CRS_RULES,
    resolution_tolerance_m=1.0,  # LISS-4 nominal 5.0 m; ±1 m tolerance
    overview_required=True,
    mask_asset="mask.tif",
    mask_valid_classes=_AKASHA_MASK_V1_VALID,
    mask_excluded_classes=_AKASHA_MASK_V1_EXCLUDED,
    mask_class_labels=_AKASHA_MASK_V1_LABELS,
    band_roles=_LISS4_MX_BAND_ROLES,
    stac_required_fields=_OPTICAL_SCENE_STAC,
    allowed_display_roles=_FCC_DISPLAY_ROLES,
    allowed_statistics_roles=_LISS4_STATS_ROLES,
    notes=(
        "ResourceSat-2A LISS-4 MX70 L2 individual scene. "
        "3 analytic bands [BAND2 Green, BAND3 Red, BAND4 NIR]; no SWIR1. "
        "FCC display NIR/RED/GREEN. Akasha threshold mask v1; no SCL. "
        "Reflectance: scale 0.0001, offset 0.0. "
        "Narrow-swath 70 km; field-intersection fallback semantics. "
        "NDMI not available (no SWIR1). Supported: NDVI, MSAVI, NDWI_GREEN_NIR."
    ),
)

_EOS04_SAR_SPEC = ValidationProfileSpec(
    profile_id="sar_backscatter",
    expected_assets=("backscatter.tif",),
    optional_assets=("backscatter_vv.tif", "backscatter_vh.tif"),
    band_count=None,
    allowed_dtypes=frozenset({"float32"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=(
        "WGS84 geographic (EPSG:4326) or UTM projected",
        "STAC registration uses EPSG:4326 bbox and geometry",
    ),
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "raster:bands",
        "sar:polarizations",
        "akasha:source_id",
    ),
    allowed_display_roles=frozenset({"SAR_VV", "SAR_VH", "SAR_VV_VH_RATIO"}),
    allowed_statistics_roles=frozenset(),
    notes=(
        "EOS-04 (RISAT) SAR MRS/CRS backscatter. C-band; L2B product. "
        "Prepared output must be Float32 dB backscatter.tif with explicit "
        "sar:polarizations. GEO-002: no optical vegetation indices. "
        "MRS/CRS modes free via NRSC; FRS-1 fine modes are not freely available."
    ),
)

_NISAR_SAR_SPEC = ValidationProfileSpec(
    profile_id="sar_backscatter",
    expected_assets=("backscatter.tif",),
    optional_assets=(),
    band_count=None,
    allowed_dtypes=frozenset({"float32"}),
    scale=None,
    offset=None,
    nodata=None,
    crs_rules=("WGS84 geographic (EPSG:4326) or UTM projected",),
    resolution_tolerance_m=None,
    overview_required=True,
    mask_asset=None,
    mask_valid_classes=None,
    mask_excluded_classes=None,
    mask_class_labels=(),
    band_roles=(),
    stac_required_fields=(
        "datetime",
        "raster:bands",
        "sar:polarizations",
        "akasha:source_id",
    ),
    allowed_display_roles=frozenset({"SAR_VV", "SAR_VH", "SAR_L_BAND"}),
    allowed_statistics_roles=frozenset(),
    notes=(
        "NISAR S-SAR Beta-GCOV L+S band SAR backscatter. "
        "GEO-002: no optical vegetation indices. "
        "Calibrated ARD/GCOV products; dual-provider path (Bhoonidhi + ASF/Earthdata)."
    ),
)


# ---------------------------------------------------------------------------
# Source-specific overrides registry (source_id -> spec)
# Populated for sources where the base profile is not specific enough.
# ---------------------------------------------------------------------------

_SOURCE_SPEC_OVERRIDES: dict[str, ValidationProfileSpec] = {
    "resourcesat-2a-liss3-boa": _LISS3_BOA_SPEC,
    "resourcesat-2a-liss4-mx70-l2": _LISS4_MX70_SPEC,
    "resourcesat-2a-awifs-boa": _AWIFS_BOA_SPEC,
    "eos-04-sar-mrs-l2b": _EOS04_SAR_SPEC,
    "nisar-ssar-beta-gcov": _NISAR_SAR_SPEC,
    "alos2-palsar2": _SAR_BACKSCATTER_BASE,
    "alos2-mosaic-25m": _SAR_BACKSCATTER_BASE,
    "sentinel-1-grd": _SAR_BACKSCATTER_BASE,
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _resolve_profile_key(key: str) -> str:
    """Normalise a profile ID or plan-doc alias to a canonical profile_id."""
    return _ALIAS_MAP.get(key, key)


def validate_statistics_role(spec: ValidationProfileSpec, role: str) -> None:
    """Raise ValueError if the statistics role is not permitted by this profile.

    Enforces GEO-002 (SAR sources must not advertise optical indices) and
    GEO-003 (context rasters are display-only, no raw-band statistics).
    """
    if role not in spec.allowed_statistics_roles:
        allowed = sorted(spec.allowed_statistics_roles)
        raise ValueError(
            f"profile {spec.profile_id!r} does not allow statistics role {role!r}. "
            f"Allowed: {allowed if allowed else '(none)'}. "
            f"To add a role the source must have bands supporting this index."
        )


def validate_display_role(spec: ValidationProfileSpec, role: str) -> None:
    """Raise ValueError if the display role is not permitted by this profile."""
    if role not in spec.allowed_display_roles:
        allowed = sorted(spec.allowed_display_roles)
        raise ValueError(
            f"profile {spec.profile_id!r} does not allow display role {role!r}. "
            f"Allowed: {allowed if allowed else '(none)'}."
        )


def validate_band_count(spec: ValidationProfileSpec, actual: int) -> None:
    """Raise ValueError if actual band count does not match the profile requirement."""
    if spec.band_count is not None and actual != spec.band_count:
        raise ValueError(
            f"profile {spec.profile_id!r} requires {spec.band_count} band(s); " f"got {actual}."
        )


def validate_asset_present(spec: ValidationProfileSpec, asset_name: str) -> None:
    """Raise ValueError if asset_name is not in expected_assets or optional_assets."""
    if asset_name not in spec.expected_assets and asset_name not in spec.optional_assets:
        raise ValueError(
            f"profile {spec.profile_id!r}: asset {asset_name!r} is not expected. "
            f"Expected: {spec.expected_assets}. Optional: {spec.optional_assets}."
        )


def validate_expected_assets_present(
    spec: ValidationProfileSpec, available_assets: set[str]
) -> None:
    """Raise ValueError if any required asset is missing from available_assets."""
    missing = [a for a in spec.expected_assets if a not in available_assets]
    if missing:
        raise ValueError(
            f"profile {spec.profile_id!r}: required asset(s) missing: {missing}. "
            f"Available: {sorted(available_assets)}."
        )


def _normalise_band_role(value: object) -> str:
    """Normalize STAC role/common_name values to Akasha uppercase role labels."""
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {
        "GREEN": "GREEN",
        "RED": "RED",
        "NIR": "NIR",
        "SWIR1": "SWIR1",
        "SWIR_1": "SWIR1",
        "SWIR16": "SWIR1",
        "SWIR_16": "SWIR1",
        "SWIR": "SWIR1",
        "BLUE": "BLUE",
    }
    return aliases.get(text, text)


def _role_for_eo_band(band: dict, band_name_to_role: dict[str, str]) -> str:
    """Resolve a STAC eo:bands entry to an Akasha role label.

    STAC ``name`` is commonly the source band ID (e.g. BAND2), while the role is
    carried by ``common_name``, ``role``, or ``akasha:band_role_mapping``.
    """
    for key in ("role", "common_name"):
        if band.get(key):
            return _normalise_band_role(band[key])
    name = str(band.get("name") or "")
    if name in band_name_to_role:
        return _normalise_band_role(band_name_to_role[name])
    return _normalise_band_role(name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_validation_profile(profile_or_source_id: str) -> ValidationProfileSpec:
    """Return a ValidationProfileSpec by profile name or source_id.

    Accepts:
    - canonical profile_id: ``"optical_composite"``, ``"sar_backscatter"``, etc.
    - plan-doc aliases: ``"context_raster"``, ``"archive_optical"``, ``"vhr_visual"``
    - source_id: ``"resourcesat-2a-liss3-boa"``, ``"sentinel-1-grd"``, etc.

    Fail-closed: raises ValueError for unknown inputs.
    """
    normalized = _resolve_profile_key(profile_or_source_id)

    if normalized in _PROFILES:
        return _PROFILES[normalized]

    # Try as source_id (delegates to profile_for_source)
    try:
        return profile_for_source(profile_or_source_id)
    except (KeyError, ValueError, ImportError):
        pass

    raise ValueError(
        f"unknown validation profile or source_id: {profile_or_source_id!r}. "
        f"Known profiles: {sorted(_PROFILES)}. "
        f"Plan-doc aliases: {sorted(_ALIAS_MAP)}."
    )


def profile_for_source(source_id: str) -> ValidationProfileSpec:
    """Return the ValidationProfileSpec for a source_id.

    Uses a source-specific override when available, otherwise falls back to
    the base profile for the source's ValidationProfile value from source_registry.

    Fail-closed: raises KeyError for unknown source_ids.
    """
    if source_id in _SOURCE_SPEC_OVERRIDES:
        return _SOURCE_SPEC_OVERRIDES[source_id]

    # Lazy import to avoid circular dependency at module load time
    from akasha_ingest.source_registry import SOURCE_REGISTRY  # noqa: PLC0415

    try:
        row = SOURCE_REGISTRY[source_id]
    except KeyError:
        raise KeyError(
            f"unknown source_id {source_id!r}: not found in source_registry "
            f"and no source-specific override registered in validation_profiles."
        ) from None

    profile_id = row.validation_profile.value
    try:
        return _PROFILES[profile_id]
    except KeyError:
        raise ValueError(
            f"source {source_id!r} maps to validation_profile={profile_id!r} "
            f"but no corresponding ValidationProfileSpec is registered. "
            f"Known profiles: {sorted(_PROFILES)}."
        ) from None


def check_source_statistics_role(source_id: str, role: str) -> None:
    """Raise ValueError if statistics role is not allowed for source_id.

    Convenience wrapper around profile_for_source + validate_statistics_role.
    Fail-closed on unknown sources.
    """
    validate_statistics_role(profile_for_source(source_id), role)


def check_source_display_role(source_id: str, role: str) -> None:
    """Raise ValueError if display role is not allowed for source_id.

    Convenience wrapper around profile_for_source + validate_display_role.
    Fail-closed on unknown sources.
    """
    validate_display_role(profile_for_source(source_id), role)


# ---------------------------------------------------------------------------
# Manifest metadata validation (TASK-037)
# Validates a prepare_manifest.json dict against a ValidationProfileSpec.
# Stdlib-only; does not require rasterio/GDAL.
# ---------------------------------------------------------------------------

# Optical vegetation index names that must not appear in SAR manifests (GEO-002).
_OPTICAL_INDEX_NAMES: frozenset[str] = frozenset(
    {
        "NDVI",
        "NDMI",
        "NDWI",
        "NDWI_GREEN_NIR",
        "MSAVI",
        "EVI",
        "SAVI",
        "NDRE",
        "RECI",
    }
)
_EOS04_KNOWN_POLARIZATIONS: frozenset[str] = frozenset({"HH", "HV", "VH", "VV", "RH", "RV"})


@dataclass(frozen=True)
class ManifestValidationResult:
    """Result of manifest metadata validation against a ValidationProfileSpec."""

    ok: bool
    checks: tuple[str, ...]
    problems: tuple[str, ...]
    detail: str


def _first_asset_dict(
    outputs: dict,
    assets_top: dict,
    *names: str,
) -> dict | None:
    """Return the first asset metadata dict matching any role/name."""
    for container in (outputs, assets_top):
        if not isinstance(container, dict):
            continue
        for name in names:
            value = container.get(name)
            if isinstance(value, dict):
                return value
    return None


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_int_set(value: object) -> frozenset[int] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        try:
            return frozenset(int(v) for v in value)
        except (TypeError, ValueError):
            return None
    return None


def _as_label_tuple(value: object) -> tuple[tuple[int, str], ...] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            return tuple(sorted((int(k), str(v)) for k, v in value.items()))
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)):
        labels: list[tuple[int, str]] = []
        try:
            for item in value:
                if isinstance(item, dict):
                    cls = item.get("class") or item.get("value") or item.get("id")
                    label = item.get("label") or item.get("name")
                    labels.append((int(cls), str(label)))
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    labels.append((int(item[0]), str(item[1])))
                else:
                    return None
        except (TypeError, ValueError):
            return None
        return tuple(sorted(labels))
    return None


def _sar_polarization_list(*containers: dict) -> list[str]:
    for container in containers:
        if not isinstance(container, dict):
            continue
        value = container.get("sar:polarizations") or container.get("polarizations")
        if isinstance(value, str):
            raw = value.replace(";", ",").replace(" ", ",").split(",")
        elif isinstance(value, list):
            raw = value
        else:
            continue
        polarizations = [str(pol).strip().upper() for pol in raw if str(pol).strip()]
        if polarizations:
            return polarizations
    return []


def validate_manifest_metadata(
    spec: ValidationProfileSpec,
    manifest_data: dict,
    *,
    source_id: str | None = None,
) -> ManifestValidationResult:
    """Validate a prepare_manifest.json dict against a ValidationProfileSpec.

    Does not require rasterio/GDAL. Checks:
    - source_id consistency between caller and manifest (if both provided)
    - expected assets declared in manifest outputs or assets
    - analytic band count against spec (if declared in manifest)
    - band roles against spec eo:bands (if declared in manifest)
    - STAC required fields (checked in properties and at top level)
    - SAR GEO-002: optical vegetation indices must not be advertised
    - Context/visual GEO-003: raw-band field statistics must not be advertised

    Returns ManifestValidationResult with ok/checks/problems/detail.
    """
    checks: list[str] = []
    problems: list[str] = []

    # --- source_id consistency ---
    manifest_source = str(manifest_data.get("source_id") or manifest_data.get("sourceId") or "")
    if source_id and manifest_source:
        if manifest_source != source_id:
            problems.append(
                f"manifest source_id {manifest_source!r} does not match expected {source_id!r}"
            )
        else:
            checks.append(f"manifest source_id matches {source_id!r}")
    elif source_id and not manifest_source:
        checks.append(f"manifest has no source_id field (expected {source_id!r}); skipped")

    checks.append(f"validating against profile {spec.profile_id!r}")

    # --- expected assets ---
    outputs: dict = manifest_data.get("outputs") or {}
    assets_top: dict = manifest_data.get("assets") or {}

    # Collect declared asset identifiers: both role keys ("analytic", "mask")
    # and filename stems/names from nested path/href fields.
    declared_asset_keys: set[str] = set()
    if isinstance(outputs, dict):
        for k, v in outputs.items():
            declared_asset_keys.add(k)
            if isinstance(v, dict):
                path_val = v.get("path") or v.get("href") or ""
                if path_val:
                    fname = Path(str(path_val)).name
                    declared_asset_keys.add(fname)
                    declared_asset_keys.add(fname.rsplit(".", 1)[0] if "." in fname else fname)
    if isinstance(assets_top, dict):
        for k, v in assets_top.items():
            declared_asset_keys.add(k)
            if isinstance(v, dict):
                href_val = v.get("href") or v.get("path") or ""
                if href_val:
                    fname = Path(str(href_val)).name
                    declared_asset_keys.add(fname)
                    declared_asset_keys.add(fname.rsplit(".", 1)[0] if "." in fname else fname)

    for expected in spec.expected_assets:
        stem = expected.rsplit(".", 1)[0] if "." in expected else expected
        if expected in declared_asset_keys or stem in declared_asset_keys:
            checks.append(f"expected asset {expected!r} declared")
        else:
            problems.append(
                f"expected asset {expected!r} not declared in manifest outputs "
                f"(profile {spec.profile_id!r} requires: {spec.expected_assets})"
            )

    # --- analytic band count ---
    if spec.band_count is not None:
        analytic_data: dict | None = _first_asset_dict(
            outputs, assets_top, "analytic", "analytic.tif"
        )
        if isinstance(analytic_data, dict):
            actual_count = analytic_data.get("band_count")
            if actual_count is not None:
                if int(actual_count) == spec.band_count:
                    checks.append(f"analytic band count {spec.band_count} matches spec")
                else:
                    problems.append(
                        f"analytic band count {actual_count} != {spec.band_count} "
                        f"(required by profile {spec.profile_id!r})"
                    )
            else:
                checks.append("analytic band_count not declared in manifest; check skipped")
        else:
            checks.append("analytic asset not present for band_count check; check skipped")

    if spec.profile_id == "sar_backscatter":
        backscatter_data = _first_asset_dict(outputs, assets_top, "backscatter", "backscatter.tif")
        props_sar_asset: dict = {}
        if isinstance(manifest_data.get("properties"), dict):
            props_sar_asset = manifest_data["properties"]
        polarizations = _sar_polarization_list(
            manifest_data,
            props_sar_asset,
            backscatter_data or {},
        )
        if isinstance(backscatter_data, dict):
            dtype = backscatter_data.get("dtype")
            if dtype is None:
                if source_id == "eos-04-sar-mrs-l2b":
                    problems.append(
                        "EOS-04 backscatter dtype must be declared as float32 before ingest."
                    )
                else:
                    checks.append("backscatter dtype not declared in manifest; check skipped")
            elif str(dtype).lower() in spec.allowed_dtypes:
                checks.append(f"backscatter dtype {dtype!r} allowed by spec")
            else:
                problems.append(
                    f"backscatter dtype {dtype!r} not in allowed dtypes "
                    f"{sorted(spec.allowed_dtypes)} (profile {spec.profile_id!r})"
                )
            actual_count = backscatter_data.get("band_count")
            if actual_count is None:
                if source_id == "eos-04-sar-mrs-l2b":
                    problems.append(
                        "EOS-04 backscatter band_count must be declared and at least 1."
                    )
                else:
                    checks.append("backscatter band_count not declared in manifest; check skipped")
            else:
                try:
                    band_count = int(actual_count)
                except (TypeError, ValueError):
                    problems.append(f"backscatter band_count {actual_count!r} is not an integer")
                else:
                    if band_count < 1:
                        problems.append("backscatter band_count must be at least 1")
                    elif (
                        source_id == "eos-04-sar-mrs-l2b"
                        and polarizations
                        and band_count != len(polarizations)
                    ):
                        problems.append(
                            "EOS-04 backscatter band_count must match explicit "
                            f"sar:polarizations ({band_count} != {len(polarizations)})"
                        )
                    else:
                        checks.append(f"backscatter band_count {band_count} is valid")
        if source_id == "eos-04-sar-mrs-l2b":
            if polarizations:
                unknown = [pol for pol in polarizations if pol not in _EOS04_KNOWN_POLARIZATIONS]
                if unknown:
                    problems.append(
                        "EOS-04 sar:polarizations contains unsupported token(s) "
                        f"{unknown}. Allowed: {sorted(_EOS04_KNOWN_POLARIZATIONS)}."
                    )
                else:
                    checks.append(f"EOS-04 sar:polarizations declared: {polarizations}")
            else:
                problems.append(
                    "EOS-04 SAR manifest requires explicit sar:polarizations; "
                    "do not default unknown backscatter bands to VV or HH."
                )

    analytic_data = _first_asset_dict(outputs, assets_top, "analytic", "analytic.tif")
    if isinstance(analytic_data, dict):
        if spec.allowed_dtypes:
            dtype = analytic_data.get("dtype")
            if dtype is None:
                checks.append("analytic dtype not declared in manifest; check skipped")
            elif str(dtype) in spec.allowed_dtypes:
                checks.append(f"analytic dtype {dtype!r} allowed by spec")
            else:
                problems.append(
                    f"analytic dtype {dtype!r} not in allowed dtypes "
                    f"{sorted(spec.allowed_dtypes)} (profile {spec.profile_id!r})"
                )

        for field_name, expected in (
            ("scale", spec.scale),
            ("offset", spec.offset),
            ("nodata", spec.nodata),
        ):
            if expected is None:
                continue
            actual = _as_float(analytic_data.get(field_name))
            if actual is None:
                checks.append(f"analytic {field_name} not declared in manifest; check skipped")
            elif abs(actual - expected) <= 1e-12:
                checks.append(f"analytic {field_name} {expected!r} matches spec")
            else:
                problems.append(
                    f"analytic {field_name} {actual!r} != {expected!r} "
                    f"(profile {spec.profile_id!r})"
                )

    mask_data = _first_asset_dict(outputs, assets_top, "mask", "mask.tif", spec.mask_asset or "")
    if isinstance(mask_data, dict):
        for field_name, expected in (
            ("valid_classes", spec.mask_valid_classes),
            ("excluded_classes", spec.mask_excluded_classes),
        ):
            if expected is None:
                continue
            actual = _as_int_set(mask_data.get(field_name))
            if actual is None:
                checks.append(f"mask {field_name} not declared in manifest; check skipped")
            elif actual == expected:
                checks.append(f"mask {field_name} matches spec: {sorted(expected)}")
            else:
                problems.append(
                    f"mask {field_name} {sorted(actual)} != {sorted(expected)} "
                    f"(profile {spec.profile_id!r})"
                )

        if spec.mask_class_labels:
            actual_labels = _as_label_tuple(mask_data.get("class_labels"))
            if actual_labels is None:
                checks.append("mask class_labels not declared in manifest; check skipped")
            elif actual_labels == spec.mask_class_labels:
                checks.append("mask class_labels match spec")
            else:
                problems.append(
                    f"mask class_labels {actual_labels!r} != {spec.mask_class_labels!r} "
                    f"(profile {spec.profile_id!r})"
                )

    # --- band roles via eo:bands ---
    if spec.band_roles:
        props_dict: dict = {}
        if isinstance(manifest_data.get("properties"), dict):
            props_dict = manifest_data["properties"]
        eo_bands = props_dict.get("eo:bands") or manifest_data.get("eo:bands")
        if isinstance(eo_bands, list):
            raw_mapping = (
                props_dict.get("akasha:band_role_mapping")
                or manifest_data.get("akasha:band_role_mapping")
                or manifest_data.get("band_role_mapping")
                or {}
            )
            band_name_to_role = (
                {str(band_name): str(role) for role, band_name in raw_mapping.items()}
                if isinstance(raw_mapping, dict)
                else {}
            )
            manifest_roles = tuple(
                _role_for_eo_band(b, band_name_to_role) for b in eo_bands if isinstance(b, dict)
            )
            if manifest_roles == spec.band_roles:
                checks.append(f"eo:bands roles match spec: {spec.band_roles}")
            else:
                problems.append(
                    f"eo:bands roles {manifest_roles} != spec {spec.band_roles} "
                    f"(profile {spec.profile_id!r})"
                )
        else:
            checks.append("eo:bands not declared in manifest; band role check skipped")

    # --- STAC required fields ---
    # Only enforce STAC field presence when the manifest is already STAC-formatted
    # (has a 'properties' dict, 'stac_version', or 'type: Feature' key).
    # Prepare manifests don't carry these fields directly — they are written into
    # the STAC item at catalog-load time.  Report absent fields as informational
    # notes rather than hard failures for non-STAC manifests.
    is_stac_manifest = bool(
        isinstance(manifest_data.get("properties"), dict)
        or manifest_data.get("stac_version")
        or manifest_data.get("type") in ("Feature", "Collection")
    )
    props_stac: dict = {}
    if isinstance(manifest_data.get("properties"), dict):
        props_stac = manifest_data["properties"]
    for field in spec.stac_required_fields:
        if field in props_stac or field in manifest_data:
            checks.append(f"STAC field {field!r} present")
        elif is_stac_manifest:
            problems.append(
                f"STAC required field {field!r} not found in STAC manifest "
                f"(profile {spec.profile_id!r} requires this field)"
            )
        else:
            checks.append(
                f"STAC field {field!r} not in prepare manifest "
                f"(expected when loaded as a STAC catalog item)"
            )

    # --- SAR GEO-002: no optical vegetation indices ---
    if spec.profile_id == "sar_backscatter":
        advertised_stats: list[str] = []
        props_sar: dict = {}
        if isinstance(manifest_data.get("properties"), dict):
            props_sar = manifest_data["properties"]
        for check_field in ("statistics_roles", "allowed_statistics", "statistics", "indices"):
            for ctx in (manifest_data, props_sar):
                val = ctx.get(check_field)
                if isinstance(val, list):
                    advertised_stats.extend(str(v) for v in val)
                elif isinstance(val, str):
                    advertised_stats.append(val)
        bad_indices = [s for s in advertised_stats if s.upper() in _OPTICAL_INDEX_NAMES]
        if bad_indices:
            problems.append(
                f"GEO-002 violation: SAR manifest advertises optical vegetation indices "
                f"{bad_indices}. SAR sources must not advertise optical index statistics."
            )
        else:
            checks.append("GEO-002: no optical vegetation indices advertised (SAR profile)")

    # --- Context/visual GEO-003: no raw-band field statistics ---
    if spec.profile_id in ("precomputed_context", "visual_only"):
        props_geo003: dict = {}
        if isinstance(manifest_data.get("properties"), dict):
            props_geo003 = manifest_data["properties"]
        found_stats = False
        for check_field in ("statistics_roles", "allowed_statistics"):
            for ctx in (manifest_data, props_geo003):
                val = ctx.get(check_field)
                if isinstance(val, list) and val:
                    found_stats = True
                    break
            if found_stats:
                break
        if found_stats:
            problems.append(
                f"GEO-003 violation: {spec.profile_id!r} manifest advertises "
                f"raw-band field statistics. Context/visual sources are display-only."
            )
        else:
            checks.append(f"GEO-003: no raw-band field statistics advertised ({spec.profile_id!r})")

    ok = len(problems) == 0
    detail = f"profile {spec.profile_id!r}: {len(checks)} check(s) passed" + (
        f", {len(problems)} problem(s): {'; '.join(problems)}"
        if problems
        else ", all checks passed"
    )
    return ManifestValidationResult(
        ok=ok,
        checks=tuple(checks),
        problems=tuple(problems),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Self-check (run as module for quick sanity validation)
# ---------------------------------------------------------------------------


def _selfcheck() -> None:
    """Run basic invariant checks; raise AssertionError on any failure."""
    # All canonical profile IDs must be registered
    for pid in _CANONICAL_PROFILE_IDS:
        assert pid in _PROFILES, f"canonical profile {pid!r} not in _PROFILES"

    # All alias targets must resolve to registered profiles
    for alias, canonical in _ALIAS_MAP.items():
        assert canonical in _PROFILES, f"alias {alias!r} -> {canonical!r} not in _PROFILES"

    # SAR profile must have empty allowed_statistics_roles (GEO-002)
    sar = _PROFILES["sar_backscatter"]
    assert (
        len(sar.allowed_statistics_roles) == 0
    ), "sar_backscatter profile must not allow any statistics roles (GEO-002)"

    # precomputed_context must have empty allowed_statistics_roles (GEO-003)
    ctx = _PROFILES["precomputed_context"]
    assert (
        len(ctx.allowed_statistics_roles) == 0
    ), "precomputed_context profile must not allow field statistics roles (GEO-003)"

    # visual_only must have empty allowed_statistics_roles
    vis = _PROFILES["visual_only"]
    assert (
        len(vis.allowed_statistics_roles) == 0
    ), "visual_only profile must not allow field statistics roles"

    # LISS-3 source override must encode exact REQ-017 invariants
    liss3 = _SOURCE_SPEC_OVERRIDES["resourcesat-2a-liss3-boa"]
    assert liss3.band_count == 4, "LISS-3 must have exactly 4 bands"
    assert liss3.band_roles == (
        "GREEN",
        "RED",
        "NIR",
        "SWIR1",
    ), "LISS-3 band roles must be (BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1)"
    assert liss3.scale == 0.0001, "LISS-3 reflectance scale must be 0.0001"
    assert liss3.offset == 0.0, "LISS-3 reflectance offset must be 0.0 (not -0.1)"
    assert liss3.mask_asset == "mask.tif", "LISS-3 must have a separate mask.tif asset"
    assert liss3.mask_valid_classes == frozenset(
        {1, 4}
    ), "LISS-3 Akasha mask v1 valid classes must be {1, 4}"
    assert liss3.mask_excluded_classes == frozenset(
        {0, 2, 3}
    ), "LISS-3 Akasha mask v1 excluded classes must be {0, 2, 3}"
    assert liss3.allowed_display_roles == frozenset(
        {"NIR", "RED", "GREEN"}
    ), "LISS-3 display must be FCC NIR/RED/GREEN only"
    assert liss3.allowed_statistics_roles == frozenset(
        {"NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"}
    ), "LISS-3 supported statistics must be NDVI, MSAVI, NDMI, NDWI_GREEN_NIR"
    assert "analytic.tif" in liss3.expected_assets, "LISS-3 must require analytic.tif"
    assert "mask.tif" in liss3.expected_assets, "LISS-3 must require mask.tif"

    # All source overrides must reference a valid profile_id
    for src_id, spec in _SOURCE_SPEC_OVERRIDES.items():
        assert (
            spec.profile_id in _CANONICAL_PROFILE_IDS
        ), f"source override {src_id!r} has unknown profile_id {spec.profile_id!r}"

    print(
        f"validation_profiles selfcheck OK: "
        f"{len(_PROFILES)} profiles, {len(_SOURCE_SPEC_OVERRIDES)} source overrides."
    )


if __name__ == "__main__":
    _selfcheck()
