from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from teams_monitor import __version__, cli
from teams_monitor.config import Settings
from teams_monitor.config_loader import load_settings
from teams_monitor.notifiers import HttpTransport, PermanentDeliveryError

SECRET = "s3cret-token"


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
    err = capsys.readouterr().err
    assert "config file not found" in err
    assert "--init-config" in err


def test_init_config_creates_a_loadable_config_and_does_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fail(settings: Settings) -> None:
        raise AssertionError("the monitor must not start")

    monkeypatch.setattr(cli, "_run", fail)
    path = tmp_path / "config.toml"
    assert cli.main(["--init-config", "--config", str(path)]) == 0
    assert str(path) in capsys.readouterr().out
    assert load_settings(path).webhook_url is None


def test_init_config_never_overwrites(config: Path, capsys) -> None:
    config.write_text("# mine\n", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        cli.main(["--init-config", "--config", str(config)])
    assert caught.value.code == 2
    assert "already exists" in capsys.readouterr().err
    assert config.read_text(encoding="utf-8") == "# mine\n"


def test_init_config_reports_an_unwritable_path(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--init-config", "--config", str(tmp_path / "missing" / "config.toml")])
    assert caught.value.code == 2
    assert "cannot create" in capsys.readouterr().err


class _Transport(HttpTransport):
    error: Exception | None = None
    bodies: list[dict] = []

    def post_json(self, url: str, body: bytes) -> None:
        if self.error is not None:
            raise self.error
        type(self).bodies.append(json.loads(body))


@pytest.fixture
def webhook_config(config: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("teams_monitor.bootstrap.UrllibTransport", _Transport)
    monkeypatch.setattr(_Transport, "error", None)
    monkeypatch.setattr(_Transport, "bodies", [])
    monkeypatch.setattr(cli, "_run", lambda settings: pytest.fail("the monitor must not start"))
    config.write_text(f'[webhook]\nurl = "https://x.test/{SECRET}"\n', encoding="utf-8")
    return config


def test_test_webhook_sends_one_alert(webhook_config: Path, no_logging_setup, capsys) -> None:
    assert cli.main(["--test-webhook", "--config", str(webhook_config)]) == 0
    assert [body["alert"] for body in _Transport.bodies] == ["test"]
    out = capsys.readouterr().out
    assert "Test alert sent" in out
    assert SECRET not in out


def test_test_webhook_reports_a_failure(webhook_config: Path, no_logging_setup, capsys) -> None:
    _Transport.error = PermanentDeliveryError("HTTP 404")
    assert cli.main(["--test-webhook", "--config", str(webhook_config)]) == 1
    err = capsys.readouterr().err
    assert "Webhook test failed: HTTP 404" in err
    assert SECRET not in err


def test_test_webhook_needs_a_url(config: Path, no_logging_setup, capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--test-webhook", "--config", str(config)])
    assert caught.value.code == 2
    assert "[webhook] url" in capsys.readouterr().err


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
