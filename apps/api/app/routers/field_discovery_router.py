"""Shared Monitoring and Scouting discovery endpoints."""

from __future__ import annotations

import functools
import logging
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Query

from ..auth import CurrentTeam, get_current_team
from ..raster.errors import AkashaError, plots_backend_unavailable
from ..repositories import field_discovery_repo
from ..schemas.field_discovery import (
    DiscoveryFacets,
    DiscoveryMapResponse,
    DiscoverySort,
    FieldDiscoveryPage,
    ScoutTaskDiscoveryPage,
)

logger = logging.getLogger("akasha.api.field_discovery")
router = APIRouter(
    prefix="/api/field-discovery",
    tags=["field-discovery"],
    dependencies=[Depends(get_current_team)],
)

CropIds = Annotated[list[str] | None, Query(alias="cropId")]
GroupIds = Annotated[list[str] | None, Query(alias="groupId")]
PinnedFieldIds = Annotated[list[str] | None, Query(alias="pinnedFieldIds", max_length=50)]


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    started = perf_counter()
    try:
        result = await anyio.to_thread.run_sync(call)
        if isinstance(result, dict):
            applied = result.get("appliedFilters") or {}
            normalized = (
                len(kwargs.get("crop_ids") or []) != len(applied.get("cropIds") or [])
                or len(kwargs.get("group_ids") or []) != len(applied.get("groupIds") or [])
                or bool(kwargs.get("include_ungrouped"))
                != bool(applied.get("includeUngrouped"))
            )
            logger.info(
                "operation=%s duration_ms=%.1f total=%s item_count=%s "
                "normalized_filters=%s",
                func.__name__,
                (perf_counter() - started) * 1000,
                result.get("total"),
                len(result.get("items") or []),
                normalized,
            )
        return result
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("field discovery backend unavailable")
        raise plots_backend_unavailable("Field discovery storage is not available.") from exc


def _crop_ids(values: list[str] | None) -> list[int]:
    normalized: list[int] = []
    for value in values or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in normalized:
            normalized.append(parsed)
    return normalized


@router.get("/facets", response_model=DiscoveryFacets, response_model_by_alias=True)
async def discovery_facets(
    season_id: Annotated[UUID, Query(alias="seasonId")],
    target: Literal["monitoring", "scouting"] = "monitoring",
    status: Literal["new", "closed"] | None = None,
    team: CurrentTeam = Depends(get_current_team),
) -> DiscoveryFacets:
    row = await _run_blocking(
        field_discovery_repo.get_facets,
        team_id=team.id,
        season_id=str(season_id),
        target=target,
        status=status if target == "scouting" else None,
    )
    return DiscoveryFacets(**row)


@router.get("/fields", response_model=FieldDiscoveryPage, response_model_by_alias=True)
async def discover_fields(
    season_id: Annotated[UUID, Query(alias="seasonId")],
    q: str = Query(default="", max_length=200),
    crop_ids: CropIds = None,
    group_ids: GroupIds = None,
    include_ungrouped: bool = Query(default=False, alias="includeUngrouped"),
    sort: DiscoverySort = "name_asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    pinned_field_ids: PinnedFieldIds = None,
    team: CurrentTeam = Depends(get_current_team),
) -> FieldDiscoveryPage:
    row = await _run_blocking(
        field_discovery_repo.list_fields,
        team_id=team.id,
        season_id=str(season_id),
        q=q,
        crop_ids=_crop_ids(crop_ids),
        group_ids=group_ids or [],
        include_ungrouped=include_ungrouped,
        sort=sort,
        page=page,
        page_size=page_size,
        pinned_field_ids=pinned_field_ids or [],
    )
    return FieldDiscoveryPage(**row)


@router.get(
    "/scout-tasks",
    response_model=ScoutTaskDiscoveryPage,
    response_model_by_alias=True,
)
async def discover_scout_tasks(
    season_id: Annotated[UUID, Query(alias="seasonId")],
    status: Literal["new", "closed"] | None = None,
    q: str = Query(default="", max_length=200),
    crop_ids: CropIds = None,
    group_ids: GroupIds = None,
    include_ungrouped: bool = Query(default=False, alias="includeUngrouped"),
    sort: DiscoverySort = "name_asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    pinned_field_ids: PinnedFieldIds = None,
    team: CurrentTeam = Depends(get_current_team),
) -> ScoutTaskDiscoveryPage:
    row = await _run_blocking(
        field_discovery_repo.list_scout_tasks,
        team_id=team.id,
        season_id=str(season_id),
        status=status,
        q=q,
        crop_ids=_crop_ids(crop_ids),
        group_ids=group_ids or [],
        include_ungrouped=include_ungrouped,
        sort=sort,
        page=page,
        page_size=page_size,
        pinned_field_ids=pinned_field_ids or [],
    )
    return ScoutTaskDiscoveryPage(**row)


@router.get("/map", response_model=DiscoveryMapResponse, response_model_by_alias=True)
async def discovery_map(
    season_id: Annotated[UUID, Query(alias="seasonId")],
    target: Literal["monitoring", "scouting"] = "monitoring",
    west: float = Query(ge=-180, le=180),
    south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=540),
    north: float = Query(ge=-90, le=90),
    zoom: float = Query(ge=0, le=24),
    status: Literal["new", "closed"] | None = None,
    q: str = Query(default="", max_length=200),
    crop_ids: CropIds = None,
    group_ids: GroupIds = None,
    include_ungrouped: bool = Query(default=False, alias="includeUngrouped"),
    team: CurrentTeam = Depends(get_current_team),
) -> DiscoveryMapResponse:
    row = await _run_blocking(
        field_discovery_repo.get_map_features,
        team_id=team.id,
        season_id=str(season_id),
        target=target,
        west=west,
        south=south,
        east=east,
        north=north,
        zoom=zoom,
        status=status if target == "scouting" else None,
        q=q,
        crop_ids=_crop_ids(crop_ids),
        group_ids=group_ids or [],
        include_ungrouped=include_ungrouped,
    )
    return DiscoveryMapResponse(**row)
