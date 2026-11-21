"""Start a local test-configured app and run the Chromium auth smoke test."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def prepare_test_databases(database_url: str, migration_url: str) -> None:
    admin_url = make_url(database_url).set(database="postgres")
    engine = create_engine(admin_url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            for target in (database_url, migration_url):
                name = make_url(target).database
                exists = connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": name},
                ).scalar_one_or_none()
                if not exists:
                    quoted = '"' + name.replace('"', '""') + '"'
                    connection.exec_driver_sql(f"CREATE DATABASE {quoted}")
    finally:
        engine.dispose()


def wait_until_ready(base_url: str, process: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + 90
    last_response = "no HTTP response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(
                f"Local Flask process exited with status {process.returncode}.\n{details}"
            )
        try:
            with urlopen(f"{base_url}/ready", timeout=2) as response:
                if response.status == 200:
                    return
                last_response = f"HTTP {response.status}"
        except URLError as error:
            status = getattr(error, "code", None)
            last_response = f"HTTP {status}" if status else str(error.reason)
        except OSError as error:
            last_response = str(error)
        time.sleep(0.5)
    details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    raise RuntimeError(
        f"Local Flask app did not become ready within 90 seconds ({last_response}).\n{details}"
    )


def main() -> int:
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_test",
    )
    migration_url = os.getenv(
        "MIGRATION_DATABASE_URL",
        "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform_migration_test",
    )
    redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
    port = int(os.getenv("E2E_PORT", "5001"))
    base_url = f"http://127.0.0.1:{port}"
    artifact_dir = ROOT / ".artifacts" / "e2e"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "server.log"
    server_env = os.environ.copy()
    server_env.update(
        {
            "APP_ENV": "development",
            "DATABASE_URL": database_url,
            "REDIS_URL": redis_url,
            "RATELIMIT_STORAGE_URI": redis_url,
            "SECRET_KEY": "local-e2e-only-secret",
            "EMAIL_BACKEND": "console",
            "PUBLIC_BASE_URL": base_url,
            "PAYFAST_SANDBOX": "true",
            "PORT": str(port),
        }
    )
    prepare_test_databases(database_url, migration_url)
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app:create_app", "db", "upgrade"],
        cwd=ROOT,
        env=server_env,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app:create_app", "seed-demo", "--reset"],
        cwd=ROOT,
        env=server_env,
        check=True,
    )

    with log_path.open("wb") as log_file:
        server = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "flask",
                "--app",
                "app:create_app",
                "run",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-reload",
            ],
            cwd=ROOT,
            env=server_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_until_ready(base_url, server, log_path)
            e2e_env = server_env.copy()
            e2e_env["E2E_BASE_URL"] = base_url
            e2e_env["E2E_EMAIL_LOG"] = str(log_path)
            test_paths = (
                ["tests/e2e/test_auth_smoke.py"]
                if os.getenv("E2E_SMOKE_ONLY", "false").lower() in {"1", "true", "yes"}
                else ["tests/e2e/test_auth_layout.py"]
                if os.getenv("E2E_LAYOUT_ONLY", "false").lower() in {"1", "true", "yes"}
                else ["tests/e2e"]
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--browser",
                    "chromium",
                    *test_paths,
                ],
                cwd=ROOT,
                env=e2e_env,
                check=True,
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
