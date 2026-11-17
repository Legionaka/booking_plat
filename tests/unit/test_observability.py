from app.observability import _scrub_sentry_event


def test_sentry_scrubber_removes_sensitive_request_data():
    event = {
        "request": {
            "cookies": "session=secret-cookie",
            "headers": {
                "X-CSRF-Token": "csrf-secret",
                "Authorization": "Bearer auth-secret",
                "Content-Type": "application/json",
            },
            "data": {
                "password": "password-secret",
                "payment_status": "COMPLETE",
                "m_payment_id": "itn-payload-secret",
            },
            "url": "https://example.test/path?password=secret",
        },
        "user": {"email": "customer@example.test", "id": "private-id"},
        "message": "Unhandled exception",
    }

    scrubbed = _scrub_sentry_event(event)

    assert scrubbed["request"] == {}
    assert "user" not in scrubbed
    serialized = str(scrubbed)
    for secret in (
        "secret-cookie",
        "csrf-secret",
        "auth-secret",
        "password-secret",
        "itn-payload-secret",
        "customer@example.test",
    ):
        assert secret not in serialized
