"""Transparent field-watch risk context."""
from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query
from pydantic import Field

from . import phase10_repo, plots_repo
from .api_models import ApiModel, CloudMaskOptions
from .auth import CurrentTeam, get_current_team
from .config import settings
from .field_analytics import _field_statistics
from .raster import catalog_resolver as catalog
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
from .raster.indices import DEFAULT_INDEX, get_index

logger = logging.getLogger("akasha.api.risk")
router = APIRouter(prefix="/api", tags=["risk"], dependencies=[Depends(get_current_team)])

RiskLevel = Literal["low", "medium", "high", "unknown"]
MODEL_VERSION = "field-watch-generic-v1"
STAGE_MODEL_VERSION = "generic-v1"
NORMALIZED_RISK_INDICES = {"NDVI", "NDRE", "NDMI"}
DEFAULT_LOOKBACK_DAYS = 90
MAX_LOOKBACK_DAYS = 180
DEFAULT_SCENE_SCAN_LIMIT = 8
MAX_SCENE_SCAN_LIMIT = 12
COMPONENT_WEIGHTS = {
    "vegetationCondition": 0.35,
    "vegetationTrend": 0.25,
    "dataGap": 0.15,
    "weatherStress": 0.15,
    "scoutingTasks": 0.10,
}


@dataclass(frozen=True)
class UsablePoint:
    acquisition_date: date
    mean: float
    valid_pixel_percent: float
    cloud_masked_percent: float


class WeatherStressFlags(ApiModel):
    heat: bool | None = None
    dryness: bool | None = None
    excess_rain: bool | None = None


class RiskComponent(ApiModel):
    id: str
    label: str
    available: bool
    level: RiskLevel = "unknown"
    score: float | None = None
    weight: float
    used_in_aggregate: bool
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source: str = "akasha"
    flags: WeatherStressFlags | None = None


class CropStageSummary(ApiModel):
    crop_type: str | None = None
    start_date: date | None = None
    start_date_type: Literal["sowingDate", "plantingDate", "unknown"] = "unknown"
    days_after_start: int | None = None
    stage_label: str = "unknown"
    model_version: str = STAGE_MODEL_VERSION
    limitations: list[str] = Field(default_factory=list)


class FieldRiskSummaryResponse(ApiModel):
    plot_id: str
    field_watch_level: RiskLevel
    vegetation_stress_context: str
    score: float | None = None
    components: list[RiskComponent]
    crop_stage: CropStageSummary
    limitations: list[str]
    metadata: dict[str, Any]


async def _run_blocking(
    func,
    *args,
    **kwargs,
):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Risk storage is not available.") from exc


def _level(score: float | None) -> RiskLevel:
    if score is None:
        return "unknown"
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def _component(
    component_id: str,
    label: str,
    *,
    available: bool,
    score: float | None,
    evidence: list[str] | None = None,
    limitations: list[str] | None = None,
    source: str = "akasha",
    flags: WeatherStressFlags | None = None,
) -> RiskComponent:
    return RiskComponent(
        id=component_id,
        label=label,
        available=available,
        level=_level(score),
        score=round(score, 4) if score is not None else None,
        weight=COMPONENT_WEIGHTS[component_id],
        used_in_aggregate=available and score is not None,
        evidence=evidence or [],
        limitations=limitations or [],
        source=source,
        flags=flags,
    )


def _date_range(start: date | None, end: date | None, lookback_days: int) -> tuple[date, date]:
    if lookback_days < 1 or lookback_days > MAX_LOOKBACK_DAYS:
        raise bad_request(
            f"lookbackDays must be between 1 and {MAX_LOOKBACK_DAYS}.",
            code="INVALID_LOOKBACK_DAYS",
            maxDays=MAX_LOOKBACK_DAYS,
        )
    end_date = end or datetime.now(UTC).date()
    start_date = start or end_date - timedelta(days=lookback_days)
    if start_date > end_date:
        raise bad_request("startDate must be on or before endDate.", code="INVALID_DATE_RANGE")
    return start_date, end_date


def _scene_dates(source_id: str, start: date, end: date, limit: int) -> list[str]:
    if limit < 1 or limit > MAX_SCENE_SCAN_LIMIT:
        raise bad_request(
            f"sceneScanLimit must be between 1 and {MAX_SCENE_SCAN_LIMIT}.",
            code="INVALID_SCENE_SCAN_LIMIT",
            maxScenes=MAX_SCENE_SCAN_LIMIT,
        )
    return sorted(
        [
            item["acquisitionDate"]
            for item in catalog.list_dates(source_id)
            if start <= date.fromisoformat(item["acquisitionDate"]) <= end
        ],
        reverse=True,
    )[:limit]


def _validate_index(source_id: str, index_type: str) -> str:
    normalized = index_type.strip().upper()
    supported = catalog.supported_indices(source_id)
    try:
        get_index(normalized)
    except KeyError as exc:
        raise bad_request(
            "Unsupported risk index.",
            code="INVALID_INDEX_TYPE",
            indexType=index_type,
            supported=supported,
        ) from exc
    if normalized not in supported:
        raise bad_request(
            "Unsupported risk index for source.",
            code="INVALID_INDEX_TYPE",
            indexType=index_type,
            sourceId=source_id,
            supported=supported,
        )
    return normalized


def _is_usable(stats) -> bool:
    s = stats.statistics
    threshold = settings.usable_pixel_threshold_percent
    if s.mean is None:
        return False
    if bool(stats.metadata.get("metricsProvisional", False)):
        return False
    if s.validPixelPercent < threshold:
        return False
    if s.cloudMaskedPercent is not None and s.cloudMaskedPercent > (100 - threshold):
        return False
    return True


def _latest_usable_points(
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    dates: list[str],
) -> list[UsablePoint]:
    points: list[UsablePoint] = []
    for acquisition_date in dates:
        try:
            stats = _field_statistics(
                plot_id=plot_id,
                plot=plot,
                source_id=source_id,
                acquisition_date=acquisition_date,
                index_type=index_type,
                cloud_mask=CloudMaskOptions(),
            )
        except AkashaError:
            continue
        if not _is_usable(stats):
            continue
        points.append(
            UsablePoint(
                acquisition_date=date.fromisoformat(stats.acquisition_date),
                mean=float(stats.statistics.mean),
                valid_pixel_percent=stats.statistics.validPixelPercent,
                cloud_masked_percent=stats.statistics.cloudMaskedPercent,
            )
        )
        if len(points) == 2:
            break
    return points


def _stage(plot: dict[str, Any]) -> CropStageSummary:
    crop_type = plot.get("cropType")
    raw_start = plot.get("plantingDate") or plot.get("sowingDate")
    start_type: Literal["sowingDate", "plantingDate", "unknown"]
    if plot.get("plantingDate"):
        start_type = "plantingDate"
    elif plot.get("sowingDate"):
        start_type = "sowingDate"
    else:
        start_type = "unknown"
    if not raw_start:
        return CropStageSummary(
            crop_type=crop_type,
            limitations=[
                "Crop stage unavailable until crop and sowing/planting date are recorded."
            ],
        )
    start = date.fromisoformat(str(raw_start))
    raw_days = (datetime.now(UTC).date() - start).days
    if raw_days < 0:
        return CropStageSummary(
            crop_type=crop_type,
            start_date=start,
            start_date_type=start_type,
            days_after_start=None,
            stage_label="not started",
            limitations=[
                "Crop stage is not active because the sowing/planting date is in the future."
            ],
        )
    days = raw_days
    if days <= 14:
        label = "establishment"
    elif days <= 45:
        label = "vegetative"
    elif days <= 75:
        label = "reproductive/flowering"
    elif days <= 110:
        label = "grain fill/maturation"
    else:
        label = "harvest/late season"
    return CropStageSummary(
        crop_type=crop_type,
        start_date=start,
        start_date_type=start_type,
        days_after_start=days,
        stage_label=label,
        limitations=[
            "Generic stage model; crop- and region-specific calendars require validation."
        ],
    )


async def _weather_component(_plot: dict[str, Any]) -> RiskComponent:
    return _component(
        "weatherStress",
        "Weather stress",
        available=False,
        score=None,
        source="unavailable",
        flags=WeatherStressFlags(),
        limitations=[
            "Weather stress evidence is unavailable until a native weather source is configured."
        ],
    )


async def _scout_component(plot_id: str, team_id: str | None) -> RiskComponent:
    try:
        tasks = await _run_blocking(
            phase10_repo.list_scout_tasks,
            {"plotId": plot_id, "status": "new"},
            team_id,
        )
    except AkashaError:
        tasks = []
    count = len(tasks)
    score = min(1.0, count / 3)
    return _component(
        "scoutingTasks",
        "Open scouting tasks",
        available=True,
        score=score,
        evidence=[f"{count} open scouting tasks."],
    )


def _components_from_points(index_type: str, points: list[UsablePoint]) -> list[RiskComponent]:
    if not points:
        unavailable = [
            _component(
                key,
                label,
                available=False,
                score=None,
                limitations=["No usable cloud-free index scene found in the requested range."],
            )
            for key, label in (
                ("vegetationCondition", "Vegetation condition"),
                ("vegetationTrend", "Vegetation trend"),
                ("dataGap", "Cloud/data gap"),
            )
        ]
        return unavailable
    latest = points[0]
    if index_type not in NORMALIZED_RISK_INDICES:
        condition = _component(
            "vegetationCondition",
            "Vegetation condition",
            available=False,
            score=None,
            limitations=[f"{index_type} is not normalized for generic risk scoring."],
        )
    else:
        vigor = max(0.0, min(1.0, (latest.mean + 1.0) / 2.0))
        condition = _component(
            "vegetationCondition",
            "Vegetation condition",
            available=True,
            score=1.0 - vigor,
            evidence=[f"Latest {index_type} value {latest.mean:.3f} on {latest.acquisition_date}."],
            limitations=[
                "Vegetation indices indicate canopy condition, not disease or pest presence."
            ],
        )
    previous = points[1] if len(points) > 1 else None
    if previous:
        delta = latest.mean - previous.mean
        trend_score = max(0.0, min(1.0, -delta / 0.2))
        trend = _component(
            "vegetationTrend",
            "Vegetation trend",
            available=True,
            score=trend_score,
            evidence=[f"{index_type} changed by {delta:.3f} since {previous.acquisition_date}."],
            limitations=["Negative trend is a scouting signal, not a diagnosis."],
        )
    else:
        trend = _component(
            "vegetationTrend",
            "Vegetation trend",
            available=False,
            score=None,
            limitations=["A previous usable scene was not available for trend comparison."],
        )
    recency_days = max(0, (datetime.now(UTC).date() - latest.acquisition_date).days)
    data_gap = _component(
        "dataGap",
        "Cloud/data gap",
        available=True,
        score=max(0.0, min(1.0, recency_days / 30)),
        evidence=[f"Latest usable scene is {recency_days} days old."],
    )
    return [condition, trend, data_gap]


def _aggregate(components: list[RiskComponent]) -> tuple[RiskLevel, float | None, dict[str, Any]]:
    imagery_available = any(
        component.id in {"vegetationCondition", "vegetationTrend", "dataGap"}
        and component.used_in_aggregate
        for component in components
    )
    if not imagery_available:
        return "unknown", None, {
            "excludedWeights": [component.id for component in components],
            "aggregateUnavailableReason": "No usable imagery evidence was available.",
        }
    used = [
        component
        for component in components
        if component.used_in_aggregate and component.score is not None
    ]
    excluded = [component.id for component in components if not component.used_in_aggregate]
    if not used:
        return "unknown", None, {"excludedWeights": excluded}
    total_weight = sum(component.weight for component in used)
    score = sum(component.weight * float(component.score) for component in used) / total_weight
    return _level(score), round(score, 4), {"excludedWeights": excluded}


@router.get(
    "/fields/{plot_id}/risk/summary",
    response_model=FieldRiskSummaryResponse,
    response_model_by_alias=True,
)
async def get_field_risk_summary(
    plot_id: str,
    indexType: str = Query(default=DEFAULT_INDEX),
    sourceId: str = Query(default=settings.default_source_id),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    lookbackDays: int = Query(default=DEFAULT_LOOKBACK_DAYS),
    sceneScanLimit: int = Query(default=DEFAULT_SCENE_SCAN_LIMIT),
    team: CurrentTeam = Depends(get_current_team),
) -> FieldRiskSummaryResponse:
    plot = await _run_blocking(plots_repo.get_plot, plot_id, team.id)
    if plot is None:
        raise not_found("Field not found.", code="FIELD_NOT_FOUND", plotId=plot_id)
    index_type = _validate_index(sourceId, indexType)
    start, end = _date_range(startDate, endDate, lookbackDays)
    dates = _scene_dates(sourceId, start, end, sceneScanLimit)
    try:
        points = await asyncio.wait_for(
            _run_blocking(_latest_usable_points, plot_id, plot, sourceId, index_type, dates),
            timeout=settings.index_request_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk imagery evidence unavailable: %s", type(exc).__name__)
        points = []
    components = _components_from_points(index_type, points)
    components.append(await _weather_component(plot))
    components.append(await _scout_component(plot_id, team.id))
    level, score, aggregate_meta = _aggregate(components)
    limitations = [
        "This is decision-support field-watch context only.",
        "High means prioritize field scouting; it does not indicate disease or pest presence.",
        "Do not use this output as diagnosis, treatment advice, or insurance determination.",
    ]
    metadata = {
        "modelVersion": MODEL_VERSION,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "weights": COMPONENT_WEIGHTS,
        "thresholds": {"lowBelow": 0.33, "mediumBelow": 0.66},
        "aggregateMethod": "weighted average over available components",
        "usedEvidenceTypes": [c.id for c in components if c.used_in_aggregate],
        **aggregate_meta,
    }
    return FieldRiskSummaryResponse(
        plot_id=plot_id,
        field_watch_level=level,
        vegetation_stress_context=(
            "Scouting priority context. not a disease or pest diagnostic model."
        ),
        score=score,
        components=components,
        crop_stage=_stage(plot),
        limitations=limitations,
        metadata=metadata,
    )
