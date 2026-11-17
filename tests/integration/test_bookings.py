"""PostgreSQL booking lifecycle integration tests."""

import json
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from hashlib import md5
from urllib.parse import quote_plus, urlencode

import pytest
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
from app.services import bookings as booking_service
from app.services import notification_jobs
from app.services import payments as payment_service
from app.services.payfast import format_cents, generate_form_signature
from psycopg.types.range import Range
from sqlalchemy import select
from sqlalchemy.orm import Session


class BookingEmailService:
    def __init__(self):
        self.sent = []
        self.notifications = []
        self.fail = False

    def send_verification(self, user, token):
        pass

    def send_password_reset(self, user, token):
        pass

    def send_booking_confirmation(self, user, booking, business, service):
        if self.fail:
            raise RuntimeError("mail provider unavailable")
        self.sent.append(booking.id)

    def send_notification_email(self, user, subject, text_body, html_body):
        if self.fail:
            raise RuntimeError("mail provider unavailable")
        self.notifications.append((user.id, subject, text_body, html_body))


@pytest.fixture
def email_service(app):
    original = app.extensions["email_service"]
    recorder = BookingEmailService()
    app.extensions["email_service"] = recorder
    yield recorder
    app.extensions["email_service"] = original


@pytest.fixture
def scenario(app):
    now = datetime.now(UTC)
    booking_day = now.date() + timedelta(days=5)
    with app.app_context():
        users = [
            User(
                email=f"booker{i}@example.test",
                password_hash=f"hash-{i}",
                full_name=f"User {i}",
                verified_at=now,
            )
            for i in range(12)
        ]
        business = Business(slug="bookable-shop", name="Bookable", timezone="UTC", slot_step_min=15)
        other_business = Business(
            slug="other-bookable", name="Other", timezone="UTC", slot_step_min=15
        )
        db.session.add_all([*users, business, other_business])
        db.session.flush()
        members = [
            Staff(business_id=business.id, user_id=users[3].id, display_name="One"),
            Staff(business_id=business.id, display_name="Two"),
        ]
        foreign_staff = Staff(business_id=other_business.id, display_name="Foreign")
        no_deposit = Service(
            business_id=business.id,
            name="Cut",
            duration_min=30,
            buffer_min=15,
            price_cents=1000,
            deposit_cents=0,
        )
        deposit = Service(
            business_id=business.id,
            name="Color",
            duration_min=30,
            buffer_min=0,
            price_cents=2000,
            deposit_cents=500,
        )
        foreign_service = Service(
            business_id=other_business.id,
            name="Foreign cut",
            duration_min=30,
            price_cents=1000,
        )
        db.session.add_all([*members, foreign_staff, no_deposit, deposit, foreign_service])
        db.session.flush()
        db.session.add_all(
            [
                Membership(user_id=users[2].id, business_id=business.id, role="owner"),
                Membership(user_id=users[3].id, business_id=business.id, role="staff"),
            ]
        )
        for staff in members:
            for offering in (no_deposit, deposit):
                db.session.execute(
                    staff_services.insert().values(staff_id=staff.id, service_id=offering.id)
                )
            db.session.add(
                WorkingHours(
                    staff_id=staff.id,
                    weekday=booking_day.weekday(),
                    start_time=time(9),
                    end_time=time(12),
                )
            )
        db.session.execute(
            staff_services.insert().values(staff_id=foreign_staff.id, service_id=foreign_service.id)
        )
        db.session.commit()
        result = {
            "users": [user.id for user in users],
            "business_id": business.id,
            "other_business_id": other_business.id,
            "slug": business.slug,
            "other_slug": other_business.slug,
            "staff_ids": [staff.id for staff in members],
            "foreign_staff_id": foreign_staff.id,
            "service_id": no_deposit.id,
            "deposit_service_id": deposit.id,
            "foreign_service_id": foreign_service.id,
            "day": booking_day,
        }
        yield result
        db.session.remove()


def client_for(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        sid = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        session_data = {
            "_user_id": user.id,
            "_auth_version": user.password_hash,
            "_csrf_token": csrf,
        }
        app.extensions["redis"].set(
            app.session_interface._key(sid),
            json.dumps(session_data),
            ex=app.config["SERVER_SESSION_TTL_SECONDS"],
        )
    client = app.test_client()
    client.set_cookie(app.config["SESSION_COOKIE_NAME"], sid)
    return client, csrf


def available_slots(client, scenario, service_id=None, staff="any"):
    service_id = service_id or scenario["service_id"]
    response = client.get(
        f"/api/b/{scenario['slug']}/slots?service={service_id}&staff={staff}&date={scenario['day']}"
    )
    assert response.status_code == 200, response.json
    return response.json["data"]["slots"]


def post_booking(client, csrf, scenario, start_at, service_id=None, staff="any"):
    return client.post(
        f"/api/b/{scenario['slug']}/bookings",
        json={
            "service_id": service_id or scenario["service_id"],
            "staff_id": staff,
            "start_at": start_at,
        },
        headers={"X-CSRF-Token": csrf},
    )


def seed_booking(
    scenario,
    *,
    start_at,
    staff_id=None,
    customer_id=None,
    service_id=None,
    status="confirmed",
    hold_expires_at=None,
):
    staff_id = staff_id or scenario["staff_ids"][0]
    service_id = service_id or scenario["service_id"]
    customer_id = customer_id or scenario["users"][0]
    with db.session.no_autoflush:
        offering = db.session.get(Service, service_id)
        end_at = start_at + timedelta(minutes=offering.duration_min)
        booking = Booking(
            business_id=scenario["business_id"],
            customer_id=customer_id,
            staff_id=staff_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            blocked_until=end_at + timedelta(minutes=offering.buffer_min),
            status=status,
            hold_expires_at=hold_expires_at,
            price_cents=offering.price_cents,
            deposit_cents=offering.deposit_cents,
        )
        db.session.add(booking)
        db.session.commit()
        db.session.refresh(booking)
        return booking.id


def test_no_deposit_booking_is_confirmed_retry_is_idempotent_and_price_is_snapshotted(
    app, scenario, email_service
):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    response = post_booking(client, csrf, scenario, slot["start_at"])
    assert response.status_code == 201
    booking = response.json["data"]
    assert booking["status"] == "confirmed"
    assert booking["price_cents"] == 1000
    with app.app_context():
        rows = db.session.execute(
            select(Notification).where(Notification.booking_id == booking["id"])
        ).scalars().all()
        assert {row.kind for row in rows} == {"confirmation", "reminder_24h", "reminder_2h"}
    assert email_service.sent == []

    retry = post_booking(client, csrf, scenario, slot["start_at"])
    assert retry.status_code == 200
    assert retry.json["data"]["id"] == booking["id"]
    assert email_service.sent == []
    with app.app_context():
        db.session.get(Service, scenario["service_id"]).price_cents = 1800
        db.session.commit()
        persisted = db.session.get(Booking, booking["id"])
        assert persisted.price_cents == 1000
        audit = (
            db.session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "booking", AuditLog.entity_id == booking["id"]
                )
            )
            .scalars()
            .all()
        )
        assert [item.action for item in audit] == ["create"]


def test_deposit_booking_creates_pending_hold(app, scenario, email_service):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario, scenario["deposit_service_id"])[0]
    response = post_booking(
        client, csrf, scenario, slot["start_at"], scenario["deposit_service_id"]
    )
    assert response.status_code == 201
    assert response.json["data"]["status"] == "pending"
    assert response.json["data"]["deposit_cents"] == 500
    expiry = datetime.fromisoformat(response.json["data"]["hold_expires_at"].replace("Z", "+00:00"))
    assert expiry > datetime.now(UTC)


@pytest.mark.parametrize("invalid_kind", ["off_grid", "outside", "time_off", "past", "notice"])
def test_invalid_start_returns_not_available(app, scenario, invalid_kind):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    requested = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
    if invalid_kind == "off_grid":
        requested += timedelta(minutes=1)
    elif invalid_kind == "outside":
        requested = datetime.combine(scenario["day"], time(8), tzinfo=UTC)
    elif invalid_kind == "past":
        requested = datetime.now(UTC) - timedelta(days=1)
    elif invalid_kind == "notice":
        app.config["AVAILABILITY_MINIMUM_NOTICE_MINUTES"] = 6 * 24 * 60
    elif invalid_kind == "time_off":
        with app.app_context():
            for staff_id in scenario["staff_ids"]:
                db.session.add(
                    TimeOff(
                        staff_id=staff_id,
                        during=Range(requested, requested + timedelta(hours=3), "[)"),
                    )
                )
            db.session.commit()
    response = post_booking(client, csrf, scenario, requested.isoformat().replace("+00:00", "Z"))
    if invalid_kind == "notice":
        app.config["AVAILABILITY_MINIMUM_NOTICE_MINUTES"] = 120
    assert response.status_code == 422
    assert response.json["error"]["code"] == "not_available"


def test_expired_hold_is_cancelled_and_replaced_but_active_hold_blocks(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(
        client, scenario, scenario["deposit_service_id"], staff=scenario["staff_ids"][0]
    )[0]
    start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
    with app.app_context():
        expired_id = seed_booking(
            scenario,
            start_at=start,
            staff_id=scenario["staff_ids"][0],
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    response = post_booking(
        client,
        csrf,
        scenario,
        slot["start_at"],
        scenario["deposit_service_id"],
        scenario["staff_ids"][0],
    )
    assert response.status_code == 201
    with app.app_context():
        assert db.session.get(Booking, expired_id).status == "cancelled"
        audit = (
            db.session.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == expired_id, AuditLog.entity == "booking"
                )
            )
            .scalars()
            .all()
        )
        assert any(item.action == "transition" for item in audit)

    active_slot = available_slots(
        client, scenario, scenario["deposit_service_id"], staff=scenario["staff_ids"][0]
    )[1]
    active_start = datetime.fromisoformat(active_slot["start_at"].replace("Z", "+00:00"))
    with app.app_context():
        seed_booking(
            scenario,
            start_at=active_start,
            staff_id=scenario["staff_ids"][0],
            customer_id=scenario["users"][1],
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    blocked = post_booking(
        client,
        csrf,
        scenario,
        active_slot["start_at"],
        scenario["deposit_service_id"],
        scenario["staff_ids"][0],
    )
    assert blocked.status_code == 409
    assert blocked.json["error"]["code"] == "slot_taken"


def test_any_staff_falls_through_after_exclusion_conflict(app, scenario, monkeypatch):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    first_staff = scenario["staff_ids"][0]
    original_transition = booking_service.transition
    raced = False

    def inject_conflict(booking, new_status, actor):
        nonlocal raced
        if not raced:
            raced = True
            with Session(db.engine) as separate_session:
                customer = separate_session.get(User, scenario["users"][1])
                offering = separate_session.get(Service, scenario["service_id"])
                start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
                end = start + timedelta(minutes=offering.duration_min)
                separate_session.add(
                    Booking(
                        business_id=scenario["business_id"],
                        customer_id=customer.id,
                        staff_id=first_staff,
                        service_id=offering.id,
                        start_at=start,
                        end_at=end,
                        blocked_until=end + timedelta(minutes=offering.buffer_min),
                        status="confirmed",
                        price_cents=offering.price_cents,
                    )
                )
                separate_session.commit()
        return original_transition(booking, new_status, actor)

    monkeypatch.setattr(booking_service, "transition", inject_conflict)
    response = post_booking(client, csrf, scenario, slot["start_at"])
    assert response.status_code == 201
    assert response.json["data"]["staff_id"] == scenario["staff_ids"][1]


def test_ten_simultaneous_same_staff_attempts_have_one_success_and_no_500s(
    app, scenario, monkeypatch
):
    slot = available_slots(app.test_client(), scenario, staff=scenario["staff_ids"][0])[0]
    original_create = booking_service.create_booking
    sessions = []
    sessions_lock = threading.Lock()

    def record_session(*args, **kwargs):
        session = db.session()
        with sessions_lock:
            sessions.append(session)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(booking_service, "create_booking", record_session)

    def attempt(user_id):
        client, csrf = client_for(app, user_id)
        response = post_booking(
            client, csrf, scenario, slot["start_at"], staff=scenario["staff_ids"][0]
        )
        return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, scenario["users"][:10]))
    statuses = [status for status, _ in results]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 9
    assert 500 not in statuses
    assert len({id(session) for session in sessions}) == 10


def test_expired_hold_race_has_one_success_one_conflict_and_no_server_error(
    app, scenario, monkeypatch
):
    client, _ = client_for(app, scenario["users"][0])
    slot = available_slots(
        client, scenario, scenario["deposit_service_id"], staff=scenario["staff_ids"][0]
    )[0]
    start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
    with app.app_context():
        expired_id = seed_booking(
            scenario,
            start_at=start,
            staff_id=scenario["staff_ids"][0],
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    barrier = threading.Barrier(2)
    original_availability = booking_service._availability

    def wait_until_both_loaded(*args, **kwargs):
        result = original_availability(*args, **kwargs)
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(booking_service, "_availability", wait_until_both_loaded)

    def attempt(user_id):
        request_client, csrf = client_for(app, user_id)
        response = post_booking(
            request_client,
            csrf,
            scenario,
            slot["start_at"],
            scenario["deposit_service_id"],
            scenario["staff_ids"][0],
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, scenario["users"][:2]))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 1
    assert 500 not in statuses
    with app.app_context():
        assert db.session.get(Booking, expired_id).status == "cancelled"


def test_all_any_staff_candidates_taken_returns_409(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
    with app.app_context():
        for staff_id in scenario["staff_ids"]:
            seed_booking(
                scenario,
                start_at=start,
                staff_id=staff_id,
                customer_id=scenario["users"][1],
            )
    response = post_booking(client, csrf, scenario, slot["start_at"])
    assert response.status_code == 409
    assert response.json["error"]["code"] == "slot_taken"


def test_pending_hold_cap_limits_only_deposit_bookings(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    app.config["MAX_PENDING_HOLDS_PER_USER"] = 1
    slots = available_slots(client, scenario, scenario["deposit_service_id"])
    first = post_booking(
        client, csrf, scenario, slots[0]["start_at"], scenario["deposit_service_id"]
    )
    assert first.status_code == 201
    next_slot = next(
        item for item in slots if item["start_at"] not in {x["start_at"] for x in slots[:3]}
    )
    second = post_booking(
        client, csrf, scenario, next_slot["start_at"], scenario["deposit_service_id"]
    )
    assert second.status_code == 422
    assert second.json["error"]["code"] == "too_many_holds"


def test_cancel_cutoff_and_owner_cancellation_inside_cutoff(app, scenario):
    customer, customer_csrf = client_for(app, scenario["users"][0])
    owner, owner_csrf = client_for(app, scenario["users"][2])
    future_slot = available_slots(customer, scenario)[0]
    future_booking = post_booking(customer, customer_csrf, scenario, future_slot["start_at"])
    assert future_booking.status_code == 201
    before_cutoff = customer.patch(
        f"/api/bookings/{future_booking.json['data']['id']}",
        json={"action": "cancel"},
        headers={"X-CSRF-Token": customer_csrf},
    )
    assert before_cutoff.status_code == 200
    assert before_cutoff.json["data"]["status"] == "cancelled"
    soon = datetime.now(UTC) + timedelta(hours=12)
    with app.app_context():
        late_id = seed_booking(scenario, start_at=soon)
        owner_cancel_id = seed_booking(
            scenario,
            start_at=soon + timedelta(hours=2),
            staff_id=scenario["staff_ids"][1],
            customer_id=scenario["users"][1],
        )
    late = customer.patch(
        f"/api/bookings/{late_id}",
        json={"action": "cancel"},
        headers={"X-CSRF-Token": customer_csrf},
    )
    assert late.status_code == 403
    assert late.json["error"]["code"] == "late_cancellation"
    assert "under 24 hours" in late.json["error"]["message"]
    owner_response = owner.patch(
        f"/api/bookings/{owner_cancel_id}",
        json={"action": "cancel"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert owner_response.status_code == 200
    assert owner_response.json["data"]["status"] == "cancelled"


def test_reschedule_overlapping_own_slot_succeeds_and_taken_slot_rolls_back(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    slots = available_slots(client, scenario, staff=scenario["staff_ids"][0])
    first = post_booking(
        client, csrf, scenario, slots[0]["start_at"], staff=scenario["staff_ids"][0]
    )
    second = post_booking(
        client, csrf, scenario, slots[4]["start_at"], staff=scenario["staff_ids"][0]
    )
    assert first.status_code == second.status_code == 201
    booking_id = first.json["data"]["id"]
    moved = datetime.fromisoformat(slots[1]["start_at"].replace("Z", "+00:00"))
    response = client.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "reschedule", "start_at": moved.isoformat().replace("+00:00", "Z")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json["data"]["start_at"] == slots[1]["start_at"]

    with app.app_context():
        original = db.session.get(Booking, booking_id)
        before = {
            "business_id": original.business_id,
            "customer_id": original.customer_id,
            "staff_id": original.staff_id,
            "service_id": original.service_id,
            "start_at": original.start_at,
            "end_at": original.end_at,
            "blocked_until": original.blocked_until,
            "status": original.status,
            "hold_expires_at": original.hold_expires_at,
            "price_cents": original.price_cents,
            "deposit_cents": original.deposit_cents,
            "audit": [
                (row.id, row.action, row.diff)
                for row in db.session.execute(
                    select(AuditLog).where(
                        AuditLog.entity == "booking", AuditLog.entity_id == booking_id
                    )
                ).scalars()
            ],
            "notifications": [
                (row.id, row.kind, row.scheduled_for, row.sent_at, row.status)
                for row in db.session.execute(
                    select(Notification).where(Notification.booking_id == booking_id)
                ).scalars()
            ],
        }
    conflict = client.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "reschedule", "start_at": slots[4]["start_at"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert conflict.status_code == 409
    with app.app_context():
        unchanged = db.session.get(Booking, booking_id)
        after = {
            "business_id": unchanged.business_id,
            "customer_id": unchanged.customer_id,
            "staff_id": unchanged.staff_id,
            "service_id": unchanged.service_id,
            "start_at": unchanged.start_at,
            "end_at": unchanged.end_at,
            "blocked_until": unchanged.blocked_until,
            "status": unchanged.status,
            "hold_expires_at": unchanged.hold_expires_at,
            "price_cents": unchanged.price_cents,
            "deposit_cents": unchanged.deposit_cents,
            "audit": [
                (row.id, row.action, row.diff)
                for row in db.session.execute(
                    select(AuditLog).where(
                        AuditLog.entity == "booking", AuditLog.entity_id == booking_id
                    )
                ).scalars()
            ],
            "notifications": [
                (row.id, row.kind, row.scheduled_for, row.sent_at, row.status)
                for row in db.session.execute(
                    select(Notification).where(Notification.booking_id == booking_id)
                ).scalars()
            ],
        }
        assert after == before


def test_permission_matrix_and_customer_booking_reads(app, scenario):
    owner, owner_csrf = client_for(app, scenario["users"][2])
    customer, customer_csrf = client_for(app, scenario["users"][0])
    other_customer, other_csrf = client_for(app, scenario["users"][1])
    slot = available_slots(customer, scenario, staff=scenario["staff_ids"][0])[0]
    created = post_booking(
        customer, customer_csrf, scenario, slot["start_at"], staff=scenario["staff_ids"][0]
    )
    booking_id = created.json["data"]["id"]
    assert customer.get(f"/api/me/bookings/{booking_id}").status_code == 200
    assert other_customer.get(f"/api/me/bookings/{booking_id}").status_code == 404
    assert (
        other_customer.patch(
            f"/api/bookings/{booking_id}",
            json={"action": "cancel"},
            headers={"X-CSRF-Token": other_csrf},
        ).status_code
        == 404
    )
    assert owner.get(f"/api/admin/businesses/{scenario['business_id']}/bookings").status_code == 200
    listing = owner.get(
        f"/api/admin/businesses/{scenario['business_id']}/bookings"
        f"?staff={scenario['staff_ids'][0]}&status=confirmed&limit=10"
    )
    assert listing.status_code == 200
    assert any(item["id"] == booking_id for item in listing.json["data"])
    assert customer.get("/api/me/bookings?filter=upcoming").status_code == 200
    assert (
        other_customer.get(f"/api/admin/businesses/{scenario['business_id']}/bookings").status_code
        == 404
    )
    staff, staff_csrf = client_for(app, scenario["users"][3])
    foreign_staff_booking = seed_booking(
        scenario,
        start_at=datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00")),
        staff_id=scenario["staff_ids"][1],
        customer_id=scenario["users"][1],
    )
    assert staff.get(f"/api/admin/businesses/{scenario['business_id']}/bookings").status_code == 200
    assert (
        staff.patch(
            f"/api/bookings/{foreign_staff_booking}",
            json={"action": "complete"},
            headers={"X-CSRF-Token": staff_csrf},
        ).status_code
        == 404
    )
    anonymous = app.test_client()
    assert anonymous.get("/api/me/bookings").status_code == 401
    assert (
        anonymous.patch(f"/api/bookings/{booking_id}", json={"action": "cancel"}).status_code == 401
    )


def test_staff_confirm_complete_and_no_show_transition_rules(app, scenario):
    owner, csrf = client_for(app, scenario["users"][2])
    future_start = datetime.now(UTC) + timedelta(days=2)
    with app.app_context():
        pending_id = seed_booking(
            scenario,
            start_at=future_start,
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        confirmed_id = seed_booking(
            scenario,
            start_at=future_start + timedelta(hours=2),
            staff_id=scenario["staff_ids"][1],
        )
        started_id = seed_booking(
            scenario,
            start_at=datetime.now(UTC) - timedelta(hours=2),
            staff_id=scenario["staff_ids"][1],
        )

    confirmed = owner.patch(
        f"/api/bookings/{pending_id}",
        json={"action": "confirm"},
        headers={"X-CSRF-Token": csrf},
    )
    assert confirmed.status_code == 200
    assert confirmed.json["data"]["status"] == "confirmed"
    completed = owner.patch(
        f"/api/bookings/{confirmed_id}",
        json={"action": "complete"},
        headers={"X-CSRF-Token": csrf},
    )
    assert completed.status_code == 200
    no_show = owner.patch(
        f"/api/bookings/{started_id}",
        json={"action": "no_show"},
        headers={"X-CSRF-Token": csrf},
    )
    assert no_show.status_code == 200
    assert no_show.json["data"]["status"] == "no_show"
    too_early = owner.patch(
        f"/api/bookings/{pending_id}",
        json={"action": "no_show"},
        headers={"X-CSRF-Token": csrf},
    )
    assert too_early.status_code == 409
    assert too_early.json["error"]["code"] == "invalid_transition"

    with app.app_context():
        audit_rows = (
            db.session.execute(select(AuditLog).where(AuditLog.entity == "booking")).scalars().all()
        )
        actions = [row.action for row in audit_rows if row.entity_id == pending_id]
        assert actions == ["transition"]


def test_expire_holds_cancels_only_expired_and_state_transitions_are_audited(app, scenario):
    customer, _ = client_for(app, scenario["users"][0])
    del customer
    start = datetime.now(UTC) + timedelta(days=3)
    with app.app_context():
        expired_id = seed_booking(
            scenario,
            start_at=start,
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        active_id = seed_booking(
            scenario,
            start_at=start + timedelta(hours=2),
            staff_id=scenario["staff_ids"][1],
            service_id=scenario["deposit_service_id"],
            status="pending",
            hold_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
        assert booking_service.expire_holds(datetime.now(UTC)) == 1
        assert db.session.get(Booking, expired_id).status == "cancelled"
        assert db.session.get(Booking, active_id).status == "pending"
        audit = (
            db.session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "booking", AuditLog.entity_id == expired_id
                )
            )
            .scalars()
            .all()
        )
        assert any(row.action == "transition" for row in audit)


def test_booking_email_delivery_is_deferred_to_outbox(app, scenario, email_service, caplog):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    response = post_booking(client, csrf, scenario, slot["start_at"])
    assert response.status_code == 201
    assert email_service.sent == []
    assert email_service.notifications == []
    with app.app_context():
        booking = db.session.get(Booking, response.json["data"]["id"])
        assert booking is not None
        assert db.session.execute(
            select(Notification).where(Notification.booking_id == booking.id)
        ).scalars().all()


def test_creation_requires_csrf_and_unknown_business_service_staff_scoping(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    body = {
        "service_id": scenario["service_id"],
        "staff_id": "any",
        "start_at": slot["start_at"],
    }
    assert client.post(f"/api/b/{scenario['slug']}/bookings", json=body).status_code == 400
    response = client.post(
        f"/api/b/{scenario['slug']}/bookings",
        json={**body, "service_id": scenario["foreign_service_id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404
    anonymous = app.test_client()
    assert anonymous.post(f"/api/b/{scenario['slug']}/bookings", json=body).status_code == 401


def test_pending_booking_has_no_outbox_until_confirmed(app, scenario, email_service):
    client, csrf = client_for(app, scenario["users"][0])
    owner, owner_csrf = client_for(app, scenario["users"][2])
    slot = available_slots(client, scenario, scenario["deposit_service_id"])[0]
    response = post_booking(
        client, csrf, scenario, slot["start_at"], scenario["deposit_service_id"]
    )
    booking_id = response.json["data"]["id"]
    with app.app_context():
        assert db.session.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        ).scalars().all() == []
    confirmed = owner.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "confirm"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert confirmed.status_code == 200
    with app.app_context():
        rows = db.session.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        ).scalars().all()
        assert {row.kind for row in rows} == {"confirmation", "reminder_24h", "reminder_2h"}


def test_past_reminders_are_omitted_and_rescheduling_moves_unsent_reminders(app, scenario):
    with app.app_context():
        now = datetime.now(UTC)
        booking_id = seed_booking(scenario, start_at=now + timedelta(hours=1))
        booking = db.session.get(Booking, booking_id)
        from app.services.outbox import enqueue_confirmation_notifications

        enqueue_confirmation_notifications(booking, now)
        db.session.commit()
        rows = db.session.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        ).scalars().all()
        assert {row.kind for row in rows} == {"confirmation"}

    client, csrf = client_for(app, scenario["users"][0])
    slots = available_slots(client, scenario, staff=scenario["staff_ids"][0])
    created = post_booking(
        client, csrf, scenario, slots[0]["start_at"], staff=scenario["staff_ids"][0]
    )
    booking_id = created.json["data"]["id"]
    with app.app_context():
        before = {
            row.kind: row.scheduled_for
            for row in db.session.execute(
                select(Notification).where(Notification.booking_id == booking_id)
            ).scalars()
            if row.kind.startswith("reminder")
        }
    moved_start = datetime.fromisoformat(slots[1]["start_at"].replace("Z", "+00:00"))
    moved = client.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "reschedule", "start_at": moved_start.isoformat().replace("+00:00", "Z")},
        headers={"X-CSRF-Token": csrf},
    )
    assert moved.status_code == 200
    with app.app_context():
        after = {
            row.kind: row.scheduled_for
            for row in db.session.execute(
                select(Notification).where(Notification.booking_id == booking_id)
            ).scalars()
            if row.kind.startswith("reminder")
        }
        assert after.keys() == before.keys()
        assert all(after[kind] == moved_start - timedelta(hours=24 if kind == "reminder_24h" else 2)
                   for kind in after)


def test_cancel_cancels_unsent_rows_and_queues_cancellation_email(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    owner, owner_csrf = client_for(app, scenario["users"][2])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    response = owner.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "cancel"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200
    with app.app_context():
        rows = db.session.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        ).scalars().all()
        assert {row.kind: row.status for row in rows} == {
            "confirmation": "cancelled",
            "reminder_24h": "cancelled",
            "reminder_2h": "cancelled",
            "cancellation": "queued",
        }
        confirmation_id = next(row.id for row in rows if row.kind == "confirmation")
    with app.app_context():
        db.session.get(Notification, confirmation_id).status = "queued"
        db.session.commit()
        assert notification_jobs.send_notification(confirmation_id) == "cancelled"


def test_send_notification_is_idempotent_and_concurrent(app, scenario, email_service):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    with app.app_context():
        notification_id = db.session.execute(
            select(Notification.id).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        db.session.execute(
            Notification.__table__.update()
            .where(Notification.id == notification_id)
            .values(scheduled_for=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.session.commit()

    def deliver():
        with app.app_context():
            return notification_jobs.send_notification(notification_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver(), range(2)))
    assert results.count("sent") == 1
    assert len(email_service.notifications) == 1
    with app.app_context():
        row = db.session.get(Notification, notification_id)
        assert row.status == "sent" and row.sent_at is not None
        assert notification_jobs.send_notification(notification_id) == "skipped"
    assert len(email_service.notifications) == 1


def test_failed_notification_retries_five_times_then_marks_failed(
    app, scenario, email_service, monkeypatch
):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    email_service.fail = True
    with app.app_context():
        app.config["NOTIFICATION_RETRY_INTERVALS_SECONDS"] = (0, 0, 0, 0)
        notification_id = db.session.execute(
            select(Notification.id).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        db.session.execute(
            Notification.__table__.update()
            .where(Notification.id == notification_id)
            .values(scheduled_for=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.session.commit()
        assert notification_jobs.enqueue_due_notifications() == 1
        from rq import SimpleWorker

        queue = notification_jobs._queue()
        SimpleWorker([queue], connection=queue.connection).work(burst=True, with_scheduler=True)
        assert db.session.get(Notification, notification_id).status == "failed"
        job = queue.fetch_job(f"notification-{notification_id}")
        assert job.meta["notification_attempts"] == 5
    assert notification_jobs._retry_policy().max == 4


def test_cancellation_does_not_cancel_the_new_cancellation_notification(app, scenario):
    client, csrf = client_for(app, scenario["users"][0])
    owner, owner_csrf = client_for(app, scenario["users"][2])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    response = owner.patch(
        f"/api/bookings/{booking_id}",
        json={"action": "cancel"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200
    with app.app_context():
        statuses = dict(
            db.session.execute(
                select(Notification.kind, Notification.status).where(
                    Notification.booking_id == booking_id
                )
            ).all()
        )
        assert statuses["reminder_24h"] == "cancelled"
        assert statuses["reminder_2h"] == "cancelled"
        assert statuses["cancellation"] == "queued"


def test_scheduler_enqueues_only_due_once_and_expires_holds(app, scenario, email_service):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    with app.app_context():
        due_id = db.session.execute(
            select(Notification.id).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        db.session.execute(
            Notification.__table__.update()
            .where(Notification.id == due_id)
            .values(scheduled_for=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.session.commit()
        assert notification_jobs.enqueue_due_notifications() == 1
        assert notification_jobs.enqueue_due_notifications() == 0

        from rq import SimpleWorker

        queue = notification_jobs._queue()
        assert SimpleWorker([queue], connection=queue.connection).work(burst=True)
        assert len(email_service.notifications) == 1
        assert notification_jobs.enqueue_due_notifications() == 0

        expired_start = datetime.now(UTC) + timedelta(days=6)
        expired_id = seed_booking(
            scenario,
            start_at=expired_start,
            status="pending",
            hold_expires_at=datetime.now(UTC) - timedelta(minutes=2),
        )
        assert notification_jobs.run_scheduler_once()[1] == 1
        assert db.session.get(Booking, expired_id).status == "cancelled"


def test_email_rendering_uses_business_timezone(app, scenario, email_service):
    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    with app.app_context():
        db.session.get(Business, scenario["business_id"]).timezone = "America/New_York"
        notification = db.session.execute(
            select(Notification).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        notification.scheduled_for = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        notification_jobs.send_notification(notification.id)
    rendered = email_service.notifications[0][2]
    assert "America/New_York" in rendered or "EST" in rendered


def test_scheduler_recovers_retrying_and_stale_in_progress_notifications(app, scenario):
    from rq.job import JobStatus

    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    with app.app_context():
        notification = db.session.execute(
            select(Notification).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        notification.status = "retrying"
        notification.scheduled_for = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

        queue = notification_jobs._queue()
        assert notification_jobs.enqueue_due_notifications() == 1
        job_id = f"notification-{notification.id}"
        assert queue.job_ids.count(job_id) == 1
        assert notification_jobs.enqueue_due_notifications() == 0
        assert queue.job_ids.count(job_id) == 1

        job = queue.fetch_job(job_id)
        queue.remove(job_id)
        job._status = JobStatus.STARTED
        job.started_at = datetime.now(UTC) - timedelta(
            seconds=app.config["NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS"] + 1
        )
        job.last_heartbeat = job.started_at
        job.save()
        assert notification_jobs.enqueue_due_notifications() == 1
        assert queue.job_ids.count(job_id) == 1


@pytest.mark.skipif(os.name == "nt", reason="RQ's normal worker requires Linux fork")
def test_normal_rq_worker_path_delivers_notification_on_linux(app, scenario):
    from rq import Worker

    client, csrf = client_for(app, scenario["users"][0])
    slot = available_slots(client, scenario)[0]
    created = post_booking(client, csrf, scenario, slot["start_at"])
    booking_id = created.json["data"]["id"]
    with app.app_context():
        notification = db.session.execute(
            select(Notification).where(
                Notification.booking_id == booking_id, Notification.kind == "confirmation"
            )
        ).scalar_one()
        notification.scheduled_for = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        assert notification_jobs.enqueue_due_notifications() == 1
        queue = notification_jobs._queue()
        db.session.remove()
        assert Worker([queue], connection=queue.connection).work(burst=True)
        with app.app_context():
            assert db.session.get(Notification, notification.id).status == "sent"


def _configure_payfast(app, *, validator_response="VALID"):
    app.config.update(
        PAYFAST_MERCHANT_ID="10000100",
        PAYFAST_MERCHANT_KEY="46f0cd694581a",
        PAYFAST_PASSPHRASE="sample secret",
        PAYFAST_SANDBOX=True,
        PUBLIC_BASE_URL="https://booking.example.test",
        PAYMENT_HOLD_MINUTES=20,
    )
    app.extensions["payfast_ip_resolver"] = lambda host: {"203.0.113.10"}
    app.extensions["payfast_itn_validator"] = (
        lambda pairs, endpoint, timeout: validator_response
    )


def _deposit_booking(app, scenario, *, user_index=0, slot_index=0):
    client, csrf = client_for(app, scenario["users"][user_index])
    slot = available_slots(client, scenario, scenario["deposit_service_id"])[slot_index]
    response = post_booking(
        client, csrf, scenario, slot["start_at"], scenario["deposit_service_id"]
    )
    assert response.status_code == 201
    return client, csrf, response.json["data"]["id"]


def _itn_body(
    reference,
    status="COMPLETE",
    *,
    merchant="10000100",
    amount="5.00",
    pf_payment_id="pf-transaction-98",
):
    pairs = [
        ("m_payment_id", reference),
        ("pf_payment_id", pf_payment_id),
        ("payment_status", status),
        ("item_name", "Color"),
        ("amount_gross", amount),
        ("merchant_id", merchant),
    ]
    parameter_string = "&".join(f"{key}={quote_plus(value)}" for key, value in pairs)
    parameter_string += "&passphrase=sample+secret"
    signature = md5(parameter_string.encode()).hexdigest()
    return urlencode([*pairs, ("signature", signature)]).encode()


def _itn(client, reference, status="COMPLETE", **kwargs):
    return client.post(
        "/api/payments/payfast/itn",
        data=_itn_body(reference, status, **kwargs),
        content_type="application/x-www-form-urlencoded",
        environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
    )


def test_payfast_form_signature_matches_documented_example_vector():
    fields = {
        "merchant_id": "10000100",
        "merchant_key": "46f0cd694581a",
        "return_url": "http://www.yourdomain.co.za/return.php",
        "cancel_url": "http://www.yourdomain.co.za/cancel.php",
        "notify_url": "http://www.yourdomain.co.za/notify.php",
        "name_first": "First Name",
        "name_last": "Last Name",
        "email_address": "test@test.com",
        "m_payment_id": "1234",
        "amount": "10.00",
        "item_name": "Order#123",
    }
    # PayFast's official Custom Payment Integration example credentials and
    # form values, processed using its documented signature algorithm.
    assert generate_form_signature(fields, "jt7NOE43FZPn") == "8317e2bbd1ae2a6f4f36837e83be4ca9"


def test_payfast_signature_encodes_ampersand_space_and_accented_item_name():
    assert generate_form_signature(
        {"merchant_id": "10000100", "item_name": "Fade & trim café"},
        "space & secret",
    ) == "5e0367381675480079eec51d22065a22"


@pytest.mark.parametrize(("cents", "expected"), [(18000, "180.00"), (5, "0.05")])
def test_payfast_amounts_use_integer_cents(cents, expected):
    assert format_cents(cents) == expected


def test_pay_endpoint_permissions_reuse_and_hold_extension(app, scenario):
    _configure_payfast(app)
    client, csrf, booking_id = _deposit_booking(app, scenario)
    original_hold = datetime.now(UTC) + timedelta(minutes=5)
    with app.app_context():
        db.session.get(Booking, booking_id).hold_expires_at = original_hold
        db.session.commit()
    first = client.post(
        f"/api/bookings/{booking_id}/pay", headers={"X-CSRF-Token": csrf}
    )
    assert first.status_code == 200
    fields = first.json["data"]["fields"]
    assert first.json["data"]["action_url"] == "https://sandbox.payfast.co.za/eng/process"
    assert fields["amount"] == "5.00" and fields["item_name"] == "Color"
    assert fields["notify_url"] == "https://booking.example.test/api/payments/payfast/itn"
    assert fields["signature"] == generate_form_signature(
        {key: value for key, value in fields.items() if key != "signature"},
        "sample secret",
    )
    second = client.post(
        f"/api/bookings/{booking_id}/pay", headers={"X-CSRF-Token": csrf}
    )
    assert second.status_code == 200
    assert second.json["data"]["fields"]["m_payment_id"] == fields["m_payment_id"]
    with app.app_context():
        assert len(db.session.execute(select(Payment)).scalars().all()) == 1
        assert db.session.get(Booking, booking_id).hold_expires_at >= original_hold
        long_hold = datetime.now(UTC) + timedelta(hours=2)
        db.session.get(Booking, booking_id).hold_expires_at = long_hold
        db.session.commit()
    third = client.post(
        f"/api/bookings/{booking_id}/pay", headers={"X-CSRF-Token": csrf}
    )
    assert third.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking_id).hold_expires_at == long_hold
    other, other_csrf = client_for(app, scenario["users"][1])
    assert other.post(
        f"/api/bookings/{booking_id}/pay", headers={"X-CSRF-Token": other_csrf}
    ).status_code == 404
    assert app.test_client().post(f"/api/bookings/{booking_id}/pay").status_code == 401


@pytest.mark.parametrize("invalid", ["confirmed", "cancelled", "zero_deposit", "expired"])
def test_pay_endpoint_rejects_ineligible_booking(app, scenario, invalid):
    _configure_payfast(app)
    client, csrf, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        if invalid == "confirmed":
            booking.status = "confirmed"
        elif invalid == "cancelled":
            booking.status = "cancelled"
        elif invalid == "zero_deposit":
            booking.deposit_cents = 0
        else:
            booking.hold_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
    response = client.post(
        f"/api/bookings/{booking_id}/pay", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 409


def test_payfast_itn_happy_path_confirms_and_writes_outbox(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        fields = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]
    response = _itn(app.test_client(), fields["m_payment_id"])
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "confirmed"
        assert db.session.execute(
            select(Payment.status).where(Payment.provider_ref == fields["m_payment_id"])
        ).scalar_one() == "paid"
        assert len(
            db.session.execute(
                select(Notification).where(Notification.booking_id == booking_id)
            ).scalars().all()
        ) == 3


@pytest.mark.parametrize(
    ("failure", "expected_status", "validator_response"),
    [
        ("signature", 400, "VALID"),
        ("ip", 400, "VALID"),
        ("merchant", 400, "VALID"),
        ("amount", 400, "VALID"),
        ("validate", 400, "INVALID"),
        ("unknown", 400, "VALID"),
    ],
)
def test_itn_rejections_leave_booking_and_payment_unchanged(
    app, scenario, failure, expected_status, validator_response
):
    _configure_payfast(app, validator_response=validator_response)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        fields = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]
    reference = "unknown-reference" if failure == "unknown" else fields["m_payment_id"]
    kwargs = {
        "merchant": "wrong" if failure == "merchant" else "10000100",
        "amount": "5.01" if failure == "amount" else "5.00",
    }
    body = _itn_body(reference, **kwargs)
    source_ip = "198.51.100.2" if failure == "ip" else "203.0.113.10"
    if failure == "signature":
        body = body.replace(b"signature=", b"signature=bad")
    response = app.test_client().post(
        "/api/payments/payfast/itn",
        data=body,
        content_type="application/x-www-form-urlencoded",
        environ_overrides={"REMOTE_ADDR": source_ip},
    )
    assert response.status_code == expected_status
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "pending"
        payment = db.session.execute(
            select(Payment).where(Payment.provider_ref == fields["m_payment_id"])
        ).scalar_one()
        assert payment.status == "pending" and payment.raw_payload is None


def test_itn_network_failure_returns_retryable_error_without_mutation(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    def fail_validation(*args):
        raise OSError("offline")
    app.extensions["payfast_itn_validator"] = fail_validation
    response = _itn(app.test_client(), ref)
    assert response.status_code == 503
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "pending"
        assert db.session.execute(
            select(Payment.status).where(Payment.provider_ref == ref)
        ).scalar_one() == "pending"


def test_itn_repeated_and_concurrent_complete_are_idempotent(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _itn(app.test_client(), ref).status_code, range(2)))
    assert responses == [200, 200]
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "confirmed"
        assert len(
            db.session.execute(
                select(Notification).where(Notification.booking_id == booking_id)
            ).scalars().all()
        ) == 3


def test_replayed_complete_with_different_provider_id_is_ignored(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    client = app.test_client()
    assert _itn(client, ref, pf_payment_id="pf-original").status_code == 200
    second = client.post(
        "/api/payments/payfast/itn",
        data=_itn_body(ref, pf_payment_id="pf-different"),
        content_type="application/x-www-form-urlencoded",
        environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
    )
    assert second.status_code == 200
    with app.app_context():
        payment = db.session.execute(
            select(Payment).where(Payment.provider_ref == ref)
        ).scalar_one()
        assert payment.raw_payload["pf_payment_id"] == "pf-original"
        assert db.session.get(Booking, booking_id).status == "confirmed"


def test_payfast_itn_is_exempt_from_rate_limiter(app):
    _configure_payfast(app)
    app.config["PAYFAST_ITN_RATE_LIMIT"] = "1 per minute"
    client = app.test_client()
    for _ in range(5):
        response = client.post(
            "/api/payments/payfast/itn",
            data=_itn_body("unknown-reference"),
            content_type="application/x-www-form-urlencoded",
            environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
        )
        assert response.status_code == 400


def test_failed_payment_then_complete_and_cancelled_booking_late_payment(
    app, scenario, email_service
):
    _configure_payfast(app)
    client, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    assert _itn(client, ref, "FAILED").status_code == 200
    assert _itn(client, ref, "COMPLETE").status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "confirmed"

    _, _, cancelled_id = _deposit_booking(app, scenario, user_index=1, slot_index=1)
    with app.app_context():
        cancelled_ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][1]), cancelled_id
        )["fields"]["m_payment_id"]
        db.session.get(Booking, cancelled_id).status = "cancelled"
        db.session.commit()
    assert _itn(client, cancelled_ref, "COMPLETE").status_code == 200
    with app.app_context():
        assert db.session.get(Booking, cancelled_id).status == "cancelled"
        assert db.session.execute(
            select(Payment.status).where(Payment.provider_ref == cancelled_ref)
        ).scalar_one() == "paid"
        assert db.session.execute(
            select(AuditLog.id).where(
                AuditLog.entity == "payment",
                AuditLog.action == "payment_received_for_cancelled_booking",
            )
        ).scalar_one_or_none() is not None
        owner_notice = db.session.execute(
            select(Notification).where(
                Notification.booking_id == cancelled_id,
                Notification.kind == "payment_for_cancelled_booking",
            )
        ).scalar_one()
        owner_notice_id = owner_notice.id
        from app.services.outbox import enqueue_late_payment_owner_notification

        enqueue_late_payment_owner_notification(db.session.get(Booking, cancelled_id))
        db.session.commit()
        assert db.session.execute(
            select(db.func.count(Notification.id)).where(
                Notification.booking_id == cancelled_id,
                Notification.kind == "payment_for_cancelled_booking",
            )
        ).scalar_one() == 1
    with app.app_context():
        assert notification_jobs.send_notification(owner_notice_id) == "sent"
    assert email_service.notifications[-1][0] == scenario["users"][2]
    assert "refund is needed" in email_service.notifications[-1][2].lower()


def test_payfast_secrets_and_full_itn_are_absent_from_logs_and_audit_diffs(
    app, scenario, caplog
):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        ref = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    response = _itn(app.test_client(), ref)
    assert response.status_code == 200
    assert "sample secret" not in caplog.text
    assert "pf-transaction-98" not in caplog.text
    with app.app_context():
        diffs = [
            str(row.diff)
            for row in db.session.execute(select(AuditLog)).scalars()
            if row.diff is not None
        ]
        assert all("sample secret" not in diff for diff in diffs)
        assert all("signature" not in diff.lower() for diff in diffs)


def test_unknown_itn_status_is_recorded_without_payment_or_booking_transition(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        reference = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
    response = _itn(app.test_client(), reference, "PENDING")
    assert response.status_code == 200
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        payment = db.session.execute(
            select(Payment).where(Payment.provider_ref == reference)
        ).scalar_one()
        assert booking.status == "pending"
        assert payment.status == "pending"
        assert payment.raw_payload["payment_status"] == "PENDING"


def test_payment_reference_for_one_booking_never_confirms_another(app, scenario):
    _configure_payfast(app)
    _, _, booking_a = _deposit_booking(app, scenario)
    _, _, booking_b = _deposit_booking(app, scenario, user_index=1, slot_index=1)
    with app.app_context():
        ref_a = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_a
        )["fields"]["m_payment_id"]
        payment_service.start_payment(
            db.session.get(User, scenario["users"][1]), booking_b
        )
    assert _itn(app.test_client(), ref_a).status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking_a).status == "confirmed"
        assert db.session.get(Booking, booking_b).status == "pending"


def test_itn_confirms_still_pending_booking_even_if_hold_time_passed(app, scenario):
    _configure_payfast(app)
    _, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        reference = payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )["fields"]["m_payment_id"]
        db.session.get(Booking, booking_id).hold_expires_at = (
            datetime.now(UTC) - timedelta(seconds=1)
        )
        db.session.commit()
    assert _itn(app.test_client(), reference).status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == "confirmed"


def test_production_startup_requires_payfast_credentials(app):
    from app import create_app

    with pytest.raises(RuntimeError, match="PayFast"):
        create_app(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "strong-test-secret",
                "EMAIL_BACKEND": "smtp",
                "SESSION_COOKIE_SECURE": True,
                "PAYFAST_MERCHANT_ID": "",
                "PAYFAST_MERCHANT_KEY": "",
                "PAYFAST_PASSPHRASE": "",
            }
        )


def test_owner_payment_listing_and_customer_booking_payment_status(app, scenario):
    _configure_payfast(app)
    customer, _, booking_id = _deposit_booking(app, scenario)
    with app.app_context():
        payment_service.start_payment(
            db.session.get(User, scenario["users"][0]), booking_id
        )
    booking_response = customer.get(f"/api/me/bookings/{booking_id}")
    assert booking_response.json["data"]["payment_status"] == "pending"
    owner, _ = client_for(app, scenario["users"][2])
    other, _ = client_for(app, scenario["users"][1])
    assert owner.get(
        f"/api/admin/businesses/{scenario['business_id']}/payments?status=pending"
    ).status_code == 200
    assert other.get(
        f"/api/admin/businesses/{scenario['business_id']}/payments"
    ).status_code == 404
