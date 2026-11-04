"""Reads Settings from a TOML config file."""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from teams_monitor.config import (
    DEFAULT_LOG_DIR,
    DEFAULT_PROCESS_NAME,
    ConfigError,
    Settings,
)
from teams_monitor.watchdog import ActiveWindow

# Every accepted section and key. Anything else is rejected so typos are not silently ignored.
SCHEMA: dict[str, frozenset[str]] = {
    "teams": frozenset({"log_dir", "process"}),
    "webhook": frozenset({"url"}),
    "monitoring": frozenset(
        {
            "poll_seconds",
            "check_interval_seconds",
            "stale_minutes",
            "active_hours",
            "suppress_after_missed_seconds",
        }
    ),
    "logging": frozenset({"file", "verbose"}),
    "debug": frozenset({"from_start"}),
}


def load_settings(path: Path) -> Settings:
    data = _read(path)
    _reject_unknown(data)

    teams = _table(data, "teams")
    webhook = _table(data, "webhook")
    monitoring = _table(data, "monitoring")
    logging_ = _table(data, "logging")
    debug = _table(data, "debug")

    active_hours = _string(monitoring, "monitoring", "active_hours", "")
    log_file = _string(logging_, "logging", "file", "")
    try:
        active_window = ActiveWindow.parse(active_hours) if active_hours else None
    except ValueError as exc:
        raise ConfigError(f"[monitoring] active_hours: {exc}") from exc

    return Settings(
        log_dir=Path(os.path.expandvars(_string(teams, "teams", "log_dir", DEFAULT_LOG_DIR))),
        process_name=_string(teams, "teams", "process", DEFAULT_PROCESS_NAME) or None,
        webhook_url=_string(webhook, "webhook", "url", "") or None,
        poll_interval=_number(monitoring, "monitoring", "poll_seconds", 0.5),
        check_interval=_number(monitoring, "monitoring", "check_interval_seconds", 30.0),
        stale_minutes=_number(monitoring, "monitoring", "stale_minutes", 10.0),
        active_window=active_window,
        suppress_after_missed=_number(
            monitoring, "monitoring", "suppress_after_missed_seconds", 3.0
        ),
        log_file=Path(os.path.expandvars(log_file)) if log_file else None,
        verbose=_boolean(logging_, "logging", "verbose", False),
        from_start=_boolean(debug, "debug", "from_start", False),
    )


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(
            f"config file not found: {path.resolve()}\n"
            "Copy config.example.toml to config.toml and edit it."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc


def _reject_unknown(data: Mapping[str, Any]) -> None:
    for section, content in data.items():
        if section not in SCHEMA:
            raise ConfigError(f"unknown section [{section}]")
        if isinstance(content, dict):
            for key in content:
                if key not in SCHEMA[section]:
                    raise ConfigError(f"unknown setting '{key}' in [{section}]")


def _table(data: Mapping[str, Any], section: str) -> Mapping[str, Any]:
    value = data.get(section, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{section}] must be a table")
    return value


def _string(table: Mapping[str, Any], section: str, key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"[{section}] {key} must be a string")
    return value


def _number(table: Mapping[str, Any], section: str, key: str, default: float) -> float:
    value = table.get(key, default)
    # bool is a subclass of int, so it must be excluded explicitly.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"[{section}] {key} must be a number")
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    # TOML allows nan and inf, and a huge integer overflows float.
    if not math.isfinite(number):
        raise ConfigError(f"[{section}] {key} must be a finite number")
    return number


def _boolean(table: Mapping[str, Any], section: str, key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"[{section}] {key} must be true or false")
    return value
