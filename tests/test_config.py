from __future__ import annotations

import math
from pathlib import Path

import pytest

from teams_monitor.config import MAX_TIME_VALUE, ConfigError, Settings

SECRET = "s3cret-token"
LOG_DIR = Path("logs")


@pytest.mark.parametrize("field", ["poll_interval", "check_interval", "stale_minutes"])
@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf, MAX_TIME_VALUE + 1])
def test_time_settings_reject(field: str, value: float) -> None:
    with pytest.raises(ConfigError):
        Settings(log_dir=LOG_DIR, **{field: value})


@pytest.mark.parametrize("field", ["poll_interval", "check_interval", "stale_minutes"])
@pytest.mark.parametrize("value", [0.001, MAX_TIME_VALUE])
def test_time_settings_accept(field: str, value: float) -> None:
    assert getattr(Settings(log_dir=LOG_DIR, **{field: value}), field) == value


@pytest.mark.parametrize("value", [0, MAX_TIME_VALUE])
def test_suppress_window_accepts_zero_and_the_maximum(value: float) -> None:
    assert Settings(log_dir=LOG_DIR, suppress_after_missed=value).suppress_after_missed == value


@pytest.mark.parametrize("value", [-1, math.nan, math.inf, MAX_TIME_VALUE + 1])
def test_suppress_window_rejects(value: float) -> None:
    with pytest.raises(ConfigError):
        Settings(log_dir=LOG_DIR, suppress_after_missed=value)


@pytest.mark.parametrize(
    "url",
    [
        f"https://hooks.example.com/{SECRET}",
        f"http://hooks.example.com:8080/{SECRET}",
        f"https://127.0.0.1/{SECRET}?x=1",
    ],
)
def test_valid_webhook_urls(url: str) -> None:
    assert Settings(log_dir=LOG_DIR, webhook_url=url).webhook_url == url


@pytest.mark.parametrize(
    "url",
    [
        f"ftp://hooks.example.com/{SECRET}",
        f"file:///{SECRET}",
        f"hooks.example.com/{SECRET}",
        f"https:///{SECRET}",
        f"https://hooks.example.com/{SECRET} ",
        f"https://hooks.example.com/{SECRET}\n",
        f"https://hooks.example.com/{SECRET}\x7f",
        f"https://hooks.example.com/{SECRET}é",
        f"https://hooks.example.com:notaport/{SECRET}",
        f"https://[broken/{SECRET}",
    ],
)
def test_invalid_webhook_urls_are_rejected_without_quoting_them(url: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings(log_dir=LOG_DIR, webhook_url=url)
    assert SECRET not in str(caught.value)


def test_repr_hides_the_webhook_url() -> None:
    settings = Settings(log_dir=LOG_DIR, webhook_url=f"https://hooks.example.com/{SECRET}")
    assert SECRET not in repr(settings)
