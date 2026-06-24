"""Field API Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..api_models import ApiModel


class SeasonItem(ApiModel):
    season_id: str
    name: str
    can_delete: bool = True


class VegetationCycleCreate(ApiModel):
    season_id: str
    year: int
    crop_type: int
    crop_variety: int | None = None
    sowing_date: str | None = None
    harvesting_date: str | None = None
    target_yield: float | None = None
    actual_yield: float | None = None
    irrigation_type: int | None = None
    tillage_type: int | None = None
    maturity: str | None = None
    fertilizer: str | None = None
    hybrid: str | None = None
    ndvi_list: str | None = None
    notes: str | None = None
    is_cut_off: bool | None = None


class VegetationCycleResponse(ApiModel):
    id: str
    field_id: str
    season_id: str
    season_name: str | None = None
    year: int
    crop_type: int
    crop_name: str | None = None
    crop_variety: int | None = None
    variety_name: str | None = None
    sowing_date: str | None = None
    harvesting_date: str | None = None
    target_yield: float | None = None
    actual_yield: float | None = None
    irrigation_type: int | None = None
    irrigation_type_name: str | None = None
    tillage_type: int | None = None
    tillage_type_name: str | None = None
    maturity: str | None = None
    fertilizer: str | None = None
    hybrid: str | None = None
    ndvi_list: str | None = None
    notes: str | None = None
    is_cut_off: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None


class FieldCreate(ApiModel):
    name: str
    geometry: dict[str, Any]
    areaHa: float | None = None
    groupId: str | None = None
    seasonIds: list[str] = Field(default_factory=list)
    vegetationData: list[VegetationCycleCreate] = Field(default_factory=list)


class FieldUpdate(ApiModel):
    name: str | None = None
    geometry: dict[str, Any] | None = None
    areaHa: float | None = None
    groupId: str | None = None
    seasonIds: list[str] | None = None
    vegetationData: list[VegetationCycleCreate] | None = None


class FieldResponse(ApiModel):
    id: str
    name: str
    areaHa: float | None = None
    geometry: dict[str, Any]
    groupId: str | None = None
    seasonIds: list[str] = Field(default_factory=list)
    seasons: list[SeasonItem] = Field(default_factory=list)
    vegetationData: list[VegetationCycleResponse] = Field(default_factory=list)
    createdAt: str | None = None
    updatedAt: str | None = None
