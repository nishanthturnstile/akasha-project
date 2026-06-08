"""Database-backed username/password auth helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import get_connection

BOOTSTRAP_ADVISORY_LOCK_KEY = 4242421201


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _user(row: tuple) -> dict[str, Any]:
    (
        user_id,
        username,
        email,
        display_name,
        status,
        password_hash,
        failed_login_count,
        locked_until,
    ) = row
    return {
        "id": str(user_id),
        "username": username,
        "email": email,
        "displayName": display_name or username or email,
        "status": status,
        "passwordHash": password_hash,
        "failedLoginCount": int(failed_login_count or 0),
        "lockedUntil": _iso(locked_until),
    }


def _membership(row: tuple) -> dict[str, Any]:
    team_id, team_name, role = row
    return {"id": str(team_id), "name": team_name, "role": role}


def active_user_count() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM akasha.users WHERE status = 'active'")
        return int(cur.fetchone()[0])


def active_password_user_count() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*)
            FROM akasha.users
            WHERE status = 'active'
              AND password_hash IS NOT NULL
            """)
        return int(cur.fetchone()[0])


def find_user_by_username(username: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, email, display_name, status, password_hash,
                   failed_login_count, locked_until
            FROM akasha.users
            WHERE lower(username) = lower(%s)
            """,
            (username.strip(),),
        )
        row = cur.fetchone()
        return _user(row) if row else None


def memberships_for_user(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.name, m.role
            FROM akasha.memberships m
            JOIN akasha.teams t ON t.id = m.team_id
            WHERE m.user_id = %s
            ORDER BY
                CASE m.role
                    WHEN 'owner' THEN 0
                    WHEN 'admin' THEN 1
                    WHEN 'member' THEN 2
                    ELSE 3
                END,
                t.created_at,
                t.id
            """,
            (user_id,),
        )
        return [_membership(row) for row in cur.fetchall()]


def record_login_failure(user_id: str, locked_until: datetime | None = None) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.users
            SET failed_login_count = failed_login_count + 1,
                locked_until = COALESCE(%s, locked_until)
            WHERE id = %s
            """,
            (locked_until, user_id),
        )


def record_login_success(user_id: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.users
            SET failed_login_count = 0,
                locked_until = NULL,
                last_login_at = now()
            WHERE id = %s
            """,
            (user_id,),
        )


def create_session(
    *,
    token_hash: str,
    user_id: str,
    team_id: str | None,
    expires_at: datetime,
    user_agent_hash: str | None,
    remember_me: bool = False,
) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.sessions (
                token_hash, user_id, team_id, expires_at, user_agent_hash, remember_me
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (token_hash, user_id, team_id, expires_at, user_agent_hash, remember_me),
        )


def get_session_context(token_hash: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.username, u.email, u.display_name, u.status, u.password_hash,
                   u.failed_login_count, u.locked_until, s.team_id::text, s.remember_me
            FROM akasha.sessions s
            JOIN akasha.users u ON u.id = s.user_id
            WHERE s.token_hash = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > now()
              AND u.status = 'active'
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        user = _user(row[:8])
        memberships = memberships_for_user(user["id"])
        return {
            "user": user,
            "memberships": memberships,
            "teamId": row[8],
            "rememberMe": bool(row[9]),
        }


def revoke_session(token_hash: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE akasha.sessions SET revoked_at = now() WHERE token_hash = %s",
            (token_hash,),
        )


def revoke_other_sessions(user_id: str, keep_token_hash: str | None = None) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        if keep_token_hash:
            cur.execute(
                """
                UPDATE akasha.sessions
                SET revoked_at = now()
                WHERE user_id = %s AND token_hash <> %s AND revoked_at IS NULL
                """,
                (user_id, keep_token_hash),
            )
        else:
            cur.execute(
                """
                UPDATE akasha.sessions
                SET revoked_at = now()
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            )


def rotate_session(old_token_hash: str, new_token_hash: str, expires_at: datetime) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.sessions
            SET token_hash = %s,
                expires_at = %s,
                rotated_at = now()
            WHERE token_hash = %s
              AND revoked_at IS NULL
              AND expires_at > now()
            """,
            (new_token_hash, expires_at, old_token_hash),
        )
        return cur.rowcount > 0


def update_password_hash(user_id: str, password_hash: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE akasha.users
            SET password_hash = %s,
                password_updated_at = now()
            WHERE id = %s
            """,
            (password_hash, user_id),
        )


def create_user_with_team(
    *,
    username: str,
    email: str,
    display_name: str,
    password_hash: str,
    team_name: str,
    require_no_password_users: bool = False,
) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        if require_no_password_users:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (BOOTSTRAP_ADVISORY_LOCK_KEY,))
            cur.execute("""
                SELECT count(*)
                FROM akasha.users
                WHERE status = 'active'
                  AND password_hash IS NOT NULL
                """)
            if int(cur.fetchone()[0]) != 0:
                return None
        cur.execute(
            """
            INSERT INTO akasha.users (
                username, email, display_name, password_hash, password_updated_at
            )
            VALUES (%s, %s, %s, %s, now())
            RETURNING id::text
            """,
            (username.strip(), email.strip().lower(), display_name.strip(), password_hash),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO akasha.teams (name, created_by)
            VALUES (%s, %s)
            RETURNING id::text
            """,
            (team_name.strip(), user_id),
        )
        team_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO akasha.memberships (team_id, user_id, role)
            VALUES (%s, %s, 'owner')
            """,
            (team_id, user_id),
        )
    return {"userId": user_id, "teamId": team_id}
