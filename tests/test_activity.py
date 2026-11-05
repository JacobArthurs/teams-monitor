from __future__ import annotations

import logging

import pytest

from teams_monitor.watchdog import ActivityTracker


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_idle_grows_with_time(clock) -> None:
    tracker = ActivityTracker(clock)
    clock.advance(12)
    assert tracker.idle_seconds() == 12


def test_touch_records_activity_and_resets_idle(clock) -> None:
    tracker = ActivityTracker(clock)
    clock.advance(12)
    tracker.touch()
    assert tracker.last_activity == clock.monotonic()
    assert tracker.idle_seconds() == 0


def test_restart_idle_does_not_count_as_activity(clock) -> None:
    tracker = ActivityTracker(clock)
    before = tracker.last_activity
    clock.advance(12)
    tracker.restart_idle()
    assert tracker.idle_seconds() == 0
    assert tracker.last_activity == before


def test_unrecognized_lines_are_not_activity(clock) -> None:
    tracker = ActivityTracker(clock)
    clock.advance(12)
    tracker.note_unrecognized(5)
    assert tracker.idle_seconds() == 12


def test_format_suspect_threshold_is_exactly_100(clock) -> None:
    tracker = ActivityTracker(clock)
    tracker.note_unrecognized(99)
    assert tracker.format_suspect is False
    tracker.note_unrecognized(1)
    assert tracker.format_suspect is True


def test_touch_clears_format_suspect(clock) -> None:
    tracker = ActivityTracker(clock)
    tracker.note_unrecognized(100)
    tracker.touch()
    assert tracker.format_suspect is False


def test_warning_logs_once_per_run_of_bad_lines(clock, caplog) -> None:
    tracker = ActivityTracker(clock)
    with caplog.at_level(logging.WARNING, logger="teams_monitor"):
        tracker.note_unrecognized(99)
        assert _warnings(caplog) == []
        tracker.note_unrecognized(1)
        tracker.note_unrecognized(50)
        assert len(_warnings(caplog)) == 1

        tracker.touch()
        tracker.note_unrecognized(100)
        assert len(_warnings(caplog)) == 2
