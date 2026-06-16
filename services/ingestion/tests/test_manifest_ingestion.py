from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

import pytest
from akasha_ingest import catalog, config, seed, storage
from akasha_ingest.scene import SAMPLE_SCENE, SceneIdentity


@pytest.fixture
def scratch_dir() -> Path:
    path = Path(__file__).resolve().parent / "_scratch"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)


def _manifest(
    tile: str = "43PHQ",
    date: str = "2026-01-15",
    acquisition_datetime: str | None = None,
    processing_baseline: str = "05.00",
) -> dict:
    acquisition_datetime = acquisition_datetime or f"{date}T05:20:00Z"
    return {
        "product_id": (
            f"S2B_MSIL2A_{date.replace('-', '')}T052000_N0500_R019_" f"T{tile}_20260115T074457.SAFE"
        ),
        "mgrs_tile": tile,
        "acquisition_datetime": acquisition_datetime,
        "acquisition_date": date,
        "processing_baseline": processing_baseline,
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "outputs": {
            "analytic": {
                "path": "analytic.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [10, 10],
                "width": 10980,
                "height": 10980,
                "dtype": "uint16",
                "band_count": 9,
                "nodata": 0,
                "descriptions": ["B04", "B08", "B05", "B06", "B07", "B11", "B12", "B03", "B02"],
            },
            "scl": {
                "path": "scl.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [10, 10],
                "width": 10980,
                "height": 10980,
                "dtype": "uint8",
                "band_count": 1,
                "nodata": 0,
            },
        },
    }


def _s1_manifest() -> dict:
    return {
        "source_id": "sentinel-1-grd",
        "product_id": ("S1C_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE"),
        "platform": "sentinel-1c",
        "acquisition_datetime": "2026-04-27T00:20:15Z",
        "sar:instrument_mode": "IW",
        "product:type": "IW_GRDH_1S",
        "sat:relative_orbit": 42,
        "sat:orbit_state": "ascending",
        "sar:polarizations": ["VV", "VH"],
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "outputs": {
            "backscatter": {
                "path": "backscatter.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [10, 10],
                "width": 10980,
                "height": 10980,
                "dtype": "float32",
                "band_count": 2,
                "nodata": -9999,
            },
        },
    }


def test_default_ingestion_collection_is_resourcesat_liss3():
    assert config.COLLECTION_ID == config.RESOURCESAT_LISS3_COLLECTION_ID


def test_default_seed_all_does_not_create_legacy_sentinel_placeholders(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(catalog, "migrate_catalog", lambda: "migrated")
    monkeypatch.setattr(seed, "seed_stac", lambda method="upsert", collection_id=None: ["stac"])
    monkeypatch.setattr(
        seed,
        "seed_minio",
        lambda force=False: calls.append("seed_minio") or ["minio"],
    )

    out = seed.seed_all()

    assert out == ["migrated", "stac"]
    assert calls == []


def test_explicit_legacy_sentinel_seed_still_creates_placeholders(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(catalog, "migrate_catalog", lambda: "migrated")
    monkeypatch.setattr(seed, "seed_stac", lambda method="upsert", collection_id=None: ["stac"])
    monkeypatch.setattr(
        seed,
        "seed_minio",
        lambda force=False: calls.append("seed_minio") or ["minio"],
    )

    out = seed.seed_all(collection_id=config.SENTINEL2_COLLECTION_ID)

    assert out == ["migrated", "stac", "minio"]
    assert calls == ["seed_minio"]


def _eos04_sar_manifest() -> dict:
    manifest = _s1_manifest()
    manifest.update(
        {
            "source_id": "eos-04-sar-mrs-l2b",
            "collection": "EOS-04_SAR-MRS_L2B",
            "product_id": "EOS04_SAMPLE_SAR_MRS_L2B_20260427",
            "platform": "eos-04",
            "product_level": "L2B",
            "sar:instrument_mode": "MRS",
            "product:type": "SAR-MRS_L2B",
            "sar:frequency_band": "C",
            "sar:polarizations": ["HH", "HV"],
        }
    )
    manifest["outputs"]["backscatter"]["resolution"] = [25, 25]
    manifest["outputs"]["backscatter"]["width"] = 4096
    manifest["outputs"]["backscatter"]["height"] = 4096
    return manifest


def _nisar_sar_manifest() -> dict:
    manifest = _s1_manifest()
    manifest.update(
        {
            "source_id": "nisar-ssar-beta-gcov",
            "collection": "NISAR_SSAR-Beta_GCOV",
            "product_id": "NISAR_SAMPLE_SSAR_BETA_GCOV_20260427",
            "platform": "nisar",
            "product_level": "GCOV",
            "sar:instrument_mode": "GCOV",
            "product:type": "NISAR_SSAR-Beta_GCOV",
            "sar:frequency_band": "S",
            "sar:polarizations": ["VV"],
        }
    )
    manifest["outputs"]["backscatter"]["resolution"] = [30, 30]
    manifest["outputs"]["backscatter"]["width"] = 2048
    manifest["outputs"]["backscatter"]["height"] = 2048
    manifest["outputs"]["backscatter"]["band_count"] = 1
    return manifest


def _resourcesat_manifest() -> dict:
    return {
        "source_id": "resourcesat-2a-liss3-boa",
        "product_id": "RA319MAR2026048153009900065PSANSTUCSRHTDF",
        "platform": "resourcesat-2a",
        "product_level": "BOA",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "path": "99",
        "row": "65",
        "gsd": 24,
        "eo:cloud_cover": 12.5,
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "outputs": {
            "analytic": {
                "path": "analytic.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [24, 24],
                "width": 4575,
                "height": 4575,
                "dtype": "uint16",
                "band_count": 4,
                "nodata": 0,
            },
            "mask": {
                "path": "mask.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [24, 24],
                "width": 4575,
                "height": 4575,
                "dtype": "uint8",
                "band_count": 1,
                "nodata": 0,
            },
        },
    }


def _resourcesat_composite_manifest() -> dict:
    manifest = _resourcesat_manifest()
    manifest.pop("acquisition_datetime")
    manifest.pop("path")
    manifest.pop("row")
    manifest.update(
        {
            "product_id": "resourcesat-2a-liss3-boa-composite-bangalore-60km-2026-03-19",
            "composite": True,
            "aoi_id": "bangalore-60km",
            "composite_grid_crs": "EPSG:32643",
            "composite_resolution_meters": 24.0,
            "composite_grid_bounds": [799980.0, 1290240.0, 800028.0, 1290288.0],
            "composite_grid_dimensions": [2, 2],
            "product_level": "BOA-COMPOSITE",
            "composite_date": "2026-03-19",
            "period_start": "2026-03-05",
            "period_end": "2026-03-19",
            "properties": {
                "akasha:coverage_percent": 98.5,
                "akasha:usable_pixel_percent": 91.25,
                "akasha:cloud_masked_percent": 7.25,
            },
            "contributing_scenes": [
                {"id": "scene-a", "datetime": "2026-03-05T00:00:00Z"},
                {"id": "scene-b", "datetime": "2026-03-19T00:00:00Z"},
            ],
        }
    )
    return manifest


def _awifs_manifest() -> dict:
    manifest = _resourcesat_manifest()
    manifest.update(
        {
            "source_id": "resourcesat-2a-awifs-boa",
            "collection": "ResourceSat-2A_AWIFS_BOA",
            "product_id": "AW319MAR2026048153009900065PSANSTUCSRHTDF",
            "gsd": 56,
        }
    )
    manifest["outputs"]["analytic"]["resolution"] = [56, 56]
    manifest["outputs"]["mask"]["resolution"] = [56, 56]
    return manifest


def _cartosat_visual_manifest() -> dict:
    return {
        "source_id": "cartosat-3-gated",
        "product_id": "CARTOSAT3_OPERATOR_VISUAL_20260416",
        "platform": "cartosat-3",
        "product_level": "VISUAL-CONTEXT",
        "product:type": "operator-upload-visual",
        "acquisition_datetime": "2026-04-16T05:30:00Z",
        "gsd": 1.0,
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "properties": {
            "akasha:coverage_percent": 100.0,
            "akasha:metrics_provisional": True,
        },
        "outputs": {
            "visual": {
                "path": "visual.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [1.0, 1.0],
                "width": 10980,
                "height": 10980,
                "dtype": "uint16",
                "band_count": 3,
                "nodata": 0,
                "descriptions": ["red", "green", "blue"],
            },
        },
    }


def _eos06_ndvi_context_manifest() -> dict:
    return {
        "source_id": "eos-06-ocm-lac-ndvi-8day-360m",
        "collection": "EOS-06_OCM-LAC_NDVI_8day_360m",
        "product_id": "EOS06_OCM_LAC_NDVI_20260416",
        "platform": "eos-06",
        "product_level": "NDVI-CONTEXT",
        "product:type": "precomputed-ndvi-context",
        "acquisition_datetime": "2026-04-16T00:00:00Z",
        "gsd": 360,
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "properties": {
            "akasha:coverage_percent": 87.5,
            "akasha:metrics_provisional": True,
        },
        "outputs": {
            "ndvi": {
                "path": "ndvi.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [360, 360],
                "width": 305,
                "height": 305,
                "dtype": "float32",
                "band_count": 1,
                "nodata": -9999,
                "descriptions": ["NDVI"],
                "raster:bands": [
                    {
                        "data_type": "float32",
                        "nodata": -9999,
                        "spatial_resolution": 360,
                        "unit": "ndvi",
                        "name": "NDVI",
                    }
                ],
            },
        },
    }


def _irs1c_archive_manifest() -> dict:
    return {
        "source_id": "irs-1c-liss3-archive",
        "product_id": "IRS1C_LISS3_ARCHIVE_19980115",
        "platform": "irs-1c",
        "product_level": "ARCHIVE",
        "product:type": "operator-upload-archive",
        "acquisition_datetime": "1998-01-15T05:30:00Z",
        "gsd": 23.5,
        "band_role_mapping": {
            "GREEN": "B2",
            "RED": "B3",
            "NIR": "B4",
            "SWIR1": "B5",
        },
        "bbox": [77.0, 11.0, 78.0, 12.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 11.0], [78.0, 11.0], [78.0, 12.0], [77.0, 12.0], [77.0, 11.0]]],
        },
        "properties": {
            "akasha:coverage_percent": 94.0,
            "akasha:metrics_provisional": True,
        },
        "outputs": {
            "analytic": {
                "path": "analytic.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [23.5, 23.5],
                "width": 4672,
                "height": 4672,
                "dtype": "uint16",
                "band_count": 4,
                "nodata": 0,
                "eo:bands": [
                    {"name": "B2", "common_name": "green"},
                    {"name": "B3", "common_name": "red"},
                    {"name": "B4", "common_name": "nir"},
                    {"name": "B5", "common_name": "swir16"},
                ],
                "raster:bands": [
                    {
                        "data_type": "uint16",
                        "nodata": 0,
                        "spatial_resolution": 23.5,
                        "unit": "reflectance",
                    }
                ]
                * 4,
            },
            "mask": {
                "path": "mask.tif",
                "crs": "EPSG:32643",
                "bounds": [799980, 1290240, 909780, 1400040],
                "resolution": [23.5, 23.5],
                "width": 4672,
                "height": 4672,
                "dtype": "uint8",
                "band_count": 1,
                "nodata": 0,
                "classification:classes": [
                    {"value": 0, "name": "nodata", "nodata": True},
                    {"value": 1, "name": "valid"},
                ],
            },
        },
    }


def _write_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.acquisition_date / scene.mgrs_tile
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytic.tif").write_bytes(b"analytic")
    (directory / "scl.tif").write_bytes(b"scl")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_resourcesat_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.source_id / "scene" / scene.acquisition_date / scene.scene_component
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytic.tif").write_bytes(b"analytic")
    (directory / "mask.tif").write_bytes(b"mask")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_resourcesat_composite_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.source_id / "composite" / str(scene.aoi_id) / scene.acquisition_date
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytic.tif").write_bytes(b"analytic")
    (directory / "mask.tif").write_bytes(b"mask")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_s1_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = (
        root
        / scene.source_id
        / scene.acquisition_date
        / scene.relative_orbit_or_unknown
        / scene.scene_component
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "backscatter.tif").write_bytes(b"backscatter")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_context_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.source_id / scene.acquisition_date / scene.scene_component
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{scene.context_asset_key}.tif").write_bytes(scene.context_asset_key.encode())
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_archive_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.source_id / "archive" / scene.acquisition_date / scene.scene_component
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytic.tif").write_bytes(b"analytic")
    (directory / "mask.tif").write_bytes(b"mask")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_scene_identity_from_prepare_manifest_uses_dynamic_tile_keys() -> None:
    scene = SceneIdentity.from_prepare_manifest(_manifest(tile="43PHQ"))

    assert scene.scene_key == "sentinel-2-l2a:L2A:43PHQ:2026-01-15T05:20:00Z:05.00"
    assert scene.scene_component == "20260115T052000Z_0500"
    assert (
        scene.analytic_key == "sentinel-2-l2a/2026-01-15/43PHQ/20260115T052000Z_0500/analytic.tif"
    )
    assert scene.scl_key == "sentinel-2-l2a/2026-01-15/43PHQ/20260115T052000Z_0500/scl.tif"
    assert SAMPLE_SCENE.analytic_key == "sentinel-2-l2a/2025-09-14/analytic.tif"
    assert SAMPLE_SCENE.scl_key == "sentinel-2-l2a/2025-09-14/scl.tif"
    assert SAMPLE_SCENE.item_id == "sentinel-2-l2a_43PHP_20250914_0511"


def test_dynamic_scene_identity_disambiguates_same_date_tile_scenes() -> None:
    morning_scene = SceneIdentity.from_prepare_manifest(
        _manifest(tile="43PHQ", acquisition_datetime="2026-01-15T05:20:00Z")
    )
    later_baseline_scene = SceneIdentity.from_prepare_manifest(
        _manifest(
            tile="43PHQ",
            acquisition_datetime="2026-01-15T05:21:00Z",
            processing_baseline="05.01",
        )
    )

    assert morning_scene.item_id != later_baseline_scene.item_id
    assert morning_scene.analytic_key != later_baseline_scene.analytic_key
    assert morning_scene.scl_key != later_baseline_scene.scl_key
    assert morning_scene.scene_component == "20260115T052000Z_0500"
    assert later_baseline_scene.scene_component == "20260115T052100Z_0501"


def test_sentinel1_scene_identity_uses_manifest_orbit_fields_and_collision_safe_keys() -> None:
    scene = SceneIdentity.from_prepare_manifest(_s1_manifest())

    assert scene.source_id == "sentinel-1-grd"
    assert scene.platform == "sentinel-1c"
    assert scene.instrument_mode == "IW"
    assert scene.product_type == "IW_GRDH_1S"
    assert scene.relative_orbit_or_unknown == "42"
    assert scene.orbit_state_or_unknown == "ascending"
    assert scene.product_id_hash
    assert scene.product_id_hash in scene.scene_component
    assert scene.backscatter_key == (
        "sentinel-1-grd/2026-04-27/42/" f"{scene.scene_component}/backscatter.tif"
    )
    assert scene.item_id == f"sentinel-1-grd_42_{scene.scene_component}"


def test_eos04_sar_scene_identity_accepts_bhoonidhi_collection_alias() -> None:
    manifest = _eos04_sar_manifest()
    manifest.pop("source_id")

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.source_id == "eos-04-sar-mrs-l2b"
    assert scene.scene_key.startswith("eos-04-sar-mrs-l2b:eos-04:MRS:SAR-MRS_L2B")
    assert scene.backscatter_key.startswith("eos-04-sar-mrs-l2b/2026-04-27/42/")


def test_nisar_sar_scene_identity_accepts_bhoonidhi_collection_alias() -> None:
    manifest = _nisar_sar_manifest()
    manifest.pop("source_id")

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.source_id == "nisar-ssar-beta-gcov"
    assert scene.scene_key.startswith("nisar-ssar-beta-gcov:nisar:GCOV:NISAR_SSAR-Beta_GCOV")
    assert scene.backscatter_key.startswith("nisar-ssar-beta-gcov/2026-04-27/42/")
    assert scene.backscatter_key.endswith("/backscatter.tif")


def test_sentinel1_scene_identity_accepts_prepare_orbit_direction_alias() -> None:
    manifest = _s1_manifest()
    manifest.pop("sat:orbit_state")
    manifest["orbit_direction"] = "descending"

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.orbit_state_or_unknown == "descending"


def test_sentinel1_product_name_parser_handles_s1a_and_s1c_without_orbit_fields() -> None:
    for platform, expected in [
        ("S1A", "sentinel-1a"),
        ("S1C", "sentinel-1c"),
    ]:
        manifest = _s1_manifest()
        manifest.pop("platform")
        manifest.pop("sat:relative_orbit")
        manifest.pop("sat:orbit_state")
        manifest["product_id"] = (
            f"{platform}_IW_GRDH_1SDV_20260427T002015_" "20260427T002040_001234_ABCDEF_1234.SAFE"
        )

        scene = SceneIdentity.from_prepare_manifest(manifest)

        assert scene.platform == expected
        assert scene.relative_orbit_or_unknown == "unknown"
        assert scene.orbit_state_or_unknown == "unknown"
        assert scene.acquisition_datetime == "2026-04-27T00:20:15Z"


def test_resourcesat_scene_identity_uses_path_row_scene_keys() -> None:
    scene = SceneIdentity.from_prepare_manifest(_resourcesat_manifest())

    assert scene.source_id == "resourcesat-2a-liss3-boa"
    assert scene.path_or_unknown == "99"
    assert scene.row_or_unknown == "65"
    assert scene.scene_key == "resourcesat-2a-liss3-boa:BOA:99:65:2026-03-19T00:00:00Z"
    assert scene.scene_component.startswith("20260319T000000Z_path-99_row-65_")
    assert scene.product_id_hash in scene.scene_component
    assert scene.item_id == f"resourcesat-2a-liss3-boa_{scene.scene_component}"
    assert scene.analytic_key == (
        "resourcesat-2a-liss3-boa/scene/2026-03-19/" f"{scene.scene_component}/analytic.tif"
    )
    assert scene.mask_key == (
        "resourcesat-2a-liss3-boa/scene/2026-03-19/" f"{scene.scene_component}/mask.tif"
    )


def test_resourcesat_composite_identity_uses_composite_layout() -> None:
    scene = SceneIdentity.from_prepare_manifest(_resourcesat_composite_manifest())

    assert scene.composite is True
    assert scene.scene_key == (
        "resourcesat-2a-liss3-boa:composite:bangalore-60km:2026-03-19T00:00:00Z"
    )
    assert scene.item_id == "resourcesat-2a-liss3-boa_composite_bangalore-60km_2026-03-19"
    assert scene.analytic_key == (
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/analytic.tif"
    )
    assert scene.mask_key == (
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/mask.tif"
    )


def test_resourcesat_scene_identity_accepts_bhoonidhi_collection_alias() -> None:
    manifest = _resourcesat_manifest()
    manifest.pop("source_id")
    manifest["collection"] = "ResourceSat-2A_LISS3_BOA"

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.source_id == "resourcesat-2a-liss3-boa"
    assert scene.scene_key == "resourcesat-2a-liss3-boa:BOA:99:65:2026-03-19T00:00:00Z"


def test_awifs_scene_identity_accepts_bhoonidhi_collection_alias() -> None:
    manifest = _awifs_manifest()
    manifest.pop("source_id")

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.source_id == "resourcesat-2a-awifs-boa"
    assert scene.scene_key == "resourcesat-2a-awifs-boa:BOA:99:65:2026-03-19T00:00:00Z"
    assert scene.analytic_key.startswith("resourcesat-2a-awifs-boa/scene/2026-03-19/")


def test_cartosat_context_scene_identity_uses_visual_layout() -> None:
    scene = SceneIdentity.from_prepare_manifest(_cartosat_visual_manifest())

    assert scene.source_id == "cartosat-3-gated"
    assert scene.scene_key.startswith("cartosat-3-gated:operator-upload-visual:")
    assert scene.product_id_hash in scene.scene_component
    assert scene.item_id == f"cartosat-3-gated_{scene.scene_component}"
    assert scene.visual_key == f"cartosat-3-gated/2026-04-16/{scene.scene_component}/visual.tif"
    assert scene.context_asset_key == "visual"
    assert scene.context_key == scene.visual_key


def test_eos06_context_scene_identity_uses_ndvi_layout_and_collection_alias() -> None:
    manifest = _eos06_ndvi_context_manifest()
    manifest.pop("source_id")

    scene = SceneIdentity.from_prepare_manifest(manifest)

    assert scene.source_id == "eos-06-ocm-lac-ndvi-8day-360m"
    assert scene.scene_key.startswith(
        "eos-06-ocm-lac-ndvi-8day-360m:precomputed-ndvi-context:"
    )
    assert scene.context_asset_key == "ndvi"
    assert scene.context_key == (
        f"eos-06-ocm-lac-ndvi-8day-360m/2026-04-16/{scene.scene_component}/ndvi.tif"
    )


def test_irs1c_archive_scene_identity_uses_archive_layout() -> None:
    scene = SceneIdentity.from_prepare_manifest(_irs1c_archive_manifest())

    assert scene.source_id == "irs-1c-liss3-archive"
    assert scene.scene_key.startswith("irs-1c-liss3-archive:operator-upload-archive:")
    assert scene.product_id_hash in scene.scene_component
    assert scene.item_id == f"irs-1c-liss3-archive_{scene.scene_component}"
    assert scene.analytic_key == (
        f"irs-1c-liss3-archive/archive/1998-01-15/{scene.scene_component}/analytic.tif"
    )
    assert scene.mask_key == (
        f"irs-1c-liss3-archive/archive/1998-01-15/{scene.scene_component}/mask.tif"
    )


def test_build_stac_item_from_prepare_manifest_uses_dynamic_asset_hrefs() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_manifest(tile="43PHP"))

    assert item["id"] == "sentinel-2-l2a_43PHP_20260115T052000Z_0500"
    assert item["collection"] == "sentinel-2-l2a"
    assert item["bbox"] == [77.0, 11.0, 78.0, 12.0]
    assert item["geometry"]["coordinates"][0][0] == [77.0, 11.0]
    assert item["properties"]["s2:mgrs_tile"] == "43PHP"
    assert item["properties"]["proj:epsg"] == 32643
    assert item["properties"]["proj:shape"] == [10980, 10980]
    assert item["assets"]["analytic"]["href"].endswith(
        "sentinel-2-l2a/2026-01-15/43PHP/20260115T052000Z_0500/analytic.tif"
    )
    assert item["assets"]["scl"]["href"].endswith(
        "sentinel-2-l2a/2026-01-15/43PHP/20260115T052000Z_0500/scl.tif"
    )
    assert len(item["assets"]["analytic"]["eo:bands"]) == 9
    assert len(item["assets"]["analytic"]["raster:bands"]) == 9


def test_build_resourcesat_stac_item_emits_liss3_mask_contract() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_resourcesat_manifest())

    scene = SceneIdentity.from_prepare_manifest(_resourcesat_manifest())
    assert item["id"] == f"resourcesat-2a-liss3-boa_{scene.scene_component}"
    assert item["collection"] == "resourcesat-2a-liss3-boa"
    assert item["properties"]["constellation"] == "resourcesat"
    assert item["properties"]["instruments"] == ["liss-3"]
    assert item["properties"]["product:type"] == "BOA"
    assert item["properties"]["akasha:path"] == "99"
    assert item["properties"]["akasha:row"] == "65"
    assert item["properties"]["akasha:metrics_provisional"] is True
    assert item["properties"]["akasha:band_role_mapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert "Akasha threshold mask v1" in item["properties"]["akasha:mask_method"]
    assert list(item["assets"]) == ["analytic", "mask"]
    assert item["assets"]["analytic"]["href"].endswith("/analytic.tif")
    assert item["assets"]["mask"]["href"].endswith("/mask.tif")
    assert [band["name"] for band in item["assets"]["analytic"]["eo:bands"]] == [
        "BAND2",
        "BAND3",
        "BAND4",
        "BAND5",
    ]
    assert [band["offset"] for band in item["assets"]["analytic"]["raster:bands"]] == [
        0,
        0,
        0,
        0,
    ]
    assert [band["scale"] for band in item["assets"]["analytic"]["raster:bands"]] == [
        0.0001,
        0.0001,
        0.0001,
        0.0001,
    ]
    assert [klass["value"] for klass in item["assets"]["mask"]["classification:classes"]] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert "scl" not in item["assets"]


def test_build_awifs_stac_item_uses_awifs_collection_and_resolution() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_awifs_manifest())

    assert item["collection"] == "resourcesat-2a-awifs-boa"
    assert item["properties"]["instruments"] == ["awifs"]
    assert item["properties"]["gsd"] == 56
    assert item["assets"]["analytic"]["gsd"] == 56
    assert item["assets"]["analytic"]["title"].startswith("ResourceSat-2A AWiFS BOA")
    assert item["assets"]["analytic"]["raster:bands"][0]["spatial_resolution"] == 56
    assert item["assets"]["analytic"]["href"].startswith(
        "s3://akasha-cogs/resourcesat-2a-awifs-boa/"
    )


def test_build_resourcesat_composite_stac_item_emits_composite_metadata() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_resourcesat_composite_manifest())

    assert item["id"] == "resourcesat-2a-liss3-boa_composite_bangalore-60km_2026-03-19"
    assert item["properties"]["akasha:composite"] is True
    assert item["properties"]["akasha:aoi_id"] == "bangalore-60km"
    assert item["properties"]["akasha:composite_grid_crs"] == "EPSG:32643"
    assert item["properties"]["akasha:composite_resolution_meters"] == 24.0
    assert item["properties"]["akasha:composite_grid_bounds"] == [
        799980.0,
        1290240.0,
        800028.0,
        1290288.0,
    ]
    assert item["properties"]["akasha:composite_grid_dimensions"] == [2, 2]
    assert item["properties"]["akasha:period_start"] == "2026-03-05"
    assert item["properties"]["akasha:period_end"] == "2026-03-19"
    assert item["properties"]["akasha:coverage_percent"] == 98.5
    assert item["properties"]["akasha:usable_pixel_percent"] == 91.25
    assert item["properties"]["akasha:cloud_masked_percent"] == 7.25
    assert item["properties"]["akasha:contributing_scenes"][1]["id"] == "scene-b"
    assert "akasha:path" not in item["properties"]
    assert "akasha:row" not in item["properties"]
    assert item["assets"]["analytic"]["href"].endswith(
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/analytic.tif"
    )
    assert item["assets"]["mask"]["href"].endswith(
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/mask.tif"
    )


def test_build_sentinel1_stac_item_emits_sar_metadata_and_backscatter_asset() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_s1_manifest())

    assert item["collection"] == "sentinel-1-grd"
    assert "https://stac-extensions.github.io/sar/v1.0.0/schema.json" in item["stac_extensions"]
    assert item["properties"]["constellation"] == "sentinel-1"
    assert item["properties"]["sar:instrument_mode"] == "IW"
    assert item["properties"]["sar:polarizations"] == ["VV", "VH"]
    assert item["properties"]["sat:relative_orbit"] == 42
    assert item["properties"]["sat:orbit_state"] == "ascending"
    assert list(item["assets"]) == ["backscatter"]
    assert item["assets"]["backscatter"]["href"].endswith("/backscatter.tif")
    assert item["assets"]["backscatter"]["raster:bands"][0]["unit"] == "dB"
    assert "eo:bands" not in item["assets"]["backscatter"]
    assert "scl" not in item["assets"]


def test_build_eos04_sar_stac_item_emits_sar_safe_metadata() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_eos04_sar_manifest())

    assert item["collection"] == "eos-04-sar-mrs-l2b"
    assert item["properties"]["constellation"] == "eos-04"
    assert item["properties"]["instruments"] == ["sar"]
    assert item["properties"]["sar:instrument_mode"] == "MRS"
    assert item["properties"]["sar:frequency_band"] == "C"
    assert item["properties"]["sar:polarizations"] == ["HH", "HV"]
    assert item["properties"]["akasha:date_metrics_kind"] == "radar"
    assert item["assets"]["backscatter"]["href"].startswith(
        "s3://akasha-cogs/eos-04-sar-mrs-l2b/"
    )
    assert item["assets"]["backscatter"]["raster:bands"][0]["unit"] == "dB"
    assert "eo:bands" not in item["assets"]["backscatter"]
    assert "analytic" not in item["assets"]


def test_build_nisar_sar_stac_item_emits_sar_safe_metadata() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_nisar_sar_manifest())

    assert item["collection"] == "nisar-ssar-beta-gcov"
    assert item["properties"]["constellation"] == "nisar"
    assert item["properties"]["instruments"] == ["s-sar"]
    assert item["properties"]["sar:instrument_mode"] == "GCOV"
    assert item["properties"]["sar:frequency_band"] == "S"
    assert item["properties"]["sar:polarizations"] == ["VV"]
    assert item["properties"]["akasha:date_metrics_kind"] == "radar"
    assert item["assets"]["backscatter"]["href"].startswith(
        "s3://akasha-cogs/nisar-ssar-beta-gcov/"
    )
    assert item["assets"]["backscatter"]["raster:bands"] == [
        {
            "data_type": "float32",
            "spatial_resolution": 30,
            "unit": "dB",
            "name": "VV_dB",
            "nodata": -9999,
        }
    ]
    assert "eo:bands" not in item["assets"]["backscatter"]
    assert list(item["assets"]) == ["backscatter"]


def test_build_cartosat_context_stac_item_emits_visual_only_metadata() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_cartosat_visual_manifest())

    assert item["collection"] == "cartosat-3-gated"
    assert item["properties"]["platform"] == "cartosat-3"
    assert item["properties"]["akasha:date_metrics_kind"] == "context"
    assert item["properties"]["akasha:crop_indices_enabled"] is False
    assert item["properties"]["akasha:coverage_percent"] == 100.0
    assert list(item["assets"]) == ["visual"]
    assert item["assets"]["visual"]["href"].startswith("s3://akasha-cogs/cartosat-3-gated/")
    assert item["assets"]["visual"]["roles"] == ["data", "visual"]
    assert [band["name"] for band in item["assets"]["visual"]["raster:bands"]] == [
        "red",
        "green",
        "blue",
    ]
    assert "analytic" not in item["assets"]
    assert "mask" not in item["assets"]
    assert "scl" not in item["assets"]
    assert "eo:cloud_cover" not in item["properties"]


def test_build_eos06_context_stac_item_emits_ndvi_asset_without_analytics() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_eos06_ndvi_context_manifest())

    assert item["collection"] == "eos-06-ocm-lac-ndvi-8day-360m"
    assert item["properties"]["platform"] == "eos-06"
    assert item["properties"]["constellation"] == "eos-06"
    assert item["properties"]["instruments"] == ["ocm"]
    assert item["properties"]["akasha:date_metrics_kind"] == "context"
    assert item["properties"]["akasha:crop_indices_enabled"] is False
    assert item["properties"]["akasha:coverage_percent"] == 87.5
    assert list(item["assets"]) == ["ndvi"]
    assert item["assets"]["ndvi"]["href"].startswith(
        "s3://akasha-cogs/eos-06-ocm-lac-ndvi-8day-360m/"
    )
    assert item["assets"]["ndvi"]["href"].endswith("/ndvi.tif")
    assert item["assets"]["ndvi"]["roles"] == ["data", "index", "ndvi"]
    assert item["assets"]["ndvi"]["raster:bands"][0]["unit"] == "ndvi"
    assert "analytic" not in item["assets"]
    assert "mask" not in item["assets"]
    assert "scl" not in item["assets"]


def test_build_irs1c_archive_stac_item_emits_analytics_disabled_assets() -> None:
    item = catalog.build_stac_item_from_prepare_manifest(_irs1c_archive_manifest())

    scene = SceneIdentity.from_prepare_manifest(_irs1c_archive_manifest())
    assert item["collection"] == "irs-1c-liss3-archive"
    assert item["id"] == f"irs-1c-liss3-archive_{scene.scene_component}"
    assert item["properties"]["platform"] == "irs-1c"
    assert item["properties"]["akasha:date_metrics_kind"] == "archive"
    assert item["properties"]["akasha:crop_indices_enabled"] is False
    assert item["properties"]["akasha:coverage_percent"] == 94.0
    assert item["properties"]["akasha:band_role_mapping"] == {
        "GREEN": "B2",
        "RED": "B3",
        "NIR": "B4",
        "SWIR1": "B5",
    }
    assert list(item["assets"]) == ["analytic", "mask"]
    assert item["assets"]["analytic"]["href"].endswith("/analytic.tif")
    assert item["assets"]["mask"]["href"].endswith("/mask.tif")
    assert item["assets"]["analytic"]["roles"] == ["data", "reflectance", "archive"]
    assert item["assets"]["mask"]["roles"] == ["metadata", "data-mask", "archive"]
    assert "scl" not in item["assets"]


def test_build_stac_item_transforms_projected_output_bounds_to_wgs84() -> None:
    manifest = _manifest(tile="43PHP")
    manifest.pop("bbox")
    manifest.pop("geometry")

    item = catalog.build_stac_item_from_prepare_manifest(manifest)

    assert item["bbox"] == pytest.approx(
        [77.75127791535229, 11.647042899643449, 78.77093931726162, 12.650224959163648]
    )
    assert item["geometry"] == {
        "type": "Polygon",
        "coordinates": [
            [
                [item["bbox"][0], item["bbox"][1]],
                [item["bbox"][2], item["bbox"][1]],
                [item["bbox"][2], item["bbox"][3]],
                [item["bbox"][0], item["bbox"][3]],
                [item["bbox"][0], item["bbox"][1]],
            ]
        ],
    }
    assert item["properties"]["proj:bbox"] == [799980, 1290240, 909780, 1400040]
    assert all(-180 <= value <= 180 for value in (item["bbox"][0], item["bbox"][2]))
    assert all(-90 <= value <= 90 for value in (item["bbox"][1], item["bbox"][3]))


def test_seed_manifest_cogs_uploads_to_dynamic_keys_without_live_s3(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_manifest(scratch_dir, _manifest(tile="43PLQ"))

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    uploaded_keys = [call[2] for call in fake_client.uploads]
    assert uploaded_keys == [
        "sentinel-2-l2a/2026-01-15/43PLQ/20260115T052000Z_0500/analytic.tif",
        "sentinel-2-l2a/2026-01-15/43PLQ/20260115T052000Z_0500/scl.tif",
    ]
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_sentinel1_backscatter_only(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_s1_manifest(scratch_dir, _s1_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    uploaded_keys = [call[2] for call in fake_client.uploads]
    assert len(uploaded_keys) == 1
    assert uploaded_keys[0].startswith("sentinel-1-grd/2026-04-27/42/")
    assert uploaded_keys[0].endswith("/backscatter.tif")
    assert fake_client.uploads[0][3]["Metadata"]["akasha-asset"] == "backscatter"
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_nisar_backscatter_only(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_s1_manifest(scratch_dir, _nisar_sar_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    uploaded_keys = [call[2] for call in fake_client.uploads]
    assert len(uploaded_keys) == 1
    assert uploaded_keys[0].startswith("nisar-ssar-beta-gcov/2026-04-27/42/")
    assert uploaded_keys[0].endswith("/backscatter.tif")
    assert fake_client.uploads[0][3]["Metadata"]["akasha-asset"] == "backscatter"
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_cartosat_visual_only(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_context_manifest(scratch_dir, _cartosat_visual_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    scene = SceneIdentity.from_prepare_manifest(_cartosat_visual_manifest())
    assert [call[2] for call in fake_client.uploads] == [scene.visual_key]
    assert fake_client.uploads[0][3]["Metadata"]["akasha-asset"] == "visual"
    assert fake_client.uploads[0][3]["Metadata"]["akasha-placeholder"] == "false"
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_eos06_ndvi_context_only(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_context_manifest(scratch_dir, _eos06_ndvi_context_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    scene = SceneIdentity.from_prepare_manifest(_eos06_ndvi_context_manifest())
    assert [call[2] for call in fake_client.uploads] == [scene.context_key]
    assert fake_client.uploads[0][3]["Metadata"]["akasha-asset"] == "ndvi"
    assert fake_client.uploads[0][3]["Metadata"]["akasha-placeholder"] == "false"
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_irs1c_archive_analytic_and_mask(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_archive_manifest(scratch_dir, _irs1c_archive_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    scene = SceneIdentity.from_prepare_manifest(_irs1c_archive_manifest())
    assert [call[2] for call in fake_client.uploads] == [scene.analytic_key, scene.mask_key]
    assert [call[3]["Metadata"]["akasha-asset"] for call in fake_client.uploads] == [
        "analytic",
        "mask",
    ]
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_resourcesat_analytic_and_mask(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_resourcesat_manifest(scratch_dir, _resourcesat_manifest())

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    result = storage.seed_manifest_cogs([manifest_path])

    uploaded_keys = [call[2] for call in fake_client.uploads]
    assert len(uploaded_keys) == 2
    assert uploaded_keys[0].startswith("resourcesat-2a-liss3-boa/scene/2026-03-19/")
    assert uploaded_keys[0].endswith("/analytic.tif")
    assert uploaded_keys[1].startswith("resourcesat-2a-liss3-boa/scene/2026-03-19/")
    assert uploaded_keys[1].endswith("/mask.tif")
    assert [call[3]["Metadata"]["akasha-asset"] for call in fake_client.uploads] == [
        "analytic",
        "mask",
    ]
    assert result[0].startswith("uploaded prepared COG")


def test_seed_manifest_cogs_uploads_resourcesat_composite_layout(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_resourcesat_composite_manifest(
        scratch_dir,
        _resourcesat_composite_manifest(),
    )

    class FakeClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str, dict]] = []

        def upload_file(
            self, filename: str, bucket: str, key: str, ExtraArgs: dict
        ) -> None:  # noqa: N803
            self.uploads.append((filename, bucket, key, ExtraArgs))

    fake_client = FakeClient()
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    monkeypatch.setattr(storage, "_object_exists", lambda _client, _key: False)

    discovered = config.prepared_manifest_files(
        root=scratch_dir,
        source_id=config.RESOURCESAT_LISS3_COLLECTION_ID,
    )
    result = storage.seed_manifest_cogs(discovered)

    assert discovered == [manifest_path.resolve()]
    assert [call[2] for call in fake_client.uploads] == [
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/analytic.tif",
        "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19/mask.tif",
    ]
    assert result[0].startswith("uploaded prepared COG")


def test_verify_manifest_cogs_accepts_sentinel1_backscatter_without_s2_assets(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_s1_manifest(scratch_dir, _s1_manifest())

    class FakeClient:
        def head_bucket(self, Bucket: str) -> None:  # noqa: N803
            return None

    monkeypatch.setattr(storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        storage,
        "object_status",
        lambda _client, key: {"key": key, "exists": True, "size": 12, "placeholder": False},
    )
    monkeypatch.setattr(storage, "_verify_cog_metadata", lambda _scene: (True, "ok"))

    ok, detail = storage.verify_manifest_cogs([manifest_path])

    assert ok
    assert "verified 1 manifest scene" in detail


def test_verify_manifest_cogs_accepts_cartosat_visual_without_analytic_assets(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_context_manifest(scratch_dir, _cartosat_visual_manifest())

    class FakeClient:
        def head_bucket(self, Bucket: str) -> None:  # noqa: N803
            return None

    monkeypatch.setattr(storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        storage,
        "object_status",
        lambda _client, key: {"key": key, "exists": True, "size": 12, "placeholder": False},
    )
    monkeypatch.setattr(storage, "_verify_cog_metadata", lambda _scene: (True, "ok"))

    ok, detail = storage.verify_manifest_cogs([manifest_path])

    assert ok
    assert "verified 1 manifest scene" in detail


def test_verify_manifest_cogs_accepts_irs1c_archive_analytic_and_mask(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_path = _write_archive_manifest(scratch_dir, _irs1c_archive_manifest())

    class FakeClient:
        def head_bucket(self, Bucket: str) -> None:  # noqa: N803
            return None

    monkeypatch.setattr(storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        storage,
        "object_status",
        lambda _client, key: {"key": key, "exists": True, "size": 12, "placeholder": False},
    )
    monkeypatch.setattr(storage, "_verify_cog_metadata", lambda _scene: (True, "ok"))

    ok, detail = storage.verify_manifest_cogs([manifest_path])

    assert ok
    assert "verified 1 manifest scene" in detail


def test_load_manifest_items_writes_multi_item_ndjson_without_live_pgstac(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    manifest_paths = [
        _write_manifest(scratch_dir, _manifest(tile="43PHQ")),
        _write_manifest(scratch_dir, _manifest(tile="43PLQ")),
    ]
    captured: dict[str, object] = {}

    class FakeDB:
        def __init__(self, dsn: str) -> None:
            captured["dsn"] = dsn

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

    class FakeMethods(str):
        pass

    class FakeLoader:
        def __init__(self, db: FakeDB) -> None:
            self.db = db

        def load_items(self, ndjson_path: str, insert_mode: FakeMethods) -> None:
            path = Path(ndjson_path)
            captured["path"] = path
            captured["mode"] = str(insert_mode)
            captured["records"] = [json.loads(line) for line in path.read_text().splitlines()]

    package = types.ModuleType("pypgstac")
    db_module = types.ModuleType("pypgstac.db")
    db_module.PgstacDB = FakeDB
    load_module = types.ModuleType("pypgstac.load")
    load_module.Loader = FakeLoader
    load_module.Methods = FakeMethods
    monkeypatch.setitem(sys.modules, "pypgstac", package)
    monkeypatch.setitem(sys.modules, "pypgstac.db", db_module)
    monkeypatch.setitem(sys.modules, "pypgstac.load", load_module)
    monkeypatch.setattr(catalog.config, "DATABASE_URL", "postgresql://example/db")

    result = catalog.load_manifest_items(manifest_paths, method="insert_ignore")

    records = captured["records"]
    assert result == "loaded 2 manifest item(s) (method=insert_ignore)"
    assert captured["dsn"] == "postgresql://example/db"
    assert captured["mode"] == "insert_ignore"
    assert [record["properties"]["s2:mgrs_tile"] for record in records] == ["43PHQ", "43PLQ"]
    assert all(
        "/2026-01-15/43P" in record["assets"]["analytic"]["href"]
        and "/20260115T052000Z_0500/" in record["assets"]["analytic"]["href"]
        for record in records
    )
    assert not captured["path"].exists()


def test_prepared_manifest_files_discovers_legacy_and_tile_scoped_layouts(
    scratch_dir: Path,
) -> None:
    root = scratch_dir / "rasters"
    tile_manifest = root / "2026-01-15" / "43PHQ" / "prepare_manifest.json"
    legacy_manifest = root / "2025-09-14" / "prepare_manifest.json"
    tile_manifest.parent.mkdir(parents=True)
    legacy_manifest.parent.mkdir(parents=True)
    tile_manifest.write_text("{}", encoding="utf-8")
    legacy_manifest.write_text("{}", encoding="utf-8")

    assert config.prepared_manifest_files(root=root) == [
        legacy_manifest.resolve(),
        tile_manifest.resolve(),
    ]


def test_prepared_manifest_files_discovers_sentinel1_source_scoped_layout(
    scratch_dir: Path,
) -> None:
    root = scratch_dir / "rasters"
    s1_manifest = (
        root
        / "sentinel-1-grd"
        / "2026-04-27"
        / "42"
        / "20260427T002015Z_scene"
        / "prepare_manifest.json"
    )
    s2_manifest = root / "2026-01-15" / "43PHQ" / "prepare_manifest.json"
    s1_manifest.parent.mkdir(parents=True)
    s2_manifest.parent.mkdir(parents=True)
    s1_manifest.write_text("{}", encoding="utf-8")
    s2_manifest.write_text("{}", encoding="utf-8")

    assert config.collection_file("sentinel-1-grd").name == "sentinel-1-grd-collection.json"
    assert config.prepared_manifest_files(root=root, source_id="sentinel-1-grd") == [
        s1_manifest.resolve()
    ]


def test_prepared_manifest_files_discovers_cartosat_context_layout(
    scratch_dir: Path,
) -> None:
    manifest_path = _write_context_manifest(scratch_dir / "rasters", _cartosat_visual_manifest())

    assert config.prepared_manifest_files(
        root=scratch_dir / "rasters",
        source_id="cartosat-3-gated",
    ) == [manifest_path.resolve()]


def test_resourcesat_sample_item_is_contract_only_not_seed_loaded(
    monkeypatch: pytest.MonkeyPatch, scratch_dir: Path
) -> None:
    stac_dir = scratch_dir / "stac"
    stac_dir.mkdir(parents=True)
    sample = stac_dir / "resourcesat-2a-liss3-boa-sample-item.json"
    sample.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "find_seed_dir", lambda: scratch_dir)

    assert config.item_file("resourcesat-2a-liss3-boa") == sample
    assert config.item_files("resourcesat-2a-liss3-boa") == []
