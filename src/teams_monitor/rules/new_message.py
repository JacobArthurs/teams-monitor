"""A3: alert when the taskbar unread count rises.

The count also rises right after a missed call, so alerts inside a short window
after one are suppressed. That window rests on a single observation.
Requires DBG level logging in Teams.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from teams_monitor import alerts
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class NewMessageRule(Rule):
    handles = frozenset({SignalName.UNREAD_BADGE, SignalName.APP_STARTED})

    def __init__(
        self,
        last_missed_at: Callable[[], datetime | None],
        suppress_after_missed: timedelta,
    ) -> None:
        self._last_missed_at = last_missed_at
        self._suppress_after_missed = suppress_after_missed
        self._last_unread: int | None = None

    def on_event(self, event: Event) -> list[Alert]:
        if event.signal is SignalName.APP_STARTED:
            # Unread messages survive a restart, so the next value is a new baseline.
            self._last_unread = None
            return []

        unread = int(event.groups["unread"])
        previous, self._last_unread = self._last_unread, unread
        # The first value seen only sets the baseline. Equal values are refreshes.
        if previous is None or unread <= previous:
            return []
        if self._is_suppressed(event.line.ts):
            return []
        return [alerts.new_message(unread, event.groups["presence"], event.line.raw_ts)]

    def _is_suppressed(self, ts: datetime | None) -> bool:
        missed_at = self._last_missed_at()
        if ts is None or missed_at is None:
            return False
        return timedelta(0) <= ts - missed_at <= self._suppress_after_missed
