"""Web entrypoint with fail-closed migration and optional demo-seed startup work."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

from sqlalchemy import create_engine

from app.config import (
    DEFAULT_DEMO_OWNER_PASSWORD,
    normalize_database_url,
    seed_startup_error,
)
from app.migration_lock import run_with_advisory_lock


def startup(
    migrate_on_startup: bool,
    migrate: Callable[[], None],
    serve: Callable[[], None],
    seed_demo_on_startup: bool = False,
    seed: Callable[[], None] | None = None,
    lock: Callable[[Callable[[], None]], None] | None = None,
) -> None:
    """Run migrations and optional seed before serving traffic."""
    if migrate_on_startup or seed_demo_on_startup:
        def prepare() -> None:
            migrate()
            if seed_demo_on_startup:
                if seed is None:
                    raise RuntimeError(
                        "Demo seed step is enabled but no seed command is configured."
                    )
                seed()

        if lock is None:
            prepare()
        else:
            lock(prepare)
    serve()


def _run_command(command: list[str], step_name: str) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"{step_name} failed (subprocess exited with status {exc.returncode})."
        ) from exc


def _migrate() -> None:
    _run_command(
        [sys.executable, "-m", "flask", "--app", "app:create_app", "db", "upgrade"],
        "Startup migration step",
    )


def _seed_demo() -> None:
    """Run the explicit seed CLI command after migration, never from Alembic."""
    _run_command(
        [sys.executable, "-m", "flask", "--app", "app:create_app", "seed-demo"],
        "Demo seed step",
    )


def _with_advisory_lock(callback: Callable[[], None]) -> None:
    """Keep one PostgreSQL session lock across migration and optional seeding."""
    database_url = normalize_database_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform",
        )
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            run_with_advisory_lock(connection, callback, enabled=True)
    finally:
        engine.dispose()


def _serve() -> None:
    args = [
        "gunicorn",
        "--bind",
        f"0.0.0.0:{os.getenv('PORT', '5000')}",
        "--workers",
        os.getenv("WEB_WORKERS", "3"),
        "--logger-class",
        "app.gunicorn_logging.JsonGunicornLogger",
        "app:create_app()",
    ]
    os.execvp(args[0], args)


def main() -> None:
    truthy = {"1", "true", "yes"}
    migrate_on_startup = os.getenv("MIGRATE_ON_STARTUP", "false").lower() in truthy
    seed_demo_on_startup = os.getenv("SEED_DEMO_ON_STARTUP", "false").lower() in truthy
    demo_mode = os.getenv("DEMO_MODE", "false").lower() in truthy
    owner_password = os.getenv("DEMO_OWNER_PASSWORD", DEFAULT_DEMO_OWNER_PASSWORD)
    seed_error = seed_startup_error(seed_demo_on_startup, demo_mode, owner_password)
    if seed_error:
        raise RuntimeError(seed_error)
    startup(
        migrate_on_startup,
        _migrate,
        _serve,
        seed_demo_on_startup,
        seed=_seed_demo,
        lock=_with_advisory_lock,
    )


if __name__ == "__main__":
    main()
