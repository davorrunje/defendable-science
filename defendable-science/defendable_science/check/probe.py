"""The filesystem seam the checks read through (#121)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class Probe(Protocol):
    """The filesystem seam.

    Every check reads through this, so error and degradation branches are
    unit-testable with a fake probe instead of a fixture repo.
    """

    def exists(self, path: Path) -> bool:
        """Return whether `path` exists — as a file *or* as a directory."""
        ...

    def is_dir(self, path: Path) -> bool:
        """Return whether `path` exists and is a directory.

        Distinct from :meth:`exists`, which cannot tell a file from a
        directory: that is exactly why a directory sitting where ``papers.md``
        belongs went unreported until #131.
        """
        ...

    def read_text(self, path: Path) -> str:
        """Read `path` as UTF-8, raising `OSError` if that is not possible."""
        ...

    def glob(self, root: Path, pattern: str) -> list[Path]:
        """Return sorted matches of `pattern` under `root` (empty if absent)."""
        ...


class FsProbe:
    """The real filesystem."""

    def exists(self, path: Path) -> bool:
        """Return whether `path` exists."""
        return path.exists()

    def is_dir(self, path: Path) -> bool:
        """Return whether `path` exists and is a directory."""
        return path.is_dir()

    def read_text(self, path: Path) -> str:
        """Read `path` as UTF-8.

        A non-UTF-8 file raises `UnicodeDecodeError`, which subclasses
        `ValueError` and would therefore sail past an ``except OSError``; it is
        re-raised as an `OSError` so each check has one error branch, not two.

        :returns: The file's decoded contents.
        :raises OSError: If it cannot be read or is not valid UTF-8. Callers
            turn this into an ``unreadable`` finding — never into "valid and
            empty".
        """
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise OSError(f"{path} is not valid UTF-8") from exc

    def glob(self, root: Path, pattern: str) -> list[Path]:
        """Return sorted matches of `pattern` under `root` (empty if absent)."""
        if not root.is_dir():
            return []
        return sorted(root.glob(pattern))
