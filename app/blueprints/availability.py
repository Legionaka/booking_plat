"""Rate-limited public availability reads."""

import re
from datetime import UTC, date, datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.extensions import limiter
from app.services.availability import (
    AvailabilityError,
    load_availability_range,
    merge_staff_slots,
)

availability_bp = Blueprint("availability", __name__, url_prefix="/api/b")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: int = Field(gt=0)
    staff: str = "any"

    @field_validator("staff")
    @classmethod
    def staff_is_id_or_any(cls, value: str) -> str:
        if value != "any" and (not value.isdecimal() or int(value) <= 0):
            raise ValueError("Staff must be a positive ID or 'any'.")
        return value


def _parse_query():
    values = {key: request.args.get(key) for key in ("service", "staff") if key in request.args}
    if "staff" not in values:
        values["staff"] = "any"
    try:
        return Query.model_validate(values)
    except ValidationError as exc:
        raise AvailabilityError("validation_error", "Query parameters are invalid.", 422) from exc


def _parse_date(value: str | None) -> date:
    if value is None or not DATE_RE.fullmatch(value):
        raise AvailabilityError("validation_error", "Date must use YYYY-MM-DD format.", 422)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AvailabilityError(
            "validation_error", "Date must use YYYY-MM-DD format.", 422
        ) from exc


def _rate_limit(view):
    return limiter.limit(lambda: current_app.config["PUBLIC_AVAILABILITY_RATE_LIMIT"])(view)


def _handle_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except AvailabilityError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status

    return wrapped


def _staff_arg(query: Query) -> int | None:
    return None if query.staff == "any" else int(query.staff)


def _get_range(slug: str, query: Query, start: date, end: date):
    config = current_app.config
    return load_availability_range(
        business_slug=slug,
        service_id=query.service,
        from_date=start,
        to_date=end,
        staff_id=_staff_arg(query),
        now=datetime.now(UTC),
        minimum_notice=timedelta(minutes=config["AVAILABILITY_MINIMUM_NOTICE_MINUTES"]),
        maximum_advance_days=config["AVAILABILITY_MAXIMUM_ADVANCE_DAYS"],
    )


@availability_bp.get("/<slug>/slots")
@_rate_limit
@_handle_errors
def slots(slug):
    query = _parse_query()
    day = _parse_date(request.args.get("date"))
    timezone, data = _get_range(slug, query, day, day)
    return jsonify({"data": {"timezone": timezone, "slots": merge_staff_slots(data[day])}})


@availability_bp.get("/<slug>/availability")
@_rate_limit
@_handle_errors
def availability(slug):
    query = _parse_query()
    start, end = _parse_date(request.args.get("from")), _parse_date(request.args.get("to"))
    if end < start:
        raise AvailabilityError(
            "validation_error", "The 'to' date must be on or after 'from'.", 422
        )
    if (end - start).days + 1 > 62:
        raise AvailabilityError("validation_error", "Date ranges are limited to 62 days.", 422)
    timezone, data = _get_range(slug, query, start, end)
    counts = []
    for day, by_staff in data.items():
        count = len(merge_staff_slots(by_staff))
        counts.append({"date": day.isoformat(), "open_slots": count, "open": count > 0})
    return jsonify({"data": {"timezone": timezone, "days": counts}})
