"""Account, team, API-key, notifications, and assistant shell routes."""
from __future__ import annotations

import functools
import logging
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import Field

from .auth import (
    CurrentTeam,
    CurrentUser,
    get_current_team,
    get_current_user,
    hash_secret,
    new_api_key,
)
from .providers.models import ProviderModel
from .raster.errors import AkashaError, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.account")
router = APIRouter(prefix="/api", tags=["account"])

_api_keys: list[dict[str, Any]] = []
_notifications: list[dict[str, Any]] = []


class AccountMe(ProviderModel):
    user: dict[str, Any]
    current_team: dict[str, Any]
    memberships: list[dict[str, Any]]
    auth_mode: str = "dev"


class ApiKeyCreate(ProviderModel):
    name: str


class ApiKeyPublic(ProviderModel):
    id: str
    name: str
    prefix: str
    last4: str
    created_at: str
    revoked_at: str | None = None
    raw_key: str | None = None


class Notification(ProviderModel):
    id: str
    type: Literal[
        "field_change",
        "risk_alert",
        "task_assignment",
        "report_available",
        "provider_sync_failure",
    ]
    title: str
    body: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    read_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AssistantStatus(ProviderModel):
    status: Literal["disabled"] = "disabled"
    message: str
    evidence_sources: list[str]
    limitations: list[str]


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("account backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Account storage is not available.") from exc


@router.get("/account/me", response_model=AccountMe, response_model_by_alias=True)
async def account_me(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> AccountMe:
    return AccountMe(
        user={"id": user.id, "email": user.email, "displayName": user.display_name},
        current_team={"id": team.id, "name": team.name, "role": team.role},
        memberships=[{"teamId": team.id, "teamName": team.name, "role": team.role}],
        auth_mode="dev" if user.id.startswith("00000000") else "enabled",
    )


@router.get("/teams", response_model=list[dict[str, Any]], response_model_by_alias=True)
async def list_teams(team: CurrentTeam = Depends(get_current_team)) -> list[dict[str, Any]]:
    return [{"id": team.id, "name": team.name, "role": team.role}]


@router.post("/teams/current", response_model=dict[str, Any], response_model_by_alias=True)
async def switch_team(team: CurrentTeam = Depends(get_current_team)) -> dict[str, Any]:
    return {"id": team.id, "name": team.name, "role": team.role}


@router.get("/account/settings", response_model=dict[str, Any], response_model_by_alias=True)
async def account_settings(team: CurrentTeam = Depends(get_current_team)) -> dict[str, Any]:
    return {"teamId": team.id, "safeLocalDev": team.id.startswith("00000000")}


@router.get(
    "/account/api-keys",
    response_model=list[ApiKeyPublic],
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def list_api_keys(team: CurrentTeam = Depends(get_current_team)) -> list[ApiKeyPublic]:
    return [
        ApiKeyPublic(**{k: v for k, v in item.items() if k not in {"keyHash", "rawKey"}})
        for item in _api_keys
        if item["teamId"] == team.id and not item.get("revokedAt")
    ]


@router.post(
    "/account/api-keys",
    response_model=ApiKeyPublic,
    response_model_by_alias=True,
    status_code=201,
)
async def create_api_key(
    payload: ApiKeyCreate,
    team: CurrentTeam = Depends(get_current_team),
) -> ApiKeyPublic:
    raw, prefix, last4 = new_api_key()
    item = {
        "id": str(len(_api_keys) + 1),
        "teamId": team.id,
        "name": payload.name,
        "prefix": prefix,
        "last4": last4,
        "keyHash": hash_secret(raw),
        "createdAt": "2026-06-04T00:00:00Z",
    }
    _api_keys.append(item)
    return ApiKeyPublic(**{k: v for k, v in item.items() if k != "keyHash"}, rawKey=raw)


@router.delete("/account/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, team: CurrentTeam = Depends(get_current_team)) -> Response:
    for item in _api_keys:
        if item["id"] == key_id and item["teamId"] == team.id:
            item["revokedAt"] = "2026-06-04T00:00:00Z"
            return Response(status_code=204)
    raise not_found("API key not found.", code="API_KEY_NOT_FOUND", keyId=key_id)


@router.get("/notifications", response_model=list[Notification], response_model_by_alias=True)
async def list_notifications(
    unreadOnly: bool = False,
    team: CurrentTeam = Depends(get_current_team),
) -> list[Notification]:
    items = [item for item in _notifications if item["teamId"] == team.id]
    if unreadOnly:
        items = [item for item in items if not item.get("readAt")]
    return [Notification(**{k: v for k, v in item.items() if k != "teamId"}) for item in items]


@router.get(
    "/notifications/unread-count",
    response_model=dict[str, int],
    response_model_by_alias=True,
)
async def unread_count(team: CurrentTeam = Depends(get_current_team)) -> dict[str, int]:
    return {
        "unreadCount": sum(
            1 for item in _notifications if item["teamId"] == team.id and not item.get("readAt")
        )
    }


@router.post(
    "/notifications/{notification_id}/read",
    response_model=Notification,
    response_model_by_alias=True,
)
async def mark_notification_read(
    notification_id: str,
    team: CurrentTeam = Depends(get_current_team),
) -> Notification:
    for item in _notifications:
        if item["id"] == notification_id and item["teamId"] == team.id:
            item["readAt"] = "2026-06-04T00:00:00Z"
            return Notification(**{k: v for k, v in item.items() if k != "teamId"})
    raise not_found(
        "Notification not found.",
        code="NOTIFICATION_NOT_FOUND",
        notificationId=notification_id,
    )


@router.post("/notifications/read-all", response_model=dict[str, int], response_model_by_alias=True)
async def mark_all_notifications_read(
    team: CurrentTeam = Depends(get_current_team),
) -> dict[str, int]:
    changed = 0
    for item in _notifications:
        if item["teamId"] == team.id and not item.get("readAt"):
            item["readAt"] = "2026-06-04T00:00:00Z"
            changed += 1
    return {"updatedCount": changed}


@router.get("/assistant/status", response_model=AssistantStatus, response_model_by_alias=True)
async def assistant_status(_: CurrentTeam = Depends(get_current_team)) -> AssistantStatus:
    return AssistantStatus(
        message="Assistant shell is disabled until evidence-only summarization is configured.",
        evidence_sources=["fields", "analytics", "weather", "risk", "operations"],
        limitations=[
            "No external LLM is called in Phase 12.",
            "The assistant must not invent agronomic advice.",
        ],
    )
