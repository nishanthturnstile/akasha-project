from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

prep = importlib.import_module("scripts.prepare_sentinel1_grd_cogs")


def test_manifest_safe_name_fallback_matches_downloader_layout(tmp_path: Path) -> None:
    entry = {
        "item_id": "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE",
        "safe_name": "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE",
    }
    product_id = prep.product_id_from_manifest_entry(entry)

    assert prep.source_path_from_manifest_entry(entry, product_id, tmp_path) == (
        tmp_path
        / "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE"
        / "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE.zip"
    )


def test_manifest_ignores_nonexistent_host_absolute_source_zip(tmp_path: Path) -> None:
    entry = {
        "item_id": "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234",
        "source_zip": (
            "C:/Users/example/repo/data/raw/sentinel-1-grd/"
            "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234/"
            "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE.zip"
        ),
    }
    product_id = prep.product_id_from_manifest_entry(entry)

    assert prep.source_path_from_manifest_entry(entry, product_id, tmp_path) == (
        tmp_path
        / "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234"
        / "S1A_IW_GRDH_1SDV_20260427T002015_20260427T002040_001234_ABCDEF_1234.SAFE.zip"
    )


def test_manifest_orbit_state_is_preserved_from_downloader_field(tmp_path: Path) -> None:
    product = prep.selected_product_from_manifest_entry(
        {
            "item_id": (
                "S1A_IW_GRDH_1SDV_20260427T002015_"
                "20260427T002040_001234_ABCDEF_1234.SAFE"
            ),
            "datetime": "2026-04-27T00:20:15Z",
            "platform": "sentinel-1a",
            "relative_orbit": 42,
            "orbit_state": "ascending",
            "polarizations": ["VV", "VH"],
        },
        raw_dir=tmp_path,
    )

    assert product.orbit_direction == "ascending"


def test_snap_map_projection_prefers_wkt_when_pyproj_available() -> None:
    projection = prep.snap_map_projection("EPSG:32643")

    assert "EPSG:32643" not in projection or projection == "EPSG:32643"
    if projection != "EPSG:32643":
        assert "PROJCS" in projection
        assert "WGS 84 / UTM zone 43N" in projection
