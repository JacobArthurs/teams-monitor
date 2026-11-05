from __future__ import annotations

import logging

from helpers import RecordingNotifier

from teams_monitor import alerts
from teams_monitor.models import Alert
from teams_monitor.notifiers import CompositeNotifier, LogNotifier
from teams_monitor.notifiers.base import DeliveryError, Notifier


class FailingNotifier(Notifier):
    def notify(self, alert: Alert) -> None:
        raise DeliveryError("nope")


def test_every_sink_receives_the_alert() -> None:
    first, second = RecordingNotifier(), RecordingNotifier()
    alert = alerts.teams_down("x")
    CompositeNotifier([first, second]).notify(alert)
    assert first.alerts == [alert]
    assert second.alerts == [alert]


def test_delivery_error_does_not_stop_the_next_sink(caplog) -> None:
    last = RecordingNotifier()
    CompositeNotifier([FailingNotifier(), last]).notify(alerts.teams_down("x"))
    assert len(last.alerts) == 1
    assert "FailingNotifier failed to deliver teams_down: nope" in caplog.text


def test_unexpected_error_does_not_stop_the_next_sink(caplog) -> None:
    class BrokenNotifier(Notifier):
        def notify(self, alert: Alert) -> None:
            raise RuntimeError("bug")

    last = RecordingNotifier()
    CompositeNotifier([BrokenNotifier(), last]).notify(alerts.teams_down("x"))
    assert len(last.alerts) == 1
    assert "unexpected error in BrokenNotifier delivering teams_down" in caplog.text


def test_close_reaches_every_sink() -> None:
    first, second = RecordingNotifier(), RecordingNotifier()
    CompositeNotifier([first, second]).close()
    assert (first.closed, second.closed) == (1, 1)


def test_log_notifier_logs_the_alert(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_monitor"):
        LogNotifier().notify(alerts.incoming_call("id", "ts"))
    assert "ALERT incoming_call p1: Incoming call" in caplog.text
