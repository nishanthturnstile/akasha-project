"""Reference/lookup table response schemas."""

from __future__ import annotations

from ..api_models import ApiModel


class IrrigationTypeResponse(ApiModel):
    id: int
    name: str
    description: str | None = None


class TillageTypeResponse(ApiModel):
    id: int
    name: str
    description: str | None = None


class SeedingTypeResponse(ApiModel):
    id: int
    name: str
    description: str | None = None


class CropGrowthStageResponse(ApiModel):
    id: int
    crop_id: int
    seq: int
    name: str
    duration: str | None = None


class CropResponse(ApiModel):
    id: int
    name: str
    seeding_type_id: int | None = None
    color: str | None = None
    maturity_options: list[str] | None = None
    has_weather_risk: bool = False
    has_variety: bool = False
    bbch_mode: str | None = None
    characteristic: str | None = None
    stages: list[CropGrowthStageResponse] = []


class VarietyResponse(ApiModel):
    id: int
    crop_id: int
    name: str
    maturity_options: list[str] | None = None


class PaginatedVarietiesResponse(ApiModel):
    items: list[VarietyResponse]
    total: int
    page: int
    page_size: int
    pages: int
