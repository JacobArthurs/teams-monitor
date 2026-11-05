"""Uses real threads, coordinated with events rather than sleeps."""

from __future__ import annotations

import logging
import queue
import threading

import pytest

from teams_monitor.models import Alert, AlertKind
from teams_monitor.notifiers import BackgroundNotifier
from teams_monitor.notifiers.base import DeliveryError, Notifier

WAIT = 5.0


def _alert(name: str, priority: int = 3, kind: AlertKind = AlertKind.NEW_MESSAGE) -> Alert:
    return Alert(kind, priority, name)


class GatedNotifier(Notifier):
    """Blocks on the alert named "gate" until released, and can raise on request."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.delivered: list[str] = []
        self.seen: queue.Queue[str] = queue.Queue()
        self.closed = 0
        self.raises: dict[str, Exception] = {}

    def notify(self, alert: Alert) -> None:
        if alert.text == "gate":
            self.started.set()
            self.release.wait(WAIT)
        if alert.text in self.raises:
            raise self.raises[alert.text]
        self.delivered.append(alert.text)
        self.seen.put(alert.text)

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def inner():
    notifier = GatedNotifier()
    yield notifier
    notifier.release.set()  # never leave a worker thread stuck


def _hold_lane(notifier: BackgroundNotifier, inner: GatedNotifier, priority: int = 3) -> None:
    notifier.notify(_alert("gate", priority))
    assert inner.started.wait(WAIT)


def test_close_delivers_what_is_queued(inner: GatedNotifier) -> None:
    notifier = BackgroundNotifier(inner)
    notifier.notify(_alert("a"))
    notifier.notify(_alert("b"))
    notifier.close()
    assert inner.delivered == ["a", "b"]
    assert inner.closed == 1


def test_lowest_priority_number_goes_first_and_ties_keep_their_order(inner: GatedNotifier) -> None:
    notifier = BackgroundNotifier(inner)
    _hold_lane(notifier, inner)
    notifier.notify(_alert("p4 first", 4))
    notifier.notify(_alert("p3", 3))
    notifier.notify(_alert("p2", 2))
    notifier.notify(_alert("p4 second", 4))
    inner.release.set()
    notifier.close()
    assert inner.delivered == ["gate", "p2", "p3", "p4 first", "p4 second"]


def test_urgent_alert_is_not_blocked_by_a_stuck_normal_one(inner: GatedNotifier) -> None:
    notifier = BackgroundNotifier(inner, urgent_max_priority=1)
    _hold_lane(notifier, inner, priority=4)
    notifier.notify(_alert("urgent", 1))
    assert inner.seen.get(timeout=WAIT) == "urgent"
    inner.release.set()
    notifier.close()


def test_urgent_threshold_is_configurable(inner: GatedNotifier) -> None:
    notifier = BackgroundNotifier(inner, urgent_max_priority=2)
    _hold_lane(notifier, inner, priority=4)
    notifier.notify(_alert("p2", 2))
    assert inner.seen.get(timeout=WAIT) == "p2"
    inner.release.set()
    notifier.close()


def test_full_queue_drops_and_logs(inner: GatedNotifier, caplog) -> None:
    notifier = BackgroundNotifier(inner, max_queue=1)
    _hold_lane(notifier, inner)
    notifier.notify(_alert("queued"))
    with caplog.at_level(logging.ERROR, logger="teams_monitor"):
        notifier.notify(_alert("dropped"))
    assert "queue full, dropping new_message" in caplog.text
    inner.release.set()
    notifier.close()
    assert inner.delivered == ["gate", "queued"]


def test_shutdown_timeout_names_undelivered_alerts(inner: GatedNotifier, caplog) -> None:
    notifier = BackgroundNotifier(inner, join_timeout=0.05)
    notifier.notify(_alert("gate", 3))
    assert inner.started.wait(WAIT)
    notifier.notify(Alert(AlertKind.TEAMS_DOWN, 4, "queued"))
    with caplog.at_level(logging.ERROR, logger="teams_monitor"):
        notifier.close()
    assert "2 alert(s) may not have been delivered: new_message, teams_down" in caplog.text
    assert inner.closed == 1


def test_clean_shutdown_logs_no_error(inner: GatedNotifier, caplog) -> None:
    notifier = BackgroundNotifier(inner)
    notifier.notify(_alert("a"))
    with caplog.at_level(logging.ERROR, logger="teams_monitor"):
        notifier.close()
    assert caplog.records == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (DeliveryError("nope"), "delivery of new_message failed: nope"),
        (RuntimeError("bug"), "unexpected error delivering new_message"),
    ],
)
def test_worker_survives_a_failed_delivery(
    inner: GatedNotifier, caplog, error: Exception, message: str
) -> None:
    inner.raises["bad"] = error
    notifier = BackgroundNotifier(inner)
    notifier.notify(_alert("bad"))
    notifier.notify(_alert("good"))
    notifier.close()
    assert inner.delivered == ["good"]
    assert message in caplog.text
