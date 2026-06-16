"""Field group routes for Phase 10."""

from __future__ import annotations

import functools
import logging

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth import CurrentTeam, CurrentUser, get_current_team, get_current_user, require_role
from ..raster.errors import AkashaError, not_found, plots_backend_unavailable
from ..repositories import phase10_repo
from ..schemas.field_groups import FieldAssignmentPayload, FieldGroup, FieldGroupPayload

logger = logging.getLogger("akasha.api.field_groups")
router = APIRouter(
    prefix="/api",
    tags=["field-groups"],
    dependencies=[Depends(get_current_team)],
)


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field groups backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Field group storage is not available.") from exc


@router.get("/field-groups", response_model=list[FieldGroup], response_model_by_alias=True)
async def list_field_groups(team: CurrentTeam = Depends(get_current_team)) -> list[FieldGroup]:
    rows = await _run_blocking(phase10_repo.list_field_groups, team.id)
    return [FieldGroup(**row) for row in rows]


@router.post(
    "/field-groups",
    response_model=FieldGroup,
    response_model_by_alias=True,
    status_code=201,
)
async def create_field_group(
    payload: FieldGroupPayload,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> FieldGroup:
    data = payload.model_dump(by_alias=True)
    data["ownerId"] = user.id
    data["teamId"] = team.id
    row = await _run_blocking(phase10_repo.create_field_group, data)
    return FieldGroup(**row)


@router.patch("/field-groups/{group_id}", response_model=FieldGroup, response_model_by_alias=True)
async def update_field_group(
    group_id: str,
    payload: FieldGroupPayload,
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> FieldGroup:
    row = await _run_blocking(
        phase10_repo.update_field_group,
        group_id,
        payload.model_dump(by_alias=True, exclude_unset=True),
        team.id,
    )
    if row is None:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return FieldGroup(**row)


@router.delete("/field-groups/{group_id}", status_code=204)
async def delete_field_group(
    group_id: str,
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> Response:
    deleted = await _run_blocking(phase10_repo.delete_field_group, group_id, team.id)
    if not deleted:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return Response(status_code=204)


@router.post(
    "/field-groups/{group_id}/fields",
    response_model=FieldGroup,
    response_model_by_alias=True,
)
async def assign_field_group(
    group_id: str,
    payload: FieldAssignmentPayload,
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> FieldGroup:
    row = await _run_blocking(
        phase10_repo.assign_group_fields,
        group_id,
        payload.plot_ids,
        team.id,
    )
    if row is None:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return FieldGroup(**row)
