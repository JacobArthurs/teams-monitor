"""A2: alert when a ringing call ends without having been answered.

Missed, declined and caller-cancelled calls cannot be told apart in the logs.
"""

from __future__ import annotations

from datetime import datetime

from teams_monitor import alerts
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class MissedCallRule(Rule):
    handles = frozenset(
        {
            SignalName.CALL_INCOMING,
            SignalName.CALL_ANSWERED,
            SignalName.CALL_ENDED,
            SignalName.APP_STARTED,
        }
    )

    def __init__(self) -> None:
        self._ringing: set[str] = set()
        self._last_missed_at: datetime | None = None

    @property
    def last_missed_at(self) -> datetime | None:
        """Log timestamp of the most recent missed call, used by other rules."""
        return self._last_missed_at

    def on_event(self, event: Event) -> list[Alert]:
        signal = event.signal
        if signal is SignalName.APP_STARTED:
            self._ringing.clear()
            return []

        call_id = event.groups["call_id"]
        if signal is SignalName.CALL_INCOMING:
            self._ringing.add(call_id)
        elif signal is SignalName.CALL_ANSWERED:
            self._ringing.discard(call_id)
        elif signal is SignalName.CALL_ENDED and call_id in self._ringing:
            self._ringing.discard(call_id)
            self._last_missed_at = event.line.ts
            return [alerts.missed_call(call_id, event.line.raw_ts)]
        return []
