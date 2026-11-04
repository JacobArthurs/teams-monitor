"""Notifier contract and delivery errors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from teams_monitor.models import Alert


class DeliveryError(Exception):
    """An alert could not be delivered."""


class TransientDeliveryError(DeliveryError):
    """Delivery failed in a way that may succeed on retry (network, 5xx, 429)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentDeliveryError(DeliveryError):
    """Delivery failed and retrying will not help (bad URL, 4xx)."""


class Notifier(ABC):
    @abstractmethod
    def notify(self, alert: Alert) -> None:
        """Deliver one alert. May raise DeliveryError."""

    def close(self) -> None:  # noqa: B027 - optional hook, intentionally not abstract
        """Release resources. Default is a no-op."""
