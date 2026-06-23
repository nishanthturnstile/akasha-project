"""Reference data endpoints (GET only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..repositories import crops_repo
from ..schemas.crops import (
    CropResponse,
    IrrigationTypeResponse,
    PaginatedVarietiesResponse,
    SeedingTypeResponse,
    TillageTypeResponse,
    VarietyResponse,
)

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/irrigation-types", response_model=list[IrrigationTypeResponse])
def get_irrigation_types():
    return crops_repo.list_irrigation_types()


@router.get("/tillage-types", response_model=list[TillageTypeResponse])
def get_tillage_types():
    return crops_repo.list_tillage_types()


@router.get("/seeding-types", response_model=list[SeedingTypeResponse])
def get_seeding_types():
    return crops_repo.list_seeding_types()


@router.get("/crops", response_model=list[CropResponse])
def get_crops():
    return crops_repo.list_crops()


@router.get("/crops/{crop_id}", response_model=CropResponse)
def get_crop(crop_id: int):
    crop = crops_repo.get_crop(crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    return crop


@router.get("/crops/{crop_id}/varieties", response_model=PaginatedVarietiesResponse)
def get_varieties(
    crop_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    skip = (page - 1) * page_size
    items, total = crops_repo.list_varieties(crop_id, skip=skip, limit=page_size)
    return PaginatedVarietiesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )
