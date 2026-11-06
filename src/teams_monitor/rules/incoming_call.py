from __future__ import annotations

from teams_monitor import alerts
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class IncomingCallRule(Rule):
    handles = frozenset({SignalName.CALL_INCOMING, SignalName.CALL_ENDED, SignalName.APP_STARTED})

    def __init__(self) -> None:
        self._alerted: set[str] = set()

    def on_event(self, event: Event) -> list[Alert]:
        if event.signal is SignalName.APP_STARTED:
            self._alerted.clear()
            return []

        call_id = event.groups["call_id"]
        if event.signal is SignalName.CALL_ENDED:
            self._alerted.discard(call_id)
            return []

        if call_id in self._alerted:
            return []
        self._alerted.add(call_id)
        return [alerts.incoming_call(call_id, event.line.log_ts)]
