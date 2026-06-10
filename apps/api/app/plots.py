"""Akasha BFF Plot API + GeoJSON import/export (Slice 3 — Phase 3).

Endpoints (all under /api):
  GET    /api/plots                          list saved plots (newest first)
  GET    /api/plots/export.geojson           export all plots (FeatureCollection)
  POST   /api/plots                          create a named plot from geometry
  POST   /api/plots/import/geojson           import FeatureCollection/Feature/raw geometry
  GET    /api/plots/{plotId}                 get one plot
  GET    /api/plots/{plotId}/export.geojson  export one plot (Feature)
  PATCH  /api/plots/{plotId}                 update name and/or geometry
  DELETE /api/plots/{plotId}                 delete a plot

Guardrails:
  * Geometry validated server-side via app.raster.geo_validate.validate_polygon
    (Polygon/MultiPolygon, validity, max area, max vertices). Client-provided
    area is never trusted — area is recomputed.
  * Blocking SQLAlchemy/PostGIS work runs off the event loop via anyio.to_thread.run_sync.
  * When PostGIS is unreachable (e.g. the Emergent preview has no DB) the routes
    return a sanitized 503 PLOTS_BACKEND_UNAVAILABLE — no DSN/credentials/SQL/
    stack traces are ever exposed to the client.
"""

from __future__ import annotations

import functools
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError, field_validator

from . import plots_repo
from .auth import CurrentTeam, CurrentUser, get_current_team, get_current_user, require_role
from .config import settings
from .raster.errors import (
    AkashaError,
    bad_request,
    invalid_geometry,
    not_found,
    plots_backend_unavailable,
)
from .raster.geo_validate import validate_polygon

logger = logging.getLogger("akasha.api.plots")

router = APIRouter(prefix="/api", tags=["plots"], dependencies=[Depends(get_current_team)])

GEOJSON_MEDIA_TYPE = "application/geo+json"
MAX_NAME_LENGTH = 200
MAX_IMPORT_FEATURES = 500
PlotStatus = Literal["planned", "active", "inactive", "archived"]
USER_METADATA_FIELDS = (
    "groupName",
    "cropType",
    "variety",
    "seasonLabel",
    "sowingDate",
    "plantingDate",
    "status",
)


# --------------------------------------------------------------------------
# Pydantic v2 models
# --------------------------------------------------------------------------
class PlotUserMetadata(BaseModel):
    groupName: str | None = None
    cropType: str | None = None
    variety: str | None = None
    seasonLabel: str | None = None
    sowingDate: date | None = None
    plantingDate: date | None = None
    status: PlotStatus | None = None

    @field_validator("sowingDate", "plantingDate", mode="before")
    @classmethod
    def _validate_date_only(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, datetime):
            raise ValueError("must be a date-only value")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            if "T" in value or " " in value:
                raise ValueError("must be a date-only value")
            return value
        raise ValueError("must be a date-only value")


class PlotCreate(PlotUserMetadata):
    name: str
    geometry: dict[str, Any]


class PlotUpdate(PlotUserMetadata):
    name: str | None = None
    geometry: dict[str, Any] | None = None


class PlotResponse(PlotUserMetadata):
    id: str
    name: str
    geometry: dict[str, Any]
    areaHa: float | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class RejectedFeature(BaseModel):
    index: int
    code: str
    message: str


class ImportResponse(BaseModel):
    imported: list[PlotResponse]
    rejected: list[RejectedFeature]
    importedCount: int
    rejectedCount: int


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
async def _run_repo(func, *args, **kwargs):
    """Run a blocking repo function in a worker thread.

    AkashaError passes through unchanged; any other exception (driver missing,
    DSN unset, connection refused, SQL error) is logged server-side and surfaced
    as a sanitized 503 so no internal detail leaks to the client.
    """
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("plots backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Plot storage is not available in this environment."
        ) from exc


def _clean_name(name: str | None, *, required: bool) -> str | None:
    if name is None:
        if required:
            raise bad_request("name is required.", code="INVALID_NAME")
        return None
    cleaned = name.strip()
    if not cleaned:
        raise bad_request("name must not be blank.", code="INVALID_NAME")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise bad_request(
            f"name exceeds {MAX_NAME_LENGTH} characters.",
            code="INVALID_NAME",
            maxLength=MAX_NAME_LENGTH,
        )
    return cleaned


def _valid_uuid(plot_id: str) -> str:
    try:
        return str(uuid.UUID(plot_id))
    except (ValueError, AttributeError, TypeError) as exc:
        # Invalid id is treated as not-found per the API contract.
        raise not_found("Plot not found.", plotId=plot_id) from exc


def _validate_geometry(geometry: dict[str, Any]) -> float | None:
    facts = validate_polygon(
        geometry,
        max_area_ha=settings.max_polygon_area_ha,
        max_vertices=settings.max_polygon_vertices,
    )
    return facts["areaHa"]


def _metadata_from_model(
    payload: PlotUserMetadata,
    *,
    include_nulls: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in USER_METADATA_FIELDS:
        if field not in payload.model_fields_set:
            continue
        value = getattr(payload, field)
        if value is None and not include_nulls:
            continue
        metadata[field] = value
    return metadata


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _to_feature(plot: dict[str, Any]) -> dict[str, Any]:
    properties = {
        "id": plot["id"],
        "name": plot["name"],
        "areaHa": plot["areaHa"],
        "createdAt": plot["createdAt"],
        "updatedAt": plot["updatedAt"],
    }
    for field in USER_METADATA_FIELDS:
        value = plot.get(field)
        if value is not None:
            properties[field] = _safe_json_value(value)
    return {
        "type": "Feature",
        "id": plot["id"],
        "geometry": plot["geometry"],
        "properties": properties,
    }


def _extract_features(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise bad_request("Request body must be a GeoJSON object.", code="INVALID_GEOJSON")
    geo_type = payload.get("type")
    if geo_type == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise bad_request("FeatureCollection.features must be a list.", code="INVALID_GEOJSON")
    elif geo_type == "Feature":
        features = [payload]
    elif geo_type in ("Polygon", "MultiPolygon"):
        features = [{"type": "Feature", "geometry": payload, "properties": {}}]
    else:
        raise bad_request(
            f"Unsupported GeoJSON type '{geo_type}'. Expected FeatureCollection, "
            "Feature, Polygon, or MultiPolygon.",
            code="INVALID_GEOJSON",
        )
    if not features:
        raise bad_request("No features to import.", code="INVALID_GEOJSON")
    if len(features) > MAX_IMPORT_FEATURES:
        raise bad_request(
            f"Too many features in import ({len(features)} > {MAX_IMPORT_FEATURES}).",
            code="TOO_MANY_FEATURES",
            maxFeatures=MAX_IMPORT_FEATURES,
            received=len(features),
        )
    return features


def _feature_geometry(feature: Any) -> dict[str, Any]:
    if not isinstance(feature, dict):
        raise invalid_geometry("Feature must be a GeoJSON object.")
    if feature.get("type") in ("Polygon", "MultiPolygon"):
        geometry = feature
    else:
        geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise invalid_geometry("Feature has no geometry object.")
    return geometry


def _resolve_import_name(feature: dict[str, Any], index: int) -> str:
    props = feature.get("properties") or {}
    if isinstance(props, dict):
        for key in ("name", "Name", "title"):
            value = props.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:MAX_NAME_LENGTH]
    return f"Imported plot {index + 1}"


def _sanitized_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "type": err.get("type"),
            "loc": list(err.get("loc", [])),
            "msg": err.get("msg"),
        }
        for err in exc.errors()
    ]


def _extract_import_metadata(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        return {}
    raw_metadata = {field: props[field] for field in USER_METADATA_FIELDS if field in props}
    if not raw_metadata:
        return {}
    try:
        metadata = PlotUserMetadata.model_validate(raw_metadata)
    except ValidationError as exc:
        raise bad_request(
            "Feature metadata is invalid.",
            code="INVALID_FIELD_METADATA",
            errors=_sanitized_validation_errors(exc),
        ) from exc
    return metadata.model_dump(exclude_unset=True)


# --------------------------------------------------------------------------
# Routes — specific paths BEFORE parameterized ones
# --------------------------------------------------------------------------
@router.get("/plots", response_model=list[PlotResponse], response_model_exclude_none=True)
async def list_plots(team: CurrentTeam = Depends(get_current_team)) -> list[dict[str, Any]]:
    return await _run_repo(plots_repo.list_plots, team.id)


@router.get("/plots/export.geojson")
async def export_all_plots(team: CurrentTeam = Depends(get_current_team)) -> JSONResponse:
    plots = await _run_repo(plots_repo.list_plots, team.id)
    feature_collection = {
        "type": "FeatureCollection",
        "features": [_to_feature(p) for p in plots],
    }
    return JSONResponse(content=feature_collection, media_type=GEOJSON_MEDIA_TYPE)


@router.post(
    "/plots",
    response_model=PlotResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_plot(
    payload: PlotCreate,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    name = _clean_name(payload.name, required=True)
    area_ha = _validate_geometry(payload.geometry)
    metadata = _metadata_from_model(payload, include_nulls=False)
    if metadata:
        created = await _run_repo(
            plots_repo.create_plot,
            name,
            payload.geometry,
            area_ha,
            metadata,
            owner_id=user.id,
            team_id=team.id,
        )
    else:
        created = await _run_repo(
            plots_repo.create_plot,
            name,
            payload.geometry,
            area_ha,
            owner_id=user.id,
            team_id=team.id,
        )
    return created


@router.post(
    "/plots/import/geojson",
    response_model=ImportResponse,
    response_model_exclude_none=True,
)
async def import_geojson(
    payload: dict[str, Any] = Body(...),
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    features = _extract_features(payload)
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        try:
            geometry = _feature_geometry(feature)
            name = _resolve_import_name(feature, index)
            area_ha = _validate_geometry(geometry)
            metadata = _extract_import_metadata(feature)
            valid.append(
                {
                    "name": name,
                    "geometry": geometry,
                    "areaHa": area_ha,
                    "metadata": metadata,
                }
            )
        except AkashaError as exc:
            rejected.append({"index": index, "code": exc.code, "message": exc.message})
    imported = (
        await _run_repo(plots_repo.create_plots_bulk, valid, owner_id=user.id, team_id=team.id)
        if valid
        else []
    )
    return {
        "imported": imported,
        "rejected": rejected,
        "importedCount": len(imported),
        "rejectedCount": len(rejected),
    }


@router.get(
    "/plots/{plot_id}",
    response_model=PlotResponse,
    response_model_exclude_none=True,
)
async def get_plot(plot_id: str, team: CurrentTeam = Depends(get_current_team)) -> dict[str, Any]:
    pid = _valid_uuid(plot_id)
    plot = await _run_repo(plots_repo.get_plot, pid, team.id)
    if plot is None:
        raise not_found("Plot not found.", plotId=plot_id)
    return plot


@router.get("/plots/{plot_id}/export.geojson")
async def export_plot(plot_id: str, team: CurrentTeam = Depends(get_current_team)) -> JSONResponse:
    pid = _valid_uuid(plot_id)
    plot = await _run_repo(plots_repo.get_plot, pid, team.id)
    if plot is None:
        raise not_found("Plot not found.", plotId=plot_id)
    return JSONResponse(content=_to_feature(plot), media_type=GEOJSON_MEDIA_TYPE)


@router.patch(
    "/plots/{plot_id}",
    response_model=PlotResponse,
    response_model_exclude_none=True,
)
async def update_plot(
    plot_id: str,
    payload: PlotUpdate,
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> dict[str, Any]:
    pid = _valid_uuid(plot_id)
    metadata = _metadata_from_model(payload, include_nulls=True)
    if payload.name is None and payload.geometry is None and not metadata:
        raise bad_request(
            "Provide at least one of 'name', 'geometry', or metadata to update.",
            code="NO_UPDATE_FIELDS",
        )
    name = _clean_name(payload.name, required=False)
    area_ha = None
    geometry = None
    if payload.geometry is not None:
        area_ha = _validate_geometry(payload.geometry)
        geometry = payload.geometry
    if metadata:
        plot = await _run_repo(
            plots_repo.update_plot,
            pid,
            name,
            geometry,
            area_ha,
            metadata,
            team.id,
        )
    else:
        plot = await _run_repo(
            plots_repo.update_plot,
            pid,
            name,
            geometry,
            area_ha,
            team_id=team.id,
        )
    if plot is None:
        raise not_found("Plot not found.", plotId=plot_id)
    return plot


@router.delete("/plots/{plot_id}", status_code=204)
async def delete_plot(
    plot_id: str,
    team: CurrentTeam = Depends(require_role("owner", "admin", "member")),
) -> Response:
    pid = _valid_uuid(plot_id)
    deleted = await _run_repo(plots_repo.delete_plot, pid, team.id)
    if not deleted:
        raise not_found("Plot not found.", plotId=plot_id)
    return Response(status_code=204)
