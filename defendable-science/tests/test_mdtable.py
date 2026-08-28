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


# --- fenced code blocks (task-8 ruling AG) --------------------------------------

FENCED_EXAMPLE = """# Positioning

A matrix looks like this:

```markdown
| Method | example axis |
|---|---|
| someone2020 | illustrative |
```

## Concept matrix

| Method | guarantee |
|---|---|
| sill1997 | architectural |
"""


def test_a_fenced_pipe_table_before_the_real_one_is_not_selected() -> None:
    doc = md.parse_document(FENCED_EXAMPLE)
    assert doc.header == ["Method", "guarantee"]
    assert doc.rows == [{"Method": "sill1997", "guarantee": "architectural"}]


def test_splicing_never_writes_into_a_fenced_example_table() -> None:
    """The write lands on the real table; the fence is byte-identical."""
    doc = md.parse_document(FENCED_EXAMPLE)
    assert doc.header is not None
    rows = [*doc.rows, {"Method": "new2026", "guarantee": "learned"}]
    out = md.splice(doc.preamble, doc.postamble, doc.header, rows)
    fence = FENCED_EXAMPLE[
        FENCED_EXAMPLE.index("```markdown") : FENCED_EXAMPLE.index("## Concept")
    ]
    assert fence in out
    assert out == FENCED_EXAMPLE.replace(
        "| sill1997 | architectural |\n",
        "| sill1997 | architectural |\n| new2026 | learned |\n",
    )


def test_a_document_whose_only_table_is_fenced_has_no_table() -> None:
    text = "# Doc\n\n```\n| a | b |\n|---|---|\n| 1 | 2 |\n```\n\nprose\n"
    doc = md.parse_document(text)
    assert doc.header is None
    assert doc.preamble == text
    assert not doc.saw_table_shape


def test_a_heading_inside_a_fence_does_not_open_a_section() -> None:
    text = (
        "# Doc\n\n```\n## Concept matrix\n\n| a |\n|---|\n| fake |\n```\n\n"
        "## Concept matrix\n\n| b |\n|---|\n| real |\n"
    )
    doc = md.parse_document(text, under_heading="Concept matrix")
    assert doc.header == ["b"]
    assert doc.rows == [{"b": "real"}]


def test_a_heading_inside_a_fence_does_not_close_a_section() -> None:
    text = "## A\n\n```\n## B\n```\n\n| x |\n|---|\n| 1 |\n"
    doc = md.parse_document(text, under_heading="A")
    assert doc.header == ["x"]


def test_a_tilde_fence_is_honoured() -> None:
    text = "~~~\n| a | b |\n|---|---|\n~~~\n\n| c |\n|---|\n| 1 |\n"
    assert md.parse_document(text).header == ["c"]


def test_a_fence_is_closed_only_by_its_own_character() -> None:
    # The ~~~ line is content inside the backtick fence, not a close, so the
    # pipe table that follows it is still fenced.
    text = "```\n~~~\n| a | b |\n|---|---|\n```\n\n| c |\n|---|\n| 1 |\n"
    assert md.parse_document(text).header == ["c"]


def test_a_shorter_closing_fence_does_not_close() -> None:
    text = "````\n```\n| a | b |\n|---|---|\n````\n\n| c |\n|---|\n| 1 |\n"
    assert md.parse_document(text).header == ["c"]


def test_a_longer_closing_fence_closes() -> None:
    text = "```\ntext\n`````\n\n| c |\n|---|\n| 1 |\n"
    assert md.parse_document(text).header == ["c"]


def test_a_closing_fence_may_not_carry_an_info_string() -> None:
    text = "```\n``` still open\n| a | b |\n|---|---|\n```\n\n| c |\n|---|\n| 1 |\n"
    assert md.parse_document(text).header == ["c"]


def test_an_unclosed_fence_runs_to_the_end_of_the_document() -> None:
    text = "# Doc\n\n```\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    doc = md.parse_document(text)
    assert doc.header is None
    assert doc.preamble == text


def test_two_sections_with_the_same_heading_are_refused() -> None:
    """Which section is *the* section cannot be guessed, so nothing is located."""
    text = (
        "## Concept matrix\n\n| a |\n|---|\n| 1 |\n\n"
        "## Concept matrix\n\n| b |\n|---|\n| 2 |\n"
    )
    with pytest.raises(
        md.AmbiguousSectionError, match=r"'Concept matrix' names 2 headings"
    ):
        md.parse_document(text, under_heading="Concept matrix")


def test_duplicate_headings_are_matched_case_insensitively() -> None:
    text = "## Concept matrix\n\n| a |\n|---|\n\n### concept MATRIX\n\nprose\n"
    with pytest.raises(md.AmbiguousSectionError):
        md.parse_document(text, under_heading="Concept matrix")


def test_a_duplicate_heading_inside_a_fence_is_not_ambiguity() -> None:
    """A heading *shown* in a code block is documentation, not a second section."""
    text = (
        "## Concept matrix\n\n| b |\n|---|\n| real |\n\n"
        "```\n## Concept matrix\n| a |\n|---|\n| fake |\n```\n"
    )
    doc = md.parse_document(text, under_heading="Concept matrix")
    assert doc.rows == [{"b": "real"}]


def test_an_ambiguous_section_is_a_table_error() -> None:
    # Callers that already catch TableError keep catching this one.
    assert issubclass(md.AmbiguousSectionError, md.TableError)


def test_a_windowed_section_holding_two_tables_is_refused() -> None:
    """A legend above the matrix: writing into the first would destroy it."""
    text = (
        "## Concept matrix\n\nLegend:\n\n| symbol | meaning |\n|---|---|\n"
        "| + | holds |\n\nThe matrix:\n\n| Method | axis |\n|---|---|\n| a | b |\n"
    )
    with pytest.raises(md.AmbiguousSectionError, match=r"holds 2 tables"):
        md.parse_document(text, under_heading="Concept matrix")


def test_a_second_table_inside_a_fence_is_not_a_second_table() -> None:
    """The over-correction guard: an illustration must not force a refusal."""
    text = (
        "## Concept matrix\n\n```\n| shown | only |\n|---|---|\n| x | y |\n```\n\n"
        "| Method | axis |\n|---|---|\n| a | b |\n"
    )
    doc = md.parse_document(text, under_heading="Concept matrix")
    assert doc.header == ["Method", "axis"]
    assert doc.rows == [{"Method": "a", "axis": "b"}]


def test_a_windowed_section_with_one_table_is_unaffected() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert doc.header == ["Method", "guarantee", "scope"]


def test_an_unwindowed_document_with_several_tables_still_takes_the_first() -> None:
    """The regression that protects `backlog.py`: no refusal without a window.

    A whole-document call legitimately meets many tables — a backlog file's
    prose routinely holds more than one — so the refusal is scoped to calls
    that named a section. Simplifying it to apply everywhere breaks them.
    """
    doc = md.parse_document(TWO_TABLES)
    assert doc.header == ["Baseline", "Why"]
    assert doc.rows == [{"Baseline": "ridge", "Why": "simplest floor"}]
    # And the round trip still preserves the second table verbatim.
    assert md.splice(doc.preamble, doc.postamble, doc.header, doc.rows) == TWO_TABLES


def test_a_table_after_the_windowed_section_is_not_a_second_table() -> None:
    text = (
        "## Concept matrix\n\n| Method | axis |\n|---|---|\n| a | b |\n\n"
        "## Baselines\n\n| Baseline | Why |\n|---|---|\n| ridge | floor |\n"
    )
    assert md.parse_document(text, under_heading="Concept matrix").header == [
        "Method",
        "axis",
    ]
