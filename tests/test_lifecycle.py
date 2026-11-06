from __future__ import annotations

import signal
import threading

import pytest

from teams_monitor.lifecycle import install_stop_handlers


def test_stop_signals_set_the_event(monkeypatch: pytest.MonkeyPatch) -> None:
    installed = {}
    monkeypatch.setattr(
        signal, "signal", lambda signum, handler: installed.update({signum: handler})
    )
    stop = threading.Event()

    install_stop_handlers(stop)

    assert {signal.SIGINT, signal.SIGTERM} <= set(installed)
    assert stop.is_set() is False
    installed[signal.SIGINT](signal.SIGINT, None)
    assert stop.is_set() is True
