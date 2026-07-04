"""Postgres-backed storage for opaque pipeline proxy records.

Proxy records hold ingestion signed-URL material server-side so the browser
only ever receives an opaque ``proxy_id``. Records live in Postgres so any BFF
worker can resolve a proxy request (multi-worker safe).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from ..db import session_scope
from ..models import PipelineProxyRecord

PROXY_ID_PREFIX = "px_"


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def new_proxy_id() -> str:
    return PROXY_ID_PREFIX + secrets.token_urlsafe(18)


def _record(row: PipelineProxyRecord) -> dict[str, Any]:
    return {
        "proxyId": row.proxy_id,
        "operation": row.operation,
        "upstreamUrl": row.upstream_url,
        "userId": str(row.user_id),
        "teamId": str(row.team_id),
        "fieldId": row.field_id,
        "sourceId": row.source_id,
        "indexType": row.index_type,
        "queryId": row.query_id,
        "layerId": row.layer_id,
        "expiresAt": row.expires_at,
        "createdAt": row.created_at,
        "lastAccessedAt": row.last_accessed_at,
    }


def create_proxy_record(
    *,
    operation: str,
    upstream_url: str,
    user_id: str,
    team_id: str,
    field_id: str,
    source_id: str,
    index_type: str,
    expires_at: datetime,
    query_id: str | None = None,
    layer_id: str | None = None,
) -> str:
    """Persist a proxy record and return its opaque ``proxy_id``."""

    proxy_id = new_proxy_id()
    record = PipelineProxyRecord(
        proxy_id=proxy_id,
        operation=operation,
        upstream_url=upstream_url,
        user_id=_uuid(user_id),
        team_id=_uuid(team_id),
        field_id=field_id,
        source_id=source_id,
        index_type=index_type,
        query_id=query_id,
        layer_id=layer_id,
        expires_at=expires_at,
    )
    with session_scope() as session:
        session.add(record)
        session.flush()
        return proxy_id


def get_proxy_record(proxy_id: str) -> dict[str, Any] | None:
    stmt = select(PipelineProxyRecord).where(PipelineProxyRecord.proxy_id == proxy_id)
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _record(row) if row is not None else None


def touch_last_accessed(proxy_id: str) -> None:
    stmt = (
        update(PipelineProxyRecord)
        .where(PipelineProxyRecord.proxy_id == proxy_id)
        .values(last_accessed_at=func.now())
    )
    with session_scope() as session:
        session.execute(stmt)


def delete_expired(*, now: datetime | None = None) -> int:
    """TTL cleanup helper: remove records whose ``expires_at`` has passed."""

    cutoff = now or datetime.now(UTC)
    stmt = delete(PipelineProxyRecord).where(PipelineProxyRecord.expires_at < cutoff)
    with session_scope() as session:
        return int(session.execute(stmt).rowcount or 0)
