"""The content-addressed private mirror over ``rclone`` (substrate).

Keys are ``<base_path>/sha256/<hash>``. Every method shells out to ``rclone``
through the injectable `run` callable, so rclone is a Go binary invoked as a
subprocess — never a Python dependency — and the mirror is testable without it.
Shared by the ``dataset`` and ``literature`` front-ends
(``docs/design/04-substrate-and-contract.md`` §2.3).

**A mirror we could not reach is not a mirror that does not have it.** rclone's
exit code carries that distinction (:data:`ABSENT_EXIT_CODES`), and this module
keeps it: an absence is a ``False`` return, everything else is a raised
:class:`MirrorUnreachableError`. It is the same rule
:class:`~defendable_science.core.download.DownloadError` applies to HTTP status
codes one layer over — ``404`` is a fact about the object, a ``403`` or a
dropped connection is a fact about us.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - rclone is a trusted, fixed-arg subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from defendable_science.core.fixity import RetrievalError, bare_sha256

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The rclone exit codes that establish an **absence**: ``3`` (directory not
#: found) and ``4`` (file not found). The remote answered, and its answer was
#: "there is no such key". Every other non-zero exit — ``1`` syntax/usage,
#: ``2`` unknown error, ``5`` temporary error, ``6`` less-serious error,
#: ``7`` fatal error, ``8`` transfer limit exceeded — means the question was
#: never answered: an expired credential, a quota, a network outage or a
#: malformed remote all land there, and none of them is evidence about what the
#: mirror holds.
ABSENT_EXIT_CODES = frozenset({3, 4})


class MirrorUnreachableError(RetrievalError):
    """Raised when an rclone call failed for a reason that is not an absence.

    A :class:`~defendable_science.core.fixity.RetrievalError` subclass, so a
    caller that only wants "the hop failed" needs no change; a caller that must
    distinguish "the mirror does not hold this key" from "we could not ask"
    catches this instead. Reporting the second as the first is how a paper
    sitting behind an expired token becomes a line on a human's hand-download
    worklist.

    A **missing rclone binary** is deliberately *not* this exception: it is a
    plain `RetrievalError`, because it is a configuration fault that affects
    every entry of a run identically and should abort it rather than be
    absorbed into a per-entry report.

    :param message: The human-readable failure.
    :param returncode: The rclone exit code.
    :param stderr: What rclone wrote to stderr, decoded and stripped.
    """

    def __init__(self, message: str, *, returncode: int, stderr: str = "") -> None:
        """Record the failure alongside what rclone said about it."""
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class _Proc(Protocol):
    """The minimal completed-process shape a runner must return."""

    @property
    def returncode(self) -> int:
        """The process exit code."""

    @property
    def stderr(self) -> bytes | str | None:
        """The captured standard error, if the runner captured any."""


#: A subprocess runner with the ``subprocess.run`` shape (injectable for tests).
Runner = Callable[..., _Proc]


def _stderr_text(raw: bytes | str | None, *, limit: int = 400) -> str:
    """Return captured stderr as a bounded, single-paragraph string.

    :param raw: The captured stream (``bytes`` under ``capture_output``, ``str``
        under a text-mode runner, ``None`` when nothing was captured).
    :param limit: Maximum characters kept, so an rclone dump cannot swamp a
        report row.
    :returns: The decoded, stripped, truncated text (empty when there is none).
    """
    if raw is None:
        return ""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass
class Mirror:
    """A content-addressed private mirror over ``rclone``.

    Keys are ``<base_path>/sha256/<hash>``. All methods shell out to ``rclone``
    via the injectable `run` callable; nothing here is a Python dependency on
    rclone.

    :param remote: The rclone remote name (credentials live outside the repo).
    :param base_path: Base path under the remote.
    :param config_path: Optional ``--config`` path (untracked ``rclone.conf``).
    :param rclone_bin: The rclone executable name.
    :param run: The subprocess runner (defaults to :func:`subprocess.run`).
    :param env: Optional scoped secrets (e.g. ``RCLONE_CONFIG_<REMOTE>_*`` from
        the key store) merged over the process environment for each rclone call,
        so credentials need not live in a config file (ADR-0029). ``None`` keeps
        the inherited environment untouched.
    """

    remote: str
    base_path: str = ""
    config_path: str | None = None
    rclone_bin: str = "rclone"
    run: Runner = subprocess.run
    env: Mapping[str, str] | None = None

    def _target(self, sha256: str) -> str:
        key = f"{self.base_path.rstrip('/')}/sha256/{bare_sha256(sha256)}".lstrip("/")
        return f"{self.remote}:{key}"

    def _cmd(self, *args: str) -> list[str]:
        base = [self.rclone_bin]
        if self.config_path:
            base += ["--config", self.config_path]
        return [*base, *args]

    def _run_ok(self, *args: str) -> bool:
        """Run one rclone call, returning success and *raising* on non-absence.

        :param args: The rclone verb and its arguments.
        :returns: ``True`` on exit ``0``; ``False`` on an exit code in
            :data:`ABSENT_EXIT_CODES`, the only non-zero codes that mean the
            object is not there.
        :raises RetrievalError: If the rclone binary is not on ``PATH``.
        :raises MirrorUnreachableError: On any other non-zero exit — the call failed
            for a reason that says nothing about whether the key exists.
        """
        kwargs: dict[str, object] = {"capture_output": True, "check": False}
        if self.env is not None:
            kwargs["env"] = {**os.environ, **self.env}
        try:
            proc = self.run(  # nosec B603 - fixed rclone args, no shell
                self._cmd(*args), **kwargs
            )
        except FileNotFoundError as exc:  # rclone not installed
            raise RetrievalError(
                "rclone not found on PATH — install it or unset the mirror"
            ) from exc
        if proc.returncode == 0:
            return True
        if proc.returncode in ABSENT_EXIT_CODES:
            return False
        detail = _stderr_text(proc.stderr)
        raise MirrorUnreachableError(
            f"rclone {args[0]} on {self.remote!r} failed with exit "
            f"{proc.returncode}{': ' + detail if detail else ''} — the mirror "
            "could not be reached, so whether it holds this key is unknown "
            "(check credentials, quota and connectivity)",
            returncode=proc.returncode,
            stderr=detail,
        )

    def put(self, local: str | Path, sha256: str) -> None:
        """Copy `local` to the content-addressed mirror key.

        :param local: The local file to push.
        :param sha256: The checksum naming the mirror key.
        :raises RetrievalError: If the copy fails, including because `local` is
            not there (exit ``3``/``4``) or rclone is not installed.
        :raises MirrorUnreachableError: If the mirror could not be reached at all.
        """
        if not self._run_ok("copyto", str(local), self._target(sha256)):
            raise RetrievalError(
                f"rclone copyto to mirror failed for {bare_sha256(sha256)}"
            )

    def get(self, sha256: str, dst: str | Path) -> bool:
        """Copy from the mirror key to `dst`; return whether it succeeded.

        :param sha256: The checksum naming the mirror key.
        :param dst: Where to write the bytes (parents are created).
        :returns: ``True`` when the bytes were retrieved, ``False`` when the
            mirror answered that it does not hold the key. Never ``False`` for a
            failure to ask.
        :raises RetrievalError: If rclone is not installed.
        :raises MirrorUnreachableError: If the mirror could not be reached — the
            caller must not read that as an absence and fall through.
        """
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return self._run_ok("copyto", self._target(sha256), str(dst))

    def check(self, sha256: str) -> bool:
        """Return whether the mirror holds the key (transport-level probe).

        :param sha256: The checksum naming the mirror key.
        :returns: ``True`` when the key is there, ``False`` when the mirror
            answered that it is not. Never ``False`` for a failure to ask.
        :raises RetrievalError: If rclone is not installed.
        :raises MirrorUnreachableError: If the mirror could not be reached.
        """
        return self._run_ok("lsf", self._target(sha256))
