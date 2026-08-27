"""Tests for the streaming binary downloader."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from defendable_science.core import download as d

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path


class FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._chunks = chunks
        self.status_code = status_code
        self.headers = (
            dict(headers)
            if headers is not None
            else {"Content-Type": "application/pdf"}
        )
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        assert chunk_size > 0
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, bool]] = []

    def get(
        self,
        url: str,
        *,
        stream: bool = False,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append((url, stream))
        return self.response


def test_streams_to_file_and_reports_media_type(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"%PDF-", b"rest"]))
    got = d.stream_to_file("http://x/p.pdf", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert got.path.read_bytes() == b"%PDF-rest"
    assert got.media_type == "application/pdf"
    assert got.size == 9
    assert session.calls == [("http://x/p.pdf", True)]
    assert session.response.closed


def test_media_type_strips_charset_parameters(tmp_path: Path) -> None:
    session = FakeSession(
        FakeResponse([b"x"], headers={"Content-Type": "text/html; charset=utf-8"})
    )
    got = d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert got.media_type == "text/html"


def test_missing_content_type_yields_none(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"x"], headers={}))
    got = d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert got.media_type is None


def test_non_200_raises_with_the_status(tmp_path: Path) -> None:
    dest = tmp_path / "p"
    session = FakeSession(FakeResponse([], status_code=403))
    with pytest.raises(d.DownloadError, match="HTTP 403"):
        d.stream_to_file("http://x", dest, 1000, session=session)  # type: ignore[arg-type]
    assert not dest.exists()
    assert session.response.closed


def test_oversize_aborts_and_removes_the_partial_file(tmp_path: Path) -> None:
    dest = tmp_path / "p"
    session = FakeSession(FakeResponse([b"a" * 6, b"b" * 6]))
    with pytest.raises(d.DownloadError, match="exceeds max_bytes"):
        d.stream_to_file("http://x", dest, 10, session=session)  # type: ignore[arg-type]
    assert not dest.exists()


def test_empty_body_is_an_error(tmp_path: Path) -> None:
    dest = tmp_path / "p"
    session = FakeSession(FakeResponse([]))
    with pytest.raises(d.DownloadError, match="empty response body"):
        d.stream_to_file("http://x", dest, 1000, session=session)  # type: ignore[arg-type]
    assert not dest.exists()
    assert session.response.closed


def test_creates_parent_directories(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"x"]))
    got = d.stream_to_file("http://x", tmp_path / "a" / "b" / "p", 100, session=session)  # type: ignore[arg-type]
    assert got.path.is_file()


def test_transport_failure_becomes_a_download_error(tmp_path: Path) -> None:
    class Boom:
        def get(self, url: str, **_kw: object) -> FakeResponse:
            raise OSError("connection reset")

    with pytest.raises(d.DownloadError, match="connection reset"):
        d.stream_to_file("http://x", tmp_path / "p", 100, session=Boom())  # type: ignore[arg-type]


def test_default_session_is_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(d.requests, "Session", lambda: sentinel)  # type: ignore[attr-defined]
    result = d._default_session()
    assert result is sentinel


# --- telling a throttle from a hard miss ------------------------------------
#
# The status has to survive on the exception, because the ladder in
# `literature/acquire.py` decides between "walk on", "record a block" and "stop
# the sweep" from nothing else. Before this, every non-200 was one indistinct
# `DownloadError` and a 429 was filed as "this paper has no PDF".


def test_a_throttle_carries_its_status_and_retry_after(tmp_path: Path) -> None:
    session = FakeSession(
        FakeResponse([], status_code=429, headers={"Retry-After": "30"})
    )
    with pytest.raises(d.DownloadError) as caught:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert caught.value.status == 429
    assert caught.value.retry_after == 30
    assert caught.value.rate_limited is True
    assert caught.value.hard_miss is False


def test_a_503_is_a_throttle_only_when_it_asks_us_to_wait(tmp_path: Path) -> None:
    """``503`` + ``Retry-After`` is "slow down"; a bare ``503`` is just broken."""
    asking = FakeSession(
        FakeResponse([], status_code=503, headers={"Retry-After": "5"})
    )
    with pytest.raises(d.DownloadError) as throttled:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=asking)  # type: ignore[arg-type]
    assert throttled.value.rate_limited is True

    bare = FakeSession(FakeResponse([], status_code=503, headers={}))
    with pytest.raises(d.DownloadError) as broken:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=bare)  # type: ignore[arg-type]
    assert broken.value.retry_after is None
    assert broken.value.rate_limited is False


def test_an_http_date_retry_after_is_not_read_as_seconds(tmp_path: Path) -> None:
    session = FakeSession(
        FakeResponse(
            [],
            status_code=503,
            headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
        )
    )
    with pytest.raises(d.DownloadError) as caught:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert caught.value.retry_after is None
    assert caught.value.rate_limited is False


@pytest.mark.parametrize("status", [404, 410])
def test_a_gone_status_is_a_hard_miss(status: int, tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([], status_code=status))
    with pytest.raises(d.DownloadError) as caught:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert caught.value.hard_miss is True
    assert caught.value.rate_limited is False


def test_a_403_is_neither_a_hard_miss_nor_a_throttle(tmp_path: Path) -> None:
    """A CDN blocking a non-browser agent tells us nothing about the paper."""
    session = FakeSession(FakeResponse([], status_code=403))
    with pytest.raises(d.DownloadError) as caught:
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)  # type: ignore[arg-type]
    assert caught.value.status == 403
    assert caught.value.hard_miss is False
    assert caught.value.rate_limited is False


def test_a_transport_level_failure_has_no_status(tmp_path: Path) -> None:
    class Boom:
        def get(self, url: str, **_kw: object) -> FakeResponse:
            raise OSError("connection reset")

    with pytest.raises(d.DownloadError) as caught:
        d.stream_to_file("http://x", tmp_path / "p", 100, session=Boom())  # type: ignore[arg-type]
    assert caught.value.status is None
    assert caught.value.hard_miss is False


# --- mid-stream failures ------------------------------------------------------


class BrokenResponse(FakeResponse):
    """A response that dies part-way through the body."""

    def __init__(self, chunks: list[bytes], boom: Exception) -> None:
        super().__init__(chunks)
        self._boom = boom

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield from self._chunks
        raise self._boom


def test_a_mid_stream_transport_failure_is_a_download_error_not_a_traceback(
    tmp_path: Path,
) -> None:
    """The point of the test.

    ``requests`` raises ``ChunkedEncodingError`` *during* body iteration, an
    ``OSError`` subclass rather than a ``DownloadError``. It used to escape the
    only handler here — leaving a truncated ``.part`` on disk, falsifying this
    function's own "a partial file is removed on any failure", and surfacing as a
    raw traceback through a whole call chain that catches ``DownloadError``.
    """
    import requests

    dest = tmp_path / "out.part"
    session = FakeSession(
        BrokenResponse(
            [b"%PDF-1.4 partial"],
            requests.exceptions.ChunkedEncodingError("connection broken"),
        )
    )
    with pytest.raises(d.DownloadError, match="connection broken"):
        d.stream_to_file("http://x/p.pdf", dest, 10_000, session=session)  # type: ignore[arg-type]
    assert not dest.exists()
    assert session.response.closed


def test_a_failed_write_is_a_download_error_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk is a failure, not a short PDF."""
    import pathlib

    class FullDisk:
        """A write handle on a disk with no room left."""

        def __enter__(self) -> FullDisk:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def write(self, _data: bytes) -> int:
            raise OSError("No space left on device")

    monkeypatch.setattr(
        pathlib.Path, "open", lambda *_a, **_kw: FullDisk(), raising=True
    )
    session = FakeSession(FakeResponse([b"%PDF-"]))
    dest = tmp_path / "out.part"
    with pytest.raises(d.DownloadError, match="No space left on device"):
        d.stream_to_file("http://x/p.pdf", dest, 10_000, session=session)  # type: ignore[arg-type]
