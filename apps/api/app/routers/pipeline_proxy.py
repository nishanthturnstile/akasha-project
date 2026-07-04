"""App-domain pipeline stats/tile proxy routes (Phase 5).

The browser only ever sees opaque ``proxyId`` app-domain URLs. Ingestion signed
URL material (host, ``sig``/``kid``/``exp``, ``queryId``/``layerId``, MinIO/S3/
pgSTAC/TiTiler references) is stored server-side in ``akasha.pipeline_proxy_records``
and resolved here. Records are persisted in Postgres so any BFF worker can serve a
proxy request. Records are auth/team/field bound and expire; expired records are
rejected with ``PIPELINE_PROXY_EXPIRED``.
"""

from __future__ import annotations

import functools
import json
import logging
from datetime import UTC, datetime
from typing import Any

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..auth import CurrentTeam, CurrentUser, get_current_team, get_current_user
from ..ingestion_client import IngestionClient, IngestionClientError
from ..raster.errors import AkashaError, not_found, plots_backend_unavailable
from ..repositories import fields_repo
from ..repositories import pipeline_proxy_repo as proxy_repo

logger = logging.getLogger("akasha.api.pipeline_proxy")

router = APIRouter(
    prefix="/api/pipeline",
    tags=["pipeline-proxy"],
    dependencies=[Depends(get_current_team)],
)

# App-domain URL templates handed to the browser. Only the opaque proxy id is
# ever embedded; XYZ coordinates stay as MapLibre template placeholders.
STATS_PROXY_URL_TEMPLATE = "/api/pipeline/field-index/stats?proxyId={proxy_id}"
TILE_PROXY_URL_TEMPLATE = "/api/pipeline/tiles/{{z}}/{{x}}/{{y}}.png?proxyId={proxy_id}"

_DEFAULT_CONTENT_TYPE = {"stats": "application/json", "tile": "image/png"}


def _proxy_forbidden(message: str = "Proxy record is not accessible.") -> AkashaError:
    return AkashaError("PIPELINE_PROXY_FORBIDDEN", message, 403)


def _proxy_not_found() -> AkashaError:
    return not_found("Pipeline proxy record not found.", code="PIPELINE_PROXY_NOT_FOUND")


def _proxy_expired() -> AkashaError:
    return AkashaError("PIPELINE_PROXY_EXPIRED", "Pipeline proxy record has expired.", 410)


async def _run_blocking(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except AkashaError:
        raise
    except IngestionClientError as exc:
        raise AkashaError(exc.code, exc.message, exc.status_code, exc.details) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline proxy backend unavailable: %s", type(exc).__name__)
        raise plots_backend_unavailable(
            "Pipeline proxy storage is not available in this environment."
        ) from exc


async def _resolve_record(
    *,
    proxy_id: str,
    operation: str,
    user: CurrentUser,
    team: CurrentTeam,
) -> dict[str, Any]:
    record = await _run_blocking(proxy_repo.get_proxy_record, proxy_id)
    if record is None or record.get("operation") != operation:
        raise _proxy_not_found()

    expires_at = record.get("expiresAt")
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise _proxy_expired()

    if record.get("userId") != str(user.id) or record.get("teamId") != str(
        team.id if team else user.current_team_id
    ):
        raise _proxy_forbidden()

    # Re-check field access where practical: fail closed if the field is no
    # longer visible to this user.
    field = await _run_blocking(fields_repo.get_field, record["fieldId"], user.id)
    if field is None:
        raise _proxy_forbidden("Field is not accessible for this proxy record.")

    await _run_blocking(proxy_repo.touch_last_accessed, proxy_id)
    return record


def _content_type(operation: str, upstream_content_type: str) -> str:
    normalized = (upstream_content_type or "").split(";")[0].strip().lower()
    if operation == "tile":
        if normalized.startswith("image/"):
            return upstream_content_type
        return _DEFAULT_CONTENT_TYPE["tile"]
    return _DEFAULT_CONTENT_TYPE["stats"]


def _strip_browser_forbidden_stats_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_browser_forbidden_stats_fields(item)
            for key, item in value.items()
            if key not in {"queryId", "layerId", "statsUrl", "tileUrl"}
        }
    if isinstance(value, list):
        return [_strip_browser_forbidden_stats_fields(item) for item in value]
    return value


def _sanitize_stats_content(content: bytes, upstream_content_type: str) -> bytes:
    normalized = (upstream_content_type or "").split(";")[0].strip().lower()
    if normalized not in {"application/json", "application/geo+json"}:
        return json.dumps(
            {
                "error": {
                    "code": "PIPELINE_PROXY_INVALID_CONTENT",
                    "message": "Pipeline stats response was not JSON.",
                }
            },
            separators=(",", ":"),
        ).encode("utf-8")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.dumps(
            {
                "error": {
                    "code": "PIPELINE_PROXY_INVALID_CONTENT",
                    "message": "Pipeline stats response was not valid JSON.",
                }
            },
            separators=(",", ":"),
        ).encode("utf-8")
    return json.dumps(
        _strip_browser_forbidden_stats_fields(payload),
        separators=(",", ":"),
    ).encode("utf-8")


@router.get("/field-index/stats")
async def proxy_field_index_stats(
    proxyId: str = Query(..., min_length=1),
    request_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> Response:
    record = await _resolve_record(proxy_id=proxyId, operation="stats", user=user, team=team)
    client = IngestionClient()
    content, upstream_content_type = await _run_blocking(
        client.fetch_binary, record["upstreamUrl"], request_id=request_id
    )
    return Response(
        content=_sanitize_stats_content(content, upstream_content_type),
        media_type=_content_type("stats", upstream_content_type),
    )


@router.get("/tiles/{z}/{x}/{y}.png")
async def proxy_tile(
    z: int,
    x: int,
    y: int,
    proxyId: str = Query(..., min_length=1),
    request_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    team: CurrentTeam = Depends(get_current_team),
) -> Response:
    record = await _resolve_record(proxy_id=proxyId, operation="tile", user=user, team=team)
    upstream_url = (
        record["upstreamUrl"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    )
    client = IngestionClient()
    content, upstream_content_type = await _run_blocking(
        client.fetch_binary, upstream_url, request_id=request_id
    )
    return Response(content=content, media_type=_content_type("tile", upstream_content_type))
