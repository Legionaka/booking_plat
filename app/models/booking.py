"""Booking model with the database-enforced overlap exclusion constraint."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    column,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_at > start_at AND blocked_until >= end_at"),
        Index("bookings_business_start", "business_id", "start_at"),
        Index("bookings_customer", "customer_id"),
        ExcludeConstraint(
            ("staff_id", "="),
            (
                func.tstzrange(column("start_at"), column("blocked_until"), literal_column("'[)'")),
                "&&",
            ),
            where=text("status IN ('pending', 'confirmed')"),
            using="gist",
            name="bookings_staff_id_tstzrange_excl",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("services.id"), nullable=False)
    start_at: Mapped[object] = mapped_column(db.DateTime(timezone=True), nullable=False)
    end_at: Mapped[object] = mapped_column(db.DateTime(timezone=True), nullable=False)
    blocked_until: Mapped[object] = mapped_column(db.DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    hold_expires_at: Mapped[object | None] = mapped_column(db.DateTime(timezone=True))
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[object] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
