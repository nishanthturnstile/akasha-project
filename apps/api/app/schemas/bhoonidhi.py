"""Bhoonidhi diagnostic API Pydantic schemas."""

from __future__ import annotations

from pydantic import Field

from app.api_models import ApiModel

RESOURCESAT_LISS3_BOA_COLLECTION = "ResourceSat-2A_LISS3_BOA"


class BhoonidhiDiagnosticRequest(ApiModel):
    collection_id: str = Field(default=RESOURCESAT_LISS3_BOA_COLLECTION)
    item_id: str = Field(min_length=1)
