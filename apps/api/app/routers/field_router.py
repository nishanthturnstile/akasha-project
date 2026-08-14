"""Akasha BFF Field API."""

from __future__ import annotations

import functools
import logging
from typing import Any

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError

from ..api_models import ApiModel
from ..auth import (
    CurrentTeam,
    CurrentUser,
    get_current_team,
    get_current_user,
    require_role,
)
from ..raster.errors import AkashaError, bad_request, field_backend_unavailable, not_found
from ..repositories import fields_repo
from ..schemas.fields import (
    FieldCreate,
    FieldResponse,
    FieldUpdate,
    GrowthStageDateUpdateRequest,
    GrowthStageResponse,
    VegetationCycleResponse,
)

logger = logging.getLogger("akasha.api.fields")
router = APIRouter(prefix="/api", tags=["fields"], dependencies=[Depends(get_current_team)])

MAX_NAME_LENGTH = 100


def _validate_field_name(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        raise bad_request("Field name must not be blank.", code="INVALID_NAME")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise bad_request(
            f"Field name exceeds {MAX_NAME_LENGTH} characters.",
            code="INVALID_NAME",
        )
    return cleaned


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except IntegrityError as exc:
        logger.warning("fields storage integrity error: %s", exc.orig)
        raise AkashaError(
            "FIELD_STORAGE_CONFLICT",
            "Field storage rejected the request.",
            409,
        ) from exc
    except Exception as exc:
        logger.warning("fields backend unavailable: %s", type(exc).__name__)
        raise field_backend_unavailable(
            "Field storage is not available in this environment."
        ) from exc


@router.get("/fields", response_model=list[FieldResponse])
async def list_fields(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> list[dict[str, Any]]:
    return await _run_blocking(fields_repo.list_fields, user.id, team.id)


@router.post("/fields", response_model=FieldResponse, status_code=201)
async def create_field(
    payload: FieldCreate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    name = _validate_field_name(payload.name)
    veg_data = [v.model_dump(by_alias=True) for v in payload.vegetationData]
    return await _run_blocking(
        fields_repo.create_field,
        user.id,
        name,
        payload.geometry,
        payload.areaHa,
        payload.groupId,
        payload.seasonIds,
        veg_data,
        team_id=team.id,
        district=payload.district,
        country=payload.country,
    )


@router.get("/fields/{field_id}", response_model=FieldResponse)
async def get_field(
    field_id: str,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> dict[str, Any]:
    field = await _run_blocking(fields_repo.get_field, field_id, user.id, team.id)
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


@router.get("/fields/{field_id}/vegetation-cycles", response_model=list[VegetationCycleResponse])
async def list_vegetation_cycles(
    field_id: str,
    season_id: str,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> list[dict[str, Any]]:
    return await _run_blocking(
        fields_repo.list_vegetation_cycles,
        field_id,
        user.id,
        season_id,
        team.id,
    )


@router.patch(
    "/vegetation-cycles/{cycle_id}/growth-stages",
    response_model=list[GrowthStageResponse],
)
async def update_growth_stages(
    cycle_id: str,
    payload: GrowthStageDateUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> list[dict[str, Any]]:
    stages = [stage.model_dump(by_alias=True) for stage in payload.stages]
    result = await _run_blocking(
        fields_repo.update_vegetation_cycle_growth_stages,
        cycle_id,
        user.id,
        stages,
        team.id,
    )
    if result is None:
        raise not_found(
            "Vegetation cycle not found.",
            code="VEGETATION_CYCLE_NOT_FOUND",
            cycleId=cycle_id,
        )
    return result


@router.patch("/fields/{field_id}", response_model=FieldResponse)
async def update_field(
    field_id: str,
    payload: FieldUpdate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    if "name" in data:
        data["name"] = _validate_field_name(data["name"])
    field = await _run_blocking(
        fields_repo.update_field,
        field_id,
        user.id,
        team_id=team.id,
        **data,
    )
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(
    field_id: str,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> Response:
    deleted = await _run_blocking(fields_repo.delete_field, field_id, user.id, team.id)
    if not deleted:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return Response(status_code=204)


class NextFieldNameResponse(ApiModel):
    name: str


@router.get("/fields/next-name", response_model=NextFieldNameResponse)
async def next_field_name(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    num = await _run_blocking(fields_repo.get_next_field_number, user.id)
    return {"name": f"Field {num}"}
