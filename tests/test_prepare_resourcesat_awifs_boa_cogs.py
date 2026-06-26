from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import scripts.prepare_resourcesat_liss3_boa_cogs as prep

pytest.importorskip("rasterio")
pytest.importorskip("rio_cogeo")


def _write_awifs_band_product(product_dir: Path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    product_dir.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "crs": "EPSG:32643",
        "transform": from_origin(799960, 1290304, 56, 56),
        "width": 16,
        "height": 16,
        "count": 1,
        "dtype": "uint16",
        "nodata": 0,
    }
    values = {
        "BAND2": [0, 1200, 900, 500, 4500],
        "BAND3": [0, 1100, 700, 500, 4200],
        "BAND4": [0, 3600, 500, 500, 4300],
        "BAND5": [0, 2600, 400, 500, 3800],
    }
    for band_name, row_values in values.items():
        data = np.full((16, 16), 1200, dtype="uint16")
        data[0, :5] = np.array(row_values, dtype="uint16")
        with rasterio.open(product_dir / f"{band_name}.tif", "w", **profile) as dst:
            dst.write(data, 1)

    (product_dir / "BAND_META.txt").write_text(
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
            ]
        ),
        encoding="utf-8",
    )


def test_awifs_prepare_builds_four_band_manifest_and_mask_classes(tmp_path: Path) -> None:
    import rasterio

    product_dir = tmp_path / "raw" / "AWIFS_PRODUCT"
    output_root = tmp_path / "rasters" / prep.AWIFS_SOURCE_ID
    _write_awifs_band_product(product_dir)

    result = prep.main(
        [
            "--source",
            prep.AWIFS_SOURCE_ID,
            "--zip-path",
            str(product_dir),
            "--output-root",
            str(output_root),
            "--work-dir",
            str(tmp_path / "work"),
            "--product-id",
            "AWIFS_PRODUCT",
            "--acquisition-datetime",
            "2026-03-19T00:00:00Z",
            "--path",
            "99",
            "--row",
            "65",
            "--overwrite",
            "--skip-validation",
        ]
    )

    manifests = sorted(output_root.glob("scene/2026-03-19/*/prepare_manifest.json"))
    assert result == 0
    assert len(manifests) == 1
    payload = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert payload["source_id"] == prep.AWIFS_SOURCE_ID
    assert payload["collection"] == prep.AWIFS_BHOONIDHI_COLLECTION
    assert payload["analytic_band_order"] == ["BAND2", "BAND3", "BAND4", "BAND5"]
    assert payload["band_role_mapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert payload["outputs"]["analytic"]["band_count"] == 4
    assert payload["outputs"]["analytic"]["resolution"] == [56.0, 56.0]
    assert payload["outputs"]["mask"]["band_count"] == 1
    assert {item["value"] for item in payload["classification_classes"]} == {0, 1, 2, 3, 4}
    assert "AWiFS" in payload["mask_method"]
    with rasterio.open(payload["outputs"]["mask"]["path"]) as dataset:
        assert set(np.unique(dataset.read(1, masked=False)).tolist()) == {0, 1, 2, 3, 4}
