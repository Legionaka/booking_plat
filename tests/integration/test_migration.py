"""Exercise upgrade and rollback on a dedicated empty PostgreSQL database."""

import os
import subprocess
import threading
import uuid

import pytest
from alembic import command
from alembic.config import Config
from app import web_startup
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


@pytest.fixture
def blank_database_url(migration_url):
    database = f"startup_test_{uuid.uuid4().hex[:16]}"
    admin_url = make_url(migration_url).set(database="postgres")
    engine = create_engine(admin_url)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
    isolated_url = make_url(migration_url).set(database=database).render_as_string(
        hide_password=False
    )
    try:
        yield isolated_url
    finally:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{database}' AND pid <> pg_backend_pid()"
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database}"')
        engine.dispose()


def _configure_startup_seed_environment(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("MIGRATE_ON_STARTUP", "true")
    monkeypatch.setenv("SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_OWNER_EMAIL", "entrypoint-owner@fade-lab.demo")
    monkeypatch.setenv("DEMO_OWNER_PASSWORD", "Entrypoint-Demo-Owner-Unique-2026!")


def test_real_web_startup_migrates_fresh_database_then_seeds_and_serves(
    blank_database_url, monkeypatch
):
    _configure_startup_seed_environment(monkeypatch, blank_database_url)
    engine = create_engine(blank_database_url)
    try:
        assert inspect(engine).get_table_names() == []
        served = []
        monkeypatch.setattr(web_startup, "_serve", lambda: served.append(True))

        web_startup.main()

        assert served == [True]
        inspector = inspect(engine)
        assert "users" in inspector.get_table_names()
        with engine.connect() as connection:
            business = connection.execute(
                text("SELECT id FROM businesses WHERE slug = 'fade-lab'")
            ).scalar_one()
            booking_count = connection.execute(
                text("SELECT count(*) FROM bookings WHERE business_id = :business_id"),
                {"business_id": business},
            ).scalar_one()
            assert booking_count > 100
    finally:
        engine.dispose()


def test_real_web_startup_repeated_on_populated_database_is_idempotent(
    blank_database_url, monkeypatch
):
    _configure_startup_seed_environment(monkeypatch, blank_database_url)
    served = []
    monkeypatch.setattr(web_startup, "_serve", lambda: served.append(True))
    web_startup.main()

    engine = create_engine(blank_database_url)
    try:
        with engine.connect() as connection:
            before = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM businesses WHERE slug='fade-lab'), "
                    "(SELECT count(*) FROM bookings), "
                    "(SELECT count(*) FROM users WHERE email LIKE '%@fade-lab.demo')"
                )
            ).one()

        web_startup.main()

        with engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM businesses WHERE slug='fade-lab'), "
                    "(SELECT count(*) FROM bookings), "
                    "(SELECT count(*) FROM users WHERE email LIKE '%@fade-lab.demo')"
                )
            ).one()
        assert served == [True, True]
        assert after == before
    finally:
        engine.dispose()


def test_flask_migration_and_inspection_commands_do_not_seed_on_empty_database(
    blank_database_url, monkeypatch
):
    _configure_startup_seed_environment(monkeypatch, blank_database_url)
    env = os.environ.copy()
    engine = create_engine(blank_database_url)
    try:
        assert inspect(engine).get_table_names() == []
        for command_args in (
            ["db", "upgrade"],
            ["db", "check"],
            ["routes"],
        ):
            result = subprocess.run(
                [
                    os.sys.executable,
                    "-m",
                    "flask",
                    "--app",
                    "app:create_app",
                    *command_args,
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            with engine.connect() as connection:
                seeded = connection.execute(
                    text("SELECT count(*) FROM businesses WHERE slug='fade-lab'")
                ).scalar_one()
                assert seeded == 0
    finally:
        engine.dispose()


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


@pytest.mark.parametrize(
    ("lock_environment", "lock_value"),
    [("MIGRATE_ON_STARTUP", "true"), ("SEED_DEMO_ON_STARTUP", "true")],
)
def test_second_startup_waits_for_lock_then_leaves_head_unchanged(
    migration_url, monkeypatch, lock_environment, lock_value
):
    config = Config("migrations/alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
    command.upgrade(config, "head")
    monkeypatch.setenv("MIGRATE_ON_STARTUP", "false")
    monkeypatch.setenv("SEED_DEMO_ON_STARTUP", "false")
    monkeypatch.setenv(lock_environment, lock_value)
    monkeypatch.setenv("DATABASE_URL", migration_url)
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
            web_startup._with_advisory_lock(lambda: command.upgrade(config, "head"))
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
