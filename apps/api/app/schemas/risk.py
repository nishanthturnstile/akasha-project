"""Risk API Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel

RiskLevel = Literal["low", "medium", "high", "unknown"]


class WeatherStressFlags(ApiModel):
    heat: bool | None = None
    dryness: bool | None = None
    excess_rain: bool | None = None


class RiskComponent(ApiModel):
    id: str
    label: str
    available: bool
    level: RiskLevel = "unknown"
    score: float | None = None
    weight: float
    used_in_aggregate: bool
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source: str = "akasha"
    flags: WeatherStressFlags | None = None


class CropStageSummary(ApiModel):
    crop_type: str | None = None
    start_date: date | None = None
    start_date_type: Literal["sowingDate", "plantingDate", "unknown"] = "unknown"
    days_after_start: int | None = None
    stage_label: str = "unknown"
    model_version: str = "generic-v1"
    limitations: list[str] = Field(default_factory=list)


class FieldRiskSummaryResponse(ApiModel):
    plot_id: str
    field_watch_level: RiskLevel
    vegetation_stress_context: str
    score: float | None = None
    components: list[RiskComponent]
    crop_stage: CropStageSummary
    limitations: list[str]
    metadata: dict[str, Any]
