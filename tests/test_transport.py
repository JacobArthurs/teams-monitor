from __future__ import annotations

import socket
import threading
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from teams_monitor import __version__
from teams_monitor.notifiers.base import PermanentDeliveryError, TransientDeliveryError
from teams_monitor.notifiers.transport import UrllibTransport, parse_retry_after

SECRET = "s3cret-token"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.requests.append(("POST", self.path, dict(self.headers), body))
        self._reply()

    def do_GET(self) -> None:
        self.server.requests.append(("GET", self.path, dict(self.headers), b""))
        self._reply()

    def _reply(self) -> None:
        status = int(self.path.rsplit("/", 1)[-1])
        self.send_response(status)
        if 300 <= status < 400:
            self.send_header("Location", "/200")
        if status == 429:
            self.send_header("Retry-After", "7")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", "*")


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.requests = []
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _url(server, status: int) -> str:
    return f"http://127.0.0.1:{server.server_port}/{SECRET}/{status}"


def test_success_posts_the_body_and_headers(server) -> None:
    UrllibTransport().post_json(_url(server, 200), b'{"a": 1}')
    method, _, headers, body = server.requests[0]
    assert method == "POST"
    assert body == b'{"a": 1}'
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == f"teams-monitor/{__version__}"


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_fails_without_being_followed(server, status: int) -> None:
    with pytest.raises(PermanentDeliveryError, match="redirects"):
        UrllibTransport().post_json(_url(server, status), b"{}")
    assert len(server.requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_permanent(server, status: int) -> None:
    with pytest.raises(PermanentDeliveryError, match=f"HTTP {status}"):
        UrllibTransport().post_json(_url(server, status), b"{}")


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_transient(server, status: int) -> None:
    with pytest.raises(TransientDeliveryError, match=f"HTTP {status}") as caught:
        UrllibTransport().post_json(_url(server, status), b"{}")
    assert caught.value.retry_after is None


def test_rate_limit_is_transient_and_carries_retry_after(server) -> None:
    with pytest.raises(TransientDeliveryError) as caught:
        UrllibTransport().post_json(_url(server, 429), b"{}")
    assert caught.value.retry_after == 7.0


def test_connection_refused_is_transient() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(TransientDeliveryError):
        UrllibTransport(timeout=2.0).post_json(f"http://127.0.0.1:{port}/", b"{}")


@pytest.mark.parametrize(
    "url",
    [f"not-a-url/{SECRET}", f"http://127.0.0.1:1/{SECRET} with space"],
)
def test_invalid_url_is_permanent_and_never_quoted(url: str) -> None:
    with pytest.raises(PermanentDeliveryError) as caught:
        UrllibTransport().post_json(url, b"{}")
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("5", 5.0),
        ("1.5", 1.5),
        ("0", 0.0),
        ("-3", 0.0),
        ("nan", None),
        ("inf", None),
        ("-inf", None),
        ("soon", None),
        ("", None),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0),
    ],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value) == expected


def test_parse_retry_after_with_a_future_date() -> None:
    value = format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
    assert parse_retry_after(value) == pytest.approx(60, abs=5)
