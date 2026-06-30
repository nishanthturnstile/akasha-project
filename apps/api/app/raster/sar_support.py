"""EOS-04 SAR support for cloudy optical field analytics.

This module intentionally does not derive NDVI or any optical index from SAR.
It resolves a nearby EOS-04 backscatter COG, reads field-clipped dB values, and
returns contextual support metadata that callers can show separately from true
optical statistics.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from ..config import settings
from . import catalog_resolver as catalog
from .raster_reader import gdal_s3_options, rasterio_aws_session, to_gdal_path

EOS04_SAR_SOURCE_ID = catalog.EOS04_SAR_SOURCE_ID


def compute_sar_support(
    *,
    geometry: dict[str, Any],
    optical_source_id: str,
    optical_acquisition_date: str,
    optical_cloud_masked_percent: float | None,
    optical_masked_pixels: int | None,
    geometry_bounds: list[float] | tuple[float, float, float, float] | None = None,
    window_days: int | None = None,
    cloud_threshold_percent: float | None = None,
) -> dict[str, Any]:
    """Return EOS-04 SAR support metadata for one optical field observation.

    The function is fail-soft: SAR lookup/read failures return
    ``available=false`` instead of failing the optical statistics request.
    """
    resolved_window_days = int(
        window_days if window_days is not None else settings.sar_support_window_days
    )
    threshold = float(
        cloud_threshold_percent
        if cloud_threshold_percent is not None
        else settings.sar_support_cloud_threshold_percent
    )
    cloud_percent = _as_float(optical_cloud_masked_percent)
    masked_pixels = int(optical_masked_pixels or 0)
    cloud_gap = (cloud_percent or 0.0) >= threshold or (
        masked_pixels > 0 and (cloud_percent or 0.0) > 0.0
    )
    base = {
        "available": False,
        "status": "unavailable",
        "sourceId": EOS04_SAR_SOURCE_ID,
        "acquisitionDate": None,
        "daysFromOpticalDate": None,
        "windowDays": resolved_window_days,
        "cloudGap": cloud_gap,
        "opticalCloudMaskedPercent": cloud_percent,
        "opticalMaskedPixels": masked_pixels,
        "polarizations": [],
        "coveragePercent": None,
        "confidence": "none",
        "reason": None,
        "bands": [],
        "wetnessSignal": "not_assessed",
        "changeSignal": "not_assessed",
    }

    if optical_source_id == EOS04_SAR_SOURCE_ID:
        return {
            **base,
            "status": "not_applicable",
            "reason": "SAR support is only attached to optical source statistics.",
        }
    if not cloud_gap:
        return {
            **base,
            "status": "not_needed",
            "reason": "Optical observation is not cloud/mask limited.",
        }

    try:
        optical_day = date.fromisoformat(optical_acquisition_date)
    except ValueError:
        return {
            **base,
            "status": "invalid_optical_date",
            "reason": "Optical acquisition date is invalid.",
        }

    try:
        candidates = _candidate_dates(
            optical_day=optical_day,
            geometry_bounds=geometry_bounds,
            window_days=resolved_window_days,
        )
    except Exception:  # noqa: BLE001 - degrade; optical stats remain authoritative.
        return {**base, "status": "catalog_unavailable", "reason": "SAR catalog lookup failed."}

    if not candidates:
        return {
            **base,
            "status": "no_scene",
            "reason": "No EOS-04 scene is available near this optical date.",
        }

    last_status = "unavailable"
    last_reason = "No intersecting EOS-04 scene could be read for this field."
    for day, days_from_optical in candidates:
        try:
            assets = catalog.resolve_assets(EOS04_SAR_SOURCE_ID, day.isoformat())
            stats = _read_sar_statistics(
                backscatter_href=assets["backscatterHref"],
                band_names=list(assets.get("bandNames") or []),
                geometry=geometry,
                nodata=assets.get("nodata", -9999.0),
            )
        except Exception:  # noqa: BLE001 - try next candidate, then fail-soft.
            last_status = "read_failed"
            last_reason = "EOS-04 backscatter COG could not be read for this field."
            continue

        if not stats["intersects"]:
            last_status = "no_overlap"
            last_reason = "Nearest EOS-04 scene does not overlap this field."
            continue
        if not _has_valid_sar_pixels(stats):
            last_status = "no_valid_pixels"
            last_reason = "EOS-04 scene overlaps this field but has no valid backscatter pixels."
            continue

        polarizations = _polarizations_from_band_names(assets.get("bandNames") or [])
        return {
            **base,
            "available": True,
            "status": "available",
            "acquisitionDate": day.isoformat(),
            "daysFromOpticalDate": days_from_optical,
            "polarizations": polarizations,
            "coveragePercent": stats["coveragePercent"],
            "confidence": _confidence(days_from_optical, stats["coveragePercent"]),
            "reason": "EOS-04 SAR support is available for cloudy/masked optical pixels.",
            "bands": stats["bands"],
        }

    return {**base, "status": last_status, "reason": last_reason}


def _candidate_dates(
    *,
    optical_day: date,
    geometry_bounds: list[float] | tuple[float, float, float, float] | None,
    window_days: int,
) -> list[tuple[date, int]]:
    candidates: list[tuple[date, int]] = []
    for entry in catalog.list_dates(EOS04_SAR_SOURCE_ID):
        raw_date = entry.get("acquisitionDate")
        if not isinstance(raw_date, str):
            continue
        try:
            sar_day = date.fromisoformat(raw_date)
        except ValueError:
            continue
        delta = (sar_day - optical_day).days
        if abs(delta) > window_days:
            continue
        if geometry_bounds is not None and not _bbox_intersects(
            entry.get("bounds"), geometry_bounds
        ):
            continue
        candidates.append((sar_day, delta))
    candidates.sort(key=lambda item: (abs(item[1]), item[0]), reverse=False)
    return candidates


def _read_sar_statistics(
    *,
    backscatter_href: str,
    band_names: list[str],
    geometry: dict[str, Any],
    nodata: float | int | None,
) -> dict[str, Any]:
    try:
        import numpy as np  # lazy
        import rasterio  # lazy
        from rasterio.features import bounds as feature_bounds
        from rasterio.features import geometry_mask
        from rasterio.warp import transform_geom
        from rasterio.windows import Window
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Raster stack is unavailable for SAR support.") from exc

    path = to_gdal_path(backscatter_href)
    try:
        with rasterio.Env(rasterio_aws_session(), **gdal_s3_options()):
            with rasterio.open(path) as dataset:
                geom_ds = transform_geom("EPSG:4326", dataset.crs, geometry)
                minx, miny, maxx, maxy = feature_bounds(geom_ds)
                inv = ~dataset.transform
                c0, r0 = inv * (minx, maxy)
                c1, r1 = inv * (maxx, miny)
                col_off = max(0, int(math.floor(min(c0, c1))))
                row_off = max(0, int(math.floor(min(r0, r1))))
                col_end = min(dataset.width, int(math.ceil(max(c0, c1))))
                row_end = min(dataset.height, int(math.ceil(max(r0, r1))))
                width = col_end - col_off
                height = row_end - row_off
                if width <= 0 or height <= 0:
                    return {"intersects": False, "coveragePercent": 0.0, "bands": []}

                window = Window(col_off, row_off, width, height)
                transform = dataset.window_transform(window)
                geom_mask = geometry_mask(
                    [geom_ds], out_shape=(height, width), transform=transform, invert=True
                )
                geometry_pixels = int(np.count_nonzero(geom_mask))
                if geometry_pixels <= 0:
                    return {"intersects": False, "coveragePercent": 0.0, "bands": []}

                resolved_nodata = dataset.nodata if dataset.nodata is not None else nodata
                bands: list[dict[str, Any]] = []
                union_valid = np.zeros((height, width), dtype=bool)
                count = min(dataset.count, max(1, len(band_names) or dataset.count))
                for band_index in range(1, count + 1):
                    arr = dataset.read(band_index, window=window).astype("float64")
                    valid = geom_mask & np.isfinite(arr)
                    if resolved_nodata is not None:
                        valid &= arr != float(resolved_nodata)
                    union_valid |= valid
                    values = arr[valid]
                    name = (
                        band_names[band_index - 1]
                        if band_index - 1 < len(band_names)
                        else f"B{band_index}"
                    )
                    bands.append(_band_stats(name, values, geometry_pixels))

                coverage = round(100.0 * int(np.count_nonzero(union_valid)) / geometry_pixels, 2)
                return {"intersects": True, "coveragePercent": coverage, "bands": bands}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SAR COG window read failed.") from exc


def _band_stats(name: str, values: Any, geometry_pixels: int) -> dict[str, Any]:
    if values.size == 0:
        return {
            "name": name,
            "min": None,
            "max": None,
            "mean": None,
            "stddev": None,
            "validPixelPercent": 0.0,
        }
    return {
        "name": name,
        "min": round(float(values.min()), 6),
        "max": round(float(values.max()), 6),
        "mean": round(float(values.mean()), 6),
        "stddev": round(float(values.std()), 6),
        "validPixelPercent": round(100.0 * int(values.size) / max(1, geometry_pixels), 2),
    }


def _has_valid_sar_pixels(stats: dict[str, Any]) -> bool:
    try:
        if float(stats.get("coveragePercent") or 0.0) <= 0.0:
            return False
    except (TypeError, ValueError):
        return False
    bands = stats.get("bands")
    if not isinstance(bands, list) or not bands:
        return False
    return any((band or {}).get("mean") is not None for band in bands if isinstance(band, dict))


def _confidence(days_from_optical: int, coverage_percent: float | None) -> str:
    coverage = float(coverage_percent or 0.0)
    delta = abs(days_from_optical)
    if delta <= 3 and coverage >= 70.0:
        return "high"
    if delta <= 7 and coverage >= 40.0:
        return "medium"
    return "low"


def _polarizations_from_band_names(band_names: list[str]) -> list[str]:
    known = {"HH", "HV", "VH", "VV", "RH", "RV"}
    polarizations: list[str] = []
    for name in band_names:
        tokens = [token for token in str(name).upper().replace("-", "_").split("_") if token]
        match = next((token for token in tokens if token in known), None)
        if match and match not in polarizations:
            polarizations.append(match)
    return polarizations


def _bbox_intersects(
    bbox: Any,
    geometry_bounds: list[float] | tuple[float, float, float, float],
) -> bool:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return True
    try:
        minx, miny, maxx, maxy = (float(value) for value in bbox)
        geom_minx, geom_miny, geom_maxx, geom_maxy = (float(value) for value in geometry_bounds)
    except (TypeError, ValueError):
        return True
    return not (maxx < geom_minx or geom_maxx < minx or maxy < geom_miny or geom_maxy < miny)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
