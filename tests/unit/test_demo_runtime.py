import pytest
from app.demo_runtime import build_demo_commands, supervise_demo_processes


class _Process:
    def __init__(self, exit_code):
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = -15

    def wait(self, timeout=None):
        return self.exit_code

    def kill(self):
        self.killed = True
        self.exit_code = -9


@pytest.mark.parametrize("failed_role", ["web", "worker", "scheduler"])
def test_demo_supervisor_exits_nonzero_and_stops_siblings(failed_role):
    roles = ["web", "worker", "scheduler"]
    processes = {}

    def spawn(command):
        role = roles[len(processes)]
        process = _Process(7 if role == failed_role else None)
        processes[role] = process
        return process

    result = supervise_demo_processes(
        {role: [role] for role in roles},
        popen_factory=spawn,
        sleep_fn=lambda _delay: None,
    )

    assert result == 7
    assert all(processes[role].terminated for role in roles if role != failed_role)


def test_supervisor_commands_use_gunicorn_and_main_thread_worker_processes():
    commands = build_demo_commands(port=5010, workers=2)
    assert commands["web"][2] == "gunicorn"
    assert commands["worker"][-2:] == ["worker", "run"]
    assert commands["scheduler"][-2:] == ["scheduler", "run"]
