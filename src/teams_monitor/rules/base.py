"""Rule contract. A rule reacts to the signals it declares and may emit alerts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from teams_monitor.models import Alert, Event, SignalName


class Rule(ABC):
    handles: ClassVar[frozenset[SignalName]]

    @abstractmethod
    def on_event(self, event: Event) -> list[Alert]:
        """Handle one event. Only events for signals in `handles` are delivered."""

    def on_tick(self) -> list[Alert]:
        """Called after each poll, for rules that alert once time has passed."""
        return []
