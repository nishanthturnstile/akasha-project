"""Scout task routes for Phase 10."""
from __future__ import annotations

import functools
import logging
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field

from . import phase10_repo
from .auth import get_current_team
from .operations import AttachmentPublic
from .api_models import ApiModel
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.scout_tasks")
router = APIRouter(
    prefix="/api",
    tags=["scout-tasks"],
    dependencies=[Depends(get_current_team)],
)


class ScoutTaskPayload(ApiModel):
    plot_id: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"] = "new"
    assignee: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    notes: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoutTaskUpdate(ApiModel):
    plot_id: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"] | None = None
    assignee: str | None = None
    priority: Literal["low", "medium", "high"] | None = None
    notes: str | None = None
    attachment_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ScoutTask(ApiModel):
    id: str
    plot_id: str | None = None
    field_name: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"]
    assignee: str | None = None
    priority: Literal["low", "medium", "high"]
    notes: str | None = None
    attachments: list[AttachmentPublic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except ValueError as exc:
        if str(exc) == "ATTACHMENT_NOT_FOUND":
            raise not_found("Attachment not found.", code="ATTACHMENT_NOT_FOUND") from exc
        if str(exc) == "ATTACHMENT_ALREADY_LINKED":
            raise bad_request(
                "Attachment is already linked to another record.",
                code="ATTACHMENT_ALREADY_LINKED",
            ) from exc
        raise
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("scout task backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Scout task storage is not available.") from exc


def _validate_coords(payload: ScoutTaskPayload | ScoutTaskUpdate) -> None:
    if payload.longitude is not None and not -180 <= payload.longitude <= 180:
        raise bad_request("longitude must be between -180 and 180.", code="INVALID_COORDINATES")
    if payload.latitude is not None and not -90 <= payload.latitude <= 90:
        raise bad_request("latitude must be between -90 and 90.", code="INVALID_COORDINATES")


@router.get("/scout-tasks", response_model=list[ScoutTask], response_model_by_alias=True)
async def list_scout_tasks(
    status: str | None = Query(default=None),
    plotId: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> list[ScoutTask]:
    rows = await _run_blocking(
        phase10_repo.list_scout_tasks,
        {"status": status, "plotId": plotId, "search": search},
    )
    return [ScoutTask(**row) for row in rows]


@router.post(
    "/scout-tasks",
    response_model=ScoutTask,
    response_model_by_alias=True,
    status_code=201,
)
async def create_scout_task(payload: ScoutTaskPayload) -> ScoutTask:
    _validate_coords(payload)
    row = await _run_blocking(
        phase10_repo.create_scout_task,
        payload.model_dump(by_alias=True),
        payload.attachment_ids,
    )
    return ScoutTask(**row)


@router.get("/scout-tasks/{task_id}", response_model=ScoutTask, response_model_by_alias=True)
async def get_scout_task(task_id: str) -> ScoutTask:
    row = await _run_blocking(phase10_repo.get_scout_task, task_id)
    if row is None:
        raise not_found("Scout task not found.", code="SCOUT_TASK_NOT_FOUND", taskId=task_id)
    return ScoutTask(**row)


@router.patch("/scout-tasks/{task_id}", response_model=ScoutTask, response_model_by_alias=True)
async def update_scout_task(task_id: str, payload: ScoutTaskUpdate) -> ScoutTask:
    _validate_coords(payload)
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    attachment_ids = data.pop("attachmentIds", None)
    row = await _run_blocking(
        phase10_repo.update_scout_task,
        task_id,
        data,
        attachment_ids,
    )
    if row is None:
        raise not_found("Scout task not found.", code="SCOUT_TASK_NOT_FOUND", taskId=task_id)
    return ScoutTask(**row)


@router.delete("/scout-tasks/{task_id}", status_code=204)
async def delete_scout_task(task_id: str) -> Response:
    deleted = await _run_blocking(phase10_repo.delete_scout_task, task_id)
    if not deleted:
        raise not_found("Scout task not found.", code="SCOUT_TASK_NOT_FOUND", taskId=task_id)
    return Response(status_code=204)
