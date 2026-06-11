"""Season persistence through SQLAlchemy + PostGIS."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update

from .db import session_scope
from .models import Season
from .raster.errors import AkashaError


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _row_to_season(row: Any) -> dict[str, Any]:
    (
        season_id,
        user_id,
        name,
        start_date,
        end_date,
        can_delete,
        created_at,
        updated_at,
    ) = row
    return {
        "id": str(season_id),
        "userId": str(user_id),
        "name": name,
        "startDate": start_date.isoformat() if start_date else None,
        "endDate": end_date.isoformat() if end_date else None,
        "canDelete": can_delete,
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def _season_columns() -> tuple[Any, ...]:
    return (
        Season.season_id,
        Season.user_id,
        Season.name,
        Season.start_date,
        Season.end_date,
        Season.can_delete,
        Season.created_at,
        Season.updated_at,
    )


def list_seasons(user_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(*_season_columns()).order_by(
        Season.start_date.nulls_last(), Season.name
    )
    if user_id is not None:
        stmt = stmt.where(Season.user_id == _uuid(user_id))
    with session_scope() as session:
        return [_row_to_season(row) for row in session.execute(stmt).all()]


def get_season(season_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    stmt = select(*_season_columns()).where(Season.season_id == _uuid(season_id))
    if user_id is not None:
        stmt = stmt.where(Season.user_id == _uuid(user_id))
    with session_scope() as session:
        row = session.execute(stmt).first()
        return _row_to_season(row) if row else None


def create_season(
    user_id: str,
    name: str,
    start_date: date | None,
    end_date: date | None,
    can_delete: bool | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        if can_delete is None:
            count = (
                session.query(Season)
                .filter(Season.user_id == _uuid(user_id))
                .count()
            )
            can_delete = count >= 1

        season = Season(
            user_id=_uuid(user_id),
            name=name,
            start_date=start_date,
            end_date=end_date,
            can_delete=can_delete,
        )
        session.add(season)
        session.flush()
        _recalculate_can_delete(session, user_id)
        session.refresh(season)
        return _row_to_season(
            (
                season.season_id,
                season.user_id,
                season.name,
                season.start_date,
                season.end_date,
                season.can_delete,
                season.created_at,
                season.updated_at,
            )
        )


def update_season(
    season_id: str,
    user_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    allowed = {"name", "start_date", "end_date", "can_delete"}
    values = {key: value for key, value in kwargs.items() if key in allowed and value is not None}
    if not values:
        stmt = select(*_season_columns()).where(Season.season_id == _uuid(season_id))
        if user_id is not None:
            stmt = stmt.where(Season.user_id == _uuid(user_id))
        with session_scope() as session:
            row = session.execute(stmt).first()
            return _row_to_season(row) if row else None

    stmt = (
        update(Season)
        .where(Season.season_id == _uuid(season_id))
        .values(**values)
        .returning(*_season_columns())
    )
    if user_id is not None:
        stmt = stmt.where(Season.user_id == _uuid(user_id))
    with session_scope() as session:
        row = session.execute(stmt).first()
        if row is None:
            return None
        return _row_to_season(row)


def delete_season(season_id: str, user_id: str | None = None) -> bool:
    with session_scope() as session:
        season = session.get(Season, _uuid(season_id))
        if season is None:
            return False
        if user_id is not None and season.user_id != _uuid(user_id):
            return False

        count = (
            session.query(Season)
            .filter(Season.user_id == season.user_id)
            .count()
        )
        if count <= 1:
            raise AkashaError(
                "Season cannot be deleted.",
                code="CANNOT_DELETE_SEASON",
                seasonId=season_id,
            )

        session.delete(season)
        session.flush()
        _recalculate_can_delete(session, str(season.user_id))
        return True


def _recalculate_can_delete(session: Any, user_id: str) -> None:
    uid = _uuid(user_id)
    count = session.query(Season).filter(Season.user_id == uid).count()
    new_flag = count >= 2
    session.execute(
        update(Season)
        .where(Season.user_id == uid)
        .values(can_delete=new_flag)
    )
