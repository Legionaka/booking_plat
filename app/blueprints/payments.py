"""Customer PayFast checkout and public ITN routes."""

from datetime import UTC, datetime, time, timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, render_template, request
from pydantic import ValidationError
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import Booking, Membership, Payment
from app.schemas.payments import PaymentListQuery
from app.security import login_required
from app.services import payments as service

payments_bp = Blueprint("payments", __name__)


def _errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except service.PaymentError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status

    return wrapped


@payments_bp.post("/api/bookings/<int:booking_id>/pay")
@_errors
@login_required
def start_payfast_payment(booking_id: int):
    return jsonify({"data": service.start_payment(g.current_user, booking_id)})


@payments_bp.post("/payments/handoff/<int:booking_id>")
@_errors
@login_required
def payfast_handoff(booking_id: int):
    """Render and submit the server-generated PayFast form under a narrow CSP exception."""
    payment = service.start_payment(g.current_user, booking_id)
    return render_template(
        "payments/payfast_handoff.html",
        action_url=payment["action_url"],
        fields=payment["fields"],
    )


@payments_bp.post("/api/payments/payfast/itn")
@limiter.exempt
@_errors
def payfast_itn():
    result = service.handle_payfast_itn(request.get_data(cache=True), request.remote_addr)
    return jsonify({"status": result}), 200


@payments_bp.get("/api/admin/businesses/<int:business_id>/payments")
@_errors
@login_required
def admin_payments(business_id: int):
    membership = db.session.get(Membership, (g.current_user.id, business_id))
    if membership is None or membership.role != "owner":
        raise service.PaymentError("not_found", "Business not found.", 404)
    try:
        query_params = PaymentListQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise service.PaymentError("validation_error", "Payment filters are invalid.", 422) from exc

    query = (
        select(Payment)
        .join(Booking, Booking.id == Payment.booking_id)
        .where(Booking.business_id == business_id)
    )
    if query_params.status:
        query = query.where(Payment.status == query_params.status)
    if query_params.from_date:
        start = datetime.combine(query_params.from_date, time.min, tzinfo=UTC)
        query = query.where(Payment.created_at >= start)
    if query_params.to_date:
        next_day = query_params.to_date + timedelta(days=1)
        end = datetime.combine(next_day, time.min, tzinfo=UTC)
        query = query.where(Payment.created_at < end)

    payments = (
        db.session.execute(
            query.order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(query_params.limit)
            .offset(query_params.offset)
        )
        .scalars()
        .all()
    )
    return jsonify(
        {
            "data": [
                {
                    "id": item.id,
                    "booking_id": item.booking_id,
                    "provider": item.provider,
                    "provider_ref": item.provider_ref,
                    "amount_cents": item.amount_cents,
                    "status": item.status,
                    "created_at": (
                        item.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
                    ),
                }
                for item in payments
            ]
        }
    )
