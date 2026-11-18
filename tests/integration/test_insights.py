"""Owner analytics, staff calendars, customer data, and demo seed tests."""

from datetime import UTC, datetime, time, timedelta
from threading import Lock

import pytest
from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    Business,
    Membership,
    Payment,
    Service,
    Staff,
    TimeOff,
    User,
    WorkingHours,
    staff_services,
)
from psycopg.types.range import Range
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from tests.integration.test_bookings import client_for


@pytest.fixture
def insights_data(app):
    with app.app_context():
        users = [
            User(
                email=f"insights-{name}@example.test",
                full_name=name.title(),
                password_hash=f"auth-{name}",
                verified_at=datetime.now(UTC),
            )
            for name in ("owner", "staff", "customer", "other", "public")
        ]
        business = Business(
            slug="insights-shop",
            name="Insights Shop",
            timezone="Africa/Johannesburg",
            slot_step_min=30,
        )
        other_business = Business(
            slug="insights-other", name="Other Shop", timezone="UTC"
        )
        db.session.add_all([*users, business, other_business])
        db.session.flush()
        member = Staff(
            business_id=business.id, user_id=users[1].id, display_name="Calendar Staff"
        )
        other_member = Staff(business_id=business.id, display_name="Second Staff")
        offering = Service(
            business_id=business.id,
            name="Evening Cut",
            duration_min=60,
            buffer_min=0,
            price_cents=18000,
        )
        foreign_offering = Service(
            business_id=other_business.id,
            name="Other Service",
            duration_min=30,
            price_cents=10000,
        )
        db.session.add_all([member, other_member, offering, foreign_offering])
        db.session.flush()
        db.session.add_all(
            [
                Membership(user_id=users[0].id, business_id=business.id, role="owner"),
                Membership(user_id=users[1].id, business_id=business.id, role="staff"),
                Membership(user_id=users[3].id, business_id=other_business.id, role="owner"),
            ]
        )
        for staff_id in (member.id, other_member.id):
            db.session.execute(
                staff_services.insert().values(staff_id=staff_id, service_id=offering.id)
            )
            if staff_id == member.id:
                db.session.add_all(
                [
                    WorkingHours(
                        staff_id=staff_id,
                        weekday=6,
                        start_time=time(22),
                        end_time=time(23, 59),
                    ),
                    WorkingHours(
                        staff_id=staff_id,
                        weekday=0,
                        start_time=time(0),
                        end_time=time(2),
                    ),
                    ]
                )
        # The one work window has a short time-off interval for utilization checks.
        db.session.add(
            TimeOff(
                staff_id=member.id,
                during=Range(
                    datetime(2025, 1, 5, 22, 30, tzinfo=UTC),
                    datetime(2025, 1, 5, 23, 0, tzinfo=UTC),
                    "[)",
                ),
                reason="break",
            )
        )
        # Local Sunday 23:30 crosses local midnight; its UTC start is Sunday 21:30.
        specs = [
            (datetime(2025, 1, 5, 21, 30, tzinfo=UTC), "completed", 18000),
            (datetime(2025, 1, 5, 22, 30, tzinfo=UTC), "no_show", 18000),
            (datetime(2025, 1, 5, 23, 30, tzinfo=UTC), "cancelled", 9000),
            (datetime(2025, 1, 6, 0, 30, tzinfo=UTC), "confirmed", 18000),
        ]
        bookings = []
        for start, status, price in specs:
            booking = Booking(
                business_id=business.id,
                customer_id=users[2].id,
                staff_id=member.id,
                service_id=offering.id,
                start_at=start,
                end_at=start + timedelta(minutes=60),
                blocked_until=start + timedelta(minutes=60),
                status=status,
                price_cents=price,
                deposit_cents=500 if status == "completed" else 0,
            )
            bookings.append(booking)
        db.session.add_all(bookings)
        db.session.flush()
        db.session.add(
            Payment(
                booking_id=bookings[0].id,
                provider="payfast",
                provider_ref="insights-paid",
                amount_cents=500,
                status="paid",
                created_at=datetime(2025, 1, 5, 21, 45, tzinfo=UTC),
            )
        )
        db.session.add(
            AuditLog(
                actor_id=users[0].id,
                business_id=business.id,
                entity="payment",
                entity_id=1,
                action="safe",
                diff={
                    "status": "paid",
                    "nested": {
                        "password_hash": "do-not-return",
                        "token": "token-secret",
                        "signature": "sig-secret",
                        "merchant_key": "merchant-secret",
                        "passphrase": "phrase-secret",
                        "raw_payload": {"email_address": "private@example.test"},
                    },
                },
            )
        )
        db.session.commit()
        return {
            "users": [item.id for item in users],
            "business_id": business.id,
            "other_business_id": other_business.id,
            "staff_id": member.id,
            "other_staff_id": other_member.id,
            "service_id": offering.id,
            "bookings": [item.id for item in bookings],
        }


def _calendar(client, business_id, day="2025-01-05"):
    return client.get(f"/api/admin/businesses/{business_id}/calendar?date={day}")


def test_calendar_role_matrix_and_timezone_midnight(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    staff, _ = client_for(app, data["users"][1])
    other_owner, _ = client_for(app, data["users"][3])
    customer, _ = client_for(app, data["users"][2])
    anonymous = app.test_client()

    owner_response = _calendar(owner, data["business_id"])
    assert owner_response.status_code == 200
    columns = owner_response.json["data"]["staff"]
    assert len(columns) == 2
    assert any(
        item["local_start"].startswith("2025-01-05T23:30")
        for item in columns[0]["bookings"]
    )

    staff_response = _calendar(staff, data["business_id"])
    assert staff_response.status_code == 200
    assert [item["id"] for item in staff_response.json["data"]["staff"]] == [
        data["staff_id"]
    ]
    assert _calendar(other_owner, data["business_id"]).status_code == 404
    assert _calendar(customer, data["business_id"]).status_code == 404
    assert _calendar(anonymous, data["business_id"]).status_code == 401
    assert _calendar(owner, data["other_business_id"]).status_code == 404

    week = owner.get(
        f"/api/admin/businesses/{data['business_id']}/calendar/week?start=2025-01-05"
    )
    assert week.status_code == 200
    assert len(week.json["data"]["staff"][0]["days"]) == 7
    sunday, monday = week.json["data"]["staff"][0]["days"][:2]
    assert (sunday["date"], sunday["bookings"]) == ("2025-01-05", 1)
    assert (monday["date"], monday["bookings"]) == ("2025-01-06", 3)


def test_analytics_summary_matches_hand_calculated_local_range(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    base = f"/api/admin/businesses/{data['business_id']}/analytics"
    response = owner.get(f"{base}/summary?from=2025-01-05&to=2025-01-06")
    assert response.status_code == 200, response.json
    current = response.json["data"]["current"]
    assert current["bookings"] == 4
    assert current["revenue_cents"] == 18000
    assert current["deposits_collected_cents"] == 500
    assert current["no_show_rate_percent"] == 25
    assert current["cancellation_rate_percent"] == 25
    assert current["available_minutes"] == 209, owner.get(
        f"{base}/utilisation?from=2025-01-05&to=2025-01-06"
    ).json
    assert current["booked_minutes"] == 119
    assert current["fill_rate_percent"] == 56.94
    assert response.json["data"]["change_percent"]["bookings"] is None

    outcomes = owner.get(f"{base}/outcomes?from=2025-01-05&to=2025-01-06")
    assert outcomes.json["data"] == {
        "created": 4,
        "confirmed": 1,
        "completed": 1,
        "cancelled": 1,
        "no_show": 1,
        "funnel_note": "Page-view and booking-start funnel steps are not tracked.",
    }


def test_analytics_timeseries_zero_fill_heatmap_and_range_limit(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    base = f"/api/admin/businesses/{data['business_id']}/analytics"
    series = owner.get(
        f"{base}/timeseries?metric=bookings&interval=day&from=2025-01-05&to=2025-01-08"
    )
    assert series.status_code == 200
    assert [row["bookings"] for row in series.json["data"]] == [1, 3, 0, 0]
    heatmap = owner.get(f"{base}/heatmap?from=2025-01-05&to=2025-01-06")
    assert heatmap.status_code == 200
    assert any(row["weekday"] == 6 and row["hour"] == 23 and row["count"] == 1
               for row in heatmap.json["data"])
    too_long = owner.get(
        f"{base}/summary?from=2024-01-01&to=2025-01-02"
    )
    assert too_long.status_code == 422
    zero_prev = owner.get(
        f"{base}/summary?from=2025-01-05&to=2025-01-06"
    )
    assert zero_prev.json["data"]["change_percent"]["revenue_cents"] is None


def test_customer_search_wildcards_and_audit_secret_fields(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    base = f"/api/admin/businesses/{data['business_id']}"
    literal = owner.get(f"{base}/customers?search=%25&sort=name")
    assert literal.status_code == 200
    assert literal.json["data"] == []
    injection = owner.get(f"{base}/customers?search=%25%27%20OR%201%3D1--")
    assert injection.status_code == 200
    assert injection.json["data"] == []
    customer_id = data["users"][2]
    detail = owner.get(f"{base}/customers/{customer_id}")
    assert detail.status_code == 200
    assert len(detail.json["data"]["bookings"]) == 4
    audit = owner.get(f"{base}/audit-log?entity=payment")
    assert audit.status_code == 200
    serialized = str(audit.json).lower()
    for secret in ("password_hash", "token-secret", "sig-secret", "merchant-secret",
                   "phrase-secret", "raw_payload", "private@example.test"):
        assert secret not in serialized


def test_insights_owner_staff_and_other_tenant_permissions(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    staff, _ = client_for(app, data["users"][1])
    other_owner, _ = client_for(app, data["users"][3])
    customer, _ = client_for(app, data["users"][2])
    anonymous = app.test_client()
    endpoints = [
        "analytics/summary?from=2025-01-05&to=2025-01-06",
        "analytics/timeseries?metric=bookings&interval=day&from=2025-01-05&to=2025-01-06",
        "analytics/status-mix?from=2025-01-05&to=2025-01-06",
        "analytics/heatmap?from=2025-01-05&to=2025-01-06",
        "analytics/utilisation?from=2025-01-05&to=2025-01-06",
        "analytics/outcomes?from=2025-01-05&to=2025-01-06",
        "customers",
        "audit-log",
    ]
    for endpoint in endpoints:
        path = f"/api/admin/businesses/{data['business_id']}/{endpoint}"
        assert owner.get(path).status_code == 200
        assert staff.get(path).status_code == 404
        assert other_owner.get(path).status_code == 404
        assert customer.get(path).status_code == 404
        assert anonymous.get(path).status_code == 401


def test_analytics_queries_remain_fixed_as_booking_volume_grows(insights_data, app):
    data = insights_data
    owner, _ = client_for(app, data["users"][0])
    endpoints = [
        f"/api/admin/businesses/{data['business_id']}/analytics/summary?from=2025-01-05&to=2025-01-06",
        f"/api/admin/businesses/{data['business_id']}/analytics/timeseries?metric=bookings&interval=day&from=2025-01-05&to=2025-01-06",
        f"/api/admin/businesses/{data['business_id']}/analytics/status-mix?from=2025-01-05&to=2025-01-06",
        f"/api/admin/businesses/{data['business_id']}/analytics/heatmap?from=2025-01-05&to=2025-01-06",
        f"/api/admin/businesses/{data['business_id']}/analytics/utilisation?from=2025-01-05&to=2025-01-06",
        f"/api/admin/businesses/{data['business_id']}/analytics/outcomes?from=2025-01-05&to=2025-01-06",
    ]

    def measure(path):
        count = 0
        guard = Lock()

        def before_cursor(*_):
            nonlocal count
            with guard:
                count += 1

        with app.app_context():
            engine = db.engine
        event.listen(engine, "before_cursor_execute", before_cursor)
        try:
            response = owner.get(path)
            assert response.status_code == 200, response.json
        finally:
            event.remove(engine, "before_cursor_execute", before_cursor)
        return count

    before = [measure(path) for path in endpoints]
    with app.app_context():
        start = datetime(2025, 1, 5, 20, 0, tzinfo=UTC)
        db.session.add_all(
            [
                Booking(
                    business_id=data["business_id"],
                    customer_id=data["users"][2],
                    staff_id=data["staff_id"],
                    service_id=data["service_id"],
                    start_at=start + timedelta(minutes=index),
                    end_at=start + timedelta(minutes=index + 1),
                    blocked_until=start + timedelta(minutes=index + 1),
                    status="cancelled",
                    price_cents=100,
                )
                for index in range(20)
            ]
        )
        db.session.commit()
    after = [measure(path) for path in endpoints]
    assert after == before


def test_demo_seed_is_idempotent_resets_only_demo_and_obeys_environment(app):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed-demo"])
    assert first.exit_code == 0, first.output
    with app.app_context():
        business_id = db.session.execute(
            select(Business.id).where(Business.slug == "fade-lab")
        ).scalar_one()
        counts = db.session.execute(
            select(
                db.func.count(Booking.id),
                db.func.count(db.distinct(Booking.customer_id)),
            ).where(Booking.business_id == business_id)
        ).one()
        assert counts[0] > 100
        assert counts[1] >= 20
        db.session.add(Business(slug="keep-this-business", name="Keep"))
        db.session.commit()
    second = runner.invoke(args=["seed-demo"])
    assert second.exit_code == 0, second.output
    with app.app_context():
        assert db.session.execute(
            select(db.func.count(Booking.id)).where(Booking.business_id == business_id)
        ).scalar_one() == counts[0]
    reset = runner.invoke(args=["seed-demo", "--reset"])
    assert reset.exit_code == 0, reset.output
    with app.app_context():
        assert db.session.execute(
            select(Business.id).where(Business.slug == "keep-this-business")
        ).scalar_one_or_none() is not None
        business_id = db.session.execute(
            select(Business.id).where(Business.slug == "fade-lab")
        ).scalar_one()
        reset_count = db.session.execute(
            select(db.func.count(Booking.id)).where(Booking.business_id == business_id)
        ).scalar_one()
        assert reset_count > 100, reset.output
        seeded = db.session.execute(
            select(Booking)
            .where(
                Booking.business_id == business_id,
                Booking.status.in_(("pending", "confirmed")),
            )
            .limit(1)
        ).scalar_one()
        overlap = Booking(
            business_id=seeded.business_id,
            customer_id=seeded.customer_id,
            staff_id=seeded.staff_id,
            service_id=seeded.service_id,
            start_at=seeded.start_at,
            end_at=seeded.end_at,
            blocked_until=seeded.blocked_until,
            status="confirmed",
            price_cents=seeded.price_cents,
        )
        db.session.add(overlap)
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_demo_seed_refuses_production(app):
    app.config["APP_ENV"] = "production"
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code != 0
    assert "disabled in production" in result.output
