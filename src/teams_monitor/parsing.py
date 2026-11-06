"""Turns raw log text into LogLine objects."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from teams_monitor.models import LogLine

MAX_LINE_LENGTH = 4096

_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT[\d:.]+[+-]\d\d:\d\d) "
    r"0x[0-9a-f]+ "
    r"<(?P<level>[A-Z]+)>\s+(?P<msg>.*)$"
)


def parse_timestamp(value: str) -> datetime | None:
    """Teams writes UTC clock time but labels it with the local offset, so the label is ignored."""
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def _local_text(ts: datetime | None, original: str) -> str:
    """The time in local time, or the original text if it is invalid or cannot be converted."""
    if ts is None:
        return original
    try:
        return ts.astimezone().isoformat()
    except (OSError, OverflowError, ValueError):  # the year is outside what the OS can convert
        return original


def parse_line(raw: str) -> LogLine | None:
    """Parse one log line, truncated first to bound regex work. None if not in the format."""
    found = _LINE.match(raw[:MAX_LINE_LENGTH])
    if found is None:
        return None
    ts = parse_timestamp(found["ts"])
    return LogLine(
        log_ts=_local_text(ts, found["ts"]),
        ts=ts,
        level=found["level"],
        msg=found["msg"],
    )
