"""Signal definitions (S1 to S7) and the matcher that applies them."""

from __future__ import annotations

import re
from collections import defaultdict
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
        found = self.pattern.match(line.msg)
        if found is None:
            return None
        return Event(signal=self.name, line=line, groups=found.groupdict())


DEFAULT_SIGNALS: tuple[Signal, ...] = (
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


class SignalMatcher:
    """Finds the signal a log line represents, if any. Indexed by log level."""

    def __init__(self) -> None:
        self._by_level: dict[str, list[Signal]] = defaultdict(list)
        for signal in DEFAULT_SIGNALS:
            self._by_level[signal.level].append(signal)

    def match(self, line: LogLine) -> Event | None:
        for signal in self._by_level.get(line.level, ()):
            event = signal.match(line)
            if event is not None:
                return event
        return None
