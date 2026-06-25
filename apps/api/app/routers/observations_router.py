"""Best-observation resolver endpoints (Phase 11 / TASK-066–069).

Provides backend-owned best-observation selection across validated active sources:

  GET  /api/observations/best     — ranked timeline/date-range candidates
  POST /api/observations/resolve  — geometry-aware single best selection

Source-specific timelines (``/api/sources/{sourceId}/dates``) remain unchanged
and continue to serve per-source views. These endpoints layer on top of them with
cross-source ranking that the frontend does not need to duplicate.

Ranking considers: source priority, date proximity, usable-pixel percent, coverage,
field intersection (bbox proxy only; no raster reads), analysis level, resolution,
and source state. AWiFS (56 m regional) is excluded from field-level results unless
``allowCoarse=true`` and the source has ``availabilityStatus == "active"``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from ..auth import get_current_team
from ..raster.catalog_resolver import ObservationCandidate, resolve_best_observation
from ..raster.errors import bad_request
from ..raster.models import Geometry

router = APIRouter(
    prefix="/api/observations",
    tags=["observations"],
    dependencies=[Depends(get_current_team)],
)


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ObservationResolveRequest(BaseModel):
    """POST /api/observations/resolve request body.

    Uses camelCase field names directly (matching the JSON wire format) to avoid
    Pydantic v2 alias_generator warnings with constrained int/bool fields.
    """

    geometry: Geometry
    targetDate: str | None = Field(
        default=None, description="YYYY-MM-DD centre date for proximity scoring."
    )
    startDate: str | None = Field(default=None, description="YYYY-MM-DD window start.")
    endDate: str | None = Field(default=None, description="YYYY-MM-DD window end.")
    lookbackDays: int | None = Field(default=None, ge=1, le=366)
    indexType: str | None = Field(
        default=None, description="Index to filter by (e.g. NDVI, NDMI)."
    )
    useCase: str = Field(default="field", description='"field" or "regional".')
    allowCoarse: bool = Field(
        default=False,
        description="Allow coarse/regional sources (e.g. AWiFS 56 m) in results.",
    )
    windowDays: int = Field(default=30, ge=1, le=366)
    maxCandidates: int = Field(default=10, ge=1, le=50)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _candidate_to_dict(c: ObservationCandidate) -> dict[str, Any]:
    return {
        "sourceId": c.source_id,
        "acquisitionDate": c.acquisition_date,
        "resolutionMeters": c.resolution_meters,
        "analysisLevel": c.analysis_level,
        "usablePixelPercent": c.usable_pixel_percent,
        "coveragePercent": c.coverage_percent,
        "cloudMaskedPercent": c.cloud_masked_percent,
        "tileAvailable": c.tile_available,
        "isLatestUsable": c.is_latest_usable,
        "score": c.score,
        "sourcePriority": c.source_priority,
        "provenanceNote": c.provenance_note,
        "isCoarse": c.is_coarse,
        "supportedIndices": c.supported_indices,
        "label": c.label,
    }


def _validate_date_param(value: str | None, param_name: str) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise bad_request(
            f"Invalid {param_name}: expected YYYY-MM-DD format.",
            code="INVALID_DATE_PARAM",
            param=param_name,
            value=value,
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/observations/best
# ---------------------------------------------------------------------------


@router.get("/best")
async def get_best_observations(
    targetDate: str | None = Query(default=None, description="YYYY-MM-DD centre date."),
    startDate: str | None = Query(default=None, description="YYYY-MM-DD window start."),
    endDate: str | None = Query(default=None, description="YYYY-MM-DD window end."),
    lookbackDays: int | None = Query(default=None, ge=1, le=366),
    indexType: str | None = Query(
        default=None, description="Filter by index (e.g. NDVI, NDMI, MSAVI)."
    ),
    useCase: Literal["field", "regional"] = Query(
        default="field",
        description=(
            '"field" excludes coarse/regional sources unless allowCoarse=true; '
            '"regional" allows them.'
        ),
    ),
    allowCoarse: bool = Query(
        default=False,
        description=(
            "Allow coarse/regional sources (e.g. AWiFS 56 m). "
            "Still requires availabilityStatus=active."
        ),
    ),
    windowDays: int = Query(
        default=30,
        ge=1,
        le=366,
        description="Symmetric window (days) around targetDate when no start/end given.",
    ),
    maxCandidates: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Return ranked best-observation candidates across active sources.

    Use for timeline/date-range views where the frontend needs the best available
    observation per date window across all active sources.

    **Source-specific timelines are preserved** — ``/api/sources/{sourceId}/dates``
    and all existing tile/statistics routes remain unchanged.

    Ranking factors (descending weight): source priority (40%), date proximity (35%),
    usable-pixel percent (15%), coverage (10%).  AWiFS (56 m regional) is excluded
    from ``useCase=field`` results unless ``allowCoarse=true`` and the source has
    been validated (``availabilityStatus=active``).
    """
    _validate_date_param(targetDate, "targetDate")
    _validate_date_param(startDate, "startDate")
    _validate_date_param(endDate, "endDate")

    candidates = resolve_best_observation(
        target_date=targetDate,
        start_date=startDate,
        end_date=endDate,
        lookback_days=lookbackDays,
        index_type=indexType,
        use_case=useCase,
        allow_coarse=allowCoarse,
        window_days=windowDays,
        max_candidates=maxCandidates,
    )

    return {
        "candidates": [_candidate_to_dict(c) for c in candidates],
        "query": {
            "targetDate": targetDate,
            "startDate": startDate,
            "endDate": endDate,
            "lookbackDays": lookbackDays,
            "indexType": indexType,
            "useCase": useCase,
            "allowCoarse": allowCoarse,
            "windowDays": windowDays,
            "maxCandidates": maxCandidates,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/observations/resolve
# ---------------------------------------------------------------------------


@router.post("/resolve")
async def resolve_observation(
    payload: ObservationResolveRequest = Body(...),
) -> dict[str, Any]:
    """Return the single best observation for a field geometry + date context.

    The geometry is used as a **metadata-only bounding-box intersection proxy**;
    no raster reads are performed here.  Full per-pixel coverage validation happens
    at the statistics/overlay computation step.

    Returns ``best: null`` when no active candidate qualifies within the window.
    """
    geometry = payload.geometry.model_dump()

    _validate_date_param(payload.targetDate, "targetDate")
    _validate_date_param(payload.startDate, "startDate")
    _validate_date_param(payload.endDate, "endDate")

    use_case = payload.useCase if payload.useCase in ("field", "regional") else "field"

    candidates = resolve_best_observation(
        target_date=payload.targetDate,
        start_date=payload.startDate,
        end_date=payload.endDate,
        lookback_days=payload.lookbackDays,
        index_type=payload.indexType,
        use_case=use_case,
        allow_coarse=payload.allowCoarse,
        field_geometry=geometry,
        window_days=payload.windowDays,
        max_candidates=payload.maxCandidates,
    )

    best = candidates[0] if candidates else None
    return {
        "best": _candidate_to_dict(best) if best else None,
        "candidates": [_candidate_to_dict(c) for c in candidates],
        "query": {
            "targetDate": payload.targetDate,
            "startDate": payload.startDate,
            "endDate": payload.endDate,
            "lookbackDays": payload.lookbackDays,
            "indexType": payload.indexType,
            "useCase": use_case,
            "allowCoarse": payload.allowCoarse,
            "windowDays": payload.windowDays,
            "maxCandidates": payload.maxCandidates,
        },
    }
