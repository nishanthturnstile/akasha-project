"""Selected-field VRA vegetation zoning routes for EOS-parity Phase 8."""
from __future__ import annotations

import functools
import logging
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import ConfigDict, Field

from . import plots_repo, zoning_repo
from .auth import get_current_team
from .config import settings
from .field_exports import _disposition, _safe_filename
from .field_monitoring import _best_scene_key
from .providers.eos.scene_provider import EosSceneProvider
from .providers.eos.zoning_provider import EosZoningProvider
from .providers.models import ProviderModel, SceneMetadata, ZoningMapStatus, ZoningZone
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable

logger = logging.getLogger("akasha.api.field_zoning")

router = APIRouter(
    prefix="/api",
    tags=["field-zoning"],
    dependencies=[Depends(get_current_team)],
)

ProviderChoice = Literal["auto", "eos", "native"]
ZoningStatus = Literal["processing", "ready", "failed", "unknown"]
PROVIDER_ZONING_INDEXES = {"NDVI", "NDRE", "NDMI", "MSAVI", "RECI"}
ZONE_COLORS = [
    "#7f1d1d",
    "#b45309",
    "#d97706",
    "#84cc16",
    "#16a34a",
    "#047857",
    "#0f766e",
    "#0369a1",
    "#4338ca",
    "#7e22ce",
    "#be185d",
    "#4b5563",
]


class VegetationZoningRequest(ProviderModel):
    model_config = ConfigDict(
        alias_generator=ProviderModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="forbid",
    )

    index_type: str
    image_date: date
    zone_count: int = Field(ge=2, le=12)
    min_zone_area: float = Field(gt=0)
    provider: ProviderChoice = "auto"
    async_processing: bool = True
    callback_url: str | None = None


class ZoningMetadataPublic(ProviderModel):
    requested_at: str | None = None
    image_date: date | None = None
    index_type: str | None = None
    zone_count: int | None = None
    min_zone_area_ha: float | None = None
    status_updated_at: str | None = None
    source: Literal["provider-adapter"] = "provider-adapter"


class ZoningZonePublic(ProviderModel):
    zone_id: str
    color: str
    area_ha: float | None = None
    area_percent: float | None = None
    cluster_value: float | None = None
    geometry: dict[str, Any] | None = None


class ZoningMapPublic(ProviderModel):
    plot_id: str
    map_id: str
    provider: str
    status: ZoningStatus
    map_type: str
    index_type: str | None = None
    image_date: date | None = None
    zone_count: int | None = None
    min_zone_area_ha: float | None = None
    zones: list[ZoningZonePublic] = Field(default_factory=list)
    metadata: ZoningMetadataPublic


class ZoningMapListResponse(ProviderModel):
    plot_id: str
    provider: str
    maps: list[ZoningMapPublic]


async def _run_blocking(
    func,
    *args,
    error_scope: Literal["storage", "provider"] = "storage",
    **kwargs,
):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("field zoning backend unavailable: %s", type(exc).__name__)
        if error_scope == "provider":
            raise AkashaError(
                "PROVIDER_UPSTREAM_ERROR",
                "Zoning provider is unavailable.",
                502,
                {"provider": "eos"},
            ) from exc
        raise plots_backend_unavailable(
            "Field zoning storage is not available in this environment."
        ) from exc


async def _get_plot_or_404(plot_id: str) -> dict[str, Any]:
    plot = await _run_blocking(plots_repo.get_plot, plot_id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    return plot


def _is_eos_ready() -> bool:
    mode = (settings.provider_mode or "disabled").strip().lower()
    return bool(settings.eos_api_key.strip()) and settings.eos_enabled and mode in {"eos", "hybrid"}


def _normalize_index(value: str) -> str:
    index_type = value.strip().upper()
    if index_type not in PROVIDER_ZONING_INDEXES:
        raise bad_request(
            f"Unsupported zoning index '{value}'.",
            code="UNSUPPORTED_ZONING_INDEX",
            indexType=value,
            supported=sorted(PROVIDER_ZONING_INDEXES),
        )
    return index_type


def _resolve_external_field_id(plot_id: str, plot: dict[str, Any], provider: ProviderChoice) -> str:
    if provider == "native":
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "Native zoning provider is not available yet.",
            503,
            {"provider": "native"},
        )
    external_field_id = plot.get("externalFieldId")
    if not external_field_id:
        raise AkashaError(
            "FIELD_PROVIDER_NOT_SYNCED",
            "Sync the selected field before creating zoning maps.",
            409,
            {"provider": "eos", "plotId": plot_id},
        )
    if not _is_eos_ready():
        raise AkashaError(
            "PROVIDER_UNAVAILABLE",
            "Zoning provider is not available.",
            503,
            {"provider": "eos"},
        )
    return str(external_field_id)


def _normalize_status(value: str | None) -> ZoningStatus:
    status = (value or "unknown").strip().lower()
    if status in {"created", "pending", "processing", "running", "queued"}:
        return "processing"
    if status in {"ready", "done", "success", "finished", "completed"}:
        return "ready"
    if status in {"failed", "error", "rejected"}:
        return "failed"
    return "unknown"


def _safe_metadata(row: dict[str, Any]) -> ZoningMetadataPublic:
    return ZoningMetadataPublic(
        requested_at=row.get("createdAt"),
        image_date=date.fromisoformat(row["imageDate"]) if row.get("imageDate") else None,
        index_type=row.get("indexType"),
        zone_count=row.get("zoneCount"),
        min_zone_area_ha=row.get("minZoneAreaHa"),
        status_updated_at=row.get("updatedAt"),
    )


def _zone_public(zone: ZoningZone, index: int) -> ZoningZonePublic:
    return ZoningZonePublic(
        zone_id=zone.zone_id,
        color=ZONE_COLORS[index % len(ZONE_COLORS)],
        area_ha=zone.area_ha,
        area_percent=zone.area_percent,
        cluster_value=zone.fertilizer,
        geometry=zone.geometry,
    )


def _public_map(row: dict[str, Any], detail: ZoningMapStatus | None = None) -> ZoningMapPublic:
    zones = [_zone_public(zone, idx) for idx, zone in enumerate(detail.zones)] if detail else []
    detail_status = detail.status if detail else row["status"]
    detail_map_type = detail.map_type if detail else row["mapType"]
    detail_index = detail.index if detail and detail.index else row.get("indexType")
    detail_zone_count = (
        detail.zone_count
        if detail and detail.zone_count is not None
        else row.get("zoneCount") or (len(zones) if zones else None)
    )
    return ZoningMapPublic(
        plot_id=row["plotId"],
        map_id=row["id"],
        provider=row["provider"],
        status=_normalize_status(detail_status),
        map_type=detail_map_type,
        index_type=detail_index,
        image_date=date.fromisoformat(row["imageDate"]) if row.get("imageDate") else None,
        zone_count=detail_zone_count,
        min_zone_area_ha=row.get("minZoneAreaHa"),
        zones=zones,
        metadata=_safe_metadata(row),
    )


def _best_scene_for_date(external_field_id: str, image_date: date) -> SceneMetadata:
    provider = EosSceneProvider()
    request = provider.search_scenes(
        external_field_id,
        image_date,
        image_date,
        sensors=["sentinel2"],
        limit=100,
    )
    scenes = (
        provider.get_scene_search_result(external_field_id, request.request_id)
        if request.request_id
        else []
    )
    exact = [scene for scene in scenes if scene.acquisition_date == image_date]
    if not exact:
        raise not_found(
            "No provider scene is available for the selected field and image date.",
            code="ZONING_SCENE_NOT_FOUND",
            imageDate=image_date.isoformat(),
        )
    return max(exact, key=_best_scene_key)


def _create_zoning_map(
    *,
    plot_id: str,
    external_field_id: str,
    payload: VegetationZoningRequest,
    index_type: str,
) -> ZoningMapPublic:
    scene = _best_scene_for_date(external_field_id, payload.image_date)
    dataset_id = scene.view_id or scene.scene_id
    if not dataset_id:
        raise not_found(
            "Provider scene cannot be used for zoning because it has no dataset id.",
            code="ZONING_SCENE_NOT_FOUND",
            imageDate=payload.image_date.isoformat(),
        )
    request = EosZoningProvider().create_vegetation_map(
        external_field_id,
        index=index_type,
        zone_quantity=payload.zone_count,
        min_zone_area=payload.min_zone_area,
        dataset_id=dataset_id,
        image_date=payload.image_date,
    )
    status = _normalize_status(request.status)
    row = zoning_repo.create_zoning_map(
        plot_id=plot_id,
        provider="eos",
        external_zmap_id=request.external_zmap_id,
        provider_request_id=request.request_id,
        status=status,
        map_type="vegetation",
        index_type=index_type,
        image_date=payload.image_date,
        zone_count=payload.zone_count,
        min_zone_area_ha=payload.min_zone_area,
        metadata={
            "source": "provider-adapter",
            "requestedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "imageDate": payload.image_date.isoformat(),
            "indexType": index_type,
            "zoneCount": payload.zone_count,
            "minZoneAreaHa": payload.min_zone_area,
        },
    )
    return _public_map(row)


def _sync_provider_maps(plot_id: str, external_field_id: str) -> None:
    provider = EosZoningProvider()
    for item in provider.list_zoning_maps(external_field_id):
        if not item.external_zmap_id:
            continue
        zoning_repo.create_zoning_map(
            plot_id=plot_id,
            provider=item.provider,
            external_zmap_id=item.external_zmap_id,
            status=_normalize_status(item.status),
            map_type=item.map_type,
            index_type=item.index,
            zone_count=item.zone_count,
            metadata={"source": "provider-adapter"},
        )


def _load_detail(plot_id: str, external_field_id: str, row: dict[str, Any]) -> ZoningMapPublic:
    external_zmap_id = row.get("externalZmapId")
    if not external_zmap_id:
        return _public_map(row)
    detail = EosZoningProvider().get_zoning_map(external_field_id, external_zmap_id)
    updated = zoning_repo.update_zoning_map(
        plot_id,
        row["id"],
        status=_normalize_status(detail.status),
        index_type=detail.index,
        zone_count=detail.zone_count or len(detail.zones),
        metadata={"source": "provider-adapter"},
    )
    return _public_map(updated or row, detail)


@router.post(
    "/fields/{plot_id}/zoning/vegetation",
    response_model=ZoningMapPublic,
    response_model_by_alias=True,
)
async def create_vegetation_zoning_map(
    plot_id: str,
    payload: VegetationZoningRequest,
) -> ZoningMapPublic:
    if payload.callback_url:
        raise bad_request(
            "Browser-supplied zoning callbacks are not supported.",
            code="CALLBACK_UNSUPPORTED",
        )
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, payload.provider)
    index_type = _normalize_index(payload.index_type)
    return await _run_blocking(
        _create_zoning_map,
        plot_id=plot_id,
        external_field_id=external_field_id,
        payload=payload,
        index_type=index_type,
        error_scope="provider",
    )


@router.get(
    "/fields/{plot_id}/zoning/maps",
    response_model=ZoningMapListResponse,
    response_model_by_alias=True,
)
async def list_zoning_maps(
    plot_id: str,
    provider: ProviderChoice = "auto",
) -> ZoningMapListResponse:
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, provider)
    await _run_blocking(
        _sync_provider_maps,
        plot_id,
        external_field_id,
        error_scope="provider",
    )
    rows = await _run_blocking(zoning_repo.list_zoning_maps, plot_id)
    return ZoningMapListResponse(
        plot_id=plot_id,
        provider="eos",
        maps=[_public_map(row) for row in rows],
    )


@router.get(
    "/fields/{plot_id}/zoning/maps/{map_id}",
    response_model=ZoningMapPublic,
    response_model_by_alias=True,
)
async def get_zoning_map(plot_id: str, map_id: str) -> ZoningMapPublic:
    plot = await _get_plot_or_404(plot_id)
    external_field_id = _resolve_external_field_id(plot_id, plot, "auto")
    row = await _run_blocking(zoning_repo.get_zoning_map, plot_id, map_id)
    if row is None:
        raise not_found("Zoning map not found.", code="ZONING_MAP_NOT_FOUND", mapId=map_id)
    return await _run_blocking(
        _load_detail,
        plot_id,
        external_field_id,
        row,
        error_scope="provider",
    )


def _feature_collection(zoning_map: ZoningMapPublic) -> dict[str, Any]:
    features = []
    for zone in zoning_map.zones:
        if not zone.geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": zone.geometry,
                "properties": {
                    "mapId": zoning_map.map_id,
                    "zoneId": zone.zone_id,
                    "color": zone.color,
                    "areaHa": zone.area_ha,
                    "areaPercent": zone.area_percent,
                    "clusterValue": zone.cluster_value,
                    "indexType": zoning_map.index_type,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _parts_from_geometry(geometry: dict[str, Any]) -> list[list[list[float]]]:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if geom_type == "Polygon":
        return [[[float(x), float(y)] for x, y, *_rest in ring] for ring in coords]
    if geom_type == "MultiPolygon":
        parts: list[list[list[float]]] = []
        for polygon in coords:
            parts.extend([[[float(x), float(y)] for x, y, *_rest in ring] for ring in polygon])
        return parts
    return []


def _shapefile_zip(zoning_map: ZoningMapPublic) -> bytes:
    try:
        import shapefile  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - covered by dependency validation
        raise AkashaError(
            "EXPORT_FORMAT_UNAVAILABLE",
            "SHP export dependency is not installed.",
            501,
            {"format": "shp"},
        ) from exc

    shp = BytesIO()
    shx = BytesIO()
    dbf = BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    writer.field("mapId", "C", size=36)
    writer.field("zoneId", "C", size=32)
    writer.field("areaHa", "F", decimal=4)
    writer.field("areaPct", "F", decimal=4)
    writer.field("cluster", "F", decimal=6)
    writer.field("indexType", "C", size=16)
    written = 0
    for zone in zoning_map.zones:
        if not zone.geometry:
            continue
        parts = _parts_from_geometry(zone.geometry)
        if not parts:
            continue
        writer.poly(parts)
        writer.record(
            zoning_map.map_id,
            zone.zone_id,
            zone.area_ha,
            zone.area_percent,
            zone.cluster_value,
            zoning_map.index_type or "",
        )
        written += 1
    writer.close()
    if written == 0:
        raise bad_request(
            "Zoning map has no zone geometries to export.",
            code="ZONING_ZONES_UNAVAILABLE",
            mapId=zoning_map.map_id,
        )
    prj = (
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
    )
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zones.shp", shp.getvalue())
        zf.writestr("zones.shx", shx.getvalue())
        zf.writestr("zones.dbf", dbf.getvalue())
        zf.writestr("zones.prj", prj)
    return archive.getvalue()


async def _zoning_map_for_export(plot_id: str, map_id: str) -> ZoningMapPublic:
    zoning_map = await get_zoning_map(plot_id, map_id)
    if not zoning_map.zones:
        raise bad_request(
            "Zoning map is not ready for export.",
            code="ZONING_MAP_NOT_READY",
            mapId=map_id,
        )
    return zoning_map


@router.get("/fields/{plot_id}/zoning/maps/{map_id}/export.geojson")
async def export_zoning_map_geojson(plot_id: str, map_id: str) -> JSONResponse:
    zoning_map = await _zoning_map_for_export(plot_id, map_id)
    filename = f"zoning_{_safe_filename(map_id)}.geojson"
    return JSONResponse(
        content=_feature_collection(zoning_map),
        media_type="application/geo+json",
        headers=_disposition(filename),
    )


@router.get("/fields/{plot_id}/zoning/maps/{map_id}/export.shp")
async def export_zoning_map_shp(plot_id: str, map_id: str) -> Response:
    zoning_map = await _zoning_map_for_export(plot_id, map_id)
    content = await _run_blocking(_shapefile_zip, zoning_map)
    filename = f"zoning_{_safe_filename(map_id)}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers=_disposition(filename),
    )
