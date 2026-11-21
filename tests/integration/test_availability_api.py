"""PostgreSQL integration tests for batched public availability reads."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.extensions import db
from app.models import (
    Booking,
    Business,
    Service,
    Staff,
    User,
    WorkingHours,
    staff_services,
)
from app.services.demo_seed import seed_demo
from sqlalchemy import event, select, update


def test_demo_seed_preserves_a_future_deposit_slot(app, client):
    with app.app_context():
        seed_demo(reset=True)
        business = db.session.execute(
            select(Business).where(Business.slug == "fade-lab")
        ).scalar_one()
        service = db.session.execute(
            select(Service).where(
                Service.business_id == business.id,
                Service.name == "Fade and beard",
            )
        ).scalar_one()
        member = db.session.execute(
            select(Staff).where(
                Staff.business_id == business.id,
                Staff.display_name == "Lerato",
            )
        ).scalar_one()
        day = datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=7)
        while day.weekday() >= 5:
            day += timedelta(days=1)

    response = client.get(
        f"/api/b/fade-lab/slots?service={service.id}&staff={member.id}&date={day.isoformat()}"
    )
    assert response.status_code == 200
    assert response.json["data"]["slots"]
    assert response.json["data"]["slots"][0]["local_start"].endswith("15:30")


@pytest.fixture
def catalog(app):
    day = date.today() + timedelta(days=5)
    with app.app_context():
        business = Business(
            slug="availability-shop", name="Availability", timezone="UTC", slot_step_min=15
        )
        customer = User(
            email="availability-customer@example.test", password_hash="unused", full_name="Customer"
        )
        service = Service(
            business_id=1, name="Cut", duration_min=30, buffer_min=0, price_cents=1000
        )
        # Flush parent IDs rather than relying on reset sequence values.
        db.session.add_all([business, customer])
        db.session.flush()
        service.business_id = business.id
        member = Staff(business_id=business.id, display_name="Sam")
        other = Staff(business_id=business.id, display_name="Lee")
        db.session.add_all([service, member, other])
        db.session.flush()
        db.session.execute(
            staff_services.insert().values(staff_id=member.id, service_id=service.id)
        )
        db.session.add(
            WorkingHours(
                staff_id=member.id,
                weekday=day.weekday(),
                start_time=time(9),
                end_time=time(11),
            )
        )
        db.session.commit()
        result = {
            "business_id": business.id,
            "customer_id": customer.id,
            "service_id": service.id,
            "staff_id": member.id,
            "other_staff_id": other.id,
            "slug": business.slug,
            "day": day,
        }
        yield result
        db.session.remove()


def test_slots_can_be_inserted_and_booking_removes_conflicting_starts(client, catalog, app):
    path = (
        f"/api/b/{catalog['slug']}/slots?service={catalog['service_id']}"
        f"&staff=any&date={catalog['day']}"
    )
    response = client.get(path)
    assert response.status_code == 200
    payload = response.json["data"]
    assert payload["timezone"] == "UTC"
    slots = payload["slots"]
    assert len(slots) == 7
    chosen = slots[0]
    with app.app_context():
        start = datetime.fromisoformat(chosen["start_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(chosen["end_at"].replace("Z", "+00:00"))
        db.session.add(
            Booking(
                business_id=catalog["business_id"],
                customer_id=catalog["customer_id"],
                staff_id=chosen["staff_ids"][0],
                service_id=catalog["service_id"],
                start_at=start,
                end_at=end,
                blocked_until=end,
                status="confirmed",
                price_cents=1000,
            )
        )
        db.session.commit()
    after = client.get(path).json["data"]["slots"]
    starts = {item["start_at"] for item in after}
    assert chosen["start_at"] not in starts
    assert slots[1]["start_at"] not in starts


def test_inactive_and_unassigned_resources_and_business_id_mixing(client, catalog, app):
    base = f"/api/b/{catalog['slug']}"
    query = f"service={catalog['service_id']}&date={catalog['day']}"
    assert client.get(f"{base}/slots?{query}&staff={catalog['other_staff_id']}").status_code == 422
    assert client.get(f"/api/b/missing-shop/slots?{query}&staff=any").status_code == 404

    with app.app_context():
        other_business = Business(slug="other-availability", name="Other")
        db.session.add(other_business)
        db.session.flush()
        foreign_service = Service(
            business_id=other_business.id,
            name="Foreign",
            duration_min=20,
            price_cents=0,
        )
        db.session.add(foreign_service)
        foreign_staff = Staff(business_id=other_business.id, display_name="Foreign")
        db.session.add(foreign_staff)
        db.session.commit()
        foreign_service_id = foreign_service.id
        foreign_staff_id = foreign_staff.id
        db.session.execute(
            update(Service).where(Service.id == catalog["service_id"]).values(active=False)
        )
        db.session.commit()
    assert (
        client.get(
            f"{base}/slots?service={catalog['service_id']}&staff=any&date={catalog['day']}"
        ).json["data"]["slots"]
        == []
    )
    with app.app_context():
        db.session.execute(
            update(Service).where(Service.id == catalog["service_id"]).values(active=True)
        )
        db.session.execute(
            update(Staff).where(Staff.id == catalog["staff_id"]).values(active=False)
        )
        db.session.commit()
    assert (
        client.get(
            f"{base}/slots?service={catalog['service_id']}&staff=any&date={catalog['day']}"
        ).json["data"]["slots"]
        == []
    )
    assert (
        client.get(
            f"{base}/slots?service={foreign_service_id}&staff=any&date={catalog['day']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{base}/slots?service={catalog['service_id']}&staff={foreign_staff_id}&date={catalog['day']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{base}/slots?service={catalog['service_id']}&staff={catalog['staff_id']}&date={catalog['day']}"
        ).json["data"]["slots"]
        == []
    )


def test_availability_counts_match_slots_and_uses_fixed_query_count(client, catalog, app):
    day = catalog["day"]
    end = day + timedelta(days=30)
    args = f"service={catalog['service_id']}&staff=any&from={day}&to={end}"
    statements = []

    def count_query(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            response = client.get(f"/api/b/{catalog['slug']}/availability?{args}")
        finally:
            event.remove(db.engine, "before_cursor_execute", count_query)
    assert response.status_code == 200
    assert len(statements) <= 6
    rows = response.json["data"]["days"]
    row = next(item for item in rows if item["date"] == day.isoformat())
    slots = client.get(
        f"/api/b/{catalog['slug']}/slots?service={catalog['service_id']}&staff=any&date={day}"
    ).json["data"]["slots"]
    assert row["open_slots"] == len(slots)
    assert row["open"] is bool(slots)


def test_availability_validation_and_past_date(client, catalog):
    base = f"/api/b/{catalog['slug']}"
    assert (
        client.get(f"{base}/slots?service={catalog['service_id']}&date=tomorrow").status_code == 422
    )
    assert (
        client.get(
            f"{base}/availability?service={catalog['service_id']}&from=2026-01-01&to=2026-03-10"
        ).status_code
        == 422
    )
    past = date.today() - timedelta(days=2)
    response = client.get(f"{base}/slots?service={catalog['service_id']}&staff=any&date={past}")
    assert response.status_code == 200
    assert response.json["data"]["slots"] == []
