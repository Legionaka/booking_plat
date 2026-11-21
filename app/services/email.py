"""Email service interface and development console backend."""

import base64
import json
import secrets
import ssl
import sys
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from smtplib import SMTP, SMTP_SSL
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from flask import current_app

from app.models import Booking, Business, Service, User


class EmailService(Protocol):
    def send_verification(self, user: User, token: str) -> None: ...

    def send_password_reset(self, user: User, token: str) -> None: ...

    def send_booking_confirmation(
        self, user: User, booking: Booking, business: Business, service: Service
    ) -> None: ...

    def send_notification_email(
        self, user: User, subject: str, text_body: str, html_body: str
    ) -> None: ...


class ConsoleEmailService:
    """Write complete messages only in development; redact all other environments."""

    def send_verification(self, user: User, token: str) -> None:
        url = self._auth_link("/auth/verify", token)
        self._log_message(user, "Verify your email", f"Verify your email address: {url}")

    def send_password_reset(self, user: User, token: str) -> None:
        url = self._auth_link("/auth/reset", token)
        self._log_message(user, "Reset your password", f"Reset your password: {url}")

    @staticmethod
    def _log_message(user: User, subject: str, text_body: str) -> None:
        if current_app.config.get("APP_ENV") == "development":
            block = (
                "========== BEGIN DEVELOPMENT EMAIL ==========\n"
                f"To: {user.email}\n"
                f"Subject: {subject}\n"
                "Body:\n"
                f"{text_body}\n"
                "========== END DEVELOPMENT EMAIL ==========\n"
            )
            sys.stdout.write(block)
            sys.stdout.flush()
            return
        current_app.logger.info("%s email prepared", subject)

    @staticmethod
    def _auth_link(path: str, token: str) -> str:
        base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
        return f"{base_url}{path}?token={quote(token, safe='')}"

    def send_booking_confirmation(
        self, user: User, booking: Booking, business: Business, service: Service
    ) -> None:
        self._log_message(
            user,
            f"Booking confirmed with {business.name}",
            f"Your {service.name} booking has been confirmed. Booking reference: {booking.id}.",
        )

    def send_notification_email(
        self, user: User, subject: str, text_body: str, html_body: str
    ) -> None:
        self._log_message(user, subject, text_body)


class SMTPEmailService:
    """Deliver plain text and optional HTML messages via configured SMTP."""

    @staticmethod
    def _safe_header(value: str) -> str:
        """Remove line breaks so untrusted header values cannot add headers."""
        return str(value).replace("\r", "").replace("\n", "")

    @staticmethod
    def _send(user: User, subject: str, text_body: str, html_body: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = SMTPEmailService._safe_header(
            current_app.config["SMTP_FROM_ADDRESS"]
        )
        message["To"] = SMTPEmailService._safe_header(user.email)
        message["Subject"] = SMTPEmailService._safe_header(subject)
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        tls_mode = current_app.config["SMTP_TLS_MODE"]
        smtp_type = SMTP_SSL if tls_mode == "ssl" else SMTP
        connection_args = {
            "host": current_app.config["SMTP_HOST"],
            "port": current_app.config["SMTP_PORT"],
            "timeout": current_app.config["SMTP_TIMEOUT_SECONDS"],
        }
        if tls_mode == "ssl":
            import ssl

            connection_args["context"] = ssl.create_default_context()
        with smtp_type(**connection_args) as server:
            if tls_mode == "starttls":
                server.starttls()
            username = current_app.config["SMTP_USERNAME"]
            if username:
                server.login(username, current_app.config["SMTP_PASSWORD"])
            server.send_message(message)

    def send_verification(self, user: User, token: str) -> None:
        url = self._auth_link("/auth/verify", token)
        self._send(user, "Verify your email", f"Verify your email address: {url}")

    def send_password_reset(self, user: User, token: str) -> None:
        url = self._auth_link("/auth/reset", token)
        self._send(user, "Reset your password", f"Reset your password: {url}")

    @staticmethod
    def _auth_link(path: str, token: str) -> str:
        base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
        return f"{base_url}{path}?token={quote(token, safe='')}"

    def send_booking_confirmation(
        self, user: User, booking: Booking, business: Business, service: Service
    ) -> None:
        self._send(
            user,
            f"Booking confirmed with {business.name}",
            f"Your {service.name} booking has been confirmed. Booking reference: {booking.id}.",
        )

    def send_notification_email(
        self, user: User, subject: str, text_body: str, html_body: str
    ) -> None:
        self._send(user, subject, text_body, html_body)


class EmailDeliveryError(Exception):
    """Safe provider delivery failure with explicit outbox retry semantics."""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


def _https_open(request: Request, timeout: float):
    """Open an HTTPS request with verified TLS and no protocol-changing redirects."""

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = build_opener(
        HTTPSHandler(context=ssl.create_default_context()),
        NoRedirect(),
    )
    return opener.open(request, timeout=timeout)


class HttpApiEmailService:
    """Send email through Brevo, Resend, or Mailgun's HTTPS API."""

    TIMEOUT_SECONDS = 10
    PROVIDERS = {"brevo", "resend", "mailgun"}

    def __init__(
        self,
        provider: str,
        api_key: str,
        from_address: str,
        from_name: str = "Booking Platform",
        mailgun_domain: str = "",
        mailgun_region: str = "us",
        transport: Callable = _https_open,
    ):
        if provider not in self.PROVIDERS:
            raise ValueError("EMAIL_PROVIDER must be brevo, resend, or mailgun")
        if not api_key:
            raise ValueError("EMAIL_API_KEY is required for EMAIL_BACKEND=http_api")
        if not from_address:
            raise ValueError("EMAIL_FROM_ADDRESS is required for EMAIL_BACKEND=http_api")
        if provider == "mailgun" and not mailgun_domain:
            raise ValueError("EMAIL_MAILGUN_DOMAIN is required for the Mailgun provider")
        if mailgun_region not in {"us", "eu"}:
            raise ValueError("EMAIL_MAILGUN_REGION must be us or eu")
        self.provider = provider
        self.api_key = self._safe_header(api_key)
        self.from_address = self._safe_header(from_address)
        self.from_name = self._safe_header(from_name)
        self.mailgun_domain = mailgun_domain
        self.mailgun_region = mailgun_region
        self.transport = transport

    @staticmethod
    def _safe_header(value: str) -> str:
        return str(value).replace("\r", "").replace("\n", "")

    @staticmethod
    def _mask_recipient(address: str) -> str:
        safe_address = HttpApiEmailService._safe_header(address)
        local, separator, _ = safe_address.partition("@")
        if not separator:
            return "***"
        return f"{local[:1]}***@masked"

    def _request(self, user: User, subject: str, text_body: str, html_body: str | None):
        recipient = self._safe_header(user.email)
        subject = self._safe_header(subject)
        sender = f"{self.from_name} <{self.from_address}>"
        if self.provider == "brevo":
            url = "https://api.brevo.com/v3/smtp/email"
            payload = {
                "sender": {"name": self.from_name, "email": self.from_address},
                "to": [{"email": recipient}],
                "subject": subject,
                "textContent": text_body,
            }
            if html_body:
                payload["htmlContent"] = html_body
            headers = {"api-key": self.api_key, "Content-Type": "application/json"}
            data = json.dumps(payload).encode("utf-8")
        elif self.provider == "resend":
            url = "https://api.resend.com/emails"
            payload = {
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": text_body,
            }
            if html_body:
                payload["html"] = html_body
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = json.dumps(payload).encode("utf-8")
        else:
            domain_path = quote(self.mailgun_domain, safe=".-")
            api_host = "api.eu.mailgun.net" if self.mailgun_region == "eu" else "api.mailgun.net"
            url = f"https://{api_host}/v3/{domain_path}/messages"
            payload = {
                "from": sender,
                "to": recipient,
                "subject": subject,
                "text": text_body,
            }
            if html_body:
                payload["html"] = html_body
            token = base64.b64encode(f"api:{self.api_key}".encode()).decode("ascii")
            boundary = f"booking-platform-{secrets.token_hex(16)}"
            data = b"".join(
                b"--"
                + boundary.encode("ascii")
                + b"\r\nContent-Disposition: form-data; name=\""
                + name.encode("ascii")
                + b"\"\r\n\r\n"
                + value.encode("utf-8")
                + b"\r\n"
                for name, value in payload.items()
            ) + b"--" + boundary.encode("ascii") + b"--\r\n"
            headers = {
                "Authorization": f"Basic {token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
        return Request(url, data=data, headers=headers, method="POST"), recipient

    def _send(
        self, user: User, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        request, recipient = self._request(user, subject, text_body, html_body)
        masked_recipient = self._mask_recipient(recipient)
        try:
            with self.transport(request, timeout=self.TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
        except HTTPError as error:
            status = error.code
        except TimeoutError:
            current_app.logger.warning(
                "Email API delivery failed provider=%s recipient=%s failure=timeout",
                self.provider,
                masked_recipient,
            )
            raise EmailDeliveryError("Email provider request timed out", retryable=True) from None
        except URLError:
            current_app.logger.warning(
                "Email API delivery failed provider=%s recipient=%s failure=network",
                self.provider,
                masked_recipient,
            )
            raise EmailDeliveryError(
                "Email provider network request failed", retryable=True
            ) from None

        if 200 <= status < 300:
            current_app.logger.info(
                "Email API delivery succeeded provider=%s recipient=%s",
                self.provider,
                masked_recipient,
            )
            return

        retryable = status == 429 or 500 <= status <= 599
        current_app.logger.warning(
            "Email API delivery failed provider=%s recipient=%s status=%s retryable=%s",
            self.provider,
            masked_recipient,
            status,
            retryable,
        )
        raise EmailDeliveryError(
            f"Email provider returned HTTP {status}",
            retryable=retryable,
            status_code=status,
        )

    def send_verification(self, user: User, token: str) -> None:
        url = SMTPEmailService._auth_link("/auth/verify", token)
        self._send(user, "Verify your email", f"Verify your email address: {url}")

    def send_password_reset(self, user: User, token: str) -> None:
        url = SMTPEmailService._auth_link("/auth/reset", token)
        self._send(user, "Reset your password", f"Reset your password: {url}")

    def send_booking_confirmation(
        self, user: User, booking: Booking, business: Business, service: Service
    ) -> None:
        self._send(
            user,
            f"Booking confirmed with {business.name}",
            f"Your {service.name} booking has been confirmed. Booking reference: {booking.id}.",
        )

    def send_notification_email(
        self, user: User, subject: str, text_body: str, html_body: str
    ) -> None:
        self._send(user, subject, text_body, html_body)


def build_email_service(
    backend: str,
    config: Mapping[str, object] | None = None,
    *,
    transport: Callable = _https_open,
) -> EmailService:
    if backend == "console":
        return ConsoleEmailService()
    if backend == "smtp":
        return SMTPEmailService()
    if backend == "http_api":
        settings = config if config is not None else current_app.config
        return HttpApiEmailService(
            provider=str(settings.get("EMAIL_PROVIDER", "resend")),
            api_key=str(settings.get("EMAIL_API_KEY", "")),
            from_address=str(settings.get("EMAIL_FROM_ADDRESS", "")),
            from_name=str(settings.get("EMAIL_FROM_NAME", "Booking Platform")),
            mailgun_domain=str(settings.get("EMAIL_MAILGUN_DOMAIN", "")),
            mailgun_region=str(settings.get("EMAIL_MAILGUN_REGION", "us")),
            transport=transport,
        )
    raise ValueError(f"Unsupported EMAIL_BACKEND: {backend}")
