"""Report / leaderboard API Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import ConfigDict, Field

from ..api_models import ApiModel


class LeaderboardScoreComponents(ApiModel):
    vigor: float | None = None
    trend: float | None = None
    recency: float | None = None
    weather: float | None = None


class FieldLeaderboardRow(ApiModel):
    plot_id: str
    rank: int | None = None
    name: str
    field: str
    group_name: str | None = None
    crop_type: str | None = None
    variety: str | None = None
    season_label: str | None = None
    location: str | None = None
    coordinates: list[float] | None = None
    area_ha: float | None = None
    sowing_date: str | None = None
    planting_date: str | None = None
    latest_index_value: float | None = None
    latest_image_date: date | None = None
    index_delta: float | None = None
    previous_image_date: date | None = None
    cloud_free_recency_days: int | None = None
    weather_risk_label: str = "Weather risk pending field weather aggregation"
    weather_risk_level: Literal["unknown"] = "unknown"
    actual_yield: float | None = None
    score: float | None = None
    score_components: LeaderboardScoreComponents = Field(default_factory=LeaderboardScoreComponents)
    data_available: bool
    unavailable_reason: str | None = None
    preview: str | None = None
    open: str | None = None


class FieldLeaderboardResponse(ApiModel):
    index_type: str
    generated_at: str
    rows: list[FieldLeaderboardRow]
    metadata: dict[str, Any]


class ReportTemplatePayload(ApiModel):
    model_config = ConfigDict(alias_generator=None, populate_by_name=True)

    name: str
    columns: list[str] = Field(default_factory=lambda: [
        "rank", "field", "group", "crop", "variety", "location",
        "areaHa", "sowingDate", "latestIndexValue", "indexDelta",
        "cloudFreeRecencyDays", "weatherRiskLabel", "actualYield",
        "latestImageDate", "score", "preview", "open",
    ])
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: dict[str, Any] = Field(default_factory=dict)


class ReportTemplateUpdate(ApiModel):
    model_config = ConfigDict(alias_generator=None, populate_by_name=True)

    name: str | None = None
    columns: list[str] | None = None
    filters: dict[str, Any] | None = None
    sort: dict[str, Any] | None = None


class ReportTemplate(ApiModel):
    id: str
    name: str
    columns: list[str]
    filters: dict[str, Any]
    sort: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None
