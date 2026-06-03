"""Phase 12 auth/team/admin/notifications tests."""
from __future__ import annotations

from app import account
from app.auth import get_current_user
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_dev_auth_me_and_api_keys_do_not_leak_hash(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "app_env", "development")
    for key in (
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)
    account._api_keys.clear()

    me = client.get("/api/account/me")
    assert me.status_code == 200
    assert me.json()["authMode"] == "dev"
    assert "password_hash" not in me.text

    created = client.post("/api/account/api-keys", json={"name": "Demo"})
    assert created.status_code == 201
    assert created.json()["rawKey"].startswith("akasha_")
    listed = client.get("/api/account/api-keys")
    assert listed.status_code == 200
    assert "rawKey" not in listed.text
    assert "keyHash" not in listed.text


def test_disabled_auth_fails_closed_on_railway(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    try:
        get_current_user()
    except Exception as exc:  # noqa: BLE001
        payload = exc.to_payload()
        assert payload["error"]["code"] == "AUTH_NOT_CONFIGURED"
        assert exc.status_code == 503
    else:  # pragma: no cover
        raise AssertionError("expected auth failure")


def test_protected_domain_routes_fail_closed_on_railway(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    r = client.get("/api/field-groups")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_notifications_and_assistant_shell(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "app_env", "development")
    account._notifications.clear()
    account._notifications.append(
        {
            "id": "note-1",
            "teamId": "00000000-0000-4000-8000-000000000010",
            "type": "task_assignment",
            "title": "Scout task assigned",
            "body": "Check field",
            "metadata": {"safe": True},
            "createdAt": "2026-06-04T00:00:00Z",
            "readAt": None,
        }
    )

    listed = client.get("/api/notifications")
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "Scout task assigned"
    count = client.get("/api/notifications/unread-count")
    assert count.json()["unreadCount"] == 1
    marked = client.post("/api/notifications/note-1/read")
    assert marked.status_code == 200
    assert marked.json()["readAt"] is not None

    assistant = client.get("/api/assistant/status")
    assert assistant.status_code == 200
    assert assistant.json()["status"] == "disabled"
    assert "agronomic advice" in " ".join(assistant.json()["limitations"])
