"""Builds the JSON body sent to the webhook."""

from __future__ import annotations

from teams_monitor.clock import Clock
from teams_monitor.models import Alert


class PayloadBuilder:
    def __init__(self, host: str, clock: Clock) -> None:
        self._host = host
        self._clock = clock

    def build(self, alert: Alert) -> dict[str, object]:
        text = f"[Teams] {alert.text}"
        return {
            **alert.fields,
            "alert": alert.kind.value,
            "priority": alert.priority,
            # Slack style hooks read "text", Discord reads "content".
            "text": text,
            "content": text,
            "host": self._host,
            "sent_at": self._clock.now().isoformat(timespec="seconds"),
        }
