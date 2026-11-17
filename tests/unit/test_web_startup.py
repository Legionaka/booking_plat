import pytest
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


def test_web_server_starts_after_successful_migration_and_skips_when_disabled():
    calls = []
    startup(True, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["migration", "serve"]
    calls.clear()
    startup(False, lambda: calls.append("migration"), lambda: calls.append("serve"))
    assert calls == ["serve"]
