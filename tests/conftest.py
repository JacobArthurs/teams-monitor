from __future__ import annotations

import logging

import pytest
from helpers import FakeClock, RecordingNotifier


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def recorder() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture(autouse=True)
def restore_package_logger():
    """configure_logging sets propagate=False, which would silently break caplog afterwards."""
    logger = logging.getLogger("teams_monitor")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    yield
    for handler in list(logger.handlers):
        if handler not in handlers:
            logger.removeHandler(handler)
            handler.close()
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.fixture(autouse=True)
def no_real_message_box(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test must never open a real Windows dialog, which would hang the run."""
    monkeypatch.setattr("teams_monitor.fatal._show_message_box", lambda text: None)
