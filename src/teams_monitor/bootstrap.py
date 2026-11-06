"""Composition root: the only module that knows every concrete class."""

from __future__ import annotations

import logging
import socket

from teams_monitor import alerts
from teams_monitor.clock import Clock, SystemClock
from teams_monitor.config import Settings
from teams_monitor.engine import Engine
from teams_monitor.monitor import Monitor
from teams_monitor.notifiers import (
    BackgroundNotifier,
    Notifier,
    NullNotifier,
    UrllibTransport,
    WebhookNotifier,
)
from teams_monitor.rules import (
    IncomingCallRule,
    MissedCallRule,
    NewActivityRule,
    Rule,
    TrayIconRule,
)
from teams_monitor.tailing import LineReader, LogLocator, LogTailer
from teams_monitor.watchdog import ProcessProbe, TasklistProbe, Watchdog

log = logging.getLogger(__name__)


def build_webhook(url: str, clock: Clock) -> WebhookNotifier:
    if url.startswith("http://"):
        log.warning("webhook URL uses plain http, alerts are sent unencrypted")
    return WebhookNotifier(url, socket.gethostname(), clock, UrllibTransport())


def build_notifier(settings: Settings, clock: Clock) -> Notifier:
    if not settings.webhook_url:
        log.warning("no webhook configured, running in dry-run mode (alerts are only logged)")
        return NullNotifier()
    return BackgroundNotifier(
        build_webhook(settings.webhook_url, clock),
        urgent_max_priority=alerts.PRIORITY_MISSED_CALL,
    )


def build_rules(watchdog: Watchdog, suppress_after_missed: float, clock: Clock) -> list[Rule]:
    missed_calls = MissedCallRule()
    return [
        IncomingCallRule(),
        missed_calls,
        NewActivityRule(lambda: missed_calls.last_missed_at, suppress_after_missed, clock),
        TrayIconRule(watchdog),
    ]


def build_monitor(
    settings: Settings,
    notifier: Notifier | None = None,
    clock: Clock | None = None,
    probe: ProcessProbe | None = None,
) -> Monitor:
    """Wire up a Monitor. Notifier, clock and probe can be overridden for tests."""
    clock = clock or SystemClock()
    notifier = notifier or build_notifier(settings, clock)
    if probe is None and settings.process_name:
        probe = TasklistProbe(settings.process_name)
    if not settings.log_dir.is_dir():
        log.warning("Teams log folder not found: %s. Check [teams] log_dir.", settings.log_dir)

    watchdog = Watchdog(
        clock=clock,
        stale_after=settings.stale_minutes * 60,
        probe=probe,
        window=settings.active_window,
    )
    return Monitor(
        tailer=LogTailer(LogLocator(settings.log_dir), LineReader(), settings.from_start),
        engine=Engine(build_rules(watchdog, settings.suppress_after_missed, clock)),
        notifier=notifier,
        watchdog=watchdog,
        clock=clock,
        poll_interval=settings.poll_interval,
        check_interval=settings.check_interval,
    )
