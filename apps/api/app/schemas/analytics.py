"""Field analytics API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel, CloudMaskOptions
from ..config import settings
from ..raster.indices import DEFAULT_INDEX
from ..raster.models import IndexStatisticsModel, PixelCounts, SarSupport


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
    metadata: dict[str, Any]
    sar_support: SarSupport | None = None
    # Best-resolution provenance (Phase D)
    resolved_source_id: str | None = None
    resolution_meters: float | None = None
    enhanced: bool = False
    basis_date: str | None = None
    provenance_note: str | None = None
