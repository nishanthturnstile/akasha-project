from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

prep = importlib.import_module("scripts.prepare_nisar_ssar_beta_gcov_cogs")


def test_covariance_diagonal_terms_map_to_polarizations():
    assert prep.COVARIANCE_DIAGONAL_TERMS == {
        "HHHH": "HH",
        "HVHV": "HV",
        "VHVH": "VH",
        "VVVV": "VV",
    }


def test_polarization_token_prefers_gcov_covariance_term():
    # GCOV subdataset leaf names carry doubled-pol covariance terms.
    assert prep._polarization_from_token("//science/LSAR/GCOV/grids/frequencyA/HHHH") == "HH"
    assert prep._polarization_from_token("frequencyA_VVVV") == "VV"
    # Plain GeoTIFF polarization token also resolves.
    assert prep._polarization_from_token("nisar_band_HV.tif") == "HV"
    assert prep._polarization_from_token("backscatter.tif") is None


def test_selected_product_defaults_to_nisar_platform_and_gcov_mode(tmp_path):
    product = prep.selected_product_from_manifest_entry(
        {
            "item_id": "NISAR_SSAR_GCOV_20260615T053000_001",
            "datetime": "2026-06-15T05:30:00Z",
        },
        raw_dir=tmp_path,
        default_polarizations=["HH"],
    )
    assert product.platform == "nisar"
    assert product.instrument_mode == "GCOV"
    assert product.product_type == prep.BHOONIDHI_COLLECTION
    assert product.acquisition_date == "2026-06-15"
    assert product.polarizations == ["HH"]


def test_to_db_defaults_to_linear_power_conversion():
    np = pytest.importorskip("numpy")
    linear = np.array([1.0, 0.1, 0.01], dtype="float64")
    assert np.allclose(prep.to_db(np, linear, "linear"), [0.0, -10.0, -20.0], atol=1e-4)


def test_detect_input_scale_auto_assumes_linear_gcov_power():
    np = pytest.importorskip("numpy")
    # GCOV diagonal terms are small positive linear power -> linear.
    assert prep.detect_input_scale(np, np.array([0.02, 0.1, 0.3]), "auto") == "linear"
    # Clearly-dB negatives -> db.
    assert prep.detect_input_scale(np, np.array([-18.0, -9.0]), "auto") == "db"
