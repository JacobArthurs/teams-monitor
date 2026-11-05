from __future__ import annotations

import json

import pytest

from teams_monitor import alerts
from teams_monitor.models import AlertKind
from teams_monitor.notifiers import PayloadBuilder


def test_common_fields(clock) -> None:
    payload = PayloadBuilder("MY-PC", clock).build(alerts.incoming_call("id", "ts"))
    assert payload == {
        "alert": "incoming_call",
        "priority": 1,
        "text": "[Teams] Incoming call",
        "content": "[Teams] Incoming call",
        "host": "MY-PC",
        "sent_at": "2026-11-03T12:00:00+00:00",
        "call_id": "id",
        "log_ts": "ts",
    }


@pytest.mark.parametrize(
    ("alert", "expected"),
    [
        (alerts.incoming_call("id", "ts"), {"call_id": "id", "log_ts": "ts"}),
        (alerts.missed_call("id", "ts"), {"call_id": "id", "log_ts": "ts"}),
        (alerts.new_message(4, "Busy", "ts"), {"unread": 4, "presence": "Busy", "log_ts": "ts"}),
        (alerts.teams_down("why"), {"reason": "why"}),
    ],
)
def test_each_alert_adds_its_own_fields_and_is_json_safe(clock, alert, expected) -> None:
    payload = PayloadBuilder("MY-PC", clock).build(alert)
    assert expected.items() <= payload.items()
    json.dumps(payload)


@pytest.mark.parametrize(
    ("alert", "kind", "priority", "text"),
    [
        (alerts.incoming_call("i", "t"), AlertKind.INCOMING_CALL, 1, "Incoming call"),
        (alerts.missed_call("i", "t"), AlertKind.MISSED_CALL, 2, "Missed call"),
        (alerts.new_message(4, "p", "t"), AlertKind.NEW_MESSAGE, 3, "New activity (unread 4)"),
        (alerts.teams_down("why"), AlertKind.TEAMS_DOWN, 4, "Teams down: why"),
    ],
)
def test_alert_priorities_and_wording(alert, kind, priority: int, text: str) -> None:
    assert (alert.kind, alert.priority, alert.text) == (kind, priority, text)
