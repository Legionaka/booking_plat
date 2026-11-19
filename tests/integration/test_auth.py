"""Authentication API integration tests against PostgreSQL and Redis."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from app.extensions import db
from app.models import Business, Membership, User
from app.services import auth as auth_service
from app.services.auth import DUMMY_PASSWORD_HASH, PASSWORD_HASHER
from argon2 import PasswordHasher

GENERIC_FORGOT_MESSAGE = "If an account exists for that email, reset instructions were sent."


class RecordingEmailService:
    def __init__(self):
        self.verification_tokens: dict[str, str] = {}
        self.reset_tokens: dict[str, str] = {}

    def send_verification(self, user: User, token: str) -> None:
        self.verification_tokens[user.email] = token

    def send_password_reset(self, user: User, token: str) -> None:
        self.reset_tokens[user.email] = token

    def send_booking_confirmation(self, user, booking, business, service) -> None:
        return None


@pytest.fixture
def email_service(app):
    original = app.extensions["email_service"]
    recorder = RecordingEmailService()
    app.extensions["email_service"] = recorder
    yield recorder
    app.extensions["email_service"] = original


def auth_post(client, path, json):
    csrf = client.get("/api/auth/csrf").json["data"]["csrf_token"]
    return client.post(path, json=json, headers={"X-CSRF-Token": csrf})


def register(
    client, email="person@example.test", password="Correct horse battery", full_name="Test User"
):
    return auth_post(
        client, "/api/auth/register", {"email": email, "password": password, "full_name": full_name}
    )


def verify(client, token):
    return auth_post(client, "/api/auth/verify", {"token": token})


def login(client, email="person@example.test", password="Correct horse battery", headers=None):
    csrf = client.get("/api/auth/csrf").json["data"]["csrf_token"]
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf, **(headers or {})},
    )


def test_register_verify_login_and_memberships_happy_path(client, app, email_service):
    response = register(client)
    assert response.status_code == 201
    token = email_service.verification_tokens["person@example.test"]
    assert verify(client, token).status_code == 200

    with app.app_context():
        user = db.session.execute(
            db.select(User).where(User.email == "person@example.test")
        ).scalar_one()
        business = Business(slug="barber", name="Barber Shop")
        db.session.add(business)
        db.session.flush()
        db.session.add(Membership(user_id=user.id, business_id=business.id, role="owner"))
        db.session.commit()

    response = login(client)
    assert response.status_code == 200
    assert response.json["data"]["user"]["memberships"] == [
        {
            "business_id": 1,
            "business_name": "Barber Shop",
            "business_slug": "barber",
            "role": "owner",
        }
    ]
    assert client.get("/api/auth/me").status_code == 200


def test_duplicate_email_is_case_insensitive(client, email_service):
    assert register(client, email="Person@Example.test").status_code == 201

    response = register(client, email="person@example.TEST")

    assert response.status_code == 409
    assert response.json["error"]["code"] == "email_in_use"


def test_weak_password_is_rejected(client):
    response = register(client, password="short")

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_error"


def test_password_over_128_characters_is_rejected(client):
    assert register(client, password="x" * 129).status_code == 422


def test_register_and_login_require_csrf(client):
    payload = {
        "email": "csrf@example.test",
        "password": "Correct horse battery",
        "full_name": "CSRF",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 400
    assert (
        client.post(
            "/api/auth/login", json={"email": payload["email"], "password": payload["password"]}
        ).status_code
        == 400
    )


def test_unknown_and_wrong_password_both_verify_argon_hashes(client, email_service):
    register(client)
    verify(client, email_service.verification_tokens["person@example.test"])

    class VerifierSpy:
        def __init__(self):
            self.hashes = []

        def verify(self, encoded, password):
            self.hashes.append(encoded)
            return PASSWORD_HASHER.verify(encoded, password)

    spy = VerifierSpy()
    original = auth_service.PASSWORD_HASHER
    auth_service.PASSWORD_HASHER = spy
    try:
        login(client, password="Wrong password value")
        login(client, email="missing@example.test", password="Wrong password value")
    finally:
        auth_service.PASSWORD_HASHER = original
    assert len(spy.hashes) == 2
    assert spy.hashes[1] == DUMMY_PASSWORD_HASH


def test_wrong_password_and_unknown_email_have_identical_responses(client, email_service):
    register(client)
    verify(client, email_service.verification_tokens["person@example.test"])

    wrong_password = login(client, password="Wrong password value")
    unknown_email = login(client, email="missing@example.test", password="Wrong password value")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert (
        wrong_password.json
        == unknown_email.json
        == {
            "error": {
                "code": "invalid_credentials",
                "message": "Email or password is incorrect.",
            }
        }
    )


def test_unverified_user_cannot_login(client, email_service):
    register(client)

    response = login(client)

    assert response.status_code == 403
    assert response.json["error"]["code"] == "email_not_verified"


def test_expired_verification_and_reset_tokens_are_rejected(client, app, email_service):
    register(client)
    verify_token = email_service.verification_tokens["person@example.test"]
    auth_post(client, "/api/auth/forgot", {"email": "person@example.test"})
    reset_token = email_service.reset_tokens["person@example.test"]

    app.config["AUTH_VERIFY_TOKEN_MAX_AGE_SECONDS"] = -1
    app.config["AUTH_RESET_TOKEN_MAX_AGE_SECONDS"] = -1
    try:
        verify_response = verify(client, verify_token)
        reset_response = auth_post(
            client, "/api/auth/reset", {"token": reset_token, "new_password": "A new safe password"}
        )
    finally:
        app.config["AUTH_VERIFY_TOKEN_MAX_AGE_SECONDS"] = 24 * 60 * 60
        app.config["AUTH_RESET_TOKEN_MAX_AGE_SECONDS"] = 60 * 60

    assert verify_response.status_code == reset_response.status_code == 400
    assert verify_response.json["error"]["code"] == "invalid_token"
    assert reset_response.json["error"]["code"] == "invalid_token"


def test_verification_and_reset_tokens_cannot_be_reused(client, email_service):
    register(client)
    verify_token = email_service.verification_tokens["person@example.test"]
    assert verify(client, verify_token).status_code == 200
    assert verify(client, verify_token).status_code == 400

    auth_post(client, "/api/auth/forgot", {"email": "person@example.test"})
    reset_token = email_service.reset_tokens["person@example.test"]
    reset_payload = {"token": reset_token, "new_password": "A new safe password"}
    assert auth_post(client, "/api/auth/reset", reset_payload).status_code == 200
    assert auth_post(client, "/api/auth/reset", reset_payload).status_code == 400


def test_concurrent_verification_and_reset_token_use_is_atomic(app, client, email_service):
    register(client)
    verify_token = email_service.verification_tokens["person@example.test"]

    def verify_once():
        with app.test_client() as c:
            return auth_post(c, "/api/auth/verify", {"token": verify_token}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: verify_once(), range(2))) == [200, 400]

    auth_post(client, "/api/auth/forgot", {"email": "person@example.test"})
    reset_token = email_service.reset_tokens["person@example.test"]

    def reset_once():
        with app.test_client() as c:
            return auth_post(
                c,
                "/api/auth/reset",
                {"token": reset_token, "new_password": "Another safe password"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: reset_once(), range(2))) == [200, 400]


def test_production_rejects_unsafe_configuration():
    import pytest
    from app import create_app

    unsafe = [
        {
            "SECRET_KEY": "local-development-only",
            "EMAIL_BACKEND": "smtp",
            "SESSION_COOKIE_SECURE": True,
        },
        {
            "SECRET_KEY": "strong-test-secret",
            "EMAIL_BACKEND": "console",
            "SESSION_COOKIE_SECURE": True,
        },
        {
            "SECRET_KEY": "strong-test-secret",
            "EMAIL_BACKEND": "smtp",
            "SESSION_COOKIE_SECURE": False,
        },
    ]
    for config in unsafe:
        with pytest.raises(RuntimeError):
            create_app({"APP_ENV": "production", **config})


def test_redis_unavailable_returns_503(client, app, monkeypatch):
    from redis.exceptions import ConnectionError

    monkeypatch.setattr(
        app.extensions["redis"], "ping", lambda: (_ for _ in ()).throw(ConnectionError())
    )
    response = client.get("/api/auth/csrf")
    assert response.status_code == 503
    assert response.json["error"]["code"] == "dependency_unavailable"


def test_forgot_response_is_identical_for_known_and_unknown_emails(client, email_service):
    register(client)

    known = auth_post(client, "/api/auth/forgot", {"email": "person@example.test"})
    unknown = auth_post(client, "/api/auth/forgot", {"email": "missing@example.test"})

    assert known.status_code == unknown.status_code == 200
    assert known.json == unknown.json == {"data": {"message": GENERIC_FORGOT_MESSAGE}}


def test_resend_verification_uses_same_response_for_known_unknown_and_verified_accounts(
    client, email_service
):
    register(client)
    initial_token = email_service.verification_tokens["person@example.test"]

    unverified = auth_post(
        client, "/api/auth/resend-verification", {"email": "person@example.test"}
    )
    unknown = auth_post(
        client, "/api/auth/resend-verification", {"email": "missing@example.test"}
    )
    resent_token = email_service.verification_tokens["person@example.test"]
    assert verify(client, resent_token).status_code == 200
    verified = auth_post(
        client, "/api/auth/resend-verification", {"email": "person@example.test"}
    )

    assert unverified.status_code == unknown.status_code == verified.status_code == 200
    assert unverified.json == unknown.json == verified.json
    assert (
        unverified.headers["Retry-After"]
        == unknown.headers["Retry-After"]
        == verified.headers["Retry-After"]
    )
    assert resent_token != initial_token
    assert email_service.verification_tokens["person@example.test"] == resent_token


def test_resend_verification_is_rate_limited_per_email(client, app):
    original = app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"]
    app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"] = "1 per hour"
    try:
        first = auth_post(
            client, "/api/auth/resend-verification", {"email": "person@example.test"}
        )
        second = auth_post(
            client, "/api/auth/resend-verification", {"email": "person@example.test"}
        )
    finally:
        app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"] = original

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json["error"]["code"] == "rate_limited"
    assert second.headers.get("Retry-After")


def test_resend_verification_is_rate_limited_per_ip(client, app):
    email_limit = app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"]
    ip_limit = app.config["AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT"]
    app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"] = "10 per hour"
    app.config["AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT"] = "1 per hour"
    try:
        first = auth_post(
            client, "/api/auth/resend-verification", {"email": "first@example.test"}
        )
        second = auth_post(
            client, "/api/auth/resend-verification", {"email": "second@example.test"}
        )
    finally:
        app.config["AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT"] = email_limit
        app.config["AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT"] = ip_limit

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


def test_resend_verification_does_not_email_verified_accounts(client, email_service):
    register(client)
    original_token = email_service.verification_tokens["person@example.test"]
    assert verify(client, original_token).status_code == 200

    response = auth_post(
        client, "/api/auth/resend-verification", {"email": "person@example.test"}
    )

    assert response.status_code == 200
    assert email_service.verification_tokens["person@example.test"] == original_token


def test_repeated_failed_logins_are_rate_limited(client):
    results = [login(client, email="missing@example.test") for _ in range(8)]

    assert results[0].status_code == 401
    assert any(response.status_code == 429 for response in results[1:])
    assert results[-1].json["error"]["code"] == "rate_limited"


def test_logout_invalidates_session_and_requires_csrf(client, email_service):
    register(client)
    verify(client, email_service.verification_tokens["person@example.test"])
    assert login(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    csrf_token = client.get("/api/auth/csrf").json["data"]["csrf_token"]
    missing_csrf = client.post("/api/auth/logout")
    assert missing_csrf.status_code == 400
    assert missing_csrf.json["error"]["code"] == "csrf_failed"

    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_login_rotates_server_side_session_id(client, email_service):
    register(client)
    verify(client, email_service.verification_tokens["person@example.test"])
    csrf_token = client.get("/api/auth/csrf").json["data"]["csrf_token"]
    anonymous_session_id = client.get_cookie("booking_session").value

    response = login(client, headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert client.get_cookie("booking_session").value != anonymous_session_id


def test_me_is_protected_without_a_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json["error"]["code"] == "authentication_required"


def test_reset_changes_argon2_password_hash(client, app, email_service):
    register(client)
    auth_post(client, "/api/auth/forgot", {"email": "person@example.test"})
    token = email_service.reset_tokens["person@example.test"]
    assert (
        auth_post(
            client, "/api/auth/reset", {"token": token, "new_password": "A new safe password"}
        ).status_code
        == 200
    )

    with app.app_context():
        user = db.session.execute(
            db.select(User).where(User.email == "person@example.test")
        ).scalar_one()
        assert PasswordHasher().verify(user.password_hash, "A new safe password")
        assert user.verified_at is None
