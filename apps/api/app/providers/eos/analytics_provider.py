"""EOS field analytics provider."""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from ..cloud_mask import eos_request_params
from ..models import AnalyticsTrendPoint, CloudMaskOptions, ProviderAsyncRequest
from .async_requests import poll_result
from .client import EosClient


class EosAnalyticsProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def create_trend_request(
        self,
        external_field_id: str,
        date_start: date,
        date_end: date,
        *,
        index: str,
        data_source: str,
        cloud_mask: CloudMaskOptions | None = None,
    ) -> ProviderAsyncRequest:
        params: dict[str, Any] = {
            "date_start": date_start.isoformat(),
            "date_end": date_end.isoformat(),
            "index": index,
            "data_source": data_source,
            "distinct_by_date": True,
        }
        if cloud_mask is not None:
            params.update(eos_request_params(cloud_mask))

        field_id = quote(external_field_id, safe="")
        response = self.client.request(
            "POST",
            f"/field-analytics/trend/{field_id}",
            json={"params": params},
            expected_status=(200, 201),
        )
        return ProviderAsyncRequest(
            request_id=str(response.get("request_id", "")),
            status=str(response.get("status", "unknown")),
            external_field_id=external_field_id,
        )

    def get_trend_result(
        self,
        external_field_id: str,
        request_id: str,
        *,
        index: str,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
    ) -> list[AnalyticsTrendPoint]:
        field_id = quote(external_field_id, safe="")
        request_token = quote(request_id, safe="")
        response = poll_result(
            lambda: self.client.request(
                "GET",
                f"/field-analytics/trend/{field_id}/{request_token}",
            ),
            operation="trend analytics",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        return [_trend_point(item, index) for item in response.get("result", [])]


def _trend_point(item: dict[str, Any], index: str) -> AnalyticsTrendPoint:
    return AnalyticsTrendPoint(
        scene_id=item.get("scene_id"),
        view_id=item.get("view_id"),
        acquisition_date=date.fromisoformat(str(item["date"])[:10]),
        index=index,
        mean=_to_float(item.get("average")),
        minimum=_to_float(item.get("min")),
        maximum=_to_float(item.get("max")),
        stddev=_to_float(item.get("std")),
        cloud_percent=_to_float(item.get("cloud")),
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
