"""Turns raw log text into LogLine objects."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from teams_monitor.models import LogLine

MAX_LINE_LENGTH = 4096

_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT[\d:.]+[+-]\d\d:\d\d) "
    r"(?P<thread>0x[0-9a-f]+) "
    r"<(?P<level>[A-Z]+)>\s+(?P<msg>.*)$"
)


def parse_timestamp(value: str) -> datetime | None:
    """Teams writes UTC clock time but labels it with the local offset, so the label is ignored."""
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


class LineParser:
    """Parses one log line. Lines are truncated first to bound regex work."""

    def __init__(self, max_length: int = MAX_LINE_LENGTH) -> None:
        self._max_length = max_length

    def parse(self, raw: str) -> LogLine | None:
        found = _LINE.match(raw[: self._max_length])
        if found is None:
            return None
        ts = parse_timestamp(found["ts"])
        return LogLine(
            log_ts=ts.astimezone().isoformat() if ts else found["ts"],
            ts=ts,
            thread=found["thread"],
            level=found["level"],
            msg=found["msg"],
        )
