"""Supported vegetation/water index registry + STAC band-position mapping.

Akasha keeps index definitions centralized here so routes and UI never hard-code
band formulas. The frozen analytic band order (data-ingestion-and-satellite-rules.md) is:

    pos: 1    2    3    4    5    6    7    8    9
    band:B04  B08  B05  B06  B07  B11  B12  B03  B02

TiTiler expressions are positional (b1, b2, ...), so the BFF must translate
band NAMES to POSITIONS using the STAC `eo:bands` metadata; positions are never
hard-coded outside this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Frozen Wave 1 analytic band order (source of truth mirrored from STAC eo:bands).
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

# True-colour RGB uses analytic bands [1, 8, 9] = (B04 Red, B03 Green, B02 Blue).
# Do NOT assume RGB = bands 1,2,3.
RGB_BAND_NAMES: list[str] = ["B04", "B03", "B02"]

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
    formula_kind: Literal["normalized_difference", "msavi", "reci"]
    band_a: str
    band_b: str | None = None

    @property
    def formula(self) -> str:
        if self.formula_kind == "msavi":
            return "(2 * B08 + 1 - sqrt((2 * B08 + 1)^2 - 8 * (B08 - B04))) / 2"
        if self.formula_kind == "reci":
            return "(B08 / B05) - 1"
        if self.band_b is None:  # pragma: no cover - registry guard
            raise ValueError(f"{self.id} requires band_b")
        return f"({self.band_a} - {self.band_b}) / ({self.band_a} + {self.band_b})"

    @property
    def required_bands(self) -> tuple[str, ...]:
        return (self.band_a,) if self.band_b is None else (self.band_a, self.band_b)


# Supported indices (data-ingestion-and-satellite-rules.md § Supported index formulas).
INDEX_REGISTRY: dict[str, IndexDef] = {
    "NDVI": IndexDef("NDVI", "NDVI", "normalized_difference", "B08", "B04"),
    "NDRE": IndexDef("NDRE", "NDRE", "normalized_difference", "B08", "B05"),
    "NDMI": IndexDef("NDMI", "NDMI (vegetation moisture)", "normalized_difference", "B08", "B11"),
    "NDWI_GREEN_NIR": IndexDef(
        "NDWI_GREEN_NIR",
        "Water NDWI (McFeeters)",
        "normalized_difference",
        "B03",
        "B08",
    ),
    "MSAVI": IndexDef("MSAVI", "MSAVI", "msavi", "B08", "B04"),
    "RECI": IndexDef("RECI", "RECI", "reci", "B08", "B05"),
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


def rgb_band_positions(band_names: list[str]) -> list[int]:
    """Return the 1-based positions of (B04, B03, B02) for true-colour display."""
    mapping = band_name_to_position(band_names)
    return [mapping[name] for name in RGB_BAND_NAMES]
