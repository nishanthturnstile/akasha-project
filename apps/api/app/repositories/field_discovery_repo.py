"""Team-scoped, geometry-light field and scouting discovery queries."""

from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, load_only

from ..db import session_scope
from ..discovery_normalization import normalize_search_text
from ..models import (
    Crop,
    Field,
    FieldGroup,
    FieldSeason,
    ScoutTask,
    Season,
    VegetationCycle,
)
from ..raster.errors import not_found

SortMode = Literal[
    "name_asc",
    "name_desc",
    "newest",
    "oldest",
    "area_asc",
    "area_desc",
]


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _valid_uuids(values: list[str]) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for value in values:
        try:
            parsed = _uuid(value)
        except (TypeError, ValueError, AttributeError):
            continue
        if parsed not in seen:
            seen.add(parsed)
            result.append(parsed)
    return result


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _require_season(session: Session, team_id: uuid.UUID, season_id: uuid.UUID) -> None:
    exists = session.execute(
        select(Season.season_id).where(
            Season.season_id == season_id,
            Season.team_id == team_id,
        )
    ).first()
    if exists is None:
        raise not_found("Season not found.", code="SEASON_NOT_FOUND", seasonId=str(season_id))


def _resolved_crop(season_id: uuid.UUID):
    today = date.today()
    active_rank = case(
        (
            and_(
                VegetationCycle.sowing_date.is_not(None),
                VegetationCycle.sowing_date <= today,
                or_(
                    VegetationCycle.harvesting_date.is_(None),
                    VegetationCycle.harvesting_date >= today,
                ),
            ),
            0,
        ),
        else_=1,
    )
    ranked = (
        select(
            VegetationCycle.field_id.label("field_id"),
            VegetationCycle.crop_id.label("crop_id"),
            func.row_number()
            .over(
                partition_by=VegetationCycle.field_id,
                order_by=(
                    active_rank,
                    VegetationCycle.year.desc(),
                    VegetationCycle.sowing_date.desc().nullslast(),
                    VegetationCycle.created_at.desc(),
                    VegetationCycle.id,
                ),
            )
            .label("crop_rank"),
        )
        .where(VegetationCycle.season_id == season_id)
        .subquery("ranked_field_crop")
    )
    return (
        select(ranked.c.field_id, ranked.c.crop_id)
        .where(ranked.c.crop_rank == 1)
        .subquery("resolved_field_crop")
    )


def _bounds_columns():
    normal_box = func.Box2D(Field.geometry)
    shifted_box = func.Box2D(func.ST_ShiftLongitude(Field.geometry))
    return (
        func.ST_XMin(normal_box).label("normal_west"),
        func.ST_YMin(normal_box).label("south"),
        func.ST_XMax(normal_box).label("normal_east"),
        func.ST_YMax(normal_box).label("north"),
        func.ST_XMin(shifted_box).label("shifted_west"),
        func.ST_XMax(shifted_box).label("shifted_east"),
    )


def _field_select(team_id: uuid.UUID, season_id: uuid.UUID) -> tuple[Select[Any], Any]:
    crop = _resolved_crop(season_id)
    stmt = (
        select(
            Field,
            FieldGroup.id.label("group_id"),
            FieldGroup.name.label("group_name"),
            Crop.id.label("crop_id"),
            Crop.name.label("crop_name"),
            *_bounds_columns(),
        )
        .join(
            FieldSeason,
            and_(
                FieldSeason.field_id == Field.id,
                FieldSeason.season_id == season_id,
            ),
        )
        .outerjoin(crop, crop.c.field_id == Field.id)
        .outerjoin(Crop, Crop.id == crop.c.crop_id)
        .outerjoin(
            FieldGroup,
            and_(
                FieldGroup.id == Field.group_id,
                FieldGroup.team_id == team_id,
            ),
        )
        .where(Field.team_id == team_id)
        .options(
            load_only(
                Field.id,
                Field.name,
                Field.area_ha,
                Field.district,
                Field.country,
                Field.created_at,
                Field.updated_at,
                raiseload=True,
            )
        )
    )
    return stmt, crop


def _available_facets(
    session: Session,
    *,
    team_id: uuid.UUID,
    season_id: uuid.UUID,
    target: str,
    status: str | None,
) -> tuple[list[tuple[int, str]], list[tuple[uuid.UUID, str]], bool]:
    crop = _resolved_crop(season_id)
    from_clause = (
        Field.__table__.join(
            FieldSeason.__table__,
            and_(
                FieldSeason.field_id == Field.id,
                FieldSeason.season_id == season_id,
            ),
        )
        .outerjoin(crop, crop.c.field_id == Field.id)
        .outerjoin(Crop.__table__, Crop.id == crop.c.crop_id)
        .outerjoin(
            FieldGroup.__table__,
            and_(FieldGroup.id == Field.group_id, FieldGroup.team_id == team_id),
        )
    )
    conditions = [Field.team_id == team_id]
    if target == "scouting":
        from_clause = from_clause.join(
            ScoutTask.__table__,
            and_(ScoutTask.field_id == Field.id, ScoutTask.team_id == team_id),
        )
        if status:
            conditions.append(ScoutTask.status == status)

    crop_rows = session.execute(
        select(Crop.id, Crop.name)
        .select_from(from_clause)
        .where(*conditions, Crop.id.is_not(None))
        .distinct()
        .order_by(Crop.name, Crop.id)
    ).all()
    group_rows = session.execute(
        select(FieldGroup.id, FieldGroup.name)
        .select_from(from_clause)
        .where(*conditions, FieldGroup.id.is_not(None))
        .distinct()
        .order_by(FieldGroup.name, FieldGroup.id)
    ).all()
    has_ungrouped = (
        session.execute(
            select(Field.id)
            .select_from(from_clause)
            .where(*conditions, Field.group_id.is_(None))
            .limit(1)
        ).first()
        is not None
    )
    return (
        [(int(row.id), row.name) for row in crop_rows],
        [(row.id, row.name) for row in group_rows],
        has_ungrouped,
    )


def get_facets(
    *,
    team_id: str,
    season_id: str,
    target: str,
    status: str | None = None,
) -> dict[str, Any]:
    team_uuid = _uuid(team_id)
    season_uuid = _uuid(season_id)
    with session_scope() as session:
        _require_season(session, team_uuid, season_uuid)
        crops, groups, has_ungrouped = _available_facets(
            session,
            team_id=team_uuid,
            season_id=season_uuid,
            target=target,
            status=status,
        )
        return {
            "crops": [{"id": crop_id, "name": name} for crop_id, name in crops],
            "groups": [{"id": str(group_id), "name": name} for group_id, name in groups],
            "hasUngrouped": has_ungrouped,
        }


def _normalize_filters(
    session: Session,
    *,
    team_id: uuid.UUID,
    season_id: uuid.UUID,
    target: str,
    status: str | None,
    crop_ids: list[int],
    group_ids: list[str],
    include_ungrouped: bool,
    q: str,
    sort: SortMode,
) -> dict[str, Any]:
    crops, groups, has_ungrouped = _available_facets(
        session,
        team_id=team_id,
        season_id=season_id,
        target=target,
        status=status,
    )
    crop_set = {crop_id for crop_id, _ in crops}
    group_set = {group_id for group_id, _ in groups}
    normalized_crops = list(dict.fromkeys(value for value in crop_ids if value in crop_set))
    normalized_groups = [
        value
        for value in _valid_uuids(group_ids)
        if value in group_set
    ]
    return {
        "seasonId": str(season_id),
        "q": q.strip(),
        "cropIds": normalized_crops,
        "groupIds": normalized_groups,
        "includeUngrouped": bool(include_ungrouped and has_ungrouped),
        "sort": sort,
        "status": status,
    }


def _apply_field_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    query = normalize_search_text(filters["q"])
    if query:
        stmt = stmt.where(Field.name_search_key.contains(query))
    if filters["cropIds"]:
        stmt = stmt.where(Crop.id.in_(filters["cropIds"]))
    groups = filters["groupIds"]
    if groups and filters["includeUngrouped"]:
        stmt = stmt.where(or_(Field.group_id.in_(groups), Field.group_id.is_(None)))
    elif groups:
        stmt = stmt.where(Field.group_id.in_(groups))
    elif filters["includeUngrouped"]:
        stmt = stmt.where(Field.group_id.is_(None))
    return stmt


def _field_order(sort: SortMode):
    if sort == "name_desc":
        return (Field.name_sort_key.desc().nullslast(), Field.id)
    if sort == "newest":
        return (Field.created_at.desc(), Field.id)
    if sort == "oldest":
        return (Field.created_at.asc(), Field.id)
    if sort == "area_asc":
        return (Field.area_ha.asc().nullslast(), Field.id)
    if sort == "area_desc":
        return (Field.area_ha.desc().nullslast(), Field.id)
    return (Field.name_sort_key.asc().nullslast(), Field.id)


def _focus_bounds(mapping: Any) -> dict[str, float]:
    normal_west = float(mapping["normal_west"])
    normal_east = float(mapping["normal_east"])
    shifted_west = float(mapping["shifted_west"])
    shifted_east = float(mapping["shifted_east"])
    if shifted_east - shifted_west < normal_east - normal_west:
        west, east = shifted_west, shifted_east
    else:
        west, east = normal_west, normal_east
    return {
        "west": west,
        "south": float(mapping["south"]),
        "east": east,
        "north": float(mapping["north"]),
    }


def _field_summary(row: Any) -> dict[str, Any]:
    mapping = row._mapping
    field: Field = row[0]
    return {
        "id": str(field.id),
        "name": field.name,
        "areaHa": field.area_ha,
        "crop": (
            {"id": int(mapping["crop_id"]), "name": mapping["crop_name"]}
            if mapping["crop_id"] is not None
            else None
        ),
        "group": (
            {"id": str(mapping["group_id"]), "name": mapping["group_name"]}
            if mapping["group_id"] is not None
            else None
        ),
        "district": field.district,
        "country": field.country,
        "createdAt": _iso(field.created_at),
        "updatedAt": _iso(field.updated_at),
        "focusBounds": _focus_bounds(mapping),
    }


def _aggregate_bounds(session: Session, filtered_stmt: Select[Any]) -> dict[str, float] | None:
    fields = filtered_stmt.with_only_columns(
        Field.id.label("field_id"),
        Field.geometry.label("geometry"),
    ).order_by(None).subquery("bounded_fields")
    normal = func.ST_Extent(fields.c.geometry)
    shifted = func.ST_Extent(func.ST_ShiftLongitude(fields.c.geometry))
    row = session.execute(
        select(
            func.ST_XMin(normal).label("normal_west"),
            func.ST_YMin(normal).label("south"),
            func.ST_XMax(normal).label("normal_east"),
            func.ST_YMax(normal).label("north"),
            func.ST_XMin(shifted).label("shifted_west"),
            func.ST_XMax(shifted).label("shifted_east"),
        )
    ).one()
    if row.normal_west is None:
        return None
    return _focus_bounds(row._mapping)


def list_fields(
    *,
    team_id: str,
    season_id: str,
    q: str = "",
    crop_ids: list[int] | None = None,
    group_ids: list[str] | None = None,
    include_ungrouped: bool = False,
    sort: SortMode = "name_asc",
    page: int = 1,
    page_size: int = 20,
    pinned_field_ids: list[str] | None = None,
) -> dict[str, Any]:
    team_uuid = _uuid(team_id)
    season_uuid = _uuid(season_id)
    with session_scope() as session:
        _require_season(session, team_uuid, season_uuid)
        filters = _normalize_filters(
            session,
            team_id=team_uuid,
            season_id=season_uuid,
            target="monitoring",
            status=None,
            crop_ids=crop_ids or [],
            group_ids=group_ids or [],
            include_ungrouped=include_ungrouped,
            q=q,
            sort=sort,
        )
        base, _ = _field_select(team_uuid, season_uuid)
        filtered = _apply_field_filters(base, filters)
        total = int(
            session.execute(
                select(func.count()).select_from(
                    filtered.with_only_columns(Field.id).order_by(None).subquery()
                )
            ).scalar_one()
        )
        rows = session.execute(
            filtered.order_by(*_field_order(sort))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        pinned_ids = _valid_uuids((pinned_field_ids or [])[:50])
        pinned_rows: list[Any] = []
        if pinned_ids:
            pinned_rows = session.execute(
                filtered.where(Field.id.in_(pinned_ids)).order_by(*_field_order(sort))
            ).all()
        return {
            "items": [_field_summary(row) for row in rows],
            "pinnedItems": [_field_summary(row) for row in pinned_rows],
            "appliedFilters": {
                **filters,
                "groupIds": [str(value) for value in filters["groupIds"]],
            },
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": math.ceil(total / page_size) if total else 0,
            "resultBounds": _aggregate_bounds(session, filtered),
        }


def _task_select(team_id: uuid.UUID, season_id: uuid.UUID) -> Select[Any]:
    crop = _resolved_crop(season_id)
    return (
        select(
            ScoutTask,
            Field,
            FieldGroup.id.label("group_id"),
            FieldGroup.name.label("group_name"),
            Crop.id.label("crop_id"),
            Crop.name.label("crop_name"),
            *_bounds_columns(),
        )
        .outerjoin(
            Field,
            and_(Field.id == ScoutTask.field_id, Field.team_id == team_id),
        )
        .outerjoin(
            FieldSeason,
            and_(
                FieldSeason.field_id == Field.id,
                FieldSeason.season_id == season_id,
            ),
        )
        .outerjoin(crop, crop.c.field_id == Field.id)
        .outerjoin(Crop, Crop.id == crop.c.crop_id)
        .outerjoin(
            FieldGroup,
            and_(FieldGroup.id == Field.group_id, FieldGroup.team_id == team_id),
        )
        .where(
            ScoutTask.team_id == team_id,
            or_(Field.id.is_(None), FieldSeason.id.is_not(None)),
        )
        .options(
            load_only(
                ScoutTask.id,
                ScoutTask.status,
                ScoutTask.priority,
                ScoutTask.notes,
                ScoutTask.assignee,
                ScoutTask.longitude,
                ScoutTask.latitude,
                ScoutTask.field_name_snapshot,
                ScoutTask.created_at,
                ScoutTask.updated_at,
                raiseload=True,
            ),
            load_only(
                Field.id,
                Field.name,
                Field.area_ha,
                Field.district,
                Field.country,
                Field.created_at,
                Field.updated_at,
                raiseload=True,
            ),
        )
    )


def _apply_task_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    if filters["status"]:
        stmt = stmt.where(ScoutTask.status == filters["status"])
    query = normalize_search_text(filters["q"])
    if query:
        stmt = stmt.where(Field.name_search_key.contains(query))
    if filters["cropIds"]:
        stmt = stmt.where(Crop.id.in_(filters["cropIds"]))
    groups = filters["groupIds"]
    if groups and filters["includeUngrouped"]:
        stmt = stmt.where(or_(Field.group_id.in_(groups), Field.group_id.is_(None)))
    elif groups:
        stmt = stmt.where(Field.group_id.in_(groups))
    elif filters["includeUngrouped"]:
        stmt = stmt.where(Field.id.is_not(None), Field.group_id.is_(None))
    return stmt


def _task_order(sort: SortMode):
    if sort == "name_desc":
        return (Field.name_sort_key.desc().nullslast(), ScoutTask.id)
    if sort == "newest":
        return (ScoutTask.created_at.desc(), ScoutTask.id)
    if sort == "oldest":
        return (ScoutTask.created_at.asc(), ScoutTask.id)
    if sort == "area_asc":
        return (Field.area_ha.asc().nullslast(), ScoutTask.id)
    if sort == "area_desc":
        return (Field.area_ha.desc().nullslast(), ScoutTask.id)
    return (Field.name_sort_key.asc().nullslast(), ScoutTask.id)


def _task_summary(row: Any) -> dict[str, Any]:
    task: ScoutTask = row[0]
    field: Field | None = row[1]
    field_summary = None
    if field is not None:
        # Re-map the task select so the shared field serializer sees Field at index 0.
        values = list(row)
        values[0] = field
        values.pop(1)
        field_summary = _field_summary(_SyntheticRow(values, row._mapping))
    return {
        "id": str(task.id),
        "status": task.status,
        "priority": task.priority,
        "notes": task.notes,
        "assignee": task.assignee,
        "longitude": task.longitude,
        "latitude": task.latitude,
        "field": field_summary,
        "fieldNameSnapshot": task.field_name_snapshot,
        "findFieldAvailable": field is not None,
        "createdAt": _iso(task.created_at),
        "updatedAt": _iso(task.updated_at),
    }


class _SyntheticRow:
    """Small adapter used to share field serialization between ORM row shapes."""

    def __init__(self, values: list[Any], mapping: Any):
        self._values = values
        self._mapping = mapping

    def __getitem__(self, index: int) -> Any:
        return self._values[index]


def list_scout_tasks(
    *,
    team_id: str,
    season_id: str,
    status: str | None = None,
    q: str = "",
    crop_ids: list[int] | None = None,
    group_ids: list[str] | None = None,
    include_ungrouped: bool = False,
    sort: SortMode = "name_asc",
    page: int = 1,
    page_size: int = 20,
    pinned_field_ids: list[str] | None = None,
) -> dict[str, Any]:
    team_uuid = _uuid(team_id)
    season_uuid = _uuid(season_id)
    with session_scope() as session:
        _require_season(session, team_uuid, season_uuid)
        filters = _normalize_filters(
            session,
            team_id=team_uuid,
            season_id=season_uuid,
            target="scouting",
            status=status,
            crop_ids=crop_ids or [],
            group_ids=group_ids or [],
            include_ungrouped=include_ungrouped,
            q=q,
            sort=sort,
        )
        filtered = _apply_task_filters(_task_select(team_uuid, season_uuid), filters)
        total = int(
            session.execute(
                select(func.count()).select_from(
                    filtered.with_only_columns(ScoutTask.id).order_by(None).subquery()
                )
            ).scalar_one()
        )
        rows = session.execute(
            filtered.order_by(*_task_order(sort))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        pinned_ids = _valid_uuids((pinned_field_ids or [])[:50])
        pinned_items: list[dict[str, Any]] = []
        if pinned_ids:
            field_base, _ = _field_select(team_uuid, season_uuid)
            field_base = _apply_field_filters(field_base, filters)
            pinned_rows = session.execute(
                field_base.where(Field.id.in_(pinned_ids)).order_by(*_field_order(sort))
            ).all()
            pinned_items = [_field_summary(row) for row in pinned_rows]

        bounded = filtered.where(Field.id.is_not(None))
        return {
            "items": [_task_summary(row) for row in rows],
            "pinnedItems": pinned_items,
            "appliedFilters": {
                **filters,
                "groupIds": [str(value) for value in filters["groupIds"]],
            },
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": math.ceil(total / page_size) if total else 0,
            "resultBounds": _aggregate_bounds(session, bounded),
        }


def _viewport_predicate(west: float, south: float, east: float, north: float):
    if east > 180:
        return or_(
            func.ST_Intersects(
                Field.geometry,
                func.ST_MakeEnvelope(west, south, 180.0, north, 4326),
            ),
            func.ST_Intersects(
                Field.geometry,
                func.ST_MakeEnvelope(-180.0, south, east - 360.0, north, 4326),
            ),
        )
    if west > east:
        return or_(
            func.ST_Intersects(
                Field.geometry,
                func.ST_MakeEnvelope(west, south, 180.0, north, 4326),
            ),
            func.ST_Intersects(
                Field.geometry,
                func.ST_MakeEnvelope(-180.0, south, east, north, 4326),
            ),
        )
    return func.ST_Intersects(
        Field.geometry,
        func.ST_MakeEnvelope(west, south, east, north, 4326),
    )


def get_map_features(
    *,
    team_id: str,
    season_id: str,
    target: str,
    west: float,
    south: float,
    east: float,
    north: float,
    zoom: float,
    status: str | None = None,
    q: str = "",
    crop_ids: list[int] | None = None,
    group_ids: list[str] | None = None,
    include_ungrouped: bool = False,
) -> dict[str, Any]:
    team_uuid = _uuid(team_id)
    season_uuid = _uuid(season_id)
    with session_scope() as session:
        _require_season(session, team_uuid, season_uuid)
        filters = _normalize_filters(
            session,
            team_id=team_uuid,
            season_id=season_uuid,
            target=target,
            status=status,
            crop_ids=crop_ids or [],
            group_ids=group_ids or [],
            include_ungrouped=include_ungrouped,
            q=q,
            sort="name_asc",
        )
        if target == "scouting":
            filtered = _apply_task_filters(_task_select(team_uuid, season_uuid), filters)
            task_ids_query = filtered.with_only_columns(ScoutTask.id).order_by(None)
            ids_query = (
                filtered.with_only_columns(Field.id)
                .where(Field.id.is_not(None))
                .order_by(None)
                .distinct()
            )
        else:
            base, _ = _field_select(team_uuid, season_uuid)
            filtered = _apply_field_filters(base, filters)
            ids_query = filtered.with_only_columns(Field.id).order_by(None)
            task_ids_query = None

        tolerance_m = max(0.25, 200000.0 / (2 ** max(0.0, min(24.0, zoom))))
        simplified = func.ST_Transform(
            func.ST_SimplifyPreserveTopology(
                func.ST_Transform(Field.geometry, 3857),
                tolerance_m,
            ),
            4326,
        )
        field_rows = session.execute(
            select(
                Field.id,
                Field.name,
                func.ST_AsGeoJSON(simplified).label("geometry"),
            )
            .where(
                Field.team_id == team_uuid,
                Field.id.in_(ids_query),
                _viewport_predicate(west, south, east, north),
            )
            .order_by(Field.id)
        ).all()
        field_features = [
            {
                "type": "Feature",
                "id": str(row.id),
                "properties": {"id": str(row.id), "name": row.name},
                "geometry": json.loads(row.geometry),
            }
            for row in field_rows
        ]

        task_features: list[dict[str, Any]] = []
        if target == "scouting":
            task_stmt = select(ScoutTask).where(
                ScoutTask.team_id == team_uuid,
                ScoutTask.id.in_(task_ids_query),
                ScoutTask.longitude.is_not(None),
                ScoutTask.latitude.is_not(None),
                ScoutTask.latitude.between(south, north),
            )
            if status:
                task_stmt = task_stmt.where(ScoutTask.status == status)
            if east > 180:
                task_stmt = task_stmt.where(
                    or_(ScoutTask.longitude >= west, ScoutTask.longitude <= east - 360)
                )
            elif west > east:
                task_stmt = task_stmt.where(
                    or_(ScoutTask.longitude >= west, ScoutTask.longitude <= east)
                )
            else:
                task_stmt = task_stmt.where(ScoutTask.longitude.between(west, east))
            for task in session.execute(task_stmt.order_by(ScoutTask.id)).scalars():
                task_features.append(
                    {
                        "type": "Feature",
                        "id": str(task.id),
                        "properties": {
                            "id": str(task.id),
                            "status": task.status,
                            "priority": task.priority,
                            "fieldId": str(task.field_id) if task.field_id else None,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [task.longitude, task.latitude],
                        },
                    }
                )
        return {
            "fields": {"type": "FeatureCollection", "features": field_features},
            "taskPoints": {"type": "FeatureCollection", "features": task_features},
        }
