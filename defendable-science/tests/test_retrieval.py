"""Tests for the dataset retrieval / mirror / fixity tooling (defendable-science#3)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from defendable_science.core import fixity as fx
from defendable_science.dataset import manifest as m
from defendable_science.dataset import retrieval as r


def _write(path: Path, data: bytes = b"payload") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return r.sha256_file(path)


def _entry(
    tier: str,
    sha: str,
    path: str = "data/f.bin",
    *,
    access: str = "open",
    **kw: object,
) -> m.DatasetEntry:
    return m.DatasetEntry(
        id="d1",
        version="1",
        tier=tier,
        license="MIT",
        redistributable=(tier == "A"),
        access=access,
        files=[m.FileRef(path=path, sha256=sha)],
        datasheet="ds.md",
        **kw,  # type: ignore[arg-type]
    )


class FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class FakeRclone:
    """Records rclone invocations; ``present`` controls lsf/get success."""

    def __init__(self, *, present: bool = False) -> None:
        self.present = present
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_kw: object) -> FakeProc:
        self.calls.append(args)
        verb = args[1] if args[1] != "--config" else args[3]
        if verb == "lsf":
            return FakeProc(0 if self.present else 1)
        if verb == "copyto":
            # A "get" (mirror -> local) only succeeds when present.
            src = args[-2]
            is_get = ":" in src
            return FakeProc(0 if (not is_get or self.present) else 1)
        return FakeProc(0)


# --- sha256 / verify --------------------------------------------------------


def test_sha256_file(tmp_path: Path) -> None:
    sha = _write(tmp_path / "x")
    assert len(sha) == 64
    assert r.sha256_file(tmp_path / "x") == sha


def test_verify_reports_states(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    good = _write(tmp_path / "good")
    blob = cache / "sha256" / good
    _write(blob)  # matching bytes in the content-addressed cache
    entry = _entry("B", good, retrieval=m.Retrieval(kind="http", url="https://x"))
    report = r.verify(entry, cache_dir=cache)
    assert report.ok
    assert report.verified == ["data/f.bin"]


def test_verify_flags_missing_and_corrupt(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    sha = "a" * 64
    entry = _entry("B", sha, retrieval=m.Retrieval(kind="http", url="https://x"))
    assert r.verify(entry, cache_dir=cache).missing == ["data/f.bin"]
    # Now write mismatching bytes at the expected blob path.
    (cache / "sha256").mkdir(parents=True)
    (cache / "sha256" / sha).write_bytes(b"different")
    assert r.verify(entry, cache_dir=cache).corrupt == ["data/f.bin"]


def test_verify_unreadable_file_is_corrupt_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    _write(cache / "sha256" / ("a" * 64))  # a present-but-(soon)-unreadable blob
    entry = _entry("B", "a" * 64, retrieval=m.Retrieval(kind="http", url="https://x"))

    def _boom(_p: object, **_kw: object) -> str:
        raise PermissionError("unreadable")

    monkeypatch.setattr(r, "sha256_file", _boom)
    report = r.verify(entry, cache_dir=cache)
    assert report.corrupt == ["data/f.bin"]  # folded into corrupt, no traceback
    assert not report.ok


def test_verified_unreadable_present_file_treated_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(Path("data/f.bin"))

    def _boom(_p: object, **_kw: object) -> str:
        raise PermissionError("unreadable")

    monkeypatch.setattr(fx, "sha256_file", _boom)
    # An unreadable Tier-A file is absent to the chain, which then fails cleanly.
    with pytest.raises(r.RetrievalError, match="missing or corrupt"):
        r.fetch(_entry("A", "a" * 64), cache_dir="cache")


# --- fetch chain ------------------------------------------------------------


def test_fetch_tier_a_verifies_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _write(Path("data/f.bin"))
    paths = r.fetch(_entry("A", sha), cache_dir="cache")
    assert paths == [Path("data/f.bin")]


def test_fetch_tier_a_corrupt_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(Path("data/f.bin"))
    with pytest.raises(r.RetrievalError, match="missing or corrupt"):
        r.fetch(_entry("A", "b" * 64), cache_dir="cache")


def test_fetch_cache_hit(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    payload = b"cached bytes"
    digest = hashlib.sha256(payload).hexdigest()
    blob = cache / "sha256" / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(payload)
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="https://x"))

    def _boom(_u: str, _s: str, _d: Path) -> Path:  # must not be called
        raise AssertionError("fetcher should not run on a cache hit")

    paths = r.fetch(entry, cache_dir=cache, tier_b_fetch=_boom)
    assert paths[0] == blob


def test_fetch_tier_b_downloads_and_populates_mirror(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    payload = b"downloaded bytes"
    digest = hashlib.sha256(payload).hexdigest()
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="https://x"))

    def _fetcher(url: str, sha256: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return dest

    rclone = FakeRclone()
    mirror = r.Mirror(remote="store", base_path="base", run=rclone)
    paths = r.fetch(entry, cache_dir=cache, mirror=mirror, tier_b_fetch=_fetcher)
    assert paths[0].read_bytes() == payload
    # Mirror was populated (a copyto local -> remote).
    assert any(c[1] == "copyto" for c in rclone.calls)


def test_fetch_tier_b_bad_hash_raises(tmp_path: Path) -> None:
    entry = _entry("B", "c" * 64, retrieval=m.Retrieval(kind="http", url="https://x"))

    def _fetcher(url: str, sha256: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"wrong")
        return dest

    with pytest.raises(r.RetrievalError, match="failed SHA-256"):
        r.fetch(entry, cache_dir=tmp_path / "cache", tier_b_fetch=_fetcher)


def test_fetch_tier_c_is_verify_only(tmp_path: Path) -> None:
    entry = _entry("C", "d" * 64, access="gated", instructions="email the authors")
    with pytest.raises(r.RetrievalError, match="gated"):
        r.fetch(entry, cache_dir=tmp_path / "cache")


def test_fetch_from_mirror(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    payload = b"from mirror"
    digest = hashlib.sha256(payload).hexdigest()
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="https://x"))

    class MirrorHit(FakeRclone):
        def __call__(self, args: list[str], **kw: object) -> FakeProc:
            self.calls.append(args)
            if args[1] == "copyto" and ":" in args[-2]:  # get: write the dst
                Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(args[-1]).write_bytes(payload)
                return FakeProc(0)
            return FakeProc(0)

    mirror = r.Mirror(remote="store", run=MirrorHit())

    def _boom(_u: str, _s: str, _d: Path) -> Path:
        raise AssertionError("should have resolved from the mirror")

    paths = r.fetch(entry, cache_dir=cache, mirror=mirror, tier_b_fetch=_boom)
    assert paths[0].read_bytes() == payload


# --- audit ------------------------------------------------------------------


def test_audit_combines_validation_and_fixity(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    blob = cache / "sha256" / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(payload)
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="https://x"))
    report = r.audit(m.Manifest(datasets=[entry]), cache_dir=cache)
    assert report.validation.ok
    assert report.ok


def test_audit_fails_on_validation_error(tmp_path: Path) -> None:
    bad = m.DatasetEntry(id="bad")  # missing everything
    report = r.audit(m.Manifest(datasets=[bad]), cache_dir=tmp_path)
    assert not report.ok
    assert not report.validation.ok


def test_fetch_tier_b_no_url_raises(tmp_path: Path) -> None:
    entry = _entry("B", "e" * 64)  # no retrieval / source
    with pytest.raises(r.RetrievalError, match="no source URL"):
        r.fetch(entry, cache_dir=tmp_path / "cache")


def test_fetch_tier_b_no_mirror_success(tmp_path: Path) -> None:
    payload = b"nomirror"
    digest = hashlib.sha256(payload).hexdigest()
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="u"))

    def _f(url: str, sha: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return dest

    paths = r.fetch(entry, cache_dir=tmp_path / "c", tier_b_fetch=_f)
    assert paths[0].read_bytes() == payload


def test_audit_with_mirror_present(tmp_path: Path) -> None:
    payload = b"p"
    digest = hashlib.sha256(payload).hexdigest()
    blob = tmp_path / "c" / "sha256" / digest
    blob.parent.mkdir(parents=True)
    blob.write_bytes(payload)
    entry = _entry("B", digest, retrieval=m.Retrieval(kind="http", url="u"))
    mirror = r.Mirror(remote="s", run=FakeRclone(present=True))
    report = r.audit(
        m.Manifest(datasets=[entry]), cache_dir=tmp_path / "c", mirror=mirror
    )
    assert report.mirror_present["d1"] is True
