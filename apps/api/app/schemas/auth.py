"""Auth API Pydantic schemas."""

from __future__ import annotations

from pydantic import Field

from ..api_models import ApiModel


class LoginPayload(ApiModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class BootstrapPayload(ApiModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=8, max_length=1024)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    team_name: str = Field(default="Akasha Team", min_length=1, max_length=200)
    bootstrap_token: str | None = Field(default=None, min_length=1, max_length=512)


class SignupPayload(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)


class PasswordChangePayload(ApiModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class AccountMe(ApiModel):
    user: dict
    current_team: dict
    memberships: list[dict]
    auth_mode: str = "enabled"
