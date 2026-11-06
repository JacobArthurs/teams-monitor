from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

from teams_monitor import fatal


@pytest.fixture
def boxes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    shown: list[str] = []
    monkeypatch.setattr(fatal, "_show_message_box", shown.append)
    return shown


def test_does_nothing_with_a_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boxes: list[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fatal.report_without_console("oops")
    assert boxes == []
    assert list(tmp_path.iterdir()) == []


def test_without_a_console_saves_the_error_and_shows_a_dialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boxes: list[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    fatal.report_without_console("oops")
    path = tmp_path / "teams-monitor" / "error.log"
    assert path.read_text(encoding="utf-8").endswith(" oops\n")
    assert boxes == [f"oops\n\nSaved to {path}"]


def test_each_error_is_added_to_the_file_with_its_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boxes: list[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    fatal.report_without_console("first")
    fatal.report_without_console("second")
    text = (tmp_path / "teams-monitor" / "error.log").read_text(encoding="utf-8")
    stamps, messages = zip(*(line.split(" ", 1) for line in text.splitlines()), strict=True)
    assert messages == ("first", "second")
    assert all(datetime.fromisoformat(stamp).tzinfo is not None for stamp in stamps)


def test_falls_back_to_the_temp_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boxes: list[str]
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(fatal.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    fatal.report_without_console("oops")
    assert (tmp_path / "teams-monitor" / "error.log").exists()


def test_dialog_is_still_shown_when_the_file_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boxes: list[str]
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))
    monkeypatch.setattr(sys, "stderr", None)
    fatal.report_without_console("oops")
    assert boxes == ["oops"]
