"""Reads Settings from a TOML config file."""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from teams_monitor.config import DEFAULT_LOG_DIR, ConfigError, Settings
from teams_monitor.window import ActiveWindow


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
            field, convert = SCHEMA[section][key]
            try:
                values[field] = convert(value)
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
