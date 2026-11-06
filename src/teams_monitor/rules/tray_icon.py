"""Passes tray icon lines to the Watchdog. Never alerts itself.

Teams removes and re-adds its tray icon at every launch, so a removal alone proves nothing.
The Watchdog alerts if the icon stays away, and it also covers crashes, which never write
these lines.
"""

from __future__ import annotations

from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule
from teams_monitor.watchdog import Watchdog


class TrayIconRule(Rule):
    handles = frozenset({SignalName.APP_STARTED, SignalName.APP_EXITED})

    def __init__(self, watchdog: Watchdog) -> None:
        self._watchdog = watchdog

    def on_event(self, event: Event) -> list[Alert]:
        if event.signal is SignalName.APP_STARTED:
            self._watchdog.note_tray_added()
        else:
            self._watchdog.note_tray_removed()
        return []
