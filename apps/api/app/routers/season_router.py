"""Akasha BFF Season API (user-scoped seasons with canDelete lifecycle).

Endpoints:
  GET    /api/seasons
  POST   /api/seasons
  GET    /api/seasons/{season_id}
  PATCH  /api/seasons/{season_id}
  DELETE /api/seasons/{season_id}
"""

from __future__ import annotations

import functools
import logging
from typing import Any

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth import CurrentTeam, CurrentUser, get_current_team, get_current_user, require_role
from ..raster.errors import (
    AkashaError,
    bad_request,
    not_found,
    seasons_backend_unavailable,
)
from ..repositories import seasons_repo
from ..schemas.seasons import SeasonCreate, SeasonResponse, SeasonUpdate

logger = logging.getLogger("akasha.api.seasons")
router = APIRouter(
    prefix="/api",
    tags=["seasons"],
    dependencies=[Depends(get_current_team)],
)

MAX_NAME_LENGTH = 100


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:
        logger.warning("seasons backend unavailable: %s", type(exc).__name__)
        raise seasons_backend_unavailable(
            "Season storage is not available in this environment."
        ) from exc


@router.get(
    "/seasons",
    response_model=list[SeasonResponse],
    response_model_exclude_none=True,
)
async def list_seasons(
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> list[dict[str, Any]]:
    return await _run_blocking(seasons_repo.list_seasons, user.id)


@router.post(
    "/seasons",
    response_model=SeasonResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_season(
    payload: SeasonCreate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    return await _run_blocking(
        seasons_repo.create_season,
        user.id,
        payload.name,
        payload.start_date,
        payload.end_date,
        field_ids=payload.fieldIds,
    )


@router.get(
    "/seasons/{season_id}",
    response_model=SeasonResponse,
    response_model_exclude_none=True,
)
async def get_season(
    season_id: str,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> dict[str, Any]:
    season = await _run_blocking(seasons_repo.get_season, season_id, user.id)
    if season is None:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonId=season_id)
    if season["userId"] != user.id:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonId=season_id)
    return season


@router.patch(
    "/seasons/{season_id}",
    response_model=SeasonResponse,
    response_model_exclude_none=True,
)
async def update_season(
    season_id: str,
    payload: SeasonUpdate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    if not payload.model_fields_set:
        raise bad_request(
            "Provide at least one field to update.",
            code="NO_UPDATE_FIELDS",
        )
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    season = await _run_blocking(
        seasons_repo.update_season,
        season_id,
        user.id,
        **data,
    )
    if season is None:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonId=season_id)
    return season


@router.delete("/seasons/{season_id}", status_code=204)
async def delete_season(
    season_id: str,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> Response:
    deleted = await _run_blocking(seasons_repo.delete_season, season_id, user.id)
    if not deleted:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonId=season_id)
    return Response(status_code=204)
