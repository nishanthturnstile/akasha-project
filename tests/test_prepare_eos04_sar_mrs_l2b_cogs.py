from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

prep = importlib.import_module("scripts.prepare_eos04_sar_mrs_l2b_cogs")


def test_polarizations_are_normalized_and_display_ordered():
    assert prep.normalize_polarizations("hv,hh") == ["HV", "HH"]
    assert prep.sort_polarizations(["HV", "HH"]) == ["HH", "HV"]
    # Unknown tokens are dropped.
    assert prep.normalize_polarizations("hh, zz, vv") == ["HH", "VV"]


def test_acquisition_datetime_inferred_from_product_id():
    assert prep.acquisition_datetime_from_product_id(
        "EOS04_SAR_MRS_20260615T053000_XYZ"
    ) == "2026-06-15T05:30:00Z"
    # Date-only fallback.
    assert prep.acquisition_datetime_from_product_id("EOS04_20260615_abc") == (
        "2026-06-15T00:00:00Z"
    )


def test_polarization_token_detection_requires_delimited_match():
    assert prep._polarization_from_filename("scene_band_HH.tif") == "HH"
    assert prep._polarization_from_filename("BAND_RV_sigma0.tiff") == "RV"
    # A bare TIFF with no polarization token yields None (caller falls back).
    assert prep._polarization_from_filename("backscatter.tif") is None


def test_selected_product_from_manifest_entry_reads_bhoonidhi_fields(tmp_path):
    product = prep.selected_product_from_manifest_entry(
        {
            "item_id": "EOS04_SAR_MRS_20260615T053000_XYZ",
            "datetime": "2026-06-15T05:30:00Z",
            "polarizations": ["HH", "HV"],
            "relative_orbit": 123,
            "orbit_state": "ascending",
        },
        raw_dir=tmp_path,
        default_polarizations=["HH"],
    )
    assert product.product_id == "EOS04_SAR_MRS_20260615T053000_XYZ"
    assert product.acquisition_date == "2026-06-15"
    assert product.polarizations == ["HH", "HV"]
    assert product.relative_orbit == "123"
    assert product.orbit_state == "ascending"
    assert product.product_type == prep.BHOONIDHI_COLLECTION


def test_selected_entries_resolve_from_download_manifest_candidates():
    payload = {
        "selection": {"selected_product_ids": ["A", "B"]},
        "candidates": [
            {"item_id": "A", "datetime": "2026-06-15T05:30:00Z"},
            {"item_id": "B", "datetime": "2026-06-16T05:30:00Z"},
        ],
    }
    entries = prep._selected_manifest_entries(payload)
    assert [entry["item_id"] for entry in entries] == ["A", "B"]


def test_to_db_conversions_match_expected_scales():
    np = pytest.importorskip("numpy")
    linear = np.array([1.0, 0.1, 0.01], dtype="float64")
    db = prep.to_db(np, linear, "linear")
    assert np.allclose(db, [0.0, -10.0, -20.0], atol=1e-4)
    # Amplitude uses 20*log10.
    amp = prep.to_db(np, np.array([10.0], dtype="float64"), "amplitude")
    assert np.allclose(amp, [20.0], atol=1e-4)
    # Passthrough leaves dB untouched.
    passed = prep.to_db(np, np.array([-12.5], dtype="float64"), "db")
    assert np.allclose(passed, [-12.5], atol=1e-6)


def test_detect_input_scale_auto_heuristic():
    np = pytest.importorskip("numpy")
    assert prep.detect_input_scale(np, np.array([-20.0, -10.0, -5.0]), "auto") == "db"
    assert prep.detect_input_scale(np, np.array([0.01, 0.2, 0.05]), "auto") == "linear"
    assert prep.detect_input_scale(np, np.array([1500.0, 3000.0]), "auto") == "amplitude"
    # Explicit request always wins.
    assert prep.detect_input_scale(np, np.array([0.01]), "db") == "db"
