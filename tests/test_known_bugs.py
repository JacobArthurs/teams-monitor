"""Tests that fail on purpose: each one describes behavior the code does not have yet.

Move a test next to the tests for its module once the bug is fixed. If you decide the current
behavior is right, change the test or the docs instead.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest
from helpers import CALL_A, FakeProbe, RecordingNotifier, event, incoming, tray_remove

from teams_monitor import alerts
from teams_monitor.bootstrap import build_monitor
from teams_monitor.config import Settings
from teams_monitor.models import Alert
from teams_monitor.notifiers import CompositeNotifier
from teams_monitor.notifiers.base import Notifier
from teams_monitor.parsing import LineParser
from teams_monitor.rules.incoming_call import IncomingCallRule
from teams_monitor.window import ActiveWindow


@pytest.mark.parametrize("year", ["0001", "9999"])
def test_out_of_range_year_keeps_the_original_text(year: str) -> None:
    """The LogLine comment promises log_ts falls back to the original text if the time is invalid.

    Today astimezone() raises OSError on Windows. Monitor._parse catches it, so the line is lost
    and a traceback is logged.
    """
    ts = f"{year}-06-15T00:00:00.000000+00:00"
    line = LineParser().parse(f"{ts} 0x1 <INFO> hello")
    assert line is not None
    assert line.log_ts == ts


def test_window_with_equal_start_and_end_is_not_silently_almost_never() -> None:
    """Today 08:00-08:00 is active for one instant, which turns off Teams down alerts.

    Either rejecting it or treating it as all day would be reasonable, so both pass.
    """
    try:
        window = ActiveWindow.parse("08:00-08:00")
    except ValueError:
        return
    assert window.contains(time(12, 0))


def test_tray_removal_alerts_soon_after_the_five_second_grace(tmp_path: Path, clock) -> None:
    """The README says Teams down fires when the icon is not re-added within 5 seconds.

    Today the removal is only looked at when the watchdog runs, every 30 seconds by default, so
    the alert can take about 30 seconds and an icon back after 20 seconds cancels it. Correcting
    the README is also a valid fix, in which case change this test to match.
    """
    log = tmp_path / "MSTeams_1.log"
    log.write_text("", encoding="utf-8")
    recorder = RecordingNotifier()
    monitor = build_monitor(
        Settings(log_dir=tmp_path), notifier=recorder, clock=clock, probe=FakeProbe(True)
    )
    monitor.run_once()
    with log.open("a", encoding="utf-8") as handle:
        handle.write(tray_remove() + "\n")

    monitor.run_once()
    for _ in range(6):
        clock.advance(1)
        monitor.run_once()

    assert recorder.kinds == ["teams_down"]


def test_unexpected_error_in_one_sink_does_not_stop_the_next() -> None:
    """The CompositeNotifier docstring promises isolated failures, but only DeliveryError is caught.

    Today any other exception skips every later sink, so a bug in one would lose the webhook alert.
    """

    class BrokenNotifier(Notifier):
        def notify(self, alert: Alert) -> None:
            raise RuntimeError("bug")

    last = RecordingNotifier()
    CompositeNotifier([BrokenNotifier(), last]).notify(alerts.teams_down("x"))
    assert len(last.alerts) == 1


def test_repeated_ring_line_for_one_call_alerts_once() -> None:
    """Today each reportIncomingCall line sends an alert, with no check on the call ID.

    It is not known whether Teams ever logs this twice for one call.
    """
    rule = IncomingCallRule()
    first = rule.on_event(event(incoming(CALL_A, at=0)))
    second = rule.on_event(event(incoming(CALL_A, at=1)))
    assert len(first) + len(second) == 1
