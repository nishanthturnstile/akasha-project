from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_context_cog.py"
WORKER_PATH = REPO_ROOT / "services" / "ingestion" / "worker.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prepare_context = _load_module(SCRIPT_PATH, "prepare_context_cog_test_module")
worker = _load_module(WORKER_PATH, "worker_context_cog_test_module")


def _write_visual_geotiff(path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    np = pytest.importorskip("numpy")
    from rasterio.transform import from_origin

    data = np.zeros((3, 8, 8), dtype="uint16")
    data[0, :, :] = 100
    data[1, :, :] = 200
    data[2, :, :] = 300
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=3,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(77.0, 13.0, 0.01, 0.01),
    ) as dataset:
        dataset.write(data)
        dataset.set_band_description(1, "red")
        dataset.set_band_description(2, "green")
        dataset.set_band_description(3, "blue")


def test_prepare_context_cog_writes_cartosat_visual_manifest(tmp_path: Path) -> None:
    pytest.importorskip("rio_cogeo")
    source = tmp_path / "cartosat_visual.tif"
    output_root = tmp_path / "rasters"
    _write_visual_geotiff(source)

    result = prepare_context.main(
        [
            "--source",
            "cartosat-3-gated",
            "--input",
            str(source),
            "--product-id",
            "CARTOSAT3_ORDER_42",
            "--acquisition-datetime",
            "2026-04-16T05:30:00Z",
            "--output-root",
            str(output_root),
            "--skip-validation",
        ]
    )

    manifests = list((output_root / "cartosat-3-gated").glob("2026-04-16/*/prepare_manifest.json"))
    assert result == 0
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    visual = manifests[0].parent / "visual.tif"
    assert visual.is_file()
    assert manifest["source_id"] == "cartosat-3-gated"
    assert manifest["product_id"] == "CARTOSAT3_ORDER_42"
    assert manifest["product:type"] == "operator-upload-visual"
    assert manifest["bbox"] == pytest.approx([77.0, 12.92, 77.08, 13.0])
    assert manifest["outputs"]["visual"]["path"] == "visual.tif"
    assert manifest["outputs"]["visual"]["band_count"] == 3
    assert manifest["outputs"]["visual"]["descriptions"] == ["red", "green", "blue"]
    assert manifest["gsd"] == 1.1
    assert manifest["outputs"]["visual"]["gsd"] == 1.1


def test_worker_prepare_context_cog_delegates_to_repo_script(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command, check):
        calls.append(command)
        assert check is True

    monkeypatch.setattr(worker.subprocess, "run", fake_run)

    result = worker.main(
        [
            "prepare-context-cog",
            "--source",
            "cartosat-3-gated",
            "--input",
            str(tmp_path / "visual.tif"),
            "--product-id",
            "CARTOSAT3_ORDER_42",
            "--acquisition-datetime",
            "2026-04-16T05:30:00Z",
            "--output-root",
            str(tmp_path / "rasters"),
            "--skip-validation",
        ]
    )

    assert result == 0
    assert calls
    command = calls[0]
    assert Path(command[1]).parts[-2:] == ("scripts", "prepare_context_cog.py")
    assert "--source" in command
    assert "cartosat-3-gated" in command
    assert "--skip-validation" in command


def test_worker_parser_defaults_work_from_flat_container_layout(
    monkeypatch, tmp_path: Path
) -> None:
    app_root = tmp_path / "app"
    (app_root / "data" / "seed").mkdir(parents=True)
    (app_root / "scripts").mkdir()

    monkeypatch.setattr(worker, "__file__", str(app_root / "worker.py"))
    monkeypatch.chdir(app_root)

    parser = worker.build_parser()
    args = parser.parse_args(
        [
            "prepare-context-cog",
            "--source",
            "cartosat-3-gated",
            "--input",
            "visual.tif",
            "--product-id",
            "CARTOSAT3_ORDER_42",
            "--acquisition-datetime",
            "2026-04-16T05:30:00Z",
        ]
    )

    assert Path(args.output_root) == app_root / "data" / "seed" / "rasters"
