"""Account API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel


class AccountMe(ApiModel):
    user: dict[str, Any]
    current_team: dict[str, Any]
    memberships: list[dict[str, Any]]
    auth_mode: str = "dev"


class AccountSettingsUpdate(ApiModel):
    optical_cloud_threshold_percent: int = Field(ge=0, le=70)


class ApiKeyCreate(ApiModel):
    name: str


class ApiKeyPublic(ApiModel):
    id: str
    name: str
    prefix: str
    last4: str
    created_at: str
    revoked_at: str | None = None
    raw_key: str | None = None


class Notification(ApiModel):
    id: str
    type: Literal[
        "field_change",
        "risk_alert",
        "task_assignment",
        "report_available",
    ]
    title: str
    body: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    read_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AssistantStatus(ApiModel):
    status: Literal["disabled"] = "disabled"
    message: str
    evidence_sources: list[str]
    limitations: list[str]
