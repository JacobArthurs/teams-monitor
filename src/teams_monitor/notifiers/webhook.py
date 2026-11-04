"""Webhook notifier with retry on transient failures."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence

from teams_monitor.models import Alert
from teams_monitor.notifiers.base import Notifier, TransientDeliveryError
from teams_monitor.notifiers.http import HttpTransport
from teams_monitor.notifiers.payload import PayloadBuilder

log = logging.getLogger(__name__)

DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0)
# Honor Retry-After up to this long, so a server cannot hold up later alerts indefinitely.
MAX_RETRY_AFTER_SECONDS = 30.0


class WebhookNotifier(Notifier):
    def __init__(
        self,
        url: str,
        payloads: PayloadBuilder,
        transport: HttpTransport,
        retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = url
        self._payloads = payloads
        self._transport = transport
        self._retry_delays = tuple(retry_delays)
        self._sleep = sleep

    def notify(self, alert: Alert) -> None:
        body = json.dumps(self._payloads.build(alert)).encode("utf-8")
        attempts = len(self._retry_delays) + 1
        for attempt in range(attempts):
            try:
                self._transport.post_json(self._url, body)
                return
            except TransientDeliveryError as exc:
                if attempt == attempts - 1:
                    raise
                delay = self._retry_delays[attempt]
                if exc.retry_after is not None:
                    delay = max(delay, min(exc.retry_after, MAX_RETRY_AFTER_SECONDS))
                log.warning(
                    "webhook attempt %d failed (%s), retrying in %gs", attempt + 1, exc, delay
                )
                self._sleep(delay)
