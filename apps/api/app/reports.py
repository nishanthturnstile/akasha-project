"""Field leaderboard and reporting routes for EOS-parity Phase 9."""
from __future__ import annotations

import asyncio
import csv
import functools
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import ConfigDict, Field

from . import plots_repo, reports_repo
from .auth import get_current_team
from .config import settings
from .field_analytics import _field_statistics
from .field_exports import _disposition, _safe_filename
from .providers.models import CloudMaskOptions, ProviderModel
from .raster import catalog_resolver as catalog
from .raster.errors import AkashaError, bad_request, not_found, plots_backend_unavailable
from .raster.indices import DEFAULT_INDEX

logger = logging.getLogger("akasha.api.reports")

router = APIRouter(prefix="/api", tags=["reports"], dependencies=[Depends(get_current_team)])

SORT_KEYS = {
    "rank",
    "score",
    "latestIndexValue",
    "indexDelta",
    "cloudFreeRecencyDays",
    "areaHa",
    "name",
    "latestImageDate",
}
SAFE_FILTER_KEYS = {
    "indexType",
    "groupName",
    "cropType",
    "variety",
    "seasonLabel",
    "search",
    "startDate",
    "endDate",
}
LEADERBOARD_COLUMNS = {
    "rank": "Rank",
    "field": "Field",
    "group": "Group",
    "crop": "Crop",
    "variety": "Variety",
    "season": "Season",
    "location": "Location",
    "coordinates": "Coordinates",
    "areaHa": "Area (ha)",
    "sowingDate": "Sowing date",
    "plantingDate": "Planting date",
    "latestIndexValue": "Index value",
    "indexDelta": "Value change",
    "cloudFreeRecencyDays": "Cloud-free recency (days)",
    "weatherRiskLabel": "Weather risk summary",
    "weatherRiskLevel": "Weather risk level",
    "actualYield": "Actual yield",
    "latestImageDate": "Image date",
    "score": "Score",
    "preview": "Preview",
    "open": "Open",
}
DEFAULT_COLUMNS = [
    "rank",
    "field",
    "group",
    "crop",
    "variety",
    "location",
    "areaHa",
    "sowingDate",
    "latestIndexValue",
    "indexDelta",
    "cloudFreeRecencyDays",
    "weatherRiskLabel",
    "actualYield",
    "latestImageDate",
    "score",
    "preview",
]
DEFAULT_LOOKBACK_DAYS = 90
MAX_LOOKBACK_DAYS = 180
DEFAULT_EVALUATION_LIMIT = 100
MAX_EVALUATION_LIMIT = 100
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100
DEFAULT_SCENE_SCAN_LIMIT = 8
MAX_SCENE_SCAN_LIMIT = 12


class LeaderboardScoreComponents(ProviderModel):
    vigor: float | None = None
    trend: float | None = None
    recency: float | None = None
    weather: float | None = None


class FieldLeaderboardRow(ProviderModel):
    plot_id: str
    rank: int | None = None
    name: str
    field: str
    group_name: str | None = None
    crop_type: str | None = None
    variety: str | None = None
    season_label: str | None = None
    location: str | None = None
    coordinates: list[float] | None = None
    area_ha: float | None = None
    sowing_date: str | None = None
    planting_date: str | None = None
    latest_index_value: float | None = None
    latest_image_date: date | None = None
    index_delta: float | None = None
    previous_image_date: date | None = None
    cloud_free_recency_days: int | None = None
    weather_risk_label: str = "Weather risk pending field weather aggregation"
    weather_risk_level: Literal["unknown"] = "unknown"
    actual_yield: float | None = None
    score: float | None = None
    score_components: LeaderboardScoreComponents = Field(default_factory=LeaderboardScoreComponents)
    data_available: bool
    unavailable_reason: str | None = None
    preview: str | None = None
    open: str | None = None


class FieldLeaderboardResponse(ProviderModel):
    index_type: str
    generated_at: str
    rows: list[FieldLeaderboardRow]
    metadata: dict[str, Any]


class ReportTemplatePayload(ProviderModel):
    model_config = ConfigDict(alias_generator=None, populate_by_name=True)

    name: str
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: dict[str, Any] = Field(default_factory=dict)


class ReportTemplateUpdate(ProviderModel):
    model_config = ConfigDict(alias_generator=None, populate_by_name=True)

    name: str | None = None
    columns: list[str] | None = None
    filters: dict[str, Any] | None = None
    sort: dict[str, Any] | None = None


class ReportTemplate(ProviderModel):
    id: str
    name: str
    columns: list[str]
    filters: dict[str, Any]
    sort: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class UsablePoint:
    acquisition_date: date
    mean: float
    valid_pixel_percent: float
    cloud_masked_percent: float


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("reports backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Report storage is not available in this environment."
        ) from exc


def _normalize_index(value: str | None) -> str:
    return (value or DEFAULT_INDEX).strip().upper()


def _validate_columns(columns: list[str]) -> list[str]:
    unknown = [column for column in columns if column not in LEADERBOARD_COLUMNS]
    if unknown:
        raise bad_request(
            "Unknown report column.",
            code="INVALID_REPORT_COLUMN",
            unsupported=unknown,
            supported=sorted(LEADERBOARD_COLUMNS),
        )
    return columns


def _validate_filters(filters: dict[str, Any]) -> dict[str, Any]:
    unknown = [key for key in filters if key not in SAFE_FILTER_KEYS]
    if unknown:
        raise bad_request(
            "Unsupported report filter.",
            code="INVALID_REPORT_FILTER",
            unsupported=unknown,
            supported=sorted(SAFE_FILTER_KEYS),
        )
    return filters


def _validate_sort(sort: dict[str, Any]) -> dict[str, Any]:
    key = sort.get("sortBy")
    if key is not None and key not in SORT_KEYS:
        raise bad_request(
            "Unsupported report sort key.",
            code="INVALID_REPORT_SORT",
            sortBy=key,
            supported=sorted(SORT_KEYS),
        )
    return sort


def _template_from_row(row: dict[str, Any]) -> ReportTemplate:
    return ReportTemplate(**row)


def _date_range(
    start_date: date | None,
    end_date: date | None,
    lookback_days: int,
) -> tuple[date, date]:
    if lookback_days < 1 or lookback_days > MAX_LOOKBACK_DAYS:
        raise bad_request(
            f"lookbackDays must be between 1 and {MAX_LOOKBACK_DAYS}.",
            code="INVALID_LOOKBACK_DAYS",
            maxDays=MAX_LOOKBACK_DAYS,
        )
    end = end_date or datetime.now(UTC).date()
    start = start_date or (end - timedelta(days=lookback_days))
    if start > end:
        raise bad_request("startDate must be on or before endDate.", code="INVALID_DATE_RANGE")
    return start, end


def _scene_dates(source_id: str, start: date, end: date, scene_scan_limit: int) -> list[str]:
    if scene_scan_limit < 1 or scene_scan_limit > MAX_SCENE_SCAN_LIMIT:
        raise bad_request(
            f"sceneScanLimit must be between 1 and {MAX_SCENE_SCAN_LIMIT}.",
            code="INVALID_SCENE_SCAN_LIMIT",
            maxScenes=MAX_SCENE_SCAN_LIMIT,
        )
    dates = [
        item["acquisitionDate"]
        for item in catalog.list_dates(source_id)
        if start <= date.fromisoformat(item["acquisitionDate"]) <= end
    ]
    return sorted(dates, reverse=True)[:scene_scan_limit]


def _flatten_positions(value: Any) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            points.append((float(value[0]), float(value[1])))
        else:
            for item in value:
                points.extend(_flatten_positions(item))
    return points


def _coordinates(plot: dict[str, Any]) -> list[float] | None:
    geometry = plot.get("geometry") or {}
    points = _flatten_positions(geometry.get("coordinates"))
    if not points:
        return None
    lngs = [point[0] for point in points]
    lats = [point[1] for point in points]
    return [round((min(lngs) + max(lngs)) / 2, 6), round((min(lats) + max(lats)) / 2, 6)]


def _location(coords: list[float] | None) -> str | None:
    if not coords:
        return None
    return f"{coords[1]:.4f}, {coords[0]:.4f}"


def _filter_plots(
    plots: list[dict[str, Any]],
    *,
    group_name: str | None,
    crop_type: str | None,
    variety: str | None,
    season_label: str | None,
    search: str | None,
) -> list[dict[str, Any]]:
    def matches(plot: dict[str, Any]) -> bool:
        checks = (
            ("groupName", group_name),
            ("cropType", crop_type),
            ("variety", variety),
            ("seasonLabel", season_label),
        )
        for field, expected in checks:
            if expected and str(plot.get(field) or "").lower() != expected.lower():
                return False
        if search:
            haystack = " ".join(
                str(plot.get(field) or "")
                for field in ("name", "groupName", "cropType", "variety", "seasonLabel")
            ).lower()
            return search.lower() in haystack
        return True

    return [plot for plot in plots if matches(plot)]


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
    *,
    plot_id: str,
    plot: dict[str, Any],
    source_id: str,
    index_type: str,
    dates: list[str],
) -> list[UsablePoint]:
    points: list[UsablePoint] = []
    for acquisition_date in dates:
        stats = _field_statistics(
            plot_id=plot_id,
            plot=plot,
            source_id=source_id,
            acquisition_date=acquisition_date,
            index_type=index_type,
            cloud_mask=CloudMaskOptions(),
        )
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


def _score(
    latest: UsablePoint,
    previous: UsablePoint | None,
    recency_days: int,
) -> tuple[float, LeaderboardScoreComponents]:
    vigor = max(0.0, min(1.0, (latest.mean + 1.0) / 2.0))
    trend = None
    if previous is not None:
        trend = max(0.0, min(1.0, ((latest.mean - previous.mean) + 0.25) / 0.5))
    recency = max(0.0, min(1.0, 1.0 - (recency_days / 30.0)))
    weighted: list[tuple[float, float]] = [(0.5, vigor), (0.2, recency)]
    if trend is not None:
        weighted.append((0.3, trend))
    total_weight = sum(weight for weight, _ in weighted)
    score = sum(weight * value for weight, value in weighted) / total_weight
    return round(score, 4), LeaderboardScoreComponents(
        vigor=round(vigor, 4),
        trend=round(trend, 4) if trend is not None else None,
        recency=round(recency, 4),
    )


async def _row_for_plot(
    *,
    plot: dict[str, Any],
    index_type: str,
    source_id: str,
    dates: list[str],
) -> FieldLeaderboardRow:
    coords = _coordinates(plot)
    base = {
        "plot_id": plot["id"],
        "name": plot.get("name") or plot["id"],
        "field": plot.get("name") or plot["id"],
        "group_name": plot.get("groupName"),
        "crop_type": plot.get("cropType"),
        "variety": plot.get("variety"),
        "season_label": plot.get("seasonLabel"),
        "location": _location(coords),
        "coordinates": coords,
        "area_ha": plot.get("areaHa"),
        "sowing_date": plot.get("sowingDate"),
        "planting_date": plot.get("plantingDate"),
        "actual_yield": None,
        "preview": f"/monitoring/field-analytics?field={plot['id']}",
        "open": f"/monitoring/field-analytics?field={plot['id']}",
    }
    try:
        points = await asyncio.wait_for(
            _run_blocking(
                _latest_usable_points,
                plot_id=plot["id"],
                plot=plot,
                source_id=source_id,
                index_type=index_type,
                dates=dates,
            ),
            timeout=settings.index_request_timeout_seconds,
        )
    except (AkashaError, TimeoutError) as exc:
        return FieldLeaderboardRow(
            **base,
            data_available=False,
            unavailable_reason=getattr(exc, "message", "Leaderboard statistics are unavailable."),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("leaderboard row unavailable: %s", type(exc).__name__)
        return FieldLeaderboardRow(
            **base,
            data_available=False,
            unavailable_reason="Leaderboard statistics are unavailable.",
        )
    if not points:
        return FieldLeaderboardRow(
            **base,
            data_available=False,
            unavailable_reason="No usable cloud-free index scene found in the requested range.",
        )
    latest = points[0]
    previous = points[1] if len(points) > 1 else None
    today = datetime.now(UTC).date()
    recency_days = max(0, (today - latest.acquisition_date).days)
    score, components = _score(latest, previous, recency_days)
    return FieldLeaderboardRow(
        **base,
        latest_index_value=round(latest.mean, 4),
        latest_image_date=latest.acquisition_date,
        index_delta=round(latest.mean - previous.mean, 4) if previous else None,
        previous_image_date=previous.acquisition_date if previous else None,
        cloud_free_recency_days=recency_days,
        score=score,
        score_components=components,
        data_available=True,
    )


def _sort_rows(
    rows: list[FieldLeaderboardRow],
    sort_by: str,
    sort_order: str,
) -> list[FieldLeaderboardRow]:
    reverse = sort_order != "asc"

    def value(row: FieldLeaderboardRow):
        item = getattr(row, _snake(sort_by), None)
        return (item is None, item)

    if sort_by == "rank":
        sort_by = "score"
    sorted_rows = sorted(
        rows,
        key=lambda row: (not row.data_available, value(row), row.name),
        reverse=reverse,
    )
    ranked = [
        row.model_copy(update={"rank": idx})
        for idx, row in enumerate([r for r in sorted_rows if r.data_available], 1)
    ]
    unavailable = [row for row in sorted_rows if not row.data_available]
    return ranked + unavailable


def _snake(value: str) -> str:
    out = []
    for char in value:
        if char.isupper():
            out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


async def _leaderboard(
    *,
    index_type: str,
    group_name: str | None,
    crop_type: str | None,
    variety: str | None,
    season_label: str | None,
    search: str | None,
    start_date: date,
    end_date: date,
    source_id: str,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
    evaluation_limit: int,
    scene_scan_limit: int,
) -> FieldLeaderboardResponse:
    plots = await _run_blocking(plots_repo.list_plots)
    filtered = _filter_plots(
        plots,
        group_name=group_name,
        crop_type=crop_type,
        variety=variety,
        season_label=season_label,
        search=search,
    )
    candidates = sorted(
        filtered,
        key=lambda item: (str(item.get("name") or ""), str(item.get("id") or "")),
    )
    evaluated = candidates[:evaluation_limit]
    dates = _scene_dates(source_id, start_date, end_date, scene_scan_limit)
    rows = [
        await _row_for_plot(plot=plot, index_type=index_type, source_id=source_id, dates=dates)
        for plot in evaluated
    ]
    ranked = _sort_rows(rows, sort_by, sort_order)
    page = ranked[offset : offset + limit]
    truncated = len(filtered) > evaluation_limit
    return FieldLeaderboardResponse(
        index_type=index_type,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        rows=page,
        metadata={
            "sourceId": source_id,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "limit": limit,
            "offset": offset,
            "totalFilteredFields": len(filtered),
            "evaluatedFieldCount": len(evaluated),
            "evaluationLimit": evaluation_limit,
            "truncated": truncated,
            "rankingScope": "first_N_filtered_fields" if truncated else "all_filtered_fields",
            "sceneScanLimit": scene_scan_limit,
            "usablePixelThreshold": settings.usable_pixel_threshold_percent,
            "partialUnavailableCount": sum(1 for row in ranked if not row.data_available),
            "weatherRiskAvailable": False,
            "weatherRiskSource": "pending",
            "scoreFormula": (
                "0.5*vigor + 0.3*trend + 0.2*recency; "
                "weights renormalize when trend is missing"
            ),
            "missingValuePolicy": "Rows without usable scenes are sorted last with rank null.",
        },
    )


def _csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        value = ",".join(str(item) for item in value)
    if isinstance(value, date):
        value = value.isoformat()
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _row_value(row: FieldLeaderboardRow, column: str) -> Any:
    mapping = {
        "field": row.field,
        "group": row.group_name,
        "crop": row.crop_type,
        "season": row.season_label,
        "open": row.open,
    }
    return mapping.get(column, getattr(row, _snake(column), None))


def _csv_content(response: FieldLeaderboardResponse, columns: list[str]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in response.rows:
        writer.writerow({column: _csv_safe(_row_value(row, column)) for column in columns})
    return output.getvalue()


def _validate_paging(limit: int, offset: int, evaluation_limit: int) -> None:
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise bad_request("limit is out of range.", code="INVALID_LIMIT", maxLimit=MAX_PAGE_LIMIT)
    if offset < 0:
        raise bad_request("offset must be non-negative.", code="INVALID_OFFSET")
    if evaluation_limit < 1 or evaluation_limit > MAX_EVALUATION_LIMIT:
        raise bad_request(
            "evaluationLimit is out of range.",
            code="INVALID_EVALUATION_LIMIT",
            maxLimit=MAX_EVALUATION_LIMIT,
        )


@router.get(
    "/reports/field-leaderboard",
    response_model=FieldLeaderboardResponse,
    response_model_by_alias=True,
)
async def get_field_leaderboard(
    indexType: str = Query(default=DEFAULT_INDEX),
    groupName: str | None = Query(default=None),
    cropType: str | None = Query(default=None),
    variety: str | None = Query(default=None),
    seasonLabel: str | None = Query(default=None),
    search: str | None = Query(default=None),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    lookbackDays: int = Query(default=DEFAULT_LOOKBACK_DAYS),
    sourceId: str = Query(default="sentinel-2-l2a"),
    sortBy: str = Query(default="score"),
    sortOrder: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=DEFAULT_PAGE_LIMIT),
    offset: int = Query(default=0),
    evaluationLimit: int = Query(default=DEFAULT_EVALUATION_LIMIT),
    sceneScanLimit: int = Query(default=DEFAULT_SCENE_SCAN_LIMIT),
) -> FieldLeaderboardResponse:
    if sortBy not in SORT_KEYS:
        raise bad_request(
            "Unsupported leaderboard sort.",
            code="INVALID_SORT",
            supported=sorted(SORT_KEYS),
        )
    _validate_paging(limit, offset, evaluationLimit)
    start, end = _date_range(startDate, endDate, lookbackDays)
    return await _leaderboard(
        index_type=_normalize_index(indexType),
        group_name=groupName,
        crop_type=cropType,
        variety=variety,
        season_label=seasonLabel,
        search=search,
        start_date=start,
        end_date=end,
        source_id=sourceId,
        sort_by=sortBy,
        sort_order=sortOrder,
        limit=limit,
        offset=offset,
        evaluation_limit=evaluationLimit,
        scene_scan_limit=sceneScanLimit,
    )


async def _columns_from_request(columns: list[str] | None, template_id: str | None) -> list[str]:
    if template_id:
        template = await _run_blocking(reports_repo.get_report_template, template_id)
        if template is None:
            raise not_found(
                "Report template not found.",
                code="REPORT_TEMPLATE_NOT_FOUND",
                templateId=template_id,
            )
        return _validate_columns(list(template["columns"]))
    return _validate_columns(columns or list(DEFAULT_COLUMNS))


@router.get("/reports/field-leaderboard/export.csv")
async def export_field_leaderboard_csv(
    indexType: str = Query(default=DEFAULT_INDEX),
    groupName: str | None = Query(default=None),
    cropType: str | None = Query(default=None),
    variety: str | None = Query(default=None),
    seasonLabel: str | None = Query(default=None),
    search: str | None = Query(default=None),
    startDate: date | None = Query(default=None),
    endDate: date | None = Query(default=None),
    lookbackDays: int = Query(default=DEFAULT_LOOKBACK_DAYS),
    sourceId: str = Query(default="sentinel-2-l2a"),
    sortBy: str = Query(default="score"),
    sortOrder: Literal["asc", "desc"] = "desc",
    columns: list[str] | None = Query(default=None),
    templateId: str | None = Query(default=None),
    evaluationLimit: int = Query(default=DEFAULT_EVALUATION_LIMIT),
    sceneScanLimit: int = Query(default=DEFAULT_SCENE_SCAN_LIMIT),
) -> Response:
    if sortBy not in SORT_KEYS:
        raise bad_request(
            "Unsupported leaderboard sort.",
            code="INVALID_SORT",
            supported=sorted(SORT_KEYS),
        )
    _validate_paging(MAX_PAGE_LIMIT, 0, evaluationLimit)
    selected_columns = await _columns_from_request(columns, templateId)
    start, end = _date_range(startDate, endDate, lookbackDays)
    response = await _leaderboard(
        index_type=_normalize_index(indexType),
        group_name=groupName,
        crop_type=cropType,
        variety=variety,
        season_label=seasonLabel,
        search=search,
        start_date=start,
        end_date=end,
        source_id=sourceId,
        sort_by=sortBy,
        sort_order=sortOrder,
        limit=MAX_PAGE_LIMIT,
        offset=0,
        evaluation_limit=evaluationLimit,
        scene_scan_limit=sceneScanLimit,
    )
    filename = f"field-leaderboard_{_safe_filename(response.index_type)}.csv"
    return Response(
        content=_csv_content(response, selected_columns),
        media_type="text/csv",
        headers=_disposition(filename),
    )


@router.get(
    "/reports/templates",
    response_model=list[ReportTemplate],
    response_model_by_alias=True,
)
async def list_report_templates() -> list[ReportTemplate]:
    rows = await _run_blocking(reports_repo.list_report_templates)
    return [_template_from_row(row) for row in rows]


@router.get(
    "/reports/templates/{template_id}",
    response_model=ReportTemplate,
    response_model_by_alias=True,
)
async def get_report_template(template_id: str) -> ReportTemplate:
    row = await _run_blocking(reports_repo.get_report_template, template_id)
    if row is None:
        raise not_found(
            "Report template not found.",
            code="REPORT_TEMPLATE_NOT_FOUND",
            templateId=template_id,
        )
    return _template_from_row(row)


@router.post(
    "/reports/templates",
    response_model=ReportTemplate,
    response_model_by_alias=True,
    status_code=201,
)
async def create_report_template(payload: ReportTemplatePayload) -> ReportTemplate:
    if not payload.name.strip():
        raise bad_request("Report template name is required.", code="REPORT_TEMPLATE_NAME_REQUIRED")
    _validate_columns(payload.columns)
    _validate_filters(payload.filters)
    _validate_sort(payload.sort)
    row = await _run_blocking(
        reports_repo.create_report_template,
        name=payload.name.strip(),
        columns=payload.columns,
        filters=payload.filters,
        sort=payload.sort,
    )
    return _template_from_row(row)


@router.patch(
    "/reports/templates/{template_id}",
    response_model=ReportTemplate,
    response_model_by_alias=True,
)
async def update_report_template(template_id: str, payload: ReportTemplateUpdate) -> ReportTemplate:
    if payload.name is not None and not payload.name.strip():
        raise bad_request("Report template name is required.", code="REPORT_TEMPLATE_NAME_REQUIRED")
    if payload.columns is not None:
        _validate_columns(payload.columns)
    if payload.filters is not None:
        _validate_filters(payload.filters)
    if payload.sort is not None:
        _validate_sort(payload.sort)
    row = await _run_blocking(
        reports_repo.update_report_template,
        template_id,
        name=payload.name.strip() if payload.name is not None else None,
        columns=payload.columns,
        filters=payload.filters,
        sort=payload.sort,
    )
    if row is None:
        raise not_found(
            "Report template not found.",
            code="REPORT_TEMPLATE_NOT_FOUND",
            templateId=template_id,
        )
    return _template_from_row(row)
