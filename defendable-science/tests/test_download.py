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
