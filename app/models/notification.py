"""Scheduled notification model."""

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("booking_id", "kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[object] = mapped_column(db.DateTime(timezone=True), nullable=False)
    sent_at: Mapped[object | None] = mapped_column(db.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
