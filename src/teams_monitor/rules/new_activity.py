"""Alert when the taskbar unread count rises and stays up.

Sending a message can make the count rise and fall within milliseconds, so a rise is held
briefly and a fall back to the earlier count cancels it. The count also rises right after a
missed call, so rises inside a short window after one are suppressed. That window rests on
a single observation. Requires DBG level logging in Teams.

A rise needs a count to compare against, and with nothing unread Teams may not write a numeric
badge for a long time. Teams also logs its unread count every 5 minutes, so that line supplies
the baseline until a badge does. Badges take priority because the count line lags behind them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from teams_monitor import alerts
from teams_monitor.clock import Clock
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule

log = logging.getLogger(__name__)

HOLD_SECONDS = 2.0
# Unread messages survive a restart, but a count logged while Teams starts may not include them
# yet. No startup log was available to measure this, so the length is a cautious estimate.
STARTUP_SETTLE_SECONDS = 60.0


@dataclass(slots=True)
class _HeldRise:
    alert: Alert
    baseline: int
    ts: datetime | None
    held_at: float


def _alert_for(event: Event, unread: int) -> Alert:
    return alerts.new_activity(unread, event.groups["presence"], event.line.log_ts)


class NewActivityRule(Rule):
    handles = frozenset({SignalName.UNREAD_BADGE, SignalName.UNREAD_COUNT, SignalName.APP_STARTED})

    def __init__(
        self,
        last_missed_at: Callable[[], datetime | None],
        suppress_after_missed: float,
        clock: Clock,
        hold: float = HOLD_SECONDS,
    ) -> None:
        self._last_missed_at = last_missed_at
        self._suppress_after_missed = suppress_after_missed
        self._clock = clock
        self._hold = hold
        self._last_unread: int | None = None
        self._held: _HeldRise | None = None
        self._restarted_at: datetime | None = None

    def on_event(self, event: Event) -> list[Alert]:
        # Log time settles a held rise first, so a burst of old lines is judged correctly.
        settled = self._release_if_settled(event.line.ts)
        if event.signal is SignalName.APP_STARTED:
            # Unread messages survive a restart, so the next value is a new baseline.
            self._mark_restart(event)
            self._held = None
        elif event.signal is SignalName.UNREAD_COUNT:
            if self._seed_from_count(event):
                log.info("unread baseline set to %d from the Teams count", self._last_unread)
        else:
            self._on_badge(event)
        return settled

    def on_tick(self) -> list[Alert]:
        held = self._held
        if held is None or self._clock.monotonic() - held.held_at < self._hold:
            return []
        self._held = None
        return [held.alert]

    def on_history(self, event: Event) -> None:
        if event.signal is SignalName.APP_STARTED:
            self._mark_restart(event)
        elif event.signal is SignalName.UNREAD_COUNT:
            self._seed_from_count(event)
        elif event.signal is SignalName.UNREAD_BADGE:
            self._last_unread = int(event.groups["unread"])

    def _on_badge(self, event: Event) -> None:
        unread = int(event.groups["unread"])
        previous, self._last_unread = self._last_unread, unread
        if previous is None:
            log.info("unread baseline set to %d from the first badge, not alerting", unread)
        elif unread < previous:
            self._on_fall(event, unread)
        elif unread > previous and not self._is_suppressed(event.line.ts):
            self._on_rise(event, unread, previous)

    def _mark_restart(self, event: Event) -> None:
        self._last_unread = None
        self._restarted_at = event.line.ts

    def _seed_from_count(self, event: Event) -> bool:
        if self._last_unread is not None or self._is_starting_up(event.line.ts):
            return False
        self._last_unread = int(event.groups["unread"])
        return True

    def _is_starting_up(self, ts: datetime | None) -> bool:
        if self._restarted_at is None:
            return False
        return ts is None or (ts - self._restarted_at).total_seconds() < STARTUP_SETTLE_SECONDS

    def _release_if_settled(self, ts: datetime | None) -> list[Alert]:
        held = self._held
        if held is None or ts is None or held.ts is None:
            return []
        if (ts - held.ts).total_seconds() < self._hold:
            return []
        self._held = None
        return [held.alert]

    def _on_rise(self, event: Event, unread: int, previous: int) -> None:
        alert = _alert_for(event, unread)
        if self._held is None:
            self._held = _HeldRise(alert, previous, event.line.ts, self._clock.monotonic())
        else:
            self._held.alert = alert

    def _on_fall(self, event: Event, unread: int) -> None:
        held = self._held
        if held is None:
            return
        if unread <= held.baseline:
            self._held = None
        else:
            held.alert = _alert_for(event, unread)

    def _is_suppressed(self, ts: datetime | None) -> bool:
        missed_at = self._last_missed_at()
        if ts is None or missed_at is None:
            return False
        return 0 <= (ts - missed_at).total_seconds() <= self._suppress_after_missed
