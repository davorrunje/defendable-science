"""Tests for the shared ``git check-ignore`` seam (#138, #139)."""

from __future__ import annotations

import subprocess
from pathlib import Path  # noqa: TC003
from types import SimpleNamespace

from defendable_science.core import gitignore as g


def _fake_run(returncode: int) -> g.GitRunner:
    """Build a fake ``git`` runner that always returns `returncode`."""

    def _run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode)

    return _run


def _raising_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
    raise FileNotFoundError("git not found")


def test_check_ignore_true_when_git_exits_zero(tmp_path: Path) -> None:
    assert g.check_ignore(tmp_path, "x", run=_fake_run(0)) is True


def test_check_ignore_false_when_git_exits_one(tmp_path: Path) -> None:
    assert g.check_ignore(tmp_path, "x", run=_fake_run(1)) is False


def test_check_ignore_none_on_any_other_exit_code(tmp_path: Path) -> None:
    """128 (not a repo / usage error) — and every other code — is "undeterminable"."""
    assert g.check_ignore(tmp_path, "x", run=_fake_run(128)) is None
    assert g.check_ignore(tmp_path, "x", run=_fake_run(2)) is None


def test_check_ignore_none_when_git_binary_is_absent(tmp_path: Path) -> None:
    assert g.check_ignore(tmp_path, "x", run=_raising_run) is None


def test_check_ignore_none_when_the_runner_raises_a_subprocess_error(
    tmp_path: Path,
) -> None:
    def _run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise subprocess.SubprocessError("boom")

    assert g.check_ignore(tmp_path, "x", run=_run) is None


def test_check_ignore_runs_git_in_the_given_root(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        seen["cwd"] = kwargs.get("cwd")
        seen["args"] = args[0]
        return SimpleNamespace(returncode=1)

    g.check_ignore(tmp_path, "some/path", run=_run)

    assert seen["cwd"] == str(tmp_path)
    assert seen["args"] == ["git", "check-ignore", "--quiet", "--", "some/path"]


def test_check_ignore_against_a_real_git_repo(tmp_path: Path) -> None:
    """End-to-end with the real ``git`` binary — the actual gitignore semantics."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # nosec B603 B607

    # Not yet ignored.
    assert g.check_ignore(tmp_path, ".defendable-science/cache/") is False

    (tmp_path / ".gitignore").write_text(
        "**/.defendable-science/cache/\n", encoding="utf-8"
    )
    assert g.check_ignore(tmp_path, ".defendable-science/cache/") is True


def test_check_ignore_recognizes_a_leading_slash_anchored_pattern(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # nosec B603 B607
    (tmp_path / ".gitignore").write_text(
        "/.defendable-science/cache/\n", encoding="utf-8"
    )

    assert g.check_ignore(tmp_path, ".defendable-science/cache/") is True


def test_check_ignore_recognizes_a_wildcard_pattern(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # nosec B603 B607
    (tmp_path / ".gitignore").write_text("*.cache/\n", encoding="utf-8")

    assert g.check_ignore(tmp_path, ".cache/") is True


def test_check_ignore_none_outside_a_git_work_tree(tmp_path: Path) -> None:
    """A plain directory that was never ``git init``'d — the `init` fallback case."""
    assert g.check_ignore(tmp_path, "x") is None
