from __future__ import annotations

import logging

from teams_monitor import alerts
from teams_monitor.clock import Clock
from teams_monitor.models import Alert
from teams_monitor.watchdog.activity import ActivityTracker
from teams_monitor.watchdog.health import HealthState
from teams_monitor.watchdog.process import ProcessProbe
from teams_monitor.window import ActiveWindow

log = logging.getLogger(__name__)


class Watchdog:
    def __init__(
        self,
        clock: Clock,
        stale_after: float,
        probe: ProcessProbe | None = None,
        window: ActiveWindow | None = None,
    ) -> None:
        self._health = HealthState(clock)
        self._activity = ActivityTracker(clock)
        self._clock = clock
        self._stale_after = stale_after
        self._probe = probe
        self._window = window

    @property
    def is_down(self) -> bool:
        return self._health.is_down

    def note_lines(self, recognized: int, unrecognized: int) -> None:
        """Only recognized lines count as activity, so a changed log format ends in an alert."""
        if recognized:
            self._activity.touch()
        else:
            self._activity.note_unrecognized(unrecognized)

    def note_tray_added(self) -> None:
        self._health.mark_up()

    def note_tray_removed(self) -> None:
        self._health.note_tray_removed()

    def note_resume(self) -> None:
        self._activity.restart_idle()

    def check_tray(self) -> list[Alert]:
        if not self._in_window() or not self._health.take_tray_removed():
            return []
        return [alerts.teams_down("tray icon removed")] if self._health.mark_down() else []

    def check(self) -> list[Alert]:
        """Outside the window it only looks for recovery from an earlier outage. Otherwise that
        outage would still count as ongoing, and the next one could not alert.
        """
        in_window = self._in_window()
        if not in_window and not self._health.is_down:
            return []

        reason = self._down_reason()
        if reason is not None:
            return [alerts.teams_down(reason)] if in_window and self._health.mark_down() else []

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
