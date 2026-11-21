"""RQ scheduler and idempotent outbox delivery jobs."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import current_app, render_template
from rq import Queue, Retry, get_current_job
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.registry import ScheduledJobRegistry
from sqlalchemy import select

from app.extensions import db
from app.models import Booking, Business, Membership, Notification, Service, Staff, User
from app.services.bookings import expire_holds
from app.services.email import EmailDeliveryError

MAX_NOTIFICATION_ATTEMPTS = 5
RETRY_INTERVALS_SECONDS = (60, 300, 900, 900)


def _queue() -> Queue:
    # RQ pickles job payloads and requires raw byte responses; sessions use a
    # separate decode_responses client configured on app.extensions.
    redis_client = current_app.extensions["rq_redis"]
    return Queue(current_app.config["RQ_QUEUE_NAME"], connection=redis_client)


def _retry_policy() -> Retry:
    intervals = current_app.config.get(
        "NOTIFICATION_RETRY_INTERVALS_SECONDS", RETRY_INTERVALS_SECONDS
    )
    return Retry(max=MAX_NOTIFICATION_ATTEMPTS - 1, interval=list(intervals))


def enqueue_due_notifications(now: datetime | None = None, limit: int | None = None) -> int:
    """Enqueue a small locked batch of due rows; repeated schedulers are safe."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    limit = limit or current_app.config["NOTIFICATION_BATCH_SIZE"]
    enqueued = 0
    queue = _queue()
    try:
        rows = (
            db.session.execute(
                select(Notification)
                .where(
                    Notification.status.in_(("queued", "retrying")),
                    Notification.scheduled_for <= now,
                )
                .order_by(Notification.scheduled_for, Notification.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for notification in rows:
            job_id = f"notification-{notification.id}"
            should_enqueue = True
            try:
                existing = Job.fetch(job_id, connection=queue.connection)
                status = existing.get_status(refresh=True)
                if status == "queued":
                    should_enqueue = job_id not in queue.job_ids
                elif status == "started":
                    progress_at = existing.last_heartbeat or existing.started_at
                    timeout = current_app.config["NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS"]
                    should_enqueue = (
                        progress_at is None
                        or (now - progress_at).total_seconds() >= timeout
                    )
                elif status in {"deferred", "scheduled"}:
                    scheduled_ids = ScheduledJobRegistry(
                        queue.name, connection=queue.connection
                    ).get_job_ids()
                    should_enqueue = job_id not in scheduled_ids
                if not should_enqueue:
                    continue
                existing.delete()
            except NoSuchJobError:
                pass
            queue.enqueue(
                send_notification,
                notification.id,
                job_id=job_id,
                retry=_retry_policy(),
            )
            enqueued += 1
        db.session.commit()
        return enqueued
    except Exception:
        db.session.rollback()
        raise


def run_scheduler_once(now: datetime | None = None) -> tuple[int, int]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    enqueued = enqueue_due_notifications(now)
    expired = expire_holds(now)
    return enqueued, expired


def _render(notification: Notification, booking: Booking, business: Business,
            service: Service, staff: Staff, user: User) -> tuple[str, str, str]:
    zone = ZoneInfo(business.timezone)
    local_start = booking.start_at.astimezone(zone)
    values = {
        "business_name": business.name,
        "service_name": service.name,
        "staff_name": staff.display_name,
        "customer_name": db.session.get(User, booking.customer_id).full_name,
        "date": local_start.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "time": local_start.strftime("%I:%M %p").lstrip("0"),
        "timezone_name": local_start.tzname() or business.timezone,
        "price": f"{booking.price_cents / 100:.2f}",
        "manage_url": (
            f"{current_app.config['BOOKING_MANAGE_BASE_URL'].rstrip('/')}/account/bookings/"
            f"{booking.id}"
        ),
    }
    labels = {
        "confirmation": ("Booking confirmed", "confirmation"),
        "reminder_24h": ("Your booking is tomorrow", "reminder"),
        "reminder_2h": ("Your booking is coming up", "reminder"),
        "cancellation": ("Booking cancelled", "cancellation"),
        "payment_for_cancelled_booking": (
            "Payment received for cancelled booking",
            "payment_for_cancelled_booking",
        ),
    }
    subject, template = labels[notification.kind]
    if notification.kind == "reminder_24h":
        values["reminder_wording"] = "This is a reminder for your booking tomorrow."
    elif notification.kind == "reminder_2h":
        values["reminder_wording"] = "This is a reminder for your booking in about two hours."
    text_body = render_template(f"emails/{template}.txt", **values)
    html_body = render_template(f"emails/{template}.html", **values)
    return subject, text_body, html_body


def _mark_failed(notification_id: int) -> None:
    row = db.session.execute(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).scalar_one_or_none()
    if row is not None and row.sent_at is None and row.status not in {"cancelled", "sent"}:
        row.status = "failed"
    db.session.commit()


def send_notification(notification_id: int) -> str:
    """Deliver once while holding the outbox row lock, then mark it sent."""
    job = get_current_job()
    attempts = 1
    if job is not None:
        attempts = int(job.meta.get("notification_attempts", 0)) + 1
        job.meta["notification_attempts"] = attempts
        job.save_meta()
    try:
        notification = db.session.execute(
            select(Notification)
            .where(Notification.id == notification_id)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if notification is None:
            db.session.rollback()
            return "locked"
        if notification.sent_at is not None or notification.status in {
            "sent",
            "cancelled",
            "failed",
        }:
            db.session.commit()
            return "skipped"
        if notification.scheduled_for > datetime.now(UTC):
            db.session.commit()
            return "not_due"

        booking = db.session.get(Booking, notification.booking_id)
        if booking is None:
            notification.status = "cancelled"
            db.session.commit()
            return "cancelled"
        if notification.kind in {"cancellation", "payment_for_cancelled_booking"}:
            if booking.status != "cancelled":
                notification.status = "cancelled"
                db.session.commit()
                return "cancelled"
        elif booking.status != "confirmed":
            notification.status = "cancelled"
            db.session.commit()
            return "cancelled"

        business = db.session.get(Business, booking.business_id)
        service = db.session.get(Service, booking.service_id)
        staff = db.session.get(Staff, booking.staff_id)
        user = db.session.get(User, booking.customer_id)
        if notification.kind == "payment_for_cancelled_booking":
            owner_id = db.session.execute(
                select(Membership.user_id)
                .where(
                    Membership.business_id == booking.business_id,
                    Membership.role == "owner",
                )
                .order_by(Membership.user_id)
                .limit(1)
            ).scalar_one_or_none()
            if owner_id is None:
                notification.status = "cancelled"
                db.session.commit()
                return "cancelled"
            user = db.session.get(User, owner_id)
        subject, text_body, html_body = _render(
            notification, booking, business, service, staff, user
        )
        current_app.extensions["email_service"].send_notification_email(
            user, subject, text_body, html_body
        )
        notification.sent_at = datetime.now(UTC)
        notification.status = "sent"
        db.session.commit()
        return "sent"
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            "Notification delivery failed; attempt=%s exception_type=%s",
            attempts,
            type(exc).__name__,
        )
        if isinstance(exc, EmailDeliveryError) and not exc.retryable:
            _mark_failed(notification_id)
            return "failed"
        if attempts >= MAX_NOTIFICATION_ATTEMPTS:
            _mark_failed(notification_id)
        else:
            row = db.session.execute(
                select(Notification).where(Notification.id == notification_id).with_for_update()
            ).scalar_one_or_none()
            if row is not None and row.sent_at is None and row.status not in {
                "cancelled",
                "failed",
            }:
                row.status = "retrying"
            db.session.commit()
        raise


