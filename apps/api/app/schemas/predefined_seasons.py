"""Predefined season response schemas."""

from __future__ import annotations

from datetime import date

from ..api_models import ApiModel


class PredefinedSeasonResponse(ApiModel):
    id: int
    season_name: str
    period_start_date: date | None = None
    period_end_date: date | None = None
    sowing_start_date: date | None = None
    sowing_end_date: date | None = None
    harvesting_start_date: date | None = None
    harvesting_end_date: date | None = None
    main_water_source: str | None = None
