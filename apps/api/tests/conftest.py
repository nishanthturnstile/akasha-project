from __future__ import annotations

import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def _allow_local_disabled_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "test")
    for key in (
        "AKASHA_DEPLOYMENT",
        "COOLIFY_URL",
        "COOLIFY_FQDN",
        "COOLIFY_RESOURCE_UUID",
        "COOLIFY_CONTAINER_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
