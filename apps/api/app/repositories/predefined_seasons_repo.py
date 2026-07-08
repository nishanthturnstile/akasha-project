"""List-only queries for predefined_seasons lookup table."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import session_scope
from ..models import PredefinedSeason

logger = logging.getLogger(__name__)


def list_predefined_seasons() -> list[dict]:
    stmt = select(PredefinedSeason).order_by(PredefinedSeason.season_name)
    with session_scope() as session:
        return [
            {
                "id": r.id,
                "season_name": r.season_name,
                "period_start_date": r.period_start_date,
                "period_end_date": r.period_end_date,
                "sowing_start_date": r.sowing_start_date,
                "sowing_end_date": r.sowing_end_date,
                "harvesting_start_date": r.harvesting_start_date,
                "harvesting_end_date": r.harvesting_end_date,
                "main_water_source": r.main_water_source,
            }
            for r in session.execute(stmt).scalars().all()
        ]
