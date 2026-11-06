from __future__ import annotations

import subprocess
import sys

import pytest

from teams_monitor.watchdog import TasklistProbe
from teams_monitor.watchdog.process import TASKLIST_TIMEOUT_SECONDS


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch):
    """Replaces subprocess.run with one that returns the given output or raises the given error."""

    def install(stdout: str = "", returncode: int = 0, raises: Exception | None = None) -> dict:
        seen: dict = {}

        def run(command, **kwargs):
            seen.update(command=command, **kwargs)
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")

        monkeypatch.setattr("teams_monitor.watchdog.process.subprocess.run", run)
        return seen

    return install


def test_found_in_the_output(fake_run) -> None:
    fake_run('"ms-teams.exe","1234","Console","1","200,000 K"\n')
    assert TasklistProbe("ms-teams.exe").is_running() is True


def test_match_ignores_case(fake_run) -> None:
    fake_run('"MS-Teams.EXE"')
    assert TasklistProbe("ms-teams.exe").is_running() is True


def test_not_found(fake_run) -> None:
    fake_run("INFO: No tasks are running which match the specified criteria.\n")
    assert TasklistProbe("ms-teams.exe").is_running() is False


def test_non_zero_exit_is_unknown(fake_run) -> None:
    fake_run("x.exe", returncode=1)
    assert TasklistProbe("x.exe").is_running() is None


@pytest.mark.parametrize(
    "exc",
    [OSError("no tasklist"), subprocess.TimeoutExpired("tasklist", 10)],
)
def test_failed_check_is_unknown(fake_run, exc: Exception) -> None:
    fake_run(raises=exc)
    assert TasklistProbe("x.exe").is_running() is None


def test_undecodable_output_does_not_break_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run
    script = "import sys; sys.stdout.buffer.write(b'\\x81 \"ms-teams.exe\"')"
    monkeypatch.setattr(
        "teams_monitor.watchdog.process.subprocess.run",
        lambda command, **kwargs: real_run([sys.executable, "-c", script], **kwargs),
    )
    assert TasklistProbe("ms-teams.exe").is_running() is True


def test_command_and_options(fake_run) -> None:
    seen = fake_run()
    TasklistProbe("ms-teams.exe").is_running()
    assert seen["command"] == [
        "tasklist",
        "/FI",
        "IMAGENAME eq ms-teams.exe",
        "/FO",
        "CSV",
        "/NH",
    ]
    assert seen["timeout"] == TASKLIST_TIMEOUT_SECONDS
    assert seen["check"] is False
