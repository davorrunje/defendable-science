"""Tests for the shared cache-root resolution (defendable-science#65).

The dataset content-addressed cache and the literature HTTP cache both live
under one configurable root (``cache_dir:`` in ``.defendable-science/config.yml``,
default ``.defendable-science/cache/``) so the directory ``research-init``
gitignores and the directory the CLI actually writes to cannot drift apart.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from defendable_science import cli


def _write_config(tmp_path: Path, body: str) -> None:
    cfg_dir = tmp_path / ".defendable-science"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yml").write_text(body, encoding="utf-8")


def test_cache_root_defaults_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Anchored to the repo root, not the cwd: the cache must not move when a
    # command is run from a paper directory (#122).
    assert cli._cache_root() == tmp_path / cli._DEFAULT_CACHE_ROOT
    assert Path(".defendable-science/cache") == cli._DEFAULT_CACHE_ROOT


def test_cache_root_reads_configured_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "cache_dir: .custom-cache\n")
    assert cli._cache_root() == tmp_path / ".custom-cache"


def test_cache_root_accepts_a_preloaded_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._cache_root({"cache_dir": ".preloaded"}) == tmp_path / ".preloaded"


def test_cache_root_rejects_non_string_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "cache_dir:\n  - not\n  - a-string\n")
    with pytest.raises(typer.Exit) as exc:
        cli._cache_root()
    assert exc.value.exit_code == 1


def test_dataset_cache_dir_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._dataset_cache_dir() == tmp_path / ".defendable-science/cache/datasets"


def test_dataset_cache_dir_follows_configured_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "cache_dir: .custom-cache\n")
    assert cli._dataset_cache_dir() == tmp_path / ".custom-cache/datasets"


def test_load_config_or_exit_returns_empty_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._load_config_or_exit() == {}


def test_load_config_or_exit_surfaces_invalid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "cache_dir: [unclosed\n")
    with pytest.raises(typer.Exit) as exc:
        cli._load_config_or_exit()
    assert exc.value.exit_code == 1


def test_repo_relative_accepts_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    absolute = Path("/tmp/external-cache")
    assert cli._repo_relative(absolute) == absolute


def test_repo_relative_anchors_relative_path_to_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    relative = ".local-cache"
    assert cli._repo_relative(relative) == tmp_path / relative


def test_repo_relative_confines_relative_paths_with_parent_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(cli.CacheDirError) as exc:
        cli._repo_relative("../../elsewhere")
    assert "escapes it" in str(exc.value)
    assert "../../elsewhere" in str(exc.value)


def test_repo_relative_error_message_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(cli.CacheDirError) as exc:
        cli._repo_relative("../sibling")
    error_msg = str(exc.value)
    assert "absolute path" in error_msg
    assert "deliberately external cache" in error_msg


def test_cache_root_confines_relative_cache_dir_that_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "cache_dir: ../../elsewhere\n")
    with pytest.raises(typer.Exit) as exc:
        cli._cache_root()
    assert exc.value.exit_code == 1


def test_cache_root_accepts_absolute_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    absolute_cache = Path("/tmp/shared-cache")
    _write_config(tmp_path, f"cache_dir: {absolute_cache}\n")
    assert cli._cache_root() == absolute_cache


def test_cache_root_accepts_safe_relative_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    safe_relative = ".custom/cache"
    _write_config(tmp_path, f"cache_dir: {safe_relative}\n")
    assert cli._cache_root() == tmp_path / safe_relative
