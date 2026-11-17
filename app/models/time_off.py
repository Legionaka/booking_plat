"""Staff time-off model."""

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class TimeOff(db.Model):
    __tablename__ = "time_off"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), nullable=False
    )
    during: Mapped[object] = mapped_column(TSTZRANGE, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
