from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SignalName(StrEnum):
    CALL_INCOMING = "call_incoming"
    CALL_ANSWERED = "call_answered"
    CALL_ENDED = "call_ended"
    UNREAD_BADGE = "unread_badge"
    APP_STARTED = "app_started"
    APP_EXITED = "app_exited"
    UNREAD_COUNT = "unread_count"


class AlertKind(StrEnum):
    INCOMING_CALL = "incoming_call"
    MISSED_CALL = "missed_call"
    # The value keeps its old name for webhook payloads.
    NEW_ACTIVITY = "new_message"
    TEAMS_DOWN = "teams_down"
    MONITOR_ERROR = "monitor_error"
    TEST = "test"


@dataclass(frozen=True, slots=True)
class LogLine:
    log_ts: str  # the line's time in local time, or its original text if that is invalid
    ts: datetime | None
    level: str
    msg: str


@dataclass(frozen=True, slots=True)
class Event:
    signal: SignalName
    line: LogLine
    groups: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Alert:
    kind: AlertKind
    priority: int
    text: str
    fields: Mapping[str, object] = field(default_factory=dict)
