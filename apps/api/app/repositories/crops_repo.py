"""List-only queries for reference/lookup tables."""

from __future__ import annotations

import logging

from sqlalchemy import exists, select

from ..db import session_scope
from ..models import Crop, IrrigationType, PredefinedSeason, SeedingType, TillageType, Variety

logger = logging.getLogger(__name__)


def list_irrigation_types() -> list[dict]:
    stmt = select(IrrigationType).order_by(IrrigationType.name)
    with session_scope() as session:
        return [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in session.execute(stmt).scalars().all()
        ]


def list_tillage_types() -> list[dict]:
    stmt = select(TillageType).order_by(TillageType.name)
    with session_scope() as session:
        return [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in session.execute(stmt).scalars().all()
        ]


def list_seeding_types() -> list[dict]:
    stmt = select(SeedingType).order_by(SeedingType.name)
    with session_scope() as session:
        return [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in session.execute(stmt).scalars().all()
        ]


def list_crops() -> list[dict]:
    stmt = select(
        Crop,
        exists().where(Variety.crop_id == Crop.id).label("has_variety"),
    ).order_by(Crop.name)
    with session_scope() as session:
        return [
            {
                "id": r[0].id,
                "name": r[0].name,
                "seeding_type_id": r[0].seeding_type_id,
                "color": r[0].color,
                "maturity_options": r[0].maturity_options,
                "has_weather_risk": r[0].has_weather_risk,
                "has_variety": r[1],
                "bbch_mode": r[0].bbch_mode,
                "characteristic": r[0].characteristic,
            }
            for r in session.execute(stmt).all()
        ]


def get_crop(crop_id: int) -> dict | None:
    stmt = select(
        Crop,
        exists().where(Variety.crop_id == Crop.id).label("has_variety"),
    ).where(Crop.id == crop_id)
    with session_scope() as session:
        row = session.execute(stmt).one_or_none()
        if row is None:
            return None
        r = row[0]
        return {
            "id": r.id,
            "name": r.name,
            "seeding_type_id": r.seeding_type_id,
            "color": r.color,
            "maturity_options": r.maturity_options,
            "has_weather_risk": r.has_weather_risk,
            "has_variety": row[1],
            "bbch_mode": r.bbch_mode,
            "characteristic": r.characteristic,
        }


def list_varieties(crop_id: int, skip: int = 0, limit: int = 100) -> tuple[list[dict], int]:
    stmt = (
        select(Variety)
        .where(Variety.crop_id == crop_id)
        .order_by(Variety.name)
    )
    with session_scope() as session:
        total = session.query(Variety).filter(Variety.crop_id == crop_id).count()
        rows = session.execute(stmt.offset(skip).limit(limit)).scalars().all()
        return [
            {
                "id": r.id,
                "crop_id": r.crop_id,
                "name": r.name,
                "maturity_options": r.maturity_options,
            }
            for r in rows
        ], total


def ensure_reference_data() -> None:
    _TABLES: list[type] = [
        SeedingType,
        IrrigationType,
        TillageType,
        Crop,
        Variety,
        PredefinedSeason,
    ]

    try:
        with session_scope() as session:
            missing = [t for t in _TABLES if session.query(t).first() is None]
    except RuntimeError:
        logger.warning("Database not available — skipping reference data check.")
        return

    if not missing:
        return

    logger.info("Reference data tables missing data: %s", [t.__tablename__ for t in missing])
    from ..bulk_creation import generate_all

    counts = generate_all()
    if counts:
        logger.info("Seeded reference data: %s", counts)
