"""Account, team, API-key, notifications, and assistant shell routes."""

from __future__ import annotations

import functools
import logging
from datetime import UTC, datetime
from typing import Any

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth import (
    CurrentTeam,
    CurrentUser,
    get_current_team,
    get_current_user,
    hash_secret,
    new_api_key,
    require_role,
)
from ..optical_cloud import optical_cloud_threshold, set_optical_cloud_threshold
from ..raster.errors import AkashaError, not_found, plots_backend_unavailable
from ..repositories import account_repo, auth_repo
from ..schemas.account import (
    AccountMe,
    AccountSettingsUpdate,
    ApiKeyCreate,
    ApiKeyPublic,
    AssistantStatus,
    Notification,
)

logger = logging.getLogger("akasha.api.account")
router = APIRouter(prefix="/api", tags=["account"])

# Local disabled-auth preview storage. Enabled auth uses Postgres.
_api_keys: list[dict[str, Any]] = []
_notifications: list[dict[str, Any]] = []


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("account backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Account storage is not available.") from exc


def _use_preview_storage(team: CurrentTeam) -> bool:
    return team.id.startswith("00000000")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@router.get("/account/me", response_model=AccountMe, response_model_by_alias=True)
async def account_me(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> AccountMe:
    return AccountMe(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "displayName": user.display_name,
            "onboardingCompleted": user.onboarding_completed,
        },
        current_team={"id": team.id, "name": team.name, "role": team.role},
        memberships=[
            {"teamId": item.id, "teamName": item.name, "role": item.role}
            for item in (user.memberships or ())
        ],
        auth_mode="dev" if user.id.startswith("00000000") else "enabled",
    )


@router.post("/account/onboarding-complete", response_model=AccountMe, response_model_by_alias=True)
async def complete_onboarding(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> AccountMe:
    if not user.id.startswith("00000000"):
        await _run_blocking(auth_repo.mark_onboarding_completed, user.id)
    return AccountMe(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "displayName": user.display_name,
            "onboardingCompleted": True,
        },
        current_team={"id": team.id, "name": team.name, "role": team.role},
        memberships=[
            {"teamId": item.id, "teamName": item.name, "role": item.role}
            for item in (user.memberships or ())
        ],
        auth_mode="dev" if user.id.startswith("00000000") else "enabled",
    )


@router.get("/teams", response_model=list[dict[str, Any]], response_model_by_alias=True)
async def list_teams(team: CurrentTeam = Depends(get_current_team)) -> list[dict[str, Any]]:
    return [{"id": team.id, "name": team.name, "role": team.role}]


@router.post("/teams/current", response_model=dict[str, Any], response_model_by_alias=True)
async def switch_team(team: CurrentTeam = Depends(get_current_team)) -> dict[str, Any]:
    return {"id": team.id, "name": team.name, "role": team.role}


@router.get("/account/settings", response_model=dict[str, Any], response_model_by_alias=True)
async def account_settings(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> dict[str, Any]:
    return {
        "teamId": team.id,
        "safeLocalDev": team.id.startswith("00000000"),
        "opticalCloudThresholdPercent": optical_cloud_threshold(user),
    }


@router.patch("/account/settings", response_model=dict[str, Any], response_model_by_alias=True)
async def update_account_settings(
    payload: AccountSettingsUpdate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> dict[str, Any]:
    threshold = payload.optical_cloud_threshold_percent
    if _use_preview_storage(team):
        # Disabled-auth local preview mode has no persisted user row. Keep its
        # preference process-local, while authenticated deployments always read
        # the database-backed value from the session context.
        set_optical_cloud_threshold(user.id, threshold)
    else:
        changed = await _run_blocking(
            auth_repo.update_optical_cloud_threshold,
            user.id,
            threshold,
        )
        if not changed:
            raise not_found("User not found.", code="USER_NOT_FOUND")
    return {
        "teamId": team.id,
        "safeLocalDev": team.id.startswith("00000000"),
        "opticalCloudThresholdPercent": threshold,
    }


@router.get(
    "/account/api-keys",
    response_model=list[ApiKeyPublic],
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def list_api_keys(team: CurrentTeam = Depends(get_current_team)) -> list[ApiKeyPublic]:
    if not _use_preview_storage(team):
        rows = await _run_blocking(account_repo.list_api_keys, team.id)
        return [ApiKeyPublic(**row) for row in rows]
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
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin")),
) -> ApiKeyPublic:
    raw, prefix, last4 = new_api_key()
    if not _use_preview_storage(team):
        row = await _run_blocking(
            account_repo.create_api_key,
            team_id=team.id,
            user_id=user.id,
            name=payload.name,
            key_hash=hash_secret(raw),
            prefix=prefix,
            last4=last4,
        )
        return ApiKeyPublic(**row, rawKey=raw)
    item = {
        "id": str(len(_api_keys) + 1),
        "teamId": team.id,
        "name": payload.name,
        "prefix": prefix,
        "last4": last4,
        "keyHash": hash_secret(raw),
        "createdAt": _now_iso(),
    }
    _api_keys.append(item)
    return ApiKeyPublic(**{k: v for k, v in item.items() if k != "keyHash"}, rawKey=raw)


@router.delete("/account/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    team: CurrentTeam = Depends(require_role("owner", "admin")),
) -> Response:
    if not _use_preview_storage(team):
        changed = await _run_blocking(
            account_repo.revoke_api_key,
            team_id=team.id,
            key_id=key_id,
        )
        if changed:
            return Response(status_code=204)
        raise not_found("API key not found.", code="API_KEY_NOT_FOUND", keyId=key_id)
    for item in _api_keys:
        if item["id"] == key_id and item["teamId"] == team.id:
            item["revokedAt"] = _now_iso()
            return Response(status_code=204)
    raise not_found("API key not found.", code="API_KEY_NOT_FOUND", keyId=key_id)


@router.get("/notifications", response_model=list[Notification], response_model_by_alias=True)
async def list_notifications(
    unreadOnly: bool = False,
    team: CurrentTeam = Depends(get_current_team),
) -> list[Notification]:
    if not _use_preview_storage(team):
        rows = await _run_blocking(
            account_repo.list_notifications,
            team_id=team.id,
            unread_only=unreadOnly,
        )
        return [Notification(**row) for row in rows]
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
    if not _use_preview_storage(team):
        count = await _run_blocking(account_repo.unread_notification_count, team.id)
        return {"unreadCount": count}
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
    if not _use_preview_storage(team):
        item = await _run_blocking(
            account_repo.mark_notification_read,
            team_id=team.id,
            notification_id=notification_id,
        )
        if item:
            return Notification(**item)
        raise not_found(
            "Notification not found.",
            code="NOTIFICATION_NOT_FOUND",
            notificationId=notification_id,
        )
    for item in _notifications:
        if item["id"] == notification_id and item["teamId"] == team.id:
            item["readAt"] = _now_iso()
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
    if not _use_preview_storage(team):
        changed = await _run_blocking(account_repo.mark_all_notifications_read, team.id)
        return {"updatedCount": changed}
    changed = 0
    for item in _notifications:
        if item["teamId"] == team.id and not item.get("readAt"):
            item["readAt"] = _now_iso()
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
