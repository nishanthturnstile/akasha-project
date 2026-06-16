from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app import source_monitoring
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_imagery_source_monitoring_reports_latest_usable_metrics(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 4, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
                "refreshPolicy": "Daily Bhoonidhi search.",
                "metricsProvisional": True,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-03-19",
                "isLatestUsable": True,
                "tileAvailable": True,
                "coveragePercent": 100.0,
                "usablePixelPercent": 78.96,
                "cloudMaskedPercent": 20.96,
                "metricsProvisional": True,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-03-19T00:30:00Z",
                    "latestSuccessfulCompositeDate": "2026-03-19",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-03-19"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-03-20T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {
            "status": "ok",
            "bucket": "akasha-cogs",
            "objectCount": 2,
            "bytes": 1234,
            "zeroByteObjectCount": 0,
            "byPrefix": [],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["statusReasons"] == []
    assert body["staleAfterDays"] == 45
    assert body["coverageThresholdPercent"] == 95
    assert body["usablePixelThresholdPercent"] == 70
    assert body["generatedAt"] == "2026-04-01T00:00:00Z"
    source = body["sources"][0]
    assert source["sourceId"] == "resourcesat-2a-liss3-boa"
    assert source["status"] == "ok"
    assert source["statusReasons"] == []
    assert source["latestAvailableDate"] == "2026-03-19"
    assert source["latestUsableDate"] == "2026-03-19"
    assert source["daysSinceLatestAvailable"] == 13
    assert source["isStale"] is False
    assert source["dateCount"] == 1
    assert source["tileAvailableDateCount"] == 1
    assert source["coveragePercent"] == 100.0
    assert source["metricsProvisional"] is True
    assert source["latestSuccessfulCompositeDate"] == "2026-03-19"
    assert (
        source["latestSuccessfulCompositeProductId"]
        == "composite:bangalore-60km:2026-03-19"
    )
    assert source["latestSuccessfulCompositeAoiId"] == "bangalore-60km"
    assert source["latestSuccessfulCompositeUpdatedAt"] == "2026-03-20T01:00:00Z"
    assert source["latestSuccessfulSearchAoiId"] == "bangalore-60km"
    assert (
        source["latestSuccessfulSearchDatetimeRange"]
        == "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z"
    )
    assert source["latestSuccessfulSearchUpdatedAt"] == "2026-03-19T00:30:00Z"
    assert source["daysSinceLatestSuccessfulSearch"] == 13
    assert source["isSuccessfulSearchStale"] is False
    assert source["daysSinceLatestSuccessfulComposite"] == 13
    assert source["isSuccessfulCompositeStale"] is False
    assert source["warnings"] == []


def test_imagery_source_monitoring_flags_stale_successful_composite(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 30, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulCompositeDate": "2026-03-19",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-03-19"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-03-20T01:00:00Z",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == ["LATEST_SUCCESSFUL_COMPOSITE_STALE"]
    assert source["latestAvailableDate"] == "2026-06-10"
    assert source["daysSinceLatestAvailable"] == 5
    assert source["isStale"] is False
    assert source["latestSuccessfulCompositeDate"] == "2026-03-19"
    assert source["daysSinceLatestSuccessfulComposite"] == 88
    assert source["isSuccessfulCompositeStale"] is True
    assert source["warnings"] == ["LATEST_SUCCESSFUL_COMPOSITE_STALE"]


def test_imagery_source_monitoring_flags_stale_active_source(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 30, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [{"acquisitionDate": "2026-03-19", "tileAvailable": True}],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {"status": "ok", "bySource": []},
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {
            "status": "ok",
            "bucket": "akasha-cogs",
            "objectCount": 2,
            "bytes": 1234,
            "zeroByteObjectCount": 0,
            "byPrefix": [],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["statusReasons"] == ["SOURCE_ERROR:resourcesat-2a-liss3-boa"]
    source = body["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == [
        "LATEST_DATE_STALE",
        "NO_SUCCESSFUL_SEARCH",
        "NO_SUCCESSFUL_COMPOSITE",
    ]
    assert source["daysSinceLatestAvailable"] == 88
    assert source["isStale"] is True
    assert source["warnings"] == ["NO_SUCCESSFUL_SEARCH", "LATEST_DATE_STALE"]


def test_imagery_source_monitoring_separates_gated_from_stale(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "cartosat-3-gated",
                "label": "Cartosat-3",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "availabilityStatus": "gated",
                "gatedReason": "Manual/order workflow pending.",
            }
        ],
    )
    monkeypatch.setattr(source_monitoring.catalog, "list_dates", lambda source_id: [])

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "warning"
    assert source["statusReasons"] == ["SOURCE_GATED"]
    assert source["availabilityStatus"] == "gated"
    assert source["latestAvailableDate"] is None
    assert source["isStale"] is False
    assert source["gatedReason"] == "Manual/order workflow pending."
    assert source["warnings"] == ["SOURCE_GATED"]


def test_imagery_source_monitoring_flags_stale_successful_search(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 30, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-04-01T00:00:00Z/2026-04-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-04-15T01:00:00Z",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-06-10"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == ["LATEST_SUCCESSFUL_SEARCH_STALE"]
    assert source["latestSuccessfulSearchAoiId"] == "bangalore-60km"
    assert (
        source["latestSuccessfulSearchDatetimeRange"]
        == "2026-04-01T00:00:00Z/2026-04-15T23:59:59Z"
    )
    assert source["daysSinceLatestSuccessfulSearch"] == 61
    assert source["isSuccessfulSearchStale"] is True


def test_imagery_source_monitoring_reports_date_lookup_failure(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )

    def fail_dates(source_id):
        raise RuntimeError("STAC registration lookup failed")

    monkeypatch.setattr(source_monitoring.catalog, "list_dates", fail_dates)

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == [
        "MONITORING_LOOKUP_FAILED",
        "DATE_LOOKUP_FAILED",
        "NO_SUCCESSFUL_SEARCH",
        "NO_SUCCESSFUL_COMPOSITE",
    ]
    assert source["latestAvailableDate"] is None
    assert source["isStale"] is True
    assert source["dateCount"] == 0
    assert source["warnings"] == ["NO_SUCCESSFUL_SEARCH", "DATE_LOOKUP_FAILED"]
    assert source["lastError"] == "RuntimeError: STAC registration lookup failed"


def test_imagery_source_monitoring_reports_tile_unavailable_reasons(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "tileAvailable": False,
                "unavailableReason": "Required raster assets are missing for this date: mask.",
            },
            {
                "acquisitionDate": "2026-06-01",
                "tileAvailable": False,
                "unavailableReason": "Required raster assets are missing for this date: mask.",
            },
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == [
        "NO_TILE_AVAILABLE_DATES",
        "NO_SUCCESSFUL_COMPOSITE",
    ]
    assert source["tileAvailableDateCount"] == 0
    assert source["warnings"] == ["NO_TILE_AVAILABLE_DATES"]
    assert source["tileUnavailableReasons"] == [
        "Required raster assets are missing for this date: mask."
    ]


def test_imagery_source_monitoring_flags_low_field_composite_coverage(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(settings, "source_coverage_threshold_percent", 95, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
                "coveragePercent": 72.5,
                "usablePixelPercent": 71.0,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-06-10"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {
            "status": "ok",
            "bucket": "akasha-cogs",
            "objectCount": 2,
            "bytes": 1234,
            "zeroByteObjectCount": 0,
            "byPrefix": [],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["statusReasons"] == ["SOURCE_ERROR:resourcesat-2a-liss3-boa"]
    source = body["sources"][0]
    assert source["coveragePercent"] == 72.5
    assert source["status"] == "error"
    assert source["statusReasons"] == ["LOW_COVERAGE_PERCENT"]
    assert source["warnings"] == ["LOW_COVERAGE_PERCENT"]


def test_imagery_source_monitoring_flags_low_usable_pixels(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(settings, "source_coverage_threshold_percent", 95, raising=False)
    monkeypatch.setattr(settings, "usable_pixel_threshold_percent", 70, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
                "coveragePercent": 98.5,
                "usablePixelPercent": 42.0,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-06-10"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {
            "status": "ok",
            "bucket": "akasha-cogs",
            "objectCount": 2,
            "bytes": 1234,
            "zeroByteObjectCount": 0,
            "byPrefix": [],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["statusReasons"] == ["SOURCE_ERROR:resourcesat-2a-liss3-boa"]
    assert body["usablePixelThresholdPercent"] == 70
    source = body["sources"][0]
    assert source["usablePixelPercent"] == 42.0
    assert source["status"] == "error"
    assert source["statusReasons"] == ["LOW_USABLE_PIXEL_PERCENT"]
    assert source["warnings"] == ["LOW_USABLE_PIXEL_PERCENT"]


def test_imagery_source_monitoring_flags_unresolved_ingestion_failure(monkeypatch):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 16, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
                "coveragePercent": 100.0,
                "usablePixelPercent": 80.0,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "failureCountsByKind": {"bhoonidhi_download": 1},
                    "lastFailure": {
                        "productId": "RS_FAIL",
                        "sourceId": "resourcesat-2a-liss3-boa",
                        "status": "failed",
                        "updatedAt": "2026-06-15T12:00:00Z",
                        "failureKind": "bhoonidhi_download",
                        "error": "download failed: 504",
                    },
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-06-10"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "error"
    assert source["statusReasons"] == ["UNRESOLVED_INGESTION_FAILURE"]
    assert source["ingestionFailureCountsByKind"] == {"bhoonidhi_download": 1}
    assert source["lastIngestionFailure"]["failureKind"] == "bhoonidhi_download"
    assert source["hasUnresolvedIngestionFailure"] is True


def test_imagery_source_monitoring_keeps_resolved_ingestion_failure_visible_but_ok(
    monkeypatch,
):
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 16, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
                "coveragePercent": 100.0,
                "usablePixelPercent": 80.0,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "failureCountsByKind": {"bhoonidhi_search": 1},
                    "lastFailure": {
                        "productId": "sync:bangalore-60km:2026-06-01/2026-06-15",
                        "sourceId": "resourcesat-2a-liss3-boa",
                        "status": "failed",
                        "updatedAt": "2026-06-10T12:00:00Z",
                        "failureKind": "bhoonidhi_search",
                        "error": "Bhoonidhi search failed: 429",
                    },
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": (
                        "composite:bangalore-60km:2026-06-10"
                    ),
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["status"] == "ok"
    assert source["statusReasons"] == []
    assert source["ingestionFailureCountsByKind"] == {"bhoonidhi_search": 1}
    assert source["lastIngestionFailure"]["failureKind"] == "bhoonidhi_search"
    assert source["hasUnresolvedIngestionFailure"] is False


def test_imagery_source_monitoring_openapi_documents_operator_contract():
    schema = client.get("/api/openapi.json").json()
    response_schema = schema["paths"]["/api/monitoring/imagery-sources"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/ImagerySourceMonitoringResponse")

    schemas = schema["components"]["schemas"]
    response_props = schemas["ImagerySourceMonitoringResponse"]["properties"]
    assert "status" in response_props
    assert "statusReasons" in response_props
    assert "coverageThresholdPercent" in response_props
    assert "usablePixelThresholdPercent" in response_props
    source_props = schemas["ImagerySourceMonitoringSource"]["properties"]
    assert "status" in source_props
    assert "statusReasons" in source_props
    assert "latestSuccessfulCompositeDate" in source_props
    assert "latestSuccessfulCompositeProductId" in source_props
    assert "latestSuccessfulComposites" in source_props
    assert "daysSinceLatestSuccessfulComposite" in source_props
    assert "isSuccessfulCompositeStale" in source_props
    assert "latestSuccessfulSearchAoiId" in source_props
    assert "latestSuccessfulSearchDatetimeRange" in source_props
    assert "latestSuccessfulSearchUpdatedAt" in source_props
    assert "daysSinceLatestSuccessfulSearch" in source_props
    assert "isSuccessfulSearchStale" in source_props
    assert "ingestionFailureCountsByKind" in source_props
    assert "lastIngestionFailure" in source_props
    assert "hasUnresolvedIngestionFailure" in source_props
    assert "warnings" in source_props
    assert "tileUnavailableReasons" in source_props

    ledger_source_props = schemas["MonitoringLedgerSource"]["properties"]
    assert "failureCountsByKind" in ledger_source_props
    assert "lastFailure" in ledger_source_props
    assert "latestSuccessfulCompositeDate" in ledger_source_props
    assert "latestSuccessfulComposites" in ledger_source_props
    assert "latestSuccessfulSearchAoiId" in ledger_source_props
    assert "latestSuccessfulSearchDatetimeRange" in ledger_source_props
    assert "latestSuccessfulSearchUpdatedAt" in ledger_source_props

    storage_props = schemas["StorageUsage"]["properties"]
    prefix_props = schemas["StoragePrefixUsage"]["properties"]
    assert "zeroByteObjectCount" in storage_props
    assert "zeroByteObjectCount" in prefix_props


def test_ingestion_ledger_summary_reports_failures_by_kind(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.sqlite"
    conn = sqlite3.connect(ledger)
    conn.execute("""
        create table ingestion_ledger (
            product_id text not null,
            source_id text not null,
            scene_key text,
            status text not null,
            retries integer not null default 0,
            bytes integer not null default 0,
            error text,
            created_at text not null,
            updated_at text not null,
            primary key (product_id, source_id)
        )
        """)
    conn.executemany(
        """
        insert into ingestion_ledger (
            product_id, source_id, scene_key, status, retries, bytes, error, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "p1",
                "resourcesat-2a-liss3-boa",
                "scene-1",
                "failed",
                2,
                0,
                "Bhoonidhi auth token rejected password=secret",
                "2026-06-15T10:00:00Z",
                "2026-06-15T10:05:00Z",
            ),
            (
                "p2",
                "resourcesat-2a-liss3-boa",
                "scene-2",
                "ingested",
                0,
                1234,
                None,
                "2026-06-15T11:00:00Z",
                "2026-06-15T11:05:00Z",
            ),
            (
                "sync:bangalore-60km:2026-06-01T00:00:00Z/2026-06-15T23:59:59Z",
                "resourcesat-2a-liss3-boa",
                None,
                "searched",
                0,
                0,
                None,
                "2026-06-15T11:30:00Z",
                "2026-06-15T11:30:00Z",
            ),
            (
                "sync:mysore-60km:2026-06-03T00:00:00Z/2026-06-17T23:59:59Z",
                "resourcesat-2a-liss3-boa",
                None,
                "searched",
                0,
                0,
                None,
                "2026-06-17T11:30:00Z",
                "2026-06-17T11:30:00Z",
            ),
            (
                "composite:bangalore-60km:2026-03-19",
                "resourcesat-2a-liss3-boa",
                None,
                "composited",
                0,
                0,
                None,
                "2026-06-15T12:00:00Z",
                "2026-06-15T12:05:00Z",
            ),
            (
                "composite:bangalore-60km:2026-04-02",
                "resourcesat-2a-liss3-boa",
                None,
                "composited",
                0,
                0,
                None,
                "2026-06-16T12:00:00Z",
                "2026-06-16T12:05:00Z",
            ),
            (
                "composite:mysore-60km:2026-04-10",
                "resourcesat-2a-liss3-boa",
                None,
                "composited",
                0,
                0,
                None,
                "2026-06-17T12:00:00Z",
                "2026-06-17T12:05:00Z",
            ),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "bhoonidhi_ledger_path", str(ledger), raising=False)

    summary = source_monitoring._ingestion_ledger_summary()

    assert summary["status"] == "ok"
    assert summary["rowCount"] == 7
    assert summary["statusCounts"] == {
        "composited": 3,
        "failed": 1,
        "ingested": 1,
        "searched": 2,
    }
    assert summary["bytes"] == 1234
    assert summary["failureCountsByKind"] == {"bhoonidhi_auth": 1}
    by_source = summary["bySource"][0]
    assert by_source["statusCounts"] == summary["statusCounts"]
    assert by_source["failureCountsByKind"] == {"bhoonidhi_auth": 1}
    assert by_source["lastFailure"]["productId"] == "p1"
    assert by_source["lastFailure"]["failureKind"] == "bhoonidhi_auth"
    assert "secret" not in by_source["lastFailure"]["error"]
    assert by_source["latestSuccessfulCompositeDate"] == "2026-04-10"
    assert (
        by_source["latestSuccessfulCompositeProductId"]
        == "composite:mysore-60km:2026-04-10"
    )
    assert by_source["latestSuccessfulCompositeAoiId"] == "mysore-60km"
    assert by_source["latestSuccessfulCompositeUpdatedAt"] == "2026-06-17T12:05:00Z"
    assert by_source["latestSuccessfulSearchAoiId"] == "mysore-60km"
    assert (
        by_source["latestSuccessfulSearchDatetimeRange"]
        == "2026-06-03T00:00:00Z/2026-06-17T23:59:59Z"
    )
    assert by_source["latestSuccessfulSearchUpdatedAt"] == "2026-06-17T11:30:00Z"
    assert by_source["latestSuccessfulComposites"] == [
        {
            "aoiId": "bangalore-60km",
            "date": "2026-04-02",
            "productId": "composite:bangalore-60km:2026-04-02",
            "updatedAt": "2026-06-16T12:05:00Z",
        },
        {
            "aoiId": "mysore-60km",
            "date": "2026-04-10",
            "productId": "composite:mysore-60km:2026-04-10",
            "updatedAt": "2026-06-17T12:05:00Z",
        },
    ]
    failure = summary["lastFailures"][0]
    assert failure["productId"] == "p1"
    assert failure["failureKind"] == "bhoonidhi_auth"
    assert "secret" not in failure["error"]


def test_ingestion_ledger_summary_classifies_operator_pipeline_failures(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.sqlite"
    conn = sqlite3.connect(ledger)
    conn.execute("""
        create table ingestion_ledger (
            product_id text not null,
            source_id text not null,
            scene_key text,
            status text not null,
            retries integer not null default 0,
            bytes integer not null default 0,
            error text,
            created_at text not null,
            updated_at text not null,
            primary key (product_id, source_id)
        )
        """)
    conn.executemany(
        """
        insert into ingestion_ledger (
            product_id, source_id, scene_key, status, retries, bytes, error, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "p-storage",
                "resourcesat-2a-liss3-boa",
                None,
                "failed",
                1,
                0,
                "storage upload failed: MinIO PutObject failed for s3://akasha-cogs/a.tif",
                "2026-06-15T10:00:00Z",
                "2026-06-15T10:05:00Z",
            ),
            (
                "p-composite",
                "resourcesat-2a-liss3-boa",
                None,
                "failed",
                1,
                0,
                "composite failed: coverage below threshold",
                "2026-06-15T11:00:00Z",
                "2026-06-15T11:05:00Z",
            ),
            (
                "p-stac",
                "resourcesat-2a-liss3-boa",
                None,
                "failed",
                1,
                0,
                "STAC registration failed: pgstac upsert rejected item",
                "2026-06-15T12:00:00Z",
                "2026-06-15T12:05:00Z",
            ),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "bhoonidhi_ledger_path", str(ledger), raising=False)

    summary = source_monitoring._ingestion_ledger_summary()

    assert summary["failureCountsByKind"] == {
        "composite": 1,
        "stac_registration": 1,
        "storage_upload": 1,
    }
    by_source = summary["bySource"][0]
    assert by_source["failureCountsByKind"] == summary["failureCountsByKind"]
    assert by_source["lastFailure"]["productId"] == "p-stac"
    assert summary["lastFailures"][0]["failureKind"] == "stac_registration"
    assert summary["lastFailures"][1]["failureKind"] == "composite"
    assert summary["lastFailures"][2]["failureKind"] == "storage_upload"


def test_failure_kind_classifies_bhoonidhi_and_conversion_failures():
    cases = [
        ("failed", "Bhoonidhi auth token rejected", "bhoonidhi_auth"),
        ("failed", "POST /data/search returned HTTP 429", "bhoonidhi_search"),
        ("failed", "download failed with 412 concurrency exceeded", "bhoonidhi_download"),
        ("failed", "prepare COG failed: GDAL could not read BAND4.tif", "conversion"),
        ("failed", "unknown worker failure", "ingestion"),
    ]

    for status, error, expected in cases:
        assert source_monitoring._failure_kind(status, error) == expected


def test_search_record_parser_is_fail_soft_for_non_sync_rows():
    assert source_monitoring._search_record("sync:bangalore-60km:2026-06-01/2026-06-15") == {
        "aoiId": "bangalore-60km",
        "datetimeRange": "2026-06-01/2026-06-15",
    }
    assert source_monitoring._search_record("composite:bangalore-60km:2026-06-15") is None
    assert source_monitoring._search_record("sync:bangalore-60km") is None
    assert source_monitoring._search_record("sync:bangalore-60km:not-a-range") is None


def test_storage_usage_summarizes_minio_bucket(monkeypatch):
    class FakePaginator:
        def paginate(self, Bucket):  # noqa: N803
            assert Bucket == "akasha-cogs"
            return [
                {
                    "Contents": [
                        {"Key": "resourcesat-2a-liss3-boa/2026/analytic.tif", "Size": 10},
                        {"Key": "resourcesat-2a-liss3-boa/2026/mask.tif", "Size": 0},
                        {"Key": "sentinel-2-l2a/sample/analytic.tif", "Size": 7},
                    ]
                }
            ]

    class FakeS3:
        def head_bucket(self, Bucket):  # noqa: N803
            assert Bucket == "akasha-cogs"

        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

    monkeypatch.setattr(settings, "s3_endpoint_url", "http://minio:9000", raising=False)
    monkeypatch.setattr(settings, "s3_access_key", "access", raising=False)
    monkeypatch.setattr(settings, "s3_secret_key", "secret", raising=False)
    monkeypatch.setattr(settings, "s3_region", "us-east-1", raising=False)
    monkeypatch.setattr(settings, "cog_bucket", "akasha-cogs", raising=False)
    monkeypatch.setattr(source_monitoring, "_s3_client", lambda: FakeS3())

    usage = source_monitoring._storage_usage()

    assert usage["status"] == "ok"
    assert usage["bucket"] == "akasha-cogs"
    assert usage["objectCount"] == 3
    assert usage["bytes"] == 17
    assert usage["zeroByteObjectCount"] == 1
    assert usage["byPrefix"] == [
        {
            "prefix": "resourcesat-2a-liss3-boa",
            "objectCount": 2,
            "bytes": 10,
            "zeroByteObjectCount": 1,
        },
        {
            "prefix": "sentinel-2-l2a",
            "objectCount": 1,
            "bytes": 7,
            "zeroByteObjectCount": 0,
        },
    ]
