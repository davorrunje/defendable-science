"""End-to-end CLI coverage for the dataset commands + error paths (#16 sweep)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.dataset import retrieval as retrieval_mod

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def _tier_a_project(tmp_path: Path) -> Path:
    """Create a cwd with a Tier-A datasets.yml + its in-repo file; return cwd."""
    (tmp_path / "data").mkdir()
    payload = b"tier-a bytes"
    (tmp_path / "data" / "f.bin").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "datasets.yml").write_text(
        f"""
datasets:
  - id: ds-a
    version: "1.0.0"
    tier: A
    license: CC0-1.0
    redistributable: true
    access: open
    files:
      - path: data/f.bin
        sha256: {digest}
    datasheet: datasheets/ds-a.md
""",
        encoding="utf-8",
    )
    return tmp_path


def test_validate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "validate"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True


def test_validate_malformed_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "validate"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_ingest_bad_file_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["dataset", "ingest", "nope.json"]).exit_code == 1


def test_emit_all_and_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    all_ = runner.invoke(app, ["dataset", "emit", "--all"])
    assert all_.exit_code == 0
    assert isinstance(json.loads(all_.stdout), list)
    assert runner.invoke(app, ["dataset", "emit", "ghost"]).exit_code == 1


def test_fetch_and_verify_tier_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    fetch = runner.invoke(app, ["dataset", "fetch", "ds-a"])
    assert fetch.exit_code == 0
    assert json.loads(fetch.stdout) == ["data/f.bin"]
    verify = runner.invoke(app, ["dataset", "verify", "ds-a"])
    assert verify.exit_code == 0
    assert json.loads(verify.stdout)["ok"] is True


def test_fetch_verify_audit_use_configured_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dataset fetch/verify/audit resolve the cache dir from config.yml (#65).

    The cache directory the CLI actually passes to :mod:`retrieval` must be
    exactly the one ``research-init`` gitignores — sourced from
    ``cache_dir:`` instead of a hardcoded literal, so the two cannot drift.
    """
    monkeypatch.chdir(_tier_a_project(tmp_path))
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir: .custom-cache\n", encoding="utf-8")

    seen: list[Path] = []
    original_fetch = retrieval_mod.fetch
    original_verify = retrieval_mod.verify
    original_audit = retrieval_mod.audit

    def _fetch_spy(entry, *, cache_dir, mirror=None, **kw):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_fetch(entry, cache_dir=cache_dir, mirror=mirror, **kw)

    def _verify_spy(entry, *, cache_dir):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_verify(entry, cache_dir=cache_dir)

    def _audit_spy(manifest, *, cache_dir, mirror=None):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_audit(manifest, cache_dir=cache_dir, mirror=mirror)

    monkeypatch.setattr(retrieval_mod, "fetch", _fetch_spy)
    monkeypatch.setattr(retrieval_mod, "verify", _verify_spy)
    monkeypatch.setattr(retrieval_mod, "audit", _audit_spy)

    assert runner.invoke(app, ["dataset", "fetch", "ds-a"]).exit_code == 0
    assert runner.invoke(app, ["dataset", "verify", "ds-a"]).exit_code == 0
    assert runner.invoke(app, ["dataset", "audit"]).exit_code == 0

    # `audit` internally re-runs `verify`, so more than 3 calls may land here —
    # what matters is that every one of them got the *configured* root, never
    # the old hardcoded ``.defendable-science/cache/datasets`` literal.
    expected = Path(".custom-cache/datasets")
    assert len(seen) >= 3
    assert all(path == expected for path in seen)


def test_fetch_exits_1_on_invalid_cache_dir_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir:\n  - nope\n", encoding="utf-8")
    result = runner.invoke(app, ["dataset", "fetch", "ds-a"])
    assert result.exit_code == 1
    assert "cache_dir" in result.stderr


def test_fetch_unknown_id_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    assert runner.invoke(app, ["dataset", "fetch", "ghost"]).exit_code == 1


def test_verify_corrupt_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    (tmp_path / "data" / "f.bin").write_bytes(b"tampered")
    assert runner.invoke(app, ["dataset", "verify", "ds-a"]).exit_code == 1


def test_mirror_without_config_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "mirror", "ds-a"])
    assert result.exit_code == 1
    assert "no mirror configured" in result.stderr


def test_audit_whole_and_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    whole = runner.invoke(app, ["dataset", "audit"])
    assert whole.exit_code == 0
    assert json.loads(whole.stdout)["ok"] is True
    by_id = runner.invoke(app, ["dataset", "audit", "ds-a"])
    assert by_id.exit_code == 0


def test_audit_fails_on_missing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    (tmp_path / "data" / "f.bin").unlink()
    result = runner.invoke(app, ["dataset", "audit"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_emit_no_arg_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "emit"])
    assert result.exit_code == 1
    assert "give a dataset id or --all" in result.stderr


def test_fetch_tier_c_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "datasets.yml").write_text(
        f"""
datasets:
  - id: ds-c
    version: "1.0.0"
    tier: C
    license: proprietary
    redistributable: false
    access: gated
    files:
      - path: data/c.bin
        sha256: {"d" * 64}
    datasheet: datasheets/ds-c.md
    instructions: email the authors
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "fetch", "ds-c"])
    assert result.exit_code == 1
    assert "gated" in result.stderr


def test_mirror_success_with_fake_rclone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from defendable_science import cli
    from defendable_science.dataset import retrieval as retrieval_mod

    monkeypatch.chdir(_tier_a_project(tmp_path))

    class _Proc:
        returncode = 0
        stderr = b""

    def _ok(args: list[str], **_kw: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr(
        cli, "_mirror_from", lambda _m: retrieval_mod.Mirror(remote="store", run=_ok)
    )
    result = runner.invoke(app, ["dataset", "mirror", "ds-a"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["mirrored"] == "ds-a"


def test_emit_malformed_manifest_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bad.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "emit", "x", "--manifest", "bad.yml"])
    assert result.exit_code == 1


def test_fetch_malformed_manifest_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "fetch", "x"])
    assert result.exit_code == 1
    assert "manifest error" in result.stderr


def test_mirror_retrieval_error_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text(
        f"""
mirror:
  rclone_remote: store
  base_path: base
datasets:
  - id: ds-c
    version: "1.0.0"
    tier: C
    license: proprietary
    redistributable: false
    access: gated
    files:
      - path: data/c.bin
        sha256: {"d" * 64}
    datasheet: datasheets/ds-c.md
    instructions: email the authors
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "mirror", "ds-c"])
    assert result.exit_code == 1
    assert "mirror failed" in result.stderr
