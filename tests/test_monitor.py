from __future__ import annotations

import logging
import threading
from collections import deque

import pytest
from helpers import CALL_A, CALL_B, RecordingNotifier, ended, incoming, unrelated

from teams_monitor import alerts
from teams_monitor.engine import Engine
from teams_monitor.models import Alert, AlertKind, Event, SignalName
from teams_monitor.monitor import Monitor
from teams_monitor.rules.base import Rule
from teams_monitor.rules.incoming_call import IncomingCallRule


class FakeTailer:
    def __init__(self) -> None:
        self.batches: deque[list[str]] = deque()
        self.history_lines: list[str] = []
        self.history_calls = 0

    def poll(self) -> list[str]:
        return self.batches.popleft() if self.batches else []

    def history(self) -> list[str]:
        self.history_calls += 1
        return self.history_lines


class SpyWatchdog:
    def __init__(self) -> None:
        self.checks = 0
        self.tray_checks = 0
        self.result: list[Alert] = []
        self.tray_result: list[Alert] = []
        self.lines: list[tuple[int, int]] = []
        self.resumes = 0

    def note_lines(self, recognized: int, unrecognized: int) -> None:
        self.lines.append((recognized, unrecognized))

    def note_resume(self) -> None:
        self.resumes += 1

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
        self.notifier = notifier or RecordingNotifier()
        self.engine = engine or Engine([IncomingCallRule()])
        self.monitor = Monitor(
            self.tailer,
            self.engine,
            self.notifier,
            self.watchdog,
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


def test_every_dispatched_alert_is_logged(rig: Rig, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_monitor"):
        rig.feed(incoming(CALL_A))
    assert "ALERT incoming_call p1: Incoming call" in caplog.text


def test_history_is_read_once_and_never_alerts(rig: Rig) -> None:
    rig.tailer.history_lines = [incoming(CALL_A)]
    rig.monitor.run_once()
    rig.monitor.run_once()
    assert rig.tailer.history_calls == 1
    assert rig.notifier.alerts == []


def test_history_does_not_count_as_activity(rig: Rig) -> None:
    rig.tailer.history_lines = [unrelated()]
    rig.monitor.run_once()
    assert rig.watchdog.lines == []


def test_history_failure_does_not_stop_monitoring(rig: Rig, caplog) -> None:
    def history() -> list[str]:
        raise OSError("disk")

    rig.tailer.history = history
    rig.feed(incoming(CALL_A))
    assert rig.notifier.kinds == ["incoming_call"]
    assert "failed to read the existing log" in caplog.text


def test_tick_alerts_are_dispatched(clock) -> None:
    class TickRule(Rule):
        handles = frozenset({SignalName.CALL_INCOMING})

        def on_event(self, event: Event) -> list[Alert]:
            return []

        def on_tick(self) -> list[Alert]:
            return [alerts.teams_down("tick")]

    rig = Rig(clock, engine=Engine([TickRule()]))
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
    rig.clock.advance(61)
    rig.monitor.run_once()
    assert rig.watchdog.resumes == 1
    assert rig.watchdog.lines == []  # sleeping is not log activity
    assert rig.watchdog.checks == 0
    rig.clock.advance(30)
    rig.monitor.run_once()
    assert rig.watchdog.checks == 1


def test_gap_at_the_limit_is_not_a_suspend(rig: Rig) -> None:
    rig.clock.advance(60)
    rig.monitor.run_once()
    assert rig.watchdog.resumes == 0
    assert rig.watchdog.checks == 1


def test_suspend_gap_scales_with_a_long_poll_interval(clock) -> None:
    rig = Rig(clock, poll_interval=20.0)
    clock.advance(70)
    rig.monitor.run_once()
    assert rig.watchdog.resumes == 0
    clock.advance(81)
    rig.monitor.run_once()
    assert rig.watchdog.resumes == 1


def test_line_counts_reach_the_watchdog(rig: Rig) -> None:
    rig.feed("garbage", unrelated(), "", "garbage")
    assert rig.watchdog.lines == [(1, 2)]


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


class ScriptedStop:
    """Stops after a set number of waits and records how long each one was."""

    def __init__(self, iterations: int) -> None:
        self.iterations = iterations
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return len(self.waits) >= self.iterations

    def wait(self, timeout: float) -> None:
        self.waits.append(timeout)


def _always_fail() -> list[str]:
    raise RuntimeError("bug")


def test_repeated_failures_back_off_up_to_the_limit(rig: Rig, caplog) -> None:
    rig.tailer.poll = _always_fail
    stop = ScriptedStop(8)
    rig.monitor.run_forever(stop)
    assert stop.waits == [1, 2, 4, 8, 16, 30, 30, 30]


def test_a_long_poll_interval_is_never_shortened_by_a_failure(clock, caplog) -> None:
    rig = Rig(clock, poll_interval=100.0)
    rig.tailer.poll = _always_fail
    stop = ScriptedStop(2)
    rig.monitor.run_forever(stop)
    assert stop.waits == [100, 100]


def test_repeated_failures_alert_once(rig: Rig, caplog) -> None:
    rig.tailer.poll = _always_fail
    rig.monitor.run_forever(ScriptedStop(4))
    assert rig.notifier.alerts == []

    rig.monitor.run_forever(ScriptedStop(20))
    assert [alert.kind for alert in rig.notifier.alerts] == [AlertKind.MONITOR_ERROR]
    assert rig.notifier.alerts[0].fields["failures"] == 5


def test_a_success_resets_the_delay_and_the_alert(rig: Rig, caplog) -> None:
    outcomes = iter([True] * 5 + [False] + [True] * 5)

    def poll() -> list[str]:
        if next(outcomes):
            raise RuntimeError("bug")
        return []

    rig.tailer.poll = poll
    stop = ScriptedStop(11)
    rig.monitor.run_forever(stop)
    assert stop.waits[5] == 0.5
    assert stop.waits[6] == 1
    assert len(rig.notifier.alerts) == 2


def test_a_failing_notifier_does_not_stop_the_loop(clock, caplog) -> None:
    class BrokenNotifier(RecordingNotifier):
        def notify(self, alert: Alert) -> None:
            raise RuntimeError("also broken")

    rig = Rig(clock, notifier=BrokenNotifier())
    rig.tailer.poll = _always_fail
    stop = ScriptedStop(6)
    rig.monitor.run_forever(stop)
    assert len(stop.waits) == 6
    assert "failed to dispatch monitor_error" in caplog.text


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
