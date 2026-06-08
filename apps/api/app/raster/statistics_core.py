"""Pure-numpy masked index-statistics engine (Slice 2 — Phase 2).

NO file/network I/O lives here on purpose: every input is an in-memory numpy
array, so the offset/scale correction + SCL masking + index math + pixel
accounting are fully unit-testable without a COG, MinIO, or GDAL.

Pixel accounting (data-ingestion-and-satellite-rules.md § Pixel accounting):

    totalPixels       = pixels intersecting the request geometry
    nodataPixels      = out-of-coverage / nodata pixels (analytic nodata OR SCL no_data=0)
    coveragePixels    = totalPixels - nodataPixels
    sclExcludedPixels = pixels excluded by the SCL mask (within coverage)
    validPixels       = coveragePixels - sclExcludedPixels

    validPixelPercent  = validPixels      / totalPixels    * 100
    cloudMaskedPercent = sclExcludedPixels / totalPixels    * 100
    coveragePercent    = coveragePixels   / totalPixels    * 100

Reflectance correction (raw uint16 DN stored):
    corrected = dn * scale + offset   (= dn * 0.0001 - 0.1)
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

SCL_NODATA_CLASS = 0


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
    scl_excluded_pixels: int
    valid_pixels: int
    valid_pixel_percent: float
    cloud_masked_percent: float
    coverage_percent: float
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
            "sclExcludedPixels": self.scl_excluded_pixels,
            "validPixels": self.valid_pixels,
            "validPixelPercent": self.valid_pixel_percent,
            "cloudMaskedPercent": self.cloud_masked_percent,
            "coveragePercent": self.coverage_percent,
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
    """Apply per-band Sentinel-2 L2A reflectance correction: dn * scale + offset."""
    return dn.astype("float64") * float(scale) + float(offset)


def compute_index_statistics(
    *,
    index_type: str,
    band_a_dn: np.ndarray,
    band_b_dn: np.ndarray,
    scl: np.ndarray,
    geometry_mask: np.ndarray,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
    nodata: float | int = 0,
    excluded_scl_classes: tuple[int, ...] = DEFAULT_EXCLUDED_SCL_CLASSES,
) -> IndexStatistics:
    """Compute cloud/SCL-masked, offset-corrected index statistics.

    Parameters
    ----------
    index_type:
        One of the supported index ids (NDVI, NDRE, NDMI, NDWI_GREEN_NIR). Used
        only to label the result; the band arrays are supplied in (a, b) order
        already so this engine stays index-agnostic.
    band_a_dn, band_b_dn:
        Raw DN windows for the index's two bands (same shape).
    index is computed from the formula registered for index_type after reflectance correction.
    scl:
        Scene Classification Layer window (same shape, categorical uint8).
    geometry_mask:
        Boolean window, True where a pixel is INSIDE the request polygon.
    """
    index_def = get_index(index_type)

    a = np.asarray(band_a_dn)
    b = np.asarray(band_b_dn)
    scl = np.asarray(scl)
    geom = np.asarray(geometry_mask, dtype=bool)

    if not (a.shape == b.shape == scl.shape == geom.shape):
        raise ValueError(
            f"shape mismatch: a={a.shape} b={b.shape} scl={scl.shape} geom={geom.shape}"
        )

    warnings: list[str] = []

    total_pixels = int(geom.sum())

    # --- coverage / nodata -------------------------------------------------
    # A pixel is nodata (out of coverage) if either analytic band equals the
    # nodata value OR the SCL marks it as no_data (class 0).
    analytic_nodata = (a == nodata) | (b == nodata)
    scl_nodata = scl == SCL_NODATA_CLASS
    nodata_mask = geom & (analytic_nodata | scl_nodata)
    coverage_mask = geom & ~nodata_mask

    nodata_pixels = int(nodata_mask.sum())
    coverage_pixels = int(coverage_mask.sum())

    # --- SCL exclusion within coverage ------------------------------------
    # Class 0 is already counted as nodata; the remaining excluded classes
    # (1,2,3,7,8,9,10,11 by default) are the "cloud-masked" pixels.
    excluded_within_coverage = tuple(c for c in excluded_scl_classes if c != SCL_NODATA_CLASS)
    scl_excluded_mask = coverage_mask & np.isin(scl, excluded_within_coverage)
    scl_excluded_pixels = int(scl_excluded_mask.sum())

    valid_mask = coverage_mask & ~scl_excluded_mask
    valid_pixels = int(valid_mask.sum())

    # --- index on valid pixels (reflectance corrected) --------------------
    min_v = max_v = mean_v = std_v = None
    if valid_pixels > 0:
        a_ref = correct_reflectance(a[valid_mask], scale, offset)
        b_ref = correct_reflectance(b[valid_mask], scale, offset)
        index_vals, good = _evaluate_index(index_def.formula_kind, a_ref, b_ref)
        if not good.all():
            warnings.append(
                f"{int((~good).sum())} valid pixel(s) could not be evaluated for {index_type} and "
                "were excluded from min/max/mean/stddev."
            )
        index_vals = index_vals[good]
        index_vals = index_vals[np.isfinite(index_vals)]
        if index_vals.size > 0:
            min_v = _round(np.min(index_vals))
            max_v = _round(np.max(index_vals))
            mean_v = _round(np.mean(index_vals))
            std_v = _round(np.std(index_vals))  # population stddev (ddof=0)
        else:  # pragma: no cover - degenerate
            warnings.append("No finite index values after masking.")
    else:
        warnings.append("No valid pixels after nodata + SCL masking for this geometry/date.")

    def pct(numerator: int) -> float:
        return _round((numerator / total_pixels * 100.0) if total_pixels else 0.0, 4) or 0.0

    return IndexStatistics(
        index_type=index_def.id,
        min=min_v,
        max=max_v,
        mean=mean_v,
        stddev=std_v,
        total_pixels=total_pixels,
        nodata_pixels=nodata_pixels,
        coverage_pixels=coverage_pixels,
        scl_excluded_pixels=scl_excluded_pixels,
        valid_pixels=valid_pixels,
        valid_pixel_percent=pct(valid_pixels),
        cloud_masked_percent=pct(scl_excluded_pixels),
        coverage_percent=pct(coverage_pixels),
        warnings=warnings,
    )


def _evaluate_index(
    formula_kind: str,
    a_ref: np.ndarray,
    b_ref: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    denom = a_ref + b_ref
    good = denom != 0
    values = np.full(a_ref.shape, np.nan, dtype="float64")
    values[good] = (a_ref[good] - b_ref[good]) / denom[good]
    return values, good
