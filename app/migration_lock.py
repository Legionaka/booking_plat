"""Optional PostgreSQL advisory lock around startup migrations and demo seeding."""

from sqlalchemy import text

MIGRATION_ADVISORY_LOCK_ID = 781245901


def run_with_advisory_lock(connection, migration_callback, enabled: bool) -> None:
    """Run the startup callback under a session lock when enabled."""
    if enabled:
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
        )
    try:
        migration_callback()
    finally:
        if enabled:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
            )
