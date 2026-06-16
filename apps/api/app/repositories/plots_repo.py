"""Plot persistence through SQLAlchemy + PostGIS."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update

from ..db import session_scope
from ..models import Plot

_METADATA_COLUMN_BY_FIELD = {
    "groupName": "group_name",
    "cropType": "crop_type",
    "variety": "variety",
    "seasonLabel": "season_label",
    "sowingDate": "sowing_date",
    "plantingDate": "planting_date",
    "status": "status",
}
_METADATA_FIELDS = tuple(_METADATA_COLUMN_BY_FIELD)


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


def _date_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _metadata_values(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    return {
        column: metadata.get(field)
        for field, column in _METADATA_COLUMN_BY_FIELD.items()
        if field in metadata
    }


def _plot_columns() -> tuple[Any, ...]:
    return (
        Plot.id,
        Plot.name,
        func.ST_AsGeoJSON(Plot.geometry).label("geometry"),
        Plot.area_ha,
        Plot.created_at,
        Plot.updated_at,
        Plot.group_name,
        Plot.crop_type,
        Plot.variety,
        Plot.season_label,
        Plot.sowing_date,
        Plot.planting_date,
        Plot.status,
    )


def _row_to_plot(row: Any) -> dict[str, Any]:
    (
        plot_id,
        name,
        geometry,
        area_ha,
        created_at,
        updated_at,
        group_name,
        crop_type,
        variety,
        season_label,
        sowing_date,
        planting_date,
        status,
    ) = row
    geom = json.loads(geometry) if isinstance(geometry, str) else geometry
    return {
        "id": str(plot_id),
        "name": name,
        "geometry": geom,
        "areaHa": round(float(area_ha), 4) if area_ha is not None else None,
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
        "groupName": group_name,
        "cropType": crop_type,
        "variety": variety,
        "seasonLabel": season_label,
        "sowingDate": _date_iso(sowing_date),
        "plantingDate": _date_iso(planting_date),
        "status": status,
    }


def _team_filter(stmt: Any, team_id: str | None) -> Any:
    if team_id is None:
        return stmt
    return stmt.where(Plot.team_id == _uuid(team_id))


def list_plots(team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(*_plot_columns()).order_by(Plot.created_at.desc(), Plot.id)
    stmt = _team_filter(stmt, team_id)
    with session_scope() as session:
        return [_row_to_plot(row) for row in session.execute(stmt).all()]


def get_plot(plot_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    stmt = select(*_plot_columns()).where(Plot.id == _uuid(plot_id))
    stmt = _team_filter(stmt, team_id)
    with session_scope() as session:
        row = session.execute(stmt).first()
        return _row_to_plot(row) if row else None


def create_plot(
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    metadata: dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return _insert_plot(
            session,
            name,
            geometry,
            area_ha,
            metadata,
            owner_id=owner_id,
            team_id=team_id,
        )


def _insert_plot(
    session: Any,
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    metadata: dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    values = {
        "name": name,
        "geometry": func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326),
        "area_ha": area_ha,
        **{column: None for column in _METADATA_COLUMN_BY_FIELD.values()},
        **_metadata_values(metadata),
    }
    if owner_id is not None:
        values["owner_id"] = _uuid(owner_id)
    if team_id is not None:
        values["team_id"] = _uuid(team_id)
    stmt = insert(Plot).values(**values).returning(*_plot_columns())
    row = session.execute(stmt).first()
    return _row_to_plot(row)


def update_plot(
    plot_id: str,
    name: str | None = None,
    geometry: dict[str, Any] | None = None,
    area_ha: float | None = None,
    metadata: dict[str, Any] | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if geometry is not None:
        values["geometry"] = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
        values["area_ha"] = area_ha
    if metadata is not None:
        for field, column in _METADATA_COLUMN_BY_FIELD.items():
            if field in metadata:
                values[column] = metadata[field]
    if not values:
        return get_plot(plot_id, team_id)

    stmt = (
        update(Plot)
        .where(Plot.id == _uuid(plot_id))
        .values(**values)
        .returning(*_plot_columns())
    )
    stmt = _team_filter(stmt, team_id)
    with session_scope() as session:
        row = session.execute(stmt).first()
        return _row_to_plot(row) if row else None


def delete_plot(plot_id: str, team_id: str | None = None) -> bool:
    stmt = delete(Plot).where(Plot.id == _uuid(plot_id))
    stmt = _team_filter(stmt, team_id)
    with session_scope() as session:
        result = session.execute(stmt)
        return result.rowcount > 0


def create_plots_bulk(
    items: list[dict[str, Any]],
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    with session_scope() as session:
        for item in items:
            created.append(
                _insert_plot(
                    session,
                    item["name"],
                    item["geometry"],
                    item.get("areaHa"),
                    item.get("metadata"),
                    owner_id=owner_id,
                    team_id=team_id,
                )
            )
    return created
