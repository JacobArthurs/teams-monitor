"""Signal definitions and the function that applies them."""

from __future__ import annotations

import re
from dataclasses import dataclass

from teams_monitor.models import Event, LogLine, SignalName

GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern.replace("{GUID}", GUID))


@dataclass(frozen=True, slots=True)
class Signal:
    name: SignalName
    level: str
    pattern: re.Pattern[str]

    def match(self, line: LogLine) -> Event | None:
        found = self.pattern.match(line.msg) if line.level == self.level else None
        if found is None:
            return None
        return Event(signal=self.name, line=line, groups=found.groupdict())


SIGNALS: tuple[Signal, ...] = (
    Signal(
        SignalName.CALL_INCOMING,
        "INFO",
        _compile(
            r"^HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: "
            r"(?P<call_id>{GUID})\s*$"
        ),
    ),
    Signal(
        SignalName.CALL_ANSWERED,
        "INFO",
        _compile(
            r"^HfpVoipCallCoordinatorImpl: reportCallAccepted for callId: "
            r"(?P<call_id>{GUID})\s*$"
        ),
    ),
    Signal(
        SignalName.CALL_ENDED,
        "INFO",
        _compile(
            r"^TeamsCallTracker: Call ended: (?P<call_id>{GUID}) "
            r"\(remaining: \d+\)"
        ),
    ),
    Signal(
        SignalName.UNREAD_BADGE,
        "DBG",
        _compile(
            r"^TaskbarBadgeServiceLegacy:Work: SetBadge Setting badge: "
            r"NumericBadge\{(?P<unread>\d+)\}, overlay: \d+ items, "
            r"status (?P<presence>.+?)\s*$"
        ),
    ),
    Signal(
        SignalName.APP_STARTED,
        "INFO",
        _compile(
            r"^NotificationIcon: \(id=\{[0-9A-F-]+\}; fallback_id=\d+\) "
            r"Shell_NotifyIconW\(NIM_ADD, id=\{[0-9A-F-]+\}\)"
        ),
    ),
    Signal(
        SignalName.APP_EXITED,
        "INFO",
        _compile(
            r"^NotificationIcon: \(id=\{[0-9A-F-]+\}; fallback_id=\d+\) "
            r"Shell_NotifyIconW\(NIM_DELETE, id=\{[0-9A-F-]+\}\)"
        ),
    ),
    Signal(
        SignalName.UNREAD_COUNT,
        "INFO",
        _compile(
            r"^native_modules::UserDataCrossCloudModule: BroadcastGlobalState: "
            r"New Global State Event: UserDataGlobalState total number of users: \d+ "
            r"\{ availability: .*?, unread notification count: (?P<unread>\d+) \}\s*$"
        ),
    ),
)


def match_signal(line: LogLine) -> Event | None:
    """Find the signal a log line represents, if any."""
    for signal in SIGNALS:
        event = signal.match(line)
        if event is not None:
            return event
    return None
