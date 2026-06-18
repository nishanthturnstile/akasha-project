"""Username/password authentication routes."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError

from ..auth import (
    CurrentUser,
    TeamMembership,
    auth_password_pepper,
    clear_session_cookie,
    ensure_auth_enabled_configured,
    forbidden,
    get_current_user,
    hash_token,
    hash_user_agent,
    invalid_credentials,
    new_session_token,
    session_expires_at,
    set_session_cookie,
    unauthorized,
)
from ..config import settings
from ..raster.errors import AkashaError, bad_request
from ..repositories import auth_repo
from ..schemas.auth import (
    AccountMe,
    LoginPayload,
    PasswordChangePayload,
    SignupPayload,
)

router = APIRouter(prefix="/api", tags=["auth"])
logger = logging.getLogger(__name__)

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
_DUMMY_PASSWORD = "akasha-invalid-login-timing-check"
_DUMMY_PASSWORD_HASH: str | None = None
_AUTH_RATE_BUCKETS: dict[tuple[str, str], list[float]] = {}


def _password_hasher():
    from argon2 import PasswordHasher  # noqa: PLC0415

    return PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher().hash(password + auth_password_pepper())


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _password_hasher().verify(password_hash, password + auth_password_pepper())
    except Exception:  # noqa: BLE001
        return False


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _enforce_auth_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: float,
) -> None:
    if limit <= 0:
        return
    now = time.monotonic()
    cutoff = now - window_seconds
    key = (scope, _client_id(request))
    hits = [ts for ts in _AUTH_RATE_BUCKETS.get(key, []) if ts >= cutoff]
    if len(hits) >= limit:
        from ..raster.errors import rate_limited  # noqa: PLC0415

        raise rate_limited("Too many authentication attempts. Please retry later.")
    hits.append(now)
    _AUTH_RATE_BUCKETS[key] = hits


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password(_DUMMY_PASSWORD)
    return _DUMMY_PASSWORD_HASH


def _verify_dummy_password(password: str) -> None:
    verify_password(password, _dummy_password_hash())


def _verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    if password_hash:
        return verify_password(password, password_hash)
    _verify_dummy_password(password)
    return False


def account_me_payload(user: CurrentUser) -> AccountMe:
    team = next(
        (item for item in user.memberships if item.id == user.current_team_id),
        user.memberships[0],
    )
    return AccountMe(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "displayName": user.display_name,
            "onboardingCompleted": user.onboarding_completed,
        },
        current_team={"id": team.id, "name": team.name, "role": team.role},
        memberships=[
            {"teamId": item.id, "teamName": item.name, "role": item.role}
            for item in user.memberships
        ],
        auth_mode="enabled",
    )


def _create_login_session(
    *,
    response: Response,
    request: Request,
    user_id: str,
    team_id: str | None,
    remember: bool,
) -> str:
    raw = new_session_token()
    expires_at = session_expires_at(remember=remember)
    auth_repo.create_session(
        token_hash=hash_token(raw),
        user_id=user_id,
        team_id=team_id,
        expires_at=expires_at,
        user_agent_hash=hash_user_agent(request.headers.get("user-agent")),
        remember_me=remember,
    )
    set_session_cookie(response, raw, expires_at)
    return raw


def _signup_team_name(display_name: str) -> str:
    clean_name = display_name.strip()
    if clean_name.endswith("s"):
        return f"{clean_name}' Team"
    return f"{clean_name}'s Team"


@router.post("/auth/login", response_model=AccountMe, response_model_by_alias=True)
async def login(payload: LoginPayload, request: Request, response: Response) -> AccountMe:
    ensure_auth_enabled_configured()
    _enforce_auth_rate_limit(
        request,
        scope="login",
        limit=settings.auth_login_rate_limit_per_minute,
        window_seconds=60.0,
    )
    user = auth_repo.find_user_by_username(payload.username)
    if user is None:
        _verify_dummy_password(payload.password)
        raise invalid_credentials()
    locked_until = _parse_dt(user.get("lockedUntil"))
    password_ok = _verify_password_or_dummy(payload.password, user.get("passwordHash"))
    if locked_until and locked_until > datetime.now(UTC):
        raise invalid_credentials()
    if user["status"] != "active" or not password_ok:
        lock_at = None
        if int(user.get("failedLoginCount") or 0) + 1 >= MAX_FAILED_LOGINS:
            lock_at = datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)
        auth_repo.record_login_failure(user["id"], lock_at)
        raise invalid_credentials()
    memberships = auth_repo.memberships_for_user(user["id"])
    if not memberships:
        raise forbidden("No team membership is available for this user.")
    auth_repo.record_login_success(user["id"])
    _create_login_session(
        response=response,
        request=request,
        user_id=user["id"],
        team_id=memberships[0]["id"],
        remember=payload.remember_me,
    )
    current = CurrentUser(
        id=user["id"],
        email=user["email"],
        display_name=user["displayName"],
        username=user.get("username"),
        role=memberships[0]["role"],
        onboarding_completed=bool(user.get("onboardingCompleted", False)),
        current_team_id=memberships[0]["id"],
        memberships=tuple(
            TeamMembership(id=item["id"], name=item["name"], role=item["role"])
            for item in memberships
        ),
    )
    return account_me_payload(current)


@router.post("/auth/signup", response_model=AccountMe, response_model_by_alias=True)
async def signup(payload: SignupPayload, request: Request, response: Response) -> AccountMe:
    ensure_auth_enabled_configured()
    _enforce_auth_rate_limit(
        request,
        scope="signup",
        limit=settings.auth_signup_rate_limit_per_hour,
        window_seconds=3600.0,
    )
    if not settings.auth_allow_signup:
        raise forbidden("Sign-up is not enabled.")
    email = payload.email
    display_name = payload.display_name
    if auth_repo.find_user_by_email(email) is not None:
        raise bad_request(
            "An account with this email already exists.",
            code="EMAIL_ALREADY_REGISTERED",
        )
    try:
        created = auth_repo.create_user_with_team(
            username=email,
            email=email,
            display_name=display_name,
            password_hash=hash_password(payload.password),
            team_name=_signup_team_name(display_name),
        )
    except IntegrityError as exc:
        raise bad_request(
            "An account with this email already exists.",
            code="EMAIL_ALREADY_REGISTERED",
        ) from exc
    if created is None:
        raise AkashaError(
            "SIGNUP_UNAVAILABLE",
            "Sign-up is temporarily unavailable.",
            503,
        )
    memberships = auth_repo.memberships_for_user(created["userId"])
    if not memberships:
        raise forbidden("No team membership is available for this user.")
    _create_login_session(
        response=response,
        request=request,
        user_id=created["userId"],
        team_id=memberships[0]["id"],
        remember=False,
    )
    current = CurrentUser(
        id=created["userId"],
        email=email,
        display_name=display_name,
        username=email,
        role=memberships[0]["role"],
        onboarding_completed=False,
        current_team_id=memberships[0]["id"],
        memberships=tuple(
            TeamMembership(id=item["id"], name=item["name"], role=item["role"])
            for item in memberships
        ),
    )
    return account_me_payload(current)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    raw_token = request.cookies.get(settings.auth_session_cookie_name)
    if raw_token and settings.auth_password_pepper.strip():
        try:
            auth_repo.revoke_session(hash_token(raw_token))
        except Exception:  # noqa: BLE001
            logger.warning("Unable to revoke session during logout.", exc_info=True)
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/auth/refresh", response_model=AccountMe, response_model_by_alias=True)
async def refresh_session(
    request: Request,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
) -> AccountMe:
    if not user.session_token_hash:
        return account_me_payload(user)
    raw = new_session_token()
    expires_at = session_expires_at(remember=user.session_remember_me)
    if not auth_repo.rotate_session(user.session_token_hash, hash_token(raw), expires_at):
        clear_session_cookie(response)
        raise unauthorized()
    set_session_cookie(response, raw, expires_at)
    return account_me_payload(user)


@router.patch("/account/password", response_model=dict[str, bool], response_model_by_alias=True)
async def change_password(
    payload: PasswordChangePayload,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    stored = auth_repo.find_user_by_username(user.username or "")
    if stored is None or not verify_password(payload.current_password, stored["passwordHash"]):
        raise bad_request("Current password is incorrect.", code="INVALID_CURRENT_PASSWORD")
    auth_repo.update_password_hash(user.id, hash_password(payload.new_password))
    auth_repo.revoke_other_sessions(user.id, keep_token_hash=user.session_token_hash)
    return {"changed": True}
