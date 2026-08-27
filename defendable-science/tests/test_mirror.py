"""Tests for the private mirror over ``rclone`` (defendable-science#3)."""

from __future__ import annotations

import pytest

from defendable_science.core import fixity as fx
from defendable_science.core import mirror as mirror_mod


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


def test_mirror_check_and_target() -> None:
    rclone = FakeRclone(present=True)
    mirror = mirror_mod.Mirror(
        remote="store", base_path="proj", config_path="c.conf", run=rclone
    )
    assert mirror.check("sha256:" + "a" * 64) is True
    assert rclone.calls[-1][:3] == ["rclone", "--config", "c.conf"]
    assert rclone.calls[-1][-1] == "store:proj/sha256/" + "a" * 64


def test_mirror_missing_binary_is_actionable() -> None:
    def _no_binary(args: list[str], **_kw: object) -> FakeProc:
        raise FileNotFoundError("rclone")

    mirror = mirror_mod.Mirror(remote="store", run=_no_binary)
    with pytest.raises(fx.RetrievalError, match="rclone not found"):
        mirror.check("a" * 64)


def test_mirror_forwards_scoped_env_merged_over_process_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    captured: dict[str, object] = {}

    def _runner(args: list[str], **kw: object) -> FakeProc:
        captured.update(kw)
        return FakeProc(0)

    mirror = mirror_mod.Mirror(
        remote="store",
        run=_runner,
        env={"RCLONE_CONFIG_STORE_TYPE": "s3"},
    )
    assert mirror.check("a" * 64) is True
    passed = captured["env"]
    assert isinstance(passed, dict)
    # scoped secret is present …
    assert passed["RCLONE_CONFIG_STORE_TYPE"] == "s3"
    # … merged over the inherited environment (PATH survives).
    assert passed["PATH"] == "/usr/bin"


def test_mirror_without_env_passes_no_env_kwarg() -> None:
    captured: dict[str, object] = {}

    def _runner(args: list[str], **kw: object) -> FakeProc:
        captured.update(kw)
        return FakeProc(0)

    mirror_mod.Mirror(remote="store", run=_runner).check("a" * 64)
    assert "env" not in captured


def test_mirror_put_failure_raises() -> None:
    def _fail(args: list[str], **_kw: object) -> FakeProc:
        return FakeProc(1)

    mirror = mirror_mod.Mirror(remote="s", run=_fail)
    with pytest.raises(fx.RetrievalError, match="copyto to mirror failed"):
        mirror.put("/tmp/x", "a" * 64)
