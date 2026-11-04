"""Graceful shutdown on Ctrl+C, Ctrl+Break and termination signals."""

from __future__ import annotations

import signal
import threading
from types import FrameType


def install_stop_handlers(stop: threading.Event) -> None:
    def handler(signum: int, frame: FrameType | None) -> None:
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, handler)
