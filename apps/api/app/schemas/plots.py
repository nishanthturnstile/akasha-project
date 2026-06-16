"""Plot API Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import field_validator

from ..api_models import ApiModel

PlotStatus = Literal["planned", "active", "inactive", "archived"]
USER_METADATA_FIELDS = (
    "groupName",
    "cropType",
    "variety",
    "seasonLabel",
    "sowingDate",
    "plantingDate",
    "status",
)


class PlotUserMetadata(ApiModel):
    groupName: str | None = None
    cropType: str | None = None
    variety: str | None = None
    seasonLabel: str | None = None
    sowingDate: date | None = None
    plantingDate: date | None = None
    status: PlotStatus | None = None

    @field_validator("sowingDate", "plantingDate", mode="before")
    @classmethod
    def _validate_date_only(cls, value: Any) -> Any:
        from datetime import datetime

        if value is None:
            return value
        if isinstance(value, datetime):
            raise ValueError("must be a date-only value")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            if "T" in value or " " in value:
                raise ValueError("must be a date-only value")
            return value
        raise ValueError("must be a date-only value")


class PlotCreate(PlotUserMetadata):
    name: str
    geometry: dict[str, Any]


class PlotUpdate(PlotUserMetadata):
    name: str | None = None
    geometry: dict[str, Any] | None = None


class PlotResponse(PlotUserMetadata):
    id: str
    name: str
    geometry: dict[str, Any]
    areaHa: float | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class RejectedFeature(ApiModel):
    index: int
    code: str
    message: str


class ImportResponse(ApiModel):
    imported: list[PlotResponse]
    rejected: list[RejectedFeature]
    importedCount: int
    rejectedCount: int
