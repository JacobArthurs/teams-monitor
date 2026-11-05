from __future__ import annotations

import json

import pytest

from teams_monitor import alerts
from teams_monitor.notifiers import PayloadBuilder, WebhookNotifier
from teams_monitor.notifiers.base import PermanentDeliveryError, TransientDeliveryError
from teams_monitor.notifiers.http import HttpTransport

URL = "https://hooks.example.com/x"


class FakeTransport(HttpTransport):
    """Raises each queued error in turn, then succeeds."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls: list[tuple[str, bytes]] = []

    def post_json(self, url: str, body: bytes) -> None:
        self.calls.append((url, body))
        if self.errors:
            raise self.errors.pop(0)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make(clock, sleeps: list[float]):
    def _make(transport: HttpTransport, **kwargs) -> WebhookNotifier:
        return WebhookNotifier(
            URL, PayloadBuilder("MY-PC", clock), transport, sleep=sleeps.append, **kwargs
        )

    return _make


def _transient(retry_after: float | None = None) -> TransientDeliveryError:
    return TransientDeliveryError("HTTP 503", retry_after=retry_after)


def test_success_posts_once_without_sleeping(make, sleeps: list[float]) -> None:
    transport = FakeTransport()
    make(transport).notify(alerts.incoming_call("id", "ts"))
    assert len(transport.calls) == 1
    assert sleeps == []


def test_posts_the_payload_as_json(make) -> None:
    transport = FakeTransport()
    make(transport).notify(alerts.incoming_call("id", "ts"))
    url, body = transport.calls[0]
    assert url == URL
    assert json.loads(body)["alert"] == "incoming_call"


def test_retries_then_succeeds(make, sleeps: list[float]) -> None:
    transport = FakeTransport(_transient(), _transient())
    make(transport).notify(alerts.teams_down("x"))
    assert len(transport.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_four_attempts_with_the_last_error(make, sleeps: list[float]) -> None:
    last = TransientDeliveryError("the last one")
    transport = FakeTransport(_transient(), _transient(), _transient(), last)
    with pytest.raises(TransientDeliveryError) as caught:
        make(transport).notify(alerts.teams_down("x"))
    assert caught.value is last
    assert len(transport.calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_permanent_error_is_not_retried(make, sleeps: list[float]) -> None:
    transport = FakeTransport(PermanentDeliveryError("HTTP 404"))
    with pytest.raises(PermanentDeliveryError):
        make(transport).notify(alerts.teams_down("x"))
    assert len(transport.calls) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("retry_after", "slept"),
    [(10.0, 10.0), (0.1, 1.0), (0.0, 1.0), (30.0, 30.0), (100.0, 30.0)],
)
def test_retry_after_can_only_lengthen_a_wait_and_is_capped(
    make, sleeps: list[float], retry_after: float, slept: float
) -> None:
    make(FakeTransport(_transient(retry_after))).notify(alerts.teams_down("x"))
    assert sleeps == [slept]


def test_no_retry_delays_means_one_attempt(make, sleeps: list[float]) -> None:
    transport = FakeTransport(_transient())
    with pytest.raises(TransientDeliveryError):
        make(transport, retry_delays=()).notify(alerts.teams_down("x"))
    assert len(transport.calls) == 1
    assert sleeps == []


def test_retry_log_does_not_contain_the_url(make, caplog: pytest.LogCaptureFixture) -> None:
    make(FakeTransport(_transient())).notify(alerts.teams_down("x"))
    assert "retrying" in caplog.text
    assert URL not in caplog.text
