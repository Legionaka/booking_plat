"""Production settings, request observability, and readiness checks."""

import io
import json
import logging
from types import SimpleNamespace

import pytest
from app import create_app
from app.extensions import db
from app.observability import JsonFormatter, RequestIdFilter
from flask import current_app, jsonify
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError


@pytest.mark.parametrize(
    ("key", "invalid", "message_key"),
    [
        ("SECRET_KEY", "local-development-only", "SECRET_KEY"),
        (
            "SQLALCHEMY_DATABASE_URI",
            "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform",
            "DATABASE_URL",
        ),
        ("SQLALCHEMY_DATABASE_URI", "", "DATABASE_URL"),
        ("REDIS_URL", "redis://localhost:6379/0", "REDIS_URL"),
        ("RATELIMIT_STORAGE_URI", "redis://localhost:6379/1", "RATELIMIT_STORAGE_URI"),
        ("EMAIL_BACKEND", "console", "EMAIL_BACKEND"),
        ("SESSION_COOKIE_SECURE", False, "SESSION_COOKIE_SECURE"),
        ("PUBLIC_BASE_URL", "http://booking.example.test", "PUBLIC_BASE_URL"),
        ("BOOKING_MANAGE_BASE_URL", "http://booking.example.test", "BOOKING_MANAGE_BASE_URL"),
        ("TRUSTED_PROXY_HOPS", 0, "TRUSTED_PROXY_HOPS"),
        ("SMTP_HOST", "", "SMTP_HOST"),
        ("SMTP_FROM_ADDRESS", "", "SMTP_FROM_ADDRESS"),
        ("SMTP_TLS_MODE", "", "SMTP_TLS_MODE"),
        ("PAYFAST_MERCHANT_ID", "", "PAYFAST_MERCHANT_ID"),
        ("PAYFAST_MERCHANT_KEY", "", "PAYFAST_MERCHANT_KEY"),
        ("PAYFAST_PASSPHRASE", "", "PAYFAST_PASSPHRASE"),
        ("PAYFAST_SANDBOX", True, "PAYFAST_SANDBOX"),
        ("DEMO_OWNER_PASSWORD", "DemoOnly-ChangeMe-2026!", "DEMO_OWNER_PASSWORD"),
    ],
)
def test_each_required_production_setting_is_guarded(key, invalid, message_key):
    valid = {
        "APP_ENV": "production",
        "SECRET_KEY": "a-long-production-secret-key",
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://prod:secret@db.example.test/booking",
        "REDIS_URL": "redis://redis.example.test:6379/0",
        "RATELIMIT_STORAGE_URI": "redis://redis.example.test:6379/1",
        "EMAIL_BACKEND": "smtp",
        "SESSION_COOKIE_SECURE": True,
        "PUBLIC_BASE_URL": "https://booking.example.test",
        "BOOKING_MANAGE_BASE_URL": "https://booking.example.test",
        "TRUSTED_PROXY_HOPS": 1,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": 587,
        "SMTP_FROM_ADDRESS": "booking@example.test",
        "SMTP_TLS_MODE": "starttls",
        "PAYFAST_MERCHANT_ID": "merchant-id",
        "PAYFAST_MERCHANT_KEY": "merchant-key",
        "PAYFAST_PASSPHRASE": "merchant-passphrase",
        "PAYFAST_SANDBOX": False,
        "DEMO_OWNER_PASSWORD": "A-unique-production-demo-password",
    }
    with pytest.raises(RuntimeError, match=message_key):
        create_app({**valid, key: invalid})


def test_ready_checks_postgres_and_redis_and_health_is_liveness(client, app, monkeypatch):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").get_json() == {"status": "ok"}

    monkeypatch.setattr(
        db.session,
        "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OperationalError("SELECT 1", {}, RuntimeError("db offline"))
        ),
    )
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json == {"status": "unhealthy"}
    assert client.get("/health").status_code == 200


def test_ready_fails_when_redis_is_unreachable(client, app, monkeypatch):
    monkeypatch.setattr(
        app.extensions["redis"],
        "ping",
        lambda: (_ for _ in ()).throw(RedisConnectionError("redis offline")),
    )
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json == {"status": "unhealthy"}


def test_security_headers_and_production_hsts(client, app):
    original = app.config["APP_ENV"]
    try:
        app.config["APP_ENV"] = "development"
        response = client.get("/health")
        assert response.headers["Content-Security-Policy"]
        policy = response.headers["Content-Security-Policy"]
        assert "script-src 'self'" in policy
        assert "style-src 'self'" in policy
        assert "style-src-attr 'none'" in policy
        assert "font-src 'self'" in policy
        assert "https://" not in policy
        assert "unsafe-inline" not in policy
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Strict-Transport-Security" not in response.headers
        app.config["APP_ENV"] = "production"
        secure_response = client.get("/health")
        assert secure_response.headers["Strict-Transport-Security"].startswith("max-age=")
    finally:
        app.config["APP_ENV"] = original


def test_request_id_is_returned_and_json_logs_exclude_secrets(client, app):
    isolated_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
            "REDIS_URL": app.config["REDIS_URL"],
            "RATELIMIT_STORAGE_URI": app.config["RATELIMIT_STORAGE_URI"],
            "RATELIMIT_KEY_PREFIX": app.config["RATELIMIT_KEY_PREFIX"],
            "SESSION_COOKIE_SECURE": False,
        }
    )
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter())
    isolated_app.logger.addHandler(handler)
    isolated_app.logger.disabled = False
    isolated_app.logger.setLevel(logging.INFO)

    def log_probe():
        current_app.extensions["email_service"].send_verification(
            SimpleNamespace(id=42), "verification-token-never-log"
        )
        return jsonify({"ok": True})

    isolated_app.add_url_rule("/_test/log-probe", view_func=log_probe)
    try:
        result = isolated_app.test_client().get(
            "/_test/log-probe?email=private-reader@example.test&password=secret-password-value-never-log"
        )
    finally:
        handler.flush()
        isolated_app.logger.removeHandler(handler)
    assert result.status_code == 200
    request_id = result.headers["X-Request-ID"]
    entries = [json.loads(line) for line in output.getvalue().splitlines() if line]
    assert entries, repr(output.getvalue())
    assert all(entry["request_id"] == request_id for entry in entries)
    assert "private-reader@example.test" not in output.getvalue()
    assert "secret-password-value-never-log" not in output.getvalue()
    assert "verification-token-never-log" not in output.getvalue()


def test_trusted_proxy_fix_uses_configured_forwarded_client_ip(app):
    proxied = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
            "REDIS_URL": app.config["REDIS_URL"],
            "RATELIMIT_STORAGE_URI": app.config["RATELIMIT_STORAGE_URI"],
            "TRUSTED_PROXY_HOPS": 1,
            "SESSION_COOKIE_SECURE": False,
        }
    )
    found = []
    from flask import request

    proxied.before_request(lambda: found.append(request.remote_addr))
    proxied.test_client().get(
        "/health",
        headers={"X-Forwarded-For": "198.51.100.17"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert found == ["198.51.100.17"]


def test_untrusted_forwarded_for_is_ignored_with_zero_proxy_hops(app):
    unproxied = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
            "REDIS_URL": app.config["REDIS_URL"],
            "RATELIMIT_STORAGE_URI": app.config["RATELIMIT_STORAGE_URI"],
            "TRUSTED_PROXY_HOPS": 0,
            "SESSION_COOKIE_SECURE": False,
        }
    )
    from flask import request

    seen = []
    unproxied.before_request(lambda: seen.append(request.remote_addr))
    unproxied.test_client().get(
        "/health",
        headers={"X-Forwarded-For": "203.0.113.250"},
        environ_overrides={"REMOTE_ADDR": "192.0.2.11"},
    )
    assert seen == ["192.0.2.11"]


def test_demo_mode_is_public_and_refuses_live_payfast(app):
    demo = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
            "REDIS_URL": app.config["REDIS_URL"],
            "RATELIMIT_STORAGE_URI": app.config["RATELIMIT_STORAGE_URI"],
            "SESSION_COOKIE_SECURE": False,
            "DEMO_MODE": True,
            "PAYFAST_SANDBOX": True,
        }
    )
    assert demo.test_client().get("/api/config").get_json() == {"demo_mode": True}
    with pytest.raises(RuntimeError, match="DEMO_MODE requires PAYFAST_SANDBOX=true"):
        create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
                "REDIS_URL": app.config["REDIS_URL"],
                "RATELIMIT_STORAGE_URI": app.config["RATELIMIT_STORAGE_URI"],
                "DEMO_MODE": True,
                "PAYFAST_SANDBOX": False,
            }
        )
