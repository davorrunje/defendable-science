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
    """Raised when a byte retrieval fails, is empty, or exceeds the size cap."""


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
    :raises DownloadError: On a non-200 status, a transport failure, an empty
        body, or a body exceeding `max_bytes`.
    """
    transport = session if session is not None else _default_session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = transport.get(url, stream=True, timeout=timeout)
    except OSError as exc:
        raise DownloadError(f"{url}: {exc}") from exc
    try:
        if response.status_code != 200:
            raise DownloadError(f"{url}: HTTP {response.status_code}")
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
    finally:
        response.close()
    return FetchedBytes(path=dest, media_type=_media_type(response.headers), size=size)
