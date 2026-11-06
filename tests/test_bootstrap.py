from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest
from helpers import FakeProbe

from teams_monitor import alerts
from teams_monitor.bootstrap import build_monitor, build_notifier
from teams_monitor.config import Settings
from teams_monitor.notifiers import NullNotifier, PermanentDeliveryError
from teams_monitor.notifiers.transport import HttpTransport

WAIT = 5.0


class RecordingTransport(HttpTransport):
    instances: list[RecordingTransport] = []

    def __init__(self) -> None:
        self.bodies: list[dict] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.missed_call_sent = threading.Event()
        RecordingTransport.instances.append(self)

    def post_json(self, url: str, body: bytes) -> None:
        payload = json.loads(body)
        if payload["alert"] == "teams_down":
            self.started.set()
            self.release.wait(WAIT)
        if payload["alert"] == "missed_call":
            self.missed_call_sent.set()
        self.bodies.append(payload)


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    RecordingTransport.instances = []
    monkeypatch.setattr("teams_monitor.bootstrap.UrllibTransport", RecordingTransport)
    yield RecordingTransport
    for instance in RecordingTransport.instances:
        instance.release.set()


def test_no_webhook_is_a_dry_run(transport, clock, tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="teams_monitor"):
        notifier = build_notifier(Settings(log_dir=tmp_path), clock)
    assert "dry-run" in caplog.text
    assert transport.instances == []
    assert isinstance(notifier, NullNotifier)
    notifier.close()


def test_failed_delivery_logs_the_message_the_readme_documents(
    monkeypatch: pytest.MonkeyPatch, clock, tmp_path: Path, caplog
) -> None:
    class RejectingTransport(HttpTransport):
        def post_json(self, url: str, body: bytes) -> None:
            raise PermanentDeliveryError("HTTP 404")

    monkeypatch.setattr("teams_monitor.bootstrap.UrllibTransport", RejectingTransport)
    notifier = build_notifier(Settings(log_dir=tmp_path, webhook_url="https://x.test/"), clock)
    notifier.notify(alerts.incoming_call("id", "ts"))
    notifier.close()
    assert "delivery of incoming_call failed: HTTP 404" in caplog.text


def test_plain_http_warns(transport, clock, tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="teams_monitor"):
        notifier = build_notifier(Settings(log_dir=tmp_path, webhook_url="http://x.test/"), clock)
    assert "unencrypted" in caplog.text
    notifier.close()


def test_https_does_not_warn(transport, clock, tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="teams_monitor"):
        notifier = build_notifier(Settings(log_dir=tmp_path, webhook_url="https://x.test/"), clock)
    assert caplog.records == []
    notifier.close()


def test_alert_reaches_the_webhook(transport, clock, tmp_path: Path) -> None:
    notifier = build_notifier(Settings(log_dir=tmp_path, webhook_url="https://x.test/"), clock)
    notifier.notify(alerts.incoming_call("id", "ts"))
    notifier.close()
    assert [body["alert"] for body in transport.instances[0].bodies] == ["incoming_call"]


def test_missed_call_does_not_wait_behind_a_stuck_outage_alert(
    transport, clock, tmp_path: Path
) -> None:
    notifier = build_notifier(Settings(log_dir=tmp_path, webhook_url="https://x.test/"), clock)
    instance = transport.instances[0]
    notifier.notify(alerts.teams_down("x"))
    assert instance.started.wait(WAIT)
    notifier.notify(alerts.missed_call("id", "ts"))
    assert instance.missed_call_sent.wait(WAIT)
    instance.release.set()
    notifier.close()


def test_missing_log_folder_warns(recorder, clock, tmp_path: Path, caplog) -> None:
    settings = Settings(log_dir=tmp_path / "missing")
    with caplog.at_level(logging.WARNING, logger="teams_monitor"):
        build_monitor(settings, notifier=recorder, clock=clock, probe=FakeProbe())
    assert "Teams log folder not found" in caplog.text


def test_close_closes_the_injected_notifier(recorder, clock, tmp_path: Path) -> None:
    monitor = build_monitor(
        Settings(log_dir=tmp_path), notifier=recorder, clock=clock, probe=FakeProbe()
    )
    monitor.close()
    assert recorder.closed == 1
