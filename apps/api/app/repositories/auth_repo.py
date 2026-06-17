"""Database-backed username/password auth helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, update

from ..db import session_scope
from ..models import AuthSession, Membership, Team, User


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _user(row: User) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "username": row.username,
        "email": row.email,
        "displayName": row.display_name or row.username or row.email,
        "onboardingCompleted": bool(row.onboarding_completed),
        "status": row.status,
        "passwordHash": row.password_hash,
        "failedLoginCount": int(row.failed_login_count or 0),
        "lockedUntil": _iso(row.locked_until),
    }


def _membership(row: tuple[Any, ...]) -> dict[str, Any]:
    team_id, team_name, role = row
    return {"id": str(team_id), "name": team_name, "role": role}


def active_user_count() -> int:
    stmt = select(func.count()).select_from(User).where(User.status == "active")
    with session_scope() as session:
        return int(session.execute(stmt).scalar_one())


def active_password_user_count() -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.status == "active", User.password_hash.is_not(None))
    )
    with session_scope() as session:
        return int(session.execute(stmt).scalar_one())


def find_user_by_username(username: str) -> dict[str, Any] | None:
    stmt = select(User).where(func.lower(User.username) == username.strip().lower())
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _user(row) if row else None


def find_user_by_email(email: str) -> dict[str, Any] | None:
    stmt = select(User).where(func.lower(User.email) == email.strip().lower())
    with session_scope() as session:
        row = session.execute(stmt).scalar_one_or_none()
        return _user(row) if row else None


def memberships_for_user(user_id: str) -> list[dict[str, Any]]:
    role_order = case(
        (Membership.role == "owner", 0),
        (Membership.role == "admin", 1),
        (Membership.role == "member", 2),
        else_=3,
    )
    stmt = (
        select(Team.id, Team.name, Membership.role)
        .join(Team, Team.id == Membership.team_id)
        .where(Membership.user_id == _uuid(user_id))
        .order_by(role_order, Team.created_at, Team.id)
    )
    with session_scope() as session:
        return [_membership(row) for row in session.execute(stmt).all()]


def record_login_failure(user_id: str, locked_until: datetime | None = None) -> None:
    values: dict[str, Any] = {"failed_login_count": User.failed_login_count + 1}
    if locked_until is not None:
        values["locked_until"] = locked_until
    stmt = update(User).where(User.id == _uuid(user_id)).values(**values)
    with session_scope() as session:
        session.execute(stmt)


def record_login_success(user_id: str) -> None:
    stmt = (
        update(User)
        .where(User.id == _uuid(user_id))
        .values(failed_login_count=0, locked_until=None, last_login_at=func.now())
    )
    with session_scope() as session:
        session.execute(stmt)


def create_session(
    *,
    token_hash: str,
    user_id: str,
    team_id: str | None,
    expires_at: datetime,
    user_agent_hash: str | None,
    remember_me: bool = False,
) -> None:
    session_row = AuthSession(
        token_hash=token_hash,
        user_id=_uuid(user_id),
        team_id=_uuid(team_id),
        expires_at=expires_at,
        user_agent_hash=user_agent_hash,
        remember_me=remember_me,
    )
    with session_scope() as session:
        session.add(session_row)


def get_session_context(token_hash: str) -> dict[str, Any] | None:
    stmt = (
        select(User, AuthSession.team_id, AuthSession.remember_me)
        .join(AuthSession, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > func.now(),
            User.status == "active",
        )
    )
    with session_scope() as session:
        row = session.execute(stmt).first()
    if not row:
        return None
    user = _user(row[0])
    memberships = memberships_for_user(user["id"])
    return {
        "user": user,
        "memberships": memberships,
        "teamId": str(row[1]) if row[1] else None,
        "rememberMe": bool(row[2]),
    }


def revoke_session(token_hash: str) -> None:
    stmt = (
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(revoked_at=func.now())
    )
    with session_scope() as session:
        session.execute(stmt)


def revoke_other_sessions(user_id: str, keep_token_hash: str | None = None) -> None:
    stmt = update(AuthSession).where(
        AuthSession.user_id == _uuid(user_id),
        AuthSession.revoked_at.is_(None),
    )
    if keep_token_hash:
        stmt = stmt.where(AuthSession.token_hash != keep_token_hash)
    stmt = stmt.values(revoked_at=func.now())
    with session_scope() as session:
        session.execute(stmt)


def rotate_session(old_token_hash: str, new_token_hash: str, expires_at: datetime) -> bool:
    stmt = (
        update(AuthSession)
        .where(
            AuthSession.token_hash == old_token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > func.now(),
        )
        .values(token_hash=new_token_hash, expires_at=expires_at, rotated_at=func.now())
    )
    with session_scope() as session:
        return session.execute(stmt).rowcount > 0


def update_password_hash(user_id: str, password_hash: str) -> None:
    stmt = (
        update(User)
        .where(User.id == _uuid(user_id))
        .values(password_hash=password_hash, password_updated_at=func.now())
    )
    with session_scope() as session:
        session.execute(stmt)


def mark_onboarding_completed(user_id: str) -> None:
    stmt = update(User).where(User.id == _uuid(user_id)).values(onboarding_completed=True)
    with session_scope() as session:
        session.execute(stmt)


def create_user_with_team(
    *,
    username: str,
    email: str,
    display_name: str,
    password_hash: str,
    team_name: str,
) -> dict[str, Any] | None:
    with session_scope() as session:
        user = User(
            username=username.strip(),
            email=email.strip().lower(),
            display_name=display_name.strip(),
            password_hash=password_hash,
            password_updated_at=func.now(),
        )
        session.add(user)
        session.flush()
        team = Team(name=team_name.strip(), created_by=user.id)
        session.add(team)
        session.flush()
        session.add(Membership(team_id=team.id, user_id=user.id, role="owner"))
        return {"userId": str(user.id), "teamId": str(team.id)}
