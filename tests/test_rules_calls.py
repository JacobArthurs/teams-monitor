from __future__ import annotations

from datetime import UTC, datetime

from helpers import CALL_A, CALL_B, answered, ended, event, incoming, parse, tray_add, tray_remove

from teams_monitor.models import AlertKind
from teams_monitor.rules.incoming_call import IncomingCallRule
from teams_monitor.rules.missed_call import MissedCallRule
from teams_monitor.rules.tray_icon import TrayIconRule
from teams_monitor.watchdog import Watchdog


def test_incoming_call_alerts_with_id_and_time() -> None:
    raw = incoming(CALL_A)
    result = IncomingCallRule().on_event(event(raw))
    assert len(result) == 1
    assert result[0].kind is AlertKind.INCOMING_CALL
    assert result[0].fields == {"call_id": CALL_A, "log_ts": parse(raw).log_ts}


def test_repeated_ring_line_for_one_call_alerts_once() -> None:
    rule = IncomingCallRule()
    assert len(rule.on_event(event(incoming(CALL_A, at=0)))) == 1
    assert rule.on_event(event(incoming(CALL_A, at=1))) == []


def test_different_calls_each_alert() -> None:
    rule = IncomingCallRule()
    assert len(rule.on_event(event(incoming(CALL_A)))) == 1
    assert len(rule.on_event(event(incoming(CALL_B)))) == 1


def test_call_is_forgotten_once_it_ends() -> None:
    rule = IncomingCallRule()
    rule.on_event(event(incoming(CALL_A, at=0)))
    assert rule.on_event(event(ended(CALL_A, at=1))) == []
    assert len(rule.on_event(event(incoming(CALL_A, at=2)))) == 1


def test_call_is_forgotten_after_a_restart() -> None:
    rule = IncomingCallRule()
    rule.on_event(event(incoming(CALL_A, at=0)))
    assert rule.on_event(event(tray_add(at=1))) == []
    assert len(rule.on_event(event(incoming(CALL_A, at=2)))) == 1


def test_ring_then_end_is_a_missed_call() -> None:
    rule = MissedCallRule()
    assert rule.on_event(event(incoming(CALL_A))) == []
    raw = ended(CALL_A, at=20)
    result = rule.on_event(event(raw))
    assert [alert.kind for alert in result] == [AlertKind.MISSED_CALL]
    assert result[0].fields == {"call_id": CALL_A, "log_ts": parse(raw).log_ts}


def test_answered_call_is_not_missed() -> None:
    rule = MissedCallRule()
    rule.on_event(event(incoming(CALL_A)))
    assert rule.on_event(event(answered(CALL_A, at=2))) == []
    assert rule.on_event(event(ended(CALL_A, at=60))) == []
    assert rule.last_missed_at is None


def test_end_without_a_ring_is_not_missed() -> None:
    # An outgoing call ends this way.
    assert MissedCallRule().on_event(event(ended(CALL_A))) == []


def test_duplicate_end_alerts_once() -> None:
    rule = MissedCallRule()
    rule.on_event(event(incoming(CALL_A)))
    assert len(rule.on_event(event(ended(CALL_A, at=1)))) == 1
    assert rule.on_event(event(ended(CALL_A, at=2))) == []


def test_overlapping_calls_are_tracked_separately() -> None:
    rule = MissedCallRule()
    rule.on_event(event(incoming(CALL_A)))
    rule.on_event(event(incoming(CALL_B, at=1)))
    rule.on_event(event(answered(CALL_B, at=2)))
    assert rule.on_event(event(ended(CALL_B, at=3, remaining=1))) == []
    missed = rule.on_event(event(ended(CALL_A, at=4)))
    assert [alert.fields["call_id"] for alert in missed] == [CALL_A]


def test_answering_a_different_call_does_not_affect_the_ringing_one() -> None:
    rule = MissedCallRule()
    rule.on_event(event(incoming(CALL_A)))
    rule.on_event(event(answered(CALL_B, at=1)))
    assert len(rule.on_event(event(ended(CALL_A, at=2)))) == 1


def test_restart_forgets_ringing_calls() -> None:
    rule = MissedCallRule()
    rule.on_event(event(incoming(CALL_A)))
    assert rule.on_event(event(tray_add(at=1))) == []
    assert rule.on_event(event(ended(CALL_A, at=2))) == []


def test_last_missed_at_is_set_only_by_a_missed_call() -> None:
    rule = MissedCallRule()
    assert rule.last_missed_at is None
    rule.on_event(event(incoming(CALL_A)))
    assert rule.last_missed_at is None
    rule.on_event(event(ended(CALL_A, at=5)))
    assert rule.last_missed_at == datetime(2026, 11, 3, 17, 53, 50, tzinfo=UTC)


def test_tray_icon_rule_never_alerts_directly(clock) -> None:
    rule = TrayIconRule(Watchdog(clock, 600.0))
    assert rule.on_event(event(tray_remove())) == []
    assert rule.on_event(event(tray_add())) == []


def test_tray_add_marks_teams_up(clock) -> None:
    watchdog = Watchdog(clock, 600.0)
    rule = TrayIconRule(watchdog)
    rule.on_event(event(tray_remove()))
    clock.advance(5)
    watchdog.check_tray()
    assert watchdog.is_down is True
    rule.on_event(event(tray_add()))
    assert watchdog.is_down is False


def test_tray_removal_is_recorded_not_treated_as_down(clock) -> None:
    watchdog = Watchdog(clock, 600.0)
    TrayIconRule(watchdog).on_event(event(tray_remove()))
    assert watchdog.is_down is False
    clock.advance(5)
    assert len(watchdog.check_tray()) == 1
