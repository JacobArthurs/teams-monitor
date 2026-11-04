"""Runs a notifier on background threads so slow delivery never stalls log tailing.

Urgent alerts get their own lane and thread, so one never waits behind a less urgent
alert that is stuck retrying. Within a lane, the lowest priority number goes first and
equal priorities keep their order.
"""

from __future__ import annotations

import itertools
import logging
import math
import queue
import threading
import time

from teams_monitor.models import Alert
from teams_monitor.notifiers.base import DeliveryError, Notifier

log = logging.getLogger(__name__)


class _Lane:
    def __init__(self, name: str, inner: Notifier, max_queue: int) -> None:
        self._inner = inner
        self._max_queue = max_queue
        # None is the stop marker. Its infinite priority sorts it after every queued alert.
        self._queue: queue.PriorityQueue[tuple[float, int, Alert | None]] = queue.PriorityQueue()
        self._order = itertools.count()
        self._in_flight: Alert | None = None
        self._thread = threading.Thread(target=self._run, name=f"notifier-{name}", daemon=True)
        self._thread.start()

    def submit(self, alert: Alert) -> bool:
        if self._queue.qsize() >= self._max_queue:
            return False
        self._queue.put((alert.priority, next(self._order), alert))
        return True

    def request_stop(self) -> None:
        self._queue.put((math.inf, next(self._order), None))

    def join(self, timeout: float) -> None:
        self._thread.join(timeout=timeout)

    def abandon(self) -> list[Alert]:
        """Discard what is left after a timed out join, returning the alerts affected."""
        if not self._thread.is_alive():
            return []
        unfinished = [self._in_flight] if self._in_flight is not None else []
        try:
            while True:
                _, _, alert = self._queue.get_nowait()
                if alert is not None:
                    unfinished.append(alert)
        except queue.Empty:
            pass
        self.request_stop()
        return unfinished

    def _run(self) -> None:
        while True:
            _, _, alert = self._queue.get()
            if alert is None:
                return
            self._in_flight = alert
            try:
                self._inner.notify(alert)
            except DeliveryError as exc:
                log.error("delivery of %s failed: %s", alert.kind.value, exc)
            except Exception:
                log.exception("unexpected error delivering %s", alert.kind.value)
            finally:
                self._in_flight = None


class BackgroundNotifier(Notifier):
    def __init__(
        self,
        inner: Notifier,
        urgent_max_priority: int = 1,
        max_queue: int = 1000,
        join_timeout: float = 15.0,
    ) -> None:
        self._inner = inner
        self._urgent_max_priority = urgent_max_priority
        self._join_timeout = join_timeout
        self._urgent = _Lane("urgent", inner, max_queue)
        self._normal = _Lane("normal", inner, max_queue)

    def notify(self, alert: Alert) -> None:
        lane = self._urgent if alert.priority <= self._urgent_max_priority else self._normal
        if not lane.submit(alert):
            log.error("notification queue full, dropping %s", alert.kind.value)

    def close(self) -> None:
        """Deliver what is queued, then stop. Waits at most join_timeout seconds in total."""
        lanes = (self._urgent, self._normal)
        for lane in lanes:
            lane.request_stop()
        deadline = time.monotonic() + self._join_timeout
        for lane in lanes:
            lane.join(max(deadline - time.monotonic(), 0.0))

        unfinished = [alert.kind.value for lane in lanes for alert in lane.abandon()]
        if unfinished:
            log.error(
                "shutdown timed out, %d alert(s) may not have been delivered: %s",
                len(unfinished),
                ", ".join(unfinished),
            )
        self._inner.close()
