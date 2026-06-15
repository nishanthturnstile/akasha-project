"""Field API Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..api_models import ApiModel


class SeasonItem(ApiModel):
    season_id: str
    name: str
    can_delete: bool = True


class FieldCreate(ApiModel):
    name: str
    geometry: dict[str, Any]
    areaHa: float | None = None
    groupId: str | None = None
    seasonIds: list[str] = Field(default_factory=list)


class FieldUpdate(ApiModel):
    name: str | None = None
    geometry: dict[str, Any] | None = None
    areaHa: float | None = None
    groupId: str | None = None
    seasonIds: list[str] | None = None


class FieldResponse(ApiModel):
    id: str
    name: str
    areaHa: float | None = None
    geometry: dict[str, Any]
    groupId: str | None = None
    seasonIds: list[str] = Field(default_factory=list)
    seasons: list[SeasonItem] = Field(default_factory=list)
    createdAt: str | None = None
    updatedAt: str | None = None
