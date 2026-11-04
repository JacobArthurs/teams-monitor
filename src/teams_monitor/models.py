"""Plain data types shared across the package. No behavior lives here."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalName(str, Enum):
    """Log patterns the monitor recognizes (S1 to S6)."""

    CALL_INCOMING = "call_incoming"
    CALL_ANSWERED = "call_answered"
    CALL_ENDED = "call_ended"
    UNREAD_BADGE = "unread_badge"
    APP_STARTED = "app_started"
    APP_EXITED = "app_exited"


class AlertKind(str, Enum):
    """Alerts the monitor can raise (A1 to A4)."""

    INCOMING_CALL = "incoming_call"
    MISSED_CALL = "missed_call"
    NEW_MESSAGE = "new_message"
    TEAMS_DOWN = "teams_down"


@dataclass(frozen=True, slots=True)
class LogLine:
    """One parsed Teams log line."""

    log_ts: str  # the line's time in local time, or its original text if that is invalid
    ts: datetime | None
    thread: str
    level: str
    msg: str


@dataclass(frozen=True, slots=True)
class Event:
    """A log line that matched a known signal, with its named regex groups."""

    signal: SignalName
    line: LogLine
    groups: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Alert:
    """Something worth telling the user about."""

    kind: AlertKind
    priority: int
    text: str
    fields: Mapping[str, object] = field(default_factory=dict)
