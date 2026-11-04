"""Tracks when the log last produced lines in the expected format."""

from __future__ import annotations

import logging

from teams_monitor.clock import Clock

log = logging.getLogger(__name__)

# Continuation lines are normal, but this many in a row with no parsable line is not.
FORMAT_SUSPECT_LINES = 100


class ActivityTracker:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._last_activity = clock.monotonic()
        self._idle_since = self._last_activity
        self._unrecognized = 0

    @property
    def last_activity(self) -> float:
        return self._last_activity

    @property
    def format_suspect(self) -> bool:
        """True when the log is growing but its recent lines cannot be parsed."""
        return self._unrecognized >= FORMAT_SUSPECT_LINES

    def touch(self) -> None:
        """Record a recognized line."""
        self._last_activity = self._clock.monotonic()
        self._idle_since = self._last_activity
        self._unrecognized = 0

    def note_unrecognized(self, count: int) -> None:
        """Record lines that are not in the expected format. They are not activity."""
        before = self._unrecognized
        self._unrecognized += count
        if before < FORMAT_SUSPECT_LINES <= self._unrecognized:
            log.warning(
                "%d log lines in a row are not in the expected format, so no alerts can fire "
                "from them. Teams may have changed its log format.",
                self._unrecognized,
            )

    def restart_idle(self) -> None:
        """Restart the idle timer without recording activity, so it cannot end an outage."""
        self._idle_since = self._clock.monotonic()

    def idle_seconds(self) -> float:
        return self._clock.monotonic() - self._idle_since
