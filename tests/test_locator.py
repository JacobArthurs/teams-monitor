from __future__ import annotations

import os
from pathlib import Path

from teams_monitor.tailing import LogLocator


def _write(path: Path, mtime: float = 1_000_000.0) -> Path:
    path.write_text("x\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_directory_property(tmp_path: Path) -> None:
    assert LogLocator(tmp_path).directory == tmp_path


def test_existing_only_includes_matching_files(tmp_path: Path) -> None:
    log = _write(tmp_path / "MSTeams_1.log")
    _write(tmp_path / "other.log")
    _write(tmp_path / "MSTeams_1.txt")
    assert LogLocator(tmp_path).existing() == [log]


def test_custom_pattern(tmp_path: Path) -> None:
    log = _write(tmp_path / "custom.txt")
    assert LogLocator(tmp_path, pattern="*.txt").existing() == [log]


def test_newest_uses_the_modified_time_not_the_name(tmp_path: Path) -> None:
    newer = _write(tmp_path / "MSTeams_a.log", mtime=2_000_000.0)
    _write(tmp_path / "MSTeams_z.log", mtime=1_000_000.0)
    assert LogLocator(tmp_path).newest() == newer


def test_newest_breaks_a_tie_by_name(tmp_path: Path) -> None:
    _write(tmp_path / "MSTeams_a.log")
    later_name = _write(tmp_path / "MSTeams_b.log")
    assert LogLocator(tmp_path).newest() == later_name


def test_empty_folder_has_no_newest(tmp_path: Path) -> None:
    assert LogLocator(tmp_path).newest() is None


def test_missing_folder_is_not_an_error(tmp_path: Path) -> None:
    locator = LogLocator(tmp_path / "missing")
    assert locator.existing() == []
    assert locator.newest() is None
