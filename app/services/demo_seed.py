"""Deterministic seed data for local demonstrations only."""

import os
import random
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    Business,
    Membership,
    Notification,
    Payment,
    Service,
    Staff,
    TimeOff,
    User,
    WorkingHours,
    staff_services,
)
from app.services.booking_state import transition

DEMO_SLUG = "fade-lab"
DEMO_PASSWORD = "DemoOnly-ChangeMe-2026!"
DEMO_CUSTOMERS = [
    "Amina Dlamini",
    "Thabo Mokoena",
    "Naledi Khumalo",
    "Liam Jacobs",
    "Zanele Nkosi",
    "Musa Ndlovu",
    "Leah van der Merwe",
    "Siphesihle Zulu",
    "Ethan Botha",
    "Palesa Molefe",
    "Daniel Naidoo",
    "Ayanda Mthembu",
    "Lerato Maseko",
    "Noah Smith",
    "Kea Ramaphosa",
    "Luke Petersen",
    "Nandi Cele",
    "Milan Pillay",
    "Kabelo Dube",
    "Grace Williams",
    "Siyabonga Hadebe",
    "Zinhle Mkhize",
    "Amir Khan",
    "Tumi Radebe",
    "Olivia Brown",
]


def _user(email: str, full_name: str, password: str) -> User:
    existing = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        return existing
    row = User(
        email=email,
        full_name=full_name,
        password_hash=PasswordHasher().hash(password),
        verified_at=datetime.now(UTC),
    )
    db.session.add(row)
    db.session.flush()
    return row


def reset_demo_business() -> bool:
    business = db.session.execute(
        select(Business).where(Business.slug == DEMO_SLUG)
    ).scalar_one_or_none()
    if business is None:
        return False
    staff_ids = select(Staff.id).where(Staff.business_id == business.id)
    booking_ids = select(Booking.id).where(Booking.business_id == business.id)
    db.session.execute(delete(Notification).where(Notification.booking_id.in_(booking_ids)))
    db.session.execute(delete(Payment).where(Payment.booking_id.in_(booking_ids)))
    db.session.execute(delete(Booking).where(Booking.business_id == business.id))
    db.session.execute(delete(AuditLog).where(AuditLog.business_id == business.id))
    db.session.execute(delete(TimeOff).where(TimeOff.staff_id.in_(staff_ids)))
    db.session.execute(delete(WorkingHours).where(WorkingHours.staff_id.in_(staff_ids)))
    db.session.execute(delete(staff_services).where(staff_services.c.staff_id.in_(staff_ids)))
    db.session.execute(delete(Membership).where(Membership.business_id == business.id))
    db.session.execute(delete(Service).where(Service.business_id == business.id))
    db.session.execute(delete(Staff).where(Staff.business_id == business.id))
    db.session.delete(business)
    db.session.flush()
    return True


def seed_demo(*, reset: bool = False) -> dict[str, int]:
    if reset:
        reset_demo_business()
        db.session.flush()

    now = datetime.now(UTC)
    owner_email = os.getenv("DEMO_OWNER_EMAIL", "owner@fade-lab.demo")
    owner_password = os.getenv("DEMO_OWNER_PASSWORD", DEMO_PASSWORD)
    owner_name = os.getenv("DEMO_OWNER_NAME", "Fade Lab Owner")
    owner = _user(owner_email, owner_name, owner_password)

    business = db.session.execute(
        select(Business).where(Business.slug == DEMO_SLUG)
    ).scalar_one_or_none()
    if business is None:
        business = Business(
            slug=DEMO_SLUG,
            name="Fade Lab Barbers",
            timezone="Africa/Johannesburg",
            cancel_cutoff_hours=24,
            slot_step_min=30,
        )
        db.session.add(business)
        db.session.flush()
    if db.session.get(Membership, (owner.id, business.id)) is None:
        db.session.add(Membership(user_id=owner.id, business_id=business.id, role="owner"))

    members = {}
    for name in ("Sipho", "Lerato"):
        member = db.session.execute(
            select(Staff).where(Staff.business_id == business.id, Staff.display_name == name)
        ).scalar_one_or_none()
        if member is None:
            member = Staff(business_id=business.id, display_name=name)
            db.session.add(member)
            db.session.flush()
        members[name] = member

    definitions = (
        ("Fade", 30, 10, 18000, 0),
        ("Beard trim", 20, 5, 9000, 0),
        ("Fade and beard", 60, 15, 25000, 5000),
    )
    offerings = {}
    for name, duration, buffer, price, deposit in definitions:
        offering = db.session.execute(
            select(Service).where(Service.business_id == business.id, Service.name == name)
        ).scalar_one_or_none()
        if offering is None:
            offering = Service(
                business_id=business.id,
                name=name,
                duration_min=duration,
                buffer_min=buffer,
                price_cents=price,
                deposit_cents=deposit,
            )
            db.session.add(offering)
            db.session.flush()
        offerings[name] = offering

    for member in members.values():
        for offering in offerings.values():
            exists = db.session.execute(
                select(staff_services.c.staff_id).where(
                    staff_services.c.staff_id == member.id,
                    staff_services.c.service_id == offering.id,
                )
            ).scalar_one_or_none()
            if exists is None:
                db.session.execute(
                    staff_services.insert().values(staff_id=member.id, service_id=offering.id)
                )
        for weekday in range(5):
            for opening, closing in ((time(9), time(13)), (time(14), time(18))):
                exists = db.session.execute(
                    select(WorkingHours.id).where(
                        WorkingHours.staff_id == member.id,
                        WorkingHours.weekday == weekday,
                        WorkingHours.start_time == opening,
                        WorkingHours.end_time == closing,
                    )
                ).scalar_one_or_none()
                if exists is None:
                    db.session.add(
                        WorkingHours(
                            staff_id=member.id,
                            weekday=weekday,
                            start_time=opening,
                            end_time=closing,
                        )
                    )

    customers = [
        _user(
            f"customer{index:02d}@fade-lab.demo",
            name,
            f"Demo-Customer-{index:02d}-ChangeMe!",
        )
        for index, name in enumerate(DEMO_CUSTOMERS, 1)
    ]
    db.session.flush()
    zone = ZoneInfo(business.timezone)
    rng = random.Random(731_991)
    services_by_slot = (
        offerings["Fade and beard"],
        offerings["Beard trim"],
        offerings["Fade"],
        offerings["Fade"],
        offerings["Fade and beard"],
    )
    created = 0
    payment_count = 0
    today = datetime.now(zone).date()
    for day_offset in range(-56, 15):
        day = today + timedelta(days=day_offset)
        if day.weekday() > 4:
            continue
        for member in members.values():
            for slot_index, local_time in enumerate(
                (time(9), time(10, 30), time(12), time(14), time(15, 30))
            ):
                if member.display_name == "Lerato" and slot_index == 4 and day >= today:
                    # Preserve a real future deposit slot for the public demo journey.
                    continue
                local_start = datetime.combine(day, local_time, zone)
                start_at = local_start.astimezone(UTC)
                if day == today and start_at < now:
                    continue
                offering = services_by_slot[slot_index]
                existing = db.session.execute(
                    select(Booking.id).where(
                        Booking.business_id == business.id,
                        Booking.staff_id == member.id,
                        Booking.start_at == start_at,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                customer = rng.choice(customers)
                if day < today:
                    status = ("completed", "completed", "cancelled", "no_show", "completed")[
                        (day.toordinal() + slot_index + member.id) % 5
                    ]
                else:
                    status = ("confirmed", "pending", "confirmed", "confirmed", "cancelled")[
                        (day.toordinal() + slot_index + member.id) % 5
                    ]
                end_at = start_at + timedelta(minutes=offering.duration_min)
                initial_status = status if status in {"pending", "confirmed"} else "confirmed"
                booking = Booking(
                    business_id=business.id,
                    customer_id=customer.id,
                    staff_id=member.id,
                    service_id=offering.id,
                    start_at=start_at,
                    end_at=end_at,
                    blocked_until=end_at + timedelta(minutes=offering.buffer_min),
                    status=None,
                    hold_expires_at=(
                        now + timedelta(minutes=20) if initial_status == "pending" else None
                    ),
                    price_cents=offering.price_cents,
                    deposit_cents=offering.deposit_cents,
                )
                transition(booking, initial_status, owner)
                if status != initial_status:
                    transition(booking, status, owner)
                created += 1
                if offering.deposit_cents:
                    is_paid = status in {"confirmed", "completed"}
                    payment_status = "paid" if is_paid else "pending"
                    db.session.add(
                        Payment(
                            booking_id=booking.id,
                            provider="payfast",
                            provider_ref=f"demo-payment-{booking.id}",
                            amount_cents=offering.deposit_cents,
                            status=payment_status,
                            raw_payload=None,
                        )
                    )
                    if is_paid:
                        payment_count += 1

    db.session.commit()
    return {
        "business_id": business.id,
        "customers": len(customers),
        "staff": len(members),
        "services": len(offerings),
        "bookings_created": created,
        "paid_deposits_created": payment_count,
    }
