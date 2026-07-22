"""List-only queries for reference/lookup tables."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import session_scope
from ..models import Crop, IrrigationType, SeedingType, TillageType, Variety

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
    stmt = select(Crop).order_by(Crop.name)
    with session_scope() as session:
        return [
            {
                "id": r.id,
                "name": r.name,
                "seeding_type_id": r.seeding_type_id,
                "color": r.color,
                "maturity_options": r.maturity_options,
                "has_weather_risk": r.has_weather_risk,
                "has_variety": r.has_variety,
                "bbch_mode": r.bbch_mode,
                "characteristic": r.characteristic,
            }
            for r in session.execute(stmt).scalars().all()
        ]


def get_crop(crop_id: int) -> dict | None:
    stmt = select(Crop).where(Crop.id == crop_id)
    with session_scope() as session:
        r = session.execute(stmt).scalar_one_or_none()
        if r is None:
            return None
        return {
            "id": r.id,
            "name": r.name,
            "seeding_type_id": r.seeding_type_id,
            "color": r.color,
            "maturity_options": r.maturity_options,
            "has_weather_risk": r.has_weather_risk,
            "has_variety": r.has_variety,
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
    from ..bulk_creation import generate_all

    try:
        with session_scope() as session:
            has_seeding = session.query(SeedingType).first() is not None
    except RuntimeError:
        logger.warning("Database not available — skipping reference data check.")
        return

    if not has_seeding:
        logger.info("Reference data tables empty — seeding all.")
        counts = generate_all()
        if counts:
            logger.info("Seeded reference data: %s", counts)
        return

    # Seeding types exist — just ensure crops are in sync via row-count check
    from ..bulk_creation import generate_crops
    with session_scope() as session:
        count = generate_crops(session)
        if count:
            logger.info("Crops refreshed: %s inserted.", count)
