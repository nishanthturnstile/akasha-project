"""Phase 12 auth/team dependency foundations."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, Response

from .config import settings
from .raster.errors import AkashaError

DEV_USER_ID = "00000000-0000-4000-8000-000000000001"
DEV_TEAM_ID = "00000000-0000-4000-8000-000000000010"
LOCAL_AUTH_ENVS = {"development", "local", "test"}


@dataclass(frozen=True)
class TeamMembership:
    id: str
    name: str
    role: str


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    username: str | None = None
    role: str = "owner"
    current_team_id: str | None = None
    session_token_hash: str | None = None
    session_remember_me: bool = False
    memberships: tuple[TeamMembership, ...] = ()


@dataclass(frozen=True)
class CurrentTeam:
    id: str
    name: str
    role: str = "owner"


def deployment_auth_required() -> bool:
    # Independent "we are really deployed" signal that auth cannot be disabled
    # on a hosted deployment even if APP_ENV is misconfigured. The Coolify
    # control plane (self-hosted Azure VM) injects COOLIFY_* runtime variables;
    # operators on a bare Docker host can set AKASHA_DEPLOYMENT explicitly.
    return any(
        os.environ.get(name)
        for name in (
            "AKASHA_DEPLOYMENT",
            "COOLIFY_URL",
            "COOLIFY_FQDN",
            "COOLIFY_RESOURCE_UUID",
            "COOLIFY_CONTAINER_NAME",
        )
    )


def _auth_disabled_allowed() -> bool:
    return (
        settings.auth_allow_disabled
        and settings.app_env.lower() in LOCAL_AUTH_ENVS
        and not deployment_auth_required()
    )


def is_local_auth_env() -> bool:
    return settings.app_env.lower() in LOCAL_AUTH_ENVS and not deployment_auth_required()


def unauthorized(message: str = "Authentication required.") -> AkashaError:
    return AkashaError("UNAUTHORIZED", message, 401)


def forbidden(message: str = "Insufficient role for this action.") -> AkashaError:
    return AkashaError("FORBIDDEN", message, 403)


def auth_not_configured(
    message: str = "Authentication must be enabled for this deployment.",
) -> AkashaError:
    return AkashaError(
        "AUTH_NOT_CONFIGURED",
        message,
        503,
    )


def auth_backend_unavailable() -> AkashaError:
    return AkashaError(
        "AUTH_BACKEND_UNAVAILABLE",
        "Authentication storage is not available.",
        503,
    )


def invalid_credentials() -> AkashaError:
    return AkashaError("INVALID_CREDENTIALS", "Invalid username or password.", 401)


def ensure_auth_enabled_configured() -> None:
    if settings.auth_mode.strip().lower() != "enabled":
        raise auth_not_configured()
    if not settings.auth_password_pepper.strip():
        raise auth_not_configured("Authentication secret is not configured.")


def auth_password_pepper() -> str:
    pepper = settings.auth_password_pepper.strip()
    if not pepper:
        raise auth_not_configured("Authentication secret is not configured.")
    return pepper


def hash_token(value: str) -> str:
    pepper = auth_password_pepper().encode("utf-8")
    digest = hmac.new(pepper, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def hash_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return "sess_" + secrets.token_urlsafe(32)


def session_expires_at(*, remember: bool = False) -> datetime:
    if remember:
        return datetime.now(UTC) + timedelta(days=settings.auth_remember_ttl_days)
    return datetime.now(UTC) + timedelta(minutes=settings.auth_session_ttl_minutes)


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        settings.auth_session_cookie_name,
        token,
        max_age=max_age,
        expires=expires_at,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.auth_session_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _dev_membership() -> TeamMembership:
    return TeamMembership(id=DEV_TEAM_ID, name=settings.auth_dev_team_name, role="owner")


def _dev_user() -> CurrentUser:
    membership = _dev_membership()
    return CurrentUser(
        id=DEV_USER_ID,
        email=settings.auth_dev_user_email,
        display_name="Akasha Dev User",
        username="dev",
        role=membership.role,
        current_team_id=membership.id,
        memberships=(membership,),
    )


def get_current_user(request: Request) -> CurrentUser:
    mode = settings.auth_mode.strip().lower()
    if mode == "disabled":
        if not _auth_disabled_allowed():
            raise auth_not_configured()
        return _dev_user()
    ensure_auth_enabled_configured()
    if request is None:
        raise unauthorized()
    raw_token = request.cookies.get(settings.auth_session_cookie_name)
    if not raw_token:
        raise unauthorized()
    token_hash = hash_token(raw_token)
    try:
        from .repositories import auth_repo  # noqa: PLC0415

        context = auth_repo.get_session_context(token_hash)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise auth_backend_unavailable() from exc
    if context is None:
        raise unauthorized()
    memberships = tuple(
        TeamMembership(id=item["id"], name=item["name"], role=item["role"])
        for item in context["memberships"]
    )
    if not memberships:
        raise forbidden("No team membership is available for this user.")
    user = context["user"]
    team_id = context.get("teamId")
    selected = next((m for m in memberships if m.id == team_id), memberships[0])
    return CurrentUser(
        id=user["id"],
        email=user["email"],
        display_name=user["displayName"],
        username=user.get("username"),
        role=selected.role,
        current_team_id=selected.id,
        session_token_hash=token_hash,
        session_remember_me=bool(context.get("rememberMe", False)),
        memberships=memberships,
    )


def get_current_team(user: CurrentUser = Depends(get_current_user)) -> CurrentTeam:
    membership = next(
        (item for item in user.memberships if item.id == user.current_team_id),
        user.memberships[0] if user.memberships else _dev_membership(),
    )
    return CurrentTeam(id=membership.id, name=membership.name, role=membership.role)


def require_role(*roles: str):
    def _dependency(team: CurrentTeam = Depends(get_current_team)) -> CurrentTeam:
        if team.role not in roles:
            raise forbidden()
        return team

    return _dependency


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    raw = "akasha_" + secrets.token_urlsafe(24)
    return raw, raw[:12], raw[-4:]
