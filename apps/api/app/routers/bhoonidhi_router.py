"""Temporary Bhoonidhi ResourceSat BOA diagnostic endpoints.

This module is intentionally narrow: it lets operators on the whitelisted
staging VM trigger one server-side Bhoonidhi product download and inspect the
archive/raster layout needed to finalize ResourceSat ingestion assumptions.

It is not the production ingestion pipeline. Jobs are in-memory and disabled by
default behind BHOONIDHI_DIAGNOSTICS_ENABLED.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import tarfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_role
from ..config import settings
from ..raster.errors import AkashaError, sanitize_error_value
from ..schemas.bhoonidhi import BhoonidhiDiagnosticRequest

_BAND_ROLE_TOKENS: dict[str, tuple[str, ...]] = {
    "GREEN": ("BAND2", "BAND_2", "B02", "B2"),
    "RED": ("BAND3", "BAND_3", "B03", "B3"),
    "NIR": ("BAND4", "BAND_4", "B04", "B4"),
    "SWIR1": ("BAND5", "BAND_5", "B05", "B5"),
}
_QUALITY_TOKENS = (
    "QUALITY",
    "QA",
    "QC",
    "CLOUD",
    "SHADOW",
    "MASK",
    "CLD",
    "PIXEL",
)
_RASTER_EXTENSIONS = {".tif", ".tiff"}
_METADATA_EXTENSIONS = {".xml", ".json", ".txt", ".met", ".hdr"}
_MAX_ARCHIVE_SAMPLES = 50
_MAX_RASTER_METADATA_READS = 20


@dataclass
class DiagnosticJob:
    job_id: str
    request: BhoonidhiDiagnosticRequest
    status: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


_JOBS: dict[str, DiagnosticJob] = {}
_JOBS_LOCK = threading.Lock()

router = APIRouter(
    prefix="/api/admin/bhoonidhi/diagnostics",
    tags=["bhoonidhi-diagnostics"],
    dependencies=[Depends(require_role("owner", "admin"))],
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _diagnostics_disabled() -> AkashaError:
    return AkashaError(
        "BHOONIDHI_DIAGNOSTICS_DISABLED",
        "Bhoonidhi diagnostics are disabled for this deployment.",
        503,
    )


def _not_configured(missing: list[str]) -> AkashaError:
    return AkashaError(
        "BHOONIDHI_NOT_CONFIGURED",
        "Bhoonidhi diagnostics require server-side credentials and configuration.",
        503,
        {"missingEnv": missing},
    )


def _job_not_found(job_id: str) -> AkashaError:
    return AkashaError(
        "BHOONIDHI_DIAGNOSTIC_JOB_NOT_FOUND",
        "Bhoonidhi diagnostic job was not found.",
        404,
        {"jobId": job_id},
    )


def _ensure_enabled_and_configured() -> None:
    if not settings.bhoonidhi_diagnostics_enabled:
        raise _diagnostics_disabled()
    missing = []
    if not settings.bhoonidhi_user_id.strip():
        missing.append("BHOONIDHI_USER_ID")
    if not settings.bhoonidhi_password.strip():
        missing.append("BHOONIDHI_PASSWORD")
    if not settings.bhoonidhi_api_base.strip():
        missing.append("BHOONIDHI_API_BASE")
    if missing:
        raise _not_configured(missing)


def clear_jobs_for_tests() -> None:
    with _JOBS_LOCK:
        _JOBS.clear()


def create_job(request: BhoonidhiDiagnosticRequest) -> DiagnosticJob:
    now = _now_iso()
    job = DiagnosticJob(
        job_id=uuid.uuid4().hex,
        request=request,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job
    return job


def _replace_job(job: DiagnosticJob) -> None:
    job.updated_at = _now_iso()
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job


def _get_job(job_id: str) -> DiagnosticJob:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise _job_not_found(job_id)
    return job


def _public_job(job: DiagnosticJob) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jobId": job.job_id,
        "status": job.status,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "request": job.request.model_dump(by_alias=True),
    }
    if job.result is not None:
        payload["result"] = sanitize_error_value(job.result)
    if job.error is not None:
        payload["error"] = sanitize_error_value(job.error)
    return payload


def get_public_job(job_id: str) -> dict[str, Any]:
    return _public_job(_get_job(job_id))


@router.post("/resourcesat-boa", status_code=202)
async def start_resourcesat_boa_diagnostic(
    payload: BhoonidhiDiagnosticRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    _ensure_enabled_and_configured()
    job = create_job(payload)
    background_tasks.add_task(_run_diagnostic_job, job.job_id, payload)
    return {
        "jobId": job.job_id,
        "status": job.status,
        "statusUrl": f"/api/admin/bhoonidhi/diagnostics/{job.job_id}",
    }


@router.get("/{job_id}")
async def get_diagnostic_job(job_id: str) -> dict[str, Any]:
    _ensure_enabled_and_configured()
    return get_public_job(job_id)


def _run_diagnostic_job(job_id: str, request: BhoonidhiDiagnosticRequest) -> None:
    job = _get_job(job_id)
    job.status = "running"
    job.error = None
    _replace_job(job)
    try:
        downloaded_path = _download_bhoonidhi_product(request)
        report = inspect_downloaded_product(downloaded_path)
        report["request"] = request.model_dump(by_alias=True)
        job.status = "succeeded"
        job.result = report
        job.error = None
    except AkashaError as exc:
        job.status = "failed"
        job.error = exc.to_payload()["error"]
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = {
            "code": "BHOONIDHI_DIAGNOSTIC_FAILED",
            "message": "Bhoonidhi diagnostic job failed.",
            "details": {"errorType": type(exc).__name__},
        }
    _replace_job(job)


def _api_base() -> str:
    return settings.bhoonidhi_api_base.strip().rstrip("/")


def _json_request(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AkashaError(
            "BHOONIDHI_AUTH_FAILED",
            "Bhoonidhi authentication request failed.",
            502,
            {"statusCode": exc.code},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise AkashaError(
            "BHOONIDHI_AUTH_FAILED",
            "Bhoonidhi authentication request failed.",
            502,
            {"errorType": type(exc).__name__},
        ) from exc


def _access_token() -> str:
    auth = _json_request(
        f"{_api_base()}/auth/token",
        {
            "userId": settings.bhoonidhi_user_id,
            "password": settings.bhoonidhi_password,
            "grant_type": "password",
        },
        timeout=float(settings.bhoonidhi_download_timeout_seconds),
    )
    token = str(auth.get("access_token") or "")
    if not token:
        raise AkashaError(
            "BHOONIDHI_AUTH_FAILED",
            "Bhoonidhi authentication response did not include an access token.",
            502,
        )
    return token


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "bhoonidhi_product"


def _filename_from_headers(headers: Any, item_id: str) -> str:
    disposition = headers.get("Content-Disposition", "") if headers else ""
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition, flags=re.I)
    if match:
        return _safe_filename(urllib.parse.unquote(match.group(1)))
    content_type = headers.get("Content-Type", "") if headers else ""
    extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ".zip"
    return _safe_filename(item_id) + extension


def _download_bhoonidhi_product(request: BhoonidhiDiagnosticRequest) -> Path:
    token = _access_token()
    root = Path(settings.bhoonidhi_download_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({"id": request.item_id, "collection": request.collection_id})
    url = f"{_api_base()}/download?{query}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/octet-stream"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            req,
            timeout=float(settings.bhoonidhi_download_timeout_seconds),
        ) as resp:
            file_name = _filename_from_headers(resp.headers, request.item_id)
            target = root / file_name
            part = target.with_suffix(target.suffix + ".part")
            total = 0
            digest = hashlib.sha256()
            with part.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.bhoonidhi_max_download_bytes:
                        raise AkashaError(
                            "BHOONIDHI_DOWNLOAD_TOO_LARGE",
                            "Bhoonidhi diagnostic download exceeded BHOONIDHI_MAX_DOWNLOAD_BYTES.",
                            413,
                            {"maxDownloadBytes": settings.bhoonidhi_max_download_bytes},
                        )
                    digest.update(chunk)
                    out.write(chunk)
            part.replace(target)
            (target.with_suffix(target.suffix + ".sha256")).write_text(
                digest.hexdigest(), encoding="utf-8"
            )
            return target
    except AkashaError:
        raise
    except urllib.error.HTTPError as exc:
        raise AkashaError(
            "BHOONIDHI_DOWNLOAD_FAILED",
            "Bhoonidhi product download failed.",
            502,
            {"statusCode": exc.code},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise AkashaError(
            "BHOONIDHI_DOWNLOAD_FAILED",
            "Bhoonidhi product download failed.",
            502,
            {"errorType": type(exc).__name__},
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extension(name: str) -> str:
    return Path(name).suffix.lower() or "<none>"


def _entry_is_raster(name: str) -> bool:
    return _extension(name) in _RASTER_EXTENSIONS


def _entry_is_metadata(name: str) -> bool:
    return _extension(name) in _METADATA_EXTENSIONS


def _normalized_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", Path(name).name.upper())


def _matches_any_token(name: str, tokens: tuple[str, ...]) -> bool:
    normalized = _normalized_name(name)
    return any(token in normalized for token in tokens)


def _archive_entries(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = [
                {"name": info.filename, "size": info.file_size}
                for info in archive.infolist()
                if not info.is_dir()
            ]
        return "zip", entries
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            entries = [
                {"name": member.name, "size": int(member.size)}
                for member in archive.getmembers()
                if member.isfile()
            ]
        return "tar", entries
    return "file", [{"name": path.name, "size": path.stat().st_size}]


def _archive_summary(kind: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_extension: dict[str, int] = {}
    for entry in entries:
        ext = _extension(str(entry["name"]))
        by_extension[ext] = by_extension.get(ext, 0) + 1
    return {
        "kind": kind,
        "entryCount": len(entries),
        "sampleEntries": [entry["name"] for entry in entries[:_MAX_ARCHIVE_SAMPLES]],
        "entriesByExtension": dict(sorted(by_extension.items())),
    }


def _band_candidates(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for role, tokens in _BAND_ROLE_TOKENS.items():
        matches = [
            str(entry["name"])
            for entry in entries
            if _entry_is_raster(str(entry["name"]))
            and _matches_any_token(str(entry["name"]), tokens)
        ]
        candidates.append({"role": role, "tokens": list(tokens), "entries": matches})
    return candidates


def _quality_candidates(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    matches = []
    for entry in entries:
        name = str(entry["name"])
        if _matches_any_token(name, _QUALITY_TOKENS):
            matches.append({"entry": name, "reason": "filename contains quality/cloud/mask token"})
    return matches


def _metadata_candidates(entries: list[dict[str, Any]]) -> list[str]:
    return [str(entry["name"]) for entry in entries if _entry_is_metadata(str(entry["name"]))]


def _raster_vsi_path(path: Path, archive_kind: str, entry_name: str) -> str:
    posix = path.resolve().as_posix()
    if archive_kind == "zip":
        return f"/vsizip/{posix}/{entry_name}"
    if archive_kind == "tar":
        return f"/vsitar/{posix}/{entry_name}"
    return posix


def _read_raster_metadata(path: Path, archive_kind: str, entry_name: str) -> dict[str, Any]:
    try:
        import rasterio  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {"entry": entry_name, "readable": False, "error": "rasterio unavailable"}
    try:
        with rasterio.open(_raster_vsi_path(path, archive_kind, entry_name)) as dataset:
            return {
                "entry": entry_name,
                "readable": True,
                "driver": dataset.driver,
                "width": dataset.width,
                "height": dataset.height,
                "count": dataset.count,
                "crs": str(dataset.crs) if dataset.crs else None,
                "transform": [round(value, 12) for value in dataset.transform[:6]],
                "dtypes": list(dataset.dtypes),
                "nodata": dataset.nodata,
                "descriptions": list(dataset.descriptions),
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "entry": entry_name,
            "readable": False,
            "error": "raster metadata could not be read",
            "errorType": type(exc).__name__,
        }


def _raster_metadata(
    path: Path, archive_kind: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    raster_entries = [
        str(entry["name"]) for entry in entries if _entry_is_raster(str(entry["name"]))
    ]
    return [
        _read_raster_metadata(path, archive_kind, entry_name)
        for entry_name in raster_entries[:_MAX_RASTER_METADATA_READS]
    ]


def _missing_roles(band_candidates: list[dict[str, Any]]) -> list[str]:
    return [candidate["role"] for candidate in band_candidates if not candidate["entries"]]


def _recommendations(
    *,
    missing_roles: list[str],
    quality_candidates: list[dict[str, str]],
    raster_metadata: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    if missing_roles:
        recommendations.append(
            "Confirm ResourceSat BOA band filename conventions for missing roles: "
            + ", ".join(missing_roles)
            + "."
        )
    else:
        recommendations.append(
            "All expected ResourceSat LISS-3 roles were found by filename; verify spectral role "
            "mapping against product metadata."
        )
    if quality_candidates:
        recommendations.append(
            "Review quality/cloud/mask candidate files and document class semantics before "
            "finalizing source-neutral mask encoding."
        )
    else:
        recommendations.append(
            "No obvious quality/cloud/mask file was found; prepare an Akasha threshold-mask "
            "fallback and verify with NRSC product documentation."
        )
    readable = [item for item in raster_metadata if item.get("readable")]
    if readable:
        recommendations.append(
            "Use readable raster metadata to confirm CRS, pixel size, band count, nodata, and "
            "scale/offset before freezing the composite grid."
        )
    else:
        recommendations.append(
            "Raster metadata was not readable from sampled entries; inspect the downloaded "
            "product on staging with GDAL/rasterio tooling."
        )
    return recommendations


def inspect_downloaded_product(path: Path) -> dict[str, Any]:
    kind, entries = _archive_entries(path)
    band_candidates = _band_candidates(entries)
    quality_candidates = _quality_candidates(entries)
    raster_metadata = _raster_metadata(path, kind, entries)
    missing_roles = _missing_roles(band_candidates)
    return {
        "download": {
            "fileName": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
        "archive": _archive_summary(kind, entries),
        "bandCandidates": band_candidates,
        "qualityCandidates": quality_candidates,
        "metadataCandidates": _metadata_candidates(entries),
        "rasterMetadata": raster_metadata,
        "missing": {
            "roles": missing_roles,
            "qualityLayer": not bool(quality_candidates),
        },
        "recommendations": _recommendations(
            missing_roles=missing_roles,
            quality_candidates=quality_candidates,
            raster_metadata=raster_metadata,
        ),
    }
