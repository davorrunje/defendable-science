"""Tests for :mod:`defendable_science.core.config`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from defendable_science.core import load_config
from defendable_science.core.config import find_repo_root


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.yml") == {}


def test_reads_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "tooling:\n  cli: defendable-science\n  version: 0.0.0\n", encoding="utf-8"
    )
    config = load_config(path)
    assert config["tooling"]["cli"] == "defendable-science"


def test_blank_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("", encoding="utf-8")
    assert load_config(path) == {}


def test_non_mapping_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a YAML mapping"):
        load_config(path)


def test_malformed_yaml_is_clean_value_error(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    # Unbalanced flow sequence — a YAMLError, surfaced as a clean ValueError.
    path.write_text("literature: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_config(path)


def test_find_repo_root_walks_up_to_the_config_dir(tmp_path: Path) -> None:
    (tmp_path / ".defendable-science").mkdir()
    nested = tmp_path / "docs" / "research" / "depth-collapse"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_returns_the_start_when_there_is_no_config_dir(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == nested.resolve()


def test_find_repo_root_defaults_to_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".defendable-science").mkdir()
    monkeypatch.chdir(tmp_path)

    assert find_repo_root() == tmp_path.resolve()
