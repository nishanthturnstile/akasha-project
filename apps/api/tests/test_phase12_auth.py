"""Phase 12 auth/team/admin/notifications tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.routers import account_router as account, auth_router as auth_routes
from app.auth import CurrentUser, TeamMembership, get_current_user
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_dev_auth_me_and_api_keys_do_not_leak_hash(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    for key in (
        "AKASHA_DEPLOYMENT",
        "COOLIFY_URL",
        "COOLIFY_FQDN",
        "COOLIFY_RESOURCE_UUID",
        "COOLIFY_CONTAINER_NAME",
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


def test_disabled_auth_fails_closed_on_deployment(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("AKASHA_DEPLOYMENT", "production")

    try:
        get_current_user(None)
    except Exception as exc:  # noqa: BLE001
        payload = exc.to_payload()
        assert payload["error"]["code"] == "AUTH_NOT_CONFIGURED"
        assert exc.status_code == 503
    else:  # pragma: no cover
        raise AssertionError("expected auth failure")


def test_protected_domain_routes_fail_closed_on_deployment(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("AKASHA_DEPLOYMENT", "production")

    r = client.get("/api/field-groups")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_product_routes_fail_closed_on_deployment(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("AKASHA_DEPLOYMENT", "production")

    r = client.get("/api/config")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_disabled_auth_requires_explicit_local_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", False)
    monkeypatch.setattr(settings, "app_env", "development")

    with pytest.raises(Exception) as exc_info:
        get_current_user(None)

    payload = exc_info.value.to_payload()
    assert payload["error"]["code"] == "AUTH_NOT_CONFIGURED"
    assert exc_info.value.status_code == 503


def test_notifications_and_assistant_shell(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
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


def test_login_sets_http_only_session_cookie(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "find_user_by_username",
        lambda username: {
            "id": "11111111-1111-4111-8111-111111111111",
            "username": username,
            "email": "owner@example.test",
            "displayName": "Owner",
            "status": "active",
            "passwordHash": "hash",
            "failedLoginCount": 0,
            "lockedUntil": None,
        },
    )
    monkeypatch.setattr(auth_routes, "verify_password", lambda password, password_hash: True)
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "memberships_for_user",
        lambda user_id: [
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "name": "Owner Team",
                "role": "owner",
            }
        ],
    )
    monkeypatch.setattr(auth_routes.auth_repo, "record_login_success", lambda user_id: None)
    created_sessions = []
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "create_session",
        lambda **kwargs: created_sessions.append(kwargs),
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "correct", "rememberMe": True},
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "owner"
    assert response.json()["currentTeam"]["role"] == "owner"
    assert created_sessions[0]["token_hash"]
    assert created_sessions[0]["remember_me"] is True
    cookie = response.headers["set-cookie"].lower()
    assert "akasha_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_login_bad_password_is_generic_and_records_failure(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "find_user_by_username",
        lambda username: {
            "id": "11111111-1111-4111-8111-111111111111",
            "username": username,
            "email": "owner@example.test",
            "displayName": "Owner",
            "status": "active",
            "passwordHash": "hash",
            "failedLoginCount": 0,
            "lockedUntil": None,
        },
    )
    monkeypatch.setattr(auth_routes, "verify_password", lambda password, password_hash: False)
    failures = []
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "record_login_failure",
        lambda user_id, locked_until=None: failures.append((user_id, locked_until)),
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "password" not in response.json()["error"]["message"].lower()
    assert failures[0][0] == "11111111-1111-4111-8111-111111111111"


def test_login_missing_user_runs_dummy_verify(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    auth_routes._AUTH_RATE_BUCKETS.clear()
    dummy_checks = []
    monkeypatch.setattr(auth_routes.auth_repo, "find_user_by_username", lambda username: None)
    monkeypatch.setattr(
        auth_routes,
        "_verify_dummy_password",
        lambda password: dummy_checks.append(password),
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert dummy_checks == ["wrong"]


def test_login_locked_user_still_verifies_password(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "find_user_by_username",
        lambda username: {
            "id": "11111111-1111-4111-8111-111111111111",
            "username": username,
            "email": "owner@example.test",
            "displayName": "Owner",
            "status": "active",
            "passwordHash": "hash",
            "failedLoginCount": 0,
            "lockedUntil": (datetime.now(UTC) + timedelta(minutes=10))
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )
    verifications = []
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        lambda password, password_hash: verifications.append((password, password_hash)) or False,
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert verifications == [("wrong", "hash")]


def test_login_rate_limit_is_coarse_per_client(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "auth_login_rate_limit_per_minute", 1)
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(auth_routes.auth_repo, "find_user_by_username", lambda username: None)
    monkeypatch.setattr(auth_routes, "_verify_dummy_password", lambda password: None)

    first = client.post("/api/auth/login", json={"username": "missing", "password": "wrong"})
    second = client.post("/api/auth/login", json={"username": "other", "password": "wrong"})

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_refresh_fails_if_session_rotation_did_not_persist(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    team_id = "22222222-2222-4222-8222-222222222222"
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="11111111-1111-4111-8111-111111111111",
        username="owner",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        current_team_id=team_id,
        session_token_hash="old-token-hash",
        memberships=(TeamMembership(id=team_id, name="Owner Team", role="owner"),),
    )
    monkeypatch.setattr(auth_routes.auth_repo, "rotate_session", lambda *args: False)

    try:
        response = client.post("/api/auth/refresh")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_refresh_preserves_remember_me_session_ttl(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "auth_session_ttl_minutes", 10)
    monkeypatch.setattr(settings, "auth_remember_ttl_days", 30)
    team_id = "22222222-2222-4222-8222-222222222222"
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="11111111-1111-4111-8111-111111111111",
        username="owner",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        current_team_id=team_id,
        session_token_hash="old-token-hash",
        session_remember_me=True,
        memberships=(TeamMembership(id=team_id, name="Owner Team", role="owner"),),
    )
    rotations = []
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "rotate_session",
        lambda old_hash, new_hash, expires_at: rotations.append(expires_at) or True,
    )

    try:
        response = client.post("/api/auth/refresh")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert rotations[0] > datetime.now(UTC) + timedelta(days=29)


def test_logout_clears_stale_cookie_without_valid_session(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_password_pepper", "")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)

    response = client.post("/api/auth/logout", cookies={settings.auth_session_cookie_name: "stale"})

    assert response.status_code == 204
    assert "akasha_session=" in response.headers["set-cookie"].lower()
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_bootstrap_requires_allow_flag_even_when_no_password_users(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_bootstrap", False)
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(auth_routes.auth_repo, "active_password_user_count", lambda: 0)

    response = client.post(
        "/api/auth/bootstrap",
        json={
            "username": "owner",
            "password": "correct horse battery staple",
            "email": "owner@example.test",
            "displayName": "Owner",
            "teamName": "Owner Team",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_bootstrap_requires_setup_token_in_deployment(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_allow_bootstrap", True)
    monkeypatch.setattr(settings, "auth_bootstrap_token", "setup-token")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "app_env", "production")
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(auth_routes.auth_repo, "active_password_user_count", lambda: 0)
    created = []
    monkeypatch.setattr(
        auth_routes.auth_repo,
        "create_user_with_team",
        lambda **kwargs: created.append(kwargs) or {"userId": "user-1", "teamId": "team-1"},
    )
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: "hashed-password")
    payload = {
        "username": "owner",
        "password": "correct horse battery staple",
        "email": "owner@example.test",
        "displayName": "Owner",
        "teamName": "Owner Team",
    }

    rejected = client.post("/api/auth/bootstrap", json=payload)
    accepted = client.post(
        "/api/auth/bootstrap",
        json={**payload, "bootstrapToken": "setup-token"},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json() == {"userId": "user-1", "teamId": "team-1"}
    assert created[0]["password_hash"] == "hashed-password"
    assert created[0]["require_no_password_users"] is True


def test_bootstrap_transaction_recheck_failure_returns_forbidden(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enabled")
    monkeypatch.setattr(settings, "auth_allow_bootstrap", True)
    monkeypatch.setattr(settings, "auth_bootstrap_token", "setup-token")
    monkeypatch.setattr(settings, "auth_password_pepper", "test-pepper")
    monkeypatch.setattr(settings, "app_env", "production")
    auth_routes._AUTH_RATE_BUCKETS.clear()
    monkeypatch.setattr(auth_routes.auth_repo, "active_password_user_count", lambda: 0)
    monkeypatch.setattr(auth_routes.auth_repo, "create_user_with_team", lambda **kwargs: None)
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: "hashed-password")

    response = client.post(
        "/api/auth/bootstrap",
        json={
            "username": "owner",
            "password": "correct horse battery staple",
            "email": "owner@example.test",
            "displayName": "Owner",
            "teamName": "Owner Team",
            "bootstrapToken": "setup-token",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_cors_wildcard_is_not_used_with_credentials(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setattr(settings, "app_env", "development")
    assert "*" not in settings.cors_allowed_origins

    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError):
        _ = settings.cors_allowed_origins


def test_dev_seed_alembic_baseline_uses_deterministic_auth_ids():
    baseline = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20260609_0001_fresh_orm_baseline.py"
    ).read_text()

    assert "DEV_USER_ID" in baseline
    assert "DEV_TEAM_ID" in baseline
    assert 'from app.auth import DEV_TEAM_ID, DEV_USER_ID' in baseline
