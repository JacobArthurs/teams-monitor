"""Outage detection that does not depend on log lines."""

from teams_monitor.watchdog.activity import ActivityTracker
from teams_monitor.watchdog.process import ProcessProbe, TasklistProbe
from teams_monitor.watchdog.watchdog import Watchdog

__all__ = ["ActivityTracker", "ProcessProbe", "TasklistProbe", "Watchdog"]
