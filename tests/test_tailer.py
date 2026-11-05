from __future__ import annotations

import os
from pathlib import Path

import pytest

from teams_monitor.tailing import LineReader, LogLocator, LogTailer


class Logs:
    """Writes log files with explicit modified times, because Windows times are too coarse."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._mtime = 1_000_000.0

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_bytes(text.encode())
        return self.touch(name)

    def append(self, name: str, text: str) -> Path:
        path = self.directory / name
        with path.open("ab") as handle:
            handle.write(text.encode())
        return self.touch(name)

    def touch(self, name: str) -> Path:
        path = self.directory / name
        self._mtime += 10
        os.utime(path, (self._mtime, self._mtime))
        return path


@pytest.fixture
def logs(tmp_path: Path) -> Logs:
    return Logs(tmp_path)


def _tailer(logs: Logs, from_start: bool = False) -> LogTailer:
    return LogTailer(LogLocator(logs.directory), LineReader(), from_start)


def test_files_present_at_startup_count_as_read(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "old\n")
    tailer = _tailer(logs)
    assert tailer.poll() == []
    logs.append("MSTeams_a.log", "new\n")
    assert tailer.poll() == ["new"]


def test_from_start_reads_only_the_newest_file(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "older file\n")
    logs.write("MSTeams_b.log", "newest file\n")
    assert _tailer(logs, from_start=True).poll() == ["newest file"]


def test_lines_are_not_returned_twice(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "")
    tailer = _tailer(logs)
    tailer.poll()
    logs.append("MSTeams_a.log", "one\n")
    assert tailer.poll() == ["one"]
    assert tailer.poll() == []


def test_empty_folder_then_a_file_appears(logs: Logs) -> None:
    tailer = _tailer(logs)
    assert tailer.poll() == []
    logs.write("MSTeams_a.log", "first\n")
    assert tailer.poll() == ["first"]


def test_new_file_is_read_from_its_beginning(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "old\n")
    tailer = _tailer(logs)
    tailer.poll()
    logs.write("MSTeams_b.log", "first\nsecond\n")
    assert tailer.poll() == ["first", "second"]


def test_rotation_finishes_the_old_file_first(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "old\n")
    tailer = _tailer(logs)
    tailer.poll()
    logs.append("MSTeams_a.log", "last of a\n")
    logs.write("MSTeams_b.log", "first of b\n")
    assert tailer.poll() == ["last of a", "first of b"]


def test_rotation_returns_the_old_files_unterminated_last_line(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "old\n")
    tailer = _tailer(logs)
    tailer.poll()
    logs.append("MSTeams_a.log", "partial")
    logs.write("MSTeams_b.log", "first of b\n")
    assert tailer.poll() == ["partial", "first of b"]


def test_returning_to_a_file_does_not_replay_it(logs: Logs) -> None:
    logs.write("MSTeams_a.log", "a1\n")
    tailer = _tailer(logs)
    tailer.poll()
    logs.write("MSTeams_b.log", "b1\n")
    assert tailer.poll() == ["b1"]
    logs.append("MSTeams_a.log", "a2\n")
    assert tailer.poll() == ["a2"]


def test_deleted_file_is_forgotten_so_a_new_one_with_its_name_reads_from_zero(logs: Logs) -> None:
    path = logs.write("MSTeams_a.log", "old\n")
    tailer = _tailer(logs)
    tailer.poll()
    logs.write("MSTeams_b.log", "b\n")
    tailer.poll()
    path.unlink()
    logs.write("MSTeams_c.log", "c\n")  # switching files is what clears the old offsets
    tailer.poll()
    logs.write("MSTeams_a.log", "fresh\n")
    assert tailer.poll() == ["fresh"]
