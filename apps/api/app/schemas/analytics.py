"""Field analytics API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel, CloudMaskOptions
from ..raster.models import IndexStatisticsModel, PixelCounts


class FieldStatisticsRequest(ApiModel):
    source_id: str = "sentinel-2-l2a"
    acquisition_date: str | None = None
    index_type: str = "NDVI"
    cloud_mask: CloudMaskOptions = Field(default_factory=CloudMaskOptions)


class FieldStatisticsResponse(ApiModel):
    plot_id: str
    provider: Literal["native"] = "native"
    scope: Literal["field"] = "field"
    index_type: str
    source_id: str
    acquisition_date: str
    cloud_mask: CloudMaskOptions
    statistics: IndexStatisticsModel
    pixel_counts: PixelCounts
    metadata: dict[str, Any]
