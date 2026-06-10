"""Postgres-backed account API key and notification storage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update

from .db import session_scope
from .models import ApiKey, Notification


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _api_key(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.prefix,
        "last4": row.last4,
        "createdAt": _iso(row.created_at),
        "revokedAt": _iso(row.revoked_at),
    }


def list_api_keys(team_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(ApiKey)
        .where(ApiKey.team_id == _uuid(team_id), ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
    )
    with session_scope() as session:
        return [_api_key(row) for row in session.execute(stmt).scalars().all()]


def create_api_key(
    *,
    team_id: str,
    user_id: str,
    name: str,
    key_hash: str,
    prefix: str,
    last4: str,
) -> dict[str, Any]:
    api_key = ApiKey(
        team_id=_uuid(team_id),
        user_id=_uuid(user_id),
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        last4=last4,
    )
    with session_scope() as session:
        session.add(api_key)
        session.flush()
        return _api_key(api_key)


def revoke_api_key(*, team_id: str, key_id: str) -> bool:
    stmt = (
        update(ApiKey)
        .where(
            ApiKey.id == _uuid(key_id),
            ApiKey.team_id == _uuid(team_id),
            ApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    with session_scope() as session:
        return session.execute(stmt).rowcount > 0


def list_notifications(*, team_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
    stmt = select(Notification).where(Notification.team_id == _uuid(team_id))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    with session_scope() as session:
        return [_notification(row) for row in session.execute(stmt).scalars().all()]


def unread_notification_count(team_id: str) -> int:
    stmt = select(func.count()).select_from(Notification).where(
        Notification.team_id == _uuid(team_id),
        Notification.read_at.is_(None),
    )
    with session_scope() as session:
        return int(session.execute(stmt).scalar_one())


def mark_notification_read(*, team_id: str, notification_id: str) -> dict[str, Any] | None:
    stmt = (
        update(Notification)
        .where(Notification.id == _uuid(notification_id), Notification.team_id == _uuid(team_id))
        .values(read_at=func.coalesce(Notification.read_at, func.now()))
        .returning(Notification)
    )
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _notification(row) if row else None


def mark_all_notifications_read(team_id: str) -> int:
    stmt = (
        update(Notification)
        .where(Notification.team_id == _uuid(team_id), Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    with session_scope() as session:
        return session.execute(stmt).rowcount


def _notification(row: Notification) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "resourceType": row.resource_type,
        "resourceId": row.resource_id,
        "readAt": _iso(row.read_at),
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
    }
