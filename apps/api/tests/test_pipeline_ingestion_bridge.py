from __future__ import annotations

import json
from typing import Any

import pytest
from app.config import settings
from app.ingestion_client import _FIELD_INDEX_POINT_CACHE
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
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setattr(settings, "ingestion_signed_url_allowed_prefix", "http://10.10.2.4:18080")
    monkeypatch.setattr(settings, "ingestion_signed_url_fetch_prefix", "http://127.0.0.1:18081")
    monkeypatch.setattr(settings, "index_request_timeout_seconds", 10)
    monkeypatch.setattr(settings, "ingestion_trend_max_dates", 3)
    _FIELD_INDEX_POINT_CACHE.clear()
    yield
    _FIELD_INDEX_POINT_CACHE.clear()


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
