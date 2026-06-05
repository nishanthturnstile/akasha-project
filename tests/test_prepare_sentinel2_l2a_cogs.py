import json
from pathlib import Path

import pytest
from scripts.prepare_sentinel2_l2a_cogs import (
    PreparedPaths,
    load_selected_products,
    manifest_output_dir,
    write_manifest,
)


def test_selection_manifest_products_generate_tile_scoped_output_dirs(tmp_path: Path) -> None:
    product_a = "S2A_MSIL2A_20260115T050711_N0511_R019_T43PHP_20260115T083121"
    product_b = "S2B_MSIL2A_20260115T050711_N0511_R019_T43PHQ_20260115T083121"
    manifest_path = tmp_path / "download_manifest.json"
    raw_dir = tmp_path / "raw" / "sentinel-2-l2a"
    output_root = tmp_path / "seed" / "rasters"
    manifest_path.write_text(
        json.dumps(
            {
                "selection": {
                    "selected_product_ids": [product_a, product_b],
                    "selected_mgrs_tiles": ["43PHP", "43PHQ"],
                },
                "candidates": [
                    {
                        "item_id": product_a,
                        "datetime": "2026-01-15T05:07:11Z",
                        "mgrs_tile": "43PHP",
                        "processing_baseline": "05.11",
                    },
                    {
                        "item_id": product_b,
                        "datetime": "2026-01-15T05:07:11Z",
                        "mgrs_tile": "43PHQ",
                        "processing_baseline": "05.11",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    products = load_selected_products(manifest_path, raw_dir=raw_dir)

    assert [product.product_id for product in products] == [product_a, product_b]
    assert products[0].zip_path == raw_dir / product_a / f"{product_a}.SAFE.zip"
    assert products[1].zip_path == raw_dir / product_b / f"{product_b}.SAFE.zip"
    assert [manifest_output_dir(output_root, product) for product in products] == [
        output_root / "2026-01-15" / "43PHP",
        output_root / "2026-01-15" / "43PHQ",
    ]
    assert manifest_output_dir(output_root, products[0]) != manifest_output_dir(
        output_root,
        products[1],
    )


def test_selection_manifest_can_parse_legacy_single_selected_product(tmp_path: Path) -> None:
    product_id = "S2A_MSIL2A_20260115T050711_N0511_R019_T43PHP_20260115T083121"
    manifest_path = tmp_path / "download_manifest.json"
    manifest_path.write_text(
        json.dumps({"selected": {"safe_name": f"{product_id}.SAFE", "grid_code": "MGRS-43PHP"}}),
        encoding="utf-8",
    )

    products = load_selected_products(manifest_path, raw_dir=tmp_path / "raw")

    assert len(products) == 1
    assert products[0].product_id == product_id
    assert products[0].mgrs_tile == "43PHP"
    assert products[0].acquisition_datetime == "2026-01-15T05:07:11Z"
    assert products[0].acquisition_date == "2026-01-15"
    assert products[0].processing_baseline == "05.11"


def test_write_manifest_includes_top_level_wgs84_bbox_and_geometry(tmp_path: Path) -> None:
    expected_bbox = [
        77.75127791535229,
        11.647042899643449,
        78.77093931726162,
        12.650224959163648,
    ]

    class FakeCrs:
        def to_string(self) -> str:
            return "EPSG:32643"

    class FakeDataset:
        crs = FakeCrs()
        bounds = (799980, 1290240, 909780, 1400040)
        res = (10, 10)
        width = 10980
        height = 10980
        dtypes = ("uint16",)
        count = 9
        nodata = 0
        descriptions = ("B04", "B08")

        def __enter__(self) -> "FakeDataset":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    class FakeRasterio:
        def open(self, _path: Path) -> FakeDataset:
            return FakeDataset()

    def fake_transform_bounds(
        src_crs: FakeCrs,
        dst_crs: str,
        left: float,
        bottom: float,
        right: float,
        top: float,
        *,
        densify_pts: int,
    ) -> tuple[float, float, float, float]:
        assert src_crs.to_string() == "EPSG:32643"
        assert dst_crs == "EPSG:4326"
        assert [left, bottom, right, top] == [799980, 1290240, 909780, 1400040]
        assert densify_pts == 21
        return tuple(expected_bbox)

    paths = PreparedPaths(
        zip_path=tmp_path / "source.SAFE.zip",
        safe_dir=tmp_path / "source.SAFE",
        output_dir=tmp_path / "out",
        analytic_cog=tmp_path / "out" / "analytic.tif",
        scl_cog=tmp_path / "out" / "scl.tif",
        manifest=tmp_path / "out" / "prepare_manifest.json",
        product_id="S2B_MSIL2A_20260115T052000_N0500_R019_T43PHP_20260115T074457",
        mgrs_tile="43PHP",
        acquisition_datetime="2026-01-15T05:20:00Z",
        acquisition_date="2026-01-15",
        processing_baseline="05.00",
    )

    write_manifest(
        deps={"rasterio": FakeRasterio(), "transform_bounds": fake_transform_bounds},
        paths=paths,
        analytic_intermediate=tmp_path / "analytic_intermediate.tif",
        scl_intermediate=tmp_path / "scl_intermediate.tif",
    )

    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["bbox"] == pytest.approx(expected_bbox)
    assert payload["geometry"] == payload["outputs"]["analytic"]["wgs84_geometry"]
    assert payload["outputs"]["analytic"]["wgs84_bbox"] == pytest.approx(expected_bbox)
    assert payload["outputs"]["analytic"]["bounds"] == [799980, 1290240, 909780, 1400040]
