"""EOS tile provider.

The browser only receives Akasha same-origin `/api/tiles/*` templates. EOS
Render API paths are constructed and fetched here, inside the BFF.
"""
from __future__ import annotations

from urllib.parse import quote

from ..cloud_mask import eos_cloud_masking_level
from ..models import CloudMaskOptions, SceneMetadata, TileBytes, TileTemplateMetadata
from .client import EosClient


_DISPLAY_MODE_TO_BANDS = {
    "RGB": "B04,B03,B02",
    "FALSE_COLOR": "B08,B04,B03",
    "NDVI": "NDVI",
    "NDRE": "NDRE",
    "NDMI": "NDMI",
    "MSAVI": "MSAVI",
    "RECI": "RECI",
}

_INDEX_MODES = {"NDVI", "NDRE", "NDMI", "MSAVI", "RECI"}


class EosTileProvider:
    def __init__(self, client: EosClient | None = None) -> None:
        self.client = client or EosClient()

    def get_tile_template(
        self,
        scene: SceneMetadata,
        *,
        layer_type: str,
        index: str | None = None,
    ) -> TileTemplateMetadata:
        scene_token = quote(scene.scene_id or scene.view_id, safe="")
        layer_token = quote(layer_type.lower(), safe="")
        return TileTemplateMetadata(
            scene_id=scene.scene_id,
            layer_type=layer_type,
            index=index,
            tile_url_template=(
                f"/api/tiles/fields/eos/{scene_token}/{layer_token}/{{z}}/{{x}}/{{y}}.png"
            ),
        )

    def render_tile(
        self,
        scene: SceneMetadata,
        *,
        display_mode: str,
        z: int,
        x: int,
        y: int,
        cloud_mask: CloudMaskOptions,
    ) -> TileBytes:
        mode = display_mode.upper()
        bands = _DISPLAY_MODE_TO_BANDS.get(mode)
        if not bands:
            from ...raster.errors import bad_request

            raise bad_request(
                f"Display mode '{display_mode}' is not supported for EOS field scenes.",
                code="UNSUPPORTED_DISPLAY_MODE",
                displayMode=display_mode,
                supportedDisplayModes=sorted(_DISPLAY_MODE_TO_BANDS),
            )
        view_id = quote(scene.view_id or scene.scene_id, safe="")
        path = f"/api/render/{view_id}/{quote(bands, safe=',')}/{z}/{x}/{y}"
        params: dict[str, str | int] = {}
        cloud_level, _, _ = eos_cloud_masking_level(cloud_mask)
        if cloud_level is not None:
            params["cloud_masking_level"] = cloud_level
        if mode in _INDEX_MODES:
            params["colormap"] = mode.lower()
        body, content_type = self.client.request_bytes("GET", path, params=params)
        return TileBytes(content=body, content_type=content_type or "image/png")
