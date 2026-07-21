"""Field persistence with season linking."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import (
    AppSetting,
    Crop,
    Field,
    FieldGroup,
    FieldSeason,
    IrrigationType,
    Season,
    TillageType,
    Variety,
    VegetationCycle,
)
from ..raster.errors import AkashaError, bad_request, invalid_geometry, not_found


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


def _field_season_data(session, season_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    if not season_ids:
        return {}
    rows = session.execute(
        select(Season.season_id, Season.name, Season.can_delete).where(
            Season.season_id.in_(season_ids)
        )
    ).all()
    return {
        row.season_id: {"name": row.name, "can_delete": row.can_delete}
        for row in rows
    }


def _validate_vegetation_cycles(
    session: Any,
    user_id: str,
    vegetation_data: list[dict[str, Any]],
    season_uuids: list[uuid.UUID],
) -> None:
    if not vegetation_data:
        return
    for item in vegetation_data:
        sid = _uuid(item.get("seasonId"))
        if sid is None or sid not in season_uuids:
            raise bad_request(
                "Vegetation cycle references a season not linked to the field.",
                code="INVALID_VEG_CYCLE_SEASON",
                seasonId=str(item.get("seasonId")),
            )
        crop_id = item.get("cropType")
        if crop_id is None:
            raise bad_request(
                "Vegetation cycle crop type is required.",
                code="MISSING_CROP_TYPE",
            )
        row = session.execute(select(Crop.id).where(Crop.id == crop_id)).first()
        if row is None:
            raise not_found(
                "Crop not found.",
                code="CROP_NOT_FOUND",
                cropType=crop_id,
            )
        variety_id = item.get("cropVariety")
        if variety_id is not None:
            row = session.execute(
                select(Variety.id).where(
                    Variety.id == variety_id, Variety.crop_id == crop_id
                )
            ).first()
            if row is None:
                raise not_found(
                    "Variety not found for the given crop.",
                    code="VARIETY_NOT_FOUND",
                    cropType=crop_id,
                    cropVariety=variety_id,
                )
        irr_id = item.get("irrigationType")
        if irr_id is not None:
            row = session.execute(
                select(IrrigationType.id).where(IrrigationType.id == irr_id)
            ).first()
            if row is None:
                raise not_found(
                    "Irrigation type not found.",
                    code="IRRIGATION_TYPE_NOT_FOUND",
                    irrigationType=irr_id,
                )
        till_id = item.get("tillageType")
        if till_id is not None:
            row = session.execute(
                select(TillageType.id).where(TillageType.id == till_id)
            ).first()
            if row is None:
                raise not_found(
                    "Tillage type not found.",
                    code="TILLAGE_TYPE_NOT_FOUND",
                    tillageType=till_id,
                )


def _veg_cycle_to_dict(
    row: Any,
    season_name: str | None = None,
    crop_name: str | None = None,
    variety_name: str | None = None,
    irrigation_type_name: str | None = None,
    tillage_type_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "fieldId": str(row.field_id),
        "seasonId": str(row.season_id),
        "seasonName": season_name,
        "year": row.year,
        "cropType": row.crop_id,
        "cropName": crop_name,
        "cropVariety": row.variety_id,
        "varietyName": variety_name,
        "sowingDate": row.sowing_date.isoformat() if row.sowing_date else None,
        "harvestingDate": row.harvesting_date.isoformat() if row.harvesting_date else None,
        "targetYield": row.target_yield,
        "actualYield": row.actual_yield,
        "irrigationType": row.irrigation_type_id,
        "irrigationTypeName": irrigation_type_name,
        "tillageType": row.tillage_type_id,
        "tillageTypeName": tillage_type_name,
        "maturity": row.maturity,
        "fertilizer": row.fertilizer,
        "hybrid": row.hybrid,
        "ndviList": row.ndvi_list,
        "notes": row.notes,
        "isCutOff": row.is_cut_off,
        "createdAt": (
            row.created_at.isoformat().replace("+00:00", "Z")
            if row.created_at
            else None
        ),
        "updatedAt": (
            row.updated_at.isoformat().replace("+00:00", "Z")
            if row.updated_at
            else None
        ),
    }


def _vegetation_cycle_data(
    session: Any, field_id: uuid.UUID, season_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    stmt = (
        select(
            VegetationCycle,
            Season.name,
            Crop.name,
            Variety.name,
            IrrigationType.name,
            TillageType.name,
        )
        .where(VegetationCycle.field_id == field_id)
        .join(Season, VegetationCycle.season_id == Season.season_id)
        .join(Crop, VegetationCycle.crop_id == Crop.id)
        .outerjoin(Variety, VegetationCycle.variety_id == Variety.id)
        .outerjoin(
            IrrigationType, VegetationCycle.irrigation_type_id == IrrigationType.id
        )
        .outerjoin(TillageType, VegetationCycle.tillage_type_id == TillageType.id)
    )
    if season_id is not None:
        stmt = stmt.where(VegetationCycle.season_id == season_id)
    stmt = stmt.order_by(VegetationCycle.created_at)
    rows = session.execute(stmt).all()
    return [
        _veg_cycle_to_dict(
            row[0],
            season_name=row[1],
            crop_name=row[2],
            variety_name=row[3],
            irrigation_type_name=row[4],
            tillage_type_name=row[5],
        )
        for row in rows
    ]


def _vegetation_cycle_data_bulk(
    session: Any, field_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    if not field_ids:
        return {}
    rows = session.execute(
        select(
            VegetationCycle,
            Season.name,
            Crop.name,
            Variety.name,
            IrrigationType.name,
            TillageType.name,
        )
        .where(VegetationCycle.field_id.in_(field_ids))
        .join(Season, VegetationCycle.season_id == Season.season_id)
        .join(Crop, VegetationCycle.crop_id == Crop.id)
        .outerjoin(Variety, VegetationCycle.variety_id == Variety.id)
        .outerjoin(
            IrrigationType, VegetationCycle.irrigation_type_id == IrrigationType.id
        )
        .outerjoin(TillageType, VegetationCycle.tillage_type_id == TillageType.id)
        .order_by(VegetationCycle.created_at)
    ).all()
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        vc = row[0]
        entry = _veg_cycle_to_dict(
            vc,
            season_name=row[1],
            crop_name=row[2],
            variety_name=row[3],
            irrigation_type_name=row[4],
            tillage_type_name=row[5],
        )
        result.setdefault(vc.field_id, []).append(entry)
    return result


def _insert_vegetation_cycles(
    session: Any,
    field_id: uuid.UUID,
    user_id: uuid.UUID,
    vegetation_data: list[dict[str, Any]],
) -> None:
    if not vegetation_data:
        return
    for item in vegetation_data:
        session.add(
            VegetationCycle(
                id=uuid.uuid4(),
                field_id=field_id,
                season_id=_uuid(item["seasonId"]),
                year=item["year"],
                crop_id=item["cropType"],
                variety_id=item.get("cropVariety"),
                sowing_date=item.get("sowingDate"),
                harvesting_date=item.get("harvestingDate"),
                target_yield=item.get("targetYield"),
                actual_yield=item.get("actualYield"),
                irrigation_type_id=item.get("irrigationType"),
                tillage_type_id=item.get("tillageType"),
                maturity=item.get("maturity"),
                fertilizer=item.get("fertilizer"),
                hybrid=item.get("hybrid"),
                ndvi_list=item.get("ndviList"),
                notes=item.get("notes"),
                is_cut_off=item.get("isCutOff"),
                user_id=user_id,
            )
        )


def _row_to_field(
    field: Any,
    season_data: dict[uuid.UUID, dict[str, Any]],
    veg_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(field.id),
        "userId": str(field.user_id),
        "name": field.name,
        "areaHa": field.area_ha,
        "geometry": _geometry_payload(field.geometry),
        "groupId": str(field.group_id) if field.group_id else None,
        "seasonIds": [str(sid) for sid in season_data],
        "seasons": [
            {
                "seasonId": str(sid),
                "name": v["name"],
                "canDelete": v["can_delete"],
            }
            for sid, v in season_data.items()
        ],
        "vegetationData": veg_data or [],
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


def _field_columns() -> tuple[Any, ...]:
    return (Field,)


def _validate_field_name_unique(
    session: Session,
    user_id: str,
    name: str,
    exclude_field_id: str | None = None,
) -> None:
    stmt = select(Field).where(
        Field.user_id == _uuid(user_id),
        Field.name == name,
    )
    if exclude_field_id is not None:
        stmt = stmt.where(Field.id != _uuid(exclude_field_id))
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        raise AkashaError(
            "DUPLICATE_FIELD_NAME",
            f'A field named "{name}" already exists.',
            409,
        )


def get_next_field_number(user_id: str) -> int:
    """Return the next auto-incremented field number for naming (Field N).

    The counter is stored in ``app_settings`` keyed by user so it persists
    across field deletions — numbers are never reused for the same user.
    """
    key = f"max_field_number:{user_id}"
    with session_scope() as session:
        setting = session.execute(
            select(AppSetting).where(AppSetting.key == key)
        ).scalar_one_or_none()
        stored_max: int = setting.value if setting else 0

        # Scan existing fields for highest number used
        real_max = 0
        for f in session.execute(
            select(Field).where(Field.user_id == _uuid(user_id))
        ).scalars().all():
            if f.name == "Field":
                real_max = max(real_max, 0)
            else:
                m = re.match(r"^Field (\d+)$", f.name)
                if m:
                    real_max = max(real_max, int(m.group(1)))

        next_number = max(stored_max, real_max) + 1

        if setting is None:
            setting = AppSetting(key=key, value=next_number)
            session.add(setting)
        else:
            setting.value = next_number
            setting.updated_at = datetime.now(timezone.utc)

        return next_number


def create_field(
    user_id: str,
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    group_id: str | None,
    season_ids: list[str] | None = None,
    vegetation_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        group_uuid = _uuid(group_id) if group_id else None
        season_uuids = _normalize_season_ids(season_ids)
        veg_data = vegetation_data or []
        _validate_field_group(session, group_uuid)
        _validate_season_links(session, user_id, season_uuids)
        _validate_vegetation_cycles(session, user_id, veg_data, season_uuids)
        _validate_field_name_unique(session, user_id, name)
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
        _insert_vegetation_cycles(session, field.id, _uuid(user_id), veg_data)
        session.flush()
        session.refresh(field)
        sids = [
            row[0]
            for row in session.execute(
                select(FieldSeason.season_id).where(FieldSeason.field_id == field.id)
            ).all()
        ]
        season_data = _field_season_data(session, sids)
        veg_rows = _vegetation_cycle_data(session, field.id)
        return _row_to_field(field, season_data, veg_rows)


def list_fields(user_id: str) -> list[dict[str, Any]]:
    stmt = select(Field).order_by(Field.name)
    with session_scope() as session:
        fields = session.execute(stmt).scalars().all()
        user_uuid = _uuid(user_id)
        all_season_ids: set[uuid.UUID] = set()
        field_season_ids: dict[uuid.UUID, list[uuid.UUID]] = {}
        field_ids: list[uuid.UUID] = []
        for field in fields:
            if field.user_id == user_uuid:
                field_ids.append(field.id)
                sids = [
                    row[0]
                    for row in session.execute(
                        select(FieldSeason.season_id).where(
                            FieldSeason.field_id == field.id
                        )
                    ).all()
                ]
                field_season_ids[field.id] = sids
                all_season_ids.update(sids)
        season_data = _field_season_data(session, list(all_season_ids))
        veg_by_field = _vegetation_cycle_data_bulk(session, field_ids)
        results = []
        for field in fields:
            if field.user_id == user_uuid:
                sids = field_season_ids.get(field.id, [])
                field_season_data = {
                    sid: season_data[sid] for sid in sids if sid in season_data
                }
                results.append(
                    _row_to_field(
                        field,
                        field_season_data,
                        veg_by_field.get(field.id, []),
                    )
                )
        return results


def get_field(field_id: str, user_id: str) -> dict[str, Any] | None:
    stmt = select(Field).where(Field.id == _uuid(field_id))
    with session_scope() as session:
        field = session.execute(stmt).scalar_one_or_none()
        if field is None or field.user_id != _uuid(user_id):
            return None
        sids = [
            row[0]
            for row in session.execute(
                select(FieldSeason.season_id).where(FieldSeason.field_id == field.id)
            ).all()
        ]
        season_data = _field_season_data(session, sids)
        veg_rows = _vegetation_cycle_data(session, field.id)
        return _row_to_field(field, season_data, veg_rows)


def update_field(field_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None:
    allowed = {"name", "geometry", "area_ha", "groupId", "seasonIds", "vegetationData"}
    values = {
        k: v
        for k, v in kwargs.items()
        if k in allowed
        and (v is not None or k in ("seasonIds", "vegetationData"))
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
        veg_data = values.get("vegetationData")
        if veg_data is not None:
            effective_season_uuids = (
                season_uuids
                if season_uuids is not None
                else [
                    row[0]
                    for row in session.execute(
                        select(FieldSeason.season_id).where(
                            FieldSeason.field_id == field.id
                        )
                    ).all()
                ]
            )
            _validate_vegetation_cycles(
                session, user_id, veg_data, effective_season_uuids
            )
        if "name" in values and values["name"] != field.name:
            _validate_field_name_unique(session, user_id, values["name"], exclude_field_id=field_id)
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
        if veg_data is not None:
            session.execute(
                delete(VegetationCycle).where(VegetationCycle.field_id == field.id)
            )
            _insert_vegetation_cycles(session, field.id, _uuid(user_id), veg_data)
            session.flush()
        session.refresh(field)
        sids = [
            row[0]
            for row in session.execute(
                select(FieldSeason.season_id).where(FieldSeason.field_id == field.id)
            ).all()
        ]
        season_data = _field_season_data(session, sids)
        veg_rows = _vegetation_cycle_data(session, field.id)
        return _row_to_field(field, season_data, veg_rows)


def list_vegetation_cycles(
    field_id: str, user_id: str, season_id: str
) -> list[dict[str, Any]]:
    with session_scope() as session:
        field = session.execute(
            select(Field.id).where(
                Field.id == _uuid(field_id),
                Field.user_id == _uuid(user_id),
            )
        ).first()
        if field is None:
            return []
        return _vegetation_cycle_data(session, _uuid(field_id), _uuid(season_id))


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
