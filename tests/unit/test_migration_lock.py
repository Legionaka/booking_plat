from app.migration_lock import MIGRATION_ADVISORY_LOCK_ID, run_with_advisory_lock


class _Connection:
    def __init__(self, events):
        self.events = events

    def execute(self, statement, params):
        self.events.append((str(statement), params))


def test_startup_migration_lock_wraps_migration_and_releases():
    events = []
    connection = _Connection(events)

    def migrate():
        events.append("migration")

    run_with_advisory_lock(connection, migrate, enabled=True)

    assert events[0][0] == "SELECT pg_advisory_lock(:lock_id)"
    assert events[0][1] == {"lock_id": MIGRATION_ADVISORY_LOCK_ID}
    assert events[1] == "migration"
    assert events[2][0] == "SELECT pg_advisory_unlock(:lock_id)"
    assert events[2][1] == {"lock_id": MIGRATION_ADVISORY_LOCK_ID}


def test_migration_lock_is_skipped_by_default():
    events = []
    run_with_advisory_lock(_Connection(events), lambda: events.append("migration"), enabled=False)
    assert events == ["migration"]


def test_migration_lock_releases_if_migration_fails():
    events = []

    def migrate():
        raise RuntimeError("migration failed")

    try:
        run_with_advisory_lock(_Connection(events), migrate, enabled=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("migration failure should propagate")
    assert events[-1][0] == "SELECT pg_advisory_unlock(:lock_id)"
