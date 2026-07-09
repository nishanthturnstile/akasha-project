"""Predefined season reference data endpoints (GET only)."""

from __future__ import annotations

from fastapi import APIRouter

from ..repositories import predefined_seasons_repo
from ..schemas.predefined_seasons import PredefinedSeasonResponse

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/predefined-seasons", response_model=list[PredefinedSeasonResponse])
def get_predefined_seasons():
    return predefined_seasons_repo.list_predefined_seasons()
