"""Field group routes for Phase 10."""
from __future__ import annotations

import functools
import logging

import anyio
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import Field

from . import phase10_repo
from .providers.models import ProviderModel
from .raster.errors import AkashaError, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.field_groups")
router = APIRouter(prefix="/api", tags=["field-groups"])


class FieldGroupPayload(ProviderModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class FieldGroup(ProviderModel):
    id: str
    name: str
    description: str | None = None
    color: str | None = None
    plot_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class FieldAssignmentPayload(ProviderModel):
    plot_ids: list[str] = Field(default_factory=list)


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
async def list_field_groups() -> list[FieldGroup]:
    rows = await _run_blocking(phase10_repo.list_field_groups)
    return [FieldGroup(**row) for row in rows]


@router.post(
    "/field-groups",
    response_model=FieldGroup,
    response_model_by_alias=True,
    status_code=201,
)
async def create_field_group(payload: FieldGroupPayload) -> FieldGroup:
    row = await _run_blocking(phase10_repo.create_field_group, payload.model_dump(by_alias=True))
    return FieldGroup(**row)


@router.patch("/field-groups/{group_id}", response_model=FieldGroup, response_model_by_alias=True)
async def update_field_group(group_id: str, payload: FieldGroupPayload) -> FieldGroup:
    row = await _run_blocking(
        phase10_repo.update_field_group,
        group_id,
        payload.model_dump(by_alias=True, exclude_unset=True),
    )
    if row is None:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return FieldGroup(**row)


@router.delete("/field-groups/{group_id}", status_code=204)
async def delete_field_group(group_id: str) -> Response:
    deleted = await _run_blocking(phase10_repo.delete_field_group, group_id)
    if not deleted:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return Response(status_code=204)


@router.post(
    "/field-groups/{group_id}/fields",
    response_model=FieldGroup,
    response_model_by_alias=True,
)
async def assign_field_group(group_id: str, payload: FieldAssignmentPayload) -> FieldGroup:
    row = await _run_blocking(phase10_repo.assign_group_fields, group_id, payload.plot_ids)
    if row is None:
        raise not_found("Field group not found.", code="FIELD_GROUP_NOT_FOUND", groupId=group_id)
    return FieldGroup(**row)
