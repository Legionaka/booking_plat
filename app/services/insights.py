"""Tenant-scoped calendar, analytics, customer, and audit read models."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import g
from sqlalchemy import (
    Date,
    and_,
    case,
    cast,
    desc,
    extract,
    func,
    or_,
    select,
    text,
)

from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    Business,
    Membership,
    Payment,
    Service,
    Staff,
    TimeOff,
    User,
    WorkingHours,
)
from app.services.availability import load_availability_range

MAX_RANGE_DAYS = 366


class InsightsError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def parse_day(value: str | None, name: str) -> date:
    if value is None:
        raise InsightsError("validation_error", f"'{name}' must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InsightsError("validation_error", f"'{name}' must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise InsightsError("validation_error", f"'{name}' must use YYYY-MM-DD.")
    return parsed


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise InsightsError("validation_error", "'to' must be on or after 'from'.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise InsightsError("validation_error", "Date ranges are limited to 366 inclusive days.")


def page_args(args) -> tuple[int, int]:
    try:
        limit, offset = int(args.get("limit", 50)), int(args.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise InsightsError("validation_error", "Invalid pagination values.") from exc
    if not 1 <= limit <= 100 or offset < 0:
        raise InsightsError("validation_error", "Limit must be 1-100 and offset non-negative.")
    return limit, offset


def authorize(business_id: int, *, calendar: bool = False) -> tuple[Business, int | None]:
    user = g.current_user
    business = db.session.get(Business, business_id)
    membership = db.session.get(Membership, (user.id, business_id))
    if business is None or membership is None:
        raise InsightsError("not_found", "Business not found.", 404)
    if membership.role == "owner":
        return business, None
    if membership.role == "staff" and calendar:
        staff_id = db.session.execute(
            select(Staff.id).where(
                Staff.business_id == business_id, Staff.user_id == user.id
            )
        ).scalar_one_or_none()
        if staff_id is not None:
            return business, staff_id
    raise InsightsError("not_found", "Business not found.", 404)


def _bounds(business: Business, start: date, end: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(business.timezone)
    return (
        datetime.combine(start, time.min, zone).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC),
    )


def _z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def calendar_day(business: Business, day: date, staff_filter: int | None) -> dict:
    zone = ZoneInfo(business.timezone)
    start_at, end_at = _bounds(business, day, day)
    staff_query = select(Staff).where(Staff.business_id == business.id).order_by(Staff.id)
    if staff_filter is not None:
        staff_query = staff_query.where(Staff.id == staff_filter)
    staff_rows = db.session.execute(staff_query).scalars().all()
    staff_ids = [item.id for item in staff_rows]
    if not staff_ids:
        return {"date": day.isoformat(), "timezone": business.timezone, "staff": []}

    hours = db.session.execute(
        select(WorkingHours)
        .where(WorkingHours.staff_id.in_(staff_ids), WorkingHours.weekday == day.weekday())
        .order_by(WorkingHours.staff_id, WorkingHours.start_time)
    ).scalars().all()
    time_off = db.session.execute(
        select(TimeOff)
        .where(
            TimeOff.staff_id.in_(staff_ids),
            TimeOff.during.op("&&")(func.tstzrange(start_at, end_at, "[)")),
        )
        .order_by(TimeOff.staff_id, TimeOff.id)
    ).scalars().all()
    payment_status = (
        select(Payment.status)
        .where(Payment.booking_id == Booking.id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.session.execute(
        select(Booking, Service.name, User.full_name, payment_status)
        .join(Service, Service.id == Booking.service_id)
        .join(User, User.id == Booking.customer_id)
        .where(
            Booking.business_id == business.id,
            Booking.staff_id.in_(staff_ids),
            Booking.start_at < end_at,
            Booking.end_at > start_at,
        )
        .order_by(Booking.start_at, Booking.id)
    ).all()
    grouped_hours: dict[int, list[dict]] = {item.id: [] for item in staff_rows}
    grouped_timeoff: dict[int, list[dict]] = {item.id: [] for item in staff_rows}
    grouped_bookings: dict[int, list[dict]] = {item.id: [] for item in staff_rows}
    for row in hours:
        grouped_hours[row.staff_id].append(
            {"start": row.start_time.strftime("%H:%M"), "end": row.end_time.strftime("%H:%M")}
        )
    for row in time_off:
        grouped_timeoff[row.staff_id].append(
            {
                "start_at": row.during.lower.astimezone(zone).isoformat(),
                "end_at": row.during.upper.astimezone(zone).isoformat(),
                "reason": row.reason,
            }
        )
    for booking, service_name, customer_name, paid in rows:
        grouped_bookings[booking.staff_id].append(
            {
                "id": booking.id,
                "start_at": _z(booking.start_at),
                "end_at": _z(booking.end_at),
                "local_start": booking.start_at.astimezone(zone).isoformat(),
                "local_end": booking.end_at.astimezone(zone).isoformat(),
                "status": booking.status,
                "service": service_name,
                "customer_name": customer_name,
                "deposit_status": paid or (
                    "pending" if booking.deposit_cents > 0 else "not_required"
                ),
            }
        )
    return {
        "date": day.isoformat(),
        "timezone": business.timezone,
        "staff": [
            {
                "id": member.id,
                "display_name": member.display_name,
                "working_windows": grouped_hours[member.id],
                "time_off": grouped_timeoff[member.id],
                "bookings": grouped_bookings[member.id],
            }
            for member in staff_rows
        ],
    }


def _utilization_rows(business: Business, start: date, end: date) -> list[dict]:
    sql = text(
        """
        WITH days AS (
          SELECT value::date AS local_day
          FROM generate_series(
            CAST(:start_day AS date), CAST(:end_day AS date), interval '1 day'
          ) AS day_series(value)
        ), windows AS (
          SELECT s.id AS staff_id,
                 ((days.local_day + wh.start_time) AT TIME ZONE :timezone) AS window_start,
                 ((days.local_day + wh.end_time) AT TIME ZONE :timezone) AS window_end
          FROM staff s
          JOIN working_hours wh ON wh.staff_id = s.id
          JOIN days ON wh.weekday = EXTRACT(ISODOW FROM days.local_day)::int - 1
          WHERE s.business_id = :business_id
        ), timeoff AS (
          SELECT w.staff_id,
                 SUM(CASE WHEN t.id IS NOT NULL THEN EXTRACT(EPOCH FROM
                   (LEAST(w.window_end, upper(t.during)) -
                    GREATEST(w.window_start, lower(t.during)))) / 60.0 ELSE 0 END) AS minutes
          FROM windows w
          LEFT JOIN time_off t
            ON t.staff_id = w.staff_id
           AND t.during && tstzrange(w.window_start, w.window_end, '[)')
          GROUP BY w.staff_id
        ), base_available AS (
          SELECT w.staff_id,
                 SUM(EXTRACT(EPOCH FROM (w.window_end - w.window_start)) / 60.0) AS minutes
          FROM windows w GROUP BY w.staff_id
        ), available AS (
          SELECT a.staff_id, GREATEST(0, a.minutes - COALESCE(t.minutes, 0)) AS minutes
          FROM base_available a
          LEFT JOIN timeoff t ON t.staff_id = a.staff_id
        ), booked AS (
          SELECT w.staff_id,
                 SUM(EXTRACT(EPOCH FROM (
                   LEAST(w.window_end, b.end_at) - GREATEST(w.window_start, b.start_at)
                 )) / 60.0) AS minutes
          FROM windows w
          JOIN bookings b
            ON b.staff_id = w.staff_id
           AND b.business_id = :business_id
           AND b.status IN ('confirmed', 'completed', 'no_show')
           AND tstzrange(b.start_at, b.end_at, '[)') &&
               tstzrange(w.window_start, w.window_end, '[)')
          GROUP BY w.staff_id
        )
        SELECT s.id AS staff_id, s.display_name,
               COALESCE(a.minutes, 0)::int AS available_minutes,
               COALESCE(b.minutes, 0)::int AS booked_minutes
        FROM staff s
        LEFT JOIN available a ON a.staff_id = s.id
        LEFT JOIN booked b ON b.staff_id = s.id
        WHERE s.business_id = :business_id
        ORDER BY s.id
        """
    )
    return [
        dict(row)
        for row in db.session.execute(
            sql,
            {
                "start_day": start,
                "end_day": end,
                "timezone": business.timezone,
                "business_id": business.id,
            },
        ).mappings()
    ]


def _sum_minutes(rows: list[dict]) -> tuple[int, int]:
    return (
        sum(int(row["booked_minutes"]) for row in rows),
        sum(int(row["available_minutes"]) for row in rows),
    )


def _date_metrics(business: Business, start: date, end: date) -> dict[str, int]:
    start_at, end_at = _bounds(business, start, end)
    now = datetime.now(UTC)
    metric_row = db.session.execute(
        select(
            func.count(Booking.id).label("bookings"),
            func.coalesce(
                func.sum(case((Booking.status == "completed", Booking.price_cents), else_=0)), 0
            ).label("revenue_cents"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(Booking.status == "confirmed", Booking.start_at >= now),
                            Booking.price_cents,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("expected_revenue_cents"),
            func.sum(case((Booking.status == "no_show", 1), else_=0)).label("no_shows"),
            func.sum(case((Booking.status == "cancelled", 1), else_=0)).label("cancellations"),
        )
        .where(
            Booking.business_id == business.id,
            Booking.start_at >= start_at,
            Booking.start_at < end_at,
        )
    ).one()
    deposits = db.session.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0))
        .join(Booking, Booking.id == Payment.booking_id)
        .where(
            Booking.business_id == business.id,
            Payment.status == "paid",
            Payment.created_at >= start_at,
            Payment.created_at < end_at,
        )
    ).scalar_one()
    booked_minutes, available_minutes = _sum_minutes(
        _utilization_rows(business, start, end)
    )
    total = int(metric_row.bookings or 0)
    values = {
        "bookings": total,
        "revenue_cents": int(metric_row.revenue_cents or 0),
        "expected_revenue_cents": int(metric_row.expected_revenue_cents or 0),
        "deposits_collected_cents": int(deposits or 0),
        "booked_minutes": booked_minutes,
        "available_minutes": available_minutes,
        "fill_rate_percent": round(booked_minutes * 100 / available_minutes, 2)
        if available_minutes
        else 0.0,
        "no_show_rate_percent": round(int(metric_row.no_shows or 0) * 100 / total, 2)
        if total
        else 0.0,
        "cancellation_rate_percent": round(
            int(metric_row.cancellations or 0) * 100 / total, 2
        )
        if total
        else 0.0,
    }
    return values


def _percent_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) * 100 / previous, 2)


def summary(business: Business, start: date, end: date) -> dict:
    validate_range(start, end)
    span = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    current = _date_metrics(business, start, end)
    previous = _date_metrics(business, previous_start, previous_end)
    changes = {
        key: _percent_change(value, previous[key])
        for key, value in current.items()
        if key not in {"booked_minutes", "available_minutes"}
    }
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "current": current,
        "previous": previous,
        "change_percent": changes,
    }


def timeseries(
    business: Business, metric: str, interval: str, start: date, end: date
) -> list[dict]:
    if metric not in {"bookings", "revenue"}:
        raise InsightsError("validation_error", "metric must be bookings or revenue.")
    if interval not in {"day", "week"}:
        raise InsightsError("validation_error", "interval must be day or week.")
    validate_range(start, end)
    trunc = "day" if interval == "day" else "week"
    if interval == "day":
        first, last, step = start, end, "1 day"
    else:
        first = start - timedelta(days=start.weekday())
        last = end - timedelta(days=end.weekday())
        step = "1 week"
    value = (
        "COUNT(b.id)" if metric == "bookings"
        else "COALESCE(SUM(CASE WHEN b.status = 'completed' THEN b.price_cents ELSE 0 END), 0)"
    )
    sql = text(
        f"""
        WITH buckets AS (
          SELECT value::date AS bucket_day
          FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '{step}') value
        ), totals AS (
          SELECT date_trunc('{trunc}', timezone(:timezone, b.start_at))::date AS bucket_day,
                 {value} AS value
          FROM bookings b
          WHERE b.business_id = :business_id
            AND b.start_at >= :start_at AND b.start_at < :end_at
          GROUP BY bucket_day
        )
        SELECT buckets.bucket_day, COALESCE(totals.value, 0) AS value
        FROM buckets LEFT JOIN totals USING (bucket_day)
        ORDER BY buckets.bucket_day
        """
    )
    start_at, end_at = _bounds(business, start, end)
    return [
        {"date": row.bucket_day.isoformat(), metric: int(row.value)}
        for row in db.session.execute(
            sql,
            {
                "first": first,
                "last": last,
                "timezone": business.timezone,
                "business_id": business.id,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
    ]


def status_mix(business: Business, start: date, end: date) -> list[dict]:
    validate_range(start, end)
    start_at, end_at = _bounds(business, start, end)
    rows = db.session.execute(
        select(Booking.status, func.count(Booking.id).label("count"))
        .where(
            Booking.business_id == business.id,
            Booking.start_at >= start_at,
            Booking.start_at < end_at,
        )
        .group_by(Booking.status)
        .order_by(Booking.status)
    ).all()
    return [{"status": row.status, "count": row.count} for row in rows]


def heatmap(business: Business, start: date, end: date) -> list[dict]:
    validate_range(start, end)
    start_at, end_at = _bounds(business, start, end)
    local_start = func.timezone(business.timezone, Booking.start_at)
    rows = db.session.execute(
        select(
            (extract("isodow", local_start) - 1).label("weekday"),
            extract("hour", local_start).label("hour"),
            func.count(Booking.id).label("count"),
        )
        .where(
            Booking.business_id == business.id,
            Booking.start_at >= start_at,
            Booking.start_at < end_at,
        )
        .group_by("weekday", "hour")
        .order_by("weekday", "hour")
    ).all()
    return [
        {"weekday": int(row.weekday), "hour": int(row.hour), "count": row.count}
        for row in rows
    ]


def utilization(business: Business, start: date, end: date) -> list[dict]:
    validate_range(start, end)
    result = []
    for row in _utilization_rows(business, start, end):
        available = int(row["available_minutes"])
        booked = int(row["booked_minutes"])
        result.append(
            {
                "staff_id": row["staff_id"],
                "staff_name": row["display_name"],
                "booked_minutes": booked,
                "available_minutes": available,
                "utilisation_percent": round(booked * 100 / available, 2) if available else 0.0,
            }
        )
    return result


def outcomes(business: Business, start: date, end: date) -> dict:
    validate_range(start, end)
    start_at, end_at = _bounds(business, start, end)
    rows = dict(
        db.session.execute(
            select(Booking.status, func.count(Booking.id))
            .where(
                Booking.business_id == business.id,
                Booking.start_at >= start_at,
                Booking.start_at < end_at,
            )
            .group_by(Booking.status)
        ).all()
    )
    return {
        "created": sum(rows.values()),
        "confirmed": rows.get("confirmed", 0),
        "completed": rows.get("completed", 0),
        "cancelled": rows.get("cancelled", 0),
        "no_show": rows.get("no_show", 0),
        "funnel_note": "Page-view and booking-start funnel steps are not tracked.",
    }


def calendar_week(
    business: Business, start: date, staff_filter: int | None
) -> dict:
    end = start + timedelta(days=6)
    start_at, end_at = _bounds(business, start, end)
    local_day = cast(func.timezone(business.timezone, Booking.start_at), Date)
    query = (
        select(
            Booking.staff_id,
            local_day,
            func.count(),
        )
        .where(
            Booking.business_id == business.id,
            Booking.start_at >= start_at,
            Booking.start_at < end_at,
        )
        .group_by(Booking.staff_id, local_day)
    )
    if staff_filter is not None:
        query = query.where(Booking.staff_id == staff_filter)
    counts = {
        (staff_id, day): count
        for staff_id, day, count in db.session.execute(query).all()
    }
    staff_query = select(Staff).where(Staff.business_id == business.id).order_by(Staff.id)
    if staff_filter is not None:
        staff_query = staff_query.where(Staff.id == staff_filter)
    staff_rows = db.session.execute(staff_query).scalars().all()
    slots: dict[tuple[int, date], int] = {}
    offerings = db.session.execute(
        select(Service)
        .where(Service.business_id == business.id, Service.active.is_(True))
        .order_by(Service.id)
    ).scalars().all()
    for offering in offerings:
        _, loaded = load_availability_range(
            business_slug=business.slug,
            service_id=offering.id,
            from_date=start,
            to_date=end,
            staff_id=staff_filter,
            now=datetime.now(UTC),
            minimum_notice=timedelta(hours=0),
            maximum_advance_days=366,
        )
        for day, by_staff in loaded.items():
            for member_id, candidate_slots in by_staff.items():
                key = (int(member_id), day)
                slots[key] = slots.get(key, 0) + len(candidate_slots)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": business.timezone,
        "staff": [
            {
                "staff_id": member.id,
                "staff_name": member.display_name,
                "days": [
                    {
                        "date": (start + timedelta(days=offset)).isoformat(),
                        "bookings": counts.get((member.id, start + timedelta(days=offset)), 0),
                        "open_slots": slots.get((member.id, start + timedelta(days=offset)), 0),
                    }
                    for offset in range(7)
                ],
            }
            for member in staff_rows
        ],
    }


def customers(
    business: Business, search: str | None, sort: str, limit: int, offset: int
) -> list[dict]:
    allowed = {"name", "booking_count", "no_show_count", "last_visit"}
    if sort not in allowed:
        raise InsightsError("validation_error", "Unsupported customer sort.")
    counts = func.count(Booking.id)
    no_shows = func.sum(case((Booking.status == "no_show", 1), else_=0))
    last_visit = func.max(case((Booking.status == "completed", Booking.start_at), else_=None))
    ordering = {
        "name": User.full_name,
        "booking_count": desc(counts),
        "no_show_count": desc(no_shows),
        "last_visit": desc(last_visit),
    }[sort]
    query = (
        select(
            User.id,
            User.full_name,
            User.email,
            counts.label("booking_count"),
            func.coalesce(no_shows, 0).label("no_show_count"),
            last_visit.label("last_visit"),
        )
        .join(Booking, Booking.customer_id == User.id)
        .where(Booking.business_id == business.id)
        .group_by(User.id)
        .order_by(ordering, User.id)
    )
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                User.full_name.ilike(f"%{escaped}%", escape="\\"),
                User.email.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    return [
        {
            "id": row.id,
            "name": row.full_name,
            "email": row.email,
            "booking_count": int(row.booking_count or 0),
            "no_show_count": int(row.no_show_count or 0),
            "last_visit": _z(row.last_visit) if row.last_visit else None,
        }
        for row in db.session.execute(query.limit(limit).offset(offset))
    ]


def customer_detail(business: Business, user_id: int) -> dict:
    user = db.session.execute(
        select(User)
        .join(Booking, Booking.customer_id == User.id)
        .where(Booking.business_id == business.id, User.id == user_id)
        .limit(1)
    ).scalar_one_or_none()
    if user is None:
        raise InsightsError("not_found", "Customer not found.", 404)
    bookings = db.session.execute(
        select(Booking, Service.name, Staff.display_name)
        .join(Service, Service.id == Booking.service_id)
        .join(Staff, Staff.id == Booking.staff_id)
        .where(Booking.business_id == business.id, Booking.customer_id == user_id)
        .order_by(Booking.start_at.desc())
    ).all()
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "bookings": [
            {
                "id": row.id,
                "status": row.status,
                "start_at": _z(row.start_at),
                "end_at": _z(row.end_at),
                "service": service_name,
                "staff": staff_name,
                "price_cents": row.price_cents,
                "deposit_cents": row.deposit_cents,
            }
            for row, service_name, staff_name in bookings
        ],
    }


SECRET_AUDIT_KEYS = {
    "password",
    "password_hash",
    "token",
    "signature",
    "passphrase",
    "merchant_key",
    "raw_payload",
    "secret",
    "csrf",
}


def _sanitize(value):
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if key.lower() not in SECRET_AUDIT_KEYS
            and not any(
                secret in key.lower()
                for secret in ("password", "token", "signature", "secret")
            )
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def audit_logs(
    business: Business,
    *,
    entity: str | None,
    actor: int | None,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
    offset: int,
) -> list[dict]:
    query = (
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.business_id == business.id)
    )
    if entity:
        query = query.where(AuditLog.entity == entity)
    if actor is not None:
        query = query.where(AuditLog.actor_id == actor)
    if start_at:
        query = query.where(AuditLog.created_at >= start_at)
    if end_at:
        query = query.where(AuditLog.created_at < end_at)
    rows = db.session.execute(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": row.id,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "action": row.action,
            "actor_id": row.actor_id,
            "actor_name": actor_name,
            "diff": _sanitize(row.diff),
            "created_at": _z(row.created_at),
        }
        for row, actor_name in rows
    ]
