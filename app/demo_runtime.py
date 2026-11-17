"""Supervise web, RQ worker, and scheduler subprocesses for a small demo deployment."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from time import sleep


def build_demo_commands(port: int, workers: int) -> dict[str, list[str]]:
    python = sys.executable
    return {
        "web": [
            python,
            "-m",
            "gunicorn",
            "--bind",
            f"0.0.0.0:{port}",
            "--workers",
            str(workers),
            "--logger-class",
            "app.gunicorn_logging.JsonGunicornLogger",
            "app:create_app()",
        ],
        "worker": [python, "-m", "flask", "--app", "app:create_app", "worker", "run"],
        "scheduler": [
            python,
            "-m",
            "flask",
            "--app",
            "app:create_app",
            "scheduler",
            "run",
        ],
    }


def supervise_demo_processes(
    commands: Mapping[str, Sequence[str]],
    *,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    sleep_fn: Callable[[float], None] = sleep,
    poll_interval: float = 0.2,
) -> int:
    """Return nonzero when any child exits and stop all remaining children."""
    processes: dict[str, subprocess.Popen] = {}
    try:
        for name, command in commands.items():
            processes[name] = popen_factory(list(command))
        while True:
            for process in processes.values():
                exit_code = process.poll()
                if exit_code is not None:
                    # A child exiting cleanly is still a failed all-in-one deployment.
                    return exit_code or 1
            sleep_fn(poll_interval)
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
