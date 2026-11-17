"""Transactional creation and maintenance of booking notification rows."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import Booking, Notification


def _insert(booking: Booking, kind: str, scheduled_for: datetime) -> None:
    db.session.execute(
        insert(Notification)
        .values(
            booking_id=booking.id,
            kind=kind,
            scheduled_for=scheduled_for.astimezone(UTC),
            status="queued",
        )
        .on_conflict_do_nothing(index_elements=["booking_id", "kind"])
    )


def enqueue_confirmation_notifications(booking: Booking, now: datetime | None = None) -> None:
    """Write confirmation/reminder intents in the booking transaction."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    _insert(booking, "confirmation", now)
    for kind, lead in (("reminder_24h", timedelta(hours=24)), ("reminder_2h", timedelta(hours=2))):
        scheduled_for = booking.start_at - lead
        if scheduled_for > now:
            _insert(booking, kind, scheduled_for)


def cancel_unsent_notifications(booking: Booking) -> None:
    db.session.execute(
        update(Notification)
        .where(
            Notification.booking_id == booking.id,
            Notification.sent_at.is_(None),
            Notification.status.not_in(("sent", "cancelled")),
        )
        .values(status="cancelled")
    )


def enqueue_cancellation_notification(booking: Booking, now: datetime | None = None) -> None:
    _insert(booking, "cancellation", (now or datetime.now(UTC)).astimezone(UTC))


def enqueue_late_payment_owner_notification(
    booking: Booking, now: datetime | None = None
) -> None:
    _insert(
        booking,
        "payment_for_cancelled_booking",
        (now or datetime.now(UTC)).astimezone(UTC),
    )


def reschedule_reminders(booking: Booking) -> None:
    for kind, lead in (("reminder_24h", timedelta(hours=24)), ("reminder_2h", timedelta(hours=2))):
        db.session.execute(
            update(Notification)
            .where(
                Notification.booking_id == booking.id,
                Notification.kind == kind,
                Notification.sent_at.is_(None),
                Notification.status.in_(("queued", "retrying")),
            )
            .values(scheduled_for=booking.start_at - lead)
        )
