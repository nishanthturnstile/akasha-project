"""EOS zoning provider."""
from __future__ import annotations

import re
from typing import Any

from ..models import ProviderAsyncRequest, ZoningMapStatus, ZoningZone
from .client import EosClient

_ZMAP_RE = re.compile(r"/zoning/[^/]+/([^/?]+)")


class EosZoningProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def create_vegetation_map(
        self,
        external_field_id: str,
        *,
        index: str,
        zone_quantity: int,
        min_zone_area: int,
        dataset_id: str,
    ) -> ProviderAsyncRequest:
        response = self.client.request(
            "POST",
            "/zoning/vegetation-map",
            json={
                "field_id": external_field_id,
                "vegetation_index": index,
                "zone_quantity": zone_quantity,
                "min_zone_area": min_zone_area,
                "dataset_id": dataset_id,
                "need_answer": False,
            },
        )
        external_zmap_id = _extract_zmap_id(str(response.get("request_url", "")))
        return ProviderAsyncRequest(
            request_id=external_zmap_id or str(response.get("request_id", "")),
            status=str(response.get("status", "unknown")),
            external_field_id=external_field_id,
            external_zmap_id=external_zmap_id,
        )

    def get_zoning_map(self, external_field_id: str, external_zmap_id: str) -> ZoningMapStatus:
        response = self.client.request(
            "GET",
            f"/zoning/maps/{external_field_id}/{external_zmap_id}",
        )
        return _zoning_status(response, fallback_field_id=external_field_id)

    def list_zoning_maps(self, external_field_id: str) -> list[ZoningMapStatus]:
        response = self.client.request("GET", f"/api/zoning/{external_field_id}")
        maps = response.get("maps") or []
        return [_zoning_list_item(external_field_id, item) for item in maps]

    def delete_zoning_map(self, external_field_id: str, external_zmap_id: str) -> None:
        self.client.request(
            "DELETE",
            f"/api/zoning/{external_field_id}/{external_zmap_id}",
            expected_status=(204,),
        )


def _extract_zmap_id(request_url: str) -> str | None:
    match = _ZMAP_RE.search(request_url)
    return match.group(1) if match else None


def _zoning_status(item: dict[str, Any], *, fallback_field_id: str) -> ZoningMapStatus:
    zones: list[ZoningZone] = []
    for zone_wrapper in item.get("zones") or []:
        if not isinstance(zone_wrapper, dict):
            continue
        for zone_id, zone in zone_wrapper.items():
            zones.append(
                ZoningZone(
                    zone_id=zone_id,
                    area_ha=_to_float(zone.get("zone_area")),
                    area_percent=_to_float(zone.get("zone_p")),
                    fertilizer=_to_float(zone.get("fertilizer")),
                    geometry=zone.get("geometry"),
                )
            )
    return ZoningMapStatus(
        external_field_id=str(item.get("field_id") or fallback_field_id),
        external_zmap_id=item.get("zmap_id"),
        status=str(item.get("status", "ready")),
        map_type=str(item.get("type_zmap", "vegetation")),
        index=item.get("vegetation_index"),
        zone_count=len(zones) if zones else None,
        zones=zones,
    )


def _zoning_list_item(external_field_id: str, item: dict[str, Any]) -> ZoningMapStatus:
    detail = item.get("zmap_detail") or {}
    return ZoningMapStatus(
        external_field_id=external_field_id,
        external_zmap_id=item.get("zmap_id"),
        status="ready",
        map_type=str(item.get("type_zmap", "vegetation")),
        index=detail.get("vegetation_index"),
        zone_count=_to_int(detail.get("zone_quantity")),
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

