"""Postgres-backed account API key and notification storage."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .db import get_connection


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def list_api_keys(team_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, name, prefix, last4, created_at, revoked_at
            FROM akasha.api_keys
            WHERE team_id = %s
              AND revoked_at IS NULL
            ORDER BY created_at DESC, id DESC
            """,
            (team_id,),
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "prefix": row[2],
                "last4": row[3],
                "createdAt": _iso(row[4]),
                "revokedAt": _iso(row[5]),
            }
            for row in cur.fetchall()
        ]


def create_api_key(
    *,
    team_id: str,
    user_id: str,
    name: str,
    key_hash: str,
    prefix: str,
    last4: str,
) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.api_keys (team_id, user_id, name, key_hash, prefix, last4)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id::text, name, prefix, last4, created_at, revoked_at
            """,
            (team_id, user_id, name, key_hash, prefix, last4),
        )
        row = cur.fetchone()
        conn.commit()
    return {
        "id": row[0],
        "name": row[1],
        "prefix": row[2],
        "last4": row[3],
        "createdAt": _iso(row[4]),
        "revokedAt": _iso(row[5]),
    }


def revoke_api_key(*, team_id: str, key_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.api_keys
            SET revoked_at = now()
            WHERE id::text = %s
              AND team_id = %s
              AND revoked_at IS NULL
            """,
            (key_id, team_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
    return changed


def list_notifications(*, team_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
    where_unread = "AND read_at IS NULL" if unread_only else ""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id::text, type, title, body, resource_type, resource_id,
                   read_at, metadata, created_at
            FROM akasha.notifications
            WHERE team_id = %s
              {where_unread}
            ORDER BY created_at DESC, id DESC
            """,
            (team_id,),
        )
        return [_notification(row) for row in cur.fetchall()]


def unread_notification_count(team_id: str) -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM akasha.notifications
            WHERE team_id = %s
              AND read_at IS NULL
            """,
            (team_id,),
        )
        return int(cur.fetchone()[0])


def mark_notification_read(*, team_id: str, notification_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.notifications
            SET read_at = COALESCE(read_at, now())
            WHERE id::text = %s
              AND team_id = %s
            RETURNING id::text, type, title, body, resource_type, resource_id,
                      read_at, metadata, created_at
            """,
            (notification_id, team_id),
        )
        row = cur.fetchone()
        conn.commit()
    return _notification(row) if row else None


def mark_all_notifications_read(team_id: str) -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.notifications
            SET read_at = COALESCE(read_at, now())
            WHERE team_id = %s
              AND read_at IS NULL
            """,
            (team_id,),
        )
        changed = cur.rowcount
        conn.commit()
    return changed


def _notification(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "type": row[1],
        "title": row[2],
        "body": row[3],
        "resourceType": row[4],
        "resourceId": row[5],
        "readAt": _iso(row[6]),
        "metadata": _metadata(row[7]),
        "createdAt": _iso(row[8]),
    }
