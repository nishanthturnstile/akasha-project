"""Persistence for Akasha report templates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from ..db import session_scope
from ..models import ReportTemplate


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _row_to_template(row: ReportTemplate) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "columns": row.columns or [],
        "filters": row.filters or {},
        "sort": row.sort or {},
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def list_report_templates(team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(ReportTemplate).order_by(ReportTemplate.created_at.desc())
    if team_id is not None:
        stmt = stmt.where(ReportTemplate.team_id == _uuid(team_id))
    with session_scope() as session:
        return [_row_to_template(row) for row in session.execute(stmt).scalars().all()]


def get_report_template(template_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    stmt = select(ReportTemplate).where(ReportTemplate.id == _uuid(template_id))
    if team_id is not None:
        stmt = stmt.where(ReportTemplate.team_id == _uuid(team_id))
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _row_to_template(row) if row else None


def create_report_template(
    *,
    name: str,
    columns: list[str],
    filters: dict[str, Any],
    sort: dict[str, Any],
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    template = ReportTemplate(
        name=name,
        columns=columns,
        filters=filters,
        sort=sort,
        owner_id=_uuid(owner_id),
        team_id=_uuid(team_id),
    )
    with session_scope() as session:
        session.add(template)
        session.flush()
        return _row_to_template(template)


def update_report_template(
    template_id: str,
    *,
    name: str | None = None,
    columns: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    sort: dict[str, Any] | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if columns is not None:
        values["columns"] = columns
    if filters is not None:
        values["filters"] = filters
    if sort is not None:
        values["sort"] = sort
    if not values:
        return get_report_template(template_id, team_id)
    stmt = update(ReportTemplate).where(ReportTemplate.id == _uuid(template_id)).values(**values)
    if team_id is not None:
        stmt = stmt.where(ReportTemplate.team_id == _uuid(team_id))
    stmt = stmt.returning(ReportTemplate)
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _row_to_template(row) if row else None
