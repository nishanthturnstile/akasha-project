"""Unit tests for the pure ingestion field-index -> app statistics adapter."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app.api_models import CloudMaskOptions
from app.ingestion_client import FieldIndexAvailableResponse
from app.ingestion_field_index_adapter import adapt_field_index_to_statistics
from app.raster.errors import AkashaError


def _available(**overrides: Any) -> FieldIndexAvailableResponse:
    data: dict[str, Any] = {
        "status": "AVAILABLE",
        "queryId": "q_01JZ8H7P5ZNDVI",
        "fieldId": "ingestion_field_123",
        "index": "NDVI",
        "requestedDate": "2026-01-15",
        "selectedSceneDate": "2026-01-13",
        "source": "sentinel-2-l2a",
        "providerRoute": "earthsearch:sentinel-2-l2a",
        "resolution": {"nativeMeters": 10, "processingMeters": 10, "displayMeters": 10},
        "layerId": "layer_01JZ8H7P5Z",
        "tileUrl": (
            "https://ingestion.internal/tiles/layer_01JZ8H7P5Z/{z}/{x}/{y}.png"
            "?op=tile&exp=1783071196&kid=default&sig=SIGNED"
        ),
        "statsUrl": (
            "https://ingestion.internal/api/v1/analytics/field-index/"
            "q_01JZ8H7P5ZNDVI?op=stats&exp=1&kid=default&sig=SIGNED"
        ),
        "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
        "statistics": {
            "min": 0.12,
            "max": 0.86,
            "mean": 0.54,
            "median": 0.55,
            "stdDev": 0.08,
            "usablePixelPercentage": 92.5,
            "cloudPercentage": 4.2,
        },
        "classStatistics": [
            {
                "class": "healthy",
                "valueRange": [0.4, 1.0],
                "areaSqM": 28100.0,
                "areaPercentage": 81.3,
            }
        ],
        "visualization": {"displayProfile": "ndvi-v1", "thresholdProfile": "ndvi-thresholds-v1"},
        "versions": {"analytics": "phase2-sentinel2-v1", "processor": "sentinel2-index-v1"},
        "quality": {
            "status": "GOOD",
            "reason": "Field cloud cover within threshold",
            "warnings": [],
        },
    }
    data.update(overrides)
    return FieldIndexAvailableResponse.model_validate(data)


def _adapt(response: FieldIndexAvailableResponse, **kwargs: Any):
    defaults: dict[str, Any] = {
        "plot_id": "field_123",
        "response": response,
        "cloud_mask": CloudMaskOptions(),
        "requested_date": date(2026, 1, 15),
    }
    defaults.update(kwargs)
    return adapt_field_index_to_statistics(**defaults)


def test_adapt_available_maps_core_fields():
    result = _adapt(_available())
    assert result.plot_id == "field_123"  # app id wins over ingestion fieldId
    assert result.provider == "native"
    assert result.scope == "field"
    assert result.index_type == "NDVI"
    assert result.source_id == "sentinel-2-l2a"
    assert result.acquisition_date == "2026-01-15"  # requested date for UI stability
    assert result.basis_date == "2026-01-13"  # selected scene date
    assert result.resolved_source_id == "sentinel-2-l2a"
    assert result.resolution_meters == 10
    assert result.enhanced is False

    stats = result.statistics
    assert stats.min == pytest.approx(0.12)
    assert stats.max == pytest.approx(0.86)
    assert stats.mean == pytest.approx(0.54)
    assert stats.stddev == pytest.approx(0.08)
    assert stats.validPixelPercent == pytest.approx(92.5)
    assert stats.cloudMaskedPercent == pytest.approx(4.2)
    assert stats.coveragePercent == pytest.approx(100.0)


def test_adapt_derives_pixel_counts():
    result = _adapt(_available())
    counts = result.pixel_counts
    assert counts.validPixels == 3456
    # coverage = round(3456 * 100 / 92.5) = 3736
    assert counts.coveragePixels == 3736
    assert counts.maskedPixels == 3736 - 3456
    assert counts.totalPixels == 3736
    assert counts.nodataPixels == 0


def test_adapt_metadata_pipeline_block_and_masks():
    result = _adapt(_available())
    meta = result.metadata
    assert meta["provider"] == "native"
    assert meta["scope"] == "field"
    assert meta["maskMethod"] == "sentinel2-pipeline-scl"
    assert meta["bands"] == ["NIR", "RED"]
    pipeline = meta["pipeline"]
    assert pipeline["enabled"] is True
    assert pipeline["status"] == "AVAILABLE"
    assert pipeline["source"] == "sentinel-2-l2a"
    assert pipeline["providerRoute"] == "earthsearch:sentinel-2-l2a"
    assert pipeline["requestedDate"] == "2026-01-15"
    assert pipeline["selectedSceneDate"] == "2026-01-13"
    assert pipeline["pixelCountsBasis"] == "derivedFromValidPixelCountAndUsablePixelPercentage"
    assert pipeline["cloudMaskedPercentBasis"] == "sceneCloudPercentage"
    assert pipeline["coveragePercentBasis"] == "availableOutputAssumedFullCoverage"
    assert pipeline["selection"]["rule"] == "quality_first"
    assert pipeline["classStatistics"][0]["class"] == "healthy"
    assert "cloudMaskOptionsNote" in pipeline


def test_adapt_does_not_leak_ingestion_urls_or_ids():
    result = _adapt(_available())
    dumped = result.model_dump_json(by_alias=True)
    assert "ingestion.internal" not in dumped
    assert "sig=SIGNED" not in dumped
    assert "queryId" not in dumped
    assert "layerId" not in dumped
    # No tile/stats URL surfaces unless an app-domain proxy URL is supplied.
    assert "tileUrl" not in result.metadata["pipeline"]
    assert "statsUrl" not in result.metadata["pipeline"]


def test_adapt_includes_app_domain_proxy_urls_when_supplied():
    result = _adapt(
        _available(),
        tile_proxy_url="/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_1",
        stats_proxy_url="/api/pipeline/field-index/stats?proxyId=px_2",
        freshness={"status": "AVAILABLE", "aoiId": "bangalore_60km_geodesic_aoi"},
    )
    pipeline = result.metadata["pipeline"]
    assert pipeline["tileUrl"] == "/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_1"
    assert pipeline["statsUrl"] == "/api/pipeline/field-index/stats?proxyId=px_2"
    assert pipeline["freshness"]["aoiId"] == "bangalore_60km_geodesic_aoi"


def test_adapt_missing_optional_fields():
    response = _available(
        selectedSceneDate=None,
        resolution=None,
        selection=None,
        statistics=None,
        classStatistics=[],
        quality=None,
        versions={},
    )
    result = _adapt(response)
    assert result.basis_date is None
    assert result.resolution_meters is None
    assert result.statistics.mean is None
    assert result.statistics.validPixelPercent == 0.0
    assert result.statistics.cloudMaskedPercent == 0.0
    counts = result.pixel_counts
    assert counts.validPixels == 0
    assert counts.coveragePixels == 0
    assert counts.maskedPixels == 0
    pipeline = result.metadata["pipeline"]
    assert "selection" not in pipeline
    assert "resolution" not in pipeline
    assert "classStatistics" not in pipeline


def test_adapt_prefers_cloud_class_percentages_when_present():
    response = _available(
        classStatistics=[
            {"class": "cloud", "areaPercentage": 3.0},
            {"class": "cloud_shadow", "areaPercentage": 1.5},
            {"class": "healthy", "areaPercentage": 95.5},
        ]
    )
    result = _adapt(response)
    assert result.statistics.cloudMaskedPercent == pytest.approx(4.5)
    assert result.metadata["pipeline"]["cloudMaskedPercentBasis"] == "sumOfCloudClassPercentages"


def test_adapt_clamps_valid_pixel_percentage():
    response = _available(statistics={"usablePixelPercentage": 140.0, "cloudPercentage": -10.0})
    result = _adapt(response)
    assert result.statistics.validPixelPercent == 100.0
    assert result.statistics.cloudMaskedPercent == 0.0


def test_adapt_multipolygon_passthrough_is_geometry_agnostic():
    # The adapter never touches geometry; MultiPolygon fields adapt identically.
    result = _adapt(_available(fieldId="mp_field"))
    assert result.plot_id == "field_123"
    assert result.index_type == "NDVI"


def test_adapt_rejects_source_mismatch():
    with pytest.raises(AkashaError) as exc:
        _adapt(_available(source="sentinel-1-grd"))
    assert exc.value.code == "PIPELINE_CONTRACT_MISMATCH"


def test_adapt_rejects_index_mismatch():
    with pytest.raises(AkashaError) as exc:
        _adapt(_available(index="NDMI"))
    assert exc.value.code == "PIPELINE_CONTRACT_MISMATCH"
