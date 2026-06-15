import json
from pathlib import Path

import numpy as np
import pytest
from akasha_ingest import composite
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


def test_build_resource_sat_composite_writes_manifest_from_scene_cogs(tmp_path: Path) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    transform_bounds = deps["transform_bounds"]
    Affine = deps["Affine"]
    transform = Affine(24, 0, 799980, 0, -24, 1290288)
    bounds = (799980, 1290240, 800028, 1290288)
    west, south, east, north = transform_bounds("EPSG:32643", "EPSG:4326", *bounds)
    aoi = {
        "id": "test-aoi",
        "type": "Feature",
        "properties": {"compositeGridCrs": "EPSG:32643"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[west, south], [east, south], [east, north], [west, north], [west, south]]
            ],
        },
    }

    def write_scene(
        scene_dir: Path,
        scene_id: str,
        dt: str,
        base: int,
        mask_values: list[list[int]],
    ) -> Path:
        scene_dir.mkdir(parents=True)
        analytic = np.stack(
            [
                np.full((2, 2), base, dtype="uint16"),
                np.full((2, 2), base + 10, dtype="uint16"),
                np.full((2, 2), base + 20, dtype="uint16"),
                np.full((2, 2), base + 30, dtype="uint16"),
            ]
        )
        profile = {
            "driver": "GTiff",
            "crs": "EPSG:32643",
            "transform": transform,
            "width": 2,
            "height": 2,
            "count": 4,
            "dtype": "uint16",
            "nodata": 0,
        }
        with rasterio.open(scene_dir / "analytic.tif", "w", **profile) as dst:
            dst.write(analytic)
        mask_profile = dict(profile, count=1, dtype="uint8", nodata=0)
        with rasterio.open(scene_dir / "mask.tif", "w", **mask_profile) as dst:
            dst.write(np.array(mask_values, dtype="uint8"), 1)
        manifest = {
            "source_id": "resourcesat-2a-liss3-boa",
            "product_id": scene_id,
            "acquisition_datetime": dt,
            "path": "99",
            "row": "65",
            "outputs": {
                "analytic": {"path": "analytic.tif"},
                "mask": {"path": "mask.tif"},
            },
        }
        path = scene_dir / "prepare_manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    older = write_scene(
        tmp_path / "scene-old",
        "older",
        "2026-03-05T00:00:00Z",
        100,
        [[1, 2], [0, 3]],
    )
    newer = write_scene(
        tmp_path / "scene-new",
        "newer",
        "2026-03-19T00:00:00Z",
        500,
        [[1, 1], [4, 0]],
    )

    result = composite.build_resource_sat_composite(
        deps=deps,
        manifest_paths=[older, newer],
        aoi=aoi,
        output_root=tmp_path / "rasters",
        window_start="2026-03-05",
        window_end="2026-03-19",
        overwrite=True,
        skip_validation=True,
    )

    payload = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert result.analytic_cog.is_file()
    assert result.mask_cog.is_file()
    assert payload["composite"] is True
    assert payload["aoi_id"] == "test-aoi"
    assert payload["composite_date"] == "2026-03-19"
    assert payload["properties"]["akasha:composite"] is True
    assert payload["properties"]["akasha:contributing_scenes"][1]["id"] == "newer"
    assert payload["outputs"]["analytic"]["band_count"] == 4
    assert payload["outputs"]["mask"]["band_count"] == 1


def test_scene_manifest_paths_for_window_skips_composites_and_out_of_window(
    tmp_path: Path,
) -> None:
    def write_manifest(name: str, payload: dict) -> Path:
        path = tmp_path / name / "prepare_manifest.json"
        path.parent.mkdir()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    in_window = write_manifest(
        "scene-in",
        {
            "source_id": "resourcesat-2a-liss3-boa",
            "acquisition_datetime": "2026-03-19T00:00:00Z",
        },
    )
    out_of_window = write_manifest(
        "scene-out",
        {
            "source_id": "resourcesat-2a-liss3-boa",
            "acquisition_datetime": "2026-02-01T00:00:00Z",
        },
    )
    composite_manifest = write_manifest(
        "composite",
        {
            "source_id": "resourcesat-2a-liss3-boa",
            "composite": True,
            "acquisition_datetime": "2026-03-19T00:00:00Z",
        },
    )

    assert composite.scene_manifest_paths_for_window(
        [composite_manifest, out_of_window, in_window],
        window_start="2026-03-01",
        window_end="2026-03-31",
    ) == [in_window]
