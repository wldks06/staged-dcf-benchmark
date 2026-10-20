"""A small throttled HTTP client. Only snapshot.py calls it during a fetch."""

from __future__ import annotations

import time

import requests

from ..config import redact

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 120.0


class FetchError(RuntimeError):
    pass


class Http:
    """GET with a minimum interval between requests and retries with backoff."""

    def __init__(self, *, min_interval: float = 0.5, headers: dict | None = None,
                 timeout: float = 60.0, retries: int = 4):
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(headers or {})
        self._last = 0.0
        self.requests_made = 0

    def get(self, url: str, params: dict | None = None) -> bytes:
        error = "no attempt made"
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests_made += 1
            backoff = min(2.0 ** attempt, 30.0)
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                error = type(exc).__name__
            else:
                if response.status_code == 200:
                    return response.content
                error = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUS:
                    break
                # A server that says when to come back is taken at its word, within reason.
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    backoff = min(max(backoff, float(retry_after)), MAX_RETRY_AFTER)
            if attempt < self.retries:
                time.sleep(backoff)
        raise FetchError(f"GET {redact(requests.Request('GET', url, params=params).prepare().url)}"
                         f" failed: {error}")
