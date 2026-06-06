"""EOS field scene-search provider."""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from ..models import ProviderAsyncRequest, SceneMetadata
from .async_requests import poll_result
from .client import EosClient


class EosSceneProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def search_scenes(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
        *,
        sensors: list[str] | None = None,
        limit: int | None = None,
        max_cloud_cover_in_aoi: float | None = None,
    ) -> ProviderAsyncRequest:
        params: dict[str, Any] = {
            "date_start": date_start.isoformat(),
            "date_end": date_end.isoformat(),
        }
        if sensors:
            params["data_source"] = sensors
        if limit is not None:
            params["limit"] = limit
        if max_cloud_cover_in_aoi is not None:
            params["max_cloud_cover_in_aoi"] = max_cloud_cover_in_aoi
        field_id = quote(external_field_id, safe="")
        response = self.client.request(
            "POST",
            f"/scene-search/for-field/{field_id}",
            json={"params": params},
            expected_status=(200, 201),
        )
        return ProviderAsyncRequest(
            request_id=str(response.get("request_id", "")),
            status=str(response.get("status", "unknown")),
            external_field_id=external_field_id,
        )

    def get_scene_search_result(
        self,
        external_field_id: str,
        request_id: str,
        *,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
    ) -> list[SceneMetadata]:
        field_id = quote(external_field_id, safe="")
        request_token = quote(request_id, safe="")
        response = poll_result(
            lambda: self.client.request(
                "GET",
                f"/scene-search/for-field/{field_id}/{request_token}",
            ),
            operation="scene search",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        return [_scene_from_eos(item) for item in response.get("result", [])]


def _scene_from_eos(item: dict[str, Any]) -> SceneMetadata:
    view_id = str(item.get("view_id") or item.get("viewId") or item.get("scene_id") or "")
    acquisition = date.fromisoformat(str(item["date"])[:10])
    return SceneMetadata(
        scene_id=str(item.get("scene_id") or view_id),
        view_id=view_id,
        acquisition_date=acquisition,
        sensor=item.get("sensor") or _sensor_from_view_id(view_id),
        cloud_percent=_to_float(item.get("cloud")),
        usable_percent=_to_float(item.get("usable_percent") or item.get("usablePixelPercent")),
        coverage_percent=_to_float(item.get("coverage_percent") or item.get("coveragePercent")),
        bounds=item.get("bounds"),
    )


def _sensor_from_view_id(view_id: str) -> str | None:
    return view_id.split("/", 1)[0] if "/" in view_id else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
