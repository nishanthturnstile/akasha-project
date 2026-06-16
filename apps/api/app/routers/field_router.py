"""Akasha BFF Field API."""

from __future__ import annotations

import functools
import logging
from typing import Any

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError

from ..auth import CurrentUser, get_current_user
from ..raster.errors import AkashaError, field_backend_unavailable, not_found
from ..repositories import fields_repo
from ..schemas.fields import FieldCreate, FieldResponse, FieldUpdate

logger = logging.getLogger("akasha.api.fields")
router = APIRouter(prefix="/api", tags=["fields"], dependencies=[Depends(get_current_user)])

MAX_NAME_LENGTH = 100


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
async def list_fields(user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    return await _run_blocking(fields_repo.list_fields, user.id)


@router.post("/fields", response_model=FieldResponse, status_code=201)
async def create_field(
    payload: FieldCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await _run_blocking(
        fields_repo.create_field,
        user.id,
        payload.name,
        payload.geometry,
        payload.areaHa,
        payload.groupId,
        payload.seasonIds,
    )


@router.get("/fields/{field_id}", response_model=FieldResponse)
async def get_field(field_id: str, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    field = await _run_blocking(fields_repo.get_field, field_id, user.id)
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


@router.patch("/fields/{field_id}", response_model=FieldResponse)
async def update_field(
    field_id: str,
    payload: FieldUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    field = await _run_blocking(fields_repo.update_field, field_id, user.id, **data)
    if field is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return field


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(
    field_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    deleted = await _run_blocking(fields_repo.delete_field, field_id, user.id)
    if not deleted:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldId=field_id)
    return Response(status_code=204)
