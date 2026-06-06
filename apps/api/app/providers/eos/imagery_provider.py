"""EOS imagery export provider.

The BFF exposes only same-origin export routes. EOS task creation, task IDs, and
download URLs stay inside this adapter.
"""
from __future__ import annotations

import base64
from datetime import date
from typing import Any

from ...raster.errors import AkashaError
from ..cloud_mask import cloud_mask_mapping, eos_request_params
from ..models import CloudMaskOptions, ExportFile, FieldExportMetadata
from .client import EosClient


class EosImageryProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def export_index_geotiff(
        self,
        external_field_id: str,
        *,
        scene_token: str | None,
        acquisition_date: date,
        index: str,
        cloud_mask: CloudMaskOptions,
        filename: str,
    ) -> ExportFile:
        params: dict[str, Any] = {
            "field_id": external_field_id,
            "date": acquisition_date.isoformat(),
            "index": index,
            "format": "tiff",
            "calibrate": 1,
        }
        if scene_token:
            params["scene_token"] = scene_token
        params.update(eos_request_params(cloud_mask))

        task = self.client.request(
            "POST",
            "/api/gdw/api",
            json={"type": "bandmath", "params": params},
            expected_status=(200, 201),
        )
        task_id = str(task.get("task_id") or task.get("request_id") or task.get("id") or "")
        if not task_id:
            raise AkashaError(
                "PROVIDER_INVALID_RESPONSE",
                "EOS provider returned an invalid export response.",
                502,
                {"provider": "eos"},
            )

        result = self.client.request("GET", f"/api/gdw/api/{task_id}")
        status = str(result.get("status") or result.get("state") or "done").lower()
        if status in {"created", "pending", "processing", "running", "queued"}:
            raise AkashaError(
                "EXPORT_PENDING",
                "Provider export is still processing. Retry shortly.",
                503,
                {"provider": "eos"},
            )

        content, content_type = _extract_bytes(result)
        if content is None:
            download_url = _extract_download_url(result)
            if not download_url:
                raise AkashaError(
                    "PROVIDER_INVALID_RESPONSE",
                    "EOS provider returned an invalid export result.",
                    502,
                    {"provider": "eos"},
                )
            content, content_type = self.client.request_bytes("GET", download_url)

        return ExportFile(
            provider="eos",
            filename=filename,
            content=content,
            content_type=content_type or "image/tiff",
            metadata=FieldExportMetadata(
                plot_id="",
                provider="eos",
                source_id="sentinel-2-l2a",
                acquisition_date=acquisition_date,
                index_type=index,
                format="geotiff",
                cloud_mask=cloud_mask,
                cloud_mask_mapping=cloud_mask_mapping(cloud_mask),
            ),
        )


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("result", result)
    if isinstance(payload, dict):
        return payload
    return result


def _extract_bytes(result: dict[str, Any]) -> tuple[bytes, str] | tuple[None, None]:
    payload = _result_payload(result)
    encoded = payload.get("contentBase64") or payload.get("content_base64")
    if isinstance(encoded, str) and encoded:
        return base64.b64decode(encoded), str(payload.get("contentType") or "image/tiff")
    return None, None


def _extract_download_url(result: dict[str, Any]) -> str | None:
    payload = _result_payload(result)
    for key in ("download_url", "downloadUrl", "url", "href"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
