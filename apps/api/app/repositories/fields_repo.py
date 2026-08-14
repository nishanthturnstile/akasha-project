"""Field persistence with season linking."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import delete, select

from ..config import settings
from ..db import session_scope
from ..discovery_normalization import natural_sort_key, normalize_search_text
from ..models import (
    AppSetting,
    Crop,
    CropGrowthStage,
    Field,
    FieldGroup,
    FieldSeason,
    IrrigationType,
    Season,
    TillageType,
    Variety,
    VegetationCycle,
    VegetationCycleGrowthStage,
)
from ..raster.errors import bad_request, invalid_geometry, not_found
from ..raster.geo_validate import validate_polygon


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


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value)).date()


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


def _validated_geometry_facts(geometry: dict[str, Any]) -> dict[str, Any]:
    facts = validate_polygon(
        geometry,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
    )
    if facts["areaHa"] <= 0:
        raise invalid_geometry("Field geometry must have a non-zero geodesic area.")
    return facts


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


def _validate_field_group(
    session: Any,
    group_id: uuid.UUID | None,
    team_id: str | uuid.UUID | None = None,
) -> None:
    if group_id is None:
        return
    stmt = select(FieldGroup.id).where(FieldGroup.id == group_id)
    if team_id is not None:
        stmt = stmt.where(FieldGroup.team_id == _uuid(team_id))
    row = session.execute(stmt).first()
    if row is None:
        raise not_found(
            "Field group not found.",
            code="FIELD_GROUP_NOT_FOUND",
            groupId=str(group_id),
        )


def _validate_season_links(
    session: Any,
    user_id: str,
    season_ids: list[uuid.UUID],
    team_id: str | None = None,
) -> None:
    if not season_ids:
        return
    user_uuid = _uuid(user_id)
    stmt = select(Season.season_id).where(Season.season_id.in_(season_ids))
    if team_id is not None:
        stmt = stmt.where(Season.team_id == _uuid(team_id))
    else:
        stmt = stmt.where(Season.user_id == user_uuid)
    rows = session.execute(stmt).all()
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
    growth_stages: list[dict[str, Any]] | None = None,
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
        "growthStages": growth_stages or [],
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


def _growth_stage_data(
    session: Any, cycles: list[Any]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    if not cycles:
        return {}

    cycle_ids = [cycle.id for cycle in cycles]
    saved_rows = session.execute(
        select(VegetationCycleGrowthStage)
        .where(VegetationCycleGrowthStage.vegetation_cycle_id.in_(cycle_ids))
        .order_by(
            VegetationCycleGrowthStage.vegetation_cycle_id,
            VegetationCycleGrowthStage.seq,
        )
    ).scalars().all()
    saved_by_cycle: dict[uuid.UUID, dict[int, VegetationCycleGrowthStage]] = {}
    for stage in saved_rows:
        saved_by_cycle.setdefault(stage.vegetation_cycle_id, {})[stage.seq] = stage

    crop_ids = {cycle.crop_id for cycle in cycles}
    templates = session.execute(
        select(CropGrowthStage)
        .where(CropGrowthStage.crop_id.in_(crop_ids))
        .order_by(CropGrowthStage.crop_id, CropGrowthStage.seq)
    ).scalars().all()
    templates_by_crop: dict[int, list[CropGrowthStage]] = {}
    for template in templates:
        templates_by_crop.setdefault(template.crop_id, []).append(template)

    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for cycle in cycles:
        result[cycle.id] = [
            {
                "id": str(saved_by_cycle[cycle.id][template.seq].id)
                if template.seq in saved_by_cycle.get(cycle.id, {})
                else None,
                "cropId": cycle.crop_id,
                "seq": template.seq,
                "name": template.name,
                "duration": template.duration,
                "startDate": (
                    saved_by_cycle[cycle.id][template.seq].start_date.isoformat()
                    if template.seq in saved_by_cycle.get(cycle.id, {})
                    and saved_by_cycle[cycle.id][template.seq].start_date
                    else None
                ),
                "saved": template.seq in saved_by_cycle.get(cycle.id, {}),
            }
            for template in templates_by_crop.get(cycle.crop_id, [])
        ]
    return result


def _harvest_template(templates: list[CropGrowthStage]) -> CropGrowthStage | None:
    return next(
        (
            template
            for template in templates
            if any(
                keyword in template.name.casefold()
                for keyword in ("harvest", "cutting", "tapping")
            )
        ),
        None,
    )


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
    cycles = [row[0] for row in rows]
    stages_by_cycle = _growth_stage_data(session, cycles)
    return [
        _veg_cycle_to_dict(
            row[0],
            season_name=row[1],
            crop_name=row[2],
            variety_name=row[3],
            irrigation_type_name=row[4],
            tillage_type_name=row[5],
            growth_stages=stages_by_cycle.get(row[0].id, []),
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
    cycles = [row[0] for row in rows]
    stages_by_cycle = _growth_stage_data(session, cycles)
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
            growth_stages=stages_by_cycle.get(vc.id, []),
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
        harvesting_date = _date_value(item.get("harvestingDate"))
        cycle = VegetationCycle(
            id=uuid.uuid4(),
            field_id=field_id,
            season_id=_uuid(item["seasonId"]),
            year=item["year"],
            crop_id=item["cropType"],
            variety_id=item.get("cropVariety"),
            sowing_date=item.get("sowingDate"),
            harvesting_date=harvesting_date,
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
        session.add(cycle)
        session.flush()
        if harvesting_date:
            templates = session.execute(
                select(CropGrowthStage)
                .where(CropGrowthStage.crop_id == cycle.crop_id)
                .order_by(CropGrowthStage.seq)
            ).scalars().all()
            harvest_template = _harvest_template(templates)
            if harvest_template:
                session.add(
                    VegetationCycleGrowthStage(
                        id=uuid.uuid4(),
                        vegetation_cycle_id=cycle.id,
                        crop_id=cycle.crop_id,
                        seq=harvest_template.seq,
                        name=harvest_template.name,
                        duration=harvest_template.duration,
                        start_date=cycle.harvesting_date,
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
        "teamId": str(field.team_id),
        "name": field.name,
        "areaHa": field.area_ha,
        "geometry": _geometry_payload(field.geometry),
        "groupId": str(field.group_id) if field.group_id else None,
        "district": field.district,
        "country": field.country,
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
            setting.updated_at = datetime.now(UTC)

        return next_number


def create_field(
    user_id: str,
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    group_id: str | None,
    season_ids: list[str] | None = None,
    vegetation_data: list[dict[str, Any]] | None = None,
    team_id: str | None = None,
    district: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        if team_id is None:
            raise bad_request("Current team is required.", code="TEAM_REQUIRED")
        group_uuid = _uuid(group_id) if group_id else None
        season_uuids = _normalize_season_ids(season_ids)
        veg_data = vegetation_data or []
        _validate_field_group(session, group_uuid, team_id)
        _validate_season_links(session, user_id, season_uuids, team_id)
        _validate_vegetation_cycles(session, user_id, veg_data, season_uuids)
        geometry_facts = _validated_geometry_facts(geometry)
        field = Field(
            user_id=_uuid(user_id),
            team_id=_uuid(team_id),
            name=name,
            name_search_key=normalize_search_text(name),
            name_sort_key=natural_sort_key(name),
            geometry=_geometry_value(geometry),
            area_ha=geometry_facts["areaHa"],
            group_id=group_uuid,
            district=district.strip() if district and district.strip() else None,
            country=country.strip() if country and country.strip() else None,
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


def list_fields(user_id: str, team_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Field).order_by(Field.name_sort_key, Field.id)
    if team_id is not None:
        stmt = stmt.where(Field.team_id == _uuid(team_id))
    else:
        stmt = stmt.where(Field.user_id == _uuid(user_id))
    with session_scope() as session:
        fields = session.execute(stmt).scalars().all()
        user_uuid = _uuid(user_id)
        all_season_ids: set[uuid.UUID] = set()
        field_season_ids: dict[uuid.UUID, list[uuid.UUID]] = {}
        field_ids: list[uuid.UUID] = []
        for field in fields:
            if team_id is not None or field.user_id == user_uuid:
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
            if team_id is not None or field.user_id == user_uuid:
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


def get_field(field_id: str, user_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    stmt = select(Field).where(Field.id == _uuid(field_id))
    with session_scope() as session:
        field = session.execute(stmt).scalar_one_or_none()
        if field is None:
            return None
        if team_id is not None and field.team_id != _uuid(team_id):
            return None
        if team_id is None and field.user_id != _uuid(user_id):
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


def update_field(
    field_id: str,
    user_id: str,
    *,
    team_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    allowed = {
        "name",
        "geometry",
        "area_ha",
        "groupId",
        "seasonIds",
        "vegetationData",
        "district",
        "country",
    }
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
                (
                    Field.team_id == _uuid(team_id)
                    if team_id is not None
                    else Field.user_id == _uuid(user_id)
                ),
            )
        ).scalar_one_or_none()
        if field is None:
            return None
        group_uuid = _uuid(values["groupId"]) if values.get("groupId") else None
        if "groupId" in values:
            _validate_field_group(session, group_uuid, team_id)
        season_uuids = (
            _normalize_season_ids(values.get("seasonIds"))
            if "seasonIds" in values
            else None
        )
        if season_uuids is not None:
            _validate_season_links(session, user_id, season_uuids, team_id)
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
        for key in ("name", "geometry", "groupId", "district", "country"):
            if key in values:
                if key == "geometry":
                    values["area_ha"] = _validated_geometry_facts(values[key])["areaHa"]
                    values[key] = _geometry_value(values[key])
                if key == "groupId":
                    field.group_id = group_uuid
                    continue
                if key in {"district", "country"}:
                    setattr(field, key, values[key].strip() if values[key] else None)
                    continue
                setattr(field, key, values[key])
        if "name" in values:
            field.name_search_key = normalize_search_text(values["name"])
            field.name_sort_key = natural_sort_key(values["name"])
        if "area_ha" in values:
            field.area_ha = values["area_ha"]
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
    field_id: str, user_id: str, season_id: str, team_id: str | None = None
) -> list[dict[str, Any]]:
    with session_scope() as session:
        field = session.execute(
            select(Field.id).where(
                Field.id == _uuid(field_id),
                (
                    Field.team_id == _uuid(team_id)
                    if team_id is not None
                    else Field.user_id == _uuid(user_id)
                ),
            )
        ).first()
        if field is None:
            return []
        return _vegetation_cycle_data(session, _uuid(field_id), _uuid(season_id))


def update_vegetation_cycle_growth_stages(
    cycle_id: str,
    user_id: str,
    stages: list[dict[str, Any]],
    team_id: str | None = None,
) -> list[dict[str, Any]] | None:
    cycle_uuid = _uuid(cycle_id)
    with session_scope() as session:
        cycle = session.execute(
            select(VegetationCycle)
            .join(Field, VegetationCycle.field_id == Field.id)
            .where(
                VegetationCycle.id == cycle_uuid,
                (
                    Field.team_id == _uuid(team_id)
                    if team_id is not None
                    else Field.user_id == _uuid(user_id)
                ),
            )
        ).scalar_one_or_none()
        if cycle is None:
            return None

        templates = session.execute(
            select(CropGrowthStage)
            .where(CropGrowthStage.crop_id == cycle.crop_id)
            .order_by(CropGrowthStage.seq)
        ).scalars().all()
        template_by_seq = {template.seq: template for template in templates}
        harvest_template = _harvest_template(templates)
        requested_by_seq = {item["seq"]: item.get("startDate") for item in stages}
        unknown = sorted(set(requested_by_seq) - set(template_by_seq))
        if unknown:
            raise bad_request(
                "One or more growth stages do not belong to this crop.",
                code="GROWTH_STAGE_NOT_FOUND",
                sequences=unknown,
            )

        parsed_dates: dict[int, Any] = {}
        for seq, value in requested_by_seq.items():
            if value is None or value == "":
                parsed_dates[seq] = None
                continue
            try:
                parsed_dates[seq] = datetime.fromisoformat(value).date()
            except (TypeError, ValueError) as exc:
                raise bad_request(
                    "Growth-stage start dates must use YYYY-MM-DD.",
                    code="INVALID_GROWTH_STAGE_DATE",
                    seq=seq,
                ) from exc

        if harvest_template and harvest_template.seq in parsed_dates:
            cycle.harvesting_date = parsed_dates[harvest_template.seq]

        existing = session.execute(
            select(VegetationCycleGrowthStage)
            .where(VegetationCycleGrowthStage.vegetation_cycle_id == cycle.id)
            .order_by(VegetationCycleGrowthStage.seq)
        ).scalars().all()
        merged_dates = {stage.seq: stage.start_date for stage in existing}
        merged_dates.update(parsed_dates)
        ordered_dates = [
            merged_dates[seq]
            for seq in sorted(merged_dates)
            if merged_dates[seq]
        ]
        if any(
            left >= right
            for left, right in zip(ordered_dates, ordered_dates[1:], strict=False)
        ):
            raise bad_request(
                "Growth-stage start dates must be strictly after the previous stage.",
                code="GROWTH_STAGE_DATE_ORDER_INVALID",
            )

        if not existing:
            for template in templates:
                session.add(
                    VegetationCycleGrowthStage(
                        id=uuid.uuid4(),
                        vegetation_cycle_id=cycle.id,
                        crop_id=cycle.crop_id,
                        seq=template.seq,
                        name=template.name,
                        duration=template.duration,
                        start_date=parsed_dates.get(template.seq),
                    )
                )
        else:
            existing_by_seq = {stage.seq: stage for stage in existing}
            for template in templates:
                if template.seq not in existing_by_seq:
                    stage = VegetationCycleGrowthStage(
                        id=uuid.uuid4(),
                        vegetation_cycle_id=cycle.id,
                        crop_id=cycle.crop_id,
                        seq=template.seq,
                        name=template.name,
                        duration=template.duration,
                        start_date=None,
                    )
                    session.add(stage)
                    existing_by_seq[template.seq] = stage
            for seq, value in parsed_dates.items():
                existing_by_seq[seq].start_date = value

        session.flush()
        return _growth_stage_data(session, [cycle])[cycle.id]


def delete_field(field_id: str, user_id: str, team_id: str | None = None) -> bool:
    with session_scope() as session:
        field = session.execute(
            select(Field).where(
                Field.id == _uuid(field_id),
                (
                    Field.team_id == _uuid(team_id)
                    if team_id is not None
                    else Field.user_id == _uuid(user_id)
                ),
            )
        ).scalar_one_or_none()
        if field is None:
            return False
        # Remove any linked FieldSeason rows first to ensure cleanup
        session.execute(delete(FieldSeason).where(FieldSeason.field_id == field.id))
        session.flush()
        session.delete(field)
        return True
