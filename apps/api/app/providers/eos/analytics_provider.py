"""EOS field analytics provider."""
from __future__ import annotations

from datetime import date
from typing import Any

from ..models import AnalyticsTrendPoint, CloudMaskOptions, ProviderAsyncRequest
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
        response = self.client.request(
            "POST",
            f"/field-analytics/trend/{external_field_id}",
            json={
                "params": {
                    "date_start": date_start.isoformat(),
                    "date_end": date_end.isoformat(),
                    "index": index,
                    "data_source": data_source,
                    "distinct_by_date": True,
                }
            },
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
    ) -> list[AnalyticsTrendPoint]:
        response = self.client.request(
            "GET",
            f"/field-analytics/trend/{external_field_id}/{request_id}",
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
