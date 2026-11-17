"""Exercise upgrade and rollback on a dedicated empty PostgreSQL database."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url


@pytest.fixture
def migration_url():
    url = os.getenv(
        "MIGRATION_DATABASE_URL",
        "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_migration_test",
    )
    if make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError(
            "MIGRATION_DATABASE_URL must point to PostgreSQL; SQLite is not supported"
        )
    return url


def test_initial_migration_upgrades_and_rolls_back(migration_url):
    config = Config("migrations/alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
    engine = create_engine(migration_url)
    try:
        # Normalize prior runs to the migration's empty-database starting point.
        with engine.connect() as connection:
            if inspect(connection).has_table("alembic_version"):
                command.downgrade(config, "base")

        command.upgrade(config, "head")
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert "bookings" in inspector.get_table_names()
            assert {"bookings_business_start", "bookings_customer"}.issubset(
                {item["name"] for item in inspector.get_indexes("bookings")}
            )

        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert "bookings" not in inspect(connection).get_table_names()

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "bookings" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
