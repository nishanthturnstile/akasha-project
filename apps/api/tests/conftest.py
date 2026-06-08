from __future__ import annotations

import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def _allow_local_disabled_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "test")
    for key in (
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)
