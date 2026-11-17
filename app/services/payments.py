"""PayFast payment creation and ordered, idempotent ITN processing."""

from datetime import UTC, datetime, timedelta
from urllib.error import URLError
from uuid import uuid4

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, Booking, Payment, Service, User
from app.services.booking_state import transition
from app.services.payfast import (
    ITN_SOURCE_HOSTS,
    format_cents,
    generate_form_signature,
    parse_amount_cents,
    resolve_payfast_ips,
    validate_itn_with_payfast,
    verify_itn_signature,
)


class PaymentError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def _payment_action_url() -> str:
    host = (
        "https://sandbox.payfast.co.za/eng/process"
        if current_app.config["PAYFAST_SANDBOX"]
        else "https://www.payfast.co.za/eng/process"
    )
    return host


def _validate_url() -> str:
    host = (
        "https://sandbox.payfast.co.za/eng/query/validate"
        if current_app.config["PAYFAST_SANDBOX"]
        else "https://www.payfast.co.za/eng/query/validate"
    )
    return host


def start_payment(user: User, booking_id: int, *, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        booking = db.session.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .with_for_update(of=Booking)
        ).scalar_one_or_none()
        if booking is None or booking.customer_id != user.id:
            raise PaymentError("not_found", "Booking not found.", 404)
        if (
            booking.status != "pending"
            or booking.deposit_cents <= 0
            or booking.hold_expires_at is None
            or booking.hold_expires_at <= now
        ):
            raise PaymentError(
                "payment_unavailable",
                "This booking cannot be paid. Its payment hold may have expired.",
                409,
            )

        payment = db.session.execute(
            select(Payment)
            .where(
                Payment.booking_id == booking.id,
                Payment.provider == "payfast",
                Payment.status == "pending",
            )
            .order_by(Payment.id.desc())
            .with_for_update(of=Payment)
        ).scalar_one_or_none()
        if payment is None:
            payment = Payment(
                booking_id=booking.id,
                provider="payfast",
                provider_ref=uuid4().hex,
                amount_cents=booking.deposit_cents,
                status="pending",
            )
            db.session.add(payment)
            db.session.flush()

        minimum_expiry = now + timedelta(minutes=current_app.config["PAYMENT_HOLD_MINUTES"])
        if booking.hold_expires_at < minimum_expiry:
            booking.hold_expires_at = minimum_expiry

        service = db.session.get(Service, booking.service_id)
        base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
        fields = {
            "merchant_id": current_app.config["PAYFAST_MERCHANT_ID"],
            "merchant_key": current_app.config["PAYFAST_MERCHANT_KEY"],
            "return_url": f"{base_url}/payments/return?booking_id={booking.id}",
            "cancel_url": f"{base_url}/payments/cancel?booking_id={booking.id}",
            "notify_url": f"{base_url}/api/payments/payfast/itn",
            "m_payment_id": payment.provider_ref,
            "amount": format_cents(payment.amount_cents),
            "item_name": service.name,
        }
        fields["signature"] = generate_form_signature(
            fields, current_app.config["PAYFAST_PASSPHRASE"] or None
        )
        db.session.commit()
        return {"action_url": _payment_action_url(), "fields": fields}
    except PaymentError:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise


def _reject(reason: str, status: int = 400) -> PaymentError:
    current_app.logger.warning("PayFast ITN rejected: %s", reason)
    return PaymentError("invalid_itn", "Payment notification could not be validated.", status)


def _decode_pairs(raw_body: bytes) -> list[tuple[str, str]]:
    from urllib.parse import parse_qsl

    try:
        text = raw_body.decode("utf-8")
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True, encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        raise _reject("malformed form body") from None
    keys = [key for key, _ in pairs]
    if not pairs or len(set(keys)) != len(keys):
        raise _reject("missing or duplicate form fields")
    return pairs


def _validate_source(source_ip: str | None) -> None:
    resolver = current_app.extensions.get("payfast_ip_resolver", resolve_payfast_ips)
    addresses: set[str] = set()
    for hostname in ITN_SOURCE_HOSTS:
        try:
            resolved = resolver(hostname)
            if isinstance(resolved, str):
                addresses.add(resolved)
            else:
                addresses.update(resolved)
        except (OSError, TimeoutError):
            current_app.logger.warning("PayFast sender hostname lookup failed for %s", hostname)
    if not source_ip or source_ip not in addresses:
        raise _reject("source IP is not in the current PayFast DNS results")


def handle_payfast_itn(raw_body: bytes, source_ip: str | None) -> str:
    pairs = _decode_pairs(raw_body)
    if not verify_itn_signature(pairs, current_app.config["PAYFAST_PASSPHRASE"] or None):
        raise _reject("signature verification failed")

    _validate_source(source_ip)
    values = dict(pairs)
    if values.get("merchant_id") != current_app.config["PAYFAST_MERCHANT_ID"]:
        raise _reject("merchant ID mismatch")

    try:
        payment = db.session.execute(
            select(Payment)
            .where(
                Payment.provider == "payfast",
                Payment.provider_ref == values.get("m_payment_id"),
            )
            .with_for_update(of=Payment)
        ).scalar_one_or_none()
        if payment is None:
            raise _reject("payment reference not found")

        received_cents = parse_amount_cents(values.get("amount_gross", ""))
        if received_cents is None or received_cents != payment.amount_cents:
            raise _reject("gross amount mismatch")

        validator = current_app.extensions.get("payfast_itn_validator", validate_itn_with_payfast)
        try:
            response = validator(
                pairs[:-1],
                _validate_url(),
                current_app.config["PAYFAST_VALIDATE_TIMEOUT_SECONDS"],
            )
        except (URLError, TimeoutError, OSError) as exc:
            db.session.rollback()
            current_app.logger.error(
                "PayFast ITN server validation unavailable: %s", type(exc).__name__
            )
            raise PaymentError(
                "payment_validation_unavailable",
                "Payment validation is temporarily unavailable. PayFast may retry.",
                503,
            ) from exc
        if response != "VALID":
            raise _reject("server-side validation response was not VALID")

        if payment.status == "paid":
            db.session.commit()
            return "already_processed"

        booking = db.session.execute(
            select(Booking)
            .where(Booking.id == payment.booking_id)
            .with_for_update(of=Booking)
        ).scalar_one()
        payload = dict(pairs)
        status = values.get("payment_status", "")
        if status == "COMPLETE":
            payment.status = "paid"
            payment.raw_payload = payload
            if booking.status == "pending":
                transition(booking, "confirmed", None)
            elif booking.status == "cancelled":
                db.session.add(
                    AuditLog(
                        actor_id=None,
                        business_id=booking.business_id,
                        entity="payment",
                        entity_id=payment.id,
                        action="payment_received_for_cancelled_booking",
                        diff={
                            "booking_id": booking.id,
                            "payment_id": payment.id,
                            "amount_cents": payment.amount_cents,
                        },
                    )
                )
                from app.services.outbox import enqueue_late_payment_owner_notification

                enqueue_late_payment_owner_notification(booking)
                current_app.logger.warning(
                    "PayFast payment received for cancelled booking_id=%s payment_id=%s; "
                    "manual refund required",
                    booking.id,
                    payment.id,
                )
        elif status in {"FAILED", "CANCELLED"}:
            payment.status = "failed"
            payment.raw_payload = payload
        else:
            payment.raw_payload = payload
        db.session.commit()
        return "processed"
    except PaymentError:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise
