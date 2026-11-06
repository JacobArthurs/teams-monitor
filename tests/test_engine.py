from __future__ import annotations

import pytest
from helpers import CALL_A, CALL_B, badge, ended, incoming, unrelated

from teams_monitor import alerts
from teams_monitor.bootstrap import build_rules
from teams_monitor.engine import Engine
from teams_monitor.models import Alert, AlertKind, Event, SignalName
from teams_monitor.parsing import parse_line
from teams_monitor.rules import IncomingCallRule, Rule
from teams_monitor.watchdog import Watchdog


class StubRule(Rule):
    handles = frozenset({SignalName.CALL_INCOMING})

    def __init__(self, name: str, ticking: bool = False) -> None:
        self.name = name
        self.ticking = ticking
        self.events: list[Event] = []
        self.history: list[Event] = []

    def on_event(self, event: Event) -> list[Alert]:
        self.events.append(event)
        return [alerts.teams_down(self.name)]

    def on_tick(self) -> list[Alert]:
        return [alerts.teams_down(f"{self.name} tick")] if self.ticking else []

    def on_history(self, event: Event) -> None:
        self.history.append(event)


def _default_engine(clock) -> Engine:
    return Engine(build_rules(Watchdog(clock, 600.0), 3.0, clock))


def test_lines_are_counted_by_kind_and_blanks_are_skipped() -> None:
    result = Engine([]).process(["garbage", unrelated(), "", "   ", "more garbage", unrelated()])
    assert (result.recognized, result.unrecognized) == (2, 2)


def test_line_matching_no_signal_reaches_no_rule() -> None:
    rule = StubRule("a")
    assert Engine([rule]).process([unrelated()]).alerts == []
    assert rule.events == []


def test_rule_only_receives_signals_it_handles() -> None:
    rule = StubRule("a")
    assert Engine([rule]).process([ended()]).alerts == []
    assert rule.events == []


def test_every_handling_rule_runs_in_order() -> None:
    result = Engine([StubRule("first"), StubRule("second")]).process([incoming()])
    assert [alert.fields["reason"] for alert in result.alerts] == ["first", "second"]


def test_parse_failure_does_not_stop_the_batch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def flaky(raw: str):
        if "boom" in raw:
            raise OSError("bad timestamp")
        return parse_line(raw)

    monkeypatch.setattr("teams_monitor.engine.parse_line", flaky)
    result = Engine([IncomingCallRule()]).process(["boom", incoming(CALL_A)])
    assert [alert.kind for alert in result.alerts] == [AlertKind.INCOMING_CALL]
    assert "failed to process a log line" in caplog.text


def test_rule_failure_does_not_stop_the_batch(caplog: pytest.LogCaptureFixture) -> None:
    class FlakyRule(IncomingCallRule):
        def on_event(self, event: Event) -> list[Alert]:
            if event.groups["call_id"] == CALL_A:
                raise RuntimeError("bug")
            return super().on_event(event)

    result = Engine([FlakyRule()]).process([incoming(CALL_A), incoming(CALL_B)])
    assert [alert.fields["call_id"] for alert in result.alerts] == [CALL_B]
    assert result.recognized == 2
    assert "failed to process a log line" in caplog.text


def test_restore_reaches_on_history_and_never_on_event() -> None:
    rule = StubRule("a")
    Engine([rule]).restore(["garbage", unrelated(), incoming(CALL_A)])
    assert [event.groups["call_id"] for event in rule.history] == [CALL_A]
    assert rule.events == []


def test_tick_collects_from_every_rule() -> None:
    result = Engine(
        [StubRule("a", ticking=True), StubRule("b"), StubRule("c", ticking=True)]
    ).tick()
    assert [alert.fields["reason"] for alert in result] == ["a tick", "c tick"]


def test_default_rules_send_incoming_and_missed_call_alerts(clock) -> None:
    engine = _default_engine(clock)
    assert [a.kind for a in engine.process([incoming(CALL_A)]).alerts] == [AlertKind.INCOMING_CALL]
    assert [a.kind for a in engine.process([ended(CALL_A)]).alerts] == [AlertKind.MISSED_CALL]


def test_default_rules_suppress_an_unread_rise_after_a_missed_call(clock) -> None:
    engine = _default_engine(clock)
    engine.process([badge(1, at=0), incoming(CALL_A, at=1), ended(CALL_A, at=2)])
    assert engine.process([badge(2, at=3)]).alerts == []
    clock.advance(10)
    assert engine.tick() == []
