from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_smoke_test_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke-test.py"
    spec = importlib.util.spec_from_file_location("akasha_smoke_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def monitoring_payload(
    *,
    source_overrides: dict | None = None,
    storage_overrides: dict | None = None,
):
    source = {
        "sourceId": "resourcesat-2a-liss3-boa",
        "status": "ok",
        "statusReasons": [],
        "kind": "optical",
        "analysisLevel": "field",
        "availabilityStatus": "active",
        "isStale": False,
        "isSuccessfulCompositeStale": False,
        "isSuccessfulSearchStale": False,
        "latestSuccessfulCompositeDate": "2026-06-01",
        "latestSuccessfulSearchAoiId": "bangalore-60km",
        "latestSuccessfulSearchDatetimeRange": "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z",
        "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
        "daysSinceLatestSuccessfulSearch": 0,
        "ingestionFailureCountsByKind": {},
        "lastIngestionFailure": None,
        "hasUnresolvedIngestionFailure": False,
        "tileUnavailableReasons": [],
        "warnings": [],
    }
    if source_overrides:
        source.update(source_overrides)
    storage = {
        "status": "ok",
        "zeroByteObjectCount": 0,
        "byPrefix": [],
    }
    if storage_overrides:
        storage.update(storage_overrides)
    return {
        "status": "ok",
        "statusReasons": [],
        "sources": [source],
        "storage": storage,
        "ingestionLedger": {"status": "ok"},
    }


def test_monitoring_clean_gate_allows_healthy_active_source():
    smoke_test = load_smoke_test_module()

    errors = smoke_test._monitoring_cleanliness_errors(monitoring_payload())

    assert errors == []


def test_monitoring_contract_requires_operator_status_fields():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload()
    del payload["status"]
    del payload["statusReasons"]
    del payload["sources"][0]["status"]
    del payload["sources"][0]["statusReasons"]
    del payload["sources"][0]["latestSuccessfulSearchUpdatedAt"]
    del payload["sources"][0]["hasUnresolvedIngestionFailure"]

    errors = smoke_test._monitoring_contract_errors(payload)

    assert "status must be ok/warning/error" in errors
    assert "statusReasons must be a list" in errors
    assert "sources[0].status must be ok/warning/error" in errors
    assert "sources[0].statusReasons missing/list" in errors
    assert "sources[0].latestSuccessfulSearchUpdatedAt missing" in errors
    assert "sources[0].hasUnresolvedIngestionFailure missing" in errors


def test_monitoring_clean_gate_ignores_gated_sources_without_composites():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload(
        source_overrides={
            "sourceId": "cartosat-3-gated",
            "kind": "context",
            "analysisLevel": "context",
            "availabilityStatus": "gated",
            "latestSuccessfulCompositeDate": None,
            "latestSuccessfulSearchUpdatedAt": None,
            "isStale": True,
            "isSuccessfulCompositeStale": True,
            "isSuccessfulSearchStale": True,
            "tileUnavailableReasons": ["Manual order workflow only"],
        }
    )

    errors = smoke_test._monitoring_cleanliness_errors(payload)

    assert errors == []


def test_monitoring_clean_gate_reports_active_source_operator_status():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload(
        source_overrides={
            "status": "error",
            "statusReasons": ["LOW_COVERAGE_PERCENT"],
            "coveragePercent": 72.5,
        }
    )

    errors = smoke_test._monitoring_cleanliness_errors(payload)

    assert (
        "resourcesat-2a-liss3-boa operator status is 'error': LOW_COVERAGE_PERCENT"
        in errors
    )


def test_monitoring_clean_gate_reports_storage_and_source_blockers():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload(
        source_overrides={
            "isStale": True,
            "isSuccessfulCompositeStale": True,
            "isSuccessfulSearchStale": True,
            "hasUnresolvedIngestionFailure": True,
            "latestSuccessfulCompositeDate": None,
            "latestSuccessfulSearchUpdatedAt": None,
            "tileUnavailableReasons": ["Missing mask asset"],
            "lastError": "RuntimeError: STAC unavailable",
        },
        storage_overrides={"status": "error", "zeroByteObjectCount": 2},
    )

    errors = smoke_test._monitoring_cleanliness_errors(payload)

    assert "storage status is 'error'" in errors
    assert "2 zero-byte storage object(s)" in errors
    assert "resourcesat-2a-liss3-boa monitoring error" in errors
    assert "resourcesat-2a-liss3-boa latest catalog date is stale" in errors
    assert "resourcesat-2a-liss3-boa latest successful composite is stale" in errors
    assert "resourcesat-2a-liss3-boa latest successful search is stale" in errors
    assert "resourcesat-2a-liss3-boa has unresolved ingestion failure" in errors
    assert "resourcesat-2a-liss3-boa has no successful composite" in errors
    assert "resourcesat-2a-liss3-boa has no successful search" in errors
    assert "resourcesat-2a-liss3-boa tile unavailable: Missing mask asset" in errors
