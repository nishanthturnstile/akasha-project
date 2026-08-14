from __future__ import annotations

import numpy as np

from app.raster.value_split import (
    compute_ndvi_value_split,
    normalize_pipeline_ndvi_value_split,
)


def test_ndvi_value_split_uses_documented_boundaries_and_cloud_bucket() -> None:
    split = compute_ndvi_value_split(
        values=np.array([0.1, 0.2, 0.3999, 0.4, 0.5999, 0.6, 0.8]),
        masked_pixel_count=1,
        total_pixel_count=9,
        nodata_pixel_count=1,
        valid_pixel_count=7,
    )

    assert [category["pixelCount"] for category in split["categories"]] == [2, 2, 2, 1, 1]
    assert sum(category["percentage"] for category in split["categories"]) == 100.0
    assert split["classifiablePixels"] == 8
    assert split["noDataPixels"] == 1
    assert split["unclassifiedPixels"] == 0


def test_ndvi_value_split_rounding_is_deterministic_and_totals_100() -> None:
    split = compute_ndvi_value_split(
        values=np.array([0.8, 0.5, 0.3]),
        masked_pixel_count=0,
        total_pixel_count=3,
        nodata_pixel_count=0,
        valid_pixel_count=3,
    )

    assert [category["percentage"] for category in split["categories"]] == [
        33.34,
        33.33,
        33.33,
        0.0,
        0.0,
    ]


def test_ndvi_value_split_tracks_unclassified_and_empty_inputs() -> None:
    split = compute_ndvi_value_split(
        values=np.array([np.nan]),
        masked_pixel_count=0,
        total_pixel_count=2,
        nodata_pixel_count=1,
        valid_pixel_count=1,
    )

    assert split["classifiablePixels"] == 0
    assert split["unclassifiedPixels"] == 1
    assert [category["percentage"] for category in split["categories"]] == [0.0] * 5


def test_pipeline_value_split_normalizes_only_complete_canonical_profile() -> None:
    split = normalize_pipeline_ndvi_value_split(
        threshold_profile="ndvi-density-v1",
        class_statistics=[
            {"class": "denseVegetation", "areaPercentage": 40.0, "areaSqM": 400.0},
            {"class": "moderate_vegetation", "areaPercentage": 30.0, "areaSqM": 300.0},
            {"class": "sparse", "areaPercentage": 20.0, "areaSqM": 200.0},
            {"class": "open soil", "areaPercentage": 5.0, "areaSqM": 50.0},
            {"class": "cloudiness", "areaPercentage": 5.0, "areaSqM": 50.0},
        ],
        total_pixel_count=100,
        coverage_pixel_count=100,
        nodata_pixel_count=0,
    )

    assert split is not None
    assert [category["percentage"] for category in split["categories"]] == [
        40.0,
        30.0,
        20.0,
        5.0,
        5.0,
    ]


def test_pipeline_value_split_rejects_legacy_or_incomplete_classes() -> None:
    classes = [{"class": "healthy", "areaPercentage": 100.0}]

    assert (
        normalize_pipeline_ndvi_value_split(
            threshold_profile="ndvi-thresholds-v1",
            class_statistics=classes,
        )
        is None
    )
    assert (
        normalize_pipeline_ndvi_value_split(
            threshold_profile="ndvi-density-v1",
            class_statistics=[{"class": "dense", "areaPercentage": 100.0}],
        )
        is None
    )