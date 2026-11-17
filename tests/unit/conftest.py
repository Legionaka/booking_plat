"""Unit tests use pure functions and intentionally avoid PostgreSQL fixtures."""

import pytest
from app import create_app


@pytest.fixture(autouse=True)
def clean_database():
    """Shadow the integration-wide database cleanup fixture for unit tests."""
    yield




@pytest.fixture
def app():
    """Create a Flask app without connecting to the unit-test dependency clients."""
    return create_app(
        {
            "TESTING": True,
            "SESSION_COOKIE_SECURE": False,
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": 587,
            "SMTP_FROM_ADDRESS": "booking@example.test",
            "SMTP_TLS_MODE": "starttls",
            "SMTP_TIMEOUT_SECONDS": 10,
        }
    )
