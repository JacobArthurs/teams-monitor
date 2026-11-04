"""A4 (log driven half): track the Teams tray icon.

Teams removes and re-adds its tray icon at every launch, so a removal alone proves nothing.
This rule only records it. The Watchdog alerts if the icon stays away, and it also covers
crashes, which never write these lines.
"""

from __future__ import annotations

from teams_monitor.health import HealthState
from teams_monitor.models import Alert, Event, SignalName
from teams_monitor.rules.base import Rule


class TeamsDownRule(Rule):
    handles = frozenset({SignalName.APP_STARTED, SignalName.APP_EXITED})

    def __init__(self, health: HealthState) -> None:
        self._health = health

    def on_event(self, event: Event) -> list[Alert]:
        if event.signal is SignalName.APP_STARTED:
            self._health.mark_up()
        else:
            self._health.note_tray_removed()
        return []
