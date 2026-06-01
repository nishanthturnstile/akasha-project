from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

import pytest
from akasha_ingest import catalog, config, storage
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
            f"S2B_MSIL2A_{date.replace('-', '')}T052000_N0500_R019_"
            f"T{tile}_20260115T074457.SAFE"
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


def _write_manifest(root: Path, manifest: dict) -> Path:
    scene = SceneIdentity.from_prepare_manifest(manifest)
    directory = root / scene.acquisition_date / scene.mgrs_tile
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytic.tif").write_bytes(b"analytic")
    (directory / "scl.tif").write_bytes(b"scl")
    path = directory / "prepare_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_scene_identity_from_prepare_manifest_uses_dynamic_tile_keys() -> None:
    scene = SceneIdentity.from_prepare_manifest(_manifest(tile="43PHQ"))

    assert scene.scene_key == "sentinel-2-l2a:L2A:43PHQ:2026-01-15T05:20:00Z:05.00"
    assert scene.scene_component == "20260115T052000Z_0500"
    assert (
        scene.analytic_key
        == "sentinel-2-l2a/2026-01-15/43PHQ/20260115T052000Z_0500/analytic.tif"
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

        def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict) -> None:  # noqa: N803
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
