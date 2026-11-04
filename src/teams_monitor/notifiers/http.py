"""HTTP transport used by the webhook notifier."""

from __future__ import annotations

import email.utils
import http.client
import math
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from teams_monitor import __version__
from teams_monitor.notifiers.base import PermanentDeliveryError, TransientDeliveryError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as errors. urllib would turn a POST into a GET and drop the alert."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class HttpTransport(ABC):
    @abstractmethod
    def post_json(self, url: str, body: bytes) -> None:
        """POST a JSON body. Raises Transient or PermanentDeliveryError on failure."""


class UrllibTransport(HttpTransport):
    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._headers = {
            "Content-Type": "application/json",
            # Some services (Discord) reject the default Python user agent.
            "User-Agent": f"teams-monitor/{__version__}",
        }

    def post_json(self, url: str, body: bytes) -> None:
        try:
            request = urllib.request.Request(  # noqa: S310 - scheme validated in Settings
                url, data=body, method="POST", headers=self._headers
            )
            with self._opener.open(request, timeout=self._timeout):
                return
        except urllib.error.HTTPError as exc:
            exc.close()
            message = f"HTTP {exc.code}"
            if 300 <= exc.code < 400:
                raise PermanentDeliveryError(
                    f"{message}: the webhook URL redirects, so update it to the final address"
                ) from exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise PermanentDeliveryError(message) from exc
            raise TransientDeliveryError(
                message, retry_after=parse_retry_after(exc.headers.get("Retry-After"))
            ) from exc
        except (http.client.InvalidURL, ValueError):
            # These messages quote the URL, which is a secret, so neither is kept.
            raise PermanentDeliveryError("the webhook URL is invalid") from None
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            raise TransientDeliveryError(str(exc)) from exc


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait from a Retry-After header (seconds or HTTP date), None if unusable."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (email.utils.parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return None
    return max(seconds, 0.0) if math.isfinite(seconds) else None
