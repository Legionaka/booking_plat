"""Web entrypoint with fail-closed migration and optional demo-seed startup work."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

from app.config import DEFAULT_DEMO_OWNER_PASSWORD, seed_startup_error


def startup(
    migrate_on_startup: bool,
    migrate: Callable[[], None],
    serve: Callable[[], None],
    seed_demo_on_startup: bool = False,
) -> None:
    """Run migration/seed startup work before serving traffic."""
    if migrate_on_startup or seed_demo_on_startup:
        migrate()
    serve()


def _migrate() -> None:
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app:create_app", "db", "upgrade"],
        check=True,
    )


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
    startup(migrate_on_startup, _migrate, _serve, seed_demo_on_startup)


if __name__ == "__main__":
    main()
