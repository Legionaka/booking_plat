"""Payment transaction model."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'paid', 'failed', 'refunded')"),
        UniqueConstraint("provider", "provider_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[object] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
