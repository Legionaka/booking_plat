"""Pydantic request schemas for authentication endpoints."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

EmailValue = Annotated[str, Field(min_length=3, max_length=320)]
PasswordValue = Annotated[str, Field(min_length=10, max_length=128)]


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthRequest):
    email: EmailValue
    password: PasswordValue
    full_name: Annotated[str, Field(min_length=1, max_length=150)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name is required.")
        return cleaned


class LoginRequest(AuthRequest):
    email: EmailValue
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class VerifyRequest(AuthRequest):
    token: Annotated[str, Field(min_length=1, max_length=4096)]


class ResendVerificationRequest(AuthRequest):
    email: EmailValue

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class ForgotRequest(AuthRequest):
    email: EmailValue

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class ResetRequest(AuthRequest):
    token: Annotated[str, Field(min_length=1, max_length=4096)]
    new_password: PasswordValue
