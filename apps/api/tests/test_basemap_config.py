"""ArcGIS basemap usage-model configuration contracts."""

from __future__ import annotations

import pytest
from app.config import Settings, settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_basemap_usage_model_defaults_to_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ESRI_BASEMAP_USAGE_MODEL", raising=False)

    configured = Settings()

    assert configured.esri_basemap_usage_model == "session"


def test_basemap_usage_model_accepts_and_normalizes_tile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESRI_BASEMAP_USAGE_MODEL", "  TiLe  ")

    configured = Settings()

    assert configured.esri_basemap_usage_model == "tile"


def test_basemap_usage_model_rejects_unsupported_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESRI_BASEMAP_USAGE_MODEL", "per-request")

    with pytest.raises(
        RuntimeError,
        match="ESRI_BASEMAP_USAGE_MODEL must be one of: session, tile",
    ):
        Settings()


def test_config_endpoint_reports_tile_usage_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "esri_basemap_usage_model", "tile")

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["basemap"]["usageModel"] == "tile"
