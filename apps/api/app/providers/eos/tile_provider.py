"""EOS tile metadata provider.

Phase 2 only returns Akasha same-origin templates. The actual proxy route is a
later phase so no direct EOS render URL reaches the browser.
"""
from __future__ import annotations

from urllib.parse import quote

from ..models import SceneMetadata, TileTemplateMetadata


class EosTileProvider:
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
                f"/api/providers/eos/tiles/{scene_token}/{layer_token}/{{z}}/{{x}}/{{y}}.png"
            ),
        )

