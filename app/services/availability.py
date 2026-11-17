"""Pure slot calculation plus a batched PostgreSQL loader."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.range import Range
from sqlalchemy import and_, or_, select

from app.extensions import db
from app.models import Booking, Business, Service, Staff, TimeOff, WorkingHours, staff_services


@dataclass(frozen=True)
class BookingBlock:
    start_at: datetime
    blocked_until: datetime
    status: str
    hold_expires_at: datetime | None = None


@dataclass(frozen=True)
class AvailabilityError(Exception):
    code: str
    message: str
    status: int


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _merge(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[list[datetime]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(item[0], item[1]) for item in merged]


def _subtract(
    start: datetime, end: datetime, blocked: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    free: list[tuple[datetime, datetime]] = []
    cursor = start
    for block_start, block_end in _merge(blocked):
        if block_end <= cursor or block_start >= end:
            continue
        if block_start > cursor:
            free.append((cursor, min(block_start, end)))
        cursor = max(cursor, block_end)
        if cursor >= end:
            break
    if cursor < end:
        free.append((cursor, end))
    return free


def slots_for_day(
    *,
    business_timezone: str,
    day: date,
    slot_step_min: int,
    service_duration_min: int,
    service_buffer_min: int,
    working_hours: Mapping[int, Iterable[tuple[time, time]]],
    time_off: Iterable[tuple[datetime, datetime]],
    blocking_bookings: Iterable[BookingBlock],
    now: datetime,
    minimum_notice: timedelta,
    maximum_advance_days: int,
) -> list[dict[str, str]]:
    """Calculate UTC candidate starts from business-local hours and plain input data."""
    _require_aware(now, "now")
    if slot_step_min <= 0 or service_duration_min <= 0 or service_buffer_min < 0:
        raise ValueError("Slot step and duration must be positive; buffer cannot be negative")
    if maximum_advance_days < 0 or minimum_notice < timedelta(0):
        raise ValueError("Availability limits cannot be negative")

    zone = ZoneInfo(business_timezone)
    now_utc = now.astimezone(UTC)
    earliest = now_utc + minimum_notice
    latest = now_utc + timedelta(days=maximum_advance_days)
    occupancy = []
    for start, end in time_off:
        _require_aware(start, "time_off.start")
        _require_aware(end, "time_off.end")
        occupancy.append((start.astimezone(UTC), end.astimezone(UTC)))
    for booking in blocking_bookings:
        _require_aware(booking.start_at, "booking.start_at")
        _require_aware(booking.blocked_until, "booking.blocked_until")
        if booking.hold_expires_at is not None:
            _require_aware(booking.hold_expires_at, "booking.hold_expires_at")
        blocks = booking.status == "confirmed" or (
            booking.status == "pending"
            and booking.hold_expires_at is not None
            and booking.hold_expires_at > now
        )
        if blocks:
            occupancy.append(
                (booking.start_at.astimezone(UTC), booking.blocked_until.astimezone(UTC))
            )

    duration = timedelta(minutes=service_duration_min + service_buffer_min)
    step = timedelta(minutes=slot_step_min)
    results: list[dict[str, str]] = []
    for local_start_time, local_end_time in working_hours.get(day.weekday(), ()):
        # Attach the zone before converting: each wall-clock boundary is interpreted in the
        # business timezone, then all interval arithmetic runs on the UTC timeline.
        window_start_local = datetime.combine(day, local_start_time, tzinfo=zone)
        window_end_day = day + timedelta(days=1) if local_end_time <= local_start_time else day
        window_end_local = datetime.combine(window_end_day, local_end_time, tzinfo=zone)
        window_start = window_start_local.astimezone(UTC)
        window_end = window_end_local.astimezone(UTC)
        if window_end <= window_start:
            continue
        for free_start, free_end in _subtract(window_start, window_end, occupancy):
            elapsed = max(timedelta(0), free_start - window_start)
            grid_index = (elapsed + step - timedelta(microseconds=1)) // step
            candidate = window_start + grid_index * step
            while candidate + duration <= free_end:
                if earliest <= candidate <= latest:
                    local_candidate = candidate.astimezone(zone)
                    results.append(
                        {
                            "start_at": candidate.isoformat().replace("+00:00", "Z"),
                            "end_at": (candidate + timedelta(minutes=service_duration_min))
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "local_start": local_candidate.strftime("%H:%M"),
                        }
                    )
                candidate += step
    results.sort(key=lambda item: item["start_at"])
    return results


def merge_staff_slots(
    slots_by_staff: Mapping[str, Iterable[dict[str, str]]],
) -> list[dict[str, object]]:
    """Merge equal starts and retain the IDs of every staff member who can take them."""
    merged: dict[str, dict[str, object]] = {}
    for staff_id, slots in slots_by_staff.items():
        for slot in slots:
            start = slot["start_at"]
            if start not in merged:
                merged[start] = {
                    "start_at": start,
                    "end_at": slot["end_at"],
                    "local_start": slot["local_start"],
                    "staff_ids": [],
                }
            merged[start]["staff_ids"].append(int(staff_id))
    return [merged[start] for start in sorted(merged)]


def _as_utc(value: datetime) -> datetime:
    _require_aware(value, "datetime")
    return value.astimezone(UTC)


def load_availability_range(
    *,
    business_slug: str,
    service_id: int,
    from_date: date,
    to_date: date,
    now: datetime,
    staff_id: int | None = None,
    exclude_booking_id: int | None = None,
    ignore_bookings: bool = False,
    minimum_notice: timedelta = timedelta(hours=2),
    maximum_advance_days: int = 60,
) -> tuple[str, dict[date, dict[str, list[dict[str, str]]]]]:
    """Load all matching schedule/occupancy rows in a fixed number of queries."""
    _require_aware(now, "now")
    business = db.session.execute(
        select(Business).where(Business.slug == business_slug)
    ).scalar_one_or_none()
    if business is None:
        raise AvailabilityError("not_found", "Business not found.", 404)
    offering = db.session.execute(
        select(Service)
        .where(
            Service.id == service_id,
            Service.business_id == business.id,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if offering is None:
        raise AvailabilityError("not_found", "Service not found.", 404)
    if not offering.active:
        return business.timezone, {day: {} for day in _days(from_date, to_date)}

    staff_query = (
        select(Staff)
        .join(staff_services, staff_services.c.staff_id == Staff.id)
        .where(
            Staff.business_id == business.id,
            Staff.active.is_(True),
            staff_services.c.service_id == offering.id,
        )
        .order_by(Staff.id)
    )
    if staff_id is not None:
        selected_staff = db.session.execute(
            select(Staff)
            .where(Staff.id == staff_id, Staff.business_id == business.id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if selected_staff is None:
            raise AvailabilityError("not_found", "Staff member not found.", 404)
        if selected_staff.active:
            offers_service = db.session.execute(
                select(staff_services.c.staff_id).where(
                    staff_services.c.staff_id == staff_id,
                    staff_services.c.service_id == offering.id,
                )
            ).scalar_one_or_none()
            if offers_service is None:
                raise AvailabilityError(
                    "service_not_offered", "This staff member does not offer the service.", 422
                )
        else:
            return business.timezone, {day: {} for day in _days(from_date, to_date)}
        staff_query = staff_query.where(Staff.id == staff_id)
    staff_rows = db.session.execute(staff_query).scalars().all()
    days = _days(from_date, to_date)
    if not staff_rows or not days:
        return business.timezone, {day: {} for day in days}

    zone = ZoneInfo(business.timezone)
    range_start = datetime.combine(from_date, time.min, tzinfo=zone).astimezone(UTC)
    range_end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    ids = [item.id for item in staff_rows]
    hours_rows = (
        db.session.execute(
            select(WorkingHours)
            .join(Staff, Staff.id == WorkingHours.staff_id)
            .where(Staff.business_id == business.id, WorkingHours.staff_id.in_(ids))
        )
        .scalars()
        .all()
    )
    hours_by_staff: dict[int, dict[int, list[tuple[time, time]]]] = {
        item.id: {} for item in staff_rows
    }
    for row in hours_rows:
        hours_by_staff[row.staff_id].setdefault(row.weekday, []).append(
            (row.start_time, row.end_time)
        )

    time_off_rows = (
        db.session.execute(
            select(TimeOff)
            .join(Staff, Staff.id == TimeOff.staff_id)
            .where(
                Staff.business_id == business.id,
                TimeOff.staff_id.in_(ids),
                TimeOff.during.op("&&")(Range(range_start, range_end, "[)")),
            )
        )
        .scalars()
        .all()
    )
    time_off_by_staff: dict[int, list[tuple[datetime, datetime]]] = {
        item.id: [] for item in staff_rows
    }
    for row in time_off_rows:
        time_off_by_staff[row.staff_id].append((row.during.lower, row.during.upper))

    booking_query = select(Booking).where(
        Booking.business_id == business.id,
        Booking.staff_id.in_(ids),
        Booking.start_at < range_end,
        Booking.blocked_until > range_start,
        or_(
            Booking.status == "confirmed",
            and_(Booking.status == "pending", Booking.hold_expires_at > now),
        ),
    )
    if exclude_booking_id is not None:
        booking_query = booking_query.where(Booking.id != exclude_booking_id)
    booking_rows = [] if ignore_bookings else db.session.execute(booking_query).scalars().all()
    blocks_by_staff: dict[int, list[BookingBlock]] = {item.id: [] for item in staff_rows}
    for row in booking_rows:
        blocks_by_staff[row.staff_id].append(
            BookingBlock(row.start_at, row.blocked_until, row.status, row.hold_expires_at)
        )

    result: dict[date, dict[str, list[dict[str, str]]]] = {}
    for day in days:
        by_staff = {}
        for member in staff_rows:
            by_staff[str(member.id)] = slots_for_day(
                business_timezone=business.timezone,
                day=day,
                slot_step_min=business.slot_step_min,
                service_duration_min=offering.duration_min,
                service_buffer_min=offering.buffer_min,
                working_hours=hours_by_staff[member.id],
                time_off=time_off_by_staff[member.id],
                blocking_bookings=blocks_by_staff[member.id],
                now=now,
                minimum_notice=minimum_notice,
                maximum_advance_days=maximum_advance_days,
            )
        result[day] = by_staff
    return business.timezone, result


def _days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]
