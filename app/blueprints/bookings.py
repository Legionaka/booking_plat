"""Customer booking creation and lifecycle endpoints."""

from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from pydantic import ValidationError
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import Booking, Business, Membership, Payment, Service, Staff, User
from app.schemas.booking import BookingAction, BookingCreate
from app.security import login_required
from app.services import bookings as service
from app.services.booking_state import InvalidTransition, transition

booking_bp = Blueprint("bookings", __name__)
LATE_CANCEL_CODE = "late_cancellation"


def _errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except service.BookingError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status
        except InvalidTransition as exc:
            db.session.rollback()
            return jsonify({"error": {"code": "invalid_transition", "message": str(exc)}}), 409

    return wrapped


def _validated(model):
    try:
        return model.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise service.BookingError("validation_error", "Request body is invalid.", 422) from exc


def _page_args():
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError
        return limit, offset
    except ValueError as exc:
        raise service.BookingError("validation_error", "Invalid pagination values.", 422) from exc


def _data(value, status=200):
    return jsonify({"data": value}), status


def _db_booking(booking_id: int, lock: bool = False) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    if lock:
        query = query.with_for_update()
    booking = db.session.execute(query).scalar_one_or_none()
    if booking is None:
        raise service.BookingError("not_found", "Booking not found.", 404)
    return booking


def _access(booking: Booking, user_id: int) -> tuple[str, Staff | None]:
    membership = db.session.get(Membership, (user_id, booking.business_id))
    if membership is not None and membership.role == "owner":
        return "owner", None
    if membership is not None and membership.role == "staff":
        member = db.session.execute(
            select(Staff).where(
                Staff.business_id == booking.business_id,
                Staff.user_id == user_id,
                Staff.id == booking.staff_id,
            )
        ).scalar_one_or_none()
        if member is not None:
            return "staff", member
    if booking.customer_id == user_id:
        return "customer", None
    if membership is None:
        raise service.BookingError("not_found", "Booking not found.", 404)
    raise service.BookingError("not_found", "Booking not found.", 404)


def _customer_business_cutoff(booking: Booking, role: str):
    if role != "customer":
        return
    business = db.session.get(Business, booking.business_id)
    now = datetime.now(UTC)
    cutoff = business.cancel_cutoff_hours
    if booking.start_at - now < timedelta(hours=cutoff):
        raise service.BookingError(
            LATE_CANCEL_CODE,
            (
                f"This booking starts in under {cutoff} hours, "
                "so it can't be cancelled online. Contact the business to change it."
            ),
            403,
        )


@booking_bp.post("/api/b/<slug>/bookings")
@limiter.limit(lambda: current_app.config["BOOKING_CREATE_RATE_LIMIT"])
@_errors
@login_required
def create_booking(slug):
    if g.current_user.verified_at is None:
        raise service.BookingError("email_not_verified", "Verify your email before booking.", 403)
    payload = _validated(BookingCreate)
    booking, retried = service.create_booking(
        g.current_user,
        slug,
        payload.service_id,
        None if payload.staff_id == "any" else payload.staff_id,
        payload.start_at.astimezone(UTC),
    )
    return _data(service.serialize_booking(booking), 200 if retried else 201)


@booking_bp.patch("/api/bookings/<int:booking_id>")
@_errors
@login_required
def update_booking(booking_id):
    payload = _validated(BookingAction)
    booking = _db_booking(booking_id, lock=True)
    role, member = _access(booking, g.current_user.id)
    now = datetime.now(UTC)

    if payload.action == "cancel":
        if role == "customer":
            _customer_business_cutoff(booking, role)
        transition(booking, "cancelled", g.current_user)
        db.session.commit()
        return _data(service.serialize_booking(booking))

    if payload.action == "reschedule":
        if role == "customer":
            _customer_business_cutoff(booking, role)
        if booking.status not in {"pending", "confirmed"}:
            raise service.BookingError(
                "invalid_transition", "Only active bookings can be rescheduled.", 409
            )
        staff_id = payload.staff_id
        if role == "staff":
            if staff_id not in (None, "any", member.id):
                raise service.BookingError("not_found", "Booking not found.", 404)
            staff_id = member.id
        elif staff_id in (None, "any"):
            staff_id = booking.staff_id
        updated = service.reschedule_booking(
            booking, g.current_user, staff_id, payload.start_at.astimezone(UTC), now=now
        )
        return _data(service.serialize_booking(updated))

    status_for_action = {
        "confirm": "confirmed",
        "complete": "completed",
        "no_show": "no_show",
    }
    if role == "customer":
        raise service.BookingError("forbidden", "Only business staff can perform this action.", 403)
    if payload.action == "confirm" and booking.status == "pending":
        if booking.hold_expires_at is not None and booking.hold_expires_at <= now:
            raise service.BookingError("invalid_transition", "This payment hold has expired.", 409)
    transition(booking, status_for_action[payload.action], g.current_user)
    if payload.action == "confirm":
        booking.hold_expires_at = None
    db.session.commit()
    return _data(service.serialize_booking(booking))


def _customer_list(user_id: int):
    limit, offset = _page_args()
    query = select(Booking).where(Booking.customer_id == user_id)
    filter_value = request.args.get("filter")
    now = datetime.now(UTC)
    if filter_value == "upcoming":
        query = query.where(Booking.start_at >= now)
    elif filter_value == "past":
        query = query.where(Booking.start_at < now)
    elif filter_value not in (None, ""):
        raise service.BookingError("validation_error", "Filter must be upcoming or past.", 422)
    rows = (
        db.session.execute(query.order_by(Booking.start_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    business_ids = {row.business_id for row in rows}
    businesses = {
        row.id: row
        for row in db.session.execute(
            select(Business).where(Business.id.in_(business_ids))
        ).scalars()
    }
    services = {
        (row.business_id, row.id): row
        for row in db.session.execute(
            select(Service).where(Service.business_id.in_(business_ids))
        ).scalars()
    }
    staff_members = {
        (row.business_id, row.id): row
        for row in db.session.execute(
            select(Staff).where(Staff.business_id.in_(business_ids))
        ).scalars()
    }
    payloads = []
    for row in rows:
        business = businesses[row.business_id]
        service_row = services[(row.business_id, row.service_id)]
        staff = staff_members[(row.business_id, row.staff_id)]
        payload = service.serialize_booking(row)
        payload.update(
            {
                "business_slug": business.slug,
                "business_name": business.name,
                "business_timezone": business.timezone,
                "cancel_cutoff_hours": business.cancel_cutoff_hours,
                "service_name": service_row.name,
                "service_duration_min": service_row.duration_min,
                "staff_name": staff.display_name,
            }
        )
        payloads.append(payload)
    return _data(payloads)


@booking_bp.get("/api/me/bookings")
@_errors
@login_required
def my_bookings():
    return _customer_list(g.current_user.id)


@booking_bp.get("/api/me/bookings/<int:booking_id>")
@_errors
@login_required
def my_booking(booking_id):
    booking = db.session.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.customer_id == g.current_user.id,
        )
    ).scalar_one_or_none()
    if booking is None:
        raise service.BookingError("not_found", "Booking not found.", 404)
    payload = service.serialize_booking(booking)
    business = db.session.execute(
        select(Business).where(Business.id == booking.business_id)
    ).scalar_one()
    staff = db.session.execute(
        select(Staff).where(Staff.id == booking.staff_id, Staff.business_id == booking.business_id)
    ).scalar_one()
    service_row = db.session.execute(
        select(Service).where(
            Service.id == booking.service_id,
            Service.business_id == booking.business_id,
        )
    ).scalar_one()
    payload.update(
        {
            "business_slug": business.slug,
            "business_name": business.name,
            "business_timezone": business.timezone,
            "cancel_cutoff_hours": business.cancel_cutoff_hours,
            "staff_name": staff.display_name,
            "service_name": service_row.name,
            "service_duration_min": service_row.duration_min,
        }
    )
    payload["payment_status"] = db.session.execute(
        select(Payment.status)
        .where(Payment.booking_id == booking.id, Payment.provider == "payfast")
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _data(payload)


@booking_bp.get("/api/admin/businesses/<int:business_id>/bookings")
@_errors
@login_required
def admin_bookings(business_id):
    user_id = g.current_user.id
    business = db.session.get(Business, business_id)
    membership = db.session.get(Membership, (user_id, business_id))
    if business is None or membership is None:
        raise service.BookingError("not_found", "Business not found.", 404)
    query = select(Booking).where(Booking.business_id == business_id)
    if membership.role == "staff":
        own_staff = (
            db.session.execute(
                select(Staff.id).where(Staff.business_id == business_id, Staff.user_id == user_id)
            )
            .scalars()
            .all()
        )
        if not own_staff:
            raise service.BookingError("not_found", "Business not found.", 404)
        query = query.where(Booking.staff_id.in_(own_staff))
    if request.args.get("staff"):
        try:
            staff_id = int(request.args["staff"])
        except ValueError as exc:
            raise service.BookingError("validation_error", "Invalid staff filter.", 422) from exc
        exists = db.session.execute(
            select(Staff.id).where(Staff.id == staff_id, Staff.business_id == business_id)
        ).scalar_one_or_none()
        if exists is None:
            raise service.BookingError("not_found", "Staff member not found.", 404)
        if membership.role == "staff" and staff_id not in own_staff:
            raise service.BookingError("not_found", "Staff member not found.", 404)
        query = query.where(Booking.staff_id == staff_id)
    if request.args.get("status"):
        status = request.args["status"]
        if status not in {"pending", "confirmed", "cancelled", "completed", "no_show"}:
            raise service.BookingError("validation_error", "Invalid status filter.", 422)
        query = query.where(Booking.status == status)
    for key, operator in (("from", ">="), ("to", "<=")):
        value = request.args.get(key)
        if value:
            try:
                bound = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if bound.tzinfo is None or bound.utcoffset() is None:
                    raise ValueError
            except ValueError as exc:
                raise service.BookingError(
                    "validation_error", f"'{key}' must be an ISO 8601 timestamp with timezone.", 422
                ) from exc
            query = query.where(
                Booking.start_at >= bound if operator == ">=" else Booking.start_at <= bound
            )
    limit, offset = _page_args()
    rows = db.session.execute(
        query.join(User, User.id == Booking.customer_id)
        .join(Service, (Service.id == Booking.service_id) & (Service.business_id == business_id))
        .join(Staff, (Staff.id == Booking.staff_id) & (Staff.business_id == business_id))
        .add_columns(User.full_name, Service.name, Staff.display_name)
        .order_by(Booking.start_at)
        .limit(limit)
        .offset(offset)
    ).all()
    payloads = []
    for booking, customer_name, service_name, staff_name in rows:
        payload = service.serialize_booking(booking)
        payload.update(
            {
                "customer_name": customer_name,
                "service_name": service_name,
                "staff_name": staff_name,
            }
        )
        payloads.append(payload)
    return _data(payloads)
