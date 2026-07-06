from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest
from app.config import Settings
from app.ingestion_client import (
    _FIELD_INDEX_POINT_CACHE,
    fetch_signed_ingestion_binary,
    fetch_signed_ingestion_json,
    is_ingestion_configured,
    request_field_index_point,
)
from app.raster.errors import AkashaError


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def _settings() -> Settings:
    return Settings(
        ingestion_api_url="https://private-ingestion.example",
        ingestion_api_key="super-secret-key",
        ingestion_signed_url_allowed_prefix="https://public-ingestion.example",
        ingestion_signed_url_fetch_prefix="http://host.docker.internal:18081",
    )


def test_is_ingestion_configured_requires_url_and_key() -> None:
    assert not is_ingestion_configured(Settings(ingestion_api_url="", ingestion_api_key=""))
    assert not is_ingestion_configured(Settings(ingestion_api_url="http://x", ingestion_api_key=""))
    assert is_ingestion_configured(Settings(ingestion_api_url="http://x", ingestion_api_key="k"))


def test_signed_binary_fetch_uses_prefix_slice_rewrite(monkeypatch) -> None:
    calls: list[str] = []

    def fake_urlopen(url, timeout):
        calls.append(str(url))
        assert timeout == _settings().ingestion_request_timeout_seconds
        return FakeResponse(b"PNG", headers={"Content-Type": "image/png"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    body, content_type, headers = fetch_signed_ingestion_binary(
        _settings(),
        "https://public-ingestion.example/api/v1/overlay/q.png?sig=abc&kid=k1&exp=9",
    )

    assert body == b"PNG"
    assert content_type == "image/png"
    assert headers["Content-Type"] == "image/png"
    assert calls == ["http://host.docker.internal:18081/api/v1/overlay/q.png?sig=abc&kid=k1&exp=9"]


def test_signed_json_fetch_uses_same_rewrite_helper(monkeypatch) -> None:
    calls: list[str] = []

    def fake_urlopen(url, timeout):
        calls.append(str(url))
        return FakeResponse(json.dumps({"value": 0.4}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    body = fetch_signed_ingestion_json(
        _settings(),
        "https://public-ingestion.example/api/v1/point/q?sig=abc",
    )

    assert body == {"value": 0.4}
    assert calls == ["http://host.docker.internal:18081/api/v1/point/q?sig=abc"]


def test_signed_fetch_rejects_unexpected_prefix() -> None:
    with pytest.raises(AkashaError) as exc:
        fetch_signed_ingestion_binary(
            _settings(),
            "https://evil.example/api/v1/overlay/q.png?sig=abc",
        )

    assert exc.value.code == "INGESTION_UPSTREAM_FORBIDDEN"


def test_signed_fetch_error_payload_redacts_url_and_secret(monkeypatch) -> None:
    def fake_urlopen(url, timeout):
        raise urllib.error.HTTPError(
            str(url),
            500,
            "boom",
            {},
            io.BytesIO(b'{"error":{"message":"bad"}}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(AkashaError) as exc:
        fetch_signed_ingestion_binary(
            _settings(),
            "https://public-ingestion.example/api/v1/overlay/q.png?sig=abc&kid=k1&exp=9",
        )

    payload = json.dumps(exc.value.to_payload())
    assert exc.value.code == "INGESTION_OVERLAY_FETCH_FAILED"
    assert "super-secret-key" not in payload
    assert "sig=abc" not in payload
    assert "public-ingestion" not in payload


def test_point_lookup_reuses_cached_field_index_query(monkeypatch) -> None:
    import app.ingestion_client as client_module

    _FIELD_INDEX_POINT_CACHE.clear()
    field_index_calls: list[str] = []
    fetch_urls: list[str] = []

    def fake_field_index(*_args, **kwargs):
        field_index_calls.append(kwargs["acquisition_date"])
        return {
            "status": "AVAILABLE",
            "queryId": "q-1",
            "pointUrl": "https://public-ingestion.example/api/v1/point/q-1?sig=s&kid=k&exp=1",
        }

    def fake_fetch(_settings, url: str):
        fetch_urls.append(url)
        return {
            "queryId": "q-1",
            "index": "NDVI",
            "lng": 77.1,
            "lat": 12.1,
            "value": 0.31,
            "masked": False,
            "maskClass": 1,
        }

    monkeypatch.setattr(client_module, "request_field_index", fake_field_index)
    monkeypatch.setattr(client_module, "fetch_signed_ingestion_json", fake_fetch)

    kwargs = {
        "geometry": {"type": "Polygon", "coordinates": []},
        "field_id": "field-1",
        "source_id": "sentinel-2-l2a",
        "index_type": "NDVI",
        "acquisition_date": "2026-03-20",
        "lng": 77.1,
        "lat": 12.1,
    }
    first = request_field_index_point(_settings(), **kwargs)
    second = request_field_index_point(_settings(), **kwargs)

    assert first["value"] == second["value"] == 0.31
    assert field_index_calls == ["2026-03-20"]
    assert len(fetch_urls) == 2
    assert all("lng=77.1" in url and "lat=12.1" in url for url in fetch_urls)
