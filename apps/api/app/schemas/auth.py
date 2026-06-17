"""Auth API Pydantic schemas."""

from __future__ import annotations

from pydantic import Field, field_validator

from ..api_models import ApiModel


class LoginPayload(ApiModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class SignupPayload(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if not clean or "@" not in clean:
            raise ValueError("valid email is required")
        return clean

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("display name is required")
        return clean


class PasswordChangePayload(ApiModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class AccountMe(ApiModel):
    user: dict
    current_team: dict
    memberships: list[dict]
    auth_mode: str = "enabled"
