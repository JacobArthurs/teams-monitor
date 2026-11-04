"""Shared Teams up/down state, so a down alert fires once per outage."""

from __future__ import annotations

from teams_monitor.clock import Clock

# Teams keeps logging while it shuts down, so lines right after going down prove nothing.
# A real restart does not wait for this: its tray icon line marks Teams up immediately.
RECOVERY_GRACE_SECONDS = 60.0


class HealthState:
    def __init__(self, clock: Clock, recovery_grace: float = RECOVERY_GRACE_SECONDS) -> None:
        self._clock = clock
        self._recovery_grace = recovery_grace
        self._down = False
        self._down_since = 0.0

    @property
    def is_down(self) -> bool:
        return self._down

    def mark_down(self) -> bool:
        """Enter the down state. Returns True only on the up to down transition."""
        if self._down:
            return False
        self._down = True
        self._down_since = self._clock.monotonic()
        return True

    def mark_up(self) -> None:
        self._down = False

    def has_recovered(self, last_activity: float) -> bool:
        """True when the log produced new lines after the shutdown grace period."""
        return self._down and last_activity > self._down_since + self._recovery_grace
