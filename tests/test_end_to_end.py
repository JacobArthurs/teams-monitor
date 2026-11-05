"""Runs the fully wired monitor against a real log file, with only time and the probe faked."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import (
    CALL_A,
    FakeProbe,
    answered,
    badge,
    ended,
    incoming,
    load_samples,
    tray_add,
    tray_remove,
    unread_count,
    unrelated,
)

from teams_monitor.bootstrap import build_monitor
from teams_monitor.config import Settings


class Rig:
    def __init__(self, tmp_path: Path, clock, recorder, existing=(), **settings) -> None:
        self.clock = clock
        self.recorder = recorder
        self.probe = FakeProbe(True)
        self.log = tmp_path / "MSTeams_1.log"
        self.log.write_text("".join(f"{line}\n" for line in existing), encoding="utf-8")
        self.monitor = build_monitor(
            Settings(log_dir=tmp_path, **settings), notifier=recorder, clock=clock, probe=self.probe
        )
        self.monitor.run_once()  # the first poll treats what already exists as read

    def write(self, *lines: str) -> None:
        with self.log.open("a", encoding="utf-8", newline="") as handle:
            handle.writelines(line + "\r\n" for line in lines)
        self.monitor.run_once()

    def wait(self, seconds: float) -> None:
        self.clock.advance(seconds)
        self.monitor.run_once()


@pytest.fixture
def rig(tmp_path: Path, clock, recorder) -> Rig:
    return Rig(tmp_path, clock, recorder)


def _reasons(rig: Rig) -> list[str]:
    return [alert.fields["reason"] for alert in rig.recorder.alerts]


def test_missed_call(rig: Rig) -> None:
    rig.write(incoming(CALL_A))
    assert rig.recorder.kinds == ["incoming_call"]
    rig.write(ended(CALL_A, at=20))
    assert rig.recorder.kinds == ["incoming_call", "missed_call"]


def test_answered_call(rig: Rig) -> None:
    rig.write(incoming(CALL_A), answered(CALL_A, at=2), ended(CALL_A, at=60))
    assert rig.recorder.kinds == ["incoming_call"]


def test_unread_rise_alerts_after_the_hold(rig: Rig) -> None:
    rig.write(badge(1, at=0), badge(2, at=5))
    assert rig.recorder.kinds == []
    rig.wait(2)
    assert rig.recorder.kinds == ["new_message"]
    assert rig.recorder.alerts[0].fields["unread"] == 2


def test_unread_rise_that_falls_right_back_does_not_alert(rig: Rig) -> None:
    rig.write(badge(1, at=0), badge(2, at=5), badge(1, at=5.1))
    rig.wait(2)
    assert rig.recorder.kinds == []


def test_unread_rise_right_after_a_missed_call_is_suppressed(rig: Rig) -> None:
    rig.write(badge(1, at=0), incoming(CALL_A, at=1), ended(CALL_A, at=10), badge(2, at=11))
    rig.wait(2)
    assert rig.recorder.kinds == ["incoming_call", "missed_call"]


def test_first_badge_alerts_when_the_count_was_logged_before_the_monitor_started(
    tmp_path: Path, clock, recorder
) -> None:
    # The 2026-11-05 miss: started with no badge line in the log, then a message arrived.
    rig = Rig(tmp_path, clock, recorder, existing=[unrelated(at=0), unread_count(0, at=60)])
    rig.write(badge(1, at=330))
    rig.wait(2)
    assert rig.recorder.kinds == ["new_message"]
    assert rig.recorder.alerts[0].fields["unread"] == 1


def test_first_badge_alerts_when_the_count_is_logged_after_the_monitor_started(
    rig: Rig,
) -> None:
    rig.write(unread_count(0, at=118))
    rig.write(badge(1, at=330))
    rig.wait(2)
    assert rig.recorder.kinds == ["new_message"]


def test_sent_message_after_reading_does_not_alert(tmp_path: Path, clock, recorder) -> None:
    rig = Rig(tmp_path, clock, recorder, existing=[unread_count(0, at=0)])
    rig.write(badge(1, at=330))
    rig.wait(2)
    rig.write(badge(0, at=1400), badge(1, at=1435), badge(0, at=1435.009))
    rig.wait(2)
    assert len(rig.recorder.alerts) == 1


def test_unread_messages_from_before_the_monitor_started_do_not_alert(
    tmp_path: Path, clock, recorder
) -> None:
    rig = Rig(tmp_path, clock, recorder, existing=[badge(3, at=0)])
    rig.write(badge(3, at=10))
    rig.wait(2)
    assert rig.recorder.kinds == []


def test_alerts_already_in_the_log_are_not_sent_at_startup(tmp_path: Path, clock, recorder) -> None:
    existing = [incoming(CALL_A, at=0), badge(0, at=1), badge(1, at=2)]
    rig = Rig(tmp_path, clock, recorder, existing=existing)
    rig.wait(2)
    assert rig.recorder.kinds == []


def test_tray_removal_without_a_restart_alerts_once(rig: Rig) -> None:
    rig.write(tray_remove())
    assert rig.recorder.kinds == []
    rig.wait(30)
    assert _reasons(rig) == ["tray icon removed"]
    rig.wait(30)
    assert len(rig.recorder.alerts) == 1


def test_tray_removal_alerts_as_soon_as_the_grace_ends(rig: Rig) -> None:
    rig.write(tray_remove())
    rig.wait(4)
    assert rig.recorder.kinds == []
    rig.wait(1)
    assert _reasons(rig) == ["tray icon removed"]


def test_tray_icon_back_after_the_grace_still_alerts_then_ends_the_outage(rig: Rig) -> None:
    rig.write(tray_remove(at=0))
    rig.wait(20)
    rig.write(tray_add(at=20))
    assert _reasons(rig) == ["tray icon removed"]
    rig.write(tray_remove(at=21))
    rig.wait(5)
    assert len(rig.recorder.alerts) == 2


def test_tray_remove_and_add_is_a_restart_not_an_outage(rig: Rig) -> None:
    rig.write(tray_remove(at=0), tray_add(at=0.49))
    rig.wait(30)
    assert rig.recorder.kinds == []


def test_process_exit_alerts_once(rig: Rig) -> None:
    rig.probe.running = False
    rig.wait(30)
    rig.wait(30)
    assert _reasons(rig) == ["Teams process is not running"]


def test_restart_ends_the_outage_so_the_next_one_alerts(rig: Rig) -> None:
    rig.probe.running = False
    rig.wait(30)
    rig.probe.running = True
    rig.write(tray_add())
    rig.probe.running = False
    rig.wait(30)
    assert len(rig.recorder.alerts) == 2


def test_silent_log_alerts_once(rig: Rig) -> None:
    for _ in range(25):
        rig.wait(30)
    assert len(rig.recorder.alerts) == 1
    assert _reasons(rig)[0].startswith("no log activity")


def test_activity_keeps_the_stale_alert_away(rig: Rig) -> None:
    for step in range(25):
        rig.clock.advance(30)
        rig.write(unrelated(at=step))
    assert rig.recorder.kinds == []


def test_changed_log_format_blames_the_format(rig: Rig) -> None:
    rig.write(*["a line in some new format"] * 100)
    for _ in range(25):
        rig.wait(30)
    assert "log format may have changed" in _reasons(rig)[0]


def test_sleep_does_not_cause_a_stale_alert(rig: Rig) -> None:
    rig.wait(3600)
    rig.wait(30)
    assert rig.recorder.kinds == []


def test_from_start_replays_the_real_samples(tmp_path: Path, clock, recorder) -> None:
    (tmp_path / "MSTeams_1.log").write_text(
        "\n".join(load_samples().values()) + "\n", encoding="utf-8"
    )
    monitor = build_monitor(
        Settings(log_dir=tmp_path, from_start=True),
        notifier=recorder,
        clock=clock,
        probe=FakeProbe(True),
    )
    monitor.run_once()
    assert recorder.kinds == ["incoming_call", "missed_call"]
