"""Polite HTTP for connectors: identifies the project, retries transient failures with backoff,
and spaces out requests to the same host so public servers are never hammered."""

from __future__ import annotations

import ssl
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

USER_AGENT = "UnnatiIndex/0.1 (+https://github.com/Agneeshz/unnati-index)"
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def legacy_renegotiation_context() -> ssl.SSLContext:
    """For servers that still need TLS legacy renegotiation (e.g. api.mospi.gov.in).

    Only renegotiation is relaxed: certificates and hostnames are still verified. Use it only
    for public, read-only fetches that send no credentials."""
    context = ssl.create_default_context()
    context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    return context


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in TRANSIENT_STATUS


class PoliteClient:
    """An httpx client that waits at least ``min_interval`` seconds between requests to a host."""

    def __init__(
        self,
        min_interval: float = 1.0,
        timeout: float = 60.0,
        ssl_context: ssl.SSLContext | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
            verify=ssl_context if ssl_context is not None else True,
            transport=transport,
        )
        self._min_interval = min_interval
        self._last_request: dict[str, float] = {}

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _wait_turn(self, url: str) -> None:
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_request.get(host, float("-inf"))
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request[host] = time.monotonic()

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self._wait_turn(url)
        response = self._client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)
