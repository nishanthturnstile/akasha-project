"""Pydantic models for the Slice 2 BFF product contracts.

Response serialization uses these models (or dicts matching them) so the API is
typed and self-documenting. Kept intentionally small — only what Phase 2 needs.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Geometry(BaseModel):
    type: str
    coordinates: Any


class StatisticsRequest(BaseModel):
    """POST /api/indices/statistics request body."""

    geometry: Geometry
    sourceId: str = Field(default="resourcesat-2a-liss3-boa")
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


class ValueSplitCategory(BaseModel):
    id: str
    label: str
    minInclusive: float | None = None
    maxExclusive: float | None = None
    pixelCount: int | None = None
    areaSqM: float | None = None
    percentage: float = Field(ge=0, le=100)


class IndexValueSplit(BaseModel):
    indexType: Literal["NDVI"] = "NDVI"
    profileId: str
    percentageBasis: Literal["classifiablePixels"] = "classifiablePixels"
    thresholds: list[float]
    totalPixels: int | None = None
    classifiablePixels: int | None = None
    noDataPixels: int | None = None
    unclassifiedPixels: int | None = None
    categories: list[ValueSplitCategory]


class StatisticsMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    formula: str
    bands: list[str]
    spectralRoles: list[str]
    maskMethod: str
    nativeExcludedMaskClasses: list[int]
    metricsProvisional: bool = False
    reflectanceCorrection: str
    itemId: str | None = None
    areaHa: float | None = None
    vertices: int | None = None
    warnings: list[str] = Field(default_factory=list)


class SarBandStatistics(BaseModel):
    name: str
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    stddev: float | None = None
    validPixelPercent: float = 0.0


class SarSupport(BaseModel):
    available: bool = False
    status: str = "unavailable"
    sourceId: str = "eos-04-sar-mrs-l2b"
    acquisitionDate: str | None = None
    daysFromOpticalDate: int | None = None
    windowDays: int = 7
    cloudGap: bool = False
    opticalCloudMaskedPercent: float | None = None
    opticalMaskedPixels: int | None = None
    polarizations: list[str] = Field(default_factory=list)
    coveragePercent: float | None = None
    confidence: str = "none"
    reason: str | None = None
    bands: list[SarBandStatistics] = Field(default_factory=list)
    wetnessSignal: str = "not_assessed"
    changeSignal: str = "not_assessed"


class StatisticsResponse(BaseModel):
    indexType: str
    sourceId: str
    acquisitionDate: str
    statistics: IndexStatisticsModel
    pixelCounts: PixelCounts
    valueSplit: IndexValueSplit | None = None
    metadata: StatisticsMetadata
    sarSupport: SarSupport | None = None
