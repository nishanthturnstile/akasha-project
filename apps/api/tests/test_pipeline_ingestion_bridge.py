from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Lock
from typing import Any

import pytest
from app.config import settings
from app.ingestion_client import _clear_field_index_point_cache
from app.main import app
from app.raster import catalog_resolver as catalog
from app.routers import analytics_router as field_analytics
from app.routers import product_router
from fastapi.testclient import TestClient

client = TestClient(app)

LEAK_TOKENS = ("tileUrl", "statsUrl", "overlayUrl", "pointUrl", "layerId", "sig", "kid", "exp")
RESOURCESAT_SOURCE_IDS = (
    catalog.RESOURCESAT_LISS3_SOURCE_ID,
    catalog.RESOURCESAT_LISS4_SOURCE_ID,
    catalog.RESOURCESAT_AWIFS_SOURCE_ID,
)


@pytest.fixture(autouse=True)
def pipeline_settings(monkeypatch):
    monkeypatch.setattr(settings, "default_source_id", catalog.SENTINEL_2_SOURCE_ID)
    monkeypatch.setattr(settings, "ingestion_api_url", "http://ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_resourcesat_cutover_enabled", True)
    monkeypatch.setattr(
        settings,
        "ingestion_resourcesat_cutover_source_ids",
        ",".join(RESOURCESAT_SOURCE_IDS),
    )
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setattr(settings, "ingestion_signed_url_allowed_prefix", "http://10.10.2.4:18080")
    monkeypatch.setattr(settings, "ingestion_signed_url_fetch_prefix", "http://127.0.0.1:18081")
    monkeypatch.setattr(settings, "index_request_timeout_seconds", 10)
    monkeypatch.setattr(settings, "ingestion_trend_max_dates", 3)
    _clear_field_index_point_cache()
    yield
    _clear_field_index_point_cache()


def _plot() -> dict[str, Any]:
    return {
        "id": "field-1",
        "name": "Pipeline Field",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [77.0, 12.0],
                    [77.01, 12.0],
                    [77.01, 12.01],
                    [77.0, 12.0],
                ]
            ],
        },
    }


def _available_result(
    selected_date: str = "2026-03-20", *, point_url: bool = True, display_meters: float = 10
) -> dict[str, Any]:
    result = {
        "status": "AVAILABLE",
        "queryId": f"query-{selected_date}",
        "selectedSceneDate": selected_date,
        "statistics": {
            "min": 0.12,
            "max": 0.82,
            "mean": 0.47,
            "median": 0.46,
            "stdDev": 0.08,
            "usablePixelPercentage": 91.5,
            "cloudPercentage": 3.25,
        },
        "resolution": {"displayMeters": display_meters},
        "selection": {"validPixelCount": 42, "coveragePixelCount": 50},
        "providerRoute": "field-index",
        "versions": {"pipeline": "test"},
        "tileUrl": "http://10.10.2.4:18080/tile?sig=tile&kid=k&exp=1",
        "statsUrl": "http://10.10.2.4:18080/stats?sig=stats&kid=k&exp=1",
        "overlayUrl": "http://10.10.2.4:18080/overlay?sig=overlay&kid=k&exp=1",
        "layerId": "signed-layer-id",
    }
    if point_url:
        result["pointUrl"] = "http://10.10.2.4:18080/point?sig=point&kid=k&exp=1"
    return result


def _assert_no_leaks(body: Any) -> None:
    serialized = json.dumps(body)
    for token in LEAK_TOKENS:
        assert token not in serialized
    assert "10.10.2.4" not in serialized
    assert "SECRET_API_KEY" not in serialized


def test_config_and_sources_expose_pipeline_default(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_args, **_kw: {"availableDates": ["2026-03-20"]},
    )

    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["defaultSourceId"] == catalog.SENTINEL_2_SOURCE_ID

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    sentinel = next(item for item in sources.json() if item["id"] == catalog.SENTINEL_2_SOURCE_ID)
    assert sentinel["pipelineBacked"] is True
    assert sentinel["displayModes"] == ["NDVI", "NDRE", "MSAVI", "NDMI"]
    assert sentinel["defaultDisplayMode"] == "NDVI"
    assert sentinel["defaultMapDisplayMode"] == "NDVI"

    dates = client.get(f"/api/sources/{catalog.SENTINEL_2_SOURCE_ID}/dates")
    assert dates.status_code == 200
    assert dates.json()[0]["acquisitionDate"] == "2026-03-20"


def test_sentinel_default_layer_uses_pipeline_readiness(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_args, **_kw: {
            "availableDates": ["2026-03-20", "2026-03-18"],
            "indexCoverage": {"NDVI": {"coveragePercent": 40.0}},
        },
    )
    monkeypatch.setattr(
        product_router.catalog,
        "list_dates",
        lambda *_args, **_kw: pytest.fail("native Sentinel date fallback"),
    )
    monkeypatch.setattr(
        product_router,
        "_next_expected_acquisition_date",
        lambda latest, revisit: "2026-07-18" if latest == "2026-03-20" and revisit == 5 else None,
    )

    response = client.get(f"/api/layers/default?sourceId={catalog.SENTINEL_2_SOURCE_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["sourceId"] == catalog.SENTINEL_2_SOURCE_ID
    assert body["acquisitionDate"] == "2026-03-20"
    assert body["revisitDays"] == 5
    assert body["nextExpectedAcquisitionDate"] == "2026-07-18"
    assert body["pipelineBacked"] is True
    assert body["tileRouteMode"] == "field-overlay"
    assert body["tileUrlTemplate"] is None


def test_field_dates_exclude_unusable_dates_and_recompute_latest(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sar_support_cloud_threshold_percent", 35)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_args: _plot())
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda _source_id, **_kwargs: [
            {
                "acquisitionDate": "2026-06-28",
                "isLatestUsable": True,
                "usablePixelPercent": None,
                "cloudMaskedPercent": None,
                "tileAvailable": True,
            },
            {
                "acquisitionDate": "2026-05-19",
                "isLatestUsable": False,
                "usablePixelPercent": None,
                "cloudMaskedPercent": None,
                "tileAvailable": True,
            },
            {
                "acquisitionDate": "2026-05-12",
                "isLatestUsable": False,
                "usablePixelPercent": None,
                "cloudMaskedPercent": None,
                "tileAvailable": True,
            },
        ],
    )
    calls: list[dict[str, Any]] = []

    def fake_field_dates(_settings, **kwargs):
        calls.append(kwargs)
        return {
            "sourceId": catalog.SENTINEL_2_SOURCE_ID,
            "index": "NDVI",
            "dates": [
                {
                    "acquisitionDate": "2026-06-28",
                    "available": False,
                    "reason": "No exact-date scene satisfies field quality thresholds.",
                },
                {
                    "acquisitionDate": "2026-05-19",
                    "available": True,
                    "selectedSceneDate": "2026-05-19",
                    "usablePixelPercentage": 92.5,
                    "cloudPercentage": 4.2,
                    "fieldCoveragePercentage": 98.0,
                    "shadowPercentage": 1.0,
                    "obscuredPercentage": 5.2,
                    "validPixelCount": 100,
                },
                {
                    "acquisitionDate": "2026-05-12",
                    "available": True,
                    "selectedSceneDate": "2026-05-12",
                    "usablePixelPercentage": 85.0,
                    "cloudPercentage": 8.0,
                    "fieldCoveragePercentage": 96.0,
                    "shadowPercentage": 2.0,
                    "obscuredPercentage": 10.0,
                    "validPixelCount": 80,
                },
            ],
        }

    monkeypatch.setattr(field_analytics, "request_field_dates", fake_field_dates)

    response = client.get(
        "/api/fields/field-1/dates?sourceId=sentinel-2-l2a&indexType=NDVI&lookbackDays=153"
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["acquisitionDate"] for item in body] == ["2026-05-19", "2026-05-12"]
    assert body[0]["isLatestUsable"] is True
    assert body[1]["isLatestUsable"] is False
    assert body[0]["usablePixelPercent"] == pytest.approx(92.5)
    assert body[0]["cloudMaskedPercent"] == pytest.approx(4.2)
    assert calls[0]["geometry"] == _plot()["geometry"]
    assert calls[0]["max_cloud_percentage"] == 20.0
    assert calls[0]["acquisition_dates"] == ["2026-06-28", "2026-05-19", "2026-05-12"]
    _assert_no_leaks(body)


def test_field_dates_reject_unknown_or_unowned_field(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_args: None)
    monkeypatch.setattr(
        field_analytics,
        "request_field_dates",
        lambda *_args, **_kwargs: pytest.fail("ingestion must not receive unowned geometry"),
    )

    response = client.get("/api/fields/not-owned/dates?sourceId=sentinel-2-l2a&indexType=NDVI")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FIELD_NOT_FOUND"


def test_monitoring_evidence_skips_radar_when_optical_is_fresh(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(settings, "eos04_field_support_enabled", True)
    monkeypatch.setattr(
        field_analytics,
        "_field_dates_response",
        lambda **_kwargs: [{"acquisitionDate": "2026-07-15"}],
    )
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda *_args, **_kwargs: [{"acquisitionDate": "2026-07-15"}],
    )
    monkeypatch.setattr(
        field_analytics,
        "request_field_sar",
        lambda *_args, **_kwargs: pytest.fail("fresh optical evidence must not request SAR"),
    )

    response = client.get(
        "/api/fields/field-1/monitoring/evidence"
        "?sourceId=sentinel-2-l2a&indexType=NDVI&targetDate=2026-07-18"
    )

    assert response.status_code == 200
    assert response.json()["optical"]["status"] == "usable"
    assert response.json()["radar"]["status"] == "NOT_REQUESTED"


def test_monitoring_evidence_uses_field_sar_for_optical_quality_gap(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(settings, "eos04_field_support_enabled", True)
    monkeypatch.setattr(field_analytics, "_field_dates_response", lambda **_kwargs: [])
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda *_args, **_kwargs: [{"acquisitionDate": "2026-07-17"}],
    )
    calls: list[dict[str, Any]] = []

    def fake_field_sar(*_args, **kwargs):
        calls.append(kwargs)
        return {
            "status": "AVAILABLE",
            "queryId": "private-query",
            "sourceId": "eos-04-sar-mrs-l2b",
            "requestedDate": "2026-07-18",
            "acquisitionDate": "2026-07-17",
            "daysFromTarget": -1,
            "coveragePercent": 100,
            "validPixelCount": 120,
            "fieldPixelCount": 120,
            "polarizations": ["HH", "HV"],
            "displayedPolarization": "HH",
            "bands": [],
            "features": {"HH_MINUS_HV_DB": 5.2},
            "quality": {"qualified": True, "confidence": "high", "warnings": []},
            "provenance": {"unit": "dB", "rtcApplied": True},
            "overlayUrl": "http://10.10.2.4:18080/private?sig=secret",
        }

    monkeypatch.setattr(field_analytics, "request_field_sar", fake_field_sar)
    response = client.get(
        "/api/fields/field-1/monitoring/evidence"
        "?sourceId=sentinel-2-l2a&indexType=NDVI&targetDate=2026-07-18"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["optical"]["status"] == "quality_limited"
    assert body["radar"]["status"] == "AVAILABLE"
    assert body["radar"]["overlayUrl"].startswith("/api/fields/field-1/sar/overlay.png")
    assert "private-query" not in json.dumps(body)
    assert "10.10.2.4" not in json.dumps(body)
    assert calls[0]["geometry"] == _plot()["geometry"]


def test_monitoring_evidence_exposes_temporal_radar_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(settings, "eos04_field_support_enabled", True)
    monkeypatch.setattr(settings, "eos04_temporal_change_enabled", True)
    monkeypatch.setattr(settings, "eos04_temporal_shadow_enabled", False)
    monkeypatch.setattr(field_analytics, "_field_dates_response", lambda **_kwargs: [])
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda *_args, **_kwargs: [{"acquisitionDate": "2026-07-17"}],
    )
    calls: list[dict[str, Any]] = []

    def fake_field_sar(*_args, **kwargs):
        calls.append(kwargs)
        return {
            "status": "AVAILABLE",
            "queryId": "private-query",
            "acquisitionDate": "2026-07-17",
            "coveragePercent": 100,
            "comparison": {
                "status": "INSUFFICIENT_BASELINE",
                "previousComparableDate": "2026-06-13",
                "comparableObservationCount": 2,
            },
            "history": [{"acquisitionDate": "2026-06-13"}],
            "change": {
                "status": "AVAILABLE",
                "referenceDate": "2026-06-13",
                "bands": [{"polarization": "HH", "medianDeltaDb": 1.2}],
            },
            "baseline": {
                "status": "INSUFFICIENT_OBSERVATIONS",
                "requiredPriorObservations": 5,
                "priorObservationCount": 1,
            },
            "overlayUrl": "http://10.10.2.4:18080/private?sig=secret",
        }

    monkeypatch.setattr(field_analytics, "request_field_sar", fake_field_sar)
    response = client.get(
        "/api/fields/field-1/monitoring/evidence"
        "?sourceId=sentinel-2-l2a&indexType=NDVI&targetDate=2026-07-18"
    )

    assert response.status_code == 200
    radar = response.json()["radar"]
    assert radar["comparison"]["previousComparableDate"] == "2026-06-13"
    assert radar["change"]["bands"][0]["medianDeltaDb"] == 1.2
    assert calls[0]["include_history"] is True
    assert "private-query" not in json.dumps(radar)


def test_field_sar_overlay_proxies_signed_png(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(settings, "eos04_field_support_enabled", True)
    monkeypatch.setattr(
        field_analytics,
        "request_field_sar",
        lambda *_args, **_kwargs: {
            "status": "AVAILABLE",
            "overlayUrl": "http://10.10.2.4:18080/sar?sig=secret",
        },
    )
    monkeypatch.setattr(
        field_analytics,
        "fetch_signed_ingestion_binary",
        lambda *_args: (
            b"sar-png",
            "image/png",
            {"X-Akasha-Overlay-Corners": "[[77,12],[77.1,12],[77.1,12.1],[77,12.1]]"},
        ),
    )

    response = client.get("/api/fields/field-1/sar/overlay.png?targetDate=2026-07-18")

    assert response.status_code == 200
    assert response.content == b"sar-png"
    assert response.headers["x-akasha-resolved-source"] == "eos-04-sar-mrs-l2b"
    assert "secret" not in response.text


def test_field_dates_use_expensive_index_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_index_per_minute", 1)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_args: _plot())
    monkeypatch.setattr(field_analytics, "_field_dates_response", lambda **_kwargs: [])

    first = client.get("/api/fields/field-1/dates?sourceId=sentinel-2-l2a&indexType=NDVI")
    second = client.get("/api/fields/field-1/dates?sourceId=sentinel-2-l2a&indexType=NDVI")

    assert first.status_code == 200
    assert second.status_code == 429


def test_field_dates_timeout_returns_without_waiting_for_blocking_worker(monkeypatch) -> None:
    monkeypatch.setattr(settings, "index_request_timeout_seconds", 0.02)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_args: _plot())

    def slow_field_dates(**_kwargs):
        time.sleep(0.2)
        return []

    monkeypatch.setattr(field_analytics, "_field_dates_response", slow_field_dates)

    started = time.monotonic()
    response = client.get("/api/fields/field-1/dates?sourceId=sentinel-2-l2a&indexType=NDVI")
    elapsed = time.monotonic() - started

    assert response.status_code == 504
    assert elapsed < 0.15


def test_field_dates_chunk_dense_timelines_without_dropping_dates(monkeypatch) -> None:
    acquisition_dates = [
        (date(2026, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(65)
    ]
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda _source_id, **_kwargs: [
            {
                "acquisitionDate": acquisition_date,
                "isLatestUsable": False,
                "tileAvailable": True,
            }
            for acquisition_date in acquisition_dates
        ],
    )
    batches: list[list[str]] = []

    def fake_field_dates(_settings, **kwargs):
        batch = kwargs["acquisition_dates"]
        batches.append(batch)
        return {
            "sourceId": catalog.SENTINEL_2_SOURCE_ID,
            "index": "NDVI",
            "dates": [
                {
                    "acquisitionDate": acquisition_date,
                    "available": True,
                    "selectedSceneDate": acquisition_date,
                    "usablePixelPercentage": 90.0,
                    "cloudPercentage": 5.0,
                    "fieldCoveragePercentage": 97.0,
                    "shadowPercentage": 1.0,
                    "obscuredPercentage": 6.0,
                    "validPixelCount": 100,
                }
                for acquisition_date in batch
            ],
        }

    monkeypatch.setattr(field_analytics, "request_field_dates", fake_field_dates)

    response = field_analytics._field_dates_response(
        plot=_plot(),
        source_id=catalog.SENTINEL_2_SOURCE_ID,
        index_type="NDVI",
        start_date=None,
        end_date=None,
        lookback_days=None,
    )

    assert [len(batch) for batch in batches] == [64, 1]
    assert len(response) == 65
    assert {item["acquisitionDate"] for item in response} == set(acquisition_dates)


def test_field_dates_include_field_qualified_regional_awifs(monkeypatch) -> None:
    monkeypatch.setattr(
        field_analytics,
        "_pipeline_dates",
        lambda *_args, **_kwargs: [
            {
                "acquisitionDate": "2026-03-15",
                "datetime": "2026-03-15T00:00:00Z",
                "tileAvailable": True,
                "sensor": "AWiFS",
                "resolutionMeters": 56,
            }
        ],
    )
    monkeypatch.setattr(
        field_analytics,
        "request_field_dates",
        lambda *_args, **_kwargs: {
            "sourceId": catalog.RESOURCESAT_AWIFS_SOURCE_ID,
            "index": "NDVI",
            "dates": [
                {
                    "acquisitionDate": "2026-03-15",
                    "available": True,
                    "selectedSceneDate": "2026-03-15",
                    "usablePixelPercentage": 84.0,
                    "cloudPercentage": 16.0,
                    "fieldCoveragePercentage": 100.0,
                    "shadowPercentage": 0.0,
                    "obscuredPercentage": 16.0,
                    "validPixelCount": 21,
                }
            ],
        },
    )

    response = field_analytics._field_dates_response(
        plot=_plot(),
        source_id=catalog.RESOURCESAT_AWIFS_SOURCE_ID,
        index_type="NDVI",
        start_date=None,
        end_date=None,
        lookback_days=None,
    )

    assert response == [
        {
            "acquisitionDate": "2026-03-15",
            "datetime": "2026-03-15T00:00:00Z",
            "tileAvailable": True,
            "sensor": "AWiFS",
            "resolutionMeters": 56,
            "usablePixelPercent": 84.0,
            "cloudMaskedPercent": 16.0,
            "coveragePercent": 100.0,
            "shadowPercent": 0.0,
            "obscuredPercent": 16.0,
            "isLatestUsable": True,
        }
    ]


def test_resourcesat_sources_and_dates_use_pipeline_readiness(monkeypatch) -> None:
    def fake_readiness(_settings, *, source_id: str, aoi_id: str, **_kwargs):
        assert source_id in RESOURCESAT_SOURCE_IDS
        assert aoi_id == "bangalore_60km_geodesic_aoi"
        return {
            "availableDates": ["2026-04-02", "2026-03-28"],
            "indexCoverage": {"NDVI": {"coveragePercent": 87.5}},
        }

    monkeypatch.setattr(product_router, "get_readiness", fake_readiness)
    monkeypatch.setattr(
        product_router.catalog,
        "list_dates",
        lambda source_id: pytest.fail(f"native dates fallback for {source_id}"),
    )

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    by_id = {item["id"]: item for item in sources.json()}

    liss3 = by_id[catalog.RESOURCESAT_LISS3_SOURCE_ID]
    assert liss3["pipelineBacked"] is True
    assert liss3["supportedIndices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert liss3["resolutionMeters"] == 24

    liss4 = by_id[catalog.RESOURCESAT_LISS4_SOURCE_ID]
    assert liss4["pipelineBacked"] is True
    assert liss4["supportedIndices"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert "NDMI" not in liss4["displayModes"]
    assert liss4["resolutionMeters"] == 5.8

    awifs = by_id[catalog.RESOURCESAT_AWIFS_SOURCE_ID]
    assert awifs["pipelineBacked"] is True
    assert awifs["analysisLevel"] == "regional"
    assert awifs["resolutionMeters"] == 56

    dates = client.get(f"/api/sources/{catalog.RESOURCESAT_LISS4_SOURCE_ID}/dates")
    assert dates.status_code == 200
    body = dates.json()
    assert [item["acquisitionDate"] for item in body] == ["2026-04-02", "2026-03-28"]
    assert body[0]["sensor"] == "LISS-4"
    assert body[0]["provenanceLabel"] == "LISS-4 · 5.8 m"
    assert body[0]["resolvedSourceId"] == catalog.RESOURCESAT_LISS4_SOURCE_ID
    assert body[0]["resolutionMeters"] == 5.8
    assert body[0]["coveragePercent"] == pytest.approx(87.5)
    assert body[0]["metricsProvisional"] is True


def test_resourcesat_uses_native_catalog_until_cutover_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_resourcesat_cutover_enabled", False)
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_args, **_kw: pytest.fail("readiness used before ResourceSat cutover"),
    )
    monkeypatch.setattr(
        product_router.catalog,
        "list_dates",
        lambda source_id: (
            [
                {
                    "acquisitionDate": "2026-03-19",
                    "tileAvailable": True,
                    "sceneCount": 1,
                }
            ]
            if source_id == catalog.RESOURCESAT_LISS3_SOURCE_ID
            else []
        ),
    )

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    liss3 = next(
        item for item in sources.json() if item["id"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    )
    assert liss3.get("pipelineBacked") is not True
    assert liss3["defaultDisplayMode"] == "FCC"

    dates = client.get(f"/api/sources/{catalog.RESOURCESAT_LISS3_SOURCE_ID}/dates")
    assert dates.status_code == 200
    assert dates.json()[0]["acquisitionDate"] == "2026-03-19"


def test_resourcesat_cutover_is_scoped_to_accepted_source_ids(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_resourcesat_cutover_enabled", True)
    monkeypatch.setattr(
        settings,
        "ingestion_resourcesat_cutover_source_ids",
        catalog.RESOURCESAT_LISS3_SOURCE_ID,
    )

    assert product_router._requires_ingestion_pipeline(catalog.RESOURCESAT_LISS3_SOURCE_ID)
    assert not product_router._requires_ingestion_pipeline(catalog.RESOURCESAT_LISS4_SOURCE_ID)
    assert not product_router._requires_ingestion_pipeline(catalog.RESOURCESAT_AWIFS_SOURCE_ID)


def test_half_enabled_bridge_does_not_advertise_pipeline_source(monkeypatch) -> None:
    # readiness ON but field-index OFF must be treated as bridge-OFF (REQ-012): otherwise the
    # source would be advertised as pipelineBacked while statistics/trend/overlay/point silently
    # take the native ResourceSat path (REQ-009).
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", False)
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_a, **_k: pytest.fail("pipeline readiness used while field-index disabled"),
    )

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    pipeline_sentinel = [
        item
        for item in sources.json()
        if item["id"] == catalog.SENTINEL_2_SOURCE_ID and item.get("pipelineBacked")
    ]
    assert pipeline_sentinel == []
    liss3 = next(
        item for item in sources.json() if item["id"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    )
    assert liss3["pipelineBacked"] is True


def test_resourcesat_dates_use_ingestion_even_when_bridge_flags_are_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", False)
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", False)
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_args, **_kw: {
            "availableDates": ["2026-04-02"],
            "indexCoverage": {"NDVI": {"coveragePercent": 88.0}},
        },
    )
    monkeypatch.setattr(
        product_router.catalog,
        "list_dates",
        lambda *_args, **_kw: pytest.fail("native ResourceSat date fallback"),
    )

    response = client.get(f"/api/sources/{catalog.RESOURCESAT_LISS3_SOURCE_ID}/dates")

    assert response.status_code == 200
    assert response.json()[0]["acquisitionDate"] == "2026-04-02"


def test_resourcesat_default_layer_does_not_use_native_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "get_readiness",
        lambda *_args, **_kw: {
            "availableDates": ["2026-04-02"],
            "indexCoverage": {"NDVI": {"coveragePercent": 88.0}},
        },
    )
    monkeypatch.setattr(
        product_router.catalog,
        "list_dates",
        lambda *_args, **_kw: pytest.fail("native ResourceSat date fallback"),
    )
    monkeypatch.setattr(
        product_router.catalog,
        "items_for_date",
        lambda *_args, **_kw: pytest.fail("native ResourceSat item lookup"),
    )

    response = client.get(f"/api/layers/default?sourceId={catalog.RESOURCESAT_LISS3_SOURCE_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["pipelineBacked"] is True
    assert body["tileRouteMode"] == "field-overlay"
    assert body["tileUrlTemplate"] is None
    assert body["acquisitionDate"] == "2026-04-02"


def test_resourcesat_direct_tile_route_does_not_use_native_assets(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router.catalog,
        "resolve_assets_for_date",
        lambda *_args, **_kw: pytest.fail("native ResourceSat asset lookup"),
    )

    response = client.get(
        f"/api/tiles/{catalog.RESOURCESAT_LISS3_SOURCE_ID}/2026-04-02/FCC/8/1/1.png"
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INGESTION_TILE_UNAVAILABLE"


def test_resourcesat_root_statistics_route_does_not_use_native_compute(monkeypatch) -> None:
    monkeypatch.setattr(
        product_router,
        "compute_statistics",
        lambda **_kw: pytest.fail("native ResourceSat root statistics fallback"),
    )

    response = client.post(
        "/api/indices/statistics",
        json={
            "sourceId": catalog.RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-04-02",
            "indexType": "NDVI",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[[77.0, 12.0], [77.01, 12.0], [77.01, 12.01], [77.0, 12.0]]]],
            },
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INGESTION_FIELD_INDEX_REQUIRED"


def test_health_exposes_only_non_secret_ingestion_flags() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ingestionConfigured"] is True
    assert body["ingestionReadinessEnabled"] is True
    assert body["ingestionFieldIndexEnabled"] is True
    _assert_no_leaks(body)


def test_pipeline_dates_do_not_fall_back_on_missing_readiness(monkeypatch) -> None:
    monkeypatch.setattr(product_router, "get_readiness", lambda *_args, **_kw: None)
    monkeypatch.setattr(
        product_router.catalog, "list_dates", lambda *_: pytest.fail("native fallback")
    )

    response = client.get(f"/api/sources/{catalog.SENTINEL_2_SOURCE_ID}/dates")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INGESTION_READINESS_UNAVAILABLE"


def test_statistics_uses_pipeline_adapter_and_no_signed_url_leaks(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics, "request_field_index", lambda *_args, **_kw: _available_result()
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: pytest.fail("native statistics fallback"),
    )

    response = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": catalog.SENTINEL_2_SOURCE_ID,
            "acquisitionDate": "2026-03-20",
            "indexType": "NDVI",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "pipeline"
    assert body["scope"] == "field"
    assert body["resolutionMeters"] == 10
    assert body["statistics"]["mean"] == pytest.approx(0.47)
    assert body["statistics"]["stddev"] == pytest.approx(0.08)
    assert body["statistics"]["validPixelPercent"] == pytest.approx(91.5)
    assert body["statistics"]["cloudMaskedPercent"] == pytest.approx(3.25)
    assert body["statistics"]["coveragePercent"] == pytest.approx(0.0)
    assert body["pixelCounts"]["validPixels"] == 42
    assert set(body["metadata"]) == {"provider", "scope", "queryId", "providerRoute", "versions"}
    _assert_no_leaks(body)


def test_resourcesat_statistics_sends_source_id_and_never_uses_native(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    calls: list[dict[str, Any]] = []

    def fake_request_field_index(*_args, **kwargs):
        calls.append(kwargs)
        return _available_result("2026-04-02", display_meters=24)

    monkeypatch.setattr(field_analytics, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: pytest.fail("native statistics fallback"),
    )

    response = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": catalog.RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-04-02",
            "indexType": "NDWI_GREEN_NIR",
        },
    )

    assert response.status_code == 200
    assert calls[0]["source_id"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    assert calls[0]["index_type"] == "NDWI_GREEN_NIR"
    body = response.json()
    assert body["provider"] == "pipeline"
    assert body["sourceId"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    assert body["indexType"] == "NDWI_GREEN_NIR"
    assert body["resolutionMeters"] == 24
    _assert_no_leaks(body)


@pytest.mark.parametrize(
    "source_id",
    (catalog.SENTINEL_2_SOURCE_ID, *RESOURCESAT_SOURCE_IDS),
)
def test_all_four_production_sources_use_pipeline_statistics(monkeypatch, source_id: str) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    calls: list[dict[str, Any]] = []

    def fake_request_field_index(*_args, **kwargs):
        calls.append(kwargs)
        return _available_result()

    monkeypatch.setattr(field_analytics, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: pytest.fail("native statistics fallback"),
    )

    response = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": source_id,
            "acquisitionDate": "2026-03-20",
            "indexType": "NDVI",
        },
    )

    assert response.status_code == 200
    assert calls[0]["source_id"] == source_id
    assert response.json()["sourceId"] == source_id


def test_resourcesat_liss4_rejects_unsupported_pipeline_index_before_upstream(
    monkeypatch,
) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "request_field_index",
        lambda *_args, **_kw: pytest.fail("unsupported index sent upstream"),
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: pytest.fail("native statistics fallback"),
    )

    response = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": catalog.RESOURCESAT_LISS4_SOURCE_ID,
            "acquisitionDate": "2026-04-02",
            "indexType": "NDMI",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_INDEX"
    assert response.json()["error"]["details"]["sourceId"] == catalog.RESOURCESAT_LISS4_SOURCE_ID


def test_statistics_unavailable_is_typed_and_never_native(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "request_field_index",
        lambda *_args, **_kw: {
            "status": "UNAVAILABLE",
            "reason": "no usable scene",
            "overlayUrl": "http://10.10.2.4:18080/overlay?sig=secret",
        },
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: pytest.fail("native statistics fallback"),
    )

    response = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": catalog.SENTINEL_2_SOURCE_ID,
            "acquisitionDate": "2026-03-20",
            "indexType": "NDVI",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INGESTION_OVERLAY_UNAVAILABLE"
    _assert_no_leaks(response.json())


def test_pipeline_trend_caps_newest_dates_dedups_and_returns_provisional(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "get_readiness",
        lambda *_args, **_kw: {
            "availableDates": ["2026-03-18", "2026-03-19", "2026-03-20", "2026-03-21"]
        },
    )
    calls: list[str] = []

    def fake_request_field_index(*_args, **kwargs):
        requested = kwargs["acquisition_date"]
        calls.append(requested)
        if requested == "2026-03-21":
            return {"status": "UNAVAILABLE", "reason": "cloudy"}
        return _available_result("2026-03-20")

    monkeypatch.setattr(field_analytics, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(
        field_analytics,
        "_native_trend_response",
        lambda **_kw: pytest.fail("native trend fallback"),
    )

    response = client.get(
        "/api/fields/field-1/analytics/trend"
        f"?sourceId={catalog.SENTINEL_2_SOURCE_ID}"
        "&indexType=NDVI&startDate=2026-03-18&endDate=2026-03-21"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "pipeline"
    assert body["scope"] == "pipeline"
    assert calls == ["2026-03-19", "2026-03-20", "2026-03-21"]
    assert [point["acquisitionDate"] for point in body["points"]] == [
        "2026-03-20",
        "2026-03-21",
    ]
    assert body["points"][0]["mean"] == pytest.approx(0.47)
    assert body["points"][1]["metricsProvisional"] is True
    assert body["points"][1]["unavailableReason"] == "cloudy"
    _assert_no_leaks(body)


def test_resourcesat_trend_sends_source_id_and_never_uses_native(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "get_readiness",
        lambda *_args, **_kw: {"availableDates": ["2026-04-01", "2026-04-02"]},
    )
    calls: list[dict[str, Any]] = []

    def fake_request_field_index(*_args, **kwargs):
        calls.append(kwargs)
        return _available_result(kwargs["acquisition_date"], display_meters=5.8)

    monkeypatch.setattr(field_analytics, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(
        field_analytics,
        "_native_trend_response",
        lambda **_kw: pytest.fail("native trend fallback"),
    )

    response = client.get(
        "/api/fields/field-1/analytics/trend"
        f"?sourceId={catalog.RESOURCESAT_LISS4_SOURCE_ID}"
        "&indexType=NDWI_GREEN_NIR&startDate=2026-04-01&endDate=2026-04-02"
    )

    assert response.status_code == 200
    assert {call["source_id"] for call in calls} == {catalog.RESOURCESAT_LISS4_SOURCE_ID}
    assert response.json()["provider"] == "pipeline"
    assert response.json()["sourceId"] == catalog.RESOURCESAT_LISS4_SOURCE_ID
    _assert_no_leaks(response.json())


def test_pipeline_trend_empty_readiness_is_typed(monkeypatch) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics, "get_readiness", lambda *_args, **_kw: {"availableDates": []}
    )
    monkeypatch.setattr(
        field_analytics,
        "_native_trend_response",
        lambda **_kw: pytest.fail("native trend fallback"),
    )

    response = client.get(
        "/api/fields/field-1/analytics/trend"
        f"?sourceId={catalog.SENTINEL_2_SOURCE_ID}"
        "&indexType=NDVI&startDate=2026-03-18&endDate=2026-03-21"
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INGESTION_READINESS_UNAVAILABLE"


def test_resourcesat_overlay_fetches_signed_pipeline_png_and_never_uses_native(
    monkeypatch,
) -> None:
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "_index_overlay_response",
        lambda **_kw: pytest.fail("native overlay fallback"),
    )
    calls: list[dict[str, Any]] = []

    def fake_request_field_index(*_args, **kwargs):
        calls.append(kwargs)
        return _available_result("2026-04-02", display_meters=24)

    def fake_fetch(_settings, url: str):
        assert "sig=overlay" in url
        return (
            b"pipeline-png",
            "image/png",
            {
                "X-Akasha-Overlay-Corners": "[[77,12],[77.1,12],[77.1,12.1],[77,12.1]]",
                "X-Akasha-Overlay-Stretch": "-1.0,1.0",
            },
        )

    monkeypatch.setattr(field_analytics, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(field_analytics, "fetch_signed_ingestion_binary", fake_fetch)

    response = client.get(
        "/api/fields/field-1/overlay/NDVI.png"
        f"?sourceId={catalog.RESOURCESAT_LISS3_SOURCE_ID}&acquisitionDate=2026-04-02"
    )

    assert response.status_code == 200
    assert response.content == b"pipeline-png"
    assert calls[0]["source_id"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    assert response.headers["x-akasha-resolved-source"] == catalog.RESOURCESAT_LISS3_SOURCE_ID
    assert response.headers["x-akasha-resolved-resolution"] == "24"
    assert "sig=overlay" not in response.text


def test_pipeline_point_route_uses_cache_and_never_native(monkeypatch) -> None:
    import app.ingestion_client as ingestion_client

    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "_field_index_point_response",
        lambda **_kw: pytest.fail("native point fallback"),
    )
    field_index_calls: list[str] = []

    def fake_request_field_index(*_args, **kwargs):
        field_index_calls.append(kwargs["acquisition_date"])
        return _available_result(point_url=True)

    def fake_fetch(_settings, url: str):
        assert "lng=77.1" in url
        assert "lat=12.1" in url
        return {
            "queryId": "query-2026-03-20",
            "index": "NDVI",
            "lng": 77.1,
            "lat": 12.1,
            "value": 0.33,
            "masked": False,
            "maskClass": 1,
            "source": {"displayMeters": 10},
            "pointUrl": "http://10.10.2.4:18080/point?sig=secret",
        }

    monkeypatch.setattr(ingestion_client, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(ingestion_client, "fetch_signed_ingestion_json", fake_fetch)

    url = (
        "/api/fields/field-1/indices/point"
        f"?sourceId={catalog.SENTINEL_2_SOURCE_ID}"
        "&acquisitionDate=2026-03-20&indexType=NDVI&lng=77.1&lat=12.1"
    )
    first = client.get(url)
    second = client.get(url)

    assert first.status_code == 200
    assert second.status_code == 200
    assert field_index_calls == ["2026-03-20"]
    body = second.json()
    assert body["value"] == pytest.approx(0.33)
    assert body["masked"] is False
    assert body["maskClass"] == 1
    assert body["resolutionMeters"] == 10
    _assert_no_leaks(body)


def test_pipeline_point_cache_single_flights_concurrent_misses(monkeypatch) -> None:
    import app.ingestion_client as ingestion_client

    field_index_calls: list[str] = []
    fetch_guard = Lock()
    active_fetches = 0
    max_active_fetches = 0

    def fake_request_field_index(*_args, **kwargs):
        field_index_calls.append(kwargs["acquisition_date"])
        time.sleep(0.05)
        return _available_result(point_url=True)

    def fake_fetch(_settings, url: str):
        nonlocal active_fetches, max_active_fetches
        with fetch_guard:
            active_fetches += 1
            max_active_fetches = max(max_active_fetches, active_fetches)
        time.sleep(0.01)
        query = url.split("?", 1)[-1]
        try:
            return {
                "queryId": "query-2026-03-20",
                "index": "NDVI",
                "lng": float(query.split("lng=", 1)[1].split("&", 1)[0]),
                "lat": 12.1,
                "value": 0.33,
                "masked": False,
                "maskClass": 1,
                "source": {"displayMeters": 10},
            }
        finally:
            with fetch_guard:
                active_fetches -= 1

    monkeypatch.setattr(ingestion_client, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(ingestion_client, "fetch_signed_ingestion_json", fake_fetch)

    def lookup(offset: int):
        return ingestion_client.request_field_index_point(
            settings,
            geometry=_plot()["geometry"],
            field_id="field-1",
            source_id=catalog.SENTINEL_2_SOURCE_ID,
            index_type="NDVI",
            acquisition_date="2026-03-20",
            lng=77.1 + offset / 10_000,
            lat=12.1,
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lookup, range(20)))

    assert field_index_calls == ["2026-03-20"]
    assert max_active_fetches == 1
    assert len(results) == 20
    assert all(result["value"] == pytest.approx(0.33) for result in results)


def test_resourcesat_point_route_sends_source_id_and_never_uses_native(monkeypatch) -> None:
    import app.ingestion_client as ingestion_client

    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "_field_index_point_response",
        lambda **_kw: pytest.fail("native point fallback"),
    )
    calls: list[dict[str, Any]] = []

    def fake_request_field_index(*_args, **kwargs):
        calls.append(kwargs)
        return _available_result("2026-04-02", point_url=True, display_meters=5.8)

    def fake_fetch(_settings, url: str):
        assert "lng=77.1" in url
        assert "lat=12.1" in url
        return {
            "queryId": "query-2026-04-02",
            "index": "NDWI_GREEN_NIR",
            "lng": 77.1,
            "lat": 12.1,
            "value": 0.22,
            "masked": False,
            "maskClass": 1,
            "source": {"displayMeters": 5.8},
        }

    monkeypatch.setattr(ingestion_client, "request_field_index", fake_request_field_index)
    monkeypatch.setattr(ingestion_client, "fetch_signed_ingestion_json", fake_fetch)

    response = client.get(
        "/api/fields/field-1/indices/point"
        f"?sourceId={catalog.RESOURCESAT_LISS4_SOURCE_ID}"
        "&acquisitionDate=2026-04-02&indexType=NDWI_GREEN_NIR&lng=77.1&lat=12.1"
    )

    assert response.status_code == 200
    assert calls[0]["source_id"] == catalog.RESOURCESAT_LISS4_SOURCE_ID
    body = response.json()
    assert body["sourceId"] == catalog.RESOURCESAT_LISS4_SOURCE_ID
    assert body["value"] == pytest.approx(0.22)
    assert body["resolutionMeters"] == 5.8
    _assert_no_leaks(body)
