"""A1: alert immediately when a call starts ringing."""

from __future__ import annotations

from teams_monitor import alerts
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class IncomingCallRule(Rule):
    handles = frozenset({SignalName.CALL_INCOMING})

    def on_event(self, event: Event) -> list[Alert]:
        return [alerts.incoming_call(event.groups["call_id"], event.line.log_ts)]
