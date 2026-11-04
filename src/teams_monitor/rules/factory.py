"""Builds the default rule set with its dependencies wired together."""

from __future__ import annotations

from datetime import timedelta

from teams_monitor.clock import Clock
from teams_monitor.health import HealthState
from teams_monitor.rules.base import Rule
from teams_monitor.rules.incoming_call import IncomingCallRule
from teams_monitor.rules.missed_call import MissedCallRule
from teams_monitor.rules.new_message import NewMessageRule
from teams_monitor.rules.teams_down import TeamsDownRule


def build_default_rules(
    health: HealthState,
    suppress_after_missed: timedelta,
    clock: Clock,
) -> list[Rule]:
    missed_calls = MissedCallRule()
    return [
        IncomingCallRule(),
        missed_calls,
        NewMessageRule(lambda: missed_calls.last_missed_at, suppress_after_missed, clock),
        TeamsDownRule(health),
    ]
