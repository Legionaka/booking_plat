"""Audit trail model."""

from sqlalchemy import BigInteger, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("businesses.id"))
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    diff: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[object] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
