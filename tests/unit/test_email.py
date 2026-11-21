import base64
import json
from io import BytesIO
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from app import create_app
from app.services import email


class _SMTPStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.message = None
        self.started_tls = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, _username, _password):
        return None

    def send_message(self, message):
        self.message = message


def test_smtp_headers_strip_crlf_from_subject_names_and_addresses(app, monkeypatch, caplog):
    smtp = _SMTPStub()
    monkeypatch.setattr(email, "SMTP", lambda **kwargs: _capture_kwargs(smtp, kwargs))
    monkeypatch.setattr(email, "SMTP_SSL", lambda **kwargs: _capture_kwargs(smtp, kwargs))
    app.config.update(
        SMTP_HOST="mail.example.test",
        SMTP_PORT=587,
        SMTP_USERNAME="user-secret",
        SMTP_PASSWORD="password-secret",
        SMTP_FROM_ADDRESS="booking@example.test\r\nBcc: attacker@example.test",
        SMTP_TLS_MODE="starttls",
        SMTP_TIMEOUT_SECONDS=7,
    )

    with app.app_context():
        email.SMTPEmailService._send(
            SimpleNamespace(email="customer@example.test\nBcc: attacker@example.test"),
            "Booking with Shop\r\nBcc: attacker@example.test",
            "Body",
        )

    assert smtp.message["Subject"] == "Booking with ShopBcc: attacker@example.test"
    assert "\r" not in str(smtp.message)
    assert "\nBcc:" not in str(smtp.message)
    assert "Bcc" not in smtp.message
    assert smtp.started_tls is True
    assert smtp.kwargs["timeout"] == 7
    assert "user-secret" not in caplog.text
    assert "password-secret" not in caplog.text


def test_smtp_ssl_mode_uses_ssl_transport(app, monkeypatch):
    smtp = _SMTPStub()
    monkeypatch.setattr(email, "SMTP_SSL", lambda **kwargs: _capture_kwargs(smtp, kwargs))
    app.config.update(
        SMTP_HOST="mail.example.test",
        SMTP_PORT=465,
        SMTP_FROM_ADDRESS="booking@example.test",
        SMTP_TLS_MODE="ssl",
        SMTP_TIMEOUT_SECONDS=3,
    )
    with app.app_context():
        email.SMTPEmailService._send(
            SimpleNamespace(email="customer@example.test"), "Hello", "Body"
        )
    assert "context" in smtp.kwargs
    assert smtp.kwargs["timeout"] == 3
    assert smtp.started_tls is False


def test_console_email_prints_complete_message_in_development(app, capsys):
    app.config.update(APP_ENV="development", PUBLIC_BASE_URL="http://localhost:5000")
    user = SimpleNamespace(email="customer@example.test")

    with app.app_context():
        email.ConsoleEmailService().send_password_reset(user, "private-reset-token")

    output = capsys.readouterr().out
    assert "BEGIN DEVELOPMENT EMAIL" in output
    assert "To: customer@example.test" in output
    assert "Subject: Reset your password" in output
    assert "Body:" in output
    assert "http://localhost:5000/auth/reset?token=private-reset-token" in output
    assert "END DEVELOPMENT EMAIL" in output


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_console_email_never_prints_body_or_token_outside_development(
    app, capsys, caplog, environment
):
    app.config.update(APP_ENV=environment, PUBLIC_BASE_URL="http://localhost:5000")
    user = SimpleNamespace(email="customer@example.test")

    with app.app_context():
        email.ConsoleEmailService().send_password_reset(user, "private-reset-token")

    output = capsys.readouterr().out
    assert output == ""
    assert "private-reset-token" not in caplog.text
    assert "/auth/reset" not in caplog.text


class _HTTPResponse(BytesIO):
    def __init__(self, status=202):
        super().__init__(b"{}")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


@pytest.mark.parametrize("provider", ["brevo", "resend", "mailgun"])
def test_http_api_email_builds_provider_specific_request(provider, app):
    requests = []

    def transport(request, timeout):
        requests.append((request, timeout))
        return _HTTPResponse()

    service = email.HttpApiEmailService(
        provider,
        "private-api-key",
        "bookings@example.test",
        "Shop Name",
        "mg.example.test",
        "eu",
        transport,
    )
    user = SimpleNamespace(email="person@example.test")
    with app.app_context():
        service.send_notification_email(user, "Booking update", "Plain body", "<p>HTML</p>")

    request, timeout = requests[0]
    assert timeout == 10
    assert request.full_url.startswith("https://")
    assert request.get_method() == "POST"
    if provider == "brevo":
        body = json.loads(request.data)
        assert request.full_url == "https://api.brevo.com/v3/smtp/email"
        assert request.get_header("Api-key") == "private-api-key"
        assert body["sender"] == {"name": "Shop Name", "email": "bookings@example.test"}
        assert body["to"] == [{"email": "person@example.test"}]
        assert body["textContent"] == "Plain body"
        assert body["htmlContent"] == "<p>HTML</p>"
    elif provider == "resend":
        body = json.loads(request.data)
        assert request.full_url == "https://api.resend.com/emails"
        assert request.get_header("Authorization") == "Bearer private-api-key"
        assert body["from"] == "Shop Name <bookings@example.test>"
        assert body["to"] == ["person@example.test"]
        assert body["text"] == "Plain body"
        assert body["html"] == "<p>HTML</p>"
    else:
        assert request.full_url == "https://api.eu.mailgun.net/v3/mg.example.test/messages"
        assert request.get_header("Authorization") == "Basic " + base64.b64encode(
            b"api:private-api-key"
        ).decode("ascii")
        assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
        for part in (
            b'name="from"',
            b"Shop Name <bookings@example.test>",
            b'name="to"',
            b"person@example.test",
            b"Plain body",
            b"<p>HTML</p>",
        ):
            assert part in request.data


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(401, False), (403, False), (422, False), (429, True), (500, True), (503, True)],
)
def test_http_api_email_classifies_http_failures(status, retryable, app, monkeypatch):
    logs = []
    monkeypatch.setattr(app.logger, "warning", lambda template, *args: logs.append(template % args))
    service = email.HttpApiEmailService(
        "resend",
        "api-secret-do-not-log",
        "bookings@example.test",
        transport=lambda *_args, **_kwargs: _HTTPResponse(status),
    )
    with app.app_context(), pytest.raises(email.EmailDeliveryError) as caught:
        service.send_notification_email(
            SimpleNamespace(email="customer.private@example.test"),
            "Subject not logged",
            "Sensitive message body",
            "<p>Sensitive html</p>",
        )

    assert caught.value.retryable is retryable
    assert caught.value.status_code == status
    logs = "\n".join(logs)
    assert "api-secret-do-not-log" not in logs
    assert "customer.private@example.test" not in logs
    assert "Sensitive message body" not in logs
    assert "c***@masked" in logs


def test_http_api_timeout_is_retryable_and_does_not_log_secret_or_body(app, monkeypatch):
    logs = []
    monkeypatch.setattr(app.logger, "warning", lambda template, *args: logs.append(template % args))
    def timeout(*_args, **_kwargs):
        raise TimeoutError("secret should not leak")

    service = email.HttpApiEmailService(
        "resend", "private-api-key", "bookings@example.test", transport=timeout
    )
    with app.app_context(), pytest.raises(email.EmailDeliveryError) as caught:
        service.send_notification_email(
            SimpleNamespace(email="person@example.test"), "Subject", "Private body", "<b>HTML</b>"
        )

    assert caught.value.retryable is True
    logs = "\n".join(logs)
    assert "private-api-key" not in logs
    assert "secret should not leak" not in logs
    assert "Private body" not in logs
    assert "person@example.test" not in logs


def test_http_api_network_failure_is_retryable(app):
    service = email.HttpApiEmailService(
        "resend",
        "private-api-key",
        "bookings@example.test",
        transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with app.app_context(), pytest.raises(email.EmailDeliveryError) as caught:
        service.send_notification_email(
            SimpleNamespace(email="person@example.test"), "Subject", "Body", "<p>Body</p>"
        )
    assert caught.value.retryable is True


def test_http_api_headers_strip_crlf_and_logs_mask_recipient(app, monkeypatch):
    requests = []
    logs = []
    monkeypatch.setattr(app.logger, "warning", lambda template, *args: logs.append(template % args))
    service = email.HttpApiEmailService(
        "resend",
        "private-api-key",
        "bookings@example.test\r\nBcc: injected@example.test",
        "Safe Name\r\nBcc: injected@example.test",
        transport=lambda request, **_kwargs: (requests.append(request) or _HTTPResponse(401)),
    )
    with app.app_context(), pytest.raises(email.EmailDeliveryError):
        service.send_notification_email(
            SimpleNamespace(email="person@example.test\r\nBcc: injected@example.test"),
            "Subject\r\nBcc: injected@example.test",
            "Private body",
            "<b>Private body</b>",
        )

    body = json.loads(requests[0].data)
    expected_sender = (
        "Safe NameBcc: injected@example.test "
        "<bookings@example.testBcc: injected@example.test>"
    )
    assert body["from"] == expected_sender
    assert body["to"] == ["person@example.testBcc: injected@example.test"]
    assert body["subject"] == "SubjectBcc: injected@example.test"
    logs = "\n".join(logs)
    assert "person@example.test\r\nBcc" not in logs
    assert "private-api-key" not in logs
    assert "Private body" not in logs
    assert "p***@masked" in logs


@pytest.mark.parametrize(
    ("provider", "api_key", "sender", "mailgun_domain", "message"),
    [
        ("smtp", "key", "sender@example.test", "", "EMAIL_PROVIDER"),
        ("resend", "", "sender@example.test", "", "EMAIL_API_KEY"),
        ("resend", "key", "", "", "EMAIL_FROM_ADDRESS"),
        ("mailgun", "key", "sender@example.test", "", "EMAIL_MAILGUN_DOMAIN"),
    ],
)
def test_http_api_service_rejects_invalid_provider_configuration(
    provider, api_key, sender, mailgun_domain, message
):
    with pytest.raises(ValueError, match=message):
        email.HttpApiEmailService(provider, api_key, sender, mailgun_domain=mailgun_domain)


def _valid_production_email_config():
    return {
        "APP_ENV": "production",
        "SECRET_KEY": "production-secret-that-is-not-default",
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://app:secret@db.example.test/booking",
        "REDIS_URL": "redis://redis.example.test:6379/0",
        "RATELIMIT_STORAGE_URI": "redis://redis.example.test:6379/1",
        "EMAIL_BACKEND": "http_api",
        "EMAIL_PROVIDER": "resend",
        "EMAIL_API_KEY": "provider-secret",
        "EMAIL_FROM_ADDRESS": "bookings@example.test",
        "SESSION_COOKIE_SECURE": True,
        "PUBLIC_BASE_URL": "https://booking.example.test",
        "BOOKING_MANAGE_BASE_URL": "https://booking.example.test",
        "TRUSTED_PROXY_HOPS": 1,
        "PAYFAST_MERCHANT_ID": "merchant-id",
        "PAYFAST_MERCHANT_KEY": "merchant-key",
        "PAYFAST_PASSPHRASE": "merchant-passphrase",
        "PAYFAST_SANDBOX": False,
        "DEMO_OWNER_PASSWORD": "unique-production-demo-password",
    }


@pytest.mark.parametrize(
    ("override", "error_name"),
    [
        ({"EMAIL_BACKEND": "console"}, "EMAIL_BACKEND"),
        ({"EMAIL_API_KEY": ""}, "EMAIL_API_KEY"),
        ({"EMAIL_FROM_ADDRESS": ""}, "EMAIL_FROM_ADDRESS"),
        ({"EMAIL_PROVIDER": "unknown"}, "EMAIL_PROVIDER"),
        ({"EMAIL_PROVIDER": "mailgun"}, "EMAIL_MAILGUN_DOMAIN"),
    ],
)
def test_production_email_guard_rejects_unsafe_configuration(override, error_name):
    with pytest.raises(RuntimeError, match=error_name):
        create_app({**_valid_production_email_config(), **override})


def test_production_accepts_https_email_and_builds_selected_provider():
    application = create_app(_valid_production_email_config())
    assert isinstance(application.extensions["email_service"], email.HttpApiEmailService)
    assert application.extensions["email_service"].provider == "resend"


def _capture_kwargs(smtp, kwargs):
    smtp.kwargs = kwargs
    return smtp
