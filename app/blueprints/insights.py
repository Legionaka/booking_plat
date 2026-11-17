"""Owner analytics and owner/staff calendar read endpoints."""

from datetime import timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.extensions import db
from app.security import login_required
from app.services import insights as service

insights_bp = Blueprint("insights", __name__, url_prefix="/api/admin/businesses")


def _errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except service.InsightsError as exc:
            db.session.rollback()
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status
        except ValidationError:
            return jsonify(
                {"error": {"code": "validation_error", "message": "Query parameters are invalid."}}
            ), 422

    return wrapped


def _data(value):
    return jsonify({"data": value})


def _range_args():
    start = service.parse_day(request.args.get("from"), "from")
    end = service.parse_day(request.args.get("to"), "to")
    service.validate_range(start, end)
    return start, end


def _business(business_id: int, *, calendar: bool = False):
    return service.authorize(business_id, calendar=calendar)


@insights_bp.get("/<int:business_id>/calendar")
@login_required
@_errors
def calendar_day(business_id):
    business, staff_id = _business(business_id, calendar=True)
    day = service.parse_day(request.args.get("date"), "date")
    return _data(service.calendar_day(business, day, staff_id))


@insights_bp.get("/<int:business_id>/calendar/week")
@login_required
@_errors
def calendar_week(business_id):
    business, staff_id = _business(business_id, calendar=True)
    start = service.parse_day(request.args.get("start"), "start")
    service.validate_range(start, start + timedelta(days=6))
    return _data(service.calendar_week(business, start, staff_id))


@insights_bp.get("/<int:business_id>/analytics/summary")
@login_required
@_errors
def analytics_summary(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    return _data(service.summary(business, start, end))


@insights_bp.get("/<int:business_id>/analytics/timeseries")
@login_required
@_errors
def analytics_timeseries(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    metric, interval = request.args.get("metric", ""), request.args.get("interval", "")
    return _data(service.timeseries(business, metric, interval, start, end))


@insights_bp.get("/<int:business_id>/analytics/status-mix")
@login_required
@_errors
def analytics_status_mix(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    return _data(service.status_mix(business, start, end))


@insights_bp.get("/<int:business_id>/analytics/heatmap")
@login_required
@_errors
def analytics_heatmap(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    return _data(service.heatmap(business, start, end))


@insights_bp.get("/<int:business_id>/analytics/utilisation")
@login_required
@_errors
def analytics_utilisation(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    return _data(service.utilization(business, start, end))


@insights_bp.get("/<int:business_id>/analytics/outcomes")
@login_required
@_errors
def analytics_outcomes(business_id):
    business, _ = _business(business_id)
    start, end = _range_args()
    return _data(service.outcomes(business, start, end))


@insights_bp.get("/<int:business_id>/customers")
@login_required
@_errors
def customers(business_id):
    business, _ = _business(business_id)
    limit, offset = service.page_args(request.args)
    return _data(
        service.customers(
            business,
            request.args.get("search"),
            request.args.get("sort", "name"),
            limit,
            offset,
        )
    )


@insights_bp.get("/<int:business_id>/customers/<int:user_id>")
@login_required
@_errors
def customer_detail(business_id, user_id):
    business, _ = _business(business_id)
    return _data(service.customer_detail(business, user_id))


@insights_bp.get("/<int:business_id>/audit-log")
@login_required
@_errors
def audit_log(business_id):
    business, _ = _business(business_id)
    limit, offset = service.page_args(request.args)
    actor = request.args.get("actor")
    try:
        actor_id = int(actor) if actor is not None else None
        if actor_id is not None and actor_id <= 0:
            raise ValueError
    except ValueError as exc:
        raise service.InsightsError("validation_error", "Invalid actor filter.") from exc
    start_at = end_at = None
    if request.args.get("from"):
        start_day = service.parse_day(request.args.get("from"), "from")
        start_at, _ = service._bounds(business, start_day, start_day)
    if request.args.get("to"):
        end_day = service.parse_day(request.args.get("to"), "to")
        _, end_at = service._bounds(business, end_day, end_day)
    if start_at and end_at and end_at <= start_at:
        raise service.InsightsError("validation_error", "'to' must be on or after 'from'.")
    rows = service.audit_logs(
        business,
        entity=request.args.get("entity"),
        actor=actor_id,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        offset=offset,
    )
    return _data(rows)
