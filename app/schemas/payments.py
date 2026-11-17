"""Validated payment filters and dates."""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaymentListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: Literal["pending", "paid", "failed", "refunded"] | None = None
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.from_date and self.to_date and self.to_date < self.from_date:
            raise ValueError("'to' must be on or after 'from'.")
        return self
