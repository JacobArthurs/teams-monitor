"""Validated runtime settings."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from teams_monitor.window import ActiveWindow

DEFAULT_LOG_DIR = r"%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs"
DEFAULT_PROCESS_NAME = "ms-teams.exe"
# Upper limit for time settings. Far larger values overflow the timers they are passed to.
MAX_TIME_VALUE = 1_000_000.0


class ConfigError(ValueError):
    """Settings are invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    log_dir: Path
    # The URL is a secret, so it is excluded from repr and never logged.
    webhook_url: str | None = field(default=None, repr=False)
    poll_interval: float = 0.5
    check_interval: float = 30.0
    stale_minutes: float = 10.0
    process_name: str | None = DEFAULT_PROCESS_NAME
    active_window: ActiveWindow | None = None
    suppress_after_missed: float = 3.0
    from_start: bool = False
    log_file: Path | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        _check_time("poll interval", self.poll_interval)
        _check_time("check interval", self.check_interval)
        _check_time("stale minutes", self.stale_minutes)
        _check_time("suppress window", self.suppress_after_missed, allow_zero=True)
        if self.webhook_url is not None:
            _check_webhook_url(self.webhook_url)


def _check_time(label: str, value: float, allow_zero: bool = False) -> None:
    # The comparisons are written so that nan fails them too.
    in_range = 0 <= value <= MAX_TIME_VALUE if allow_zero else 0 < value <= MAX_TIME_VALUE
    if not (in_range and math.isfinite(value)):
        lowest = "at least 0" if allow_zero else "greater than 0"
        raise ConfigError(f"{label} must be a number {lowest} and at most {MAX_TIME_VALUE:g}")


def _check_webhook_url(url: str) -> None:
    """Reject anything that would only fail when the first alert is sent.

    Error messages never quote the URL because it is a secret.
    """
    if not url.isascii() or any(char <= " " or char == "\x7f" for char in url):
        raise ConfigError("webhook URL must not contain spaces or control or non-ASCII characters")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        parsed.port  # noqa: B018 - reading it validates the port
    except ValueError:
        raise ConfigError("webhook URL is malformed (check the host and port)") from None
    if parsed.scheme not in ("http", "https") or not hostname:
        raise ConfigError("webhook URL must be an absolute http or https URL")
