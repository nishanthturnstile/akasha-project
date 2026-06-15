import json
from pathlib import Path

import numpy as np
import pytest

from scripts.prepare_resourcesat_liss3_boa_cogs import (
    MASK_METHOD,
    PreparedPaths,
    ResourceSatMeta,
    SelectedProduct,
    build_mask_array,
    load_selected_products,
    output_dir_for_product,
    parse_band_meta,
    scene_component,
    write_manifest,
)


def test_parse_band_meta_reads_path_row_date_and_backgrounds(tmp_path: Path) -> None:
    meta_path = tmp_path / "BAND_META.txt"
    meta_path.write_text(
        "\n".join(
            [
                "PATH = 99",
                "ROW = 65",
                "DATE = 19MAR2026",
                "BAND2_BACKGROUND_VALUE = 0",
                "BAND3_BACKGROUND_VALUE = 0",
                "BAND4_BACKGROUND_VALUE = 0",
                "BAND5_BACKGROUND_VALUE = 0",
                "REFLECTANCE_SCALE = 0.0001",
                "REFLECTANCE_OFFSET = 0",
            ]
        ),
        encoding="utf-8",
    )

    meta = parse_band_meta(meta_path)

    assert meta.path == "99"
    assert meta.row == "65"
    assert meta.acquisition_datetime == "2026-03-19T00:00:00Z"
    assert meta.background_values == {
        "BAND2": 0,
        "BAND3": 0,
        "BAND4": 0,
        "BAND5": 0,
    }
    assert meta.scale == 0.0001
    assert meta.offset == 0


def test_resourcesat_mask_generation_uses_provisional_classes() -> None:
    # band order: BAND2 green, BAND3 red, BAND4 nir, BAND5 swir1
    analytic = np.array(
        [
            [[0, 1200, 900, 500, 4500]],
            [[0, 1100, 700, 500, 4200]],
            [[0, 3600, 500, 500, 4300]],
            [[0, 2600, 400, 500, 3800]],
        ],
        dtype="uint16",
    )

    mask = build_mask_array(np, analytic)

    assert mask.tolist() == [[0, 1, 4, 3, 2]]


def test_selection_manifest_accepts_bhoonidhi_download_candidates(tmp_path: Path) -> None:
    manifest_path = tmp_path / "download_manifest.json"
    downloaded = tmp_path / "raw" / "resourcesat-2a-liss3-boa" / "RS_PRODUCT.zip"
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "candidates": [
                    {
                        "item_id": "RS_PRODUCT",
                        "datetime": "2026-03-19T00:00:00Z",
                    }
                ],
                "downloaded": [
                    {
                        "item_id": "RS_PRODUCT",
                        "downloaded_path": downloaded.as_posix(),
                        "datetime": "2026-03-19T00:00:00Z",
                        "path": "99",
                        "row": "65",
                        "bbox": [77.0, 11.0, 78.0, 12.0],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    products = load_selected_products(manifest_path, raw_dir=tmp_path / "raw")

    assert len(products) == 1
    assert products[0].product_id == "RS_PRODUCT"
    assert products[0].source_path == downloaded
    assert products[0].acquisition_date == "2026-03-19"
    assert products[0].path == "99"
    assert products[0].row == "65"


def test_output_dir_matches_resourcesat_scene_component(tmp_path: Path) -> None:
    product = SelectedProduct(
        product_id="RA319MAR2026048153009900065PSANSTUCSRHTDF",
        source_path=tmp_path / "source.zip",
        acquisition_datetime="2026-03-19T00:00:00Z",
        acquisition_date="2026-03-19",
        path="99",
        row="65",
    )

    output_dir = output_dir_for_product(tmp_path / "rasters", product)

    assert output_dir == (
        tmp_path / "rasters" / "scene" / "2026-03-19" / scene_component(product)
    )
    assert scene_component(product).startswith("20260319T000000Z_path-99_row-65_")


def test_write_manifest_emits_resourcesat_contract(tmp_path: Path) -> None:
    expected_bbox = [77.0, 11.0, 78.0, 12.0]

    class FakeCrs:
        def to_string(self) -> str:
            return "EPSG:32643"

    class FakeDataset:
        def __init__(self, count: int, descriptions: tuple[str, ...]) -> None:
            self.count = count
            self.descriptions = descriptions

        crs = FakeCrs()
        bounds = (799980, 1290240, 909780, 1400040)
        res = (24, 24)
        transform = (24, 0, 799980, 0, -24, 1400040, 0, 0, 1)
        width = 4575
        height = 4575
        dtypes = ("uint16",)
        nodata = 0

        def __enter__(self) -> "FakeDataset":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def overviews(self, _band: int) -> list[int]:
            return [2, 4]

    class FakeRasterio:
        def open(self, path: Path) -> FakeDataset:
            if Path(path).name == "mask.tif":
                return FakeDataset(1, ("mask",))
            return FakeDataset(4, ("BAND2", "BAND3", "BAND4", "BAND5"))

    def fake_transform_bounds(*_args: object, **_kwargs: object) -> list[float]:
        return expected_bbox

    product_dir = tmp_path / "product"
    product_dir.mkdir()
    (product_dir / "BAND_META.txt").write_text("PATH=99\nROW=65\n", encoding="utf-8")
    product = SelectedProduct(
        product_id="RS_PRODUCT",
        source_path=tmp_path / "RS_PRODUCT.zip",
        acquisition_datetime="2026-03-19T00:00:00Z",
        acquisition_date="2026-03-19",
        path="99",
        row="65",
    )
    paths = PreparedPaths(
        product=product,
        product_dir=product_dir,
        output_dir=tmp_path / "out",
        analytic_cog=tmp_path / "out" / "analytic.tif",
        mask_cog=tmp_path / "out" / "mask.tif",
        manifest=tmp_path / "out" / "prepare_manifest.json",
    )

    write_manifest(
        deps={"rasterio": FakeRasterio(), "transform_bounds": fake_transform_bounds},
        paths=paths,
        meta=ResourceSatMeta(raw={"PATH": "99", "ROW": "65"}),
        analytic_intermediate=tmp_path / "analytic_intermediate.tif",
        mask_intermediate=tmp_path / "mask_intermediate.tif",
    )

    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "resourcesat-2a-liss3-boa"
    assert payload["collection"] == "ResourceSat-2A_LISS3_BOA"
    assert payload["analytic_band_order"] == ["BAND2", "BAND3", "BAND4", "BAND5"]
    assert payload["outputs"]["analytic"]["band_count"] == 4
    assert payload["outputs"]["mask"]["band_count"] == 1
    assert payload["properties"]["akasha:metrics_provisional"] is True
    assert payload["properties"]["akasha:mask_method"] == MASK_METHOD
    assert payload["classification_classes"][0]["value"] == 0
    assert payload["bbox"] == pytest.approx(expected_bbox)
