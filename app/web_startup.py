"""Production web entrypoint with optional fail-closed migrations."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable


def startup(
    migrate_on_startup: bool,
    migrate: Callable[[], None],
    serve: Callable[[], None],
) -> None:
    """Run migrations first when enabled; never serve after a migration failure."""
    if migrate_on_startup:
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
    migrate_on_startup = os.getenv("MIGRATE_ON_STARTUP", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    startup(migrate_on_startup, _migrate, _serve)


if __name__ == "__main__":
    main()
