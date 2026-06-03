"""Provider interfaces for swappable Akasha data providers."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import (
    AnalyticsTrendPoint,
    CloudMaskOptions,
    ExportFile,
    FieldMirrorResult,
    ProviderAsyncRequest,
    SceneMetadata,
    TileBytes,
    TileTemplateMetadata,
    WeatherResponse,
    ZoningMapStatus,
)


class FieldProvider(Protocol):
    def mirror_field(self, plot: dict) -> FieldMirrorResult: ...

    def update_mirror(self, plot: dict, external_field_id: str) -> FieldMirrorResult: ...

    def delete_mirror(self, external_field_id: str) -> None: ...

    def get_mirror(self, external_field_id: str) -> FieldMirrorResult: ...


class SceneProvider(Protocol):
    def search_scenes(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
        *,
        sensors: list[str] | None = None,
        limit: int | None = None,
        max_cloud_cover_in_aoi: float | None = None,
    ) -> ProviderAsyncRequest: ...

    def get_scene_search_result(
        self,
        external_field_id: str,
        request_id: str,
    ) -> list[SceneMetadata]: ...


class TileProvider(Protocol):
    def get_tile_template(
        self,
        scene: SceneMetadata,
        *,
        layer_type: str,
        index: str | None = None,
    ) -> TileTemplateMetadata: ...

    def render_tile(
        self,
        scene: SceneMetadata,
        *,
        display_mode: str,
        z: int,
        x: int,
        y: int,
        cloud_mask: CloudMaskOptions,
    ) -> TileBytes: ...


class AnalyticsProvider(Protocol):
    def create_trend_request(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
        *,
        index: str,
        data_source: str,
        cloud_mask: CloudMaskOptions | None = None,
    ) -> ProviderAsyncRequest: ...

    def get_trend_result(
        self,
        external_field_id: str,
        request_id: str,
        *,
        index: str,
    ) -> list[AnalyticsTrendPoint]: ...


class ImageryExportProvider(Protocol):
    def export_index_geotiff(
        self,
        external_field_id: str,
        *,
        scene_token: str | None,
        acquisition_date: date,
        index: str,
        cloud_mask: CloudMaskOptions,
        filename: str,
    ) -> ExportFile: ...


class WeatherProvider(Protocol):
    def get_forecast(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse: ...

    def get_history(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse: ...

    def get_accumulated(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
    ) -> WeatherResponse: ...


class ZoningProvider(Protocol):
    def create_vegetation_map(
        self,
        external_field_id: str,
        *,
        index: str,
        zone_quantity: int,
        min_zone_area: int,
        dataset_id: str,
    ) -> ProviderAsyncRequest: ...

    def get_zoning_map(self, external_field_id: str, external_zmap_id: str) -> ZoningMapStatus: ...

    def list_zoning_maps(self, external_field_id: str) -> list[ZoningMapStatus]: ...

    def delete_zoning_map(self, external_field_id: str, external_zmap_id: str) -> None: ...
