"""The content-addressed private mirror over ``rclone`` (substrate).

Keys are ``<base_path>/sha256/<hash>``. Every method shells out to ``rclone``
through the injectable `run` callable, so rclone is a Go binary invoked as a
subprocess — never a Python dependency — and the mirror is testable without it.
Shared by the ``dataset`` and ``literature`` front-ends
(``docs/design/04-substrate-and-contract.md`` §2.3).
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


class _Proc(Protocol):
    """The minimal completed-process shape a runner must return."""

    returncode: int


#: A subprocess runner with the ``subprocess.run`` shape (injectable for tests).
Runner = Callable[..., _Proc]


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
        return proc.returncode == 0

    def put(self, local: str | Path, sha256: str) -> None:
        """Copy `local` to the content-addressed mirror key."""
        if not self._run_ok("copyto", str(local), self._target(sha256)):
            raise RetrievalError(
                f"rclone copyto to mirror failed for {bare_sha256(sha256)}"
            )

    def get(self, sha256: str, dst: str | Path) -> bool:
        """Copy from the mirror key to `dst`; return whether it succeeded."""
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return self._run_ok("copyto", self._target(sha256), str(dst))

    def check(self, sha256: str) -> bool:
        """Return whether the mirror holds the key (transport-level probe)."""
        return self._run_ok("lsf", self._target(sha256))
