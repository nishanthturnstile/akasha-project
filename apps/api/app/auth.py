"""Phase 12 auth/team dependency foundations."""
from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass

from fastapi import Depends

from .config import settings
from .raster.errors import AkashaError

DEV_USER_ID = "00000000-0000-4000-8000-000000000001"
DEV_TEAM_ID = "00000000-0000-4000-8000-000000000010"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    role: str = "owner"


@dataclass(frozen=True)
class CurrentTeam:
    id: str
    name: str
    role: str = "owner"


def deployment_auth_required() -> bool:
    return any(
        os.environ.get(name)
        for name in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_PUBLIC_DOMAIN",
        )
    )


def _auth_disabled_allowed() -> bool:
    return (
        settings.app_env.lower() in {"development", "local", "test"}
        and not deployment_auth_required()
    )


def unauthorized(message: str = "Authentication required.") -> AkashaError:
    return AkashaError("UNAUTHORIZED", message, 401)


def forbidden(message: str = "Insufficient role for this action.") -> AkashaError:
    return AkashaError("FORBIDDEN", message, 403)


def auth_not_configured() -> AkashaError:
    return AkashaError(
        "AUTH_NOT_CONFIGURED",
        "Authentication must be enabled for this deployment.",
        503,
    )


def get_current_user() -> CurrentUser:
    mode = settings.auth_mode.strip().lower()
    if mode == "disabled":
        if not _auth_disabled_allowed():
            raise auth_not_configured()
        return CurrentUser(
            id=DEV_USER_ID,
            email=settings.auth_dev_user_email,
            display_name="Akasha Dev User",
        )
    raise unauthorized("Session validation is not configured in this Phase 12 shell.")


def get_current_team(user: CurrentUser = Depends(get_current_user)) -> CurrentTeam:
    return CurrentTeam(id=DEV_TEAM_ID, name=settings.auth_dev_team_name, role=user.role)


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
