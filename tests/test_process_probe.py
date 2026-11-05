from __future__ import annotations

import subprocess

import pytest

from teams_monitor.watchdog import TasklistProbe


def _runner(stdout: str = "", returncode: int = 0):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")

    return run


def _raises(exc: Exception):
    def run(command, **kwargs):
        raise exc

    return run


def test_found_in_the_output() -> None:
    stdout = '"ms-teams.exe","1234","Console","1","200,000 K"\n'
    assert TasklistProbe("ms-teams.exe", runner=_runner(stdout)).is_running() is True


def test_match_ignores_case() -> None:
    assert TasklistProbe("ms-teams.exe", runner=_runner('"MS-Teams.EXE"')).is_running() is True


def test_not_found() -> None:
    stdout = "INFO: No tasks are running which match the specified criteria.\n"
    assert TasklistProbe("ms-teams.exe", runner=_runner(stdout)).is_running() is False


def test_non_zero_exit_is_unknown() -> None:
    assert TasklistProbe("x.exe", runner=_runner("x.exe", returncode=1)).is_running() is None


@pytest.mark.parametrize(
    "exc",
    [OSError("no tasklist"), subprocess.TimeoutExpired("tasklist", 10)],
)
def test_failed_check_is_unknown(exc: Exception) -> None:
    assert TasklistProbe("x.exe", runner=_raises(exc)).is_running() is None


def test_command_and_options() -> None:
    seen = {}

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    TasklistProbe("ms-teams.exe", runner=run, timeout=3.0).is_running()
    assert seen["command"] == [
        "tasklist",
        "/FI",
        "IMAGENAME eq ms-teams.exe",
        "/FO",
        "CSV",
        "/NH",
    ]
    assert seen["timeout"] == 3.0
    assert seen["check"] is False
