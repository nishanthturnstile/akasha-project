"""Field analytics API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel, CloudMaskOptions
from ..config import settings
from ..raster.indices import DEFAULT_INDEX
from ..raster.models import (
    IndexStatisticsModel,
    IndexValueSplit,
    PixelCounts,
    SarSupport,
)


class FieldStatisticsRequest(ApiModel):
    source_id: str = Field(default_factory=lambda: settings.default_source_id)
    acquisition_date: str | None = None
    index_type: str = DEFAULT_INDEX
    cloud_mask: CloudMaskOptions = Field(default_factory=CloudMaskOptions)
    prefer_high_res: bool = True


class FieldStatisticsResponse(ApiModel):
    plot_id: str
    provider: Literal["native", "pipeline"] = "native"
    scope: Literal["field"] = "field"
    index_type: str
    source_id: str
    acquisition_date: str
    cloud_mask: CloudMaskOptions
    statistics: IndexStatisticsModel
    pixel_counts: PixelCounts
    value_split: IndexValueSplit | None = None
    metadata: dict[str, Any]
    sar_support: SarSupport | None = None
    # Best-resolution provenance (Phase D)
    resolved_source_id: str | None = None
    resolution_meters: float | None = None
    enhanced: bool = False
    basis_date: str | None = None
    provenance_note: str | None = None


class ViewerSelection(ApiModel):
    source_id: str
    acquisition_date: str
    index_type: str = DEFAULT_INDEX
    cloud_mask: CloudMaskOptions = Field(default_factory=CloudMaskOptions)
    render_profile: Literal["standard", "contrast"] = "standard"
    prefer_high_res: bool = True


class IndexRenderProfile(ApiModel):
    source_id: str
    scene_id: str
    index_type: str
    requested_profile: Literal["standard", "contrast"]
    applied_profile: Literal["standard", "contrast"]
    profile_version: str
    thresholds: list[float] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    legend_labels: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    overlay_url: str
    precision: int = 3
    masked_label: str = "Cloud / masked"
    statistics_version: str = "field-statistics-v1"
    mask_provenance: dict[str, bool] = Field(default_factory=dict)
    formula_version: str
    geometry_reference: str


class ComparisonSampleRequest(ApiModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    left: ViewerSelection
    right: ViewerSelection


class RasterSample(ApiModel):
    status: Literal["ok", "error"]
    value: float | None = None
    category: int | None = None
    masked: bool = False
    mask_class: int | None = None
    error: str | None = None
