from __future__ import annotations

from datetime import datetime

from teams_monitor.models import Alert


def build_payload(alert: Alert, host: str, sent_at: datetime) -> dict[str, object]:
    text = f"[Teams] {alert.text}"
    return {
        **alert.fields,
        "alert": alert.kind.value,
        "priority": alert.priority,
        # Slack style hooks read "text", Discord reads "content".
        "text": text,
        "content": text,
        "host": host,
        "sent_at": sent_at.isoformat(timespec="seconds"),
    }
