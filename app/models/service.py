"""Bookable service model."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Service(db.Model):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_min > 0"),
        CheckConstraint("buffer_min >= 0"),
        CheckConstraint("price_cents >= 0"),
        CheckConstraint("deposit_cents >= 0"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
