"""Tests for the shared fixity primitives (promoted from dataset/retrieval.py)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from defendable_science.core import fixity as f

if TYPE_CHECKING:
    from pathlib import Path


def test_sha256_file_streams_in_chunks(tmp_path: Path) -> None:
    payload = b"payload" * 1000
    target = tmp_path / "x"
    target.write_bytes(payload)
    assert f.sha256_file(target, chunk=8) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("sha256:ABC", "abc"), ("abc", "abc"), ("  sha256:AbC  ", "abc")],
)
def test_bare_sha256_normalizes(raw: str, expected: str) -> None:
    assert f.bare_sha256(raw) == expected


def test_blob_path_is_content_addressed(tmp_path: Path) -> None:
    assert f.blob_path(tmp_path, "sha256:AB") == tmp_path / "sha256" / "ab"


def test_verified_true_on_match(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")
    assert f.verified(target, hashlib.sha256(b"p").hexdigest()) is True


def test_verified_false_when_absent(tmp_path: Path) -> None:
    assert f.verified(tmp_path / "nope", "a" * 64) is False


def test_verified_false_on_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")
    assert f.verified(target, "a" * 64) is False


def test_verified_treats_unreadable_file_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")

    def _boom(_path: object, **_kw: object) -> str:
        raise OSError("unreadable")

    monkeypatch.setattr(f, "sha256_file", _boom)
    assert f.verified(target, "a" * 64) is False


def test_retrieval_error_is_a_runtime_error() -> None:
    assert issubclass(f.RetrievalError, RuntimeError)
