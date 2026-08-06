"""Pure-numpy masked index-statistics engine (Slice 2 - Phase 2).

NO file/network I/O lives here on purpose: every input is an in-memory numpy
array, so the offset/scale correction + source-mask filtering + index math + pixel
accounting are fully unit-testable without a COG, MinIO, or GDAL.

Pixel accounting:

    totalPixels       = pixels intersecting the request geometry
    nodataPixels      = out-of-coverage / nodata pixels
    coveragePixels    = totalPixels - nodataPixels
    maskedPixels      = pixels excluded by the source mask (within coverage)
    validPixels       = coveragePixels - maskedPixels

    validPixelPercent  = validPixels      / totalPixels    * 100
    cloudMaskedPercent = maskedPixels     / totalPixels    * 100
    coveragePercent    = coveragePixels   / totalPixels    * 100

Reflectance correction (raw uint16 DN stored):
    corrected = dn * scale + offset
The offset does NOT cancel in a normalized-difference index because it biases
the denominator; correction is therefore applied BEFORE the index is computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .indices import (
    DEFAULT_EXCLUDED_SCL_CLASSES,
    DEFAULT_OFFSET,
    DEFAULT_SCALE,
    get_index,
)
from .value_split import IndexValueSplitPayload, compute_ndvi_value_split

MASK_NODATA_CLASS = 0


@dataclass
class IndexStatistics:
    """Normalized statistics + pixel accounting for one masked index request."""

    index_type: str
    min: float | None
    max: float | None
    mean: float | None
    stddev: float | None
    total_pixels: int
    nodata_pixels: int
    coverage_pixels: int
    masked_pixels: int
    valid_pixels: int
    valid_pixel_percent: float
    cloud_masked_percent: float
    coverage_percent: float
    value_split: IndexValueSplitPayload | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "indexType": self.index_type,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "stddev": self.stddev,
            "totalPixels": self.total_pixels,
            "nodataPixels": self.nodata_pixels,
            "coveragePixels": self.coverage_pixels,
            "maskedPixels": self.masked_pixels,
            "validPixels": self.valid_pixels,
            "validPixelPercent": self.valid_pixel_percent,
            "cloudMaskedPercent": self.cloud_masked_percent,
            "coveragePercent": self.coverage_percent,
            "valueSplit": self.value_split,
            "warnings": list(self.warnings),
        }


def _round(value: float | None, ndigits: int = 6) -> float | None:
    if value is None:
        return None
    if not np.isfinite(value):
        return None
    return float(round(float(value), ndigits))


def correct_reflectance(
    dn: np.ndarray, scale: float = DEFAULT_SCALE, offset: float = DEFAULT_OFFSET
) -> np.ndarray:
    """Apply per-band source reflectance correction: dn * scale + offset."""
    return dn.astype("float64") * float(scale) + float(offset)


def compute_index_statistics(
    *,
    index_type: str,
    band_a_dn: np.ndarray,
    band_b_dn: np.ndarray,
    mask: np.ndarray,
    geometry_mask: np.ndarray,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
    nodata: float | int = 0,
    excluded_mask_classes: tuple[int, ...] = DEFAULT_EXCLUDED_SCL_CLASSES,
    analytic_nodata_policy: str = "selected_band_or_mask",
) -> IndexStatistics:
    """Compute source-mask-aware, offset-corrected index statistics.

    Parameters
    ----------
    index_type:
        One of the supported index ids (NDVI, NDRE, NDMI, NDWI_GREEN_NIR). Used
        only to label the result; the band arrays are supplied in (a, b) order
        already so this engine stays index-agnostic.
    band_a_dn, band_b_dn:
        Raw DN windows for the index's two bands (same shape).
    index is computed from the formula registered for index_type after reflectance correction.
    mask:
        Source mask window (same shape, categorical uint8).
    geometry_mask:
        Boolean window, True where a pixel is INSIDE the request polygon.
    """
    index_def = get_index(index_type)

    a = np.asarray(band_a_dn)
    b = np.asarray(band_b_dn)
    mask = np.asarray(mask)
    geom = np.asarray(geometry_mask, dtype=bool)

    if not (a.shape == b.shape == mask.shape == geom.shape):
        raise ValueError(
            f"shape mismatch: a={a.shape} b={b.shape} mask={mask.shape} geom={geom.shape}"
        )

    warnings: list[str] = []

    total_pixels = int(geom.sum())

    # --- coverage / nodata -------------------------------------------------
    mask_nodata = mask == MASK_NODATA_CLASS
    if analytic_nodata_policy == "mask_only":
        analytic_nodata = np.zeros(a.shape, dtype=bool)
    elif analytic_nodata_policy == "selected_band_or_mask":
        # Sentinel-style products still use selected-band nodata in addition
        # to the source categorical mask.
        analytic_nodata = (a == nodata) | (b == nodata)
    else:
        raise ValueError(f"unknown analytic_nodata_policy: {analytic_nodata_policy}")
    nodata_mask = geom & (analytic_nodata | mask_nodata)
    coverage_mask = geom & ~nodata_mask

    nodata_pixels = int(nodata_mask.sum())
    coverage_pixels = int(coverage_mask.sum())

    # --- source mask exclusion within coverage ----------------------------
    # Class 0 is already counted as nodata; remaining source-declared excluded
    # classes are the masked pixels.
    excluded_within_coverage = tuple(c for c in excluded_mask_classes if c != MASK_NODATA_CLASS)
    mask_excluded_mask = coverage_mask & np.isin(mask, excluded_within_coverage)
    masked_pixels = int(mask_excluded_mask.sum())

    valid_mask = coverage_mask & ~mask_excluded_mask
    valid_pixels = int(valid_mask.sum())

    # --- index on valid pixels (reflectance corrected) --------------------
    min_v = max_v = mean_v = std_v = None
    finite_index_values = np.array([], dtype="float64")
    if valid_pixels > 0:
        a_ref = correct_reflectance(a[valid_mask], scale, offset)
        b_ref = correct_reflectance(b[valid_mask], scale, offset)
        index_vals, good = evaluate_index_values(index_def.formula_kind, a_ref, b_ref)
        if not good.all():
            warnings.append(
                f"{int((~good).sum())} valid pixel(s) could not be evaluated for {index_type} and "
                "were excluded from min/max/mean/stddev."
            )
        index_vals = index_vals[good]
        finite_index_values = index_vals[np.isfinite(index_vals)]
        if finite_index_values.size > 0:
            min_v = _round(np.min(finite_index_values))
            max_v = _round(np.max(finite_index_values))
            mean_v = _round(np.mean(finite_index_values))
            std_v = _round(np.std(finite_index_values))  # population stddev (ddof=0)
        else:  # pragma: no cover - degenerate
            warnings.append("No finite index values after masking.")
    else:
        warnings.append(
            "No valid pixels after nodata + source-mask filtering for this geometry/date."
        )

    def pct(numerator: int) -> float:
        return _round((numerator / total_pixels * 100.0) if total_pixels else 0.0, 4) or 0.0

    value_split = None
    if index_def.id == "NDVI":
        value_split = compute_ndvi_value_split(
            values=finite_index_values,
            masked_pixel_count=masked_pixels,
            total_pixel_count=total_pixels,
            nodata_pixel_count=nodata_pixels,
            valid_pixel_count=valid_pixels,
        )

    return IndexStatistics(
        index_type=index_def.id,
        min=min_v,
        max=max_v,
        mean=mean_v,
        stddev=std_v,
        total_pixels=total_pixels,
        nodata_pixels=nodata_pixels,
        coverage_pixels=coverage_pixels,
        masked_pixels=masked_pixels,
        valid_pixels=valid_pixels,
        valid_pixel_percent=pct(valid_pixels),
        cloud_masked_percent=pct(masked_pixels),
        coverage_percent=pct(coverage_pixels),
        value_split=value_split,
        warnings=warnings,
    )


def evaluate_index_values(
    formula_kind: str,
    a_ref: np.ndarray,
    b_ref: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate one index formula on reflectance-corrected arrays.

    Returns `(values, good_mask)` where `good_mask` marks pixels whose formula
    denominator/radicand was mathematically valid. Keeping this helper exported
    lets statistics, overlay rendering, and hover point-readout share exactly the
    same formula implementation.
    """
    if formula_kind == "msavi":
        term = 2 * a_ref + 1
        radicand = term**2 - 8 * (a_ref - b_ref)
        good = radicand >= 0
        values = np.full(a_ref.shape, np.nan, dtype="float64")
        values[good] = (term[good] - np.sqrt(radicand[good])) / 2
        return values, good

    denom = a_ref + b_ref
    good = denom != 0
    values = np.full(a_ref.shape, np.nan, dtype="float64")
    values[good] = (a_ref[good] - b_ref[good]) / denom[good]
    return values, good
