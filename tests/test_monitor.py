from __future__ import annotations

import threading
from collections import deque

import pytest
from helpers import CALL_A, CALL_B, RecordingNotifier, ended, incoming, unrelated

from teams_monitor import alerts
from teams_monitor.engine import Engine
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.monitor import Monitor
from teams_monitor.parsing import LineParser
from teams_monitor.rules.base import Rule
from teams_monitor.rules.incoming_call import IncomingCallRule
from teams_monitor.signals import SignalMatcher
from teams_monitor.watchdog import ActivityTracker


class FakeTailer:
    def __init__(self) -> None:
        self.batches: deque[list[str]] = deque()

    def poll(self) -> list[str]:
        return self.batches.popleft() if self.batches else []


class SpyWatchdog:
    def __init__(self) -> None:
        self.checks = 0
        self.tray_checks = 0
        self.result: list[Alert] = []
        self.tray_result: list[Alert] = []

    def check(self) -> list[Alert]:
        self.checks += 1
        return self.result

    def check_tray(self) -> list[Alert]:
        self.tray_checks += 1
        return self.tray_result


class Rig:
    def __init__(self, clock, engine=None, notifier=None, poll_interval=0.5, check_interval=30.0):
        self.clock = clock
        self.tailer = FakeTailer()
        self.watchdog = SpyWatchdog()
        self.activity = ActivityTracker(clock)
        self.notifier = notifier or RecordingNotifier()
        self.engine = engine or Engine(LineParser(), SignalMatcher(), [IncomingCallRule()])
        self.monitor = Monitor(
            self.tailer,
            self.engine,
            self.notifier,
            self.watchdog,
            self.activity,
            clock,
            poll_interval,
            check_interval,
        )

    def feed(self, *lines: str) -> None:
        self.tailer.batches.append(list(lines))
        self.monitor.run_once()


@pytest.fixture
def rig(clock) -> Rig:
    return Rig(clock)


def test_lines_become_alerts(rig: Rig) -> None:
    rig.feed(incoming(CALL_A), unrelated(), incoming(CALL_B))
    assert [a.fields["call_id"] for a in rig.notifier.alerts] == [CALL_A, CALL_B]


def test_tick_alerts_are_dispatched(clock) -> None:
    class TickRule(Rule):
        handles = frozenset({SignalName.CALL_INCOMING})

        def on_event(self, event: Event) -> list[Alert]:
            return []

        def on_tick(self) -> list[Alert]:
            return [alerts.teams_down("tick")]

    rig = Rig(clock, engine=Engine(LineParser(), SignalMatcher(), [TickRule()]))
    rig.monitor.run_once()
    assert rig.notifier.kinds == ["teams_down"]


def test_watchdog_runs_only_when_due(rig: Rig) -> None:
    rig.clock.advance(29)
    rig.monitor.run_once()
    assert rig.watchdog.checks == 0
    rig.clock.advance(1)
    rig.monitor.run_once()
    assert rig.watchdog.checks == 1
    rig.monitor.run_once()
    assert rig.watchdog.checks == 1


def test_tray_check_runs_on_every_iteration(rig: Rig) -> None:
    rig.monitor.run_once()
    rig.monitor.run_once()
    assert rig.watchdog.tray_checks == 2
    assert rig.watchdog.checks == 0


def test_tray_alerts_are_dispatched(rig: Rig) -> None:
    rig.watchdog.tray_result = [alerts.teams_down("x")]
    rig.monitor.run_once()
    assert rig.notifier.kinds == ["teams_down"]


def test_watchdog_alerts_are_dispatched(rig: Rig) -> None:
    rig.watchdog.result = [alerts.teams_down("x")]
    rig.clock.advance(30)
    rig.monitor.run_once()
    assert rig.notifier.kinds == ["teams_down"]


def test_long_gap_restarts_the_stale_timer_and_skips_the_check(rig: Rig) -> None:
    before = rig.activity.last_activity
    rig.clock.advance(61)
    rig.monitor.run_once()
    assert rig.activity.idle_seconds() == 0
    assert rig.activity.last_activity == before  # sleeping is not log activity
    assert rig.watchdog.checks == 0
    rig.clock.advance(30)
    rig.monitor.run_once()
    assert rig.watchdog.checks == 1


def test_gap_at_the_limit_is_not_a_suspend(rig: Rig) -> None:
    rig.clock.advance(60)
    rig.monitor.run_once()
    assert rig.activity.idle_seconds() == 60
    assert rig.watchdog.checks == 1


def test_suspend_gap_scales_with_a_long_poll_interval(clock) -> None:
    rig = Rig(clock, poll_interval=20.0)
    clock.advance(70)
    rig.monitor.run_once()
    assert rig.activity.idle_seconds() == 70
    clock.advance(81)
    rig.monitor.run_once()
    assert rig.activity.idle_seconds() == 0


def test_recognized_line_counts_as_activity(rig: Rig) -> None:
    rig.clock.advance(10)
    rig.feed(unrelated())
    assert rig.activity.last_activity == rig.clock.monotonic()


def test_unrecognized_lines_are_not_activity(rig: Rig) -> None:
    before = rig.activity.last_activity
    rig.clock.advance(10)
    rig.feed("garbage")
    assert rig.activity.last_activity == before


def test_batch_of_only_unrecognized_lines_builds_format_suspicion(rig: Rig) -> None:
    rig.feed(*["garbage"] * 100)
    assert rig.activity.format_suspect is True


def test_one_recognized_line_clears_format_suspicion(rig: Rig) -> None:
    rig.feed(*["garbage"] * 100)
    rig.feed("garbage", unrelated())
    assert rig.activity.format_suspect is False


def test_blank_lines_are_ignored(rig: Rig) -> None:
    rig.feed(*["", "   "] * 100)
    assert rig.activity.format_suspect is False


def test_parse_failure_does_not_stop_the_batch(clock, caplog) -> None:
    class FlakyParser(LineParser):
        def parse(self, raw: str):
            if "boom" in raw:
                raise OSError("bad timestamp")
            return super().parse(raw)

    rig = Rig(clock, engine=Engine(FlakyParser(), SignalMatcher(), [IncomingCallRule()]))
    rig.feed("boom", incoming(CALL_A))
    assert rig.notifier.kinds == ["incoming_call"]
    assert "failed to parse a log line" in caplog.text


def test_rule_failure_does_not_stop_the_batch(clock, caplog) -> None:
    class FlakyRule(IncomingCallRule):
        def on_event(self, event: Event) -> list[Alert]:
            if event.groups["call_id"] == CALL_A:
                raise RuntimeError("bug")
            return super().on_event(event)

    rig = Rig(clock, engine=Engine(LineParser(), SignalMatcher(), [FlakyRule()]))
    rig.feed(incoming(CALL_A), incoming(CALL_B))
    assert [a.fields["call_id"] for a in rig.notifier.alerts] == [CALL_B]
    assert "failed to process a log line" in caplog.text


def test_notifier_failure_does_not_stop_the_batch(clock, caplog) -> None:
    class FlakyNotifier(RecordingNotifier):
        def notify(self, alert: Alert) -> None:
            if alert.fields["call_id"] == CALL_A:
                raise RuntimeError("bug")
            super().notify(alert)

    rig = Rig(clock, notifier=FlakyNotifier())
    rig.feed(incoming(CALL_A), incoming(CALL_B))
    assert [a.fields["call_id"] for a in rig.notifier.alerts] == [CALL_B]


def test_run_forever_survives_a_failed_iteration_and_stops(clock, caplog) -> None:
    rig = Rig(clock, poll_interval=0.001)
    stop = threading.Event()
    calls = []

    def poll() -> list[str]:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("bug")
        stop.set()
        return []

    rig.tailer.poll = poll
    rig.monitor.run_forever(stop)
    assert len(calls) == 2
    assert "monitor iteration failed" in caplog.text


def test_run_forever_does_nothing_when_already_stopped(rig: Rig) -> None:
    stop = threading.Event()
    stop.set()
    rig.tailer.batches.append([incoming(CALL_A)])
    rig.monitor.run_forever(stop)
    assert rig.notifier.alerts == []


def test_close_closes_the_notifier(rig: Rig) -> None:
    rig.monitor.close()
    assert rig.notifier.closed == 1


def test_call_end_with_no_ring_rule_sends_nothing(rig: Rig) -> None:
    rig.feed(ended(CALL_A))
    assert rig.notifier.alerts == []
