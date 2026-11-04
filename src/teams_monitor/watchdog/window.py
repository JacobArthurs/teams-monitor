"""Daily time window in which outage checks are active."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class ActiveWindow:
    start: time
    end: time

    @classmethod
    def parse(cls, text: str) -> ActiveWindow:
        """Parse "HH:MM-HH:MM". The window may wrap past midnight."""
        try:
            raw_start, raw_end = text.split("-")
            return cls(
                datetime.strptime(raw_start.strip(), "%H:%M").time(),
                datetime.strptime(raw_end.strip(), "%H:%M").time(),
            )
        except ValueError as exc:
            raise ValueError(f"invalid window {text!r}, expected HH:MM-HH:MM") from exc

    def contains(self, moment: time) -> bool:
        if self.start <= self.end:
            return self.start <= moment <= self.end
        return moment >= self.start or moment <= self.end
