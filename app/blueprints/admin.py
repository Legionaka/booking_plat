"""Tenant-scoped business administration API."""

from datetime import UTC, datetime

from flask import Blueprint, current_app, g, jsonify, request
from psycopg.types.range import Range
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import (
    Booking,
    Business,
    Membership,
    Service,
    Staff,
    TimeOff,
    User,
    WorkingHours,
    staff_services,
)
from app.schemas.admin import (
    BusinessCreate,
    BusinessPatch,
    HoursReplace,
    ServiceCreate,
    ServicePatch,
    StaffCreate,
    StaffPatch,
    TimeOffCreate,
)
from app.security import login_required
from app.services import admin as service

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _payload(model):
    try:
        return model.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise service.AdminError("validation_error", "Request body is invalid.", 422) from exc


def _errors(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except service.AdminError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status

    return wrapped


def _page_args():
    try:
        limit, offset = int(request.args.get("limit", 50)), int(request.args.get("offset", 0))
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError
        return limit, offset
    except ValueError as exc:
        raise service.AdminError(
            "validation_error", "Pagination requires limit 1–100 and offset >= 0.", 422
        ) from exc


def _data(value, status=200):
    return jsonify({"data": value}), status


@admin_bp.post("/businesses")
@login_required
@_errors
def create_business():
    payload = _payload(BusinessCreate)
    business = Business(**payload.model_dump())
    db.session.add(business)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise service.AdminError(
            "conflict", "The requested resource conflicts with existing data.", 409
        ) from exc
    db.session.add(Membership(user_id=g.current_user.id, business_id=business.id, role="owner"))
    service.audit(
        "business",
        business.id,
        "create",
        {"after": service.serialize_business(business)},
        business.id,
    )
    service.commit()
    return _data(service.serialize_business(business), 201)


@admin_bp.get("/businesses/<int:business_id>")
@login_required
@_errors
def get_business(business_id):
    return _data(
        service.serialize_business(service.require_business(business_id, ("owner", "staff")))
    )


@admin_bp.patch("/businesses/<int:business_id>")
@login_required
@_errors
def patch_business(business_id):
    business = service.require_business(business_id)
    changes = _payload(BusinessPatch).model_dump(exclude_unset=True)
    before = {key: getattr(business, key) for key in changes}
    for key, value in changes.items():
        setattr(business, key, value)
    service.audit(
        "business", business.id, "update", {"before": before, "after": changes}, business.id
    )
    service.commit()
    return _data(service.serialize_business(business))


@admin_bp.get("/businesses/<int:business_id>/services")
@login_required
@_errors
def list_services(business_id):
    service.require_business(business_id, ("owner", "staff"))
    limit, offset = _page_args()
    rows = service.page(
        select(Service).where(Service.business_id == business_id).order_by(Service.id),
        limit,
        offset,
    )
    return _data([service.serialize_service(row) for row in rows])


@admin_bp.post("/businesses/<int:business_id>/services")
@login_required
@_errors
def create_service(business_id):
    service.require_business(business_id)
    payload = _payload(ServiceCreate)
    item = Service(business_id=business_id, **payload.model_dump())
    db.session.add(item)
    db.session.flush()
    service.audit(
        "service", item.id, "create", {"after": service.serialize_service(item)}, business_id
    )
    service.commit()
    return _data(service.serialize_service(item), 201)


@admin_bp.patch("/businesses/<int:business_id>/services/<int:service_id>")
@login_required
@_errors
def update_service(business_id, service_id):
    service.require_business(business_id)
    item = service._get_scoped(Service, service_id, business_id)
    changes = _payload(ServicePatch).model_dump(exclude_unset=True)
    merged = {
        "duration_min": item.duration_min,
        "buffer_min": item.buffer_min,
        "price_cents": item.price_cents,
        "deposit_cents": item.deposit_cents,
    }
    merged.update(changes)
    if (
        merged["duration_min"] <= 0
        or merged["buffer_min"] < 0
        or merged["price_cents"] < 0
        or merged["deposit_cents"] < 0
        or merged["deposit_cents"] > merged["price_cents"]
    ):
        raise service.AdminError(
            "validation_error", "Service prices and duration are invalid.", 422
        )
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    service.audit("service", item.id, "update", {"before": before, "after": changes}, business_id)
    service.commit()
    return _data(service.serialize_service(item))


@admin_bp.post("/businesses/<int:business_id>/services/<int:service_id>/deactivate")
@login_required
@_errors
def deactivate_service(business_id, service_id):
    service.require_business(business_id)
    item = service._get_scoped(Service, service_id, business_id)
    affected = db.session.execute(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.service_id == service_id,
            Booking.start_at >= datetime.now(UTC),
            Booking.status.in_(("pending", "confirmed")),
        )
    ).scalar_one()
    before = item.active
    item.active = False
    service.audit(
        "service",
        item.id,
        "deactivate",
        {"before": {"active": before}, "after": {"active": False}},
        business_id,
    )
    service.commit()
    payload = service.serialize_service(item)
    payload["affected_future_bookings"] = affected
    return _data(payload)


@admin_bp.get("/businesses/<int:business_id>/staff")
@login_required
@_errors
def list_staff(business_id):
    service.require_business(business_id, ("owner", "staff"))
    limit, offset = _page_args()
    rows = service.page(
        select(Staff).where(Staff.business_id == business_id).order_by(Staff.id),
        limit,
        offset,
    )
    assignments = db.session.execute(
        select(staff_services.c.staff_id, staff_services.c.service_id)
        .join(Service, Service.id == staff_services.c.service_id)
        .where(
            staff_services.c.staff_id.in_([row.id for row in rows]),
            Service.business_id == business_id,
        )
    ).all()
    assigned_by_staff = {}
    for staff_id, service_id in assignments:
        assigned_by_staff.setdefault(staff_id, []).append(service_id)
    payloads = []
    for row in rows:
        payload = service.serialize_staff(row)
        payload["service_ids"] = assigned_by_staff.get(row.id, [])
        payloads.append(payload)
    return _data(payloads)


@admin_bp.post("/businesses/<int:business_id>/staff")
@login_required
@_errors
def create_staff(business_id):
    service.require_business(business_id)
    payload = _payload(StaffCreate)
    if payload.user_id is not None and db.session.get(User, payload.user_id) is None:
        raise service.AdminError("validation_error", "Linked user does not exist.", 422)
    item = Staff(business_id=business_id, **payload.model_dump())
    db.session.add(item)
    db.session.flush()
    if item.user_id is not None:
        membership = db.session.get(Membership, (item.user_id, business_id))
        if membership is None:
            db.session.add(Membership(user_id=item.user_id, business_id=business_id, role="staff"))
    service.audit("staff", item.id, "create", {"after": service.serialize_staff(item)}, business_id)
    service.commit()
    return _data(service.serialize_staff(item), 201)


@admin_bp.patch("/businesses/<int:business_id>/staff/<int:staff_id>")
@login_required
@_errors
def update_staff(business_id, staff_id):
    service.require_business(business_id)
    item = service.get_staff(staff_id, business_id)
    changes = _payload(StaffPatch).model_dump(exclude_unset=True)
    if changes.get("user_id") is not None and db.session.get(User, changes["user_id"]) is None:
        raise service.AdminError("validation_error", "Linked user does not exist.", 422)
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    if item.user_id is not None and db.session.get(Membership, (item.user_id, business_id)) is None:
        db.session.add(Membership(user_id=item.user_id, business_id=business_id, role="staff"))
    service.audit("staff", item.id, "update", {"before": before, "after": changes}, business_id)
    service.commit()
    return _data(service.serialize_staff(item))


@admin_bp.post("/businesses/<int:business_id>/staff/<int:staff_id>/deactivate")
@login_required
@_errors
def deactivate_staff(business_id, staff_id):
    service.require_business(business_id)
    item = service.get_staff(staff_id, business_id)
    affected = db.session.execute(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.staff_id == staff_id,
            Booking.start_at >= datetime.now(UTC),
            Booking.status.in_(("pending", "confirmed")),
        )
    ).scalar_one()
    item.active = False
    service.audit(
        "staff",
        item.id,
        "deactivate",
        {"before": {"active": True}, "after": {"active": False}},
        business_id,
    )
    service.commit()
    payload = service.serialize_staff(item)
    payload["affected_future_bookings"] = affected
    return _data(payload)


@admin_bp.post("/businesses/<int:business_id>/staff/<int:staff_id>/services/<int:service_id>")
@login_required
@_errors
def assign_service(business_id, staff_id, service_id):
    service.require_business(business_id)
    member = service.get_staff(staff_id, business_id)
    item = service._get_scoped(Service, service_id, business_id)
    db.session.execute(
        pg_insert(staff_services)
        .values(staff_id=member.id, service_id=item.id)
        .on_conflict_do_nothing()
    )
    service.audit("staff_service", member.id, "assign", {"service_id": item.id}, business_id)
    service.commit()
    return _data({"staff_id": member.id, "service_id": item.id})


@admin_bp.delete("/businesses/<int:business_id>/staff/<int:staff_id>/services/<int:service_id>")
@login_required
@_errors
def unassign_service(business_id, staff_id, service_id):
    service.require_business(business_id)
    member = service.get_staff(staff_id, business_id)
    item = service._get_scoped(Service, service_id, business_id)
    db.session.execute(
        delete(staff_services).where(
            staff_services.c.staff_id == member.id, staff_services.c.service_id == item.id
        )
    )
    service.audit("staff_service", member.id, "unassign", {"service_id": item.id}, business_id)
    service.commit()
    return _data({"staff_id": member.id, "service_id": item.id})


@admin_bp.get("/businesses/<int:business_id>/staff/<int:staff_id>/working-hours")
@login_required
@_errors
def get_hours(business_id, staff_id):
    service.require_business(business_id, ("owner", "staff"))
    service.get_staff(staff_id, business_id)
    rows = (
        db.session.execute(
            select(WorkingHours)
            .where(WorkingHours.staff_id == staff_id)
            .order_by(WorkingHours.weekday, WorkingHours.start_time)
        )
        .scalars()
        .all()
    )
    return _data(
        [
            {
                "id": row.id,
                "weekday": row.weekday,
                "start_time": row.start_time.isoformat(),
                "end_time": row.end_time.isoformat(),
            }
            for row in rows
        ]
    )


@admin_bp.put("/businesses/<int:business_id>/staff/<int:staff_id>/working-hours")
@login_required
@_errors
def replace_hours(business_id, staff_id):
    service.require_business(business_id)
    service.get_staff(staff_id, business_id)
    payload = _payload(HoursReplace)
    schedule = sorted(payload.hours, key=lambda x: (x.weekday, x.start_time))
    for earlier, later in zip(schedule, schedule[1:], strict=False):
        if earlier.weekday == later.weekday and later.start_time < earlier.end_time:
            raise service.AdminError("validation_error", "Working-hour ranges cannot overlap.", 422)
    old = (
        db.session.execute(select(WorkingHours).where(WorkingHours.staff_id == staff_id))
        .scalars()
        .all()
    )
    before = [
        {
            "weekday": x.weekday,
            "start_time": x.start_time.isoformat(),
            "end_time": x.end_time.isoformat(),
        }
        for x in old
    ]
    try:
        db.session.execute(delete(WorkingHours).where(WorkingHours.staff_id == staff_id))
        db.session.add_all(
            [
                WorkingHours(
                    staff_id=staff_id,
                    weekday=x.weekday,
                    start_time=x.start_time,
                    end_time=x.end_time,
                )
                for x in schedule
            ]
        )
        service.audit(
            "working_hours",
            staff_id,
            "replace",
            {"before": before, "after": [x.model_dump(mode="json") for x in schedule]},
            business_id,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return get_hours(business_id, staff_id)


@admin_bp.get("/businesses/<int:business_id>/staff/<int:staff_id>/time-off")
@login_required
@_errors
def list_time_off(business_id, staff_id):
    service.require_business(business_id, ("owner", "staff"))
    member = service.get_staff(staff_id, business_id)
    membership = db.session.get(Membership, (g.current_user.id, business_id))
    if membership.role != "owner":
        service.staff_time_off(member, g.current_user.id)
    limit, offset = _page_args()
    rows = (
        db.session.execute(
            select(TimeOff)
            .where(TimeOff.staff_id == staff_id)
            .order_by(TimeOff.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return _data(
        [
            {
                "id": x.id,
                "start_at": x.during.lower.isoformat(),
                "end_at": x.during.upper.isoformat(),
                "reason": x.reason,
            }
            for x in rows
        ]
    )


@admin_bp.post("/businesses/<int:business_id>/staff/<int:staff_id>/time-off")
@login_required
@_errors
def create_time_off(business_id, staff_id):
    service.require_business(business_id, ("owner", "staff"))
    member = service.get_staff(staff_id, business_id)
    membership = db.session.get(Membership, (g.current_user.id, business_id))
    if membership.role != "owner":
        service.staff_time_off(member, g.current_user.id)
    payload = _payload(TimeOffCreate)
    item = TimeOff(
        staff_id=staff_id,
        during=Range(payload.start_at.astimezone(UTC), payload.end_at.astimezone(UTC), "[)"),
        reason=payload.reason,
    )
    db.session.add(item)
    db.session.flush()
    service.audit(
        "time_off",
        item.id,
        "create",
        {
            "start_at": item.during.lower.isoformat(),
            "end_at": item.during.upper.isoformat(),
            "reason": item.reason,
        },
        business_id,
    )
    service.commit()
    return _data(
        {
            "id": item.id,
            "start_at": item.during.lower.isoformat(),
            "end_at": item.during.upper.isoformat(),
            "reason": item.reason,
        },
        201,
    )


@admin_bp.delete("/businesses/<int:business_id>/staff/<int:staff_id>/time-off/<int:time_off_id>")
@login_required
@_errors
def delete_time_off(business_id, staff_id, time_off_id):
    service.require_business(business_id, ("owner", "staff"))
    member = service.get_staff(staff_id, business_id)
    membership = db.session.get(Membership, (g.current_user.id, business_id))
    if membership.role != "owner":
        service.staff_time_off(member, g.current_user.id)
    item = db.session.get(TimeOff, time_off_id)
    if item is None or item.staff_id != staff_id:
        raise service.AdminError("not_found", "Resource not found.", 404)
    db.session.delete(item)
    service.audit(
        "time_off", time_off_id, "delete", {"before": {"staff_id": staff_id}}, business_id
    )
    service.commit()
    return _data({"deleted": True})


public_bp = Blueprint("public_catalog", __name__, url_prefix="/api/b")


@public_bp.errorhandler(service.AdminError)
def _public_error(error):
    return jsonify({"error": {"code": error.code, "message": error.message}}), error.status


@public_bp.get("/<slug>/services")
def public_services(slug):
    business = db.session.execute(
        select(Business).where(Business.slug == slug)
    ).scalar_one_or_none()
    if business is None:
        raise service.AdminError("not_found", "Resource not found.", 404)
    rows = (
        db.session.execute(
            select(Service)
            .where(Service.business_id == business.id, Service.active.is_(True))
            .order_by(Service.id)
        )
        .scalars()
        .all()
    )
    return _data([service.serialize_service(row) for row in rows])


@public_bp.get("/<slug>")
@limiter.limit(lambda: current_app.config["PUBLIC_AVAILABILITY_RATE_LIMIT"])
def public_business(slug):
    business = db.session.execute(
        select(Business).where(Business.slug == slug)
    ).scalar_one_or_none()
    if business is None:
        raise service.AdminError("not_found", "Resource not found.", 404)
    return _data({"name": business.name, "slug": business.slug, "timezone": business.timezone})


@public_bp.get("/<slug>/staff")
def public_staff(slug):
    business = db.session.execute(
        select(Business).where(Business.slug == slug)
    ).scalar_one_or_none()
    if business is None:
        raise service.AdminError("not_found", "Resource not found.", 404)
    rows = (
        db.session.execute(
            select(Staff)
            .where(Staff.business_id == business.id, Staff.active.is_(True))
            .order_by(Staff.id)
        )
        .scalars()
        .all()
    )
    return _data([service.serialize_staff(row) for row in rows])
