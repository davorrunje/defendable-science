"""Streaming binary retrieval with a hard size cap.

Deliberately separate from :mod:`defendable_science.core.http`: that client is a
*JSON* client with a JSON response cache and a retry loop built around
``resp.json()``, none of which a binary stream shares. Here the content-addressed
blob store is the cache, so nothing is cached at this layer.

The transport is injectable (:class:`StreamSession`), so the acquisition ladder
is exercised without network access.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import requests

#: Read size for the streamed body.
CHUNK = 1 << 16


class DownloadError(RuntimeError):
    """Raised when a byte retrieval fails, is empty, or exceeds the size cap.

    Carries the HTTP status when the failure had one, because a caller walking a
    list of candidate URLs must be able to tell a **hard miss** (``404``: that
    link is dead, which is a fact about the paper) from a **block** (``403``,
    ``429``, ``503``, or a transport failure: we were prevented from looking, and
    know nothing about the paper). Reporting the second as the first is how "we
    failed" becomes "there is no PDF" — the confusion the failure-honesty rule
    exists to prevent.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Record the failure alongside what the server said about it.

        :param message: The human-readable failure.
        :param status: The HTTP status code, or ``None`` for a transport-level
            failure that never got one.
        :param retry_after: ``Retry-After`` in seconds, when the server sent a
            parsable one.
        """
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after

    @property
    def rate_limited(self) -> bool:
        """Return whether this failure is a throttle rather than a refusal.

        The signal is the same one
        :class:`~defendable_science.core.http.RateLimitError` uses for the JSON
        client — a ``429``, or a ``503`` carrying ``Retry-After`` — so the byte
        layer and the metadata layer agree on what "slow down" looks like.

        :returns: Whether the caller should back off rather than move on.
        """
        return self.status == 429 or (
            self.status == 503 and self.retry_after is not None
        )

    @property
    def hard_miss(self) -> bool:
        """Return whether this failure is evidence the URL has no bytes to serve.

        Only ``404`` and ``410`` qualify: the server answered, and its answer was
        "there is nothing here". Everything else — a block, a server fault, an
        oversized body, a dropped connection — leaves the question open, and a
        caller must not fold it into "no PDF exists".

        :returns: Whether the absence of bytes is established rather than assumed.
        """
        return self.status in (404, 410)


@dataclass
class FetchedBytes:
    """Bytes that landed on disk, with what the server said about them.

    :param path: Where the bytes were written.
    :param media_type: The ``Content-Type`` with parameters stripped, or ``None``
        when the server sent none. Advisory only — servers misreport it, so a
        caller that cares about the true format must inspect the bytes.
    :param size: Byte count actually written.
    """

    path: Path
    media_type: str | None
    size: int


#: A byte fetcher: ``(url, dest, max_bytes) -> FetchedBytes`` (injectable).
BytesFetcher = Callable[[str, Path, int], FetchedBytes]


class StreamResponse(Protocol):
    """The minimal streaming-response shape the downloader needs."""

    status_code: int
    headers: Mapping[str, str]

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        """Yield the body in chunks."""

    def close(self) -> None:
        """Release the connection."""


class StreamSession(Protocol):
    """The minimal session shape the downloader needs (``requests.Session``)."""

    def get(
        self,
        url: str,
        *,
        stream: bool = ...,
        timeout: float | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> StreamResponse:
        """Issue a streaming GET."""


def _default_session() -> StreamSession:
    """Return a fresh ``requests.Session`` (indirection for tests)."""
    return cast("StreamSession", requests.Session())


def _media_type(headers: Mapping[str, str]) -> str | None:
    """Return the bare ``Content-Type``, parameters stripped, else ``None``."""
    raw = headers.get("Content-Type")
    if not raw:
        return None
    return raw.split(";", 1)[0].strip().lower() or None


def _retry_after_seconds(headers: Mapping[str, str]) -> int | None:
    """Parse a ``Retry-After`` header value as integer seconds, else ``None``.

    The same rule as ``core.http``'s namesake, deliberately duplicated rather
    than imported: this module stays independent of the JSON client (see the
    module docstring), and the rule is six lines.

    :param headers: The response headers.
    :returns: The delay in seconds, or ``None`` when the header is absent or is
        an HTTP-date / otherwise unparsable.
    """
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def stream_to_file(
    url: str,
    dest: Path,
    max_bytes: int,
    *,
    session: StreamSession | None = None,
    timeout: float = 30.0,
) -> FetchedBytes:
    """Stream `url` into `dest`, aborting past `max_bytes`.

    A partial file is removed on any failure, so a caller never sees truncated
    bytes it might mistake for a complete download.

    :param url: The URL to retrieve.
    :param dest: Destination path (parents are created).
    :param max_bytes: Hard ceiling; exceeding it aborts the transfer.
    :param session: The streaming transport (defaults to ``requests.Session``).
    :param timeout: Per-request timeout in seconds.
    :returns: The landed bytes with their reported media type and size.
    :raises DownloadError: On a non-200 status, a transport failure (including one
        that interrupts the body mid-stream), a write failure, an empty body, or a
        body exceeding `max_bytes`. The status — and ``Retry-After`` on a throttle
        — travels on the exception, so the caller can tell a hard miss from a block.
    """
    transport = session if session is not None else _default_session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = transport.get(url, stream=True, timeout=timeout)
    except OSError as exc:
        raise DownloadError(f"{url}: {exc}") from exc
    try:
        if response.status_code != 200:
            raise DownloadError(
                f"{url}: HTTP {response.status_code}",
                status=response.status_code,
                retry_after=_retry_after_seconds(response.headers),
            )
        size = 0
        with dest.open("wb") as handle:
            for block in response.iter_content(chunk_size=CHUNK):
                size += len(block)
                if size > max_bytes:
                    raise DownloadError(
                        f"{url}: exceeds max_bytes ({max_bytes}) — aborted"
                    )
                handle.write(block)
        if size == 0:
            raise DownloadError(f"{url}: empty response body")
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    except OSError as exc:
        # The body was interrupted mid-stream (``requests``' transport errors are
        # ``OSError`` subclasses) or the write itself failed (a full disk). Either
        # way a truncated file is on disk and must not escape as a raw traceback
        # through a caller that only handles `DownloadError`.
        dest.unlink(missing_ok=True)
        raise DownloadError(f"{url}: {exc}") from exc
    finally:
        response.close()
    return FetchedBytes(path=dest, media_type=_media_type(response.headers), size=size)
