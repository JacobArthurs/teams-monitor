"""Turns raw log text into LogLine objects."""

from __future__ import annotations

import re
from datetime import datetime

from teams_monitor.models import LogLine

MAX_LINE_LENGTH = 4096

_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT[\d:.]+[+-]\d\d:\d\d) "
    r"(?P<thread>0x[0-9a-f]+) "
    r"<(?P<level>[A-Z]+)>\s+(?P<msg>.*)$"
)


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
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
        ts = found["ts"]
        return LogLine(
            raw_ts=ts,
            ts=parse_timestamp(ts),
            thread=found["thread"],
            level=found["level"],
            msg=found["msg"],
        )
