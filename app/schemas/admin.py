"""Validated payloads for business administration routes."""

import re
from datetime import datetime, time
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BusinessCreate(Payload):
    slug: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1)
    timezone: str = "Africa/Johannesburg"

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9-]{3,40}", value):
            raise ValueError("Slug must contain lowercase letters, digits and hyphens.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone.") from exc
        return value


class BusinessPatch(Payload):
    name: str | None = Field(default=None, min_length=1)
    timezone: str | None = None
    cancel_cutoff_hours: int | None = Field(default=None, ge=0)
    slot_step_min: int | None = Field(default=None, gt=0)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Timezone must be a valid IANA timezone.") from exc
        return value


class ServiceCreate(Payload):
    name: str = Field(min_length=1)
    description: str | None = None
    duration_min: int = Field(gt=0)
    buffer_min: int = Field(default=0, ge=0)
    price_cents: int = Field(ge=0)
    deposit_cents: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def deposit_within_price(self) -> Self:
        if self.deposit_cents > self.price_cents:
            raise ValueError("Deposit cannot exceed price.")
        return self


class ServicePatch(Payload):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    duration_min: int | None = Field(default=None, gt=0)
    buffer_min: int | None = Field(default=None, ge=0)
    price_cents: int | None = Field(default=None, ge=0)
    deposit_cents: int | None = Field(default=None, ge=0)


class StaffCreate(Payload):
    display_name: str = Field(min_length=1)
    user_id: int | None = None


class StaffPatch(Payload):
    display_name: str | None = Field(default=None, min_length=1)
    user_id: int | None = None


class HoursEntry(Payload):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def end_is_later(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time.")
        return self


class HoursReplace(Payload):
    hours: list[HoursEntry]


class TimeOffCreate(Payload):
    start_at: datetime
    end_at: datetime
    reason: str | None = None

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Time off timestamps must include a timezone.")
        if self.end_at <= self.start_at:
            raise ValueError("End must be after start.")
        return self
