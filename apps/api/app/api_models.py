"""Shared API DTO helpers for Akasha-owned BFF contracts."""

from __future__ import annotations

import warnings
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# FastAPI (>=0.139) decomposes request-body models via ``get_model_fields()`` and
# builds a per-field ``TypeAdapter(Annotated[type, FieldInfo])``. With Pydantic
# (>=2.13) this emits a false-positive ``UnsupportedFieldAttributeWarning`` for
# every ``alias_generator``-derived field alias (e.g. ``sourceId``, ``indexType``),
# claiming the alias "has no effect" — even though ``populate_by_name`` plus the
# camelCase ``alias_generator`` continue to validate and serialize correctly.
# Silence only this specific, verified false positive so it does not spam server
# logs and test output. See docs/impl-plan/feature-ui-pipeline-integration-1.md.
try:  # pragma: no cover - defensive: warning class may be absent on older pydantic
    from pydantic.warnings import UnsupportedFieldAttributeWarning

    warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)
except ImportError:  # pragma: no cover
    pass


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class CloudMaskOptions(ApiModel):
    clouds: bool = True
    cloud_shadows: bool = True
    cirrus: bool = True


class CloudMaskMapping(ApiModel):
    native_excluded_mask_classes: list[int]
    warnings: list[str] = Field(default_factory=list)


class FieldTrendPoint(ApiModel):
    acquisition_date: date
    scene_id: str | None = None
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    stddev: float | None = None
    valid_pixel_percent: float | None = None
    cloud_masked_percent: float | None = None
    coverage_percent: float | None = None
    cloud_percent: float | None = None
    metrics_provisional: bool = False
    unavailable_reason: str | None = None


class FieldTrendResponse(ApiModel):
    plot_id: str
    provider: Literal["native"] = "native"
    scope: Literal["native_fallback"] = "native_fallback"
    source_id: str
    index_type: str
    start_date: date
    end_date: date
    points: list[FieldTrendPoint]
    fallback_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
