"""Provider factory helpers.

Routes use this module instead of constructing concrete provider classes
directly so the EOS trial provider can be replaced without changing public
route contracts.
"""
from __future__ import annotations

from typing import Literal

from ..config import settings
from ..raster.errors import bad_request
from .base import FieldProvider, SceneProvider, TileProvider
from .eos.field_provider import EosFieldProvider
from .eos.scene_provider import EosSceneProvider
from .eos.tile_provider import EosTileProvider

ProviderId = Literal["eos"]


def is_ready(provider: ProviderId = "eos") -> bool:
    if provider == "eos":
        mode = (settings.provider_mode or "disabled").strip().lower()
        return (
            bool(settings.eos_api_key.strip())
            and settings.eos_enabled
            and mode in {"eos", "hybrid"}
        )
    raise bad_request(
        f"Unknown provider '{provider}'.",
        code="UNKNOWN_PROVIDER",
        provider=provider,
    )


def field_provider(provider: ProviderId = "eos") -> FieldProvider:
    if provider == "eos":
        return EosFieldProvider()
    raise bad_request(
        f"Unknown field provider '{provider}'.",
        code="UNKNOWN_PROVIDER",
        provider=provider,
    )


def scene_provider(provider: ProviderId = "eos") -> SceneProvider:
    if provider == "eos":
        return EosSceneProvider()
    raise bad_request(
        f"Unknown scene provider '{provider}'.",
        code="UNKNOWN_PROVIDER",
        provider=provider,
    )


def tile_provider(provider: ProviderId = "eos") -> TileProvider:
    if provider == "eos":
        return EosTileProvider()
    raise bad_request(
        f"Unknown tile provider '{provider}'.",
        code="UNKNOWN_PROVIDER",
        provider=provider,
    )
