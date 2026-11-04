"""The run loop: poll the log, run lines through the engine, dispatch alerts."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Sequence

from teams_monitor.clock import Clock
from teams_monitor.engine import Engine
from teams_monitor.models import Alert, LogLine
from teams_monitor.notifiers import Notifier
from teams_monitor.tailing import LogTailer
from teams_monitor.watchdog import ActivityTracker, Watchdog

log = logging.getLogger(__name__)

# A gap this long between polls means the machine slept, or the monitor could not run.
# It sits well above the longest normal iteration, a tasklist call that times out at 10s.
MIN_SUSPEND_GAP_SECONDS = 60.0


class Monitor:
    def __init__(
        self,
        tailer: LogTailer,
        engine: Engine,
        notifier: Notifier,
        watchdog: Watchdog,
        activity: ActivityTracker,
        clock: Clock,
        poll_interval: float,
        check_interval: float,
    ) -> None:
        self._tailer = tailer
        self._engine = engine
        self._notifier = notifier
        self._watchdog = watchdog
        self._activity = activity
        self._clock = clock
        self._poll_interval = poll_interval
        self._check_interval = check_interval
        self._suspend_gap = max(MIN_SUSPEND_GAP_SECONDS, 4 * poll_interval)
        self._last_check = clock.monotonic()
        self._last_iteration = self._last_check

    def run_once(self) -> None:
        """One iteration: read new lines, then run the watchdog if it is due."""
        self._handle_suspend()

        lines = self._tailer.poll()
        if lines:
            self._process(lines)

        now = self._clock.monotonic()
        if now - self._last_check >= self._check_interval:
            self._last_check = now
            self._dispatch(self._watchdog.check())

    def run_forever(self, stop: threading.Event) -> None:
        log.info("monitor started")
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("monitor iteration failed")
            stop.wait(self._poll_interval)
        log.info("monitor stopping")

    def close(self) -> None:
        self._notifier.close()

    def _handle_suspend(self) -> None:
        """After sleep, give Teams a full stale period to write again before judging it."""
        now = self._clock.monotonic()
        gap = now - self._last_iteration
        self._last_iteration = now
        if gap > self._suspend_gap:
            log.info("no poll for %.0f s (system sleep?), restarting the stale timer", gap)
            self._activity.restart_idle()
            self._last_check = now

    def _process(self, raw_lines: Sequence[str]) -> None:
        parsed: list[LogLine] = []
        unrecognized = 0
        for raw in raw_lines:
            if not raw.strip():
                continue
            line = self._parse(raw)
            if line is None:
                unrecognized += 1
            else:
                parsed.append(line)

        # Only recognized lines count as activity, so a changed log format ends in an alert.
        # Touch before routing so a down line cannot count as later activity.
        if parsed:
            self._activity.touch()
        else:
            self._activity.note_unrecognized(unrecognized)

        for line in parsed:
            try:
                self._dispatch(self._engine.route(line))
            except Exception:
                log.exception("failed to process a log line, continuing with the next one")

    def _parse(self, raw: str) -> LogLine | None:
        try:
            return self._engine.parse(raw)
        except Exception:
            log.exception("failed to parse a log line, continuing with the next one")
            return None

    def _dispatch(self, alerts: Iterable[Alert]) -> None:
        for alert in alerts:
            self._notifier.notify(alert)
