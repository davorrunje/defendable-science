"""Tests for :mod:`defendable_science.core.config`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from defendable_science.core import load_config


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
