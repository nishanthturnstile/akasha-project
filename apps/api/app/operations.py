"""Field activity log routes for Phase 10."""
from __future__ import annotations

import csv
import functools
import logging
from io import StringIO
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field

from . import phase10_repo
from .auth import get_current_team
from .field_exports import _disposition
from .providers.models import ProviderModel
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.operations")
router = APIRouter(
    prefix="/api",
    tags=["operations"],
    dependencies=[Depends(get_current_team)],
)

ActivityStatus = Literal["planned", "in_progress", "done", "cancelled"]


class AttachmentPublic(ProviderModel):
    id: str
    parent_type: str | None = None
    parent_id: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class AttachmentCreate(ProviderModel):
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldActivityPayload(ProviderModel):
    activity_type: str
    activity_date: str
    plot_id: str | None = None
    assignee: str | None = None
    status: ActivityStatus = "planned"
    input_product: str | None = None
    cost: float | None = None
    notes: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldActivityUpdate(ProviderModel):
    activity_type: str | None = None
    activity_date: str | None = None
    plot_id: str | None = None
    assignee: str | None = None
    status: ActivityStatus | None = None
    input_product: str | None = None
    cost: float | None = None
    notes: str | None = None
    attachment_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class FieldActivity(ProviderModel):
    id: str
    plot_id: str | None = None
    field_name: str | None = None
    group_name: str | None = None
    group_names: list[str] = Field(default_factory=list)
    crop_type: str | None = None
    variety: str | None = None
    season_label: str | None = None
    activity_type: str
    activity_date: str
    assignee: str | None = None
    status: ActivityStatus
    input_product: str | None = None
    cost: float | None = None
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
        logger.warning("operations backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Operations storage is not available.") from exc


def _csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    if text.startswith(("=", "+", "-", "@", "\t")):
        return "'" + text
    return text


def _filters(
    plotId: str | None = None,
    groupName: str | None = None,
    cropType: str | None = None,
    variety: str | None = None,
    activityType: str | None = None,
    assignee: str | None = None,
    year: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "plotId": plotId,
        "groupName": groupName,
        "cropType": cropType,
        "variety": variety,
        "activityType": activityType,
        "assignee": assignee,
        "year": year,
        "status": status,
    }


@router.post(
    "/attachments",
    response_model=AttachmentPublic,
    response_model_by_alias=True,
    status_code=201,
)
async def create_attachment(payload: AttachmentCreate) -> AttachmentPublic:
    row = await _run_blocking(
        phase10_repo.create_attachment,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        metadata=payload.metadata,
    )
    return AttachmentPublic(**row)


@router.get("/attachments", response_model=list[AttachmentPublic], response_model_by_alias=True)
async def list_attachments(
    parentType: str | None = Query(default=None),
    parentId: str | None = Query(default=None),
) -> list[AttachmentPublic]:
    rows = await _run_blocking(
        phase10_repo.list_attachments,
        parent_type=parentType,
        parent_id=parentId,
    )
    return [AttachmentPublic(**row) for row in rows]


@router.get("/activities", response_model=list[FieldActivity], response_model_by_alias=True)
async def list_activities(
    plotId: str | None = Query(default=None),
    groupName: str | None = Query(default=None),
    cropType: str | None = Query(default=None),
    variety: str | None = Query(default=None),
    activityType: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    year: int | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[FieldActivity]:
    rows = await _run_blocking(
        phase10_repo.list_activities,
        _filters(plotId, groupName, cropType, variety, activityType, assignee, year, status),
    )
    return [FieldActivity(**row) for row in rows]


@router.post(
    "/fields/{plot_id}/activities",
    response_model=FieldActivity,
    response_model_by_alias=True,
    status_code=201,
)
async def create_field_activity(plot_id: str, payload: FieldActivityPayload) -> FieldActivity:
    data = payload.model_dump(by_alias=True)
    data["plotId"] = plot_id
    row = await _run_blocking(
        phase10_repo.create_activity,
        data,
        payload.attachment_ids,
    )
    return FieldActivity(**row)


@router.get("/activities/export.csv")
async def export_activities_csv(
    plotId: str | None = Query(default=None),
    groupName: str | None = Query(default=None),
    cropType: str | None = Query(default=None),
    variety: str | None = Query(default=None),
    activityType: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    year: int | None = Query(default=None),
    status: str | None = Query(default=None),
) -> Response:
    rows = await list_activities(
        plotId,
        groupName,
        cropType,
        variety,
        activityType,
        assignee,
        year,
        status,
    )
    output = StringIO()
    fields = [
        "fieldName",
        "activityType",
        "activityDate",
        "assignee",
        "status",
        "inputProduct",
        "cost",
        "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        payload = row.model_dump(by_alias=True)
        writer.writerow({key: _csv_safe(payload.get(key)) for key in fields})
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers=_disposition("field-activities.csv"),
    )


@router.get("/activities/{activity_id}", response_model=FieldActivity, response_model_by_alias=True)
async def get_activity(activity_id: str) -> FieldActivity:
    row = await _run_blocking(phase10_repo.get_activity, activity_id)
    if row is None:
        raise not_found("Activity not found.", code="ACTIVITY_NOT_FOUND", activityId=activity_id)
    return FieldActivity(**row)


@router.patch(
    "/activities/{activity_id}",
    response_model=FieldActivity,
    response_model_by_alias=True,
)
async def update_activity(activity_id: str, payload: FieldActivityUpdate) -> FieldActivity:
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    attachment_ids = data.pop("attachmentIds", None)
    row = await _run_blocking(
        phase10_repo.update_activity,
        activity_id,
        data,
        attachment_ids,
    )
    if row is None:
        raise not_found("Activity not found.", code="ACTIVITY_NOT_FOUND", activityId=activity_id)
    return FieldActivity(**row)


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(activity_id: str) -> Response:
    deleted = await _run_blocking(phase10_repo.delete_activity, activity_id)
    if not deleted:
        raise not_found("Activity not found.", code="ACTIVITY_NOT_FOUND", activityId=activity_id)
    return Response(status_code=204)
