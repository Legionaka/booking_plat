"""Business administration operations and tenant-scoped authorization."""

from datetime import UTC

from flask import g
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AuditLog,
    Business,
    Membership,
    Staff,
)


class AdminError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def require_business(business_id: int, roles=("owner",)) -> Business:
    user = getattr(g, "current_user", None)
    if user is None:
        raise AdminError("authentication_required", "Sign in to continue.", 401)
    business = db.session.get(Business, business_id)
    membership = db.session.get(Membership, (user.id, business_id))
    if business is None or membership is None:
        raise AdminError("not_found", "Resource not found.", 404)
    if membership.role not in roles:
        raise AdminError("forbidden", "You do not have permission for this action.", 403)
    return business


def audit(entity: str, entity_id: int, action: str, diff: dict, business_id: int | None = None):
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            business_id=business_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            diff=diff,
        )
    )


def commit():
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise AdminError(
            "conflict", "The requested resource conflicts with existing data.", 409
        ) from exc


def page(query, limit: int, offset: int):
    return db.session.execute(query.limit(limit).offset(offset)).scalars().all()


def serialize_business(x):
    return {
        "id": x.id,
        "slug": x.slug,
        "name": x.name,
        "timezone": x.timezone,
        "cancel_cutoff_hours": x.cancel_cutoff_hours,
        "slot_step_min": x.slot_step_min,
    }


def serialize_service(x):
    return {
        "id": x.id,
        "business_id": x.business_id,
        "name": x.name,
        "description": x.description,
        "duration_min": x.duration_min,
        "buffer_min": x.buffer_min,
        "price_cents": x.price_cents,
        "deposit_cents": x.deposit_cents,
        "active": x.active,
    }


def serialize_staff(x):
    return {
        "id": x.id,
        "business_id": x.business_id,
        "user_id": x.user_id,
        "display_name": x.display_name,
        "active": x.active,
    }


def _get_scoped(model, resource_id, business_id):
    obj = db.session.execute(
        select(model).where(model.id == resource_id, model.business_id == business_id)
    ).scalar_one_or_none()
    if obj is None:
        raise AdminError("not_found", "Resource not found.", 404)
    return obj


def get_staff(staff_id, business_id):
    return _get_scoped(Staff, staff_id, business_id)


def staff_time_off(staff: Staff, user_id: int):
    if staff.user_id != user_id:
        raise AdminError("not_found", "Resource not found.", 404)


def to_utc(value):
    return value.astimezone(UTC)
