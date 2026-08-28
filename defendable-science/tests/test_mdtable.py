"""Tests for the shared host-preserving markdown-table core."""

from __future__ import annotations

import pytest

from defendable_science.core import mdtable as md

TWO_TABLES = """# Positioning

## Baselines

| Baseline | Why |
|---|---|
| ridge | simplest floor |

## Concept matrix

<!-- rows = methods -->

| Method | guarantee | scope |
|---|---|---|
| sill1997 | architectural | full |

## Notes

trailing prose
"""


def test_parse_document_takes_the_first_table_by_default() -> None:
    doc = md.parse_document(TWO_TABLES)
    assert doc.header == ["Baseline", "Why"]


def test_under_heading_targets_that_section_s_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert doc.header == ["Method", "guarantee", "scope"]
    assert doc.rows == [
        {"Method": "sill1997", "guarantee": "architectural", "scope": "full"}
    ]


def test_under_heading_round_trips_the_whole_document() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert doc.header is not None
    out = md.splice(doc.preamble, doc.postamble, doc.header, doc.rows)
    assert out == TWO_TABLES


def test_under_heading_preserves_the_other_table_verbatim() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert "| ridge | simplest floor |" in doc.preamble
    assert "trailing prose" in doc.postamble


def test_under_heading_absent_yields_no_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Nonexistent")
    assert doc.header is None
    assert doc.preamble == TWO_TABLES


def test_under_heading_section_with_no_table_yields_no_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Notes")
    assert doc.header is None


def test_under_heading_stops_at_the_next_heading() -> None:
    text = "## A\n\nprose\n\n## B\n\n| X |\n|---|\n| 1 |\n"
    assert md.parse_document(text, under_heading="A").header is None
    assert md.parse_document(text, under_heading="B").header == ["X"]


def test_under_heading_matches_any_heading_level() -> None:
    text = "### Concept matrix\n\n| M |\n|---|\n| a |\n"
    assert md.parse_document(text, under_heading="Concept matrix").header == ["M"]


def test_under_heading_is_case_insensitive() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="  concept MATRIX ")
    assert doc.header == ["Method", "guarantee", "scope"]


def test_window_does_not_swallow_the_next_section_s_rows() -> None:
    # A heading that itself contains a pipe would otherwise be read as a data
    # row of the previous section's table.
    text = "## A\n\n| X |\n|---|\n| 1 |\n## B | C\n\nprose\n"
    doc = md.parse_document(text, under_heading="A")
    assert doc.rows == [{"X": "1"}]
    assert doc.postamble == "## B | C\n\nprose\n"


def test_ragged_row_raises_with_the_default_label() -> None:
    text = "| a | b |\n|---|---|\n| 1 |\n"
    with pytest.raises(md.TableError, match="ragged table row"):
        md.parse_document(text)


def test_ragged_row_uses_the_caller_s_label() -> None:
    text = "| a | b |\n|---|---|\n| 1 |\n"
    with pytest.raises(md.TableError, match="ragged concept-matrix row"):
        md.parse_document(text, row_label="concept-matrix")


def test_separator_before_any_header_is_ignored() -> None:
    assert md.parse_document("|---|---|\n").header is None


def test_table_shape_without_a_separator_is_flagged() -> None:
    doc = md.parse_document("| a | b |\n| 1 | 2 |\n")
    assert doc.header is None
    assert doc.saw_table_shape


def test_escape_cell_neutralizes_pipes_and_newlines() -> None:
    assert md.escape_cell("a|b\nc") == r"a\|b c"


def test_split_cells_without_borders() -> None:
    assert md.split_cells("a | b | c") == ["a", "b", "c"]


def test_is_separator_rejects_an_empty_cell() -> None:
    assert md.is_separator(["---", ":-:"])
    assert not md.is_separator([""])
    assert not md.is_separator([])


def test_splice_terminates_a_preamble_that_lacks_a_newline() -> None:
    out = md.splice("intro", "", ["a"], [{"a": "1"}])
    assert out == "intro\n| a |\n|---|\n| 1 |\n"
