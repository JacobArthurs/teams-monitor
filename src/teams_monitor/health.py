"""Shared Teams up/down state, so a down alert fires once per outage."""

from __future__ import annotations

from teams_monitor.clock import Clock

# Teams keeps logging while it shuts down, so lines right after going down prove nothing.
# A real restart does not wait for this: its tray icon line marks Teams up immediately.
RECOVERY_GRACE_SECONDS = 60.0
# Teams removes and re-adds its tray icon at every launch, so a removal only counts as an
# outage if the icon is not back after this long. The longest gap observed was 0.49 s.
TRAY_RESTART_GRACE_SECONDS = 5.0


class HealthState:
    def __init__(
        self,
        clock: Clock,
        recovery_grace: float = RECOVERY_GRACE_SECONDS,
        tray_restart_grace: float = TRAY_RESTART_GRACE_SECONDS,
    ) -> None:
        self._clock = clock
        self._recovery_grace = recovery_grace
        self._tray_restart_grace = tray_restart_grace
        self._down = False
        self._down_since = 0.0
        self._tray_removed_at: float | None = None

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
        self._tray_removed_at = None

    def note_tray_removed(self) -> None:
        """Record a tray icon removal. A tray icon add before the grace ends cancels it."""
        if self._tray_removed_at is None:
            self._tray_removed_at = self._clock.monotonic()

    def take_tray_removed(self) -> bool:
        """True once if the tray icon was removed and has stayed away past the grace."""
        removed_at = self._tray_removed_at
        if removed_at is None or self._clock.monotonic() - removed_at < self._tray_restart_grace:
            return False
        self._tray_removed_at = None
        return True

    def has_recovered(self, last_activity: float) -> bool:
        """True when the log produced new lines after the shutdown grace period."""
        return self._down and last_activity > self._down_since + self._recovery_grace
