from __future__ import annotations

import argparse
import json
import urllib.request

from app import cli
from app.config import settings


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def _configure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_api_url", "http://secret-ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_aoi_id", "bangalore_60km_geodesic_aoi")
    monkeypatch.setenv("INGESTION_SIGNED_URL_ALLOWED_PREFIX", "http://10.10.2.4:18080")
    monkeypatch.setattr(settings, "ingestion_signed_url_allowed_prefix", "http://10.10.2.4:18080")
    monkeypatch.setattr(
        settings,
        "ingestion_signed_url_fetch_prefix",
        "http://host.docker.internal:18081",
    )


def test_ingestion_check_success_does_not_print_secrets(monkeypatch, capsys) -> None:
    _configure(monkeypatch)
    requested: list[str] = []

    def fake_urlopen(request, timeout):
        requested.append(
            request.full_url if isinstance(request, urllib.request.Request) else str(request)
        )
        if requested[-1].endswith("/health"):
            return FakeResponse(b'{"status":"ok"}')
        return FakeResponse(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "availableDates": ["2026-03-20"],
                        "tileUrl": "http://10.10.2.4:18080/x?sig=secret&kid=k&exp=1",
                    },
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.cmd_ingestion_check(argparse.Namespace()) == 0
    output = capsys.readouterr().out

    assert "Remote ingestion bridge check passed." in output
    assert "SECRET_API_KEY" not in output
    assert "secret-ingestion" not in output
    assert "10.10.2.4" not in output
    assert "sig=secret" not in output


def test_ingestion_check_incomplete_config_does_not_print_secret(monkeypatch, capsys) -> None:
    _configure(monkeypatch)
    monkeypatch.delenv("INGESTION_SIGNED_URL_ALLOWED_PREFIX", raising=False)
    monkeypatch.setattr(settings, "ingestion_signed_url_allowed_prefix", "")

    assert cli.cmd_ingestion_check(argparse.Namespace()) == 1
    output = capsys.readouterr().out

    assert "Bridge configuration is incomplete." in output
    assert "SECRET_API_KEY" not in output
    assert "secret-ingestion" not in output
