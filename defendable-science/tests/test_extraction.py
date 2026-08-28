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


def test_the_missing_section_remedy_is_a_skill_request_not_a_shell_command(
    tmp_path: Path,
) -> None:
    """`literature position` is a skill mode; there is no such CLI command.

    Rendering it alone in backticks inside a CLI error reads as something to
    paste into a terminal, where it fails — the defect class fixed across the
    user guide in #102/#109.
    """
    with pytest.raises(ex.ExtractionError) as caught:
        ex.axes_from_positioning(_write(tmp_path, "## Baselines\n\nprose\n"))
    message = str(caught.value)
    assert "ask the `literature` skill" in message
    assert "`literature position" not in message


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


def test_a_table_missing_its_separator_says_so(tmp_path: Path) -> None:
    """A header plus rows with no ``|---|`` is a table, not an absent one.

    ``parse_document`` reports this as ``header=None, saw_table_shape=True``.
    Without the discrimination the author is told the section "holds no table"
    about a matrix sitting in front of them, with nothing to act on.
    """
    text = "## Concept matrix\n\n| Method | scope |\n| a | b |\n"
    with pytest.raises(ex.ExtractionError, match=r"missing its .* separator"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_a_blank_axis_name_refuses_and_says_which_column(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method | scope |  |\n|---|---|---|\n| a | | |\n"
    with pytest.raises(ex.ExtractionError, match=r"unnamed columns at position\(s\)"):
        ex.axes_from_positioning(_write(tmp_path, text))
    with pytest.raises(ex.ExtractionError, match=r"\[3\]"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_missing_file_refuses_actionably(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="not found"):
        ex.axes_from_positioning(tmp_path / "absent.md")


def test_duplicate_axis_names_refuse(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method | a | a |\n|---|---|---|\n| x | | |\n"
    with pytest.raises(ex.ExtractionError, match="duplicate"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_the_duplicate_refusal_names_only_the_repeats_and_a_remedy(
    tmp_path: Path,
) -> None:
    text = (
        "## Concept matrix\n\n| Method | scope | a | verifiability | a |\n"
        "|---|---|---|---|---|\n| x | | | | |\n"
    )
    with pytest.raises(ex.ExtractionError) as caught:
        ex.axes_from_positioning(_write(tmp_path, text))
    message = str(caught.value)
    assert "['a']" in message
    assert "scope" not in message  # the innocent axes are not paraded as suspects
    assert "rename" in message


def test_a_ragged_matrix_refuses_as_an_extraction_error(tmp_path: Path) -> None:
    """A ragged row is the author's document to fix, reported against its path.

    ``parse_document`` raises :class:`~defendable_science.core.mdtable.TableError`
    here; letting that escape would make callers handle a second exception type
    for the same "your positioning document is unusable" condition.
    """
    text = "## Concept matrix\n\n| Method | a | b |\n|---|---|---|\n| x | |\n"
    with pytest.raises(ex.ExtractionError, match="ragged concept-matrix row") as caught:
        ex.axes_from_positioning(_write(tmp_path, text))
    assert "positioning.md" in str(caught.value)


# --- cells, locators, validation --------------------------------------------

AXES = ["guarantee type", "scope"]


def _cell(**kw: object) -> ex.Cell:
    base: dict[str, object] = {
        "citekey": "sill1997",
        "axis": "guarantee type",
        "value": "architectural",
        "locator": "§2, Eq. (3)",
    }
    base.update(kw)
    return ex.Cell(**base)  # type: ignore[arg-type]


def _full(citekey: str = "sill1997") -> list[ex.Cell]:
    return [
        _cell(citekey=citekey, axis="guarantee type"),
        _cell(citekey=citekey, axis="scope", locator="p. 4"),
    ]


PATTERNS = ex.compile_locator_patterns()


@pytest.mark.parametrize(
    "locator",
    [
        "§3",
        "§3.2",
        "§3.2.1",
        "Section 3",
        "Sec. 3",
        "p. 7",
        "pp. 7-9",
        "pp. 7–9",  # noqa: RUF001 — an en dash is what a PDF page range pastes as
        "page 7",
        "Eq. (4)",
        "Equation 4",
        "Table 2",
        "Fig. 5",
        "Figure 5",
        "Alg. 1",
        "Thm. 2",
        "Theorem 2",
        "Lemma 3",
        "Def. 1",
        "§3, Eq. (4)",
        "p. 7, Table 2",
    ],
)
def test_well_formed_locators_are_accepted(locator: str) -> None:
    assert ex.is_valid_locator(locator, PATTERNS)


@pytest.mark.parametrize(
    "locator",
    [
        "see paper",
        "somewhere in §3",
        "the introduction",
        "passim",
        "",
        "   ",
        "throughout",
        "as discussed",
    ],
)
def test_vague_locators_are_refused(locator: str) -> None:
    assert not ex.is_valid_locator(locator, PATTERNS)


def test_extra_patterns_extend_the_default_set() -> None:
    patterns = ex.compile_locator_patterns([r"cl\. \d+"])
    assert ex.is_valid_locator("cl. 14", patterns)
    assert ex.is_valid_locator("§3", patterns)


def test_an_invalid_configured_pattern_refuses_by_name() -> None:
    """A broken config regex must name itself, not surface as a raw `re.error`."""
    with pytest.raises(ex.ExtractionError, match=r"invalid locator pattern"):
        ex.compile_locator_patterns(["cl\\. (\\d+"])


def test_patterns_that_clash_only_once_combined_refuse_readably() -> None:
    """Each compiles alone; joining them does not. That must not be a traceback.

    The patterns come from the user's `literature.extraction.locator_patterns`,
    so a raw ``re.error`` would quote a character offset into a combined
    pattern they never wrote.
    """
    with pytest.raises(ex.ExtractionError, match="cannot be combined") as caught:
        ex.compile_locator_patterns([r"(?P<n>\d+)", r"(?P<n>x\d+)"])
    message = str(caught.value)
    assert "(?P<n>x" in message  # the offending set is named, not just the clash
    assert "position" not in message  # no offset into a pattern nobody wrote


def test_a_complete_paper_is_accepted() -> None:
    accepted, rejections = ex.validate(_full(), AXES, PATTERNS)
    assert rejections == []
    assert sorted(c.axis for c in accepted["sill1997"]) == ["guarantee type", "scope"]


def test_a_missing_axis_rejects_the_whole_paper() -> None:
    accepted, rejections = ex.validate(_full()[:1], AXES, PATTERNS)
    assert accepted == {}
    assert any("scope" in r.reason and "missing" in r.reason for r in rejections)


def test_an_invented_axis_rejects_the_whole_paper() -> None:
    cells = [*_full(), _cell(axis="made up", locator="§9")]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert accepted == {}
    assert any("not a matrix axis" in r.reason for r in rejections)


def test_a_bad_locator_rejects_the_whole_paper_not_just_the_cell() -> None:
    cells = [_cell(), _cell(axis="scope", locator="see paper")]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert accepted == {}
    assert any("see paper" in r.reason for r in rejections)


def test_one_bad_paper_does_not_reject_a_good_one() -> None:
    cells = [*_full("good"), *_full("bad")[:1]]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert set(accepted) == {"good"}
    assert {r.citekey for r in rejections} == {"bad"}


def test_not_addressed_needs_a_justification_not_a_locator() -> None:
    cells = [
        _cell(),
        _cell(
            axis="scope",
            value=ex.NOT_ADDRESSED,
            locator=None,
            justification="scoped to full monotonicity in §1",
        ),
    ]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert rejections == []
    assert len(accepted["sill1997"]) == 2


def test_not_addressed_without_a_justification_is_rejected() -> None:
    cells = [_cell(), _cell(axis="scope", value=ex.NOT_ADDRESSED, locator=None)]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("justification" in r.reason for r in rejections)


def test_not_addressed_with_a_blank_justification_is_rejected() -> None:
    cells = [
        _cell(),
        _cell(
            axis="scope",
            value=ex.NOT_ADDRESSED,
            locator=None,
            justification="   ",
        ),
    ]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("justification" in r.reason for r in rejections)


def test_a_normal_cell_with_no_locator_is_rejected() -> None:
    cells = [_cell(), _cell(axis="scope", locator=None)]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("locator" in r.reason for r in rejections)


def test_a_duplicated_axis_for_one_paper_is_rejected() -> None:
    cells = [*_full(), _cell(axis="scope", locator="p. 9")]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("twice" in r.reason for r in rejections)


def test_a_rejection_names_the_axis_it_is_about() -> None:
    """A count sends the reader hunting; the named cell does not (spec §7.4)."""
    _, rejections = ex.validate(
        [_cell(), _cell(axis="scope", locator="see paper")], AXES, PATTERNS
    )
    assert [(r.citekey, r.axis) for r in rejections] == [("sill1997", "scope")]


def test_a_missing_axis_rejection_carries_the_axis_not_none() -> None:
    _, rejections = ex.validate(_full()[:1], AXES, PATTERNS)
    assert [r.axis for r in rejections] == ["scope"]


def test_cell_from_mapping_builds_a_cell() -> None:
    cell = ex.cell_from_mapping(
        {"citekey": "k", "axis": "a", "value": "v", "locator": "§3"}
    )
    assert cell == ex.Cell(citekey="k", axis="a", value="v", locator="§3")


def test_cell_from_mapping_rejects_a_non_string_field() -> None:
    with pytest.raises(ex.ExtractionError, match="citekey"):
        ex.cell_from_mapping({"citekey": 7, "axis": "a", "value": "v"})


def test_cell_from_mapping_rejects_an_unknown_field() -> None:
    with pytest.raises(ex.ExtractionError, match="unknown"):
        ex.cell_from_mapping({"citekey": "k", "axis": "a", "value": "v", "bogus": "x"})


def test_cell_from_mapping_rejects_a_missing_required_field() -> None:
    with pytest.raises(ex.ExtractionError, match="malformed"):
        ex.cell_from_mapping({"citekey": "k", "axis": "a"})


def test_a_rejection_renders_as_one_line_naming_the_paper_and_the_cell() -> None:
    """Spec §7.4: a refusal names the offending cell, never just a count."""
    _, rejections = ex.validate(
        [_cell(), _cell(axis="scope", locator="see paper")], AXES, PATTERNS
    )
    line = ex.render_rejection(rejections[0])
    assert line.startswith("sill1997 / axis 'scope':")
    assert "'see paper' matches no known form" in line


def test_a_whole_paper_rejection_renders_without_inventing_an_axis() -> None:
    line = ex.render_rejection(ex.Rejection("sill1997", None, "no cells at all"))
    assert line == "sill1997 / no cells at all"
