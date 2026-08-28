"""Tests for extraction's pure library: axes, cells, locators, validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from defendable_science.digest import extraction as ex

REAL = """## Concept matrix

<!-- rows = methods -->

| Method | guarantee type | scope | verifiability |
|---|---|---|---|
| *<prior work>* | | | |
| **This paper** | | | |
"""

TEMPLATE = """## Concept matrix

| Method | <attr 1> | <attr 2> | <attr 3> |
|---|---|---|---|
| **This paper** | | | |
"""


def _write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "positioning.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_axes_are_the_header_minus_the_row_label(tmp_path: Path) -> None:
    assert ex.axes_from_positioning(_write(tmp_path, REAL)) == [
        "guarantee type",
        "scope",
        "verifiability",
    ]


def test_a_string_path_is_accepted(tmp_path: Path) -> None:
    assert ex.axes_from_positioning(str(_write(tmp_path, REAL)))[0] == "guarantee type"


def test_unreplaced_placeholders_refuse(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="placeholder"):
        ex.axes_from_positioning(_write(tmp_path, TEMPLATE))


def test_one_replaced_axis_still_refuses_if_others_are_placeholders(
    tmp_path: Path,
) -> None:
    text = TEMPLATE.replace("<attr 1>", "guarantee type")
    with pytest.raises(ex.ExtractionError, match="placeholder"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_no_concept_matrix_section_refuses(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="no 'Concept matrix'"):
        ex.axes_from_positioning(_write(tmp_path, "## Baselines\n\nprose\n"))


def test_section_present_but_no_table_refuses(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="no table"):
        ex.axes_from_positioning(_write(tmp_path, "## Concept matrix\n\nTBD\n"))


def test_a_differently_cased_heading_still_reports_the_missing_table(
    tmp_path: Path,
) -> None:
    """The two refusals are told apart the way the parser finds the section.

    ``parse_document`` matches a heading case-insensitively, so the
    discriminator between "no section" and "section without a table" must too;
    a case-sensitive substring test would blame the author for a missing
    section they plainly wrote.
    """
    with pytest.raises(ex.ExtractionError, match="no table"):
        ex.axes_from_positioning(_write(tmp_path, "### concept MATRIX\n\nTBD\n"))


def test_header_with_only_a_row_label_refuses(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method |\n|---|\n| a |\n"
    with pytest.raises(ex.ExtractionError, match="no comparison axes"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_a_blank_axis_name_refuses(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method | scope |  |\n|---|---|---|\n| a | | |\n"
    with pytest.raises(ex.ExtractionError, match="unnamed"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_missing_file_refuses_actionably(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="not found"):
        ex.axes_from_positioning(tmp_path / "absent.md")


def test_duplicate_axis_names_refuse(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method | a | a |\n|---|---|---|\n| x | | |\n"
    with pytest.raises(ex.ExtractionError, match="duplicate"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_a_ragged_matrix_refuses_as_an_extraction_error(tmp_path: Path) -> None:
    """A ragged row is the author's document to fix, reported against its path.

    ``parse_document`` raises :class:`~defendable_science.core.mdtable.TableError`
    here; letting that escape would make callers handle a second exception type
    for the same "your positioning document is unusable" condition.
    """
    text = "## Concept matrix\n\n| Method | a | b |\n|---|---|---|\n| x | |\n"
    with pytest.raises(ex.ExtractionError, match="ragged") as caught:
        ex.axes_from_positioning(_write(tmp_path, text))
    assert "positioning.md" in str(caught.value)
