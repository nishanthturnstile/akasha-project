"""Scout task API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel
from .operations import AttachmentPublic


class ScoutTaskPayload(ApiModel):
    plot_id: str | None = None
    field_id: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"] = "new"
    assignee: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    notes: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoutTaskUpdate(ApiModel):
    plot_id: str | None = None
    field_id: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"] | None = None
    assignee: str | None = None
    priority: Literal["low", "medium", "high"] | None = None
    notes: str | None = None
    attachment_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ScoutTask(ApiModel):
    id: str
    plot_id: str | None = None
    field_id: str | None = None
    field_name: str | None = None
    field_name_snapshot: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    status: Literal["new", "closed"]
    assignee: str | None = None
    priority: Literal["low", "medium", "high"]
    notes: str | None = None
    attachments: list[AttachmentPublic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
