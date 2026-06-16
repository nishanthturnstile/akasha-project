"""Field group API Pydantic schemas."""

from __future__ import annotations

from pydantic import Field

from ..api_models import ApiModel


class FieldGroupPayload(ApiModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class FieldGroup(ApiModel):
    id: str
    name: str
    description: str | None = None
    color: str | None = None
    plot_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class FieldAssignmentPayload(ApiModel):
    plot_ids: list[str] = Field(default_factory=list)
