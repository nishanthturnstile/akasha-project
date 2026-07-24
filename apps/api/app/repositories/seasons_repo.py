"""Season persistence through SQLAlchemy + PostGIS."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from ..db import session_scope
from ..models import Field, FieldSeason, Season, VegetationCycle
from ..raster.errors import AkashaError, not_found


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


def _row_to_season(
    row: Any,
    fields: list[dict] | None = None,
    can_remove_map: dict[str, bool] | None = None,
) -> dict[str, Any]:
    (
        season_id,
        user_id,
        team_id,
        name,
        start_date,
        end_date,
        can_delete,
        created_at,
        updated_at,
    ) = row

    can_remove_map = can_remove_map or {}
    field_ids_list: list[dict] = []
    total_area = 0.0
    for f in (fields or []):
        is_mapped = f.get("isMapped", True)
        if is_mapped:
            total_area += f.get("areaHa") or 0
        field_ids_list.append({
            "id": str(f["id"]),
            "name": f["name"],
            "canRemove": can_remove_map.get(str(f["id"]), False) if is_mapped else False,
            "isMapped": is_mapped,
        })

    return {
        "id": str(season_id),
        "userId": str(user_id),
        "teamId": str(team_id),
        "name": name,
        "startDate": start_date.isoformat() if start_date else None,
        "endDate": end_date.isoformat() if end_date else None,
        "canDelete": can_delete,
        "totalArea": total_area,
        "fieldIds": field_ids_list,
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }
def _season_columns() -> tuple[Any, ...]:
    return (
        Season.season_id,
        Season.user_id,
        Season.team_id,
        Season.name,
        Season.start_date,
        Season.end_date,
        Season.can_delete,
        Season.created_at,
        Season.updated_at,
    )


def _season_field_ids(
    session: Any,
    user_id: uuid.UUID,
    season_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
) -> list[dict]:
    field_stmt = select(Field.id, Field.name, Field.area_ha)
    if team_id is not None:
        field_stmt = field_stmt.where(Field.team_id == team_id)
    else:
        field_stmt = field_stmt.where(Field.user_id == user_id)
    all_fields = session.execute(field_stmt).all()
    mapped_ids = {
        row[0]
        for row in session.execute(
            select(FieldSeason.field_id).where(FieldSeason.season_id == season_id)
        ).all()
    }
    return [
        {
            "id": row.id,
            "name": row.name,
            "areaHa": row.area_ha,
            "isMapped": row.id in mapped_ids,
        }
        for row in all_fields
    ]

def _field_can_remove_map(session: Any, fields: list[dict]) -> dict[str, bool]:
    if not fields:
        return {}
    field_ids = [f["id"] for f in fields]
    rows = session.execute(
        select(FieldSeason.field_id, func.count().label("season_count"))
        .where(FieldSeason.field_id.in_(field_ids))
        .group_by(FieldSeason.field_id)
    ).all()
    return {str(row.field_id): row.season_count > 1 for row in rows}

def _normalize_field_ids(field_ids: list[str] | None) -> list[uuid.UUID]:
    if not field_ids:
        return []
    normalized: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for field_id in field_ids:
        value = _uuid(field_id)
        if value is None or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _validate_field_links(
    session: Any,
    user_id: str | None,
    field_ids: list[uuid.UUID],
    team_id: str | None = None,
) -> None:
    if not field_ids:
        return
    user_uuid = _uuid(user_id)
    stmt = select(Field.id).where(Field.id.in_(field_ids))
    if team_id is not None:
        stmt = stmt.where(Field.team_id == _uuid(team_id))
    else:
        stmt = stmt.where(Field.user_id == user_uuid)
    rows = session.execute(stmt).all()
    found = {row[0] for row in rows}
    missing = [str(field_id) for field_id in field_ids if field_id not in found]
    if missing:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", fieldIds=missing)


def list_seasons(
    user_id: str | None = None,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(*_season_columns()).order_by(
        Season.start_date.nulls_last(), Season.name
    )
    user_uuid = _uuid(user_id)
    if team_id is not None:
        stmt = stmt.where(Season.team_id == _uuid(team_id))
    elif user_id is not None:
        stmt = stmt.where(Season.user_id == user_uuid)
    with session_scope() as session:
        seasons = session.execute(stmt).all()
        results = []
        for row in seasons:
            season_id = row[0]
            field_ids = _season_field_ids(
                session,
                user_uuid,
                season_id,
                _uuid(team_id) if team_id else None,
            )
            mapped_field_ids = [f for f in field_ids if f.get("isMapped")]
            can_remove_map = _field_can_remove_map(session, mapped_field_ids)
            results.append(_row_to_season(row, field_ids, can_remove_map=can_remove_map))
        return results


def get_season(
    season_id: str,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        season_uuid = uuid.UUID(str(season_id))
        user_uuid = _uuid(user_id)
        stmt = select(*_season_columns()).where(Season.season_id == season_uuid)
        if team_id is not None:
            stmt = stmt.where(Season.team_id == _uuid(team_id))
        elif user_id is not None:
            stmt = stmt.where(Season.user_id == user_uuid)
        with session_scope() as session:
            row = session.execute(stmt).first()
            if row is None:
                return None
            field_ids_result = _season_field_ids(
                session,
                user_uuid,
                season_uuid,
                _uuid(team_id) if team_id else None,
            )
            mapped_field_ids = [f for f in field_ids_result if f.get("isMapped")]
            can_remove_map = _field_can_remove_map(session, mapped_field_ids)
            return _row_to_season(row, field_ids_result, can_remove_map=can_remove_map)
    except Exception as exc:
        print(f"Error in get_season: {exc}")
        import traceback
        (traceback.format_exc())

def create_season(
    user_id: str,
    name: str,
    start_date: date | None,
    end_date: date | None,
    can_delete: bool | None = None,
    field_ids: list[str] | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        if team_id is None:
            raise ValueError("TEAM_REQUIRED")
        if can_delete is None:
            count = (
                session.query(Season)
                .filter(Season.team_id == _uuid(team_id))
                .count()
            )
            can_delete = count >= 1

        season = Season(
            user_id=_uuid(user_id),
            team_id=_uuid(team_id),
            name=name,
            start_date=start_date,
            end_date=end_date,
            can_delete=can_delete,
        )
        session.add(season)
        session.flush()

        field_uuids = _normalize_field_ids(field_ids)
        _validate_field_links(session, user_id, field_uuids, team_id)
        for field_uuid in field_uuids:
            session.add(
                FieldSeason(id=uuid.uuid4(), season_id=season.season_id, field_id=field_uuid)
            )

        _recalculate_can_delete(session, user_id, team_id)
        session.refresh(season)
        field_ids_result = _season_field_ids(
            session,
            _uuid(user_id),
            season.season_id,
            _uuid(team_id),
        )
        return _row_to_season(
            (
                season.season_id,
                season.user_id,
                season.team_id,
                season.name,
                season.start_date,
                season.end_date,
                season.can_delete,
                season.created_at,
                season.updated_at,
            ),
            field_ids_result,
        )


def _clamp_vegetation_cycle_dates(
    session: Any,
    season_id: uuid.UUID,
    new_start: date | None,
    new_end: date | None,
    start_changed: bool,
    end_changed: bool,
) -> None:
    if not start_changed and not end_changed:
        return
    cycles = (
        session.query(VegetationCycle)
        .filter(VegetationCycle.season_id == season_id)
        .all()
    )
    modified = False
    for vc in cycles:
        if start_changed and new_start and vc.sowing_date and vc.sowing_date < new_start:
            vc.sowing_date = new_start
            modified = True
        if end_changed and new_end and vc.harvesting_date and vc.harvesting_date > new_end:
            vc.harvesting_date = new_end
            modified = True
    if modified:
        session.flush()


def update_season(
    season_id: str,
    user_id: str | None = None,
    team_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    allowed = {"name", "start_date", "end_date", "can_delete", "fieldIds"}
    values = {key: value for key, value in kwargs.items()
              if key in allowed and (value is not None or key == "fieldIds")}
    with session_scope() as session:
        season = session.execute(
            select(Season).where(
                Season.season_id == _uuid(season_id),
            )
        ).scalar_one_or_none()
        if season is None:
            return None
        if user_id is not None and season.user_id != _uuid(user_id):
            if team_id is None:
                return None
        if team_id is not None and season.team_id != _uuid(team_id):
            return None

        old_start = season.start_date
        old_end = season.end_date

        field_uuids = None
        if "fieldIds" in values:
            field_uuids = _normalize_field_ids(values["fieldIds"])
            _validate_field_links(session, user_id, field_uuids, team_id)

        for key in ("name", "start_date", "end_date", "can_delete"):
            if key in values:
                setattr(season, key, values[key])
        session.flush()

        if field_uuids is not None:
            session.execute(delete(FieldSeason).where(FieldSeason.season_id == season.season_id))
            for field_uuid in field_uuids:
                session.add(
                    FieldSeason(id=uuid.uuid4(), season_id=season.season_id, field_id=field_uuid)
                )
            session.flush()

        season_uuid = _uuid(season_id)
        _clamp_vegetation_cycle_dates(
            session,
            season_uuid,
            season.start_date,
            season.end_date,
            start_changed="start_date" in values and values["start_date"] != old_start,
            end_changed="end_date" in values and values["end_date"] != old_end,
        )

        session.refresh(season)
        field_ids_result = _season_field_ids(
            session,
            season.user_id,
            season.season_id,
            season.team_id,
        )
        return _row_to_season(
            (
                season.season_id,
                season.user_id,
                season.team_id,
                season.name,
                season.start_date,
                season.end_date,
                season.can_delete,
                season.created_at,
                season.updated_at,
            ),
            field_ids_result,
        )


def delete_season(
    season_id: str,
    user_id: str | None = None,
    move_fields_to_season_id: str | None = None,
    team_id: str | None = None,
) -> bool:
    with session_scope() as session:
        season = session.get(Season, _uuid(season_id))
        if season is None:
            return False
        if user_id is not None and season.user_id != _uuid(user_id):
            if team_id is None:
                return False
        if team_id is not None and season.team_id != _uuid(team_id):
            return False

        scope = (
            Season.team_id == season.team_id
            if team_id is not None
            else Season.user_id == season.user_id
        )
        count = session.query(Season).filter(scope).count()
        if count <= 1:
            raise AkashaError(
                "CANNOT_DELETE_SEASON",
                "Season cannot be deleted.",
                409,
                {"seasonId": season_id},
            )

        if move_fields_to_season_id:
            dest_id = _uuid(move_fields_to_season_id)
            field_seasons = (
                session.query(FieldSeason)
                .filter(FieldSeason.season_id == season.season_id)
                .all()
            )
            for fs in field_seasons:
                existing = (
                    session.query(FieldSeason)
                    .filter(
                        FieldSeason.field_id == fs.field_id,
                        FieldSeason.season_id == dest_id,
                    )
                    .first()
                )
                if not existing:
                    session.add(FieldSeason(field_id=fs.field_id, season_id=dest_id))

        session.delete(season)
        session.flush()
        _recalculate_can_delete(session, str(season.user_id), str(season.team_id))
        return True


def _recalculate_can_delete(
    session: Any,
    user_id: str,
    team_id: str | None = None,
) -> None:
    uid = _uuid(user_id)
    team_uuid = _uuid(team_id)
    if team_uuid is not None:
        count = session.query(Season).filter(Season.team_id == team_uuid).count()
    else:
        count = session.query(Season).filter(Season.user_id == uid).count()
    new_flag = count >= 2
    stmt = update(Season)
    stmt = stmt.where(Season.team_id == team_uuid) if team_uuid else stmt.where(Season.user_id == uid)
    session.execute(stmt.values(can_delete=new_flag))
