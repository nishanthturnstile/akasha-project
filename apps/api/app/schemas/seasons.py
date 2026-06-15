"""Season API Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import field_validator

from ..api_models import ApiModel


class SeasonCreate(ApiModel):
    name: str
    start_date: date | None = None
    end_date: date | None = None
    field_ids: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Season name must not be blank.")
        if len(cleaned) > 120:
            raise ValueError("Season name exceeds 120 characters.")
        return cleaned

    @field_validator("end_date")
    @classmethod
    def _validate_date_range(cls, end_date: date | None, info: Any) -> date | None:
        if end_date is None:
            return end_date
        start_date = info.data.get("start_date")
        if start_date is not None and end_date < start_date:
            raise ValueError("endDate cannot be earlier than startDate.")
        return end_date


class SeasonUpdate(ApiModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    field_ids: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Season name must not be blank.")
        if len(cleaned) > 120:
            raise ValueError("Season name exceeds 120 characters.")
        return cleaned

    @field_validator("end_date")
    @classmethod
    def _validate_date_range(cls, end_date: date | None, info: Any) -> date | None:
        if end_date is None:
            return end_date
        start_date = info.data.get("start_date")
        if start_date is not None and end_date < start_date:
            raise ValueError("endDate cannot be earlier than startDate.")
        return end_date


class FieldIdEntry(ApiModel):
    id: str
    name: str
    canRemove: bool


class SeasonResponse(ApiModel):
    id: str
    userId: str
    name: str
    startDate: str | None = None
    endDate: str | None = None
    canDelete: bool = True
    totalArea: float = 0.0
    fieldIds: list[FieldIdEntry] = []
    createdAt: str
    updatedAt: str
