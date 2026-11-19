"""Email service interface and development console backend."""

from email.message import EmailMessage
from smtplib import SMTP, SMTP_SSL
from typing import Protocol
from urllib.parse import quote

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
    """Log development email links so local flows can be completed without a mailbox."""

    def send_verification(self, user: User, token: str) -> None:
        self._log_message("Verification", "/auth/verify", token)

    def send_password_reset(self, user: User, token: str) -> None:
        self._log_message("Password reset", "/auth/reset", token)

    @classmethod
    def _log_message(cls, label: str, path: str, token: str) -> None:
        if current_app.config.get("CONSOLE_EMAIL_EXPOSE_LINKS", False):
            current_app.logger.info("%s email prepared: %s", label, cls._auth_link(path, token))
        else:
            current_app.logger.info("%s email prepared", label)

    @staticmethod
    def _auth_link(path: str, token: str) -> str:
        base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
        return f"{base_url}{path}?token={quote(token, safe='')}"

    def send_booking_confirmation(
        self, user: User, booking: Booking, business: Business, service: Service
    ) -> None:
        current_app.logger.info("Booking confirmation email prepared")

    def send_notification_email(
        self, user: User, subject: str, text_body: str, html_body: str
    ) -> None:
        current_app.logger.info("Notification email prepared")


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


def build_email_service(backend: str) -> EmailService:
    if backend == "console":
        return ConsoleEmailService()
    if backend == "smtp":
        return SMTPEmailService()
    raise ValueError(f"Unsupported EMAIL_BACKEND: {backend}")
