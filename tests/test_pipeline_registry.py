from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import pipeline_registry  # noqa: E402


def test_resourcesat_mvp_sources_have_bhoonidhi_pipeline_metadata():
    expected = {
        "resourcesat-2a-awifs-boa": "ResourceSat-2A_AWIFS_BOA",
        "resourcesat-2a-liss3-boa": "ResourceSat-2A_LISS3_BOA",
        "resourcesat-2a-liss4-mx70-l2": "ResourceSat-2A_LISS4-MX70_L2",
    }

    for source_id, collection_id in expected.items():
        source = pipeline_registry.get_pipeline_source(source_id)

        assert source.provider == "bhoonidhi"
        assert source.collection_id == collection_id
        assert source.prepare_script == "prepare_resourcesat_liss3_boa_cogs.py"
        assert source.supports_composite is True
        assert source.mvp_enabled is True


def test_awifs_pipeline_source_declares_regional_production_profile():
    source = pipeline_registry.get_pipeline_source("resourcesat-2a-awifs-boa")

    assert source.provider == "bhoonidhi"
    assert source.collection_id == "ResourceSat-2A_AWIFS_BOA"
    assert source.prepare_script == "prepare_resourcesat_liss3_boa_cogs.py"
    assert source.supports_search is True
    assert source.supports_download is True
    assert source.supports_composite is True
    assert source.mvp_enabled is True
    assert source.default_min_coverage_percent == 95.0
    assert source.output_profile == "resourcesat-awifs-boa"


def test_sar_sources_keep_source_specific_prepare_scripts():
    assert (
        pipeline_registry.prepare_script_name("sentinel-1-grd") == "prepare_sentinel1_grd_cogs.py"
    )
    assert (
        pipeline_registry.prepare_script_name("eos-04-sar-mrs-l2b")
        == "prepare_eos04_sar_mrs_l2b_cogs.py"
    )
    assert (
        pipeline_registry.prepare_script_name("nisar-ssar-beta-gcov")
        == "prepare_nisar_ssar_beta_gcov_cogs.py"
    )


def test_eos04_pipeline_remains_manual_refresh_not_legacy_mvp_default():
    source = pipeline_registry.get_pipeline_source("eos-04-sar-mrs-l2b")

    assert source.provider == "bhoonidhi"
    assert source.collection_id == "EOS-04_SAR-MRS_L2B"
    assert source.supports_search is True
    assert source.supports_download is True
    assert source.supports_validate is True
    assert source.supports_composite is False
    # Product exposure is controlled by source_registry/BFF activation.  The legacy
    # mvp_enabled flag stays false so old composite-oriented helpers do not schedule SAR.
    assert source.mvp_enabled is False
    assert source.manual_validation_enabled is True
    assert pipeline_registry.is_source_allowed("eos-04-sar-mrs-l2b", None) is False
    assert pipeline_registry.is_source_allowed("eos-04-sar-mrs-l2b", {"eos-04-sar-mrs-l2b"}) is True


def test_supported_source_ids_returns_sorted_mvp_bhoonidhi_sources():
    assert pipeline_registry.supported_source_ids("bhoonidhi") == [
        "resourcesat-2a-awifs-boa",
        "resourcesat-2a-liss3-boa",
        "resourcesat-2a-liss4-mx70-l2",
    ]


def test_unknown_source_raises_clear_key_error():
    with pytest.raises(KeyError, match="unsupported ingestion source: totally-unknown"):
        pipeline_registry.get_pipeline_source("totally-unknown")
