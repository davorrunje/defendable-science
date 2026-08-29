"""Tests for `core.paths.require_path_segment` (defendable-science, gap 5)."""

from __future__ import annotations

import pytest

from defendable_science.core import paths


class _BoomError(Exception):
    """A stand-in for a module's own domain error."""


@pytest.mark.parametrize("value", ["W1", "sill1997monotonic", "hyp-01", "a.b_c-1"])
def test_accepts_an_ordinary_identifier(value: str) -> None:
    assert paths.require_path_segment(value, what="citekey", error=_BoomError) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../etc/passwd",
        "../../../../../../tmp/dsaudit/PWNED",
        "foo/bar",
        "/etc/passwd",
        "foo\\bar",
        "..\\..\\PWNED",
        "a\x00b",
        "a\nb",
        "a\tb",
        "\x1f",
        "C:PWNED",
        "C:",
        "c:PWNED",
    ],
)
def test_rejects_anything_that_is_not_a_single_path_segment(value: str) -> None:
    with pytest.raises(_BoomError, match=r"citekey"):
        paths.require_path_segment(value, what="citekey", error=_BoomError)


def test_error_message_names_the_offending_value() -> None:
    with pytest.raises(_BoomError, match=r"'\.\.'"):
        paths.require_path_segment("..", what="paper_id", error=_BoomError)


def test_error_uses_the_caller_supplied_label() -> None:
    with pytest.raises(_BoomError, match=r"slug"):
        paths.require_path_segment("a/b", what="slug", error=_BoomError)
