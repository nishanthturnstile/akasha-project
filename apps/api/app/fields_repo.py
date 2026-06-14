"""Field persistence with season linking."""

from __future__ import annotations

import uuid
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import delete, select

from .db import session_scope
from .models import Field, FieldGroup, FieldSeason, Season
from .raster.errors import bad_request, invalid_geometry, not_found


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise bad_request(
            "UUID value is invalid.",
            code="INVALID_UUID",
            value=str(value),
        ) from exc


def _geometry_value(geometry: dict[str, Any]):
    geom = shape(geometry)
    if geom.is_empty or not geom.is_valid:
        raise invalid_geometry(
            "Field geometry must be a valid, non-empty polygon.",
            geometryType=geom.geom_type,
            valid=geom.is_valid,
        )
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise invalid_geometry(
            "Field geometry must be a Polygon or MultiPolygon.",
            geometryType=geom.geom_type,
        )
    return from_shape(geom, srid=4326)


def _geometry_payload(geometry: Any) -> dict[str, Any]:
    if isinstance(geometry, dict):
        return geometry
    return to_shape(geometry).__geo_interface__


def _normalize_season_ids(season_ids: list[str] | None) -> list[uuid.UUID]:
    if not season_ids:
        return []
    normalized: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for season_id in season_ids:
        value = _uuid(season_id)
        if value is None or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _validate_field_group(session: Any, group_id: uuid.UUID | None) -> None:
    if group_id is None:
        return
    row = session.execute(select(FieldGroup.id).where(FieldGroup.id == group_id)).first()
    if row is None:
        raise not_found(
            "Field group not found.",
            code="FIELD_GROUP_NOT_FOUND",
            groupId=str(group_id),
        )


def _validate_season_links(session: Any, user_id: str, season_ids: list[uuid.UUID]) -> None:
    if not season_ids:
        return
    user_uuid = _uuid(user_id)
    rows = session.execute(
        select(Season.season_id).where(
            Season.season_id.in_(season_ids),
            Season.user_id == user_uuid,
        )
    ).all()
    found = {row[0] for row in rows}
    missing = [str(season_id) for season_id in season_ids if season_id not in found]
    if missing:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonIds=missing)


def _row_to_field(row: tuple[Any, ...]) -> dict[str, Any]:
    field, season_ids = row
    return {
        "id": str(field.id),
        "userId": str(field.user_id),
        "name": field.name,
        "areaHa": field.area_ha,
        "geometry": _geometry_payload(field.geometry),
        "groupId": str(field.group_id) if field.group_id else None,
        "seasonIds": [str(sid) for sid in season_ids],
        "createdAt": (
            field.created_at.isoformat().replace("+00:00", "Z")
            if field.created_at
            else None
        ),
        "updatedAt": (
            field.updated_at.isoformat().replace("+00:00", "Z")
            if field.updated_at
            else None
        ),
    }


def _field_season_ids(session, field_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(FieldSeason.season_id).where(FieldSeason.field_id == field_id)
    return [row[0] for row in session.execute(stmt).all()]


def _field_columns() -> tuple[Any, ...]:
    return (Field,)


def create_field(
    user_id: str,
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    group_id: str | None,
    season_ids: list[str] | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        group_uuid = _uuid(group_id) if group_id else None
        season_uuids = _normalize_season_ids(season_ids)
        _validate_field_group(session, group_uuid)
        _validate_season_links(session, user_id, season_uuids)
        field = Field(
            user_id=_uuid(user_id),
            name=name,
            geometry=_geometry_value(geometry),
            area_ha=area_ha,
            group_id=group_uuid,
        )
        # Ensure UUIDs are generated in Python to avoid DB-side gen_random_uuid() errors
        field.id = uuid.uuid4()
        session.add(field)
        session.flush()
        if season_uuids:
            for sid in season_uuids:
                session.add(
                    FieldSeason(id=uuid.uuid4(), field_id=field.id, season_id=sid)
                )
        session.refresh(field)
        return _row_to_field((field, _field_season_ids(session, field.id)))


def list_fields(user_id: str) -> list[dict[str, Any]]:
    stmt = select(Field).order_by(Field.name)
    with session_scope() as session:
        fields = session.execute(stmt).scalars().all()
        results = []
        for field in fields:
            if field.user_id == _uuid(user_id):
                season_ids = _field_season_ids(session, field.id)
                results.append(_row_to_field((field, season_ids)))
        return results


def get_field(field_id: str, user_id: str) -> dict[str, Any] | None:
    stmt = select(Field).where(Field.id == _uuid(field_id))
    with session_scope() as session:
        field = session.execute(stmt).scalar_one_or_none()
        if field is None or field.user_id != _uuid(user_id):
            return None
        return _row_to_field((field, _field_season_ids(session, field.id)))


def update_field(field_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None:
    allowed = {"name", "geometry", "area_ha", "groupId", "seasonIds"}
    values = {
        k: v
        for k, v in kwargs.items()
        if k in allowed and (v is not None or k == "seasonIds")
    }
    with session_scope() as session:
        field = session.execute(
            select(Field).where(
                Field.id == _uuid(field_id),
                Field.user_id == _uuid(user_id),
            )
        ).scalar_one_or_none()
        if field is None:
            return None
        group_uuid = _uuid(values["groupId"]) if values.get("groupId") else None
        if "groupId" in values:
            _validate_field_group(session, group_uuid)
        season_uuids = (
            _normalize_season_ids(values.get("seasonIds"))
            if "seasonIds" in values
            else None
        )
        if season_uuids is not None:
            _validate_season_links(session, user_id, season_uuids)
        for key in ("name", "geometry", "area_ha", "groupId"):
            if key in values:
                if key == "geometry":
                    values[key] = _geometry_value(values[key])
                if key == "groupId":
                    values[key] = group_uuid
                setattr(field, key, values[key])
        session.flush()
        if season_uuids is not None:
            session.execute(delete(FieldSeason).where(FieldSeason.field_id == field.id))
            for sid in season_uuids:
                session.add(
                    FieldSeason(id=uuid.uuid4(), field_id=field.id, season_id=sid)
                )
            session.flush()
        session.refresh(field)
        return _row_to_field((field, _field_season_ids(session, field.id)))


def delete_field(field_id: str, user_id: str) -> bool:
    with session_scope() as session:
        field = session.execute(
            select(Field).where(
                Field.id == _uuid(field_id),
                Field.user_id == _uuid(user_id),
            )
        ).scalar_one_or_none()
        if field is None:
            return False
        # Remove any linked FieldSeason rows first to ensure cleanup
        session.execute(delete(FieldSeason).where(FieldSeason.field_id == field.id))
        session.flush()
        session.delete(field)
        return True
