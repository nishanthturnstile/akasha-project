"""Route tests for the feature-gated Sentinel-2 NDVI pipeline stats branch."""

from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.ingestion_client import (
    FieldIndexAvailableResponse,
    FieldIndexUnavailableResponse,
    IngestionClientError,
    ReadinessResponse,
)
from app.main import app
from app.routers import analytics_router as field_analytics
from app.schemas.analytics import FieldStatisticsResponse
from fastapi.testclient import TestClient

client = TestClient(app)

SENTINEL = "sentinel-2-l2a"


@pytest.fixture(autouse=True)
def _pipeline_settings(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setattr(settings, "max_polygon_area_ha", 100000)
    monkeypatch.setattr(settings, "max_polygon_vertices", 10000)


def _plot(geom_type: str = "Polygon") -> dict[str, Any]:
    if geom_type == "MultiPolygon":
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [[[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]]],
        }
    else:
        geometry = {
            "type": "Polygon",
            "coordinates": [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]],
        }
    return {"id": "field-1", "name": "Field 1", "geometry": geometry, "areaHa": 3.0}


def _available_response() -> FieldIndexAvailableResponse:
    return FieldIndexAvailableResponse.model_validate(
        {
            "status": "AVAILABLE",
            "queryId": "q_secret",
            "fieldId": "ingestion_field",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "selectedSceneDate": "2026-01-13",
            "source": SENTINEL,
            "providerRoute": "earthsearch:sentinel-2-l2a",
            "resolution": {"processingMeters": 10},
            "layerId": "layer_secret",
            "tileUrl": "https://ingestion.internal/tiles/x?sig=SIGNED",
            "statsUrl": "https://ingestion.internal/stats?sig=SIGNED",
            "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
            "statistics": {
                "min": 0.12,
                "max": 0.86,
                "mean": 0.54,
                "stdDev": 0.08,
                "usablePixelPercentage": 92.5,
                "cloudPercentage": 4.2,
            },
            "quality": {"status": "GOOD", "reason": "OK", "warnings": []},
            "versions": {"analytics": "phase2-sentinel2-v1"},
        }
    )


def _unavailable_response() -> FieldIndexUnavailableResponse:
    return FieldIndexUnavailableResponse.model_validate(
        {
            "status": "UNAVAILABLE",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "reason": "No optical scene with field usable-pixels >= 80% within +/- 7 days",
            "searchedSources": [SENTINEL],
        }
    )


def _readiness(status: str = "AVAILABLE", **overrides: Any) -> ReadinessResponse:
    data: dict[str, Any] = {
        "status": status,
        "sourceId": SENTINEL,
        "aoiId": "bangalore_60km_geodesic_aoi",
        "latestProcessedSceneDate": "2026-01-13",
        "staleAfter": "2026-01-21T02:30:00Z",
        "availableDates": ["2026-01-13", "2026-01-06"],
        "indexCoverage": {"NDVI": {"available": True, "dateCount": 2, "coveragePercent": 100.0}},
    }
    data.update(overrides)
    return ReadinessResponse.model_validate(data)


class FakeClient:
    """Records calls; returns queued readiness/field_index results or raises."""

    def __init__(
        self,
        *,
        readiness_result: Any = None,
        field_index_result: Any = None,
    ) -> None:
        self._readiness_result = readiness_result
        self._field_index_result = field_index_result
        self.readiness_calls: list[dict[str, Any]] = []
        self.field_index_calls: list[Any] = []

    def readiness(self, *, source_id=None, aoi_id=None, request_id=None):
        self.readiness_calls.append({"source_id": source_id, "aoi_id": aoi_id})
        if isinstance(self._readiness_result, Exception):
            raise self._readiness_result
        return self._readiness_result

    def field_index(self, request, *, request_id=None):
        self.field_index_calls.append(request)
        if isinstance(self._field_index_result, Exception):
            raise self._field_index_result
        return self._field_index_result


def _install_client(monkeypatch, fake: FakeClient) -> FakeClient:
    monkeypatch.setattr(field_analytics, "IngestionClient", lambda *a, **k: fake)
    return fake


def _post(source_id: str = SENTINEL, index_type: str = "NDVI", **body: Any):
    payload = {"sourceId": source_id, "indexType": index_type, "acquisitionDate": "2026-01-15"}
    payload.update(body)
    return client.post("/api/fields/field-1/indices/statistics", json=payload)


def test_pipeline_available_calls_ingestion_and_adapts(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(readiness_result=_readiness(), field_index_result=_available_response()),
    )
    # Native path must not run for pipeline requests.
    monkeypatch.setattr(
        field_analytics, "compute_statistics", lambda **_: pytest.fail("native path used")
    )

    r = _post()
    assert r.status_code == 200
    body = r.json()
    assert body["plotId"] == "field-1"
    assert body["provider"] == "native"
    assert body["scope"] == "field"
    assert body["sourceId"] == SENTINEL
    assert body["acquisitionDate"] == "2026-01-15"
    assert body["basisDate"] == "2026-01-13"
    assert body["metadata"]["pipeline"]["enabled"] is True
    assert body["statistics"]["validPixelPercent"] == pytest.approx(92.5)
    assert body["pixelCounts"]["validPixels"] == 3456
    assert len(fake.readiness_calls) == 1
    assert len(fake.field_index_calls) == 1
    fi = fake.field_index_calls[0]
    assert fi.crs == "EPSG:4326"
    assert fi.index == "NDVI"
    assert fi.fallback_policy == "nearest_valid_scene"
    assert fi.max_cloud_percentage == 20
    assert fi.field_id == "field-1"
    assert fi.geometry["type"] == "Polygon"
    # No ingestion internals leak to the browser response.
    assert "ingestion.internal" not in r.text
    assert "q_secret" not in r.text
    assert "layer_secret" not in r.text


def test_pipeline_rejects_malformed_acquisition_date(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(readiness_result=_readiness(), field_index_result=_available_response()),
    )

    r = _post(acquisitionDate="2026-99-99")

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DATE"
    assert fake.field_index_calls == []


def test_pipeline_multipolygon_passthrough(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot("MultiPolygon"))
    fake = _install_client(
        monkeypatch,
        FakeClient(readiness_result=_readiness(), field_index_result=_available_response()),
    )
    r = _post()
    assert r.status_code == 200
    assert fake.field_index_calls[0].geometry["type"] == "MultiPolygon"


def test_pipeline_unavailable_returns_404(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(readiness_result=_readiness(), field_index_result=_unavailable_response()),
    )
    r = _post()
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "PIPELINE_OUTPUT_UNAVAILABLE"
    assert err["details"]["searchedSources"] == [SENTINEL]
    assert err["details"]["retryable"] is False


def test_pipeline_readiness_stale_gate(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness("STALE"),
            field_index_result=RuntimeError("field_index must not be called"),
        ),
    )
    r = _post()
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "PIPELINE_STALE"
    assert err["details"]["retryable"] is True
    assert fake.field_index_calls == []  # readiness gate blocks before ingestion


def test_pipeline_readiness_unavailable_gate(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness("UNAVAILABLE"),
            field_index_result=RuntimeError("must not call"),
        ),
    )
    r = _post()
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PIPELINE_OUTPUT_UNAVAILABLE"
    assert fake.field_index_calls == []


def test_pipeline_readiness_missing_ndvi_coverage_gate(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(
                indexCoverage={"NDVI": {"available": False, "dateCount": 0}}
            ),
            field_index_result=RuntimeError("must not call"),
        ),
    )
    r = _post()
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PIPELINE_OUTPUT_UNAVAILABLE"


def test_pipeline_enforces_readiness_even_when_readiness_flag_disabled(monkeypatch):
    # Mandatory readiness gate: taking the pipeline stats branch always calls and
    # enforces readiness, regardless of INGESTION_READINESS_ENABLED.
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", False)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness("STALE"),
            field_index_result=RuntimeError("field_index must not be called"),
        ),
    )
    r = _post()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PIPELINE_STALE"
    assert len(fake.readiness_calls) == 1  # readiness still fetched
    assert fake.field_index_calls == []


def test_pipeline_calls_field_index_when_readiness_flag_disabled_but_available(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", False)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(readiness_result=_readiness(), field_index_result=_available_response()),
    )
    r = _post()
    assert r.status_code == 200
    assert len(fake.readiness_calls) == 1  # readiness is mandatory
    assert len(fake.field_index_calls) == 1


def test_pipeline_client_error_propagates_no_native_fallback(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(),
            field_index_result=IngestionClientError(
                "PIPELINE_UPSTREAM_TIMEOUT",
                "Ingestion pipeline request timed out.",
                status_code=504,
                retryable=True,
            ),
        ),
    )
    monkeypatch.setattr(
        field_analytics, "compute_statistics", lambda **_: pytest.fail("native fallback used")
    )
    r = _post()
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "PIPELINE_UPSTREAM_TIMEOUT"


def test_flag_disabled_uses_native_path(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", False)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(field_index_result=RuntimeError("ingestion must not be called")),
    )
    called = {"native": False}

    def fake_native(**_):
        called["native"] = True
        return _native_stats()

    monkeypatch.setattr(field_analytics, "_field_statistics", fake_native)
    r = _post()
    assert r.status_code == 200
    assert called["native"] is True


def test_non_ndvi_uses_native_path(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(field_index_result=RuntimeError("ingestion must not be called")),
    )
    called = {"native": False}

    def fake_native(**_):
        called["native"] = True
        return _native_stats(index_type="NDMI")

    monkeypatch.setattr(field_analytics, "_field_statistics", fake_native)
    r = _post(index_type="NDMI")
    assert r.status_code == 200
    assert called["native"] is True


def test_non_sentinel_source_uses_native_path(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    _install_client(
        monkeypatch,
        FakeClient(field_index_result=RuntimeError("ingestion must not be called")),
    )
    called = {"native": False}

    def fake_native(**_):
        called["native"] = True
        return _native_stats(source_id="resourcesat-2a-liss3-boa")

    monkeypatch.setattr(field_analytics, "_field_statistics", fake_native)
    r = _post(source_id="resourcesat-2a-liss3-boa")
    assert r.status_code == 200
    assert called["native"] is True


def test_pipeline_rejects_invalid_geometry_before_ingestion(monkeypatch):
    bad_plot = {
        "id": "field-1",
        "name": "Field 1",
        "geometry": {"type": "Polygon", "coordinates": []},
        "areaHa": 0.0,
    }
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: bad_plot)
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(),
            field_index_result=RuntimeError("field_index must not be called"),
        ),
    )
    r = _post()
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_GEOMETRY"
    assert fake.field_index_calls == []


def test_pipeline_rejects_oversized_polygon_before_ingestion(monkeypatch):
    monkeypatch.setattr(settings, "max_polygon_area_ha", 0.0001)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    fake = _install_client(
        monkeypatch,
        FakeClient(
            readiness_result=_readiness(),
            field_index_result=RuntimeError("field_index must not be called"),
        ),
    )
    r = _post()
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "POLYGON_TOO_LARGE"
    assert fake.field_index_calls == []


def _native_stats(
    index_type: str = "NDVI", source_id: str = SENTINEL, acquisition_date: str = "2026-01-15"
) -> FieldStatisticsResponse:
    return FieldStatisticsResponse.model_validate(
        {
            "plotId": "field-1",
            "indexType": index_type,
            "sourceId": source_id,
            "acquisitionDate": acquisition_date,
            "cloudMask": {"clouds": True, "cloudShadows": True, "cirrus": True},
            "statistics": {
                "min": 0.1,
                "max": 0.8,
                "mean": 0.5,
                "stddev": 0.1,
                "validPixelPercent": 80.0,
                "cloudMaskedPercent": 5.0,
                "coveragePercent": 90.0,
            },
            "pixelCounts": {
                "totalPixels": 100,
                "nodataPixels": 5,
                "coveragePixels": 95,
                "maskedPixels": 5,
                "validPixels": 90,
            },
            "metadata": {"provider": "native", "scope": "field"},
        }
    )
