import os
from logging.config import fileConfig

from alembic import context
from app import (
    models,  # noqa: F401
)
from app.extensions import db
from app.migration_lock import run_with_advisory_lock
from flask import current_app, has_app_context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if has_app_context():
        url = current_app.config["SQLALCHEMY_DATABASE_URI"]
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        startup_lock_enabled = os.getenv("MIGRATE_ON_STARTUP", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        seed_demo_on_startup = os.getenv("SEED_DEMO_ON_STARTUP", "false").lower() in {
            "1",
            "true",
            "yes",
        }

        def migrate():
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()

            if seed_demo_on_startup and has_app_context():
                if not current_app.config.get("SEED_DEMO_ON_STARTUP"):
                    raise RuntimeError("SEED_DEMO_ON_STARTUP configuration is inconsistent.")
                from app.services.demo_seed import seed_demo

                seed_demo()

        run_with_advisory_lock(
            connection,
            migrate,
            startup_lock_enabled or seed_demo_on_startup,
        )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
