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
        "kind": "optical",
        "analysisLevel": "field",
        "availabilityStatus": "active",
        "isStale": False,
        "isSuccessfulCompositeStale": False,
        "latestSuccessfulCompositeDate": "2026-06-01",
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
        "sources": [source],
        "storage": storage,
        "ingestionLedger": {"status": "ok"},
    }


def test_monitoring_clean_gate_allows_healthy_active_source():
    smoke_test = load_smoke_test_module()

    errors = smoke_test._monitoring_cleanliness_errors(monitoring_payload())

    assert errors == []


def test_monitoring_clean_gate_ignores_gated_sources_without_composites():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload(
        source_overrides={
            "sourceId": "cartosat-3-gated",
            "kind": "context",
            "analysisLevel": "context",
            "availabilityStatus": "gated",
            "latestSuccessfulCompositeDate": None,
            "isStale": True,
            "isSuccessfulCompositeStale": True,
            "tileUnavailableReasons": ["Manual order workflow only"],
        }
    )

    errors = smoke_test._monitoring_cleanliness_errors(payload)

    assert errors == []


def test_monitoring_clean_gate_reports_storage_and_source_blockers():
    smoke_test = load_smoke_test_module()
    payload = monitoring_payload(
        source_overrides={
            "isStale": True,
            "isSuccessfulCompositeStale": True,
            "latestSuccessfulCompositeDate": None,
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
    assert "resourcesat-2a-liss3-boa has no successful composite" in errors
    assert "resourcesat-2a-liss3-boa tile unavailable: Missing mask asset" in errors
