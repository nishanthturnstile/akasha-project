"""EOS field mirroring provider."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ... import plots_repo
from ...raster.errors import AkashaError
from ..models import FieldMirrorResult
from .client import EosClient


class EosFieldProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def mirror_field(self, plot: dict[str, Any]) -> FieldMirrorResult:
        payload = _plot_to_eos_feature(plot)
        response = self.client.request("POST", "/field-management", json=payload)
        external_field_id = str(response.get("id", ""))
        if not external_field_id:
            raise AkashaError(
                "PROVIDER_INVALID_RESPONSE",
                "EOS provider returned an invalid field response.",
                502,
                {"provider": "eos"},
            )
        result = FieldMirrorResult(
            plot_id=str(plot["id"]),
            external_field_id=external_field_id,
            sync_status="synced",
            synced_at=datetime.now(UTC),
            provider_area_ha=_to_float(response.get("area")),
        )
        plots_repo.update_provider_link(
            str(plot["id"]),
            external_provider="eos",
            external_field_id=external_field_id,
            provider_sync_status="synced",
            provider_metadata={"fieldAreaHa": result.provider_area_ha},
        )
        return result

    def update_mirror(self, plot: dict[str, Any], external_field_id: str) -> FieldMirrorResult:
        response = self.client.request(
            "PATCH",
            f"/field-management/{external_field_id}",
            json=_plot_to_eos_feature(plot),
        )
        return FieldMirrorResult(
            plot_id=str(plot["id"]),
            external_field_id=str(response.get("id", external_field_id)),
            sync_status="synced",
            synced_at=datetime.now(UTC),
            provider_area_ha=_to_float((response.get("properties") or {}).get("area")),
        )

    def delete_mirror(self, external_field_id: str) -> None:
        self.client.request(
            "DELETE",
            f"/field-management/{external_field_id}",
            expected_status=(204,),
        )

    def get_mirror(self, external_field_id: str) -> FieldMirrorResult:
        response = self.client.request("GET", f"/field-management/{external_field_id}")
        return FieldMirrorResult(
            plot_id="",
            external_field_id=str(response.get("id", external_field_id)),
            sync_status="synced",
            provider_area_ha=_to_float((response.get("properties") or {}).get("area")),
        )


def _plot_to_eos_feature(plot: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "name": plot.get("name"),
        "group": plot.get("groupName"),
    }
    crop_year: dict[str, Any] = {}
    if plot.get("cropType"):
        crop_year["crop_type"] = plot["cropType"]
    sowing_date = plot.get("sowingDate") or plot.get("plantingDate")
    if sowing_date:
        crop_year["sowing_date"] = sowing_date
        crop_year["year"] = int(str(sowing_date)[:4])
    if crop_year:
        properties["years_data"] = [crop_year]
    return {
        "type": "Feature",
        "properties": {k: v for k, v in properties.items() if v is not None},
        "geometry": plot["geometry"],
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

