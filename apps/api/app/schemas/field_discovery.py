"""Compact, geometry-light contracts for field and scouting discovery."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel

DiscoverySort = Literal[
    "name_asc",
    "name_desc",
    "newest",
    "oldest",
    "area_asc",
    "area_desc",
]


class CropFacet(ApiModel):
    id: int
    name: str


class GroupFacet(ApiModel):
    id: str
    name: str


class DiscoveryFacets(ApiModel):
    crops: list[CropFacet] = Field(default_factory=list)
    groups: list[GroupFacet] = Field(default_factory=list)
    has_ungrouped: bool = False


class FocusBounds(ApiModel):
    west: float
    south: float
    east: float
    north: float


class ResolvedCrop(ApiModel):
    id: int
    name: str


class ResolvedGroup(ApiModel):
    id: str
    name: str


class DiscoveryFieldSummary(ApiModel):
    id: str
    name: str
    area_ha: float | None = None
    crop: ResolvedCrop | None = None
    group: ResolvedGroup | None = None
    district: str | None = None
    country: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    focus_bounds: FocusBounds


class DiscoveryTaskSummary(ApiModel):
    id: str
    status: Literal["new", "closed"]
    priority: Literal["low", "medium", "high"]
    notes: str | None = None
    assignee: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    field: DiscoveryFieldSummary | None = None
    field_name_snapshot: str | None = None
    find_field_available: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class AppliedDiscoveryFilters(ApiModel):
    season_id: str
    q: str = ""
    crop_ids: list[int] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    include_ungrouped: bool = False
    sort: DiscoverySort = "name_asc"
    status: Literal["new", "closed"] | None = None


class FieldDiscoveryPage(ApiModel):
    items: list[DiscoveryFieldSummary]
    pinned_items: list[DiscoveryFieldSummary] = Field(default_factory=list)
    applied_filters: AppliedDiscoveryFilters
    page: int
    page_size: int
    total: int
    total_pages: int
    result_bounds: FocusBounds | None = None


class ScoutTaskDiscoveryPage(ApiModel):
    items: list[DiscoveryTaskSummary]
    pinned_items: list[DiscoveryFieldSummary] = Field(default_factory=list)
    applied_filters: AppliedDiscoveryFilters
    page: int
    page_size: int
    total: int
    total_pages: int
    result_bounds: FocusBounds | None = None


class DiscoveryMapResponse(ApiModel):
    fields: dict[str, Any]
    task_points: dict[str, Any]
