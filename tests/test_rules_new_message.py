from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from helpers import badge, event, parse, stamp, tray_add

from teams_monitor.models import AlertKind
from teams_monitor.rules.new_message import NewMessageRule


class Rig:
    """A rule plus an adjustable missed call time."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.missed_at: datetime | None = None
        self.rule = NewMessageRule(lambda: self.missed_at, timedelta(seconds=3), clock)

    def feed(self, raw: str) -> list:
        return self.rule.on_event(event(raw))

    def tick_after(self, seconds: float = 2.0) -> list:
        self.clock.advance(seconds)
        return self.rule.on_tick()


@pytest.fixture
def rig(clock) -> Rig:
    return Rig(clock)


def _unread(alerts: list) -> list[int]:
    return [alert.fields["unread"] for alert in alerts]


def test_first_value_only_sets_the_baseline(rig: Rig) -> None:
    assert rig.feed(badge(1)) == []
    assert rig.tick_after() == []


def test_equal_value_is_a_refresh(rig: Rig) -> None:
    rig.feed(badge(1))
    assert rig.feed(badge(1, at=1)) == []
    assert rig.tick_after() == []


def test_rise_is_held_for_exactly_the_hold_period(rig: Rig) -> None:
    rig.feed(badge(1, at=0))
    assert rig.feed(badge(2, at=1)) == []
    assert rig.rule.on_tick() == []
    assert rig.tick_after(1.5) == []
    assert _unread(rig.tick_after(0.5)) == [2]


def test_held_rise_alerts_only_once(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(badge(2))
    assert len(rig.tick_after()) == 1
    assert rig.tick_after() == []


def test_alert_carries_unread_presence_and_time(rig: Rig) -> None:
    raw = badge(2, presence="Busy")
    rig.feed(badge(1))
    rig.feed(raw)
    alert = rig.tick_after()[0]
    assert alert.kind is AlertKind.NEW_MESSAGE
    assert alert.fields == {"unread": 2, "presence": "Busy", "log_ts": parse(raw).log_ts}


@pytest.mark.parametrize("fallen_to", [1, 0])
def test_fall_to_baseline_or_lower_cancels_the_rise(rig: Rig, fallen_to: int) -> None:
    rig.feed(badge(1))
    rig.feed(badge(2))
    assert rig.feed(badge(fallen_to)) == []
    assert rig.tick_after() == []


def test_partial_fall_keeps_the_alert_with_the_lower_count(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(badge(3))
    rig.feed(badge(2))
    assert _unread(rig.tick_after()) == [2]


def test_fall_with_nothing_held_updates_the_baseline(rig: Rig) -> None:
    rig.feed(badge(3))
    assert rig.feed(badge(1)) == []
    assert rig.tick_after() == []
    rig.feed(badge(2))
    assert _unread(rig.tick_after()) == [2]


def test_burst_is_one_alert_with_the_latest_count(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(badge(2))
    rig.feed(badge(3))
    rig.feed(badge(4))
    assert _unread(rig.tick_after()) == [4]


def test_burst_keeps_the_original_deadline(rig: Rig) -> None:
    rig.feed(badge(1, at=0))
    rig.feed(badge(2, at=0))
    rig.clock.advance(1.5)
    rig.feed(badge(3, at=1.5))
    assert _unread(rig.tick_after(0.5)) == [3]


def test_burst_keeps_the_original_baseline(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(badge(2))
    rig.feed(badge(3))
    rig.feed(badge(1))
    assert rig.tick_after() == []


def test_later_log_line_releases_a_settled_rise_so_a_fall_cannot_cancel_it(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert _unread(rig.feed(badge(1, at=3))) == [2]
    assert rig.tick_after() == []


def test_log_time_settles_at_exactly_the_hold(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert _unread(rig.feed(badge(2, at=2))) == [2]


def test_fall_just_inside_the_hold_still_cancels(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert rig.feed(badge(1, at=1.999)) == []
    assert rig.tick_after() == []


def test_rise_after_a_settled_rise_starts_a_new_hold(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert _unread(rig.feed(badge(3, at=2))) == [2]
    assert _unread(rig.tick_after()) == [3]


def test_restart_releases_a_settled_rise(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert _unread(rig.feed(tray_add(at=3))) == [2]


def test_restart_drops_an_unsettled_rise(rig: Rig) -> None:
    rig.feed(badge(1, at=-1))
    rig.feed(badge(2, at=0))
    assert rig.feed(tray_add(at=1)) == []
    assert rig.tick_after() == []


def test_restart_resets_the_baseline(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(tray_add(at=1))
    assert rig.feed(badge(5, at=2)) == []
    assert rig.tick_after() == []


@pytest.mark.parametrize(
    ("after_missed", "alerted"),
    [(0, False), (3, False), (3.001, True), (-0.001, True)],
)
def test_suppression_window_after_a_missed_call(
    rig: Rig, after_missed: float, alerted: bool
) -> None:
    rig.missed_at = parse(badge(0, at=10)).ts
    rig.feed(badge(1, at=0))
    rig.feed(badge(2, at=10 + after_missed))
    assert len(rig.tick_after()) == (1 if alerted else 0)


def test_suppressed_rise_still_moves_the_baseline(rig: Rig) -> None:
    rig.missed_at = parse(badge(0, at=10)).ts
    rig.feed(badge(1, at=0))
    rig.feed(badge(2, at=11))
    assert rig.feed(badge(2, at=30)) == []
    assert rig.tick_after() == []
    rig.feed(badge(3, at=31))
    assert _unread(rig.tick_after()) == [3]


def test_no_missed_call_means_no_suppression(rig: Rig) -> None:
    rig.feed(badge(1))
    rig.feed(badge(2))
    assert len(rig.tick_after()) == 1


def test_line_with_an_invalid_time_is_held_and_released_by_tick(rig: Rig) -> None:
    rig.missed_at = parse(badge(0, at=0)).ts
    rig.feed(badge(1, at=0))
    rig.feed(badge(2, at=0).replace(stamp(0), "2026-13-45T00:00:00.000000-05:00"))
    assert _unread(rig.tick_after()) == [2]


def test_custom_hold_is_honored(clock) -> None:
    rule = NewMessageRule(lambda: None, timedelta(0), clock, hold=timedelta(seconds=10))
    rule.on_event(event(badge(1)))
    rule.on_event(event(badge(2)))
    clock.advance(9)
    assert rule.on_tick() == []
    clock.advance(1)
    assert len(rule.on_tick()) == 1
