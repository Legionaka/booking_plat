import subprocess

import pytest
from app import web_startup
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


def test_web_server_starts_after_successful_migration_and_skips_when_disabled():
    calls = []
    startup(True, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["migration", "serve"]
    calls.clear()
    startup(False, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["serve"]
