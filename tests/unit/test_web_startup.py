import subprocess

import pytest
from app import create_app, web_startup
from app.web_startup import startup


def test_migration_failure_prevents_web_server_start():
    calls = []

    def migration():
        calls.append("migration")
        raise RuntimeError("migration failed")

    def serve():
        calls.append("serve")

    with pytest.raises(RuntimeError, match="migration failed"):
        startup(True, migration, serve)

    assert calls == ["migration"]


def test_startup_propagates_migration_process_failure_without_execing_gunicorn(monkeypatch):
    calls = []

    def migration():
        calls.append("migration")
        raise subprocess.CalledProcessError(1, ["flask", "db", "upgrade"])

    monkeypatch.setenv("MIGRATE_ON_STARTUP", "true")
    monkeypatch.setattr(web_startup, "_migrate", migration)
    monkeypatch.setattr(web_startup, "_serve", lambda: calls.append("gunicorn"))

    with pytest.raises(subprocess.CalledProcessError):
        web_startup.main()

    assert calls == ["migration"]


def test_startup_seed_requires_demo_mode_and_never_starts_services(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("DEMO_MODE", "false")
    calls = []
    monkeypatch.setattr(web_startup, "_migrate", lambda: calls.append("migration"))
    monkeypatch.setattr(web_startup, "_serve", lambda: calls.append("gunicorn"))

    with pytest.raises(RuntimeError, match="SEED_DEMO_ON_STARTUP=true requires DEMO_MODE=true"):
        web_startup.main()

    assert calls == []


def test_application_factory_refuses_seed_flag_without_demo_mode():
    with pytest.raises(RuntimeError, match="SEED_DEMO_ON_STARTUP=true requires DEMO_MODE=true"):
        create_app(
            {
                "APP_ENV": "development",
                "SEED_DEMO_ON_STARTUP": True,
                "DEMO_MODE": False,
                "DEMO_OWNER_PASSWORD": "A non-default owner password",
            }
        )


def test_startup_seed_rejects_repository_demo_password(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("DEMO_OWNER_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="non-default DEMO_OWNER_PASSWORD"):
        web_startup.main()


def test_web_server_starts_after_successful_migration_and_skips_when_disabled():
    calls = []
    startup(True, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["migration", "serve"]
    calls.clear()
    startup(False, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["serve"]
    calls.clear()
    startup(
        False,
        lambda: calls.append("migration-and-seed"),
        lambda: calls.append("serve"),
        seed_demo_on_startup=True,
    )
    assert calls == ["migration-and-seed", "serve"]
