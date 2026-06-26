from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.raster import catalog_resolver as catalog  # noqa: E402

CONTRACT_PATH = REPO_ROOT / "docs" / "reference" / "satellite-ingestion-scheduler-contracts.md"
CATALOG_PATH = REPO_ROOT / "docs" / "reference" / "satellite-catalog.md"
PLAN_PATH = REPO_ROOT / "docs" / "impl-plan" / "architecture-satellite-ingestion-scheduler-1.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase0_contract_covers_required_source_state_and_fail_closed_gates() -> None:
    contract = _read(CONTRACT_PATH)

    for field in (
        "catalogSlug",
        "catalogPlatform",
        "sourceId",
        "providerAdapter",
        "productFamily",
        "instrumentMode",
        "productVariant",
        "analysisLevel",
        "lifecycleState",
        "scheduleState",
        "capabilities",
        "productExposure",
        "commercialState",
        "aoiScope",
        "validationState",
        "readinessReasons",
        "validationProfile",
        "cadence",
        "hostPool",
        "ownedBy",
    ):
        assert f"`{field}`" in contract

    for invalid_gate in (
        "commercialState=commercial_blocked",
        "scheduleState=archive_only",
        "scheduleState=background_only",
        "aoiScope=out_of_aoi",
        "validationState=validation_failed",
        "Executable row without `catalogSlug`",
    ):
        assert invalid_gate in contract


def test_phase0_contract_defines_job_monitoring_ledger_and_runtime_boundaries() -> None:
    contract = _read(CONTRACT_PATH)

    for required in (
        "/srv/akasha/ingestion/scheduler/job_ledger.db",
        "/srv/akasha/ingestion/scheduler/jobs/schedule_state.json",
        "GET /api/monitoring/ingestion-schedules",
        "GET /api/monitoring/ingestion-jobs",
        "GET /api/monitoring/ingestion-jobs/{jobId}",
        "WAL mode",
        "busy timeout of at least 5000 ms",
        "`nextDueAt`",
        "must not expose raw server paths",
        "/opt/akasha/bin/akasha-ingestion-job.sh",
    ):
        assert required in contract


def test_phase0_contract_defines_catalog_mapping_and_current_ownership_matrix() -> None:
    contract = _read(CONTRACT_PATH)

    for source_id in (
        "resourcesat-2a-liss3-boa",
        "resourcesat-2a-liss4-mx70-l2",
        "resourcesat-2a-awifs-boa",
    ):
        assert source_id in contract

    assert "`resourcesat-2a`" in contract
    assert "`background_only`" in contract
    assert "`manual_only`" in contract
    assert "`scheduler_active`" in contract
    assert "old source-specific Bhoonidhi timers were removed" in contract
    assert "scripts/staging_ingestion_job.py trigger" in contract
    assert "systemctl enable --now akasha-bhoonidhi-sync.timer" not in contract


def test_phase0_contract_catalog_slugs_match_satellite_catalog() -> None:
    contract = _read(CONTRACT_PATH)
    catalog_text = _read(CATALOG_PATH)
    catalog_slugs = set(re.findall(r"\|\s*[^|\n]+\s*\|\s*`([^`]+)`\s*\|", catalog_text))
    required_slugs = {
        "sentinel-2",
        "sentinel-1",
        "landsat-8",
        "landsat-9",
        "modis",
        "eos-04-risat",
        "eos-06-oceansat-3",
        "nisar",
        "landsat-7",
        "landsat-5",
        "irs-1c",
        "planetscope",
        "skysat",
        "superview-neo-1",
        "blacksky-gen-3",
        "kompsat-3a",
        "alos-2-palsar-2",
        "cartosat-3",
        "naip",
    }

    assert required_slugs <= catalog_slugs
    for slug in required_slugs:
        assert f"`{slug}`" in contract
    assert "modis-terra-aqua" not in contract
    assert "naip-usda-aerial" not in contract


def test_resourcesat_liss3_release_gate_matches_bff_source_payload() -> None:
    contract = _read(CONTRACT_PATH)
    registry_source = catalog.get_source(catalog.RESOURCESAT_LISS3_SOURCE_ID)
    source = catalog.source_payload(catalog.RESOURCESAT_LISS3_SOURCE_ID)

    assert "Four bands in order `[BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]`" in contract
    assert "role order `NIR,RED,GREEN`, resolving to `bidx=3,2,1`" in contract
    assert "Akasha threshold mask v1" in contract
    assert "`corrected = dn * 0.0001 + 0.0`" in contract
    assert "Analytic COG and mask COG remain separate assets" in contract

    assert source["expectedAssets"] == ["analytic", "mask"]
    assert source["bandRoleMapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert source["defaultDisplayMode"] == "FCC"
    assert source["tileRouteMode"] == "fcc"
    assert source["maskAsset"] == "mask"
    assert source["metricsProvisional"] is True
    assert "Akasha threshold mask v1" in source["maskMethod"]
    assert registry_source["excludedMaskClasses"] == [0, 2, 3]
    assert source["supportedIndices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert "NDRE" not in source["supportedIndices"]
    assert "RECI" not in source["supportedIndices"]


def test_phase0_tasks_are_marked_complete_in_architecture_plan() -> None:
    plan = _read(PLAN_PATH)

    for suffix in "ABCDEFGHIJ":
        pattern = rf"\| TASK-000{suffix} \| .* \| Yes \| 2026-06-24 \|"
        assert re.search(pattern, plan), f"TASK-000{suffix} is not marked complete"
