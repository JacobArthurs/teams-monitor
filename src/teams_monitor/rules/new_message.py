"""A3: alert when the taskbar unread count rises and stays up.

Sending a message can make the count rise and fall within milliseconds, so a rise is held
briefly and a fall back to the earlier count cancels it. The count also rises right after a
missed call, so rises inside a short window after one are suppressed. That window rests on
a single observation. Requires DBG level logging in Teams.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from teams_monitor import alerts
from teams_monitor.clock import Clock
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule

MESSAGE_HOLD = timedelta(seconds=2)


@dataclass(slots=True)
class _HeldRise:
    alert: Alert
    baseline: int
    ts: datetime | None
    held_at: float


class NewMessageRule(Rule):
    handles = frozenset({SignalName.UNREAD_BADGE, SignalName.APP_STARTED})

    def __init__(
        self,
        last_missed_at: Callable[[], datetime | None],
        suppress_after_missed: timedelta,
        clock: Clock,
        hold: timedelta = MESSAGE_HOLD,
    ) -> None:
        self._last_missed_at = last_missed_at
        self._suppress_after_missed = suppress_after_missed
        self._clock = clock
        self._hold = hold
        self._last_unread: int | None = None
        self._held: _HeldRise | None = None

    def on_event(self, event: Event) -> list[Alert]:
        # Log time settles a held rise first, so a burst of old lines is judged correctly.
        settled = self._release_if_settled(event.line.ts)

        if event.signal is SignalName.APP_STARTED:
            # Unread messages survive a restart, so the next value is a new baseline.
            self._last_unread = None
            self._held = None
            return settled

        unread = int(event.groups["unread"])
        previous, self._last_unread = self._last_unread, unread
        # The first value seen only sets the baseline. Equal values are refreshes.
        if previous is None or unread == previous:
            return settled
        alert = alerts.new_message(unread, event.groups["presence"], event.line.log_ts)
        if unread < previous:
            self._on_fall(unread, alert)
        elif not self._is_suppressed(event.line.ts):
            self._on_rise(previous, alert, event.line.ts)
        return settled

    def on_tick(self) -> list[Alert]:
        """Release a held rise once the hold has passed with no fall."""
        held = self._held
        if held is None or self._clock.monotonic() - held.held_at < self._hold.total_seconds():
            return []
        self._held = None
        return [held.alert]

    def _release_if_settled(self, ts: datetime | None) -> list[Alert]:
        held = self._held
        if held is None or ts is None or held.ts is None or ts - held.ts < self._hold:
            return []
        self._held = None
        return [held.alert]

    def _on_rise(self, previous: int, alert: Alert, ts: datetime | None) -> None:
        if self._held is None:
            self._held = _HeldRise(alert, previous, ts, self._clock.monotonic())
        else:
            # A burst stays one alert with the latest count, and keeps its original deadline.
            self._held.alert = alert

    def _on_fall(self, unread: int, alert: Alert) -> None:
        held = self._held
        if held is None:
            return
        if unread <= held.baseline:
            self._held = None
        else:
            held.alert = alert

    def _is_suppressed(self, ts: datetime | None) -> bool:
        missed_at = self._last_missed_at()
        if ts is None or missed_at is None:
            return False
        return timedelta(0) <= ts - missed_at <= self._suppress_after_missed
