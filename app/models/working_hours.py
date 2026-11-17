"""Weekly staff working-hours model."""

from datetime import time

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, SmallInteger, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class WorkingHours(db.Model):
    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6"),
        CheckConstraint("end_time > start_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
