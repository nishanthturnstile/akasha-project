"""Versioned NDVI vegetation-density distribution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

import numpy as np

NDVI_VALUE_SPLIT_PROFILE_ID = "ndvi-density-v1"
NDVI_VALUE_SPLIT_THRESHOLDS = (0.2, 0.4, 0.6)


class ValueSplitCategoryPayload(TypedDict):
    id: str
    label: str
    minInclusive: float | None
    maxExclusive: float | None
    pixelCount: int | None
    areaSqM: float | None
    percentage: float


class IndexValueSplitPayload(TypedDict):
    indexType: Literal["NDVI"]
    profileId: str
    percentageBasis: Literal["classifiablePixels"]
    thresholds: list[float]
    totalPixels: int | None
    classifiablePixels: int | None
    noDataPixels: int | None
    unclassifiedPixels: int | None
    categories: list[ValueSplitCategoryPayload]


@dataclass(frozen=True, slots=True)
class ValueSplitCategorySpec:
    id: str
    label: str
    min_inclusive: float | None
    max_exclusive: float | None
    source_bin: int | None


NDVI_VALUE_SPLIT_CATEGORIES = (
    ValueSplitCategorySpec("denseVegetation", "Dense vegetation", 0.6, None, 3),
    ValueSplitCategorySpec("moderateVegetation", "Moderate vegetation", 0.4, 0.6, 2),
    ValueSplitCategorySpec("sparseVegetation", "Sparse vegetation", 0.2, 0.4, 1),
    ValueSplitCategorySpec("openSoil", "Open soil", None, 0.2, 0),
    ValueSplitCategorySpec("cloudiness", "Cloudiness", None, None, None),
)

_PIPELINE_CATEGORY_ALIASES = {
    "dense": "denseVegetation",
    "densevegetation": "denseVegetation",
    "dense_vegetation": "denseVegetation",
    "moderate": "moderateVegetation",
    "moderatevegetation": "moderateVegetation",
    "moderate_vegetation": "moderateVegetation",
    "sparse": "sparseVegetation",
    "sparsevegetation": "sparseVegetation",
    "sparse_vegetation": "sparseVegetation",
    "opensoil": "openSoil",
    "open_soil": "openSoil",
    "bare_soil": "openSoil",
    "cloud": "cloudiness",
    "clouds": "cloudiness",
    "cloudiness": "cloudiness",
    "cloud_shadow": "cloudiness",
    "cloud_shadows": "cloudiness",
    "cirrus": "cloudiness",
}


def _percentages_totaling_100(counts: list[int]) -> list[float]:
    total = sum(counts)
    if total <= 0:
        return [0.0] * len(counts)

    basis_points = [(count * 10_000) // total for count in counts]
    remainders = [(count * 10_000) % total for count in counts]
    missing = 10_000 - sum(basis_points)
    order = sorted(range(len(counts)), key=lambda index: (-remainders[index], index))
    for index in order[:missing]:
        basis_points[index] += 1
    return [value / 100 for value in basis_points]


def _weighted_percentages_totaling_100(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return [0.0] * len(weights)

    exact = [weight * 10_000 / total for weight in weights]
    basis_points = [int(np.floor(value)) for value in exact]
    missing = 10_000 - sum(basis_points)
    order = sorted(
        range(len(weights)),
        key=lambda index: (-(exact[index] - basis_points[index]), index),
    )
    for index in order[:missing]:
        basis_points[index] += 1
    return [value / 100 for value in basis_points]


def normalize_pipeline_ndvi_value_split(
    *,
    class_statistics: list[dict[str, object]],
    threshold_profile: str | None,
    total_pixel_count: int | None = None,
    coverage_pixel_count: int | None = None,
    nodata_pixel_count: int | None = None,
) -> IndexValueSplitPayload | None:
    """Normalize the canonical ingestion profile into the app value-split contract."""
    if threshold_profile != NDVI_VALUE_SPLIT_PROFILE_ID:
        return None

    grouped: dict[str, dict[str, float | int | None]] = {
        spec.id: {"percentage": 0.0, "areaSqM": 0.0, "pixelCount": 0}
        for spec in NDVI_VALUE_SPLIT_CATEGORIES
    }
    seen: set[str] = set()
    for item in class_statistics:
        raw_name = str(item.get("class") or "").strip().lower().replace("-", " ")
        normalized_name = "_".join(raw_name.split())
        category_id = _PIPELINE_CATEGORY_ALIASES.get(normalized_name)
        if category_id is None:
            continue
        try:
            percentage = float(item.get("areaPercentage") or 0.0)
        except (TypeError, ValueError):
            return None
        if not 0.0 <= percentage <= 100.0:
            return None
        grouped[category_id]["percentage"] = (
            float(grouped[category_id]["percentage"] or 0.0) + percentage
        )
        area = item.get("areaSqM")
        if area is not None:
            try:
                grouped[category_id]["areaSqM"] = float(
                    grouped[category_id]["areaSqM"] or 0.0
                ) + float(area)
            except (TypeError, ValueError):
                return None
        else:
            grouped[category_id]["areaSqM"] = None
        pixel_count = item.get("pixelCount")
        if pixel_count is not None:
            try:
                grouped[category_id]["pixelCount"] = int(
                    grouped[category_id]["pixelCount"] or 0
                ) + int(pixel_count)
            except (TypeError, ValueError):
                return None
        else:
            grouped[category_id]["pixelCount"] = None
        seen.add(category_id)

    required_ids = {spec.id for spec in NDVI_VALUE_SPLIT_CATEGORIES}
    if seen != required_ids:
        return None

    weights = [float(grouped[spec.id]["percentage"] or 0.0) for spec in NDVI_VALUE_SPLIT_CATEGORIES]
    if sum(weights) <= 0:
        return None
    percentages = _weighted_percentages_totaling_100(weights)
    categories: list[ValueSplitCategoryPayload] = []
    for spec, percentage in zip(NDVI_VALUE_SPLIT_CATEGORIES, percentages, strict=True):
        grouped_category = grouped[spec.id]
        pixel_count = grouped_category["pixelCount"]
        area_sq_m = grouped_category["areaSqM"]
        categories.append(
            ValueSplitCategoryPayload(
                id=spec.id,
                label=spec.label,
                minInclusive=spec.min_inclusive,
                maxExclusive=spec.max_exclusive,
                pixelCount=int(pixel_count) if pixel_count is not None else None,
                areaSqM=float(area_sq_m) if area_sq_m is not None else None,
                percentage=percentage,
            )
        )
    classifiable_pixels = coverage_pixel_count
    return IndexValueSplitPayload(
        indexType="NDVI",
        profileId=NDVI_VALUE_SPLIT_PROFILE_ID,
        percentageBasis="classifiablePixels",
        thresholds=list(NDVI_VALUE_SPLIT_THRESHOLDS),
        totalPixels=total_pixel_count,
        classifiablePixels=classifiable_pixels,
        noDataPixels=nodata_pixel_count,
        unclassifiedPixels=(
            max(total_pixel_count - classifiable_pixels - (nodata_pixel_count or 0), 0)
            if total_pixel_count is not None and classifiable_pixels is not None
            else None
        ),
        categories=categories,
    )



def compute_ndvi_value_split(
    *,
    values: np.ndarray,
    masked_pixel_count: int,
    total_pixel_count: int,
    nodata_pixel_count: int,
    valid_pixel_count: int,
) -> IndexValueSplitPayload:
    """Classify finite NDVI values and cloud-masked pixels into EOS-style buckets."""
    finite_values = np.asarray(values, dtype="float64")
    finite_values = finite_values[np.isfinite(finite_values)]
    bins = np.digitize(finite_values, NDVI_VALUE_SPLIT_THRESHOLDS, right=False)
    counts_by_bin = np.bincount(bins, minlength=4)

    category_counts = [
        int(counts_by_bin[spec.source_bin])
        if spec.source_bin is not None
        else max(int(masked_pixel_count), 0)
        for spec in NDVI_VALUE_SPLIT_CATEGORIES
    ]
    percentages = _percentages_totaling_100(category_counts)
    categories = [
        ValueSplitCategoryPayload(
            id=spec.id,
            label=spec.label,
            minInclusive=spec.min_inclusive,
            maxExclusive=spec.max_exclusive,
            pixelCount=count,
            areaSqM=None,
            percentage=percentage,
        )
        for spec, count, percentage in zip(
            NDVI_VALUE_SPLIT_CATEGORIES, category_counts, percentages, strict=True
        )
    ]

    return IndexValueSplitPayload(
        indexType="NDVI",
        profileId=NDVI_VALUE_SPLIT_PROFILE_ID,
        percentageBasis="classifiablePixels",
        thresholds=list(NDVI_VALUE_SPLIT_THRESHOLDS),
        totalPixels=max(int(total_pixel_count), 0),
        classifiablePixels=sum(category_counts),
        noDataPixels=max(int(nodata_pixel_count), 0),
        unclassifiedPixels=max(int(valid_pixel_count) - int(finite_values.size), 0),
        categories=categories,
    )