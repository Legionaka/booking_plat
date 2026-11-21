"""Environment-backed application configuration."""

import os
from ipaddress import ip_address
from urllib.parse import urlsplit

DEFAULT_SECRET_KEY = "local-development-only"
DEFAULT_DEMO_OWNER_PASSWORD = "DemoOnly-ChangeMe-2026!"


def seed_startup_error(seed_enabled: bool, demo_mode: bool, owner_password: str) -> str | None:
    """Describe unsafe startup-seed configurations before any service starts."""
    if seed_enabled and not demo_mode:
        return "SEED_DEMO_ON_STARTUP=true requires DEMO_MODE=true."
    if seed_enabled and (
        not owner_password or owner_password == DEFAULT_DEMO_OWNER_PASSWORD
    ):
        return (
            "SEED_DEMO_ON_STARTUP requires a non-default DEMO_OWNER_PASSWORD "
            "set through the environment."
        )
    return None


def normalize_database_url(value: str) -> str:
    """Normalize provider PostgreSQL URL schemes for psycopg 3."""
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def is_loopback_url(value: str | None) -> bool:
    """Treat missing, malformed, and loopback service URLs as unsafe for production."""
    if not value:
        return True
    try:
        hostname = urlsplit(value).hostname
    except ValueError:
        return True
    if not hostname:
        return True
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


_database_url = normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform",
    )
)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    APP_ENV = os.getenv("APP_ENV", "development").lower()
    SQLALCHEMY_DATABASE_URI = _database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "redis://localhost:6379/1")
    RATELIMIT_KEY_PREFIX = os.getenv("RATELIMIT_KEY_PREFIX", "booking-platform:")
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = False
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend").lower()
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY", "")
    EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "")
    EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Booking Platform")
    EMAIL_MAILGUN_DOMAIN = os.getenv("EMAIL_MAILGUN_DOMAIN", "")
    EMAIL_MAILGUN_REGION = os.getenv("EMAIL_MAILGUN_REGION", "us").lower()
    SESSION_COOKIE_NAME = "booking_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    SERVER_SESSION_TTL_SECONDS = int(os.getenv("SERVER_SESSION_TTL_SECONDS", "86400"))
    AUTH_VERIFY_TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60
    AUTH_RESET_TOKEN_MAX_AGE_SECONDS = 60 * 60
    AUTH_REGISTER_RATE_LIMIT = os.getenv("AUTH_REGISTER_RATE_LIMIT", "20 per hour")
    AUTH_LOGIN_EMAIL_RATE_LIMIT = os.getenv("AUTH_LOGIN_EMAIL_RATE_LIMIT", "5 per minute")
    AUTH_LOGIN_IP_RATE_LIMIT = os.getenv("AUTH_LOGIN_IP_RATE_LIMIT", "30 per hour")
    AUTH_FORGOT_EMAIL_RATE_LIMIT = os.getenv("AUTH_FORGOT_EMAIL_RATE_LIMIT", "5 per hour")
    AUTH_FORGOT_IP_RATE_LIMIT = os.getenv("AUTH_FORGOT_IP_RATE_LIMIT", "30 per hour")
    AUTH_RESET_TOKEN_RATE_LIMIT = os.getenv("AUTH_RESET_TOKEN_RATE_LIMIT", "5 per hour")
    AUTH_RESET_IP_RATE_LIMIT = os.getenv("AUTH_RESET_IP_RATE_LIMIT", "30 per hour")
    AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT = os.getenv(
        "AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT", "3 per hour"
    )
    AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT = os.getenv(
        "AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT", "30 per hour"
    )
    AUTH_RESEND_VERIFICATION_COOLDOWN_SECONDS = int(
        os.getenv("AUTH_RESEND_VERIFICATION_COOLDOWN_SECONDS", "60")
    )
    PUBLIC_AVAILABILITY_RATE_LIMIT = os.getenv("PUBLIC_AVAILABILITY_RATE_LIMIT", "60 per minute")
    AVAILABILITY_MINIMUM_NOTICE_MINUTES = int(
        os.getenv("AVAILABILITY_MINIMUM_NOTICE_MINUTES", "120")
    )
    AVAILABILITY_MAXIMUM_ADVANCE_DAYS = int(
        os.getenv("AVAILABILITY_MAXIMUM_ADVANCE_DAYS", "60")
    )
    HOLD_MINUTES = int(os.getenv("HOLD_MINUTES", "15"))
    MAX_PENDING_HOLDS_PER_USER = int(os.getenv("MAX_PENDING_HOLDS_PER_USER", "3"))
    BOOKING_CREATE_RATE_LIMIT = os.getenv("BOOKING_CREATE_RATE_LIMIT", "10 per minute")
    RQ_QUEUE_NAME = os.getenv("RQ_QUEUE_NAME", "default")
    BOOKING_MANAGE_BASE_URL = os.getenv("BOOKING_MANAGE_BASE_URL", "http://localhost:5000")
    NOTIFICATION_BATCH_SIZE = int(os.getenv("NOTIFICATION_BATCH_SIZE", "100"))
    SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))
    NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS = int(
        os.getenv("NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS", "300")
    )
    NOTIFICATION_RETRY_INTERVALS_SECONDS = tuple(
        int(value)
        for value in os.getenv(
            "NOTIFICATION_RETRY_INTERVALS_SECONDS", "60,300,900,900"
        ).split(",")
    )
    PAYFAST_MERCHANT_ID = os.getenv("PAYFAST_MERCHANT_ID", "")
    PAYFAST_MERCHANT_KEY = os.getenv("PAYFAST_MERCHANT_KEY", "")
    PAYFAST_PASSPHRASE = os.getenv("PAYFAST_PASSPHRASE", "")
    PAYFAST_SANDBOX = os.getenv("PAYFAST_SANDBOX", "true").lower() in {"1", "true", "yes"}
    PAYFAST_ITN_RATE_LIMIT = os.getenv("PAYFAST_ITN_RATE_LIMIT", "600 per minute")
    PAYFAST_VALIDATE_TIMEOUT_SECONDS = int(os.getenv("PAYFAST_VALIDATE_TIMEOUT_SECONDS", "8"))
    PAYMENT_HOLD_MINUTES = int(os.getenv("PAYMENT_HOLD_MINUTES", "20"))
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000")
    DEMO_OWNER_EMAIL = os.getenv("DEMO_OWNER_EMAIL", "owner@fade-lab.demo")
    DEMO_OWNER_PASSWORD = os.getenv("DEMO_OWNER_PASSWORD", DEFAULT_DEMO_OWNER_PASSWORD)
    DEMO_OWNER_NAME = os.getenv("DEMO_OWNER_NAME", "Fade Lab Owner")
    WEB_WORKERS = int(os.getenv("WEB_WORKERS", "3"))
    PORT = int(os.getenv("PORT", "5000"))
    TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_ADDRESS = os.getenv("SMTP_FROM_ADDRESS", "")
    SMTP_TLS_MODE = os.getenv("SMTP_TLS_MODE", "starttls").lower()
    SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes"}
    MIGRATE_ON_STARTUP = os.getenv("MIGRATE_ON_STARTUP", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    SEED_DEMO_ON_STARTUP = os.getenv("SEED_DEMO_ON_STARTUP", "false").lower() in {
        "1",
        "true",
        "yes",
    }
