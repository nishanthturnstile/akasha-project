import asyncio
from typing import get_type_hints

import pytest
from app.raster.render_profiles import (
    CONTRAST_PALETTE_V1,
    category_for_value,
    resolve_render_descriptor,
)
from app.routers import latest_imagery_router
from app.routers.latest_imagery_router import (
    LatestImagerySearchRequest,
    _viewport_diagonal_meters,
)
from app.routers.analytics_router import get_field_dates
from pydantic import ValidationError
from pydantic import TypeAdapter


def test_contrast_descriptor_has_exact_equal_breaks_and_categories() -> None:
    descriptor = resolve_render_descriptor("contrast", -0.5, 1.0)

    assert descriptor.applied == "contrast"
    assert descriptor.thresholds == pytest.approx((-0.2, 0.1, 0.4, 0.7, 1.0))
    assert descriptor.palette == CONTRAST_PALETTE_V1
    assert category_for_value(-0.21, descriptor.thresholds) == 0
    assert category_for_value(0.4, descriptor.thresholds) == 3


def test_contrast_descriptor_falls_back_for_missing_or_constant_statistics() -> None:
    assert resolve_render_descriptor("contrast", None, None).fallback_reason == "missing_statistics"
    assert resolve_render_descriptor("contrast", 0.4, 0.4).fallback_reason == "constant_scene"


def test_latest_imagery_viewport_validation_and_distance() -> None:
    viewport = {
        "type": "Polygon",
        "coordinates": [[[77.0, 12.0], [77.01, 12.0], [77.01, 12.01], [77.0, 12.0]]],
    }
    request = LatestImagerySearchRequest(viewport=viewport)

    assert 1_000 < _viewport_diagonal_meters(request.viewport) < 2_000
    with pytest.raises(ValidationError):
        LatestImagerySearchRequest(
            viewport={"type": "Polygon", "coordinates": [[[77.0, 12.0], [77.01, 12.0]]]}
        )


def test_latest_imagery_search_whitelists_upstream_metadata_and_rewrites_urls(monkeypatch) -> None:
    viewport = {
        "type": "Polygon",
        "coordinates": [[[77.0, 12.0], [77.005, 12.0], [77.005, 12.005], [77.0, 12.0]]],
    }
    captured = {}

    def upstream(_settings, **kwargs):
        captured.update(kwargs)
        return {
            "policyVersion": "latest-image-s2-l2a-v1",
            "searchedAt": "2026-07-22T00:00:00Z",
            "candidates": [
                {
                    "sceneId": "scene-1",
                    "sourceId": "sentinel-2-l2a",
                    "processingLevel": "L2A",
                    "usable": True,
                    "providerUrl": "https://provider.invalid/signed-secret",
                }
            ],
        }

    latest_imagery_router._SEARCH_CACHE.clear()
    monkeypatch.setattr(latest_imagery_router.settings, "latest_imagery_enabled", True)
    monkeypatch.setattr(latest_imagery_router, "search_latest_imagery", upstream)
    result = asyncio.run(
        latest_imagery_router.search_latest(LatestImagerySearchRequest(viewport=viewport))
    )

    assert captured["source_id"] == "sentinel-2-l2a"
    assert captured["processing_level"] == "L2A"
    assert captured["lookback_days"] == 365
    assert captured["max_cloud_percent"] == 10
    assert "providerUrl" not in result["candidates"][0]
    assert result["candidates"][0]["tileUrlTemplate"].startswith("/api/imagery/scenes/")


def test_field_history_response_contract_accepts_cursor_pages() -> None:
    response_type = get_type_hints(get_field_dates)["return"]

    result = TypeAdapter(response_type).validate_python(
        {"items": [{"acquisitionDate": "2026-05-12"}], "nextCursor": None}
    )

    assert result["items"][0]["acquisitionDate"] == "2026-05-12"
