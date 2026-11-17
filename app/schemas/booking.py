"""Validated booking request bodies."""

from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BookingCreate(Payload):
    service_id: int = Field(gt=0)
    staff_id: int | Literal["any"]
    start_at: datetime

    @field_validator("staff_id", mode="before")
    @classmethod
    def parse_staff_id(cls, value):
        if value == "any":
            return value
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Staff must be a positive ID or 'any'.") from exc
        if parsed <= 0:
            raise ValueError("Staff must be a positive ID or 'any'.")
        return parsed

    @field_validator("start_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_at must include a UTC timezone offset.")
        if value.utcoffset() != timedelta(0):
            raise ValueError("start_at must be expressed in UTC.")
        return value


class BookingReschedule(Payload):
    start_at: datetime
    staff_id: int | Literal["any"] | None = None

    @field_validator("staff_id", mode="before")
    @classmethod
    def parse_staff_id(cls, value):
        if value is None or value == "any":
            return value
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Staff must be a positive ID or 'any'.") from exc
        if parsed <= 0:
            raise ValueError("Staff must be a positive ID or 'any'.")
        return parsed

    @field_validator("start_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_at must include a UTC timezone offset.")
        if value.utcoffset() != timedelta(0):
            raise ValueError("start_at must be expressed in UTC.")
        return value


class BookingAction(Payload):
    action: Literal["cancel", "reschedule", "confirm", "complete", "no_show"]
    start_at: datetime | None = None
    staff_id: int | Literal["any"] | None = None

    @model_validator(mode="after")
    def reschedule_fields(self) -> Self:
        if self.action == "reschedule" and self.start_at is None:
            raise ValueError("Reschedule requires start_at.")
        if self.action != "reschedule" and (self.start_at is not None or self.staff_id is not None):
            raise ValueError("Only reschedule accepts start_at or staff_id.")
        return self

    @field_validator("start_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("start_at must be expressed in UTC with an offset.")
        return value

    @field_validator("staff_id", mode="before")
    @classmethod
    def parse_staff_id(cls, value):
        if value is None or value == "any":
            return value
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Staff must be a positive ID or 'any'.") from exc
        if parsed <= 0:
            raise ValueError("Staff must be a positive ID or 'any'.")
        return parsed
