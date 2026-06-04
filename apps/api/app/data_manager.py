"""Data manager metadata/upload routes for Phase 10."""
from __future__ import annotations

import functools
import json
import logging
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import Field

from . import phase10_repo
from .auth import get_current_team
from .providers.models import ProviderModel
from .raster.errors import AkashaError, bad_request, plots_backend_unavailable

logger = logging.getLogger("akasha.api.data_manager")
router = APIRouter(
    prefix="/api",
    tags=["data-manager"],
    dependencies=[Depends(get_current_team)],
)

MAX_UPLOAD_BYTES = 1_048_576


class DatasetPayload(ProviderModel):
    name: str
    dataset_type: Literal["geojson", "shp_zip", "iso_xml"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedDataset(ProviderModel):
    id: str
    name: str
    dataset_type: str
    upload_status: str
    original_filename: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    feature_count: int | None = None
    validation_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ConnectionStatus(ProviderModel):
    provider: str
    status: Literal["not_connected"]
    message: str


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("data manager backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable("Data manager storage is not available.") from exc


def _dataset_type(filename: str, requested: str | None) -> str:
    if requested in {"geojson", "shp_zip", "iso_xml"}:
        return requested
    lower = filename.lower()
    if lower.endswith(".geojson") or lower.endswith(".json"):
        return "geojson"
    if lower.endswith(".zip") and "iso" in lower:
        return "iso_xml"
    if lower.endswith(".zip"):
        return "shp_zip"
    raise bad_request("Unsupported dataset file type.", code="UNSUPPORTED_DATASET_TYPE")


async def _read_limited(file: UploadFile) -> bytes:
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise AkashaError(
                "DATASET_UPLOAD_TOO_LARGE",
                "Dataset upload exceeds the Phase 10 demo limit.",
                413,
                {"maxUploadBytes": MAX_UPLOAD_BYTES},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _feature_count(payload: bytes, dataset_type: str) -> int | None:
    if dataset_type != "geojson":
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if data.get("type") == "FeatureCollection" and isinstance(data.get("features"), list):
        return len(data["features"])
    if data.get("type") == "Feature":
        return 1
    return None


@router.get("/datasets", response_model=list[UploadedDataset], response_model_by_alias=True)
async def list_datasets() -> list[UploadedDataset]:
    rows = await _run_blocking(phase10_repo.list_datasets)
    return [UploadedDataset(**row) for row in rows]


@router.post(
    "/datasets",
    response_model=UploadedDataset,
    response_model_by_alias=True,
    status_code=201,
)
async def create_dataset_metadata(payload: DatasetPayload) -> UploadedDataset:
    row = await _run_blocking(
        phase10_repo.create_dataset,
        {
            "name": payload.name,
            "datasetType": payload.dataset_type,
            "metadata": payload.metadata,
        },
    )
    return UploadedDataset(**row)


@router.post(
    "/datasets/upload",
    response_model=UploadedDataset,
    response_model_by_alias=True,
    status_code=201,
)
async def upload_dataset(
    file: UploadFile = File(...),
    datasetType: str | None = Form(default=None),
) -> UploadedDataset:
    dataset_type = _dataset_type(file.filename or "dataset", datasetType)
    payload = await _read_limited(file)
    row = await _run_blocking(
        phase10_repo.create_dataset,
        {
            "name": file.filename or "dataset",
            "datasetType": dataset_type,
            "originalFilename": file.filename,
            "contentType": file.content_type,
            "fileSizeBytes": len(payload),
            "featureCount": _feature_count(payload, dataset_type),
            "uploadStatus": "parsed" if dataset_type == "geojson" else "uploaded",
            "validationMessage": (
                "ISO-XML parsing is deferred; metadata only."
                if dataset_type == "iso_xml"
                else None
            ),
        },
    )
    return UploadedDataset(**row)


@router.get(
    "/connections/john-deere",
    response_model=ConnectionStatus,
    response_model_by_alias=True,
)
async def john_deere_connection_status() -> ConnectionStatus:
    return ConnectionStatus(
        provider="john-deere",
        status="not_connected",
        message="John Deere OAuth is deferred until a customer integration is confirmed.",
    )
