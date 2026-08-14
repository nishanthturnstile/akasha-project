from __future__ import annotations

from copy import deepcopy

from app.api_models import CloudMaskOptions
from app.ingestion_adapters import field_index_to_statistics_response
from app.main import app


def _pipeline_result() -> dict:
    return {
        "status": "AVAILABLE",
        "selectedSceneDate": "2026-01-13",
        "resolution": {"displayMeters": 10},
        "selection": {
            "totalPixelCount": 100,
            "coveragePixelCount": 100,
            "nodataPixelCount": 0,
            "maskedPixelCount": 5,
            "validPixelCount": 95,
        },
        "statistics": {
            "min": 0.1,
            "max": 0.8,
            "mean": 0.5,
            "stdDev": 0.1,
            "usablePixelPercentage": 95,
            "cloudPercentage": 5,
        },
        "classStatistics": [
            {"class": "denseVegetation", "areaPercentage": 40},
            {"class": "moderateVegetation", "areaPercentage": 30},
            {"class": "sparseVegetation", "areaPercentage": 20},
            {"class": "openSoil", "areaPercentage": 5},
            {"class": "cloudiness", "areaPercentage": 5},
        ],
        "visualization": {"thresholdProfile": "ndvi-density-v1"},
    }


def _adapt(result: dict, *, index_type: str = "NDVI"):
    return field_index_to_statistics_response(
        result,
        plot_id="field-1",
        source_id="sentinel-2-l2a",
        index_type=index_type,
        cloud_mask=CloudMaskOptions(),
    )


def test_pipeline_statistics_exposes_canonical_value_split() -> None:
    payload = _adapt(_pipeline_result()).model_dump(by_alias=True)

    assert payload["valueSplit"]["profileId"] == "ndvi-density-v1"
    assert sum(item["percentage"] for item in payload["valueSplit"]["categories"]) == 100


def test_pipeline_statistics_omits_value_split_for_non_ndvi_or_legacy_profile() -> None:
    assert _adapt(_pipeline_result(), index_type="NDMI").value_split is None

    legacy = deepcopy(_pipeline_result())
    legacy["visualization"]["thresholdProfile"] = "ndvi-thresholds-v1"
    assert _adapt(legacy).value_split is None


def test_openapi_exposes_optional_typed_value_split() -> None:
    schema = app.openapi()
    for response_name in ("FieldStatisticsResponse", "StatisticsResponse"):
        response_schema = schema["components"]["schemas"][response_name]
        assert "valueSplit" in response_schema["properties"]
        assert "valueSplit" not in response_schema.get("required", [])