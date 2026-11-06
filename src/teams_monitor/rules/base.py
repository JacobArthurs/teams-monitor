from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from teams_monitor.models import Alert, Event, SignalName


class Rule(ABC):
    handles: ClassVar[frozenset[SignalName]]

    @abstractmethod
    def on_event(self, event: Event) -> list[Alert]:
        pass

    def on_tick(self) -> list[Alert]:
        """Called after each poll, for rules that alert once time has passed."""
        return []

    def on_history(self, event: Event) -> None:
        """Restore state from a line written before the monitor started. Must not alert."""
        return None
