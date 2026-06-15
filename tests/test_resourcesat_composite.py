import numpy as np
import pytest
from akasha_ingest.composite import AlignedScene, CompositeGrid, build_best_available_composite


def _scene(scene_id: str, dt: str, values: list[list[int]], mask: list[list[int]]) -> AlignedScene:
    band = np.array(values, dtype="uint16")
    analytic = np.stack([band, band + 100, band + 200, band + 300])
    return AlignedScene(
        scene_id=scene_id,
        acquisition_datetime=dt,
        analytic=analytic,
        mask=np.array(mask, dtype="uint8"),
    )


def test_composite_grid_snaps_projected_extent_to_resolution() -> None:
    grid = CompositeGrid.from_projected_bounds(
        [100.5, 200.5, 155.1, 260.1],
        resolution=24,
        padding_pixels=1,
    )

    assert grid.crs == "EPSG:32643"
    assert grid.bounds == (72.0, 168.0, 192.0, 288.0)
    assert grid.width == 5
    assert grid.height == 5
    assert grid.transform == (24, 0.0, 72.0, 0.0, -24, 288.0, 0.0, 0.0, 1.0)


def test_best_available_composite_prefers_most_recent_valid_pixel() -> None:
    older = _scene(
        "older",
        "2026-03-05T00:00:00Z",
        [[10, 20], [30, 40]],
        [[1, 2], [0, 3]],
    )
    newer = _scene(
        "newer",
        "2026-03-19T00:00:00Z",
        [[50, 60], [70, 80]],
        [[1, 1], [4, 0]],
    )

    result = build_best_available_composite([newer, older])

    assert result["analytic"][0].tolist() == [[50, 60], [70, 40]]
    assert result["mask"].tolist() == [[1, 1], [4, 3]]
    assert result["source_scene_index"].tolist() == [[1, 1], [1, 0]]
    assert result["metrics"]["coverage_percent"] == 100.0
    assert result["metrics"]["usable_pixel_percent"] == 75.0
    assert result["metrics"]["cloud_masked_percent"] == 0.0
    assert [scene["id"] for scene in result["metrics"]["contributing_scenes"]] == [
        "older",
        "newer",
    ]


def test_best_available_composite_keeps_masked_fallback_when_no_valid_scene_exists() -> None:
    first = _scene("first", "2026-03-05T00:00:00Z", [[10, 20]], [[2, 0]])
    second = _scene("second", "2026-03-19T00:00:00Z", [[50, 60]], [[3, 0]])

    result = build_best_available_composite([first, second])

    assert result["analytic"][0].tolist() == [[10, 0]]
    assert result["mask"].tolist() == [[2, 0]]
    assert result["metrics"]["coverage_percent"] == 50.0
    assert result["metrics"]["usable_pixel_percent"] == 0.0
    assert result["metrics"]["cloud_masked_percent"] == 50.0


def test_best_available_composite_rejects_shape_mismatch() -> None:
    first = _scene("first", "2026-03-05T00:00:00Z", [[10, 20]], [[1, 1]])
    second = _scene("second", "2026-03-19T00:00:00Z", [[50]], [[1]])

    with pytest.raises(ValueError, match="shape does not match"):
        build_best_available_composite([first, second])
