"""Staff model and service-assignment table."""

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Table, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

staff_services = Table(
    "staff_services",
    db.metadata,
    Column("staff_id", BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "service_id", BigInteger, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Staff(db.Model):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
