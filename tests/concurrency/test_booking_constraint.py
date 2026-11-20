from datetime import UTC, datetime, timedelta

import pytest
from app.extensions import db
from app.models import Booking, Business, Service, Staff, User
from sqlalchemy.exc import IntegrityError


def add_booking(status: str, start: datetime, end: datetime, blocked_until: datetime) -> Booking:
    business = Business.query.one()
    customer = User.query.one()
    staff = Staff.query.one()
    service = Service.query.one()
    booking = Booking(
        business_id=business.id,
        customer_id=customer.id,
        staff_id=staff.id,
        service_id=service.id,
        start_at=start,
        end_at=end,
        blocked_until=blocked_until,
        status=status,
        price_cents=5000,
        deposit_cents=0,
    )
    db.session.add(booking)
    db.session.flush()
    return booking


@pytest.fixture(autouse=True)
def booking_data(app):
    with app.app_context():
        business = Business(slug="demo", name="Demo business")
        customer = User(
            email="customer@example.test", password_hash="not-used", full_name="Customer"
        )
        db.session.add_all([business, customer])
        db.session.flush()
        service = Service(
            business_id=business.id,
            name="Consultation",
            duration_min=30,
            buffer_min=0,
            price_cents=5000,
            deposit_cents=0,
        )
        staff = Staff(business_id=business.id, display_name="Staff member")
        db.session.add_all([service, staff])
        db.session.commit()


@pytest.mark.parametrize("first_status", ["pending", "confirmed"])
@pytest.mark.parametrize("second_status", ["pending", "confirmed"])
def test_active_overlapping_bookings_are_rejected(app, first_status, second_status):
    start = datetime(2030, 1, 2, 10, tzinfo=UTC)
    with app.app_context():
        add_booking(
            first_status, start, start + timedelta(minutes=30), start + timedelta(minutes=30)
        )
        db.session.commit()

        with pytest.raises(IntegrityError, match="exclusion"):
            add_booking(
                second_status,
                start + timedelta(minutes=15),
                start + timedelta(minutes=45),
                start + timedelta(minutes=45),
            )
            db.session.commit()
        db.session.rollback()


def test_cancelled_booking_does_not_block_same_slot(app):
    start = datetime(2030, 1, 2, 10, tzinfo=UTC)
    with app.app_context():
        add_booking(
            "cancelled", start, start + timedelta(minutes=30), start + timedelta(minutes=30)
        )
        db.session.commit()

        add_booking(
            "confirmed", start, start + timedelta(minutes=30), start + timedelta(minutes=30)
        )
        db.session.commit()

        next_start = start + timedelta(minutes=30)
        add_booking(
            "confirmed",
            next_start,
            next_start + timedelta(minutes=30),
            next_start + timedelta(minutes=30),
        )
        db.session.commit()


def test_back_to_back_bookings_without_buffer_are_allowed(app):
    start = datetime(2030, 1, 2, 10, tzinfo=UTC)
    with app.app_context():
        add_booking(
            "confirmed", start, start + timedelta(minutes=30), start + timedelta(minutes=30)
        )
        db.session.commit()


def test_buffer_blocks_overlap_until_its_exclusive_end(app):
    start = datetime(2030, 1, 2, 10, tzinfo=UTC)
    with app.app_context():
        add_booking(
            "confirmed", start, start + timedelta(minutes=30), start + timedelta(minutes=45)
        )
        db.session.commit()

        # This begins during the first booking's 15-minute buffer.
        with pytest.raises(IntegrityError, match="exclusion"):
            add_booking(
                "confirmed",
                start + timedelta(minutes=30),
                start + timedelta(minutes=45),
                start + timedelta(minutes=45),
            )
        db.session.rollback()

        # The half-open range allows a new booking exactly at blocked_until.
        next_start = start + timedelta(minutes=45)
        add_booking(
            "confirmed",
            next_start,
            next_start + timedelta(minutes=15),
            next_start + timedelta(minutes=15),
        )
        db.session.commit()
