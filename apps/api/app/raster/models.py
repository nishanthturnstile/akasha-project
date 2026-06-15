"""Pydantic models for the Slice 2 BFF product contracts.

Response serialization uses these models (or dicts matching them) so the API is
typed and self-documenting. Kept intentionally small — only what Phase 2 needs.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Geometry(BaseModel):
    type: str
    coordinates: Any


class StatisticsRequest(BaseModel):
    """POST /api/indices/statistics request body."""

    geometry: Geometry
    sourceId: str = Field(default="sentinel-2-l2a")
    acquisitionDate: str | None = Field(
        default=None, description="YYYY-MM-DD; defaults to the latest usable scene."
    )
    indexType: str = Field(default="NDVI")


class IndexStatisticsModel(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    stddev: float | None = None
    validPixelPercent: float = 0.0
    cloudMaskedPercent: float = 0.0
    coveragePercent: float = 0.0


class PixelCounts(BaseModel):
    totalPixels: int = 0
    nodataPixels: int = 0
    coveragePixels: int = 0
    maskedPixels: int = 0
    validPixels: int = 0


class StatisticsResponse(BaseModel):
    indexType: str
    sourceId: str
    acquisitionDate: str
    statistics: IndexStatisticsModel
    pixelCounts: PixelCounts
    metadata: dict[str, Any]
