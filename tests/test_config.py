from __future__ import annotations

import math
import os
from datetime import time
from pathlib import Path

import pytest

from teams_monitor.config import (
    DEFAULT_LOG_DIR,
    DEFAULT_PROCESS_NAME,
    MAX_TIME_VALUE,
    ConfigError,
    Settings,
    load_settings,
)
from teams_monitor.window import ActiveWindow

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


EXAMPLE_CONFIG = Path(__file__).parents[1] / "src" / "teams_monitor" / "config.example.toml"


@pytest.fixture
def load(tmp_path: Path):
    def _load(text: str) -> Settings:
        path = tmp_path / "config.toml"
        path.write_text(text, encoding="utf-8")
        return load_settings(path)

    return _load


def test_empty_file_gives_the_defaults(load) -> None:
    settings = load("")
    assert settings == Settings(log_dir=Path(os.path.expandvars(DEFAULT_LOG_DIR)))
    assert settings.process_name == DEFAULT_PROCESS_NAME
    assert settings.webhook_url is None


def test_example_config_loads_and_documents_the_real_defaults() -> None:
    assert load_settings(EXAMPLE_CONFIG) == Settings(
        log_dir=Path(os.path.expandvars(DEFAULT_LOG_DIR))
    )


def test_every_setting_is_read(load, tmp_path: Path) -> None:
    settings = load(
        f"""
        [teams]
        log_dir = '{tmp_path}'
        process = "other.exe"
        [webhook]
        url = "https://hooks.example.com/x"
        [monitoring]
        poll_seconds = 1
        check_interval_seconds = 2
        stale_minutes = 3
        active_hours = "08:00-18:00"
        suppress_after_missed_seconds = 0
        [logging]
        file = '{tmp_path / "monitor.log"}'
        verbose = true
        [debug]
        from_start = true
        """
    )
    assert settings == Settings(
        log_dir=tmp_path,
        process_name="other.exe",
        webhook_url="https://hooks.example.com/x",
        poll_interval=1.0,
        check_interval=2.0,
        stale_minutes=3.0,
        active_window=ActiveWindow(time(8), time(18)),
        suppress_after_missed=0.0,
        log_file=tmp_path / "monitor.log",
        verbose=True,
        from_start=True,
    )


def test_environment_variables_are_expanded(load, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TM_TEST_DIR", "C:\\somewhere")
    settings = load(
        """
        [teams]
        log_dir = '%TM_TEST_DIR%\\logs'
        [logging]
        file = '%TM_TEST_DIR%\\monitor.log'
        """
    )
    assert settings.log_dir == Path("C:\\somewhere\\logs")
    assert settings.log_file == Path("C:\\somewhere\\monitor.log")


def test_empty_strings_mean_unset(load) -> None:
    settings = load(
        """
        [teams]
        process = ""
        [webhook]
        url = ""
        [monitoring]
        active_hours = ""
        [logging]
        file = ""
        """
    )
    assert settings.process_name is None
    assert settings.webhook_url is None
    assert settings.active_window is None
    assert settings.log_file is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[nope]\n", "unknown section"),
        ("[teams]\ntypo = 1\n", "unknown setting 'typo'"),
        ('teams = "x"\n', r"\[teams\] must be a table"),
        ("[teams]\nprocess = 1\n", "must be a string"),
        ("[webhook]\nurl = 1\n", "must be a string"),
        ('[monitoring]\npoll_seconds = "1"\n', "must be a number"),
        ("[monitoring]\npoll_seconds = true\n", "must be a number"),
        ("[monitoring]\nstale_minutes = nan\n", "stale minutes must be"),
        ("[monitoring]\nstale_minutes = inf\n", "stale minutes must be"),
        (f"[monitoring]\nstale_minutes = {10**400}\n", "stale minutes must be"),
        ("[monitoring]\nstale_minutes = 0\n", "stale minutes must be"),
        ('[monitoring]\nactive_hours = "soon"\n', "active_hours"),
        ('[monitoring]\nactive_hours = "08:00-08:00"\n', "start and end must differ"),
        ('[logging]\nverbose = "yes"\n', "must be true or false"),
        ("[debug]\nfrom_start = 1\n", "must be true or false"),
        ("this is not toml\n", "not valid TOML"),
    ],
)
def test_bad_config_is_rejected(load, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load(text)


def test_bad_webhook_url_does_not_leak_it(load) -> None:
    with pytest.raises(ConfigError) as caught:
        load('[webhook]\nurl = "ftp://hooks.example.com/s3cret-token"\n')
    assert "s3cret-token" not in str(caught.value)


def test_missing_file_explains_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config file not found"):
        load_settings(tmp_path / "missing.toml")


def test_unreadable_path_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_settings(tmp_path)
