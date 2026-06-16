"""Supported vegetation/water index registry + STAC band-position mapping.

Akasha keeps index definitions centralized here so routes and UI never hard-code
band formulas. Sentinel compatibility keeps the original 9-band analytic order:

    pos: 1    2    3    4    5    6    7    8    9
    band:B04  B08  B05  B06  B07  B11  B12  B03  B02

TiTiler expressions are positional (b1, b2, ...), so the BFF must translate
band NAMES to POSITIONS using the STAC `eo:bands` metadata; positions are never
hard-coded outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Legacy Sentinel analytic band order (source of truth mirrored from STAC eo:bands).
FROZEN_ANALYTIC_BANDS: list[str] = [
    "B04",
    "B08",
    "B05",
    "B06",
    "B07",
    "B11",
    "B12",
    "B03",
    "B02",
]

# Sentinel true-colour RGB uses analytic bands [1, 8, 9] = (B04 Red, B03 Green, B02 Blue).
# Do NOT assume RGB = bands 1,2,3.
RGB_BAND_NAMES: list[str] = ["B04", "B03", "B02"]
FCC_ROLE_ORDER: list[str] = ["NIR", "RED", "GREEN"]

SpectralRole = Literal["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2", "RED_EDGE"]
FormulaKind = Literal["normalized_difference", "msavi"]

# Default excluded SCL classes (water class 6 kept by default).
DEFAULT_EXCLUDED_SCL_CLASSES: tuple[int, ...] = (0, 1, 2, 3, 7, 8, 9, 10, 11)

# Sentinel-2 L2A reflectance correction (raw uint16 DN stored).
#   corrected = dn * scale + offset = dn * 0.0001 - 0.1
DEFAULT_SCALE: float = 0.0001
DEFAULT_OFFSET: float = -0.1


@dataclass(frozen=True)
class IndexDef:
    """Formula and band requirements for one supported index."""

    id: str
    label: str
    formula_kind: FormulaKind
    role_a: SpectralRole
    role_b: SpectralRole
    # Display colorization for index map tiles (TiTiler colormap_name + rescale).
    # display_colormap is a rio-tiler/TiTiler colormap name; display_rescale is the
    # (min, max) index-value range the colormap is stretched across.
    display_colormap: str = "rdylgn"
    display_rescale: tuple[float, float] = (-1.0, 1.0)

    @property
    def formula(self) -> str:
        if self.formula_kind == "msavi":
            return (
                f"(2 * {self.role_a} + 1 - sqrt((2 * {self.role_a} + 1)^2 "
                f"- 8 * ({self.role_a} - {self.role_b}))) / 2"
            )
        return f"({self.role_a} - {self.role_b}) / ({self.role_a} + {self.role_b})"

    @property
    def required_roles(self) -> tuple[SpectralRole, ...]:
        return (self.role_a, self.role_b)

    @property
    def display_rescale_str(self) -> str:
        """rescale formatted as the "min,max" string TiTiler expects."""
        lo, hi = self.display_rescale
        return f"{lo},{hi}"


# Supported indices (data-ingestion-and-satellite-rules.md § Supported index formulas).
INDEX_REGISTRY: dict[str, IndexDef] = {
    "NDVI": IndexDef(
        "NDVI", "NDVI", "normalized_difference", "NIR", "RED",
        display_colormap="rdylgn", display_rescale=(-0.2, 0.9),
    ),
    "MSAVI": IndexDef(
        "MSAVI", "MSAVI", "msavi", "NIR", "RED",
        display_colormap="rdylgn", display_rescale=(0.0, 1.0),
    ),
    "NDRE": IndexDef(
        "NDRE", "NDRE", "normalized_difference", "NIR", "RED_EDGE",
        display_colormap="rdylgn", display_rescale=(-0.2, 0.9),
    ),
    "NDMI": IndexDef(
        "NDMI", "NDMI (vegetation moisture)", "normalized_difference", "NIR", "SWIR1",
        display_colormap="rdbu", display_rescale=(-0.5, 0.6),
    ),
    "NDWI_GREEN_NIR": IndexDef(
        "NDWI_GREEN_NIR",
        "Water NDWI (McFeeters)",
        "normalized_difference",
        "GREEN",
        "NIR",
        display_colormap="rdbu",
        display_rescale=(-0.5, 0.6),
    ),
}

SUPPORTED_INDICES: list[str] = list(INDEX_REGISTRY.keys())
DEFAULT_INDEX: str = "NDVI"


def get_index(index_type: str) -> IndexDef:
    """Return the IndexDef for an index id, raising KeyError if unsupported."""
    try:
        return INDEX_REGISTRY[index_type]
    except KeyError as exc:  # pragma: no cover - trivial
        raise KeyError(index_type) from exc


def band_name_to_position(band_names: list[str]) -> dict[str, int]:
    """Map band NAME -> 1-based position using the ordered eo:bands list.

    Positions are 1-based to match GDAL/rasterio band indexing and TiTiler `bN`
    expressions.
    """
    return {name: pos for pos, name in enumerate(band_names, start=1)}


def role_to_position(
    band_names: list[str],
    band_role_mapping: dict[str, str],
) -> dict[str, int]:
    """Map spectral role -> 1-based band position for a source analytic asset."""
    name_to_pos = band_name_to_position(band_names)
    role_positions: dict[str, int] = {}
    for role, band_name in band_role_mapping.items():
        if band_name in name_to_pos:
            role_positions[role] = name_to_pos[band_name]
    return role_positions


def index_band_positions(
    band_names: list[str],
    band_role_mapping: dict[str, str],
    index_def: IndexDef,
) -> tuple[int, int, tuple[str, str]]:
    """Resolve an index's required spectral roles to asset positions and names."""
    name_to_pos = band_name_to_position(band_names)
    resolved_names: list[str] = []
    positions: list[int] = []
    for role in index_def.required_roles:
        band_name = band_role_mapping[role]
        resolved_names.append(band_name)
        positions.append(name_to_pos[band_name])
    return positions[0], positions[1], (resolved_names[0], resolved_names[1])


def rgb_band_positions(band_names: list[str]) -> list[int]:
    """Return the 1-based positions of (B04, B03, B02) for true-colour display."""
    mapping = band_name_to_position(band_names)
    return [mapping[name] for name in RGB_BAND_NAMES]


def fcc_band_positions(band_names: list[str], band_role_mapping: dict[str, str]) -> list[int]:
    """Return 1-based positions for false-colour composite (NIR, Red, Green)."""
    role_positions = role_to_position(band_names, band_role_mapping)
    return [role_positions[role] for role in FCC_ROLE_ORDER]


def _corrected_band(position: int, scale: float, offset: float) -> str:
    """TiTiler/numexpr sub-expression for one reflectance-corrected band.

    TiTiler expressions run on raw DN, so the per-band reflectance correction
    (dn * scale + offset) is baked into the expression. The offset does NOT cancel
    in a normalized-difference denominator, so it must be applied per band here —
    keeping display tiles consistent with the BFF statistics engine.
    """
    return f"({scale}*b{position}{offset:+})"


def index_tile_expression(
    band_names: list[str],
    band_role_mapping: dict[str, str],
    index_def: IndexDef,
    *,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
) -> str:
    """Build a TiTiler band-math expression for a colorized index display tile.

    Resolves the index's spectral roles to 1-based band positions, then emits a
    reflectance-corrected normalized-difference (or MSAVI) expression. Raises
    KeyError if the asset lacks a band required for the index.
    """
    pos_a, pos_b, _names = index_band_positions(band_names, band_role_mapping, index_def)
    a = _corrected_band(pos_a, scale, offset)
    b = _corrected_band(pos_b, scale, offset)
    if index_def.formula_kind == "msavi":
        return f"(2*{a}+1-sqrt((2*{a}+1)**2-8*({a}-{b})))/2"
    return f"({a}-{b})/({a}+{b})"
