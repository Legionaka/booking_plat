"""Start a local test-configured app and run the Chromium auth smoke test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

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


def verify_seeded_login(base_url: str, email: str, password: str) -> None:
    """Prove that the running server sees the seeded owner before browser flows start."""
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    with client.open(f"{base_url}/api/auth/csrf", timeout=20) as response:
        csrf = json.load(response)["data"]["csrf_token"]
    request = Request(
        f"{base_url}/api/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
        method="POST",
    )
    try:
        with client.open(request, timeout=20) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
    if status != 200:
        raise RuntimeError(f"Seeded demo login smoke check returned HTTP {status}.")


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
    server_env.setdefault("DEMO_OWNER_EMAIL", "owner@fade-lab.demo")
    server_env.setdefault("DEMO_OWNER_PASSWORD", "DemoOnly-ChangeMe-2026!")
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
            "AUTH_LOGIN_EMAIL_RATE_LIMIT": "100 per minute",
            "AUTH_LOGIN_IP_RATE_LIMIT": "500 per hour",
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
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from app import create_app; from app.services.auth import authenticate; "
            "app=create_app({'TESTING': True}); "
            "ctx=app.app_context(); ctx.push(); "
            "authenticate(app.config['DEMO_OWNER_EMAIL'], app.config['DEMO_OWNER_PASSWORD']); "
            "authenticate('customer01@fade-lab.demo', 'Demo-Customer-01-ChangeMe!'); "
            "ctx.pop()",
        ],
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
            verify_seeded_login(
                base_url,
                str(server_env.get("DEMO_OWNER_EMAIL", "owner@fade-lab.demo")),
                str(server_env.get("DEMO_OWNER_PASSWORD", "DemoOnly-ChangeMe-2026!")),
            )
            e2e_env = server_env.copy()
            e2e_env["E2E_BASE_URL"] = base_url
            e2e_env["E2E_EMAIL_LOG"] = str(log_path)
            requested_paths = os.getenv("E2E_TEST_PATHS", "").strip()
            test_paths = (
                requested_paths.split(os.pathsep)
                if requested_paths
                else ["tests/e2e/test_auth_smoke.py"]
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
