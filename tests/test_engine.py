from __future__ import annotations

from datetime import timedelta

from helpers import CALL_A, badge, ended, incoming, parse, unrelated

from teams_monitor import alerts
from teams_monitor.engine import Engine
from teams_monitor.health import HealthState
from teams_monitor.models import Alert, AlertKind, Event, SignalName
from teams_monitor.parsing import LineParser
from teams_monitor.rules import build_default_rules
from teams_monitor.rules.base import Rule
from teams_monitor.signals import SignalMatcher


class StubRule(Rule):
    handles = frozenset({SignalName.CALL_INCOMING})

    def __init__(self, name: str, ticking: bool = False) -> None:
        self.name = name
        self.ticking = ticking
        self.events: list[Event] = []

    def on_event(self, event: Event) -> list[Alert]:
        self.events.append(event)
        return [alerts.teams_down(self.name)]

    def on_tick(self) -> list[Alert]:
        return [alerts.teams_down(f"{self.name} tick")] if self.ticking else []


def _engine(*rules: Rule) -> Engine:
    return Engine(LineParser(), SignalMatcher(), rules)


def test_parse_returns_none_for_lines_not_in_the_format() -> None:
    assert _engine().parse("garbage") is None


def test_line_matching_no_signal_reaches_no_rule() -> None:
    rule = StubRule("a")
    assert _engine(rule).route(parse(unrelated())) == []
    assert rule.events == []


def test_rule_only_receives_signals_it_handles() -> None:
    rule = StubRule("a")
    assert _engine(rule).route(parse(ended())) == []
    assert rule.events == []


def test_every_handling_rule_runs_in_order() -> None:
    first, second = StubRule("first"), StubRule("second")
    result = _engine(first, second).route(parse(incoming()))
    assert [alert.fields["reason"] for alert in result] == ["first", "second"]


def test_tick_collects_from_every_rule() -> None:
    result = _engine(StubRule("a", ticking=True), StubRule("b"), StubRule("c", ticking=True)).tick()
    assert [alert.fields["reason"] for alert in result] == ["a tick", "c tick"]


def test_default_rules_send_incoming_and_missed_call_alerts(clock) -> None:
    engine = Engine(
        LineParser(),
        SignalMatcher(),
        build_default_rules(HealthState(clock), timedelta(seconds=3), clock),
    )
    assert [a.kind for a in engine.route(parse(incoming(CALL_A)))] == [AlertKind.INCOMING_CALL]
    assert [a.kind for a in engine.route(parse(ended(CALL_A)))] == [AlertKind.MISSED_CALL]


def test_default_rules_suppress_an_unread_rise_after_a_missed_call(clock) -> None:
    engine = Engine(
        LineParser(),
        SignalMatcher(),
        build_default_rules(HealthState(clock), timedelta(seconds=3), clock),
    )
    engine.route(parse(badge(1, at=0)))
    engine.route(parse(incoming(CALL_A, at=1)))
    engine.route(parse(ended(CALL_A, at=2)))
    assert engine.route(parse(badge(2, at=3))) == []
    clock.advance(10)
    assert engine.tick() == []
