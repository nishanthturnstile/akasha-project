"""Tests for the app-domain pipeline stats/tile proxy routes (Phase 5).

Covers: no URL/secret leakage, expired/invalid proxy IDs, unauthorized
user/team/field mismatch, sanitized upstream failures, DB-backed multi-worker
lookup, and adapter URL rewriting to opaque proxy URLs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth import DEV_TEAM_ID, DEV_USER_ID
from app.config import settings
from app.ingestion_client import IngestionClientError
from app.main import app
from app.routers import analytics_router as field_analytics
from app.routers import pipeline_proxy
from fastapi.testclient import TestClient

client = TestClient(app)

SENTINEL = "sentinel-2-l2a"
UPSTREAM_STATS = (
    "https://ingestion.internal/stats?queryId=q_secret&sig=SIGNED&kid=K1&exp=9999999999"
)
UPSTREAM_TILE = "https://ingestion.internal/tiles/{z}/{x}/{y}.png?layerId=layer_secret&sig=SIGNED&exp=9999999999"


@pytest.fixture(autouse=True)
def _relax_polygon_limits(monkeypatch):
    monkeypatch.setattr(settings, "max_polygon_area_ha", 100000)
    monkeypatch.setattr(settings, "max_polygon_vertices", 10000)


class FakeIngestionClient:
    def __init__(self, *, result: Any = None) -> None:
        self._result = result if result is not None else (b"\x89PNG_BYTES", "image/png")
        self.calls: list[str] = []

    def fetch_binary(self, url: str, *, request_id: str | None = None) -> tuple[bytes, str]:
        self.calls.append(url)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _record(
    *,
    operation: str = "stats",
    upstream_url: str = UPSTREAM_STATS,
    user_id: str = DEV_USER_ID,
    team_id: str = DEV_TEAM_ID,
    field_id: str = "field-1",
    expires_delta: timedelta = timedelta(hours=1),
) -> dict[str, Any]:
    return {
        "proxyId": "px_test",
        "operation": operation,
        "upstreamUrl": upstream_url,
        "userId": user_id,
        "teamId": team_id,
        "fieldId": field_id,
        "sourceId": SENTINEL,
        "indexType": "NDVI",
        "queryId": "q_secret",
        "layerId": "layer_secret",
        "expiresAt": datetime.now(UTC) + expires_delta,
        "createdAt": datetime.now(UTC),
        "lastAccessedAt": None,
    }


def _install(monkeypatch, *, record: dict[str, Any] | None, ingestion: FakeIngestionClient):
    monkeypatch.setattr(pipeline_proxy.proxy_repo, "get_proxy_record", lambda _pid: record)
    monkeypatch.setattr(pipeline_proxy.proxy_repo, "touch_last_accessed", lambda _pid: None)
    monkeypatch.setattr(
        pipeline_proxy.fields_repo,
        "get_field",
        lambda *_a, **_k: {"id": "field-1", "name": "Field 1"},
    )
    monkeypatch.setattr(pipeline_proxy, "IngestionClient", lambda *a, **k: ingestion)
    return ingestion


# --- stats proxy -----------------------------------------------------------


def test_stats_proxy_returns_json_and_no_leakage(monkeypatch):
    fake = _install(
        monkeypatch,
        record=_record(operation="stats"),
        ingestion=FakeIngestionClient(
            result=(
                b'{"success":true,"data":{"queryId":"q_secret","statistics":{"mean":0.42},"quality":{"status":"GOOD"}}}',
                "application/json",
            )
        ),
    )
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {
        "success": True,
        "data": {"statistics": {"mean": 0.42}, "quality": {"status": "GOOD"}},
    }
    # Upstream signed URL is used server-side, never returned to the browser.
    assert fake.calls == [UPSTREAM_STATS]
    for secret in ("ingestion.internal", "sig=", "kid=", "exp=", "q_secret", "layer_secret"):
        assert secret not in r.text


def test_stats_proxy_expired_record(monkeypatch):
    _install(
        monkeypatch,
        record=_record(operation="stats", expires_delta=timedelta(seconds=-1)),
        ingestion=FakeIngestionClient(),
    )
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_EXPIRED"


def test_stats_proxy_missing_record(monkeypatch):
    _install(monkeypatch, record=None, ingestion=FakeIngestionClient())
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "nope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_NOT_FOUND"


def test_stats_proxy_operation_mismatch(monkeypatch):
    # A tile record must not be resolvable through the stats route.
    _install(monkeypatch, record=_record(operation="tile"), ingestion=FakeIngestionClient())
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_NOT_FOUND"


def test_stats_proxy_user_mismatch_forbidden(monkeypatch):
    _install(
        monkeypatch,
        record=_record(operation="stats", user_id="00000000-0000-4000-8000-000000000999"),
        ingestion=FakeIngestionClient(),
    )
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_FORBIDDEN"


def test_stats_proxy_team_mismatch_forbidden(monkeypatch):
    _install(
        monkeypatch,
        record=_record(operation="stats", team_id="00000000-0000-4000-8000-000000000999"),
        ingestion=FakeIngestionClient(),
    )
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_FORBIDDEN"


def test_stats_proxy_field_access_forbidden(monkeypatch):
    _install(monkeypatch, record=_record(operation="stats"), ingestion=FakeIngestionClient())
    monkeypatch.setattr(pipeline_proxy.fields_repo, "get_field", lambda *_a, **_k: None)
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_FORBIDDEN"


def test_stats_proxy_upstream_failure_sanitized(monkeypatch):
    _install(
        monkeypatch,
        record=_record(operation="stats"),
        ingestion=FakeIngestionClient(
            result=IngestionClientError(
                "PIPELINE_UPSTREAM_TIMEOUT",
                "Ingestion pipeline request timed out.",
                status_code=504,
                retryable=True,
            )
        ),
    )
    r = client.get("/api/pipeline/field-index/stats", params={"proxyId": "px_test"})
    assert r.status_code == 504
    err = r.json()["error"]
    assert err["code"] == "PIPELINE_UPSTREAM_TIMEOUT"
    assert "ingestion.internal" not in r.text
    assert "sig=" not in r.text


# --- tile proxy ------------------------------------------------------------


def test_tile_proxy_returns_png_and_substitutes_xyz(monkeypatch):
    fake = _install(
        monkeypatch,
        record=_record(operation="tile", upstream_url=UPSTREAM_TILE),
        ingestion=FakeIngestionClient(result=(b"\x89PNG", "image/png")),
    )
    r = client.get("/api/pipeline/tiles/10/20/30.png", params={"proxyId": "px_test"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == b"\x89PNG"
    # XYZ placeholders are filled server-side against the stored template.
    assert fake.calls == [
        "https://ingestion.internal/tiles/10/20/30.png?layerId=layer_secret&sig=SIGNED&exp=9999999999"
    ]
    assert "ingestion.internal" not in r.text


def test_tile_proxy_expired_record(monkeypatch):
    _install(
        monkeypatch,
        record=_record(
            operation="tile", upstream_url=UPSTREAM_TILE, expires_delta=timedelta(seconds=-5)
        ),
        ingestion=FakeIngestionClient(),
    )
    r = client.get("/api/pipeline/tiles/1/2/3.png", params={"proxyId": "px_test"})
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "PIPELINE_PROXY_EXPIRED"


# --- DB-backed multi-worker lookup (repository round-trip) -----------------


def test_repo_record_dict_shape_supports_cross_worker_lookup():
    from app.models import PipelineProxyRecord
    from app.repositories.pipeline_proxy_repo import _record, new_proxy_id

    assert new_proxy_id().startswith("px_")
    now = datetime.now(UTC)
    row = PipelineProxyRecord(
        proxy_id="px_abc",
        operation="stats",
        upstream_url=UPSTREAM_STATS,
        user_id=None,
        team_id=None,
        field_id="field-1",
        source_id=SENTINEL,
        index_type="NDVI",
        query_id="q_secret",
        layer_id="layer_secret",
        expires_at=now,
        created_at=now,
        last_accessed_at=None,
    )
    # user_id/team_id are cast to str in the dict form used by the proxy route;
    # feed real-looking values to mirror a persisted row resolved by any worker.
    row.user_id = DEV_USER_ID
    row.team_id = DEV_TEAM_ID
    record = _record(row)
    assert record["operation"] == "stats"
    assert record["upstreamUrl"] == UPSTREAM_STATS
    assert record["userId"] == DEV_USER_ID
    assert record["teamId"] == DEV_TEAM_ID
    assert record["queryId"] == "q_secret"


# --- adapter URL rewriting via the stats route -----------------------------


def _available_response():
    from app.ingestion_client import FieldIndexAvailableResponse

    return FieldIndexAvailableResponse.model_validate(
        {
            "status": "AVAILABLE",
            "queryId": "q_secret",
            "index": "NDVI",
            "requestedDate": "2026-01-15",
            "selectedSceneDate": "2026-01-13",
            "source": SENTINEL,
            "providerRoute": "earthsearch:sentinel-2-l2a",
            "resolution": {"processingMeters": 10},
            "layerId": "layer_secret",
            "tileUrl": UPSTREAM_TILE,
            "statsUrl": UPSTREAM_STATS,
            "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
            "statistics": {
                "min": 0.1,
                "max": 0.8,
                "mean": 0.5,
                "stdDev": 0.08,
                "usablePixelPercentage": 90.0,
                "cloudPercentage": 5.0,
            },
        }
    )


def _readiness():
    from app.ingestion_client import ReadinessResponse

    return ReadinessResponse.model_validate(
        {
            "status": "AVAILABLE",
            "sourceId": SENTINEL,
            "aoiId": "bangalore_60km_geodesic_aoi",
            "latestProcessedSceneDate": "2026-01-13",
            "availableDates": ["2026-01-13"],
            "indexCoverage": {"NDVI": {"available": True, "dateCount": 1}},
        }
    )


class _StatsFakeClient:
    def readiness(self, *, source_id=None, aoi_id=None, request_id=None):
        return _readiness()

    def field_index(self, request, *, request_id=None):
        return _available_response()


def test_adapter_rewrites_urls_to_opaque_proxies(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(settings, "ingestion_pipeline_tile_layer_enabled", True)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics, "IngestionClient", lambda *a, **k: _StatsFakeClient())

    created: list[dict[str, Any]] = []
    counter = {"n": 0}

    def fake_create(**kwargs):
        counter["n"] += 1
        created.append(kwargs)
        return f"px_generated_{counter['n']}"

    monkeypatch.setattr(field_analytics.proxy_repo, "create_proxy_record", fake_create)

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    pipeline = r.json()["metadata"]["pipeline"]
    assert pipeline["statsUrl"] == "/api/pipeline/field-index/stats?proxyId=px_generated_1"
    assert pipeline["tileUrl"] == "/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_generated_2"

    # queryId/layerId are stored server-side but never leak to the browser.
    ops = {c["operation"] for c in created}
    assert ops == {"stats", "tile"}
    assert all(c["query_id"] == "q_secret" for c in created)
    assert all(c["upstream_url"].startswith("https://ingestion.internal") for c in created)
    for secret in ("ingestion.internal", "sig=", "kid=", "q_secret", "layer_secret"):
        assert secret not in r.text


def test_tile_proxy_url_omitted_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(settings, "ingestion_pipeline_tile_layer_enabled", False)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(field_analytics, "IngestionClient", lambda *a, **k: _StatsFakeClient())
    monkeypatch.setattr(
        field_analytics.proxy_repo, "create_proxy_record", lambda **_k: "px_stats_only"
    )

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    pipeline = r.json()["metadata"]["pipeline"]
    assert pipeline["statsUrl"] == "/api/pipeline/field-index/stats?proxyId=px_stats_only"
    assert "tileUrl" not in pipeline


def _available_with(stats_url: str, tile_url: str | None = None):
    from app.ingestion_client import FieldIndexAvailableResponse

    data: dict[str, Any] = {
        "status": "AVAILABLE",
        "queryId": "q_secret",
        "index": "NDVI",
        "requestedDate": "2026-01-15",
        "selectedSceneDate": "2026-01-13",
        "source": SENTINEL,
        "resolution": {"processingMeters": 10},
        "layerId": "layer_secret",
        "statsUrl": stats_url,
        "selection": {"windowDays": 7, "rule": "quality_first", "validPixelCount": 3456},
        "statistics": {
            "min": 0.1,
            "max": 0.8,
            "mean": 0.5,
            "stdDev": 0.08,
            "usablePixelPercentage": 90.0,
            "cloudPercentage": 5.0,
        },
    }
    if tile_url is not None:
        data["tileUrl"] = tile_url
    return FieldIndexAvailableResponse.model_validate(data)


class _ConfigurableStatsClient:
    def __init__(self, response) -> None:
        self._response = response

    def readiness(self, *, source_id=None, aoi_id=None, request_id=None):
        return _readiness()

    def field_index(self, request, *, request_id=None):
        return self._response


def _install_stats_client(monkeypatch, response, created: list[dict[str, Any]]):
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_source_id", SENTINEL)
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics, "IngestionClient", lambda *a, **k: _ConfigurableStatsClient(response)
    )

    counter = {"n": 0}

    def fake_create(**kwargs):
        counter["n"] += 1
        created.append(kwargs)
        return f"px_{kwargs['operation']}_{counter['n']}"

    monkeypatch.setattr(field_analytics.proxy_repo, "create_proxy_record", fake_create)


def test_stats_proxy_ttl_capped_to_upstream_exp(monkeypatch):
    # Upstream stats signature expires well before the configured proxy TTL, so
    # the persisted proxy record must not outlive the upstream signed URL.
    monkeypatch.setattr(settings, "ingestion_pipeline_proxy_ttl_seconds", 3600)
    upstream_exp = int((datetime.now(UTC) + timedelta(seconds=120)).timestamp())
    stats_url = f"https://ingestion.internal/stats?sig=SIGNED&exp={upstream_exp}"
    created: list[dict[str, Any]] = []
    _install_stats_client(monkeypatch, _available_with(stats_url), created)

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    stats_records = [c for c in created if c["operation"] == "stats"]
    assert len(stats_records) == 1
    persisted = stats_records[0]["expires_at"]
    assert persisted == datetime.fromtimestamp(upstream_exp, tz=UTC)
    # And it is capped strictly below now + configured TTL.
    assert persisted < datetime.now(UTC) + timedelta(seconds=3600)


def test_stats_proxy_omitted_when_upstream_exp_past(monkeypatch):
    # An already-expired upstream signed stats URL must not be wrapped in a proxy.
    monkeypatch.setattr(settings, "ingestion_pipeline_proxy_ttl_seconds", 3600)
    past_exp = int((datetime.now(UTC) - timedelta(seconds=60)).timestamp())
    stats_url = f"https://ingestion.internal/stats?sig=SIGNED&exp={past_exp}"
    created: list[dict[str, Any]] = []
    _install_stats_client(monkeypatch, _available_with(stats_url), created)

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    pipeline = r.json()["metadata"]["pipeline"]
    assert "statsUrl" not in pipeline
    assert [c for c in created if c["operation"] == "stats"] == []


@pytest.mark.parametrize(
    "stats_url",
    [
        "https://ingestion.internal/stats?sig=SIGNED",
        "https://ingestion.internal/stats?sig=SIGNED&exp=not-an-int",
    ],
)
def test_stats_proxy_omitted_when_upstream_exp_missing_or_malformed(monkeypatch, stats_url):
    # If the upstream signature expiry cannot be validated, fail closed rather
    # than minting an opaque proxy that may outlive the upstream authorization.
    monkeypatch.setattr(settings, "ingestion_pipeline_proxy_ttl_seconds", 3600)
    created: list[dict[str, Any]] = []
    _install_stats_client(monkeypatch, _available_with(stats_url), created)

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    pipeline = r.json()["metadata"]["pipeline"]
    assert "statsUrl" not in pipeline
    assert [c for c in created if c["operation"] == "stats"] == []
    assert "ingestion.internal" not in r.text
    assert "sig=" not in r.text


def test_tile_proxy_omitted_when_upstream_exp_missing(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_pipeline_proxy_ttl_seconds", 3600)
    monkeypatch.setattr(settings, "ingestion_pipeline_tile_layer_enabled", True)
    future_exp = int((datetime.now(UTC) + timedelta(seconds=120)).timestamp())
    stats_url = f"https://ingestion.internal/stats?sig=SIGNED&exp={future_exp}"
    tile_url = "https://ingestion.internal/tiles/{z}/{x}/{y}.png?sig=SIGNED"
    created: list[dict[str, Any]] = []
    _install_stats_client(monkeypatch, _available_with(stats_url, tile_url), created)

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={"sourceId": SENTINEL, "indexType": "NDVI", "acquisitionDate": "2026-01-15"},
    )
    assert r.status_code == 200
    pipeline = r.json()["metadata"]["pipeline"]
    assert pipeline["statsUrl"].startswith("/api/pipeline/field-index/stats?proxyId=")
    assert "tileUrl" not in pipeline
    assert [c["operation"] for c in created] == ["stats"]
    assert "ingestion.internal" not in r.text
    assert "sig=" not in r.text


def _plot() -> dict[str, Any]:
    return {
        "id": "field-1",
        "name": "Field 1",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]],
        },
        "areaHa": 3.0,
    }
