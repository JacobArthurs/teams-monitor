from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

from teams_monitor import alerts
from teams_monitor.clock import Clock
from teams_monitor.engine import Engine
from teams_monitor.models import Alert
from teams_monitor.notifiers import Notifier
from teams_monitor.tailing import LogTailer
from teams_monitor.watchdog import Watchdog

log = logging.getLogger(__name__)

# A gap this long between polls means the machine slept, or the monitor could not run.
# It sits well above the longest normal iteration, a tasklist call that times out at 10s.
MIN_SUSPEND_GAP_SECONDS = 60.0
FAILURE_ALERT_THRESHOLD = 5
# Stays below the suspend gap, so waiting after a failure never looks like system sleep.
MAX_FAILURE_DELAY_SECONDS = 30.0


class Monitor:
    def __init__(
        self,
        tailer: LogTailer,
        engine: Engine,
        notifier: Notifier,
        watchdog: Watchdog,
        clock: Clock,
        poll_interval: float,
        check_interval: float,
    ) -> None:
        self._tailer = tailer
        self._engine = engine
        self._notifier = notifier
        self._watchdog = watchdog
        self._clock = clock
        self._poll_interval = poll_interval
        self._check_interval = check_interval
        self._suspend_gap = max(MIN_SUSPEND_GAP_SECONDS, 4 * poll_interval)
        self._last_check = clock.monotonic()
        self._last_iteration = self._last_check
        self._restored = False

    def run_once(self) -> None:
        self._handle_suspend()
        if not self._restored:
            self._restore()

        lines = self._tailer.poll()
        if lines:
            result = self._engine.process(lines)
            self._watchdog.note_lines(result.recognized, result.unrecognized)
            self._dispatch(result.alerts)
        self._dispatch(self._engine.tick())
        self._dispatch(self._watchdog.check_tray())

        now = self._clock.monotonic()
        if now - self._last_check >= self._check_interval:
            self._last_check = now
            self._dispatch(self._watchdog.check())

    def run_forever(self, stop: threading.Event) -> None:
        log.info("monitor started")
        failures = 0
        delay = self._poll_interval
        while not stop.is_set():
            try:
                self.run_once()
                failures = 0
                delay = self._poll_interval
            except Exception:
                failures += 1
                log.exception("monitor iteration failed (%d in a row)", failures)
                if failures == FAILURE_ALERT_THRESHOLD:
                    self._dispatch([alerts.monitor_error(failures)])
                delay = max(self._poll_interval, min(delay * 2, MAX_FAILURE_DELAY_SECONDS))
            stop.wait(delay)
        log.info("monitor stopping")

    def close(self) -> None:
        self._notifier.close()

    def _restore(self) -> None:
        self._restored = True
        try:
            self._engine.restore(self._tailer.history())
        except Exception:
            log.exception("failed to read the existing log, continuing without it")

    def _handle_suspend(self) -> None:
        now = self._clock.monotonic()
        gap = now - self._last_iteration
        self._last_iteration = now
        if gap > self._suspend_gap:
            log.info("no poll for %.0f s (system sleep?), restarting the stale timer", gap)
            self._watchdog.note_resume()
            self._last_check = now

    def _dispatch(self, pending: Iterable[Alert]) -> None:
        for alert in pending:
            # Logged here, not on a delivery thread, so a retrying alert cannot delay this line.
            log.info("ALERT %s p%d: %s", alert.kind.value, alert.priority, alert.text)
            try:
                self._notifier.notify(alert)
            except Exception:
                log.exception("failed to dispatch %s", alert.kind.value)
