"""Test doubles and builders for Teams log lines."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from teams_monitor.models import Alert, Event, LogLine
from teams_monitor.notifiers.base import Notifier
from teams_monitor.parsing import LineParser
from teams_monitor.signals import SignalMatcher
from teams_monitor.watchdog import ProcessProbe

SAMPLES_PATH = Path(__file__).parent / "data" / "log_samples.json"

CALL_A = "5287a96c-657d-4d03-a428-516cae679e0a"
CALL_B = "13e25d06-3814-4a7f-afbd-109d3c013a6a"
TRAY_ID = "{AF0ADBF8-4B35-4FFD-B1DB-18DE16ABB0F4}"

_BASE = datetime(2026, 11, 3, 17, 53, 45)


def load_samples() -> dict[str, str]:
    """The real log lines supplied for each event, keyed by event name."""
    entries = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    return {entry["event"]: entry["example"] for entry in entries}


def stamp(at: float = 0.0) -> str:
    """A log timestamp `at` seconds after the base time."""
    return (_BASE + timedelta(seconds=at)).isoformat(timespec="microseconds") + "-05:00"


def _line(at: float, level: str, msg: str) -> str:
    return f"{stamp(at)} 0x00003e44 <{level}> {msg}"


def incoming(call_id: str = CALL_A, at: float = 0.0) -> str:
    return _line(
        at, "INFO", f"HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {call_id}"
    )


def answered(call_id: str = CALL_A, at: float = 0.0) -> str:
    return _line(
        at, "INFO", f"HfpVoipCallCoordinatorImpl: reportCallAccepted for callId: {call_id}"
    )


def ended(call_id: str = CALL_A, at: float = 0.0, remaining: int = 0) -> str:
    return _line(at, "INFO", f"TeamsCallTracker: Call ended: {call_id} (remaining: {remaining})")


def badge(unread: int, at: float = 0.0, presence: str = "Available") -> str:
    return _line(
        at,
        "DBG",
        f"TaskbarBadgeServiceLegacy:Work: SetBadge Setting badge: NumericBadge{{{unread}}}, "
        f"overlay: 1 items, status {presence}",
    )


def unread_count(unread: int, at: float = 0.0) -> str:
    return _line(
        at,
        "INFO",
        "native_modules::UserDataCrossCloudModule: BroadcastGlobalState: New Global State Event: "
        "UserDataGlobalState total number of users: 1 "
        f"{{ availability: Available, unread notification count: {unread} }}",
    )


def tray_add(at: float = 0.0) -> str:
    return _line(
        at,
        "INFO",
        f"NotificationIcon: (id={TRAY_ID}; fallback_id=1) Shell_NotifyIconW(NIM_ADD, id={TRAY_ID})",
    )


def tray_remove(at: float = 0.0) -> str:
    # SYNTHETIC: built from the real NIM_ADD sample by swapping the verb. No real NIM_DELETE
    # line was available, so this shows what the signal accepts, not what Teams writes.
    return _line(
        at,
        "INFO",
        f"NotificationIcon: (id={TRAY_ID}; fallback_id=1) "
        f"Shell_NotifyIconW(NIM_DELETE, id={TRAY_ID})",
    )


def unrelated(at: float = 0.0) -> str:
    return _line(at, "INFO", "SomeComponent: nothing the monitor cares about")


def parse(raw: str) -> LogLine:
    line = LineParser().parse(raw)
    assert line is not None, f"line did not parse: {raw}"
    return line


def event(raw: str) -> Event:
    found = SignalMatcher().match(parse(raw))
    assert found is not None, f"line matched no signal: {raw}"
    return found


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self) -> None:
        self._monotonic = 1000.0
        self._now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self._monotonic

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)

    def set_time_of_day(self, value: time) -> None:
        self._now = self._now.replace(hour=value.hour, minute=value.minute, second=value.second)


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.closed = 0

    def notify(self, alert: Alert) -> None:
        self.alerts.append(alert)

    def close(self) -> None:
        self.closed += 1

    @property
    def kinds(self) -> list[str]:
        return [alert.kind.value for alert in self.alerts]


class FakeProbe(ProcessProbe):
    def __init__(self, running: bool | None = True) -> None:
        self.running = running

    def is_running(self) -> bool | None:
        return self.running
