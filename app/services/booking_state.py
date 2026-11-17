"""The single authority for persisted booking status transitions."""

from datetime import UTC, datetime

from app.extensions import db
from app.models import AuditLog, Booking, User


class InvalidTransition(Exception):
    """Raised when a requested booking status change is outside the state table."""


TRANSITIONS = {
    "new": {"pending", "confirmed"},
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"cancelled", "completed", "no_show"},
}


def transition(booking: Booking, new_status: str, actor: User | None) -> None:
    """Apply one planned state transition and add its audit row to the transaction."""
    current = "new" if booking.id is None and booking.status is None else booking.status
    if new_status not in TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Cannot transition booking from {current} to {new_status}.")
    if new_status == "no_show" and booking.start_at > datetime.now(UTC):
        raise InvalidTransition("A booking cannot be marked no-show before it starts.")

    booking.status = new_status
    if current == "new":
        db.session.add(booking)
        db.session.flush()
    db.session.add(
        AuditLog(
            actor_id=actor.id if actor is not None else None,
            business_id=booking.business_id,
            entity="booking",
            entity_id=booking.id,
            action="create" if current == "new" else "transition",
            diff={"before": {"status": current}, "after": {"status": new_status}},
        )
    )
    from app.services.outbox import (
        cancel_unsent_notifications,
        enqueue_cancellation_notification,
        enqueue_confirmation_notifications,
    )

    if new_status == "confirmed":
        enqueue_confirmation_notifications(booking)
    elif new_status in {"cancelled", "no_show", "completed"}:
        cancel_unsent_notifications(booking)
        if new_status == "cancelled" and (
            actor is None or actor.id != booking.customer_id
        ):
            enqueue_cancellation_notification(booking)
