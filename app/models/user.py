"""User model."""

from sqlalchemy import BigInteger, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[object | None] = mapped_column(db.DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
