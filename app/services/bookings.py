"""Booking creation, rescheduling, ownership queries, and hold expiry."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AuditLog, Booking, Business, Service, Staff, User, staff_services
from app.services.availability import AvailabilityError, load_availability_range
from app.services.booking_state import InvalidTransition, transition


class BookingError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


SLOT_TAKEN_MESSAGE = "That time was just booked. Pick another slot."


def _z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def serialize_booking(booking: Booking) -> dict[str, object]:
    return {
        "id": booking.id,
        "business_id": booking.business_id,
        "customer_id": booking.customer_id,
        "staff_id": booking.staff_id,
        "service_id": booking.service_id,
        "start_at": _z(booking.start_at),
        "end_at": _z(booking.end_at),
        "blocked_until": _z(booking.blocked_until),
        "status": booking.status,
        "hold_expires_at": _z(booking.hold_expires_at) if booking.hold_expires_at else None,
        "price_cents": booking.price_cents,
        "deposit_cents": booking.deposit_cents,
    }


def _iso(value: datetime) -> str:
    return _z(value)


def _slot_staff(by_staff: dict[str, list[dict[str, str]]], start_at: datetime) -> list[int]:
    wanted = _iso(start_at)
    return [
        int(staff_id)
        for staff_id, slots in by_staff.items()
        if any(slot["start_at"] == wanted for slot in slots)
    ]


def _business(slug: str) -> Business:
    item = db.session.execute(select(Business).where(Business.slug == slug)).scalar_one_or_none()
    if item is None:
        raise BookingError("not_found", "Business not found.", 404)
    return item


def _availability(
    business: Business,
    service: Service,
    start_at: datetime,
    now: datetime,
    staff_id: int | None,
    exclude_booking_id: int | None = None,
    ignore_bookings: bool = False,
):
    day = start_at.astimezone(ZoneInfo(business.timezone)).date()
    config = current_app.config
    try:
        return load_availability_range(
            business_slug=business.slug,
            service_id=service.id,
            from_date=day,
            to_date=day,
            now=now,
            staff_id=staff_id,
            exclude_booking_id=exclude_booking_id,
            ignore_bookings=ignore_bookings,
            minimum_notice=timedelta(minutes=config["AVAILABILITY_MINIMUM_NOTICE_MINUTES"]),
            maximum_advance_days=config["AVAILABILITY_MAXIMUM_ADVANCE_DAYS"],
        )[1][day]
    except AvailabilityError as exc:
        raise BookingError(exc.code, exc.message, exc.status) from exc


def _active_staff_ids(business_id: int, service_id: int, requested_staff: int | None):
    query = (
        select(Staff.id)
        .join(staff_services, staff_services.c.staff_id == Staff.id)
        .where(
            Staff.business_id == business_id,
            Staff.active.is_(True),
            staff_services.c.service_id == service_id,
        )
        .order_by(Staff.id)
    )
    if requested_staff is not None:
        selected = db.session.execute(
            select(Staff.id, Staff.active).where(
                Staff.id == requested_staff,
                Staff.business_id == business_id,
            )
        ).one_or_none()
        if selected is None:
            raise BookingError("not_found", "Staff member not found.", 404)
        if not selected.active:
            raise BookingError("not_available", "That time is not available.", 422)
        query = query.where(Staff.id == requested_staff)
    return list(db.session.execute(query).scalars())


def _active_booking_filter(now: datetime):
    return or_(
        Booking.status == "confirmed",
        and_(Booking.status == "pending", Booking.hold_expires_at > now),
    )


def _retry_booking(user_id: int, business_id: int, service_id: int, staff_ids, start_at, now):
    if not staff_ids:
        return None
    return db.session.execute(
        select(Booking)
        .where(
            Booking.business_id == business_id,
            Booking.customer_id == user_id,
            Booking.service_id == service_id,
            Booking.staff_id.in_(staff_ids),
            Booking.start_at == start_at,
            _active_booking_filter(now),
        )
        .order_by(Booking.id)
        .limit(1)
    ).scalar_one_or_none()


def _has_active_conflict(
    business_id: int,
    staff_ids: list[int],
    start_at: datetime,
    blocked_until: datetime,
    now: datetime,
    exclude_booking_id: int | None = None,
) -> bool:
    if not staff_ids:
        return False
    query = select(Booking.id).where(
        Booking.business_id == business_id,
        Booking.staff_id.in_(staff_ids),
        _active_booking_filter(now),
        Booking.start_at < blocked_until,
        Booking.blocked_until > start_at,
    )
    if exclude_booking_id is not None:
        query = query.where(Booking.id != exclude_booking_id)
    return db.session.execute(query.limit(1)).scalar_one_or_none() is not None


def _ordered_available_staff(business: Business, staff_ids: list[int], start_at: datetime):
    zone = ZoneInfo(business.timezone)
    local_day = start_at.astimezone(zone).date()
    day_start = datetime.combine(local_day, time.min, tzinfo=zone).astimezone(UTC)
    day_end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    counts = dict(
        db.session.execute(
            select(Booking.staff_id, func.count(Booking.id))
            .where(
                Booking.business_id == business.id,
                Booking.staff_id.in_(staff_ids),
                Booking.start_at >= day_start,
                Booking.start_at < day_end,
                or_(
                    Booking.status.in_(("confirmed", "completed", "no_show")),
                    and_(Booking.status == "pending", Booking.hold_expires_at > datetime.now(UTC)),
                ),
            )
            .group_by(Booking.staff_id)
        ).all()
    )
    return sorted(staff_ids, key=lambda member_id: (counts.get(member_id, 0), member_id))


def _cancel_expired_overlaps(
    business_id: int, staff_id: int, start_at: datetime, blocked_until: datetime, now: datetime
) -> None:
    expired = (
        db.session.execute(
            select(Booking)
            .where(
                Booking.business_id == business_id,
                Booking.staff_id == staff_id,
                Booking.status == "pending",
                Booking.hold_expires_at <= now,
                Booking.start_at < blocked_until,
                Booking.blocked_until > start_at,
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for booking in expired:
        transition(booking, "cancelled", None)


def create_booking(
    user: User,
    slug: str,
    service_id: int,
    requested_staff: int | None,
    start_at: datetime,
    *,
    now: datetime | None = None,
) -> tuple[Booking, bool]:
    """Commit a booking atomically; return (booking, was_idempotent_retry)."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        business = _business(slug)
        offering = db.session.execute(
            select(Service).where(
                Service.id == service_id,
                Service.business_id == business.id,
                Service.active.is_(True),
            )
        ).scalar_one_or_none()
        if offering is None:
            raise BookingError("not_found", "Service not found.", 404)
        eligible_ids = _active_staff_ids(business.id, offering.id, requested_staff)
        by_staff = _availability(business, offering, start_at, now, requested_staff)
        end_at = start_at + timedelta(minutes=offering.duration_min)
        blocked_until = end_at + timedelta(minutes=offering.buffer_min)

        retry = _retry_booking(user.id, business.id, offering.id, eligible_ids, start_at, now)
        if retry is not None:
            return retry, True

        candidate_ids = _slot_staff(by_staff, start_at)
        if requested_staff is not None:
            candidate_ids = [item for item in candidate_ids if item == requested_staff]
        if not candidate_ids:
            potential = _availability(
                business, offering, start_at, now, requested_staff, ignore_bookings=True
            )
            potential_ids = _slot_staff(potential, start_at)
            if _has_active_conflict(business.id, potential_ids, start_at, blocked_until, now):
                raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409)
            raise BookingError("not_available", "That time is not available.", 422)
        ordered_ids = _ordered_available_staff(business, candidate_ids, start_at)

        for member_id in ordered_ids:
            _cancel_expired_overlaps(business.id, member_id, start_at, blocked_until, now)
            if offering.deposit_cents > 0:
                active_holds = db.session.execute(
                    select(func.count(Booking.id)).where(
                        Booking.customer_id == user.id,
                        Booking.status == "pending",
                        Booking.hold_expires_at > now,
                    )
                ).scalar_one()
                if active_holds >= current_app.config["MAX_PENDING_HOLDS_PER_USER"]:
                    raise BookingError(
                        "too_many_holds",
                        "You have reached the maximum number of active holds.",
                        422,
                    )

            booking = Booking(
                business_id=business.id,
                customer_id=user.id,
                staff_id=member_id,
                service_id=offering.id,
                start_at=start_at,
                end_at=end_at,
                blocked_until=blocked_until,
                status=None,
                hold_expires_at=(
                    now + timedelta(minutes=current_app.config["HOLD_MINUTES"])
                    if offering.deposit_cents > 0
                    else None
                ),
                price_cents=offering.price_cents,
                deposit_cents=offering.deposit_cents,
            )
            status = "pending" if offering.deposit_cents > 0 else "confirmed"
            savepoint = db.session.begin_nested()
            try:
                transition(booking, status, user)
                savepoint.commit()
                db.session.commit()
                return booking, False
            except IntegrityError as exc:
                savepoint.rollback()
                sqlstate = getattr(exc.orig, "sqlstate", None)
                if sqlstate != "23P01":
                    raise
        raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409)
    except (BookingError, InvalidTransition):
        db.session.rollback()
        raise
    except IntegrityError as exc:
        db.session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23P01":
            raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409) from exc
        raise


def reschedule_booking(
    booking: Booking,
    user: User,
    requested_staff: int | None,
    start_at: datetime,
    *,
    now: datetime | None = None,
) -> Booking:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        business = db.session.get(Business, booking.business_id)
        offering = db.session.execute(
            select(Service).where(
                Service.id == booking.service_id,
                Service.business_id == booking.business_id,
                Service.active.is_(True),
            )
        ).scalar_one_or_none()
        if business is None or offering is None:
            raise BookingError("not_available", "That time is not available.", 422)
        by_staff = _availability(
            business, offering, start_at, now, requested_staff, exclude_booking_id=booking.id
        )
        eligible_ids = _active_staff_ids(booking.business_id, offering.id, requested_staff)
        candidate_ids = _slot_staff(by_staff, start_at)
        if requested_staff is not None:
            candidate_ids = [item for item in candidate_ids if item == requested_staff]
        candidate_ids = [item for item in candidate_ids if item in eligible_ids]
        if not candidate_ids:
            end_at = start_at + timedelta(minutes=offering.duration_min)
            blocked_until = end_at + timedelta(minutes=offering.buffer_min)
            potential = _availability(
                business,
                offering,
                start_at,
                now,
                requested_staff,
                exclude_booking_id=booking.id,
                ignore_bookings=True,
            )
            potential_ids = [
                staff for staff in _slot_staff(potential, start_at) if staff in eligible_ids
            ]
            if _has_active_conflict(
                booking.business_id,
                potential_ids,
                start_at,
                blocked_until,
                now,
                exclude_booking_id=booking.id,
            ):
                raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409)
            raise BookingError("not_available", "That time is not available.", 422)

        ordered_ids = _ordered_available_staff(business, candidate_ids, start_at)
        end_at = start_at + timedelta(minutes=offering.duration_min)
        blocked_until = end_at + timedelta(minutes=offering.buffer_min)
        for member_id in ordered_ids:
            savepoint = db.session.begin_nested()
            before = {
                "staff_id": booking.staff_id,
                "start_at": _z(booking.start_at),
                "end_at": _z(booking.end_at),
                "blocked_until": _z(booking.blocked_until),
            }
            try:
                booking.staff_id = member_id
                booking.start_at = start_at
                booking.end_at = end_at
                booking.blocked_until = blocked_until
                db.session.flush()
                db.session.add(
                    AuditLog(
                        actor_id=user.id,
                        business_id=booking.business_id,
                        entity="booking",
                        entity_id=booking.id,
                        action="reschedule",
                        diff={
                            "before": before,
                            "after": {
                                "staff_id": member_id,
                                "start_at": _z(start_at),
                                "end_at": _z(end_at),
                                "blocked_until": _z(blocked_until),
                            },
                        },
                    )
                )
                from app.services.outbox import reschedule_reminders

                reschedule_reminders(booking)
                savepoint.commit()
                db.session.commit()
                return booking
            except IntegrityError as exc:
                savepoint.rollback()
                if getattr(exc.orig, "sqlstate", None) != "23P01":
                    raise
        raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409)
    except BookingError:
        db.session.rollback()
        raise
    except IntegrityError as exc:
        db.session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23P01":
            raise BookingError("slot_taken", SLOT_TAKEN_MESSAGE, 409) from exc
        raise


def expire_holds(now: datetime) -> int:
    """Cancel all pending holds whose expiry has passed and return their count."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    try:
        expired = (
            db.session.execute(
                select(Booking)
                .where(Booking.status == "pending", Booking.hold_expires_at <= now)
                .order_by(Booking.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for booking in expired:
            transition(booking, "cancelled", None)
        db.session.commit()
        return len(expired)
    except Exception:
        db.session.rollback()
        raise
