"""Business administration authorization and persistence tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app.extensions import db
from app.models import AuditLog, Booking, Business, Membership, Service, Staff, User
from flask.testing import FlaskClient
from tests.integration.test_auth import login, register, verify


class RecordingEmailService:
    def __init__(self):
        self.verification_tokens = {}
        self.reset_tokens = {}

    def send_verification(self, user, token):
        self.verification_tokens[user.email] = token

    def send_password_reset(self, user, token):
        self.reset_tokens[user.email] = token

    def send_booking_confirmation(self, user, booking, business, service):
        return None


@pytest.fixture
def email_service(app):
    original = app.extensions["email_service"]
    recorder = RecordingEmailService()
    app.extensions["email_service"] = recorder
    yield recorder
    app.extensions["email_service"] = original


class CSRFFlaskClient(FlaskClient):
    def _csrf(self, kwargs):
        token = self.get("/api/auth/csrf").json["data"]["csrf_token"]
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("X-CSRF-Token", token)
        kwargs["headers"] = headers
        return kwargs

    def post(self, *args, **kwargs):
        return super().post(*args, **self._csrf(kwargs))

    def put(self, *args, **kwargs):
        return super().put(*args, **self._csrf(kwargs))

    def patch(self, *args, **kwargs):
        return super().patch(*args, **self._csrf(kwargs))

    def delete(self, *args, **kwargs):
        return super().delete(*args, **self._csrf(kwargs))


@pytest.fixture
def client(app):
    original = app.test_client_class
    app.test_client_class = CSRFFlaskClient
    yield app.test_client()
    app.test_client_class = original


def signed_in(client, email, name, email_service):
    assert register(client, email=email, full_name=name).status_code == 201
    verify(client, email_service.verification_tokens[email])
    assert login(client, email=email).status_code == 200


def create_business(client, slug="my-business"):
    return client.post("/api/admin/businesses", json={"slug": slug, "name": "My Business"})


def test_business_create_owner_duplicate_slug_and_timezone(client, app, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    response = create_business(client)
    assert response.status_code == 201
    business_id = response.json["data"]["id"]
    with app.app_context():
        assert db.session.get(Membership, (1, business_id)).role == "owner"
    assert create_business(client).status_code == 409
    assert (
        client.post(
            "/api/admin/businesses",
            json={"slug": "other-shop", "name": "X", "timezone": "Mars/Olympus"},
        ).status_code
        == 422
    )


def test_service_validation_audit_and_deactivated_public_catalog(client, app, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business = create_business(client).json["data"]
    base = f"/api/admin/businesses/{business['id']}"
    assert (
        client.post(
            f"{base}/services",
            json={
                "name": "Cut",
                "duration_min": 30,
                "buffer_min": 5,
                "price_cents": 1000,
                "deposit_cents": 1200,
            },
        ).status_code
        == 422
    )
    created = client.post(
        f"{base}/services",
        json={"name": "Cut", "duration_min": 30, "buffer_min": 5, "price_cents": 1000},
    ).json["data"]
    service_id = created["id"]
    assert client.post(f"{base}/services/{service_id}/deactivate").status_code == 200
    assert client.get(f"/api/b/{business['slug']}/services").json["data"] == []
    with app.app_context():
        assert db.session.get(Service, service_id).active is False
        logs = (
            db.session.execute(db.select(AuditLog).where(AuditLog.entity == "service"))
            .scalars()
            .all()
        )
        assert {x.action for x in logs} == {"create", "deactivate"}
        assert all(x.actor_id == 1 and x.diff for x in logs)
        for row in logs:
            assert "password" not in str(row.diff).lower()
            assert "token" not in str(row.diff).lower()
            assert "secret" not in str(row.diff).lower()


def test_staff_list_includes_business_scoped_service_assignments_and_booking_qr(
    client, email_service
):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business = create_business(client, slug="qr-shop").json["data"]
    base = f"/api/admin/businesses/{business['id']}"
    service_row = client.post(
        f"{base}/services",
        json={"name": "Consultation", "duration_min": 30, "price_cents": 2500},
    ).json["data"]
    staff_row = client.post(f"{base}/staff", json={"display_name": "Ari"}).json["data"]
    assert (
        client.post(
            f"{base}/staff/{staff_row['id']}/services/{service_row['id']}", json={}
        ).status_code
        == 200
    )
    listed = client.get(f"{base}/staff").json["data"]
    assert next(row for row in listed if row["id"] == staff_row["id"])["service_ids"] == [
        service_row["id"]
    ]
    qr = client.get(f"/app/{business['id']}/qr.svg")
    assert qr.status_code == 200
    assert qr.mimetype == "image/svg+xml"
    assert "<svg" in qr.text
    assert "qr-shop" not in qr.text


def test_staff_roles_hours_time_off_and_atomic_week_replacement(
    client, app, email_service, monkeypatch
):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business = create_business(client).json["data"]
    base = f"/api/admin/businesses/{business['id']}"
    staff = client.post(f"{base}/staff", json={"display_name": "Worker"}).json["data"]
    staff_id = staff["id"]
    hours_url = f"{base}/staff/{staff_id}/working-hours"
    good = {"hours": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]}
    assert client.put(hours_url, json=good).status_code == 200
    original_commit = db.session.commit

    def failing_commit():
        db.session.flush()
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(db.session, "commit", failing_commit)
    previous_propagation = app.config["PROPAGATE_EXCEPTIONS"]
    app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        failed_replace = client.put(
            hours_url,
            json={"hours": [{"weekday": 1, "start_time": "10:00", "end_time": "14:00"}]},
        )
    finally:
        app.config["PROPAGATE_EXCEPTIONS"] = previous_propagation
    assert failed_replace.status_code == 500
    monkeypatch.setattr(db.session, "commit", original_commit)
    assert client.get(hours_url).json["data"][0]["weekday"] == 0
    bad = {
        "hours": [
            {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
            {"weekday": 0, "start_time": "11:00", "end_time": "13:00"},
        ]
    }
    assert client.put(hours_url, json=bad).status_code == 422
    assert len(client.get(hours_url).json["data"]) == 1
    off_url = f"{base}/staff/{staff_id}/time-off"
    assert (
        client.post(
            off_url, json={"start_at": "2026-01-01T12:00:00Z", "end_at": "2026-01-01T11:00:00Z"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            off_url, json={"start_at": "2026-01-01T12:00:00Z", "end_at": "2026-01-01T13:00:00Z"}
        ).status_code
        == 201
    )
    service_item = client.post(
        f"{base}/services",
        json={"name": "Linked", "duration_min": 20, "price_cents": 500},
    ).json["data"]
    with app.app_context():
        customer = User(email="customer@example.test", password_hash="unused", full_name="Customer")
        db.session.add(customer)
        db.session.flush()
        booking = Booking(
            business_id=business["id"],
            customer_id=customer.id,
            staff_id=staff_id,
            service_id=service_item["id"],
            start_at=datetime.now(UTC) + timedelta(days=10),
            end_at=datetime.now(UTC) + timedelta(days=10, minutes=20),
            blocked_until=datetime.now(UTC) + timedelta(days=10, minutes=20),
            status="confirmed",
            price_cents=500,
        )
        db.session.add(booking)
        db.session.commit()
        booking_id = booking.id
    staff_deactivation = client.post(f"{base}/staff/{staff_id}/deactivate")
    assert staff_deactivation.status_code == 200
    assert staff_deactivation.json["data"]["affected_future_bookings"] == 1
    assert client.get(f"/api/b/{business['slug']}/staff").json["data"] == []
    service_deactivation = client.post(f"{base}/services/{service_item['id']}/deactivate")
    assert service_deactivation.status_code == 200
    assert service_deactivation.json["data"]["affected_future_bookings"] == 1
    with app.app_context():
        assert db.session.get(Booking, booking_id) is not None
        assert db.session.get(Service, service_item["id"]) is not None
        assert db.session.get(Staff, staff_id) is not None


def test_cross_business_resources_return_404(client, app, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business1 = create_business(client, "one-shop").json["data"]
    staff = client.post(
        f"/api/admin/businesses/{business1['id']}/staff", json={"display_name": "One"}
    ).json["data"]
    service1 = client.post(
        f"/api/admin/businesses/{business1['id']}/services",
        json={"name": "Service", "duration_min": 30, "price_cents": 0},
    ).json["data"]
    business2 = create_business(client, "two-shop").json["data"]
    base2 = f"/api/admin/businesses/{business2['id']}"
    assert (
        client.patch(f"{base2}/staff/{staff['id']}", json={"display_name": "hack"}).status_code
        == 404
    )
    assert (
        client.patch(f"{base2}/services/{service1['id']}", json={"name": "hack"}).status_code == 404
    )
    staff2 = client.post(f"{base2}/staff", json={"display_name": "Two"}).json["data"]
    service2 = client.post(
        f"{base2}/services",
        json={"name": "Second", "duration_min": 30, "price_cents": 0},
    ).json["data"]
    assert client.post(f"{base2}/staff/{staff2['id']}/services/{service1['id']}").status_code == 404
    assert (
        client.delete(f"{base2}/staff/{staff['id']}/services/{service2['id']}").status_code == 404
    )
    assert client.get(f"{base2}/staff/{staff['id']}/working-hours").status_code == 404
    assert client.get(f"{base2}/staff/{staff['id']}/time-off").status_code == 404
    assert client.post(f"{base2}/staff/{staff['id']}/deactivate").status_code == 404
    assert client.post(f"{base2}/services/{service1['id']}/deactivate").status_code == 404
    assert client.get(f"/api/admin/businesses/{business2['id'] + 999}").status_code == 404
    outsider = client.application.test_client()
    signed_in(outsider, "outsider@example.test", "Outsider", email_service)
    assert outsider.get(f"/api/admin/businesses/{business1['id']}").status_code == 404
    assert outsider.get(f"/api/admin/businesses/{business1['id']}/services").status_code == 404
    assert outsider.get(f"/api/admin/businesses/{business1['id']}/staff").status_code == 404
    assert (
        outsider.get(
            f"/api/admin/businesses/{business1['id']}/staff/{staff['id']}/working-hours"
        ).status_code
        == 404
    )
    assert (
        outsider.get(
            f"/api/admin/businesses/{business1['id']}/staff/{staff['id']}/time-off"
        ).status_code
        == 404
    )


def test_customer_cannot_access_business_admin(client, app, email_service):
    signed_in(client, "customer@example.test", "Customer", email_service)
    with app.app_context():
        business = Business(slug="the-shop", name="Shop")
        db.session.add(business)
        db.session.commit()
        business_id = business.id
    assert client.get(f"/api/admin/businesses/{business_id}").status_code == 404


def test_staff_can_read_admin_lists_but_manage_only_own_time_off(client, app, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business = create_business(client).json["data"]
    base = f"/api/admin/businesses/{business['id']}"
    with app.app_context():
        staff_user = User(
            email="staff@example.test",
            password_hash="unused",
            full_name="Staff",
            verified_at=db.func.now(),
        )
        db.session.add(staff_user)
        db.session.flush()
        db.session.add(Membership(user_id=staff_user.id, business_id=business["id"], role="staff"))
        db.session.commit()
        staff_uid = staff_user.id
    staff = client.post(
        f"{base}/staff", json={"display_name": "Linked", "user_id": staff_uid}
    ).json["data"]
    staff_id = staff["id"]
    assert (
        client.post(
            f"{base}/services", json={"name": "Read", "duration_min": 15, "price_cents": 0}
        ).status_code
        == 201
    )
    # Sign in as linked staff using a freshly created password hash.
    from app.services.auth import PASSWORD_HASHER

    with app.app_context():
        user = db.session.get(User, staff_uid)
        user.password_hash = PASSWORD_HASHER.hash("Correct horse battery")
        db.session.commit()
    other = client.application.test_client()
    assert login(other, "staff@example.test").status_code == 200
    assert other.get(f"{base}/services").status_code == 200
    assert other.get(f"{base}/staff").status_code == 200
    owner_created_staff = client.post(
        f"{base}/staff", json={"display_name": "Others time off"}
    ).json["data"]
    outsider_time_off = client.post(
        f"{base}/staff/{owner_created_staff['id']}/time-off",
        json={"start_at": "2026-02-02T10:00:00Z", "end_at": "2026-02-02T11:00:00Z"},
    ).json["data"]
    assert other.get(f"{base}/staff/{owner_created_staff['id']}/time-off").status_code == 404
    assert (
        other.delete(
            f"{base}/staff/{owner_created_staff['id']}/time-off/{outsider_time_off['id']}"
        ).status_code
        == 404
    )
    assert other.patch(f"{base}", json={"name": "Stolen"}).status_code == 403
    assert (
        other.post(
            f"{base}/services",
            json={"name": "Forbidden", "duration_min": 15, "price_cents": 0},
        ).status_code
        == 403
    )
    assert other.post(f"{base}/staff", json={"display_name": "Forbidden"}).status_code == 403
    assert (
        other.put(
            f"{base}/staff/{staff_id}/working-hours",
            json={"hours": [{"weekday": 0, "start_time": "09:00", "end_time": "10:00"}]},
        ).status_code
        == 403
    )
    assert other.post(f"{base}/staff/{staff_id}/services/1").status_code == 403
    own = other.post(
        f"{base}/staff/{staff_id}/time-off",
        json={"start_at": "2026-02-01T10:00:00Z", "end_at": "2026-02-01T11:00:00Z"},
    )
    assert own.status_code == 201


def test_pagination_limit_is_bounded(client, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    business = create_business(client).json["data"]
    assert (
        client.get(f"/api/admin/businesses/{business['id']}/services?limit=101").status_code == 422
    )


def test_concurrent_duplicate_slug_creation_returns_conflict(client, app, email_service):
    signed_in(client, "owner@example.test", "Owner", email_service)
    csrf = client.get("/api/auth/csrf").json["data"]["csrf_token"]
    sid = client.get_cookie("booking_session").value

    def create():
        other = app.test_client()
        other.set_cookie("booking_session", sid)
        response = other.post(
            "/api/admin/businesses",
            json={"slug": "race-shop", "name": "Race"},
            headers={"X-CSRF-Token": csrf},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: create(), range(2)))
    assert statuses == [201, 409]
