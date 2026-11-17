"""Flask CLI commands for the booking domain."""

from datetime import UTC, datetime
from time import sleep

import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from app.services.bookings import expire_holds
from app.services.notification_jobs import run_scheduler_once


@click.group("bookings")
def bookings_cli():
    """Booking maintenance commands."""


@bookings_cli.command("expire-holds")
def expire_holds_command():
    """Cancel pending bookings whose payment holds have expired."""
    count = expire_holds(datetime.now(UTC))
    click.echo(f"Expired {count} booking hold(s).")


def register_cli(app: Flask) -> None:
    app.cli.add_command(bookings_cli)
    app.cli.add_command(worker_cli)
    app.cli.add_command(scheduler_cli)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(demo_cli)


@click.group("worker")
def worker_cli():
    """RQ background worker commands."""


@worker_cli.command("run")
def worker_run():
    """Run an RQ worker for booking notifications."""
    import os

    from rq import SimpleWorker, Worker

    from app.services.notification_jobs import _queue

    queue = _queue()
    click.echo(f"Listening on RQ queue {queue.name}.")
    worker_type = SimpleWorker if os.name == "nt" else Worker
    worker_type([queue], connection=queue.connection).work(with_scheduler=True)


@click.group("scheduler")
def scheduler_cli():
    """Notification and booking maintenance scheduler."""


@scheduler_cli.command("run")
def scheduler_run():
    """Enqueue due notifications and expire holds every minute."""
    interval = current_app.config["SCHEDULER_INTERVAL_SECONDS"]
    click.echo(f"Scheduler running; polling every {interval} seconds.")
    while True:
        enqueued, expired = run_scheduler_once(datetime.now(UTC))
        click.echo(f"Enqueued {enqueued} notification(s); expired {expired} hold(s).")
        sleep(interval)


@click.command("seed-demo")
@click.option("--reset", is_flag=True, help="Delete and recreate only the Fade Lab demo data.")
@with_appcontext
def seed_demo_command(reset: bool):
    """Create deterministic demo data for local environments only."""
    if current_app.config.get("APP_ENV") == "production":
        raise click.ClickException("seed-demo is disabled in production.")
    from app.services.demo_seed import seed_demo

    try:
        counts = seed_demo(reset=reset)
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        raise click.ClickException(f"Demo seed failed: {exc}") from exc
    click.echo("Fade Lab demo data is ready (demo credentials only).")
    click.echo(f"Owner login: {current_app.config['DEMO_OWNER_EMAIL']}")
    click.echo(f"Owner password: {current_app.config['DEMO_OWNER_PASSWORD']}")
    click.echo(", ".join(f"{key}={value}" for key, value in counts.items()))


@click.group("demo")
def demo_cli():
    """Commands for low-cost, single-container demonstrations."""


@demo_cli.command("run-all")
@with_appcontext
def demo_run_all():
    """Run web, RQ worker, and scheduler as supervised children for demos."""
    from app.demo_runtime import build_demo_commands, supervise_demo_processes

    config = current_app.config
    commands = build_demo_commands(config["PORT"], config["WEB_WORKERS"])
    click.echo("Demo mode: supervising web, worker, and scheduler processes.")
    exit_code = supervise_demo_processes(commands)
    raise click.exceptions.Exit(exit_code)
