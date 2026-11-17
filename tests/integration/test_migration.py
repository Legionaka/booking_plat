"""Exercise upgrade and rollback on a dedicated empty PostgreSQL database."""

import os
import threading

import pytest
from alembic import command
from alembic.config import Config
from app.migration_lock import MIGRATION_ADVISORY_LOCK_ID
from sqlalchemy import create_engine, inspect, text
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


def test_second_startup_waits_for_lock_then_leaves_head_unchanged(migration_url, monkeypatch):
    config = Config("migrations/alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
    command.upgrade(config, "head")
    monkeypatch.setenv("MIGRATE_ON_STARTUP", "true")
    engine = create_engine(migration_url)
    with engine.connect() as connection:
        revision_before = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    holder = engine.connect()
    holder.execute(
        text("SELECT pg_advisory_lock(:lock_id)"),
        {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
    )
    holder.commit()
    entered = threading.Event()
    completed = threading.Event()
    failures = []

    def second_startup():
        entered.set()
        try:
            command.upgrade(config, "head")
        except Exception as exc:  # surfaced in the main test thread below
            failures.append(exc)
        finally:
            completed.set()

    thread = threading.Thread(target=second_startup)
    try:
        thread.start()
        assert entered.wait(timeout=2)
        assert not completed.wait(timeout=0.25)
        holder.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
        )
        holder.commit()
        assert completed.wait(timeout=10)
        thread.join(timeout=1)
        assert failures == []
        with engine.connect() as connection:
            revision_after = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision_after == revision_before
    finally:
        if thread.is_alive():
            holder.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
            )
            holder.commit()
            thread.join(timeout=2)
        holder.close()
        engine.dispose()
