"""A4 (log driven half): alert when Teams removes its tray icon.

Crashes never write this line. The Watchdog covers those cases.
"""

from __future__ import annotations

from collections.abc import Callable

from teams_monitor import alerts
from teams_monitor.health import HealthState
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class TeamsDownRule(Rule):
    handles = frozenset({SignalName.APP_STARTED, SignalName.APP_EXITED})

    def __init__(self, health: HealthState, in_active_hours: Callable[[], bool]) -> None:
        self._health = health
        self._in_active_hours = in_active_hours

    def on_event(self, event: Event) -> list[Alert]:
        if event.signal is SignalName.APP_STARTED:
            self._health.mark_up()
            return []
        # Outside active hours Teams stays marked up, so if it is still down when the
        # window opens, the Watchdog raises the alert then.
        if self._in_active_hours() and self._health.mark_down():
            return [alerts.teams_down("tray icon removed (exit or restart)", event.line.raw_ts)]
        return []
