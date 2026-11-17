"""Business model."""

from sqlalchemy import BigInteger, Integer, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Business(db.Model):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="Africa/Johannesburg"
    )
    cancel_cutoff_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    slot_step_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15")
    created_at: Mapped[object] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
