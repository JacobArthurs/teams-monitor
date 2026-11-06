from __future__ import annotations

from abc import ABC, abstractmethod

from teams_monitor.models import Alert


class DeliveryError(Exception):
    pass


class TransientDeliveryError(DeliveryError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentDeliveryError(DeliveryError):
    pass


class Notifier(ABC):
    @abstractmethod
    def notify(self, alert: Alert) -> None:
        """May raise DeliveryError."""

    def close(self) -> None:  # noqa: B027
        pass


class NullNotifier(Notifier):
    def notify(self, alert: Alert) -> None:
        pass
