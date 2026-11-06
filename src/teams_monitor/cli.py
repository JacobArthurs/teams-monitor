from __future__ import annotations

import argparse
import logging
import sys
import threading
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from teams_monitor import __version__, alerts
from teams_monitor.bootstrap import build_monitor, build_webhook
from teams_monitor.clock import SystemClock
from teams_monitor.config import ConfigError, Settings, load_settings, write_example_config
from teams_monitor.fatal import report_without_console
from teams_monitor.lifecycle import install_stop_handlers
from teams_monitor.logging_setup import configure_logging
from teams_monitor.notifiers import DeliveryError

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config.toml")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        report_without_console(f"teams-monitor could not start:\n\n{message}")
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m teams_monitor",
        description="Tail Microsoft Teams logs and send webhook alerts (Windows).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"path to the config file (default: {DEFAULT_CONFIG_PATH} in the current directory)",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="create a starter config file at the --config path and exit",
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="send one test alert to the configured webhook and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.init_config:
        try:
            write_example_config(args.config)
        except ConfigError as exc:
            parser.error(str(exc))
        print(f"Created {args.config.resolve()}. Edit it, then start the monitor.")
        return 0

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        parser.error(str(exc))

    try:
        configure_logging(settings.verbose, settings.log_file)
    except OSError as exc:
        parser.error(f"[logging] file cannot be opened: {exc}")

    if args.test_webhook:
        if not settings.webhook_url:
            parser.error("--test-webhook needs [webhook] url to be set")
        return _test_webhook(settings.webhook_url)

    try:
        _run(settings)
    except Exception:
        log.exception("monitor crashed")
        report_without_console(f"teams-monitor crashed:\n\n{traceback.format_exc()}")
        return 1
    return 0


def _test_webhook(url: str) -> int:
    try:
        build_webhook(url, SystemClock()).notify(alerts.webhook_test())
    except DeliveryError as exc:
        print(f"Webhook test failed: {exc}", file=sys.stderr)
        return 1
    print("Test alert sent. Check that it arrived.")
    return 0


def _run(settings: Settings) -> None:
    stop = threading.Event()
    install_stop_handlers(stop)

    monitor = build_monitor(settings)
    try:
        monitor.run_forever(stop)
    finally:
        monitor.close()
