import json
from pathlib import Path

import numpy as np
import pytest

import scripts.prepare_resourcesat_liss3_boa_cogs as prep
from scripts.prepare_resourcesat_liss3_boa_cogs import (
    AWIFS_BHOONIDHI_COLLECTION,
    AWIFS_SOURCE_ID,
    MASK_METHOD,
    PreparedPaths,
    ResourceSatMeta,
    SelectedProduct,
    acquisition_datetime_from_text,
    build_mask_array,
    load_selected_products,
    mask_method_for_source,
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
                "VALID_RANGE = 0-10000",
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
    assert meta.valid_ranges == {
        "BAND2": (0.0, 10000.0),
        "BAND3": (0.0, 10000.0),
        "BAND4": (0.0, 10000.0),
        "BAND5": (0.0, 10000.0),
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


def test_liss4_mask_generation_uses_swir_free_provisional_classes() -> None:
    analytic = np.array(
        [
            [[0, 1200, 3000, 4000, 500]],
            [[0, 1000, 1000, 3600, 600]],
            [[0, 4000, 1000, 3800, 700]],
        ],
        dtype="uint16",
    )

    mask = prep.build_mask_array_3band(np, analytic)

    assert mask.tolist() == [[0, 1, 4, 2, 3]]


def test_liss4_source_profile_declares_three_analytic_bands() -> None:
    profile = prep.source_profile("resourcesat-2a-liss4-mx70-l2")

    assert profile["collection"] == "ResourceSat-2A_LISS4-MX70_L2"
    assert profile["label"] == "LISS-4"
    assert profile["resolution_meters"] == 5.0
    assert profile["analytic_bands"] == (
        ("BAND2", "GREEN", "Green"),
        ("BAND3", "RED", "Red"),
        ("BAND4", "NIR", "Near infrared"),
    )


def test_resourcesat_mask_generation_uses_all_band_valid_range_gap_rule() -> None:
    # The ResourceSat gap authority stays all-band based: one invalid band is not enough.
    analytic = np.array(
        [
            [[1000, 12000, 12000]],
            [[1000, 1100, 12000]],
            [[3000, 3600, 12000]],
            [[2000, 2600, 12000]],
        ],
        dtype="uint16",
    )

    valid_ranges = {
        "BAND2": (0.0, 10000.0),
        "BAND3": (0.0, 10000.0),
        "BAND4": (0.0, 10000.0),
        "BAND5": (0.0, 10000.0),
    }

    mask = build_mask_array(
        np,
        analytic,
        valid_ranges=valid_ranges,
        cloud_brightness_threshold=10,
        cloud_swir_threshold=10,
    )

    assert mask.tolist() == [[1, 1, 0]]


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
                        "bbox": [77.0, 11.0, 78.0, 12.0],
                        "properties": {
                            "Path": "99",
                            "Row": "65",
                        },
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


def test_bhoonidhi_product_id_date_takes_precedence_over_embedded_numeric_tokens() -> None:
    assert (
        acquisition_datetime_from_text("RA319MAR2026048153009900065PSANSTUCSRHTDF")
        == "2026-03-19T00:00:00Z"
    )


def test_downloaded_zip_path_does_not_override_bhoonidhi_path_row(tmp_path: Path) -> None:
    manifest_path = tmp_path / "download_manifest.json"
    downloaded = (
        tmp_path
        / "raw"
        / "resourcesat-2a-liss3-boa"
        / "RA319MAR2026048153009900065PSANSTUCSRHTDF.zip"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "candidates": [
                    {
                        "item_id": "RA319MAR2026048153009900065PSANSTUCSRHTDF",
                        "bbox": [75.598123, 11.140278, 77.293455, 12.717257],
                        "properties": {
                            "datetime": "2026-03-19T00:00:00Z",
                            "Path": "99",
                            "Row": "65",
                        },
                    }
                ],
                "downloaded": [
                    {
                        "item_id": "RA319MAR2026048153009900065PSANSTUCSRHTDF",
                        "status": "downloaded",
                        "path": downloaded.as_posix(),
                        "bytes": 240751189,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    products = load_selected_products(manifest_path, raw_dir=tmp_path / "raw")

    assert len(products) == 1
    assert products[0].source_path == downloaded
    assert products[0].acquisition_datetime == "2026-03-19T00:00:00Z"
    assert products[0].acquisition_date == "2026-03-19"
    assert products[0].path == "99"
    assert products[0].row == "65"
    assert output_dir_for_product(tmp_path / "rasters", products[0]) == (
        tmp_path
        / "rasters"
        / "scene"
        / "2026-03-19"
        / scene_component(products[0])
    )


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
        meta=ResourceSatMeta(
            raw={"PATH": "99", "ROW": "65"},
            valid_ranges={"BAND2": (0.0, 10000.0)},
        ),
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
    assert payload["band_meta"]["valid_ranges"] == {"BAND2": [0.0, 10000.0]}
    assert payload["bbox"] == pytest.approx(expected_bbox)


def test_write_manifest_uses_awifs_specific_mask_method(tmp_path: Path) -> None:
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
        res = (56, 56)
        transform = (56, 0, 799980, 0, -56, 1400040, 0, 0, 1)
        width = 1961
        height = 1961
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
        product_id="AWIFS_PRODUCT",
        source_path=tmp_path / "AWIFS_PRODUCT.zip",
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
        source_id=AWIFS_SOURCE_ID,
        collection=AWIFS_BHOONIDHI_COLLECTION,
    )

    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == AWIFS_SOURCE_ID
    assert payload["collection"] == AWIFS_BHOONIDHI_COLLECTION
    assert payload["mask_method"] == mask_method_for_source(AWIFS_SOURCE_ID)
    assert payload["properties"]["akasha:mask_method"] == mask_method_for_source(AWIFS_SOURCE_ID)
    assert "AWiFS" in payload["mask_method"]
    assert "LISS-3 BOA sample" not in payload["mask_method"]


def test_write_manifest_emits_liss4_three_band_contract(tmp_path: Path) -> None:
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
        res = (5.0, 5.0)
        transform = (5.0, 0, 799980, 0, -5.0, 1400040, 0, 0, 1)
        width = 18931
        height = 18931
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
            return FakeDataset(3, ("BAND2", "BAND3", "BAND4"))

    def fake_transform_bounds(*_args: object, **_kwargs: object) -> list[float]:
        return expected_bbox

    product_dir = tmp_path / "product"
    product_dir.mkdir()
    (product_dir / "BAND_META.txt").write_text("PATH=99\nROW=65\n", encoding="utf-8")
    product = SelectedProduct(
        product_id="LISS4_PRODUCT",
        source_path=tmp_path / "LISS4_PRODUCT.zip",
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
        source_id="resourcesat-2a-liss4-mx70-l2",
        collection="ResourceSat-2A_LISS4-MX70_L2",
    )

    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "resourcesat-2a-liss4-mx70-l2"
    assert payload["collection"] == "ResourceSat-2A_LISS4-MX70_L2"
    assert payload["analytic_band_order"] == ["BAND2", "BAND3", "BAND4"]
    assert payload["band_role_mapping"] == {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4"}
    assert payload["outputs"]["analytic"]["band_count"] == 3


class _FakeCrs:
    def __init__(self, value: str = "EPSG:32643") -> None:
        self.value = value

    def to_string(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _FakeCrs) and self.value == other.value


class _FakeResourceSatDataset:
    def __init__(
        self,
        *,
        count: int,
        crs: _FakeCrs | None = None,
        transform: tuple[int, int, int, int, int, int] = (24, 0, 799980, 0, -24, 1290288),
        width: int = 2,
        height: int = 2,
        res: tuple[float, float] = (24.0, 24.0),
        overviews: list[int] | None = None,
        mask_values: np.ndarray | None = None,
    ) -> None:
        self.count = count
        self.crs = _FakeCrs() if crs is None else crs
        self.transform = transform
        self.width = width
        self.height = height
        self.res = res
        self._overviews = [2, 4] if overviews is None else overviews
        self._mask_values = (
            np.array([[0, 1], [2, 4]], dtype="uint8") if mask_values is None else mask_values
        )

    def __enter__(self) -> "_FakeResourceSatDataset":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def overviews(self, _band: int) -> list[int]:
        return self._overviews

    def read(self, _band: int, masked: bool = False) -> np.ndarray:
        return self._mask_values


class _FakeResourceSatRasterio:
    def __init__(self, analytic: _FakeResourceSatDataset, mask: _FakeResourceSatDataset) -> None:
        self.analytic = analytic
        self.mask = mask

    def open(self, path: Path) -> _FakeResourceSatDataset:
        return self.mask if Path(path).name == "mask.tif" else self.analytic


def _strict_validation_deps(
    analytic: _FakeResourceSatDataset,
    mask: _FakeResourceSatDataset,
) -> dict[str, object]:
    return {
        "np": np,
        "rasterio": _FakeResourceSatRasterio(analytic, mask),
        "cog_validate": lambda *_args, **_kwargs: (True, [], []),
    }


def test_validate_resourcesat_cogs_accepts_strict_liss3_outputs(tmp_path: Path) -> None:
    analytic = _FakeResourceSatDataset(count=4)
    mask = _FakeResourceSatDataset(count=1)

    prep.validate_resourcesat_cogs(
        _strict_validation_deps(analytic, mask),
        tmp_path / "analytic.tif",
        tmp_path / "mask.tif",
        source_id="resourcesat-2a-liss3-boa",
    )


def test_validate_resourcesat_cogs_accepts_strict_liss4_outputs(tmp_path: Path) -> None:
    analytic = _FakeResourceSatDataset(count=3, res=(5.0, 5.0))
    mask = _FakeResourceSatDataset(count=1, res=(5.0, 5.0))

    prep.validate_resourcesat_cogs(
        _strict_validation_deps(analytic, mask),
        tmp_path / "analytic.tif",
        tmp_path / "mask.tif",
        source_id="resourcesat-2a-liss4-mx70-l2",
    )


def test_validate_resourcesat_cogs_rejects_mask_transform_mismatch(tmp_path: Path) -> None:
    analytic = _FakeResourceSatDataset(count=4)
    mask = _FakeResourceSatDataset(count=1, transform=(24, 0, 799980, 0, -24, 1290312))

    with pytest.raises(SystemExit, match="analytic/mask transform mismatch"):
        prep.validate_resourcesat_cogs(
            _strict_validation_deps(analytic, mask),
            tmp_path / "analytic.tif",
            tmp_path / "mask.tif",
            source_id="resourcesat-2a-liss3-boa",
        )


def test_validate_resourcesat_cogs_rejects_invalid_mask_classes(tmp_path: Path) -> None:
    analytic = _FakeResourceSatDataset(count=4)
    mask = _FakeResourceSatDataset(
        count=1,
        mask_values=np.array([[1, 5], [0, 4]], dtype="uint8"),
    )

    with pytest.raises(SystemExit, match=r"invalid mask class value\(s\): \[5\]"):
        prep.validate_resourcesat_cogs(
            _strict_validation_deps(analytic, mask),
            tmp_path / "analytic.tif",
            tmp_path / "mask.tif",
            source_id="resourcesat-2a-liss3-boa",
        )
