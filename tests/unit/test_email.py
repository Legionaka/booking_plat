from types import SimpleNamespace

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


def _capture_kwargs(smtp, kwargs):
    smtp.kwargs = kwargs
    return smtp
