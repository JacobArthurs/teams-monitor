"""Time source abstraction so time-dependent logic is testable."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin, never goes backwards."""
        ...

    def now(self) -> datetime:
        """Current local time, timezone aware."""
        ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now().astimezone()
