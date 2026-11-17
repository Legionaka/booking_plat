"""Database-free availability calculation tests."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from app.services.availability import BookingBlock, merge_staff_slots, slots_for_day

MONDAY = date(2026, 1, 5)
NOW = datetime(2026, 1, 1, 8, tzinfo=UTC)


def calculate(
    *,
    zone="UTC",
    day=MONDAY,
    windows=None,
    duration=30,
    buffer=0,
    step=30,
    off=(),
    bookings=(),
    now=NOW,
    notice=timedelta(0),
    advance=60,
):
    return slots_for_day(
        business_timezone=zone,
        day=day,
        slot_step_min=step,
        service_duration_min=duration,
        service_buffer_min=buffer,
        working_hours=windows or {day.weekday(): [(time(9), time(11))]},
        time_off=off,
        blocking_bookings=bookings,
        now=now,
        minimum_notice=notice,
        maximum_advance_days=advance,
    )


def starts(slots):
    return [item["local_start"] for item in slots]


def test_basic_day_generates_expected_grid():
    assert starts(calculate()) == ["09:00", "09:30", "10:00", "10:30"]


def test_slot_grid_is_anchored_to_working_window_start():
    slots = calculate(
        windows={MONDAY.weekday(): [(time(9, 10), time(10, 10))]},
        duration=15,
        step=15,
    )
    assert starts(slots) == ["09:10", "09:25", "09:40", "09:55"]


def test_booking_buffer_blocks_until_boundary_and_then_allows_slot():
    booking = BookingBlock(
        datetime(2026, 1, 5, 9, tzinfo=UTC),
        datetime(2026, 1, 5, 10, tzinfo=UTC),
        "confirmed",
    )
    assert starts(calculate(bookings=[booking])) == ["10:00", "10:30"]


def test_back_to_back_booking_is_allowed_without_buffer():
    booking = BookingBlock(
        datetime(2026, 1, 5, 9, tzinfo=UTC),
        datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
        "confirmed",
    )
    assert starts(calculate(bookings=[booking]))[0] == "09:30"


def test_partial_and_full_day_time_off():
    partial = (datetime(2026, 1, 5, 9, 30, tzinfo=UTC), datetime(2026, 1, 5, 10, tzinfo=UTC))
    assert starts(calculate(off=[partial])) == ["09:00", "10:00", "10:30"]
    whole = (datetime(2026, 1, 5, 8, tzinfo=UTC), datetime(2026, 1, 5, 12, tzinfo=UTC))
    assert calculate(off=[whole]) == []


def test_service_longer_than_free_gap_returns_nothing():
    assert calculate(duration=130) == []


def test_two_working_windows_preserve_lunch_break():
    windows = {MONDAY.weekday(): [(time(9), time(10)), (time(13), time(14))]}
    assert starts(calculate(windows=windows, duration=30)) == ["09:00", "09:30", "13:00", "13:30"]


def test_slots_never_extend_past_working_window():
    assert starts(calculate(windows={MONDAY.weekday(): [(time(9), time(10, 15))]})) == [
        "09:00",
        "09:30",
    ]


def test_minimum_notice_and_maximum_advance_cutoffs():
    current = datetime(2026, 1, 5, 9, 10, tzinfo=UTC)
    got = calculate(now=current, notice=timedelta(minutes=50), advance=1)
    assert starts(got) == ["10:00", "10:30"]
    assert calculate(now=current, advance=0) == []


def test_expired_pending_hold_does_not_block_but_live_hold_does():
    start = datetime(2026, 1, 5, 9, tzinfo=UTC)
    end = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
    expired = BookingBlock(start, end, "pending", NOW - timedelta(seconds=1))
    live = BookingBlock(start, end, "pending", NOW + timedelta(hours=1))
    assert starts(calculate(bookings=[expired]))[0] == "09:00"
    assert starts(calculate(bookings=[live]))[0] == "09:30"


def test_local_date_working_window_can_cross_utc_midnight():
    slots = calculate(
        zone="Asia/Tokyo",
        windows={MONDAY.weekday(): [(time(0), time(2))]},
    )
    assert slots[0]["start_at"] == "2026-01-04T15:00:00Z"
    assert slots[0]["local_start"] == "00:00"


def test_slot_can_cross_business_local_midnight_in_an_overnight_window():
    slots = calculate(
        zone="UTC",
        windows={MONDAY.weekday(): [(time(23), time(1))]},
        duration=30,
        step=30,
    )
    assert starts(slots) == ["23:00", "23:30", "00:00", "00:30"]
    assert slots[1]["end_at"] == "2026-01-06T00:00:00Z"


def test_daylight_saving_spring_forward_uses_real_utc_elapsed_time():
    dst_day = date(2026, 3, 8)
    slots = calculate(
        zone="America/New_York",
        day=dst_day,
        windows={dst_day.weekday(): [(time(1), time(4))]},
        now=datetime(2026, 3, 1, 12, tzinfo=UTC),
    )
    assert starts(slots) == ["01:00", "01:30", "03:00", "03:30"]
    assert slots[0]["start_at"] == "2026-03-08T06:00:00Z"
    assert slots[-1]["end_at"] == "2026-03-08T08:00:00Z"


def test_staff_any_merges_same_start_and_reports_all_staff():
    one = calculate()
    two = calculate(windows={MONDAY.weekday(): [(time(9), time(10))]})
    merged = merge_staff_slots({"7": one, "9": two})
    assert merged[0]["staff_ids"] == [7, 9]
    assert len(merged) == 4


def test_naive_current_time_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate(now=datetime(2026, 1, 1, 8))
