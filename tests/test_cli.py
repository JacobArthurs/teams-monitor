from __future__ import annotations

import threading
from pathlib import Path

import pytest

from teams_monitor import __version__, cli
from teams_monitor.config import Settings


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture
def no_logging_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "configure_logging", lambda verbose, log_file: None)


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--version"])
    assert caught.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_missing_config_exits_with_2(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--config", str(tmp_path / "missing.toml")])
    assert caught.value.code == 2
    assert "config file not found" in capsys.readouterr().err


def test_unknown_flag_exits_with_2() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--nope"])
    assert caught.value.code == 2


def test_log_file_that_cannot_be_opened_exits_with_2(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fail(verbose: bool, log_file: Path | None) -> None:
        raise OSError("denied")

    monkeypatch.setattr(cli, "configure_logging", fail)
    with pytest.raises(SystemExit) as caught:
        cli.main(["--config", str(config)])
    assert caught.value.code == 2
    assert "[logging] file cannot be opened" in capsys.readouterr().err


def test_clean_run_returns_0(config: Path, monkeypatch, no_logging_setup) -> None:
    seen: list[Settings] = []
    monkeypatch.setattr(cli, "_run", seen.append)
    assert cli.main(["--config", str(config)]) == 0
    assert len(seen) == 1


def test_crash_returns_1(config: Path, monkeypatch, no_logging_setup, caplog) -> None:
    def crash(settings: Settings) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(cli, "_run", crash)
    assert cli.main(["--config", str(config)]) == 1
    assert "monitor crashed" in caplog.text


def test_run_closes_the_monitor_even_if_it_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMonitor:
        closed = False

        def run_forever(self, stop: threading.Event) -> None:
            raise RuntimeError("bug")

        def close(self) -> None:
            self.closed = True

    monitor = FakeMonitor()
    monkeypatch.setattr(cli, "install_stop_handlers", lambda stop: None)
    monkeypatch.setattr(cli, "build_monitor", lambda settings: monitor)
    with pytest.raises(RuntimeError):
        cli._run(Settings(log_dir=Path("logs")))
    assert monitor.closed is True
