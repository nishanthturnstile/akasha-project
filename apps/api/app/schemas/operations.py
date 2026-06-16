"""Field activity / operations API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel

ActivityStatus = Literal["planned", "in_progress", "done", "cancelled"]


class AttachmentPublic(ApiModel):
    id: str
    parent_type: str | None = None
    parent_id: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class AttachmentCreate(ApiModel):
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldActivityPayload(ApiModel):
    activity_type: str
    activity_date: str
    plot_id: str | None = None
    assignee: str | None = None
    status: ActivityStatus = "planned"
    input_product: str | None = None
    cost: float | None = None
    notes: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldActivityUpdate(ApiModel):
    activity_type: str | None = None
    activity_date: str | None = None
    plot_id: str | None = None
    assignee: str | None = None
    status: ActivityStatus | None = None
    input_product: str | None = None
    cost: float | None = None
    notes: str | None = None
    attachment_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class FieldActivity(ApiModel):
    id: str
    plot_id: str | None = None
    field_name: str | None = None
    group_name: str | None = None
    group_names: list[str] = Field(default_factory=list)
    crop_type: str | None = None
    variety: str | None = None
    season_label: str | None = None
    activity_type: str
    activity_date: str
    assignee: str | None = None
    status: ActivityStatus
    input_product: str | None = None
    cost: float | None = None
    notes: str | None = None
    attachments: list[AttachmentPublic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
