from __future__ import annotations

from datetime import time

import pytest
from helpers import FakeProbe

from teams_monitor.health import HealthState
from teams_monitor.models import AlertKind
from teams_monitor.watchdog import ActivityTracker, Watchdog
from teams_monitor.window import ActiveWindow

STALE_AFTER = 600.0


class Rig:
    def __init__(self, clock, running: bool | None = True, window: ActiveWindow | None = None):
        self.clock = clock
        self.health = HealthState(clock)
        self.activity = ActivityTracker(clock)
        self.probe = FakeProbe(running)
        self.watchdog = Watchdog(self.health, self.activity, clock, STALE_AFTER, self.probe, window)

    def reasons(self) -> list[str]:
        return [alert.fields["reason"] for alert in self.watchdog.check()]


@pytest.fixture
def rig(clock) -> Rig:
    return Rig(clock)


def test_healthy_teams_is_quiet(rig: Rig) -> None:
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False


def test_process_not_running_alerts(rig: Rig) -> None:
    rig.probe.running = False
    result = rig.watchdog.check()
    assert [alert.kind for alert in result] == [AlertKind.TEAMS_DOWN]
    assert result[0].fields["reason"] == "Teams process is not running"
    assert rig.health.is_down is True


def test_long_outage_alerts_once(rig: Rig) -> None:
    rig.probe.running = False
    assert len(rig.watchdog.check()) == 1
    for _ in range(5):
        rig.clock.advance(30)
        assert rig.watchdog.check() == []


def test_failed_probe_is_not_treated_as_down(rig: Rig) -> None:
    rig.probe.running = None
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False


def test_no_probe_is_allowed(clock) -> None:
    health = HealthState(clock)
    watchdog = Watchdog(health, ActivityTracker(clock), clock, STALE_AFTER)
    assert watchdog.check() == []


def test_tray_removal_alerts_after_the_grace(rig: Rig) -> None:
    rig.health.note_tray_removed()
    rig.clock.advance(4)
    assert rig.watchdog.check_tray() == []
    rig.clock.advance(1)
    result = rig.watchdog.check_tray()
    assert [alert.fields["reason"] for alert in result] == ["tray icon removed"]
    assert rig.health.is_down is True


def test_tray_alert_is_skipped_during_an_outage_already_alerted(rig: Rig) -> None:
    rig.probe.running = False
    rig.watchdog.check()
    rig.health.note_tray_removed()
    rig.clock.advance(5)
    assert rig.watchdog.check_tray() == []


def test_tray_check_does_not_run_the_process_probe(rig: Rig) -> None:
    rig.probe.running = False
    assert rig.watchdog.check_tray() == []
    assert rig.health.is_down is False


def test_full_check_leaves_a_tray_removal_to_the_tray_check(rig: Rig) -> None:
    rig.health.note_tray_removed()
    rig.clock.advance(5)
    assert rig.watchdog.check() == []
    assert len(rig.watchdog.check_tray()) == 1


def test_stale_log_alerts_only_past_the_limit(rig: Rig) -> None:
    rig.clock.advance(STALE_AFTER)
    assert rig.reasons() == []
    rig.clock.advance(1)
    assert rig.reasons() == ["no log activity for 10 min"]


def test_stale_log_with_unrecognized_lines_blames_the_format(rig: Rig) -> None:
    rig.activity.note_unrecognized(100)
    rig.clock.advance(STALE_AFTER + 1)
    assert rig.reasons() == [
        "log lines not recognized for 10 min (the log format may have changed)"
    ]


def test_process_reason_wins_over_stale(rig: Rig) -> None:
    rig.probe.running = False
    rig.clock.advance(STALE_AFTER + 1)
    assert rig.reasons() == ["Teams process is not running"]


def test_recovery_needs_activity_after_the_grace_then_allows_a_new_alert(rig: Rig) -> None:
    rig.probe.running = False
    rig.watchdog.check()

    rig.probe.running = True
    rig.clock.advance(30)
    rig.activity.touch()
    assert rig.watchdog.check() == []
    assert rig.health.is_down is True  # lines this soon may be Teams shutting down

    rig.clock.advance(31)
    rig.activity.touch()
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False

    rig.probe.running = False
    assert len(rig.watchdog.check()) == 1


def test_outside_the_window_nothing_is_checked(clock) -> None:
    rig = Rig(clock, running=False, window=ActiveWindow(time(8), time(18)))
    clock.set_time_of_day(time(7, 59))
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False


def test_ongoing_outage_alerts_when_the_window_opens(clock) -> None:
    rig = Rig(clock, running=False, window=ActiveWindow(time(8), time(18)))
    clock.set_time_of_day(time(7, 59))
    assert rig.watchdog.check() == []
    clock.set_time_of_day(time(8, 0))
    assert len(rig.watchdog.check()) == 1


def test_recovery_outside_the_window_lets_the_next_outage_alert(clock) -> None:
    rig = Rig(clock, window=ActiveWindow(time(8), time(18)))
    clock.set_time_of_day(time(17, 0))
    clock.advance(STALE_AFTER + 1)
    assert rig.reasons() == ["no log activity for 10 min"]

    clock.set_time_of_day(time(19, 0))
    clock.advance(61)
    rig.activity.touch()
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False

    rig.probe.running = False
    clock.set_time_of_day(time(23, 0))
    assert rig.watchdog.check() == []
    assert rig.health.is_down is False

    clock.set_time_of_day(time(8, 0))
    assert rig.reasons() == ["Teams process is not running"]


def test_outage_continuing_outside_the_window_alerts_only_once(clock) -> None:
    rig = Rig(clock, running=False, window=ActiveWindow(time(8), time(18)))
    clock.set_time_of_day(time(17, 0))
    assert len(rig.watchdog.check()) == 1

    clock.set_time_of_day(time(19, 0))
    clock.advance(61)
    rig.activity.touch()
    assert rig.watchdog.check() == []
    assert rig.health.is_down is True

    clock.set_time_of_day(time(8, 0))
    assert rig.watchdog.check() == []


def test_tray_removal_outside_the_window_alerts_when_it_opens(clock) -> None:
    rig = Rig(clock, window=ActiveWindow(time(8), time(18)))
    clock.set_time_of_day(time(7, 0))
    rig.health.note_tray_removed()
    clock.advance(10)
    assert rig.watchdog.check_tray() == []
    clock.set_time_of_day(time(8, 0))
    assert len(rig.watchdog.check_tray()) == 1
