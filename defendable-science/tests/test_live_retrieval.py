"""Opt-in live integration tests: real pooch download + real rclone (defendable-science#30).

Skipped unless ``DEFENDABLE_SCIENCE_LIVE=1``. The Tier-B download runs **real** ``pooch``
over a localhost HTTP server (deterministic, no external host to flake on); the
mirror runs the **real** ``rclone`` binary against a local-filesystem *alias*
remote — exercising the real subprocess arg construction, ``copyto``/``lsf``, and
the post-transfer re-hash. A real *cloud* remote is a manual check (credentials);
this validates that the code path shape is correct.

    DEFENDABLE_SCIENCE_LIVE=1 uv run pytest -m live --no-cov

The rclone tests skip automatically when ``rclone`` is not on ``PATH``.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import os
import shutil
import threading
from typing import TYPE_CHECKING

import pytest

from defendable_science.dataset import retrieval as r
from defendable_science.dataset.manifest import (
    DatasetEntry,
    FileRef,
    Manifest,
    Retrieval,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("DEFENDABLE_SCIENCE_LIVE") != "1",
        reason="live test — set DEFENDABLE_SCIENCE_LIVE=1 (needs network / rclone)",
    ),
]

_needs_rclone = pytest.mark.skipif(
    shutil.which("rclone") is None, reason="rclone not on PATH"
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # silence per-request logging
        pass


@pytest.fixture
def http_file(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """Serve a small payload over localhost; yield ``(url, sha256)``."""
    served = tmp_path / "served"
    served.mkdir()
    payload = b"defendable-science live-fetch payload\n" * 8
    (served / "data.bin").write_bytes(payload)
    handler = functools.partial(_QuietHandler, directory=str(served))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    sha = hashlib.sha256(payload).hexdigest()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/data.bin", sha
    finally:
        srv.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def mirror(tmp_path: Path) -> r.Mirror:
    """Return a real rclone mirror over a local-filesystem alias remote."""
    root = tmp_path / "mirror-root"
    root.mkdir()
    conf = tmp_path / "rclone.conf"
    conf.write_text(f"[testmirror]\ntype = alias\nremote = {root}\n", encoding="utf-8")
    return r.Mirror(remote="testmirror", base_path="proj", config_path=str(conf))


def _tier_b_entry(url: str, sha256: str) -> DatasetEntry:
    return DatasetEntry(
        id="live-b",
        version="1",
        tier="B",
        license="Apache-2.0",
        redistributable=True,
        access="open",
        datasheet="datasheets/x.md",
        files=[FileRef(path="data.bin", sha256=sha256)],
        retrieval=Retrieval(kind="http", url=url),
    )


def test_pooch_fetch_and_verify(tmp_path: Path, http_file: tuple[str, str]) -> None:
    url, sha = http_file
    paths = r.fetch(_tier_b_entry(url, sha), cache_dir=tmp_path / "cache")
    assert len(paths) == 1
    assert r.sha256_file(paths[0]) == sha


def test_pooch_fetch_wrong_hash_raises(
    tmp_path: Path, http_file: tuple[str, str]
) -> None:
    url, _ = http_file
    with pytest.raises(ValueError, match="does not match"):
        r.fetch(_tier_b_entry(url, "0" * 64), cache_dir=tmp_path / "cache")


@_needs_rclone
def test_rclone_mirror_roundtrip(tmp_path: Path, mirror: r.Mirror) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi\n", encoding="utf-8")
    sha = r.sha256_file(f)
    assert mirror.check(sha) is False
    mirror.put(f, sha)
    assert mirror.check(sha) is True
    dst = tmp_path / "back.txt"
    assert mirror.get(sha, dst) is True
    assert r.sha256_file(dst) == sha


@_needs_rclone
def test_fetch_populates_then_hits_mirror(
    tmp_path: Path, http_file: tuple[str, str], mirror: r.Mirror
) -> None:
    url, sha = http_file
    entry = _tier_b_entry(url, sha)
    cache = tmp_path / "cache"
    r.fetch(entry, cache_dir=cache, mirror=mirror)
    assert mirror.check(sha) is True

    # Clear the cache; the second fetch must come from the MIRROR, not the network.
    r._blob_path(cache, sha).unlink()

    def _no_network(url: str, sha256: str, dest: Path) -> Path:
        raise AssertionError("second fetch should hit the mirror, not re-download")

    paths = r.fetch(entry, cache_dir=cache, mirror=mirror, tier_b_fetch=_no_network)
    assert r.sha256_file(paths[0]) == sha


@_needs_rclone
def test_audit_reports_mirror_presence(
    tmp_path: Path, http_file: tuple[str, str], mirror: r.Mirror
) -> None:
    url, sha = http_file
    entry = _tier_b_entry(url, sha)
    cache = tmp_path / "cache"
    r.fetch(entry, cache_dir=cache, mirror=mirror)
    report = r.audit(Manifest(datasets=[entry]), cache_dir=cache, mirror=mirror)
    assert report.ok is True
    assert report.mirror_present[entry.id] is True
