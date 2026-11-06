"""Validated runtime settings, and reading them from a TOML config file."""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any
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


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value


def _optional_string(value: Any) -> str | None:
    return _string(value) or None


def _path(value: Any) -> Path:
    return Path(os.path.expandvars(_string(value)))


def _optional_path(value: Any) -> Path | None:
    return _path(value) if _string(value) else None


def _number(value: Any) -> float:
    # bool is a subclass of int, so it must be excluded explicitly.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("must be a number")
    try:
        return float(value)
    except OverflowError:  # a huge integer. Settings rejects anything out of range.
        return math.inf


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("must be true or false")
    return value


def _active_window(value: Any) -> ActiveWindow | None:
    return ActiveWindow.parse(_string(value)) if _string(value) else None


# Every accepted key, as the Settings field it sets and how to read it. Anything else is
# rejected so typos are not silently ignored. Settings holds the defaults, so keys missing
# from the file are simply not passed on.
SCHEMA: dict[str, dict[str, tuple[str, Callable[[Any], Any]]]] = {
    "teams": {
        "log_dir": ("log_dir", _path),
        "process": ("process_name", _optional_string),
    },
    "webhook": {
        "url": ("webhook_url", _optional_string),
    },
    "monitoring": {
        "poll_seconds": ("poll_interval", _number),
        "check_interval_seconds": ("check_interval", _number),
        "stale_minutes": ("stale_minutes", _number),
        "active_hours": ("active_window", _active_window),
        "suppress_after_missed_seconds": ("suppress_after_missed", _number),
    },
    "logging": {
        "file": ("log_file", _optional_path),
        "verbose": ("verbose", _boolean),
    },
    "debug": {
        "from_start": ("from_start", _boolean),
    },
}


def write_example_config(path: Path) -> None:
    """Create a starter config. Never overwrites, because the file holds the user's settings."""
    example = resources.files("teams_monitor").joinpath("config.example.toml").read_bytes()
    try:
        with path.open("xb") as handle:
            handle.write(example)
    except FileExistsError as exc:
        raise ConfigError(f"{path.resolve()} already exists, so it was left unchanged") from exc
    except OSError as exc:
        raise ConfigError(f"cannot create {path}: {exc}") from exc


def load_settings(path: Path) -> Settings:
    values: dict[str, Any] = {"log_dir": _path(DEFAULT_LOG_DIR)}
    for section, content in _read(path).items():
        if section not in SCHEMA:
            raise ConfigError(f"unknown section [{section}]")
        if not isinstance(content, dict):
            raise ConfigError(f"[{section}] must be a table")
        for key, value in content.items():
            if key not in SCHEMA[section]:
                raise ConfigError(f"unknown setting '{key}' in [{section}]")
            setting, convert = SCHEMA[section][key]
            try:
                values[setting] = convert(value)
            except ValueError as exc:
                raise ConfigError(f"[{section}] {key}: {exc}") from exc
    return Settings(**values)


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(
            f"config file not found: {path.resolve()}\n"
            "Add --init-config to this command to create it."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
