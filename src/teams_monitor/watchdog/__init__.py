"""Outage detection that does not depend on log lines alone."""

from teams_monitor.watchdog.process import ProcessProbe, TasklistProbe
from teams_monitor.watchdog.watchdog import Watchdog

__all__ = ["ProcessProbe", "TasklistProbe", "Watchdog"]
