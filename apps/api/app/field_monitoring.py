"""Field-aware Monitoring routes for EOS-parity Phase 4."""
from __future__ import annotations

import base64
import functools
import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from . import plots_repo
from .auth import get_current_team
from .config import settings
from .providers.eos.field_provider import EosFieldProvider
from .providers.eos.scene_provider import EosSceneProvider
from .providers.eos.tile_provider import EosTileProvider
from .providers.models import (
    CloudMaskOptions,
    FieldLayer,
    FieldScene,
    FieldSceneListResponse,
    ProviderSyncResponse,
    SceneMetadata,
)
from .raster import catalog_resolver as catalog
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.field_monitoring")

router = APIRouter(
    prefix="/api",
    tags=["field-monitoring"],
    dependencies=[Depends(get_current_team)],
)

ProviderChoice = Literal["auto", "eos", "native"]
DISPLAY_MODES = ["RGB", "NDVI", "NDRE", "NDMI", "MSAVI", "RECI", "FALSE_COLOR"]
INDEX_MODES = {"NDVI", "NDRE", "NDMI", "MSAVI", "RECI"}
DISPLAY_LABELS = {
    "RGB": "True colour",
    "NDVI": "NDVI",
    "NDRE": "NDRE",
    "NDMI": "NDMI",
    "MSAVI": "MSAVI",
    "RECI": "RECI",
    "FALSE_COLOR": "False colour",
}


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field monitoring backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Field monitoring storage is not available in this environment."
        ) from exc


async def _get_plot_or_404(plot_id: str) -> dict:
    plot = await _run_blocking(plots_repo.get_plot, plot_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


def _is_eos_ready() -> bool:
    mode = (settings.provider_mode or "disabled").strip().lower()
    return bool(settings.eos_api_key.strip()) and settings.eos_enabled and mode in {"eos", "hybrid"}


def _default_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=180), today


def _parse_date(value: date | None, fallback: date) -> date:
    return value or fallback


def _scene_token(scene: SceneMetadata) -> str:
    payload = {
        "provider": scene.provider,
        "sceneId": scene.scene_id,
        "viewId": scene.view_id,
        "date": scene.acquisition_date.isoformat(),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_scene_token(token: str) -> SceneMetadata:
    try:
        padded = token + ("=" * (-len(token) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        acquisition = date.fromisoformat(str(payload["date"]))
        return SceneMetadata(
            provider=str(payload.get("provider") or "eos"),
            scene_id=str(payload.get("sceneId") or payload.get("viewId") or ""),
            view_id=str(payload.get("viewId") or payload.get("sceneId") or ""),
            acquisition_date=acquisition,
        )
    except Exception as exc:  # noqa: BLE001
        raise bad_request("Scene token is invalid.", code="INVALID_SCENE_TOKEN") from exc


def _field_tile_template(plot_id: str, scene_token: str, display_mode: str) -> str:
    return (
        f"/api/tiles/fields/{quote(plot_id, safe='')}/{scene_token}/"
        f"{quote(display_mode, safe='')}/{{z}}/{{x}}/{{y}}.png"
        "?clouds=true&cloudShadows=true&cirrus=true"
    )


def _field_layers(plot_id: str, scene_token: str) -> list[FieldLayer]:
    layers: list[FieldLayer] = []
    for mode in DISPLAY_MODES:
        if mode == "RGB":
            kind = "rgb"
        elif mode == "FALSE_COLOR":
            kind = "composite"
        else:
            kind = "index"
        layers.append(
            FieldLayer(
                display_mode=mode,
                label=DISPLAY_LABELS[mode],
                kind=kind,
                tile_url_template=_field_tile_template(plot_id, scene_token, mode),
                attribution="EOSDA API Connect",
            )
        )
    return layers


def _best_scene_key(scene: SceneMetadata) -> tuple[float, float, float]:
    usable = scene.usable_percent if scene.usable_percent is not None else -1.0
    coverage = scene.coverage_percent if scene.coverage_percent is not None else -1.0
    cloud = scene.cloud_percent if scene.cloud_percent is not None else 101.0
    return usable, coverage, -cloud


def _dedupe_scenes(scenes: list[SceneMetadata]) -> list[SceneMetadata]:
    by_date: dict[date, SceneMetadata] = {}
    for scene in scenes:
        current = by_date.get(scene.acquisition_date)
        if current is None or _best_scene_key(scene) > _best_scene_key(current):
            by_date[scene.acquisition_date] = scene
    return sorted(by_date.values(), key=lambda item: item.acquisition_date, reverse=True)


def _scene_from_eos(plot_id: str, scene: SceneMetadata) -> FieldScene:
    token = _scene_token(scene)
    cloud = scene.cloud_percent
    usable = scene.usable_percent if scene.usable_percent is not None else (
        round(max(0.0, 100.0 - cloud), 2) if cloud is not None else None
    )
    return FieldScene(
        scene_token=token,
        acquisition_date=scene.acquisition_date,
        sensor=scene.sensor,
        cloud_percent=cloud,
        usable_pixel_percent=usable,
        cloud_masked_percent=cloud,
        coverage_percent=scene.coverage_percent,
        bounds=scene.bounds,
        tile_available=True,
        metrics_provisional=scene.usable_percent is None,
        scene_count=1,
        layers=_field_layers(plot_id, token),
    )


def _native_layer(source_id: str, acquisition_date: str, attribution: str) -> FieldLayer:
    return FieldLayer(
        display_mode="RGB",
        label="True colour",
        kind="rgb",
        tile_url_template=catalog.tile_url_template(source_id, acquisition_date),
        attribution=attribution,
    )


def _native_fallback_response(
    plot_id: str,
    *,
    date_start: date,
    date_end: date,
    reason: str,
) -> FieldSceneListResponse:
    source_id = settings.default_source_id or catalog.COLLECTION_ID
    source = catalog.get_source(source_id)
    all_dates = catalog.list_dates(source_id)
    dates = [
        item for item in all_dates
        if date_start <= date.fromisoformat(item["acquisitionDate"]) <= date_end
    ]
    if not dates:
        dates = all_dates
    scenes = [
        FieldScene(
            scene_token=item["acquisitionDate"],
            acquisition_date=date.fromisoformat(item["acquisitionDate"]),
            datetime=(
                datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
                if item.get("datetime")
                else None
            ),
            sensor=source["label"],
            cloud_percent=item.get("cloudMaskedPercent"),
            usable_pixel_percent=item.get("usablePixelPercent"),
            cloud_masked_percent=item.get("cloudMaskedPercent"),
            coverage_percent=item.get("coveragePercent"),
            bounds=item.get("bounds"),
            tile_available=bool(item.get("tileAvailable", True)),
            metrics_provisional=bool(item.get("metricsProvisional", False)),
            scene_count=item.get("sceneCount"),
            layers=[
                _native_layer(
                    source_id,
                    item["acquisitionDate"],
                    str(source.get("attribution") or source.get("provider") or "Satellite imagery"),
                )
            ],
        )
        for item in dates
    ]
    return FieldSceneListResponse(
        plot_id=plot_id,
        provider="native",
        scope="global_fallback",
        source_id=source_id,
        display_modes=["RGB"],
        scenes=scenes,
        fallback_reason=reason,
    )


def _eos_scenes_response(
    plot_id: str,
    external_field_id: str,
    date_start: date,
    date_end: date,
) -> FieldSceneListResponse:
    scene_provider = EosSceneProvider()
    request = scene_provider.search_scenes(
        external_field_id,
        date_start,
        date_end,
        sensors=["sentinel2"],
        limit=100,
    )
    if not request.request_id:
        scenes: list[SceneMetadata] = []
    else:
        scenes = scene_provider.get_scene_search_result(external_field_id, request.request_id)
    return FieldSceneListResponse(
        plot_id=plot_id,
        provider="eos",
        scope="field",
        source_id="sentinel-2-l2a",
        display_modes=DISPLAY_MODES,
        scenes=[_scene_from_eos(plot_id, scene) for scene in _dedupe_scenes(scenes)],
    )


@router.post(
    "/fields/{plot_id}/providers/eos/sync",
    response_model=ProviderSyncResponse,
    response_model_by_alias=True,
)
async def sync_field_provider(plot_id: str) -> ProviderSyncResponse:
    plot = await _get_plot_or_404(plot_id)

    def _sync() -> ProviderSyncResponse:
        provider = EosFieldProvider()
        external_field_id = plot.get("externalFieldId")
        if plot.get("externalProvider") == "eos" and external_field_id:
            result = provider.update_mirror(plot, str(external_field_id))
            plots_repo.update_provider_link(
                plot_id,
                external_provider="eos",
                external_field_id=result.external_field_id,
                provider_sync_status=result.sync_status,
                provider_metadata={"fieldAreaHa": result.provider_area_ha},
            )
        else:
            result = provider.mirror_field(plot)
        return ProviderSyncResponse(
            plot_id=plot_id,
            sync_status=result.sync_status,
            synced_at=result.synced_at,
            field=result,
        )

    return await _run_blocking(_sync)


@router.get(
    "/fields/{plot_id}/scenes",
    response_model=FieldSceneListResponse,
    response_model_by_alias=True,
)
async def get_field_scenes(
    plot_id: str,
    provider: ProviderChoice = "auto",
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
) -> FieldSceneListResponse:
    default_start, default_end = _default_range()
    date_start = _parse_date(startDate, default_start)
    date_end = _parse_date(endDate, default_end)
    if date_start > date_end:
        raise bad_request("startDate must be on or before endDate.", code="INVALID_DATE_RANGE")

    plot = await _get_plot_or_404(plot_id)
    external_field_id = plot.get("externalFieldId")

    if provider == "native":
        return _native_fallback_response(
            plot_id,
            date_start=date_start,
            date_end=date_end,
            reason="Native global scene timeline is used for the selected field.",
        )

    if provider == "eos" and not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before loading EOS field scenes.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )

    can_use_eos = bool(external_field_id) and _is_eos_ready()
    if provider == "eos" and not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "EOS provider is not available.",
            503,
            {"provider": "eos"},
        )

    if provider == "auto" and not can_use_eos:
        return _native_fallback_response(
            plot_id,
            date_start=date_start,
            date_end=date_end,
            reason=(
                "Selected field is not synced to the configured provider."
                if not external_field_id
                else "EOS provider is not available."
            ),
        )

    return await _run_blocking(
        _eos_scenes_response,
        plot_id,
        str(external_field_id),
        date_start,
        date_end,
    )


@router.get("/tiles/fields/{plot_id}/{scene_token}/{display_mode}/{z}/{x}/{y}.png")
async def get_field_tile(
    plot_id: str,
    scene_token: str,
    display_mode: str,
    z: int,
    x: int,
    y: int,
    clouds: bool = True,
    cloudShadows: bool = True,
    cirrus: bool = True,
) -> Response:
    await _get_plot_or_404(plot_id)
    scene = _decode_scene_token(scene_token)
    if scene.provider != "eos":
        raise bad_request(
            "Field tile proxy supports provider field scenes only.",
            code="UNSUPPORTED_FIELD_TILE_SOURCE",
        )
    if not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "EOS provider is not available.",
            503,
            {"provider": "eos"},
        )
    cloud_mask = CloudMaskOptions(
        clouds=clouds,
        cloud_shadows=cloudShadows,
        cirrus=cirrus,
    )

    def _render():
        return EosTileProvider().render_tile(
            scene,
            display_mode=display_mode,
            z=z,
            x=x,
            y=y,
            cloud_mask=cloud_mask,
        )

    tile = await _run_blocking(_render)
    return Response(content=tile.content, media_type=tile.content_type)
