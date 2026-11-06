from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class ActiveWindow:
    start: time
    end: time

    @classmethod
    def parse(cls, text: str) -> ActiveWindow:
        try:
            raw_start, raw_end = text.split("-")
            start = datetime.strptime(raw_start.strip(), "%H:%M").time()
            end = datetime.strptime(raw_end.strip(), "%H:%M").time()
        except ValueError as exc:
            raise ValueError(f"invalid window {text!r}, expected HH:MM-HH:MM") from exc
        if start == end:
            # This would be active for a single instant, silently turning off outage alerts.
            raise ValueError(f"invalid window {text!r}, start and end must differ")
        return cls(start, end)

    def contains(self, moment: time) -> bool:
        if self.start <= self.end:
            return self.start <= moment <= self.end
        return moment >= self.start or moment <= self.end
