"""Run the complete local CI check sequence from one command."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def ensure_test_databases() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    urls = [
        os.getenv(
            "TEST_DATABASE_URL",
            "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_test",
        ),
        os.getenv(
            "MIGRATION_DATABASE_URL",
            "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_migration_test",
        ),
    ]
    admin_url = make_url(urls[0]).set(database="postgres")
    engine = create_engine(admin_url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            for url in urls:
                database = make_url(url).database
                exists = connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": database},
                ).scalar_one_or_none()
                if not exists:
                    quoted_name = '"' + database.replace('"', '""') + '"'
                    connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="run the optional Chromium authentication browser smoke test",
    )
    args = parser.parse_args()
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--require-hashes",
            "-r",
            "requirements-dev.txt",
        ]
    )
    ensure_test_databases()
    run([sys.executable, "-m", "ruff", "check", "."])
    run([sys.executable, "scripts/check_frontend_policy.py"])
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--ignore=tests/e2e",
        ]
    )
    if args.e2e:
        run([sys.executable, "scripts/run_e2e.py"])
    run(["docker", "build", "--tag", "booking-platform:ci", "."])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
