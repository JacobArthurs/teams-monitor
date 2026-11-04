"""Fans one alert out to several notifiers, isolating their failures."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from teams_monitor.models import Alert
from teams_monitor.notifiers.base import DeliveryError, Notifier

log = logging.getLogger(__name__)


class CompositeNotifier(Notifier):
    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        self._notifiers = tuple(notifiers)

    def notify(self, alert: Alert) -> None:
        for notifier in self._notifiers:
            try:
                notifier.notify(alert)
            except DeliveryError as exc:
                log.error(
                    "%s failed to deliver %s: %s", type(notifier).__name__, alert.kind.value, exc
                )

    def close(self) -> None:
        for notifier in self._notifiers:
            notifier.close()
