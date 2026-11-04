"""Alert constructors. Single place that owns alert priorities and wording."""

from __future__ import annotations

from teams_monitor.models import Alert, AlertKind

PRIORITY_INCOMING_CALL = 1
PRIORITY_MISSED_CALL = 2
PRIORITY_NEW_MESSAGE = 3
PRIORITY_TEAMS_DOWN = 4


def incoming_call(call_id: str, log_ts: str) -> Alert:
    return Alert(
        AlertKind.INCOMING_CALL,
        PRIORITY_INCOMING_CALL,
        "Incoming call",
        {"call_id": call_id, "log_ts": log_ts},
    )


def missed_call(call_id: str, log_ts: str) -> Alert:
    return Alert(
        AlertKind.MISSED_CALL,
        PRIORITY_MISSED_CALL,
        "Missed call",
        {"call_id": call_id, "log_ts": log_ts},
    )


def new_message(unread: int, presence: str, log_ts: str) -> Alert:
    return Alert(
        AlertKind.NEW_MESSAGE,
        PRIORITY_NEW_MESSAGE,
        f"New activity (unread {unread})",
        {"unread": unread, "presence": presence, "log_ts": log_ts},
    )


def teams_down(reason: str, log_ts: str | None = None) -> Alert:
    fields: dict[str, object] = {"reason": reason}
    if log_ts is not None:
        fields["log_ts"] = log_ts
    return Alert(
        AlertKind.TEAMS_DOWN,
        PRIORITY_TEAMS_DOWN,
        f"Teams down: {reason}",
        fields,
    )
