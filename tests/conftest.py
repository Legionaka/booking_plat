"""PostgreSQL-backed test fixtures."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app import create_app
from app.extensions import db
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _postgres_url(variable: str, fallback: str) -> str:
    url = os.getenv(variable, fallback)
    if make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError(f"{variable} must point to PostgreSQL; SQLite is not supported")
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _postgres_url(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_test",
    )


@pytest.fixture(scope="session")
def app(test_database_url: str):
    test_prefix = uuid4().hex
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": test_database_url,
            "REDIS_URL": os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"),
            "RATELIMIT_STORAGE_URI": os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"),
            "SESSION_COOKIE_SECURE": False,
            "BOOKING_CREATE_RATE_LIMIT": "100 per minute",
            "RATELIMIT_KEY_PREFIX": f"test:{test_prefix}:",
            "SERVER_SESSION_KEY_PREFIX": f"booking-platform:test-session:{test_prefix}:",
        }
    )
    yield application
    with application.app_context():
        db.session.remove()


@pytest.fixture(scope="session")
def apply_test_migrations(test_database_url: str) -> None:
    alembic_config = Config("migrations/alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    command.upgrade(alembic_config, "head")


@pytest.fixture(autouse=True)
def clean_database(app, apply_test_migrations) -> None:
    # TEST_REDIS_URL defaults to Redis DB 15, reserved for isolated test state.
    Redis.from_url(app.config["RATELIMIT_STORAGE_URI"]).flushdb()
    with app.app_context():
        db.session.execute(
            text(
                "TRUNCATE TABLE audit_log, notifications, payments, bookings, time_off, "
                "working_hours, staff_services, services, staff, memberships, users, businesses "
                "RESTART IDENTITY CASCADE"
            )
        )
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def database_engine(test_database_url: str):
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()
