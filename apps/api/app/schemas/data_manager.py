"""Data manager API Pydantic schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..api_models import ApiModel


class DatasetPayload(ApiModel):
    name: str
    dataset_type: Literal["geojson", "shp_zip", "iso_xml"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedDataset(ApiModel):
    id: str
    name: str
    dataset_type: str
    upload_status: str
    original_filename: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    feature_count: int | None = None
    validation_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ConnectionStatus(ApiModel):
    provider: str
    status: Literal["not_connected"]
    message: str
