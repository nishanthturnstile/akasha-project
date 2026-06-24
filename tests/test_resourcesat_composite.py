import json
import sys
from pathlib import Path

import numpy as np
import pytest

INGESTION_ROOT = Path(__file__).resolve().parents[1] / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import composite  # noqa: E402
from akasha_ingest.composite import (  # noqa: E402
    AlignedScene,
    CompositeGrid,
    build_best_available_composite,
)


def _scene(scene_id: str, dt: str, values: list[list[int]], mask: list[list[int]]) -> AlignedScene:
    band = np.array(values, dtype="uint16")
    analytic = np.stack([band, band + 100, band + 200, band + 300])
    return AlignedScene(
        scene_id=scene_id,
        acquisition_datetime=dt,
        analytic=analytic,
        mask=np.array(mask, dtype="uint8"),
    )


def _with_resource_sat_provenance(manifest: dict) -> dict:
    manifest.setdefault("mask_method", composite.MASK_METHOD)
    manifest.setdefault("classification_classes", composite.MASK_CLASSES)
    props = dict(manifest.get("properties") or {})
    props.setdefault("akasha:mask_method", composite.MASK_METHOD)
    props.setdefault("akasha:metrics_provisional", True)
    manifest["properties"] = props
    return manifest


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


def test_best_available_composite_accepts_liss4_three_band_scenes() -> None:
    older_band = np.array([[10, 20], [30, 40]], dtype="uint16")
    newer_band = np.array([[50, 60], [70, 80]], dtype="uint16")
    older = AlignedScene(
        scene_id="older-liss4",
        acquisition_datetime="2026-03-05T00:00:00Z",
        analytic=np.stack([older_band, older_band + 100, older_band + 200]),
        mask=np.array([[1, 2], [0, 3]], dtype="uint8"),
    )
    newer = AlignedScene(
        scene_id="newer-liss4",
        acquisition_datetime="2026-03-19T00:00:00Z",
        analytic=np.stack([newer_band, newer_band + 100, newer_band + 200]),
        mask=np.array([[1, 1], [4, 0]], dtype="uint8"),
    )

    result = build_best_available_composite([newer, older])

    assert result["analytic"].shape == (3, 2, 2)
    assert result["analytic"][0].tolist() == [[50, 60], [70, 40]]
    assert result["mask"].tolist() == [[1, 1], [4, 3]]


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
    assert payload["composite_grid_crs"] == "EPSG:32643"
    assert payload["composite_resolution_meters"] == 24.0
    assert payload["composite_grid_dimensions"] == [
        payload["outputs"]["analytic"]["width"],
        payload["outputs"]["analytic"]["height"],
    ]
    assert payload["composite_date"] == "2026-03-19"
    assert payload["properties"]["akasha:composite"] is True
    assert payload["properties"]["akasha:composite_grid_crs"] == "EPSG:32643"
    assert payload["properties"]["akasha:composite_resolution_meters"] == 24.0
    assert payload["properties"]["akasha:contributing_scenes"][1]["id"] == "newer"
    assert payload["outputs"]["analytic"]["band_count"] == 4
    assert payload["outputs"]["mask"]["band_count"] == 1


def test_build_resource_sat_composite_defaults_awifs_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_grid_from_aoi(**kwargs):
        captured["resolution"] = kwargs["resolution"]
        return CompositeGrid.from_projected_bounds(
            [799960, 1290192, 800072, 1290304],
            crs="EPSG:32643",
            resolution=kwargs["resolution"],
        )

    def fake_align_manifest_scene(**_kwargs):
        return _scene(
            "awifs-scene",
            "2026-03-19T00:00:00Z",
            [[100, 100], [100, 100]],
            [[1, 1], [1, 1]],
        )

    def fake_write_intermediate_rasters(**kwargs):
        captured["written_band_count"] = kwargs["analytic"].shape[0]
        kwargs["analytic_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["analytic_path"].write_bytes(b"analytic")
        kwargs["mask_path"].write_bytes(b"mask")

    def fake_translate_to_cog(**kwargs):
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(b"cog")

    def fake_write_composite_manifest(**kwargs):
        kwargs["manifest_path"].write_text(
            json.dumps({"source_id": kwargs["source_id"]}),
            encoding="utf-8",
        )

    monkeypatch.setattr(composite, "grid_from_aoi", fake_grid_from_aoi)
    monkeypatch.setattr(composite, "align_manifest_scene", fake_align_manifest_scene)
    monkeypatch.setattr(composite, "_write_intermediate_rasters", fake_write_intermediate_rasters)
    monkeypatch.setattr(composite, "_translate_to_cog", fake_translate_to_cog)
    monkeypatch.setattr(composite, "_write_composite_manifest", fake_write_composite_manifest)

    result = composite.build_resource_sat_composite(
        deps={},
        manifest_paths=[tmp_path / "scene" / "prepare_manifest.json"],
        aoi={"id": "test-aoi", "geometry": {"type": "Polygon", "coordinates": []}},
        output_root=tmp_path / "rasters",
        window_start="2026-03-01",
        window_end="2026-03-31",
        source_id="resourcesat-2a-awifs-boa",
        overwrite=True,
        skip_validation=True,
    )

    assert captured["resolution"] == 56.0
    assert captured["written_band_count"] == 4
    assert result.output_dir == (
        tmp_path
        / "rasters"
        / "resourcesat-2a-awifs-boa"
        / "composite"
        / "test-aoi"
        / "2026-03-19"
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "resourcesat-2a-awifs-boa"


def test_build_resource_sat_composite_defaults_liss4_resolution_and_band_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_grid_from_aoi(**kwargs):
        captured["resolution"] = kwargs["resolution"]
        return CompositeGrid.from_projected_bounds(
            [799960, 1290192, 800024, 1290256],
            crs="EPSG:32643",
            resolution=kwargs["resolution"],
        )

    def fake_align_manifest_scene(**_kwargs):
        band = np.full((2, 2), 100, dtype="uint16")
        return AlignedScene(
            scene_id="liss4-scene",
            acquisition_datetime="2026-03-19T00:00:00Z",
            analytic=np.stack([band, band + 10, band + 20]),
            mask=np.ones((2, 2), dtype="uint8"),
        )

    def fake_write_intermediate_rasters(**kwargs):
        captured["written_band_count"] = kwargs["analytic"].shape[0]
        kwargs["analytic_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["analytic_path"].write_bytes(b"analytic")
        kwargs["mask_path"].write_bytes(b"mask")

    def fake_translate_to_cog(**kwargs):
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(b"cog")

    def fake_write_composite_manifest(**kwargs):
        captured["manifest_source_id"] = kwargs["source_id"]
        kwargs["manifest_path"].write_text(
            json.dumps(
                {
                    "source_id": kwargs["source_id"],
                    "composite_resolution_meters": kwargs["grid"].resolution,
                    "analytic_band_order": ["BAND2", "BAND3", "BAND4"],
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(composite, "grid_from_aoi", fake_grid_from_aoi)
    monkeypatch.setattr(composite, "align_manifest_scene", fake_align_manifest_scene)
    monkeypatch.setattr(composite, "_write_intermediate_rasters", fake_write_intermediate_rasters)
    monkeypatch.setattr(composite, "_translate_to_cog", fake_translate_to_cog)
    monkeypatch.setattr(composite, "_write_composite_manifest", fake_write_composite_manifest)

    result = composite.build_resource_sat_composite(
        deps={},
        manifest_paths=[tmp_path / "scene" / "prepare_manifest.json"],
        aoi={"id": "test-aoi", "geometry": {"type": "Polygon", "coordinates": []}},
        output_root=tmp_path / "rasters",
        window_start="2026-03-01",
        window_end="2026-03-31",
        source_id="resourcesat-2a-liss4-mx70-l2",
        overwrite=True,
        skip_validation=True,
    )

    assert captured["resolution"] == 5.8
    assert captured["written_band_count"] == 3
    assert result.output_dir == (
        tmp_path
        / "rasters"
        / "resourcesat-2a-liss4-mx70-l2"
        / "composite"
        / "test-aoi"
        / "2026-03-19"
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "resourcesat-2a-liss4-mx70-l2"
    assert manifest["composite_resolution_meters"] == 5.8
    assert manifest["analytic_band_order"] == ["BAND2", "BAND3", "BAND4"]


def test_build_resource_sat_composite_accepts_aoi_grid_crs_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_grid_from_aoi(**kwargs):
        captured["crs"] = kwargs["crs"]
        return CompositeGrid.from_projected_bounds(
            [799960, 1290192, 800032, 1290264],
            crs=kwargs["crs"],
            resolution=kwargs["resolution"],
        )

    def fake_align_manifest_scene(**_kwargs):
        return _scene(
            "liss3-scene",
            "2026-03-19T00:00:00Z",
            [[100, 100], [100, 100]],
            [[1, 1], [1, 1]],
        )

    def fake_write_intermediate_rasters(**kwargs):
        kwargs["analytic_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["analytic_path"].write_bytes(b"analytic")
        kwargs["mask_path"].write_bytes(b"mask")

    def fake_translate_to_cog(**kwargs):
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(b"cog")

    def fake_write_composite_manifest(**kwargs):
        kwargs["manifest_path"].write_text("{}", encoding="utf-8")

    monkeypatch.setattr(composite, "grid_from_aoi", fake_grid_from_aoi)
    monkeypatch.setattr(composite, "align_manifest_scene", fake_align_manifest_scene)
    monkeypatch.setattr(composite, "_write_intermediate_rasters", fake_write_intermediate_rasters)
    monkeypatch.setattr(composite, "_translate_to_cog", fake_translate_to_cog)
    monkeypatch.setattr(composite, "_write_composite_manifest", fake_write_composite_manifest)

    composite.build_resource_sat_composite(
        deps={},
        manifest_paths=[tmp_path / "scene" / "prepare_manifest.json"],
        aoi={
            "id": "mysore-60km",
            "composite_grid_crs": "EPSG:32644",
            "geometry": {"type": "Polygon", "coordinates": []},
        },
        output_root=tmp_path / "rasters",
        window_start="2026-03-01",
        window_end="2026-03-31",
        overwrite=True,
        skip_validation=True,
    )

    assert captured["crs"] == "EPSG:32644"


def test_awifs_composite_manifest_uses_awifs_specific_mask_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_raster_summary(_deps: dict, path: Path) -> dict:
        return {
            "path": path.as_posix(),
            "wgs84_bbox": [77.0, 12.0, 78.0, 13.0],
            "wgs84_geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[77.0, 12.0], [78.0, 12.0], [78.0, 13.0], [77.0, 13.0], [77.0, 12.0]]
                ],
            },
        }

    monkeypatch.setattr(composite, "_raster_summary", fake_raster_summary)
    manifest_path = tmp_path / "prepare_manifest.json"
    grid = CompositeGrid.from_projected_bounds(
        [799960, 1290240, 800128, 1290408],
        resolution=56,
    )

    composite._write_composite_manifest(
        deps={},
        manifest_path=manifest_path,
        aoi_id="bangalore-60km",
        grid=grid,
        composite_datetime="2026-03-19T00:00:00Z",
        period_start="2026-03-01",
        period_end="2026-03-31",
        source_manifest_paths=[tmp_path / "scene" / "prepare_manifest.json"],
        analytic_cog=tmp_path / "analytic.tif",
        mask_cog=tmp_path / "mask.tif",
        metrics={
            "contributing_scenes": 1,
            "coverage_percent": 99.0,
            "usable_pixel_percent": 95.0,
            "cloud_masked_percent": 4.0,
        },
        source_id="resourcesat-2a-awifs-boa",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == "resourcesat-2a-awifs-boa"
    assert payload["mask_method"] == composite.mask_method_for_source("resourcesat-2a-awifs-boa")
    assert payload["properties"]["akasha:mask_method"] == composite.mask_method_for_source(
        "resourcesat-2a-awifs-boa"
    )
    assert "AWiFS" in payload["mask_method"]
    assert "LISS-3 BOA sample" not in payload["mask_method"]


def test_verify_composite_manifest_accepts_generated_composite(tmp_path: Path) -> None:
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

    def write_scene(scene_dir: Path, scene_id: str, dt: str) -> Path:
        scene_dir.mkdir(parents=True)
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
            dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
        with rasterio.open(
            scene_dir / "mask.tif",
            "w",
            **dict(profile, count=1, dtype="uint8", nodata=0),
        ) as dst:
            dst.write(np.ones((2, 2), dtype="uint8"), 1)
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

    scene = write_scene(tmp_path / "scene", "scene", "2026-03-19T00:00:00Z")
    build = composite.build_resource_sat_composite(
        deps=deps,
        manifest_paths=[scene],
        aoi=aoi,
        output_root=tmp_path / "rasters",
        window_start="2026-03-01",
        window_end="2026-03-31",
        overwrite=True,
        skip_validation=True,
    )

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=build.manifest,
        min_coverage_percent=30,
        require_overviews=False,
    )

    assert verify.ok
    assert "dated composite STAC item buildable" in "\n".join(verify.checks)


def test_verify_composite_manifest_rejects_low_coverage(tmp_path: Path) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    transform = Affine(24, 0, 799980, 0, -24, 1290288)
    output = tmp_path / "composite"
    output.mkdir()
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
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.array([[1, 0], [0, 0]], dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "collection": "ResourceSat-2A_LISS3_BOA",
        "product_id": "low-coverage",
        "composite": True,
        "aoi_id": "test-aoi",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(_with_resource_sat_provenance(manifest)), encoding="utf-8")

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        min_coverage_percent=95,
        require_overviews=False,
    )

    assert not verify.ok
    assert any("coverage 25.0% below threshold" in problem for problem in verify.problems)


def test_verify_composite_manifest_rejects_unexpected_aoi_id(tmp_path: Path) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    output = tmp_path / "composite"
    output.mkdir()
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": Affine(24, 0, 799980, 0, -24, 1290288),
        "width": 2,
        "height": 2,
        "count": 4,
        "dtype": "uint16",
        "nodata": 0,
    }
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.ones((2, 2), dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "collection": "ResourceSat-2A_LISS3_BOA",
        "product_id": "wrong-aoi",
        "composite": True,
        "aoi_id": "bangalore-60km",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(_with_resource_sat_provenance(manifest)), encoding="utf-8")

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        expected_aoi_id="mysore-60km",
        min_coverage_percent=95,
        require_overviews=False,
    )

    assert not verify.ok
    assert any("does not match expected 'mysore-60km'" in problem for problem in verify.problems)


def test_verify_composite_manifest_requires_provisional_mask_provenance(tmp_path: Path) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    output = tmp_path / "composite"
    output.mkdir()
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": Affine(24, 0, 799980, 0, -24, 1290288),
        "width": 2,
        "height": 2,
        "count": 4,
        "dtype": "uint16",
        "nodata": 0,
    }
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.ones((2, 2), dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "collection": "ResourceSat-2A_LISS3_BOA",
        "product_id": "missing-provenance",
        "composite": True,
        "aoi_id": "test-aoi",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        min_coverage_percent=95,
        require_overviews=False,
    )

    assert not verify.ok
    assert "manifest missing ResourceSat provisional mask method" in verify.problems
    assert "manifest does not mark ResourceSat metrics as provisional" in verify.problems
    assert (
        "manifest classification classes do not match ResourceSat mask classes"
        in verify.problems
    )


def test_verify_composite_manifest_can_require_catalog_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    output = tmp_path / "composite"
    output.mkdir()
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": Affine(24, 0, 799980, 0, -24, 1290288),
        "width": 2,
        "height": 2,
        "count": 4,
        "dtype": "uint16",
        "nodata": 0,
    }
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.ones((2, 2), dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "collection": "ResourceSat-2A_LISS3_BOA",
        "product_id": "catalog-present",
        "composite": True,
        "aoi_id": "test-aoi",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(_with_resource_sat_provenance(manifest)), encoding="utf-8")
    monkeypatch.setattr(
        composite,
        "_stac_item_exists",
        lambda **_kwargs: (True, "catalog item present: item"),
    )

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        min_coverage_percent=95,
        require_overviews=False,
        require_catalog_item=True,
        stac_api_url="http://stac-api",
    )

    assert verify.ok
    assert "catalog item present: item" in verify.checks


def test_verify_composite_manifest_reports_missing_catalog_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    output = tmp_path / "composite"
    output.mkdir()
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": Affine(24, 0, 799980, 0, -24, 1290288),
        "width": 2,
        "height": 2,
        "count": 4,
        "dtype": "uint16",
        "nodata": 0,
    }
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.ones((2, 2), dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "collection": "ResourceSat-2A_LISS3_BOA",
        "product_id": "catalog-missing",
        "composite": True,
        "aoi_id": "test-aoi",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(_with_resource_sat_provenance(manifest)), encoding="utf-8")
    monkeypatch.setattr(
        composite,
        "_stac_item_exists",
        lambda **_kwargs: (False, "catalog item missing: item"),
    )

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        min_coverage_percent=95,
        require_overviews=False,
        require_catalog_item=True,
        stac_api_url="http://stac-api",
    )

    assert not verify.ok
    assert "catalog item missing: item" in verify.problems


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


def test_scene_manifest_paths_for_window_filters_awifs_source(tmp_path: Path) -> None:
    def write_manifest(name: str, source_id: str) -> Path:
        path = tmp_path / name / "prepare_manifest.json"
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "acquisition_datetime": "2026-03-19T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        return path

    liss3 = write_manifest("liss3", "resourcesat-2a-liss3-boa")
    awifs = write_manifest("awifs", "resourcesat-2a-awifs-boa")

    assert composite.scene_manifest_paths_for_window(
        [liss3, awifs],
        window_start="2026-03-01",
        window_end="2026-03-31",
        source_id="resourcesat-2a-awifs-boa",
    ) == [awifs]


def test_scene_manifest_paths_for_window_filters_explicit_aoi_id(tmp_path: Path) -> None:
    def write_manifest(name: str, payload: dict) -> Path:
        path = tmp_path / name / "prepare_manifest.json"
        path.parent.mkdir()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    base = {
        "source_id": "resourcesat-2a-liss3-boa",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
    }
    aoi_neutral = write_manifest("neutral-scene", base)
    matching_aoi = write_manifest("matching-aoi-scene", {**base, "aoi_id": "mysore-60km"})
    other_aoi = write_manifest(
        "other-aoi-scene",
        {**base, "properties": {"akasha:aoi_id": "bangalore-60km"}},
    )

    assert composite.scene_manifest_paths_for_window(
        [other_aoi, aoi_neutral, matching_aoi],
        window_start="2026-03-01",
        window_end="2026-03-31",
        source_id="resourcesat-2a-liss3-boa",
        aoi_id="mysore-60km",
    ) == [matching_aoi, aoi_neutral]


def test_verify_composite_manifest_accepts_awifs_resolution(tmp_path: Path) -> None:
    deps = composite.require_raster_deps()
    rasterio = deps["rasterio"]
    Affine = deps["Affine"]
    output = tmp_path / "composite"
    output.mkdir()
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": Affine(56, 0, 799960, 0, -56, 1290304),
        "width": 2,
        "height": 2,
        "count": 4,
        "dtype": "uint16",
        "nodata": 0,
    }
    with rasterio.open(output / "analytic.tif", "w", **profile) as dst:
        dst.write(np.ones((4, 2, 2), dtype="uint16") * 100)
    with rasterio.open(
        output / "mask.tif",
        "w",
        **dict(profile, count=1, dtype="uint8", nodata=0),
    ) as dst:
        dst.write(np.ones((2, 2), dtype="uint8"), 1)
    manifest = {
        "source_id": "resourcesat-2a-awifs-boa",
        "collection": "ResourceSat-2A_AWIFS_BOA",
        "product_id": "resourcesat-2a-awifs-boa-composite-test-aoi-2026-03-19",
        "composite": True,
        "aoi_id": "test-aoi",
        "composite_date": "2026-03-19",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "contributing_scenes": [{"id": "scene", "datetime": "2026-03-19T00:00:00Z"}],
        "outputs": {
            "analytic": {"path": "analytic.tif"},
            "mask": {"path": "mask.tif"},
        },
        "properties": {"akasha:composite": True},
    }
    manifest_path = output / "prepare_manifest.json"
    manifest_path.write_text(json.dumps(_with_resource_sat_provenance(manifest)), encoding="utf-8")

    verify = composite.verify_composite_manifest(
        deps=deps,
        manifest_path=manifest_path,
        source_id="resourcesat-2a-awifs-boa",
        min_coverage_percent=95,
        require_overviews=False,
    )

    assert verify.ok
    assert "manifest source is ResourceSat AWiFS" in verify.checks
    assert "resolution near 56.0m" in verify.checks
