"""A small caching JSON-over-HTTP client — the package's house HTTP layer.

Wraps ``requests`` with an on-disk, content-addressed response cache (the
provenance root — never silently refreshed within a run), a **proactive**
per-host rate limiter (paces requests *before* sending), and **reactive**
exponential backoff on ``429`` / ``5xx`` as the fallback. The transport
(`session`), the clock, and the sleep function are injectable so the client is
fully testable without touching the network or a real wall clock.

Design: ``docs/design/proposals/literature-citation-graph-client.md`` (deps &
posture), ``docs/design/proposals/tooling-package.md`` (house HTTP client).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlencode

import requests

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

JsonValue = dict[str, Any] | list[Any]


class HttpError(RuntimeError):
    """Raised when a request ultimately fails (after retries) or returns non-JSON."""


class RateLimitError(HttpError):
    """Raised when retries are exhausted on a rate-limit signal.

    The signal is a ``429``, or a ``503`` carrying ``Retry-After``. A distinct
    type so callers can tell a *transient throttle* apart from a permanent miss
    (``404``): a throttle must never be recorded as "not found".
    """


class Response(Protocol):
    """The minimal response shape the client needs (``requests``-compatible)."""

    status_code: int

    @property
    def headers(self) -> Mapping[str, str]:
        """Response headers (read for ``Retry-After``)."""

    def json(self) -> Any:
        """Decode the response body as JSON."""


class Session(Protocol):
    """The minimal session shape the client needs (``requests.Session``)."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = ...,
        headers: dict[str, str] | None = ...,
        timeout: float | None = ...,
    ) -> Response:
        """Issue a GET request."""


def _cache_key(url: str, params: dict[str, str] | None) -> str:
    """Return a stable content-addressed cache key for a URL + params."""
    query = urlencode(sorted((params or {}).items()))
    return hashlib.sha256(f"{url}?{query}".encode()).hexdigest()


def _retry_after_seconds(headers: Mapping[str, str]) -> int | None:
    """Parse a ``Retry-After`` header value as integer seconds, else ``None``.

    :param headers: The response headers.
    :returns: The delay in seconds, or ``None`` when the header is absent or is
        an HTTP-date / otherwise unparsable (in which case the caller falls back
        to exponential backoff).
    """
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        # An HTTP-date (or garbage) — ignore it and fall back to backoff.
        return None


@dataclass
class HttpClient:
    """A caching JSON HTTP client.

    :param cache_dir: Directory for the response cache (no caching if ``None``).
    :param mailto: Email for the OpenAlex polite pool (sent as ``mailto=``).
    :param s2_key: Optional Semantic Scholar API key (sent as ``x-api-key``).
    :param session: The HTTP transport (defaults to a ``requests.Session``).
    :param sleep: Sleep function for backoff and throttling (injectable for tests).
    :param clock: Monotonic clock for the proactive throttle (injectable for tests).
    :param timeout: Per-request timeout in seconds.
    :param max_retries: Attempts on ``429`` / ``5xx`` before giving up.
    :param s2_rps: Proactive cap on Semantic Scholar requests/second. Default is
        conservatively *below* S2's documented per-key ceiling of 1 req/s
        cumulative, per their "stay below this threshold" guidance. ``0``
        disables the proactive throttle (reactive backoff still applies).
    :param openalex_rps: Proactive cap on OpenAlex requests/second — a polite
        pace under OpenAlex's documented 10 req/s ceiling. ``0`` disables it.
    """

    cache_dir: Path | None = None
    mailto: str | None = None
    s2_key: str | None = None
    session: Session = field(default_factory=requests.Session)
    sleep: object = time.sleep
    clock: object = time.monotonic
    timeout: float = 30.0
    max_retries: int = 4
    s2_rps: float = 0.9
    openalex_rps: float = 10.0
    _last_request: dict[str, float] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def _cached(self, key: str) -> JsonValue | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            try:
                data: JsonValue = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # A truncated/corrupt entry (e.g. an interrupted ``_store``) is
                # treated as a cache miss and re-fetched, never a raw traceback.
                return None
            return data
        return None

    def _store(self, key: str, value: JsonValue) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then atomically rename, so an interruption can
        # never leave a half-written (corrupt) cache entry behind.
        path = self.cache_dir / f"{key}.json"
        tmp = self.cache_dir / f"{key}.json.tmp"
        tmp.write_text(json.dumps(value), encoding="utf-8")
        tmp.replace(path)

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        headers: dict[str, str] | None = None,
        s2: bool = False,
    ) -> JsonValue:
        """GET `url` and return decoded JSON, cache-backed with backoff.

        :param url: The request URL.
        :param params: Query parameters (``mailto`` is added for non-S2 calls).
        :param headers: Extra headers (``x-api-key`` is added when `s2` + a key).
        :param s2: Whether this is a Semantic Scholar call (key/header handling).
        :returns: The decoded JSON document (served from cache when present).
        :raises HttpError: On a non-retryable status, a non-JSON body, or a
            non-rate-limit exhaustion.
        :raises RateLimitError: When retries are exhausted on a rate-limit signal.
        """
        query = dict(params or {})
        if not s2 and self.mailto:
            query.setdefault("mailto", self.mailto)
        request_headers = dict(headers or {})
        if s2 and self.s2_key:
            request_headers.setdefault("x-api-key", self.s2_key)

        key = _cache_key(url, query)
        if (hit := self._cached(key)) is not None:
            return hit

        value = self._fetch(url, query, request_headers, s2=s2)
        self._store(key, value)
        return value

    def _throttle(self, *, s2: bool) -> None:
        """Proactively pace requests to a host, before the reactive retry loop.

        Sleeps just enough that this send lands at least ``1 / rps`` after the
        last send to the same host (Semantic Scholar vs. OpenAlex are tracked
        independently, since each has its own ceiling). This is the *proactive*
        half of rate-limit handling: it runs once per :meth:`get_json` call — on
        the first attempt only — so a sweep of many calls self-throttles instead
        of bursting and collecting ``429``s. Retries *within* one call still rely
        on the existing reactive backoff/``Retry-After`` handling, unchanged.

        :param s2: Whether this call targets Semantic Scholar (selects
            ``s2_rps`` vs. ``openalex_rps``, and the per-host tracking key).
        """
        rps = self.s2_rps if s2 else self.openalex_rps
        if rps <= 0:
            return
        min_interval = 1.0 / rps
        key = "s2" if s2 else "openalex"
        now: float = self.clock()  # type: ignore[operator]
        last = self._last_request.get(key)
        if last is not None:
            wait = min_interval - (now - last)
            if wait > 0:
                self.sleep(wait)  # type: ignore[operator]
                now = self.clock()  # type: ignore[operator]
        self._last_request[key] = now

    def _fetch(
        self, url: str, query: dict[str, str], headers: dict[str, str], *, s2: bool
    ) -> JsonValue:
        """Issue the request with retries; the network side of :meth:`get_json`.

        Honors ``Retry-After`` on ``429`` / ``503`` (integer seconds); otherwise
        backs off exponentially with jitter. A rate-limit signal (``429``, or a
        ``503`` carrying ``Retry-After``) that survives every retry surfaces as a
        :class:`RateLimitError` so it is never mistaken for a permanent miss.

        :param s2: Whether this call targets Semantic Scholar (selects the
            proactive throttle's rps + tracking key; see :meth:`_throttle`).
        """
        self._throttle(s2=s2)
        last_error = "no attempt made"
        rate_limited = False
        for attempt in range(self.max_retries):
            retry_after: int | None = None
            try:
                resp = self.session.get(
                    url, params=query, headers=headers, timeout=self.timeout
                )
            except requests.RequestException as exc:  # pragma: no cover - network
                last_error = str(exc)
                rate_limited = False
            else:
                if resp.status_code == 200:
                    try:
                        data: JsonValue = resp.json()
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise HttpError(f"{url}: non-JSON response") from exc
                    return data
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise HttpError(f"{url}: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                retry_after = _retry_after_seconds(resp.headers)
                rate_limited = resp.status_code == 429 or (
                    resp.status_code == 503 and retry_after is not None
                )
            self.sleep(self._backoff(attempt, retry_after))  # type: ignore[operator]
        detail = f"{url}: giving up after {self.max_retries} attempts ({last_error})"
        if rate_limited:
            raise RateLimitError(detail)
        raise HttpError(detail)

    @staticmethod
    def _backoff(attempt: int, retry_after: int | None) -> float:
        """Return the seconds to sleep before the next attempt.

        :param attempt: The zero-based attempt index.
        :param retry_after: A server-supplied ``Retry-After`` delay, if any.
        :returns: `retry_after` when the server asked for one, else exponential
            backoff (``2**attempt``) with additive jitter to avoid thundering herds.
        """
        if retry_after is not None:
            return float(retry_after)
        return 2.0**attempt + random.uniform(0.0, 1.0)
