from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from teams_monitor.logging_setup import configure_logging


def _logger() -> logging.Logger:
    return logging.getLogger("teams_monitor")


def test_defaults_to_the_console_at_info() -> None:
    configure_logging()
    handlers = _logger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert not isinstance(handlers[0], RotatingFileHandler)
    assert _logger().level == logging.INFO


def test_verbose_enables_debug() -> None:
    configure_logging(verbose=True)
    assert _logger().level == logging.DEBUG


def test_log_file_is_written(tmp_path: Path) -> None:
    path = tmp_path / "monitor.log"
    configure_logging(log_file=path)
    logging.getLogger("teams_monitor.test").info("hello")
    for handler in _logger().handlers:
        handler.flush()
    assert "INFO teams_monitor.test: hello" in path.read_text(encoding="utf-8")


def test_reconfiguring_replaces_the_handler() -> None:
    configure_logging()
    configure_logging()
    assert len(_logger().handlers) == 1


def test_only_the_package_logger_is_configured() -> None:
    root_handlers = list(logging.getLogger().handlers)
    configure_logging()
    assert logging.getLogger().handlers == root_handlers
    assert _logger().propagate is False
