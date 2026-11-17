"""State-machine transition validation tests that do not require PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from app.models import Booking
from app.services.booking_state import InvalidTransition, transition

STATUS_NAMES = ("new", "pending", "confirmed", "cancelled", "completed", "no_show")
ALLOWED = {
    "new": {"pending", "confirmed"},
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"cancelled", "completed", "no_show"},
    "cancelled": set(),
    "completed": set(),
    "no_show": set(),
}
INVALID_PAIRS = [
    (current, target)
    for current in STATUS_NAMES
    for target in STATUS_NAMES
    if target not in ALLOWED[current]
]


@pytest.mark.parametrize(("current", "target"), INVALID_PAIRS)
def test_invalid_state_pairs_are_rejected(current, target):
    booking = Booking(
        id=5,
        business_id=1,
        customer_id=2,
        staff_id=3,
        service_id=4,
        start_at=datetime.now(UTC) + timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=1, minutes=30),
        blocked_until=datetime.now(UTC) + timedelta(days=1, minutes=30),
        status=current,
        price_cents=100,
    )
    with pytest.raises(InvalidTransition):
        transition(booking, target, None)


def test_no_show_before_start_is_rejected():
    booking = Booking(
        id=5,
        business_id=1,
        customer_id=2,
        staff_id=3,
        service_id=4,
        start_at=datetime.now(UTC) + timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=2),
        blocked_until=datetime.now(UTC) + timedelta(hours=2),
        status="confirmed",
        price_cents=100,
    )
    with pytest.raises(InvalidTransition, match="before it starts"):
        transition(booking, "no_show", None)
