"""A4 (outage half): detects crashes and hangs that never write a log line."""

from __future__ import annotations

import logging

from teams_monitor import alerts
from teams_monitor.clock import Clock
from teams_monitor.health import HealthState
from teams_monitor.models import Alert
from teams_monitor.watchdog.activity import ActivityTracker
from teams_monitor.watchdog.process import ProcessProbe
from teams_monitor.window import ActiveWindow

log = logging.getLogger(__name__)


class Watchdog:
    def __init__(
        self,
        health: HealthState,
        activity: ActivityTracker,
        clock: Clock,
        stale_after: float,
        probe: ProcessProbe | None = None,
        window: ActiveWindow | None = None,
    ) -> None:
        self._health = health
        self._activity = activity
        self._clock = clock
        self._stale_after = stale_after
        self._probe = probe
        self._window = window

    def check_tray(self) -> list[Alert]:
        """Alert if the tray icon stayed away past its grace. Cheap enough to run on every poll."""
        if not self._in_window() or not self._health.take_tray_removed():
            return []
        return [alerts.teams_down("tray icon removed")] if self._health.mark_down() else []

    def check(self) -> list[Alert]:
        """The full outage check. It runs a process probe, so it runs less often than check_tray."""
        if not self._in_window():
            return []

        reason = self._down_reason()
        if reason is not None:
            return [alerts.teams_down(reason)] if self._health.mark_down() else []

        if self._health.has_recovered(self._activity.last_activity):
            log.info("Teams recovered")
            self._health.mark_up()
        return []

    def _in_window(self) -> bool:
        return self._window is None or self._window.contains(self._clock.now().time())

    def _down_reason(self) -> str | None:
        if self._probe is not None and self._probe.is_running() is False:
            return "Teams process is not running"
        idle = self._activity.idle_seconds()
        if idle > self._stale_after:
            if self._activity.format_suspect:
                return (
                    f"log lines not recognized for {idle / 60:.0f} min "
                    "(the log format may have changed)"
                )
            return f"no log activity for {idle / 60:.0f} min"
        return None
