"""Persistence helpers for Phase 10 first-party operations modules."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, delete, select, update
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import (
    Attachment,
    Field,
    FieldActivity,
    FieldGroup,
    FieldGroupMember,
    Plot,
    ScoutTask,
    UploadedDataset,
)


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _parse_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _date(value: date | datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _attachment(row: Attachment) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "parentType": row.parent_type,
        "parentId": str(row.parent_id) if row.parent_id else None,
        "filename": row.filename,
        "contentType": row.content_type,
        "sizeBytes": int(row.size_bytes) if row.size_bytes is not None else None,
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def _activity(
    row: FieldActivity,
    plot: Plot | None,
    group_names: list[str],
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    groups = [item for item in group_names if item]
    legacy_group_name = plot.group_name if plot else None
    if not groups and legacy_group_name:
        groups = [legacy_group_name]
    return {
        "id": str(row.id),
        "plotId": str(row.plot_id) if row.plot_id else None,
        "fieldName": plot.name if plot else None,
        "groupName": legacy_group_name,
        "groupNames": groups,
        "cropType": plot.crop_type if plot else None,
        "variety": plot.variety if plot else None,
        "seasonLabel": plot.season_label if plot else None,
        "activityType": row.activity_type,
        "activityDate": _date(row.activity_date),
        "assignee": row.assignee,
        "status": row.status,
        "inputProduct": row.input_product,
        "cost": float(row.cost) if row.cost is not None else None,
        "notes": row.notes,
        "attachments": attachments or [],
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def _task(
    row: ScoutTask,
    plot: Plot | None,
    field: Field | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "plotId": str(row.plot_id) if row.plot_id else None,
        "fieldId": str(row.field_id) if row.field_id else None,
        "fieldName": field.name if field else (row.field_name_snapshot or (plot.name if plot else None)),
        "fieldNameSnapshot": row.field_name_snapshot,
        "longitude": row.longitude,
        "latitude": row.latitude,
        "status": row.status,
        "assignee": row.assignee,
        "priority": row.priority,
        "notes": row.notes,
        "attachments": attachments or [],
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def _dataset(row: UploadedDataset) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "datasetType": row.dataset_type,
        "uploadStatus": row.upload_status,
        "originalFilename": row.original_filename,
        "contentType": row.content_type,
        "fileSizeBytes": int(row.file_size_bytes) if row.file_size_bytes is not None else None,
        "featureCount": row.feature_count,
        "validationMessage": row.validation_message,
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def _group(
    row: FieldGroup,
    plot_ids: list[str] | None = None,
    field_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "color": row.color,
        "fieldIds": field_ids or [],
        "plotIds": plot_ids or [],
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def create_attachment(
    *,
    filename: str,
    content_type: str | None,
    size_bytes: int | None,
    metadata: dict[str, Any] | None = None,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    row = Attachment(
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        internal_storage_key=str(uuid.uuid4()),
        metadata_json=metadata or {},
        owner_id=_uuid(owner_id),
        team_id=_uuid(team_id),
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _attachment(row)


def list_attachments(
    *,
    parent_type: str | None = None,
    parent_id: str | None = None,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(Attachment).order_by(Attachment.created_at.desc())
    if team_id:
        stmt = stmt.where(Attachment.team_id == _uuid(team_id))
    if parent_type:
        stmt = stmt.where(Attachment.parent_type == parent_type)
    if parent_id:
        stmt = stmt.where(Attachment.parent_id == _uuid(parent_id))
    with session_scope() as session:
        return [_attachment(row) for row in session.execute(stmt).scalars().all()]


def _link_attachments(
    session: Session,
    attachment_ids: list[str],
    parent_type: str,
    parent_id: str,
    team_id: str | None = None,
) -> None:
    target_parent_id = _uuid(parent_id)
    unlink_stmt = update(Attachment).where(
        Attachment.parent_type == parent_type,
        Attachment.parent_id == target_parent_id,
        Attachment.id.not_in([_uuid(item) for item in attachment_ids] or [uuid.uuid4()]),
    )
    if team_id is not None:
        unlink_stmt = unlink_stmt.where(Attachment.team_id == _uuid(team_id))
    session.execute(unlink_stmt.values(parent_type=None, parent_id=None))

    for attachment_id in attachment_ids:
        stmt = select(Attachment).where(Attachment.id == _uuid(attachment_id))
        if team_id is not None:
            stmt = stmt.where(Attachment.team_id == _uuid(team_id))
        attachment = session.execute(stmt).scalar_one_or_none()
        if attachment is None:
            raise ValueError("ATTACHMENT_NOT_FOUND")
        existing_parent = str(attachment.parent_id) if attachment.parent_id else None
        if attachment.parent_type and (
            attachment.parent_type != parent_type or existing_parent != str(target_parent_id)
        ):
            raise ValueError("ATTACHMENT_ALREADY_LINKED")
        attachment.parent_type = parent_type
        attachment.parent_id = target_parent_id


def _plot_belongs_to_team(session: Session, plot_id: str | None, team_id: str | None) -> bool:
    if plot_id is None or team_id is None:
        return True
    stmt = select(Plot.id).where(Plot.id == _uuid(plot_id), Plot.team_id == _uuid(team_id))
    return session.execute(stmt).first() is not None


def _field_for_team(
    session: Session,
    field_id: str | None,
    team_id: str | None,
) -> Field | None:
    if field_id is None:
        return None
    stmt = select(Field).where(Field.id == _uuid(field_id))
    if team_id is not None:
        stmt = stmt.where(Field.team_id == _uuid(team_id))
    return session.execute(stmt).scalar_one_or_none()


def _group_names_for_plot(
    session: Session,
    plot_id: uuid.UUID | None,
    team_id: str | uuid.UUID | None,
) -> list[str]:
    if plot_id is None:
        return []
    stmt = (
        select(FieldGroup.name)
        .join(FieldGroupMember, FieldGroupMember.group_id == FieldGroup.id)
        .where(FieldGroupMember.plot_id == plot_id)
        .order_by(FieldGroup.name)
        .distinct()
    )
    if team_id is not None:
        stmt = stmt.where(FieldGroup.team_id == _uuid(team_id))
    return [row[0] for row in session.execute(stmt).all()]


def _attachments_for_parent(
    session: Session,
    parent_type: str,
    parent_id: uuid.UUID,
    team_id: str | None,
) -> list[dict[str, Any]]:
    stmt = select(Attachment).where(
        Attachment.parent_type == parent_type,
        Attachment.parent_id == parent_id,
    )
    if team_id is not None:
        stmt = stmt.where(Attachment.team_id == _uuid(team_id))
    stmt = stmt.order_by(Attachment.created_at.desc())
    return [_attachment(row) for row in session.execute(stmt).scalars().all()]


def _activity_row(
    session: Session,
    activity_id: str,
    team_id: str | None = None,
) -> tuple[FieldActivity, Plot | None] | None:
    stmt = (
        select(FieldActivity, Plot)
        .outerjoin(Plot, FieldActivity.plot_id == Plot.id)
        .where(FieldActivity.id == _uuid(activity_id))
    )
    if team_id is not None:
        stmt = stmt.where(FieldActivity.team_id == _uuid(team_id))
    return session.execute(stmt).first()


def _activity_by_id(
    session: Session,
    activity_id: str,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    row = _activity_row(session, activity_id, team_id)
    if not row:
        return None
    activity, plot = row
    return _activity(
        activity,
        plot,
        _group_names_for_plot(session, activity.plot_id, activity.team_id),
        _attachments_for_parent(session, "activity", activity.id, team_id),
    )


def create_activity(payload: dict[str, Any], attachment_ids: list[str]) -> dict[str, Any]:
    with session_scope() as session:
        if not _plot_belongs_to_team(session, payload.get("plotId"), payload.get("teamId")):
            raise ValueError("PLOT_NOT_FOUND")
        row = FieldActivity(
            plot_id=_uuid(payload.get("plotId")),
            activity_type=payload["activityType"],
            activity_date=_parse_date(payload["activityDate"]),
            assignee=payload.get("assignee"),
            status=payload.get("status", "planned"),
            input_product=payload.get("inputProduct"),
            cost=payload.get("cost"),
            notes=payload.get("notes"),
            metadata_json=payload.get("metadata") or {},
            owner_id=_uuid(payload.get("ownerId")),
            team_id=_uuid(payload.get("teamId")),
        )
        session.add(row)
        session.flush()
        _link_attachments(session, attachment_ids, "activity", str(row.id), payload.get("teamId"))
        session.flush()
        session.refresh(row)
        return _activity_by_id(session, str(row.id), payload.get("teamId"))


def update_activity(
    activity_id: str,
    payload: dict[str, Any],
    attachment_ids: list[str] | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        row = _activity_row(session, activity_id, team_id)
        if row is None:
            return None
        activity = row[0]
        if "plotId" in payload and not _plot_belongs_to_team(session, payload["plotId"], team_id):
            raise ValueError("PLOT_NOT_FOUND")
        field_map = {
            "plotId": "plot_id",
            "activityType": "activity_type",
            "activityDate": "activity_date",
            "assignee": "assignee",
            "status": "status",
            "inputProduct": "input_product",
            "cost": "cost",
            "notes": "notes",
        }
        for field, attr in field_map.items():
            if field in payload:
                value = _parse_date(payload[field]) if field == "activityDate" else payload[field]
                setattr(activity, attr, value)
        if "metadata" in payload:
            activity.metadata_json = payload.get("metadata") or {}
        if attachment_ids is not None:
            _link_attachments(session, attachment_ids, "activity", activity_id, team_id)
        session.flush()
        session.refresh(activity)
        return _activity_by_id(session, activity_id, team_id)


def list_activities(filters: dict[str, Any], team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = (
        select(FieldActivity, Plot)
        .outerjoin(Plot, FieldActivity.plot_id == Plot.id)
        .order_by(FieldActivity.activity_date.desc(), FieldActivity.created_at.desc())
    )
    if team_id is not None:
        stmt = stmt.where(FieldActivity.team_id == _uuid(team_id))
    with session_scope() as session:
        rows = [
            _activity(row, plot, _group_names_for_plot(session, row.plot_id, row.team_id))
            for row, plot in session.execute(stmt).all()
        ]
    return _filter_activities(rows, filters)


def _filter_activities(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    def ok(row: dict[str, Any]) -> bool:
        if filters.get("plotId") and row.get("plotId") != filters["plotId"]:
            return False
        if filters.get("groupName") and filters["groupName"] not in row.get("groupNames", []):
            return False
        for key, row_key in (
            ("cropType", "cropType"),
            ("variety", "variety"),
            ("activityType", "activityType"),
            ("assignee", "assignee"),
            ("status", "status"),
        ):
            if filters.get(key) and (
                str(row.get(row_key) or "").lower() != str(filters[key]).lower()
            ):
                return False
        if filters.get("year") and not str(row.get("activityDate") or "").startswith(
            str(filters["year"])
        ):
            return False
        return True

    return [row for row in rows if ok(row)]


def get_activity(activity_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    with session_scope() as session:
        return _activity_by_id(session, activity_id, team_id)


def delete_activity(activity_id: str, team_id: str | None = None) -> bool:
    with session_scope() as session:
        row = _activity_row(session, activity_id, team_id)
        if row is None:
            return False
        activity = row[0]
        unlink = update(Attachment).where(
            Attachment.parent_type == "activity",
            Attachment.parent_id == activity.id,
        )
        if team_id is not None:
            unlink = unlink.where(Attachment.team_id == _uuid(team_id))
        session.execute(unlink.values(parent_type=None, parent_id=None))
        session.delete(activity)
        return True


def create_scout_task(payload: dict[str, Any], attachment_ids: list[str]) -> dict[str, Any]:
    with session_scope() as session:
        if not _plot_belongs_to_team(session, payload.get("plotId"), payload.get("teamId")):
            raise ValueError("PLOT_NOT_FOUND")
        field = _field_for_team(session, payload.get("fieldId"), payload.get("teamId"))
        if payload.get("fieldId") and field is None:
            raise ValueError("FIELD_NOT_FOUND")
        row = ScoutTask(
            plot_id=_uuid(payload.get("plotId")),
            field_id=_uuid(payload.get("fieldId")),
            field_name_snapshot=field.name if field else payload.get("fieldNameSnapshot"),
            longitude=payload.get("longitude"),
            latitude=payload.get("latitude"),
            status=payload.get("status", "new"),
            assignee=payload.get("assignee"),
            priority=payload.get("priority", "medium"),
            notes=payload.get("notes"),
            metadata_json=payload.get("metadata") or {},
            owner_id=_uuid(payload.get("ownerId")),
            team_id=_uuid(payload.get("teamId")),
        )
        session.add(row)
        session.flush()
        _link_attachments(session, attachment_ids, "scout_task", str(row.id), payload.get("teamId"))
        session.flush()
        session.refresh(row)
        return _task_by_id(session, str(row.id), payload.get("teamId"))


def update_scout_task(
    task_id: str,
    payload: dict[str, Any],
    attachment_ids: list[str] | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        row = _task_row(session, task_id, team_id)
        if row is None:
            return None
        task = row[0]
        if "plotId" in payload and not _plot_belongs_to_team(session, payload["plotId"], team_id):
            raise ValueError("PLOT_NOT_FOUND")
        linked_field = None
        if "fieldId" in payload:
            linked_field = _field_for_team(session, payload["fieldId"], team_id)
            if payload["fieldId"] and linked_field is None:
                raise ValueError("FIELD_NOT_FOUND")
        field_map = {
            "plotId": "plot_id",
            "fieldId": "field_id",
            "longitude": "longitude",
            "latitude": "latitude",
            "status": "status",
            "assignee": "assignee",
            "priority": "priority",
            "notes": "notes",
        }
        for api_field, attr in field_map.items():
            if api_field in payload:
                setattr(
                    task,
                    attr,
                    (
                        _uuid(payload[api_field])
                        if api_field in {"plotId", "fieldId"}
                        else payload[api_field]
                    ),
                )
        if "fieldId" in payload and linked_field is not None:
            task.field_name_snapshot = linked_field.name
        if "metadata" in payload:
            task.metadata_json = payload.get("metadata") or {}
        if attachment_ids is not None:
            _link_attachments(session, attachment_ids, "scout_task", task_id, team_id)
        session.flush()
        session.refresh(task)
        return _task_by_id(session, task_id, team_id)


def _task_row(
    session: Session,
    task_id: str,
    team_id: str | None = None,
) -> tuple[ScoutTask, Plot | None, Field | None] | None:
    stmt = (
        select(ScoutTask, Plot, Field)
        .outerjoin(Plot, ScoutTask.plot_id == Plot.id)
        .outerjoin(
            Field,
            and_(ScoutTask.field_id == Field.id, Field.team_id == ScoutTask.team_id),
        )
        .where(ScoutTask.id == _uuid(task_id))
    )
    if team_id is not None:
        stmt = stmt.where(ScoutTask.team_id == _uuid(team_id))
    return session.execute(stmt).first()


def _task_by_id(
    session: Session,
    task_id: str,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    row = _task_row(session, task_id, team_id)
    if not row:
        return None
    task, plot, field = row
    return _task(
        task,
        plot,
        field,
        _attachments_for_parent(session, "scout_task", task.id, team_id),
    )


def list_scout_tasks(filters: dict[str, Any], team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = (
        select(ScoutTask, Plot, Field)
        .outerjoin(Plot, ScoutTask.plot_id == Plot.id)
        .outerjoin(
            Field,
            and_(ScoutTask.field_id == Field.id, Field.team_id == ScoutTask.team_id),
        )
    )
    if team_id is not None:
        stmt = stmt.where(ScoutTask.team_id == _uuid(team_id))
    stmt = stmt.order_by(ScoutTask.created_at.desc())
    with session_scope() as session:
        rows = [_task(task, plot, field) for task, plot, field in session.execute(stmt).all()]
    return [
        row
        for row in rows
        if (not filters.get("status") or row["status"] == filters["status"])
        and (not filters.get("plotId") or row.get("plotId") == filters["plotId"])
        and (
            not filters.get("search")
            or filters["search"].lower()
            in " ".join(
                str(row.get(k) or "") for k in ("fieldName", "notes", "assignee")
            ).lower()
        )
    ]


def get_scout_task(task_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    with session_scope() as session:
        return _task_by_id(session, task_id, team_id)


def delete_scout_task(task_id: str, team_id: str | None = None) -> bool:
    with session_scope() as session:
        row = _task_row(session, task_id, team_id)
        if row is None:
            return False
        task = row[0]
        unlink = update(Attachment).where(
            Attachment.parent_type == "scout_task",
            Attachment.parent_id == task.id,
        )
        if team_id is not None:
            unlink = unlink.where(Attachment.team_id == _uuid(team_id))
        session.execute(unlink.values(parent_type=None, parent_id=None))
        session.delete(task)
        return True


def create_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    row = UploadedDataset(
        name=payload["name"],
        dataset_type=payload["datasetType"],
        upload_status=payload.get("uploadStatus", "uploaded"),
        original_filename=payload.get("originalFilename"),
        content_type=payload.get("contentType"),
        file_size_bytes=payload.get("fileSizeBytes"),
        feature_count=payload.get("featureCount"),
        validation_message=payload.get("validationMessage"),
        internal_storage_key=str(uuid.uuid4()),
        metadata_json=payload.get("metadata") or {},
        owner_id=_uuid(payload.get("ownerId")),
        team_id=_uuid(payload.get("teamId")),
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _dataset(row)


def list_datasets(team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(UploadedDataset).order_by(UploadedDataset.created_at.desc())
    if team_id is not None:
        stmt = stmt.where(UploadedDataset.team_id == _uuid(team_id))
    with session_scope() as session:
        return [_dataset(row) for row in session.execute(stmt).scalars().all()]


def create_field_group(payload: dict[str, Any]) -> dict[str, Any]:
    row = FieldGroup(
        name=payload["name"],
        description=payload.get("description"),
        color=payload.get("color"),
        owner_id=_uuid(payload.get("ownerId")),
        team_id=_uuid(payload.get("teamId")),
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _group(row)


def list_field_groups(team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(FieldGroup).order_by(FieldGroup.name)
    if team_id is not None:
        stmt = stmt.where(FieldGroup.team_id == _uuid(team_id))
    with session_scope() as session:
        return [
            _group(
                row,
                _group_plot_ids(session, str(row.id), team_id),
                _group_field_ids(session, str(row.id), team_id),
            )
            for row in session.execute(stmt).scalars().all()
        ]


def update_field_group(
    group_id: str,
    payload: dict[str, Any],
    team_id: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        group = _field_group_obj(session, group_id, team_id)
        if group is None:
            return None
        for key in ("name", "description", "color"):
            if key in payload:
                setattr(group, key, payload[key])
        session.flush()
        session.refresh(group)
        return _group(
            group,
            _group_plot_ids(session, group_id, team_id),
            _group_field_ids(session, group_id, team_id),
        )


def _field_group_obj(
    session: Session,
    group_id: str,
    team_id: str | None = None,
) -> FieldGroup | None:
    stmt = select(FieldGroup).where(FieldGroup.id == _uuid(group_id))
    if team_id is not None:
        stmt = stmt.where(FieldGroup.team_id == _uuid(team_id))
    return session.execute(stmt).scalar_one_or_none()


def get_field_group(group_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    with session_scope() as session:
        group = _field_group_obj(session, group_id, team_id)
        return (
            _group(
                group,
                _group_plot_ids(session, group_id, team_id),
                _group_field_ids(session, group_id, team_id),
            )
            if group
            else None
        )


def delete_field_group(group_id: str, team_id: str | None = None) -> bool:
    stmt = delete(FieldGroup).where(FieldGroup.id == _uuid(group_id))
    if team_id is not None:
        stmt = stmt.where(FieldGroup.team_id == _uuid(team_id))
    with session_scope() as session:
        return session.execute(stmt).rowcount > 0


def assign_group_fields(
    group_id: str,
    plot_ids: list[str],
    team_id: str | None = None,
    field_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        group = _field_group_obj(session, group_id, team_id)
        if group is None:
            return None
        if field_ids is not None:
            team_uuid = _uuid(team_id)
            requested_ids = {_uuid(field_id) for field_id in field_ids}
            field_stmt = select(Field.id).where(Field.id.in_(requested_ids))
            if team_uuid is not None:
                field_stmt = field_stmt.where(Field.team_id == team_uuid)
            authorized_ids = set(session.execute(field_stmt).scalars().all())
            if requested_ids != authorized_ids:
                return None
            session.execute(
                update(Field)
                .where(Field.group_id == group.id)
                .where(Field.team_id == team_uuid)
                .values(group_id=None)
            )
            if authorized_ids:
                session.execute(
                    update(Field)
                    .where(Field.id.in_(authorized_ids))
                    .where(Field.team_id == team_uuid)
                    .values(group_id=group.id)
                )
        delete_stmt = delete(FieldGroupMember).where(FieldGroupMember.group_id == group.id)
        if team_id is not None:
            delete_stmt = delete_stmt.where(FieldGroupMember.team_id == _uuid(team_id))
        session.execute(delete_stmt)
        seen_plot_ids: set[uuid.UUID] = set()
        for plot_id in plot_ids:
            plot_stmt = select(Plot.id).where(Plot.id == _uuid(plot_id))
            if team_id is not None:
                plot_stmt = plot_stmt.where(Plot.team_id == _uuid(team_id))
            plot_row = session.execute(plot_stmt).first()
            if plot_row and plot_row[0] not in seen_plot_ids:
                seen_plot_ids.add(plot_row[0])
                session.add(
                    FieldGroupMember(
                        group_id=group.id,
                        plot_id=plot_row[0],
                        team_id=_uuid(team_id),
                    )
                )
        session.flush()
        return _group(
            group,
            _group_plot_ids(session, group_id, team_id),
            _group_field_ids(session, group_id, team_id),
        )


def _group_plot_ids(session: Session, group_id: str, team_id: str | None = None) -> list[str]:
    stmt = (
        select(FieldGroupMember.plot_id)
        .where(FieldGroupMember.group_id == _uuid(group_id))
        .order_by(FieldGroupMember.created_at)
    )
    if team_id is not None:
        stmt = stmt.where(FieldGroupMember.team_id == _uuid(team_id))
    return [str(row[0]) for row in session.execute(stmt).all()]


def _group_field_ids(session: Session, group_id: str, team_id: str | None = None) -> list[str]:
    stmt = select(Field.id).where(Field.group_id == _uuid(group_id)).order_by(Field.created_at)
    if team_id is not None:
        stmt = stmt.where(Field.team_id == _uuid(team_id))
    return [str(row[0]) for row in session.execute(stmt).all()]
