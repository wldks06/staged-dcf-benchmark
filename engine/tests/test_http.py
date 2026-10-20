"""data/http.py: throttling, retries and redacted errors. No network and no real sleeping.

The requests session is replaced by a scripted fake, and the module's clock
(time.monotonic and time.sleep) by a fake that advances only when told to sleep.
"""

from __future__ import annotations

import pytest
import requests

from dcfbench.data import http as http_module
from dcfbench.data.http import MAX_RETRY_AFTER, FetchError, Http

URL = "https://api.example.test/data"


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", headers: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class FakeSession:
    """Plays back a script of responses or exceptions, one per request."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok(content: bytes = b"body") -> FakeResponse:
    return FakeResponse(200, content)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    # Only the name inside data/http.py is swapped, the real time module is untouched.
    monkeypatch.setattr(http_module, "time", fake)
    return fake


def client(script, **kwargs) -> Http:
    kwargs.setdefault("min_interval", 0.0)
    http = Http(**kwargs)
    http.session = FakeSession(script)
    return http


# --- the plain path ----------------------------------------------------------


def test_returns_content_on_200(clock):
    http = client([ok(b"hello")], timeout=12.5)
    assert http.get(URL, params={"id": "DGS10"}) == b"hello"
    assert http.session.calls == [{"url": URL, "params": {"id": "DGS10"}, "timeout": 12.5}]
    assert http.requests_made == 1
    assert clock.sleeps == []


def test_headers_go_on_the_session():
    http = Http(headers={"User-Agent": "dcfbench test"})
    assert http.session.headers["User-Agent"] == "dcfbench test"


# --- retries -----------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_on_429_and_5xx(clock, status):
    http = client([FakeResponse(status), ok(b"second try")])
    assert http.get(URL) == b"second try"
    assert http.requests_made == 2
    assert clock.sleeps == [1.0]


def test_backoff_doubles_between_attempts(clock):
    http = client([FakeResponse(503)] * 4 + [ok()])
    assert http.get(URL) == b"body"
    assert clock.sleeps == [1.0, 2.0, 4.0, 8.0]
    assert http.requests_made == 5


def test_gives_up_after_the_last_retry_without_sleeping_again(clock):
    http = client([FakeResponse(503)] * 3, retries=2)
    with pytest.raises(FetchError, match="HTTP 503"):
        http.get(URL)
    assert http.requests_made == 3
    assert clock.sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_does_not_retry_a_client_error(clock, status):
    http = client([FakeResponse(status), ok()])
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        http.get(URL)
    assert http.requests_made == 1
    assert clock.sleeps == []


def test_retries_a_connection_error(clock):
    http = client([requests.ConnectionError("boom"), ok(b"recovered")])
    assert http.get(URL) == b"recovered"
    assert http.requests_made == 2
    assert clock.sleeps == [1.0]


def test_reports_the_exception_class_when_every_attempt_fails(clock):
    http = client([requests.Timeout("slow")] * 2, retries=1)
    with pytest.raises(FetchError, match="failed: Timeout"):
        http.get(URL)
    assert http.requests_made == 2


# --- Retry-After -------------------------------------------------------------


def test_honors_a_numeric_retry_after(clock):
    http = client([FakeResponse(429, headers={"Retry-After": "7"}), ok()])
    http.get(URL)
    assert clock.sleeps == [7.0]


def test_retry_after_is_capped(clock):
    http = client([FakeResponse(429, headers={"Retry-After": "100000"}), ok()])
    http.get(URL)
    assert clock.sleeps == [MAX_RETRY_AFTER]


def test_retry_after_never_shortens_the_backoff(clock):
    script = [FakeResponse(503)] * 2 + [FakeResponse(503, headers={"Retry-After": "1"}), ok()]
    http = client(script)
    http.get(URL)
    # Third failure: the server says 1 second, the backoff is already at 4.
    assert clock.sleeps == [1.0, 2.0, 4.0]


def test_a_date_valued_retry_after_falls_back_to_the_backoff(clock):
    headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    http = client([FakeResponse(503, headers=headers), ok()])
    http.get(URL)
    assert clock.sleeps == [1.0]


# --- redaction ---------------------------------------------------------------


def test_fetch_error_message_has_the_key_redacted(clock):
    http = client([FakeResponse(404)])
    with pytest.raises(FetchError) as caught:
        http.get(URL, params={"series_id": "DGS10", "api_key": "SECRET123"})
    message = str(caught.value)
    assert "SECRET123" not in message
    assert message == f"GET {URL}?series_id=DGS10&api_key=REDACTED failed: HTTP 404"
    # The request itself carried the real key.
    assert http.session.calls[0]["params"]["api_key"] == "SECRET123"


def test_fetch_error_redacts_a_key_written_into_the_url(clock):
    http = client([requests.ConnectionError("no route to api_key=SECRET123")] * 5)
    with pytest.raises(FetchError) as caught:
        http.get(URL + "?crtfc_key=SECRET123&corp_code=00126380")
    assert "SECRET123" not in str(caught.value)
    assert "corp_code=00126380" in str(caught.value)


# --- throttle ----------------------------------------------------------------


def test_respects_min_interval_between_calls(clock):
    http = client([ok(), ok(), ok(), ok()], min_interval=0.5)
    http.get(URL)
    assert clock.sleeps == []  # nothing to wait for before the first request
    http.get(URL)
    assert clock.sleeps == [0.5]
    clock.now += 0.2  # some of the interval has already passed
    http.get(URL)
    assert clock.sleeps[-1] == pytest.approx(0.3)
    clock.now += 5.0  # long idle: no wait at all
    http.get(URL)
    assert len(clock.sleeps) == 2


def test_min_interval_also_spaces_out_retries(clock):
    http = client([FakeResponse(503), ok()], min_interval=3.0)
    http.get(URL)
    # One second of backoff, then two more to reach the three-second spacing.
    assert clock.sleeps == [1.0, 2.0]


def test_requests_made_counts_every_attempt(clock):
    http = client([ok(), FakeResponse(500), ok(), FakeResponse(404)])
    http.get(URL)
    http.get(URL)
    with pytest.raises(FetchError):
        http.get(URL)
    assert http.requests_made == 4
