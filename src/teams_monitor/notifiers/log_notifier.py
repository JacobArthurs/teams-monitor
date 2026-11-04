"""Writes alerts to the application log. Doubles as the dry-run sink."""

from __future__ import annotations

import logging

from teams_monitor.models import Alert
from teams_monitor.notifiers.base import Notifier

log = logging.getLogger(__name__)


class LogNotifier(Notifier):
    def notify(self, alert: Alert) -> None:
        log.info("ALERT %s p%d: %s", alert.kind.value, alert.priority, alert.text)
