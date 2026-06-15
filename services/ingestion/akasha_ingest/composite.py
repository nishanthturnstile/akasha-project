"""ResourceSat LISS-3 composite helpers.

This module keeps the Phase 2b core deterministic and testable. Raster IO and
reprojection are wired in later; the pixel-selection rules here operate on
already aligned analytic and mask arrays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

RESOURCE_SAT_VALID_MASK_CLASSES = frozenset({1, 4})
RESOURCE_SAT_EXCLUDED_MASK_CLASSES = frozenset({0, 2, 3})


@dataclass(frozen=True)
class CompositeGrid:
    crs: str
    bounds: tuple[float, float, float, float]
    resolution: float
    width: int
    height: int
    transform: tuple[float, float, float, float, float, float, float, float, float]

    @classmethod
    def from_projected_bounds(
        cls,
        bounds: tuple[float, float, float, float] | list[float],
        *,
        crs: str = "EPSG:32643",
        resolution: float = 24.0,
        padding_pixels: int = 0,
    ) -> CompositeGrid:
        if len(bounds) != 4:
            raise ValueError("grid bounds must contain west, south, east, north")
        west, south, east, north = [float(value) for value in bounds]
        if west >= east or south >= north:
            raise ValueError(f"invalid projected bounds: {bounds}")
        if resolution <= 0:
            raise ValueError("grid resolution must be positive")
        pad = max(0, int(padding_pixels)) * resolution
        west = math.floor((west - pad) / resolution) * resolution
        south = math.floor((south - pad) / resolution) * resolution
        east = math.ceil((east + pad) / resolution) * resolution
        north = math.ceil((north + pad) / resolution) * resolution
        width = int(round((east - west) / resolution))
        height = int(round((north - south) / resolution))
        return cls(
            crs=crs,
            bounds=(west, south, east, north),
            resolution=resolution,
            width=width,
            height=height,
            transform=(resolution, 0.0, west, 0.0, -resolution, north, 0.0, 0.0, 1.0),
        )


@dataclass(frozen=True)
class AlignedScene:
    scene_id: str
    acquisition_datetime: str
    analytic: Any
    mask: Any

    @property
    def timestamp(self) -> datetime:
        value = self.acquisition_datetime
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)


def _as_scene_arrays(scene: AlignedScene) -> tuple[np.ndarray, np.ndarray]:
    analytic = np.asarray(scene.analytic)
    mask = np.asarray(scene.mask)
    if analytic.ndim != 3:
        raise ValueError(f"{scene.scene_id}: analytic array must be band,height,width")
    if analytic.shape[0] != 4:
        raise ValueError(f"{scene.scene_id}: ResourceSat analytic array must have 4 bands")
    if mask.ndim != 2:
        raise ValueError(f"{scene.scene_id}: mask array must be height,width")
    if analytic.shape[1:] != mask.shape:
        raise ValueError(
            f"{scene.scene_id}: analytic/mask shape mismatch "
            f"{analytic.shape[1:]} != {mask.shape}"
        )
    return analytic, mask


def _valid_pixels(mask: np.ndarray) -> np.ndarray:
    return np.isin(mask, list(RESOURCE_SAT_VALID_MASK_CLASSES))


def build_best_available_composite(scenes: list[AlignedScene]) -> dict[str, Any]:
    """Merge aligned scenes using Phase 2b's most-recent valid-pixel rule."""
    if not scenes:
        raise ValueError("at least one aligned scene is required")

    ordered = sorted(scenes, key=lambda scene: scene.timestamp)
    first_analytic, first_mask = _as_scene_arrays(ordered[0])
    output_analytic = np.zeros_like(first_analytic)
    output_mask = np.zeros_like(first_mask, dtype=np.uint8)
    output_scene_index = np.full(first_mask.shape, -1, dtype=np.int16)
    has_any = np.zeros(first_mask.shape, dtype=bool)
    has_valid = np.zeros(first_mask.shape, dtype=bool)

    for index, scene in enumerate(ordered):
        analytic, mask = _as_scene_arrays(scene)
        if analytic.shape != first_analytic.shape:
            raise ValueError(f"{scene.scene_id}: shape does not match first scene")
        valid = _valid_pixels(mask)
        any_coverage = mask != 0

        fallback_take = any_coverage & ~has_any
        valid_take = valid
        take = fallback_take | valid_take
        if not np.any(take):
            continue

        output_analytic[:, take] = analytic[:, take]
        output_scene_index[take] = index
        output_mask[fallback_take & ~valid] = mask[fallback_take & ~valid]
        output_mask[valid_take] = mask[valid_take]
        has_any |= any_coverage
        has_valid |= valid

    output_mask[~has_any] = 0
    invalid_output = has_any & ~has_valid
    output_mask[invalid_output] = np.where(
        output_mask[invalid_output] == 0,
        2,
        output_mask[invalid_output],
    )

    total_pixels = output_mask.size
    coverage_pixels = int(np.count_nonzero(has_any))
    usable_pixels = int(np.count_nonzero(_valid_pixels(output_mask)))
    cloud_pixels = int(np.count_nonzero(output_mask == 2))
    metrics = {
        "coverage_percent": round(coverage_pixels * 100.0 / total_pixels, 4),
        "usable_pixel_percent": round(usable_pixels * 100.0 / total_pixels, 4),
        "cloud_masked_percent": round(cloud_pixels * 100.0 / total_pixels, 4),
        "contributing_scenes": [
            {"id": scene.scene_id, "datetime": scene.acquisition_datetime} for scene in ordered
        ],
    }
    return {
        "analytic": output_analytic,
        "mask": output_mask,
        "source_scene_index": output_scene_index,
        "metrics": metrics,
    }
