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
                "usablePixelPercent": 38.96,
                "cloudMaskedPercent": 60.96,
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

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["staleAfterDays"] == 45
    assert body["generatedAt"] == "2026-04-01T00:00:00Z"
    source = body["sources"][0]
    assert source["sourceId"] == "resourcesat-2a-liss3-boa"
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
                }
            ],
        },
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
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
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [{"acquisitionDate": "2026-03-19", "tileAvailable": True}],
    )

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["daysSinceLatestAvailable"] == 88
    assert source["isStale"] is True
    assert source["warnings"] == ["LATEST_DATE_STALE"]


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
    assert source["availabilityStatus"] == "gated"
    assert source["latestAvailableDate"] is None
    assert source["isStale"] is False
    assert source["gatedReason"] == "Manual/order workflow pending."
    assert source["warnings"] == ["SOURCE_GATED"]


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
            }
        ],
    )

    def fail_dates(source_id):
        raise RuntimeError("STAC registration lookup failed")

    monkeypatch.setattr(source_monitoring.catalog, "list_dates", fail_dates)

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["latestAvailableDate"] is None
    assert source["isStale"] is True
    assert source["dateCount"] == 0
    assert source["warnings"] == ["DATE_LOOKUP_FAILED"]
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

    response = client.get("/api/monitoring/imagery-sources")

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["tileAvailableDateCount"] == 0
    assert source["warnings"] == ["NO_TILE_AVAILABLE_DATES"]
    assert source["tileUnavailableReasons"] == [
        "Required raster assets are missing for this date: mask."
    ]


def test_imagery_source_monitoring_openapi_documents_operator_contract():
    schema = client.get("/api/openapi.json").json()
    response_schema = schema["paths"]["/api/monitoring/imagery-sources"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/ImagerySourceMonitoringResponse")

    schemas = schema["components"]["schemas"]
    source_props = schemas["ImagerySourceMonitoringSource"]["properties"]
    assert "latestSuccessfulCompositeDate" in source_props
    assert "latestSuccessfulCompositeProductId" in source_props
    assert "latestSuccessfulComposites" in source_props
    assert "daysSinceLatestSuccessfulComposite" in source_props
    assert "isSuccessfulCompositeStale" in source_props
    assert "warnings" in source_props
    assert "tileUnavailableReasons" in source_props

    ledger_source_props = schemas["MonitoringLedgerSource"]["properties"]
    assert "failureCountsByKind" in ledger_source_props
    assert "lastFailure" in ledger_source_props
    assert "latestSuccessfulCompositeDate" in ledger_source_props
    assert "latestSuccessfulComposites" in ledger_source_props

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
    assert summary["rowCount"] == 5
    assert summary["statusCounts"] == {"composited": 3, "failed": 1, "ingested": 1}
    assert summary["bytes"] == 1234
    assert summary["failureCountsByKind"] == {"bhoonidhi_auth": 1}
    by_source = summary["bySource"][0]
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
