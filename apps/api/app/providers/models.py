"""Normalized provider DTOs exposed inside the Akasha BFF."""
from __future__ import annotations

from datetime import date, datetime as DateTime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class ProviderModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class ProviderFeature(ProviderModel):
    id: str
    available: bool


class ProviderStatus(ProviderModel):
    provider: str
    mode: str
    configured: bool
    enabled: bool
    status: Literal["unconfigured", "disabled", "ready"]
    features: list[ProviderFeature]
    cache_ttl_seconds: int
    rate_limit_per_minute: int


class ProviderError(ProviderModel):
    provider: str = "eos"
    code: str
    message: str
    retry_after_seconds: int | None = None


class ProviderAsyncRequest(ProviderModel):
    provider: str = "eos"
    request_id: str
    status: str
    external_field_id: str | None = None
    external_zmap_id: str | None = None


class FieldMirrorResult(ProviderModel):
    plot_id: str
    provider: str = "eos"
    external_field_id: str
    sync_status: Literal["pending", "synced", "failed"]
    synced_at: DateTime | None = None
    provider_area_ha: float | None = None


class SceneMetadata(ProviderModel):
    provider: str = "eos"
    scene_id: str
    view_id: str
    acquisition_date: date
    sensor: str | None = None
    cloud_percent: float | None = None
    usable_percent: float | None = None
    coverage_percent: float | None = None
    bounds: list[float] | None = None


class TileTemplateMetadata(ProviderModel):
    provider: str = "eos"
    scene_id: str
    layer_type: str
    tile_url_template: str
    index: str | None = None
    attribution: str = "EOSDA API Connect"


class TileBytes(ProviderModel):
    provider: str = "eos"
    content: bytes
    content_type: str = "image/png"


class CloudMaskOptions(ProviderModel):
    clouds: bool = True
    cloud_shadows: bool = True
    cirrus: bool = True


class FieldLayer(ProviderModel):
    display_mode: str
    label: str
    kind: Literal["rgb", "index", "composite"]
    tile_url_template: str
    available: bool = True
    unavailable_reason: str | None = None
    attribution: str = "Akasha"


class FieldScene(ProviderModel):
    scene_token: str
    acquisition_date: date
    datetime: DateTime | None = None
    sensor: str | None = None
    cloud_percent: float | None = None
    usable_pixel_percent: float | None = None
    cloud_masked_percent: float | None = None
    coverage_percent: float | None = None
    bounds: list[float] | None = None
    tile_available: bool = True
    metrics_provisional: bool = False
    scene_count: int | None = None
    layers: list[FieldLayer] = []


class FieldSceneListResponse(ProviderModel):
    plot_id: str
    provider: str
    scope: Literal["field", "global_fallback"]
    source_id: str
    default_display_mode: Literal["RGB"] = "RGB"
    display_modes: list[str]
    scenes: list[FieldScene]
    fallback_reason: str | None = None


class ProviderSyncResponse(ProviderModel):
    plot_id: str
    provider: str = "eos"
    sync_status: Literal["pending", "synced", "failed"]
    synced_at: DateTime | None = None
    field: FieldMirrorResult | None = None


class AnalyticsTrendPoint(ProviderModel):
    provider: str = "eos"
    scene_id: str | None = None
    view_id: str | None = None
    acquisition_date: date
    index: str
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    stddev: float | None = None
    cloud_percent: float | None = None


class WeatherRecord(ProviderModel):
    record_date: date | None = Field(default=None, alias="date")
    start_time: DateTime | None = None
    end_time: DateTime | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_mm: float | None = None
    humidity_percent: float | None = None
    cloudiness_percent: float | None = None
    wind_mps: float | None = None
    wind_direction: str | None = None
    conditions: str | None = None
    conditions_code: str | None = None


class WeatherResponse(ProviderModel):
    provider: str = "eos"
    external_field_id: str
    kind: Literal["forecast", "history", "accumulated"]
    records: list[WeatherRecord]


class ZoningZone(ProviderModel):
    zone_id: str
    area_ha: float | None = None
    area_percent: float | None = None
    fertilizer: float | None = None
    geometry: dict[str, Any] | None = None


class ZoningMapStatus(ProviderModel):
    provider: str = "eos"
    external_field_id: str
    external_zmap_id: str | None = None
    status: str
    map_type: str
    index: str | None = None
    zone_count: int | None = None
    zones: list[ZoningZone] = []
