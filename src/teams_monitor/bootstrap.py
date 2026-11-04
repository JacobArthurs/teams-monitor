"""Composition root: the only module that knows every concrete class."""

from __future__ import annotations

import logging
import socket
from datetime import timedelta

from teams_monitor import alerts
from teams_monitor.clock import Clock, SystemClock
from teams_monitor.config import Settings
from teams_monitor.engine import Engine
from teams_monitor.health import HealthState
from teams_monitor.monitor import Monitor
from teams_monitor.notifiers import (
    BackgroundNotifier,
    CompositeNotifier,
    LogNotifier,
    Notifier,
    PayloadBuilder,
    UrllibTransport,
    WebhookNotifier,
)
from teams_monitor.parsing import LineParser
from teams_monitor.rules import build_default_rules
from teams_monitor.signals import SignalMatcher
from teams_monitor.tailing import LineReader, LogLocator, LogTailer
from teams_monitor.watchdog import ActivityTracker, ProcessProbe, TasklistProbe, Watchdog

log = logging.getLogger(__name__)


def build_notifier(settings: Settings, clock: Clock) -> Notifier:
    sinks: list[Notifier] = [LogNotifier()]
    if settings.webhook_url:
        sinks.append(
            WebhookNotifier(
                settings.webhook_url,
                PayloadBuilder(socket.gethostname(), clock),
                UrllibTransport(),
            )
        )
        if settings.webhook_url.startswith("http://"):
            log.warning("webhook URL uses plain http, alerts are sent unencrypted")
    else:
        log.warning("no webhook configured, running in dry-run mode (alerts are only logged)")
    return BackgroundNotifier(
        CompositeNotifier(sinks), urgent_max_priority=alerts.PRIORITY_MISSED_CALL
    )


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

    window = settings.active_window
    now = clock.now

    def in_active_hours() -> bool:
        return window is None or window.contains(now().time())

    health = HealthState(clock)
    activity = ActivityTracker(clock)
    engine = Engine(
        LineParser(),
        SignalMatcher(),
        build_default_rules(
            health, timedelta(seconds=settings.suppress_after_missed), in_active_hours
        ),
    )
    tailer = LogTailer(LogLocator(settings.log_dir), LineReader(), settings.from_start)
    watchdog = Watchdog(
        health=health,
        activity=activity,
        clock=clock,
        stale_after=settings.stale_minutes * 60,
        probe=probe,
        window=settings.active_window,
    )
    return Monitor(
        tailer=tailer,
        engine=engine,
        notifier=notifier,
        watchdog=watchdog,
        activity=activity,
        clock=clock,
        poll_interval=settings.poll_interval,
        check_interval=settings.check_interval,
    )
