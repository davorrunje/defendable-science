"""Tests for extraction's artifact writer and the shared log appender."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from defendable_science.core.frontmatter import split_frontmatter
from defendable_science.digest import artifact as art
from defendable_science.digest import extraction as ex

if TYPE_CHECKING:
    from pathlib import Path

DATE = "2026-08-28"
CITEKEY = "sill1997monotonic"

#: A depth-mode artifact: an ``understanding`` block, a trailing comment, and
#: prose. Every byte of it must survive an extraction write.
DEPTH_ARTIFACT = """---
title: Monotonic networks
status:
  understanding: {"status": "gaps", "unresolved": ["why convexity matters"]}  # defend
  last-updated: 2026-08-01
---

# sill1997monotonic

The author's own summary prose.
"""

UNDERSTANDING_LINE = (
    '  understanding: {"status": "gaps", "unresolved": '
    '["why convexity matters"]}  # defend'
)


def _cells(citekey: str = CITEKEY) -> list[ex.Cell]:
    """Two cells: one value with a locator, one justified absence."""
    return [
        ex.Cell(citekey, "guarantee type", "architectural", locator="§2, Eq. (3)"),
        ex.Cell(
            citekey,
            "scope",
            ex.NOT_ADDRESSED,
            justification="scoped to fully-monotone inputs in §1; never revisited",
        ),
    ]


def _write(
    path: Path,
    log_dir: Path,
    cells: list[ex.Cell] | None = None,
    *,
    in_sample: bool = False,
    batch_check: str = "pending",
) -> Path:
    return art.write_extraction(
        path,
        _cells() if cells is None else cells,
        in_sample=in_sample,
        batch_check=batch_check,
        log_dir=log_dir,
        date=DATE,
    )


def _status(path: Path) -> dict[str, Any]:
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    status = yaml.safe_load("\n".join(fm))["status"]
    assert isinstance(status, dict)
    return status


def _last_updated(path: Path) -> str:
    """``last-updated`` as written; YAML decodes an unquoted ISO date to a date."""
    return str(_status(path)["last-updated"])


# --- behaviour 1: a fresh artifact --------------------------------------------


def test_a_fresh_artifact_is_seeded_with_the_extraction_block(tmp_path: Path) -> None:
    target = tmp_path / "digests" / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")

    assert _status(target)["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "pending",
    }
    assert _last_updated(target) == DATE
    assert art.read_cells(target) == _cells()


def test_a_fresh_artifact_carries_the_cells_in_its_body(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    text = target.read_text(encoding="utf-8")
    assert art.CELLS_BEGIN in text
    assert art.CELLS_END in text
    assert "guarantee type" in text
    # Extraction's own caveat, unchanged by #142's depth-sourced writer sharing
    # the same block machinery under a different heading/caveat.
    assert "## Extracted cells" in text
    assert "checked by sample" in text


# --- behaviour 2: an existing depth-mode artifact ------------------------------


def test_an_existing_understanding_block_is_left_byte_identical(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")

    lines = target.read_text(encoding="utf-8").splitlines()
    assert UNDERSTANDING_LINE in lines
    assert "title: Monotonic networks" in lines
    assert "The author's own summary prose." in lines
    assert _status(target)["extraction"]["cells"] == 2


# --- behaviour 3: the guarantee-inflation guard (spec §3.2) --------------------


def test_extraction_never_writes_an_understanding_key(tmp_path: Path) -> None:
    """`progress` reads any `understanding` block as "digested & understood".

    A paper with eight extracted cells that nobody read must not be counted as
    read, so extraction's writer may not write that key at all — not even as
    ``pending``. This test fails the moment the two writers are "simplified"
    into one.
    """
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")

    fm, _ = split_frontmatter(target.read_text(encoding="utf-8"))
    assert set(_status(target)) == {"extraction", "last-updated"}
    assert not [ln for ln in fm if "understanding" in ln]


def test_extraction_does_not_advance_a_pending_understanding_block(
    tmp_path: Path,
) -> None:
    seeded = (
        '---\nstatus:\n  understanding: {"status": "pending", "unresolved": []}\n---\n'
    )
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(seeded, encoding="utf-8")
    _write(target, tmp_path / "log")

    assert _status(target)["understanding"] == {"status": "pending", "unresolved": []}


# --- behaviour 4: in-sample and batch-check are separate keys (spec §5) --------


def test_an_unsampled_paper_in_a_failed_batch_says_so_without_blaming_itself(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log", in_sample=False, batch_check="failed")

    block = _status(target)["extraction"]
    assert block["in-sample"] is False
    assert block["batch-check"] == "failed"


def test_a_sampled_paper_in_a_verified_batch(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log", in_sample=True, batch_check="verified")

    block = _status(target)["extraction"]
    assert block["in-sample"] is True
    assert block["batch-check"] == "verified"


def test_an_unknown_batch_check_verdict_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="batch-check must be one of"):
        _write(tmp_path / "a.md", tmp_path / "log", batch_check="probably fine")


# --- behaviour 5: re-running replaces the cells --------------------------------


def test_re_extracting_replaces_the_cells_rather_than_appending(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    second = [ex.Cell(CITEKEY, "guarantee type", "learned", locator="§4")]
    _write(target, tmp_path / "log", second)

    text = target.read_text(encoding="utf-8")
    assert text.count(art.CELLS_BEGIN) == 1
    assert text.count(art.CELLS_END) == 1
    assert art.read_cells(target) == second
    assert _status(target)["extraction"]["cells"] == 1


def test_re_extracting_preserves_prose_on_both_sides_of_the_block(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")
    with target.open("a", encoding="utf-8") as fh:
        fh.write("\nA note added afterwards.\n")
    _write(target, tmp_path / "log")

    lines = target.read_text(encoding="utf-8").splitlines()
    assert "The author's own summary prose." in lines
    assert "A note added afterwards." in lines


# --- behaviour 6: the accountability log ---------------------------------------


def test_the_log_entry_records_every_cell_including_the_absences(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "defend-log"
    entry_path = _write(tmp_path / f"{CITEKEY}.md", log_dir)

    assert entry_path == log_dir / f"{DATE}-{CITEKEY}.yml"
    entry = yaml.safe_load(entry_path.read_text(encoding="utf-8"))[0]
    assert entry["kind"] == "extraction"
    assert entry["citekey"] == CITEKEY
    assert entry["date"] == DATE
    assert entry["not-addressed"] == 1
    assert entry["cells"] == [
        {
            "axis": "guarantee type",
            "value": "architectural",
            "locator": "§2, Eq. (3)",
        },
        {
            "axis": "scope",
            "value": ex.NOT_ADDRESSED,
            "justification": ("scoped to fully-monotone inputs in §1; never revisited"),
        },
    ]


def test_the_log_entry_is_named_from_the_citekey_not_the_artifacts_stem(
    tmp_path: Path,
) -> None:
    """Pins defendable-science#146: the join must survive `Layout.digest` changing.

    Today ``Layout.digest`` happens to name the artifact ``<citekey>.md``, so a
    log entry named from ``path.stem`` coincides with one named from the
    citekey — for every path through the code. This writes the artifact at a
    filename that deliberately does *not* match its citekey, so the two would
    diverge if the log entry were still keyed off the file's stem.
    """
    log_dir = tmp_path / "defend-log"
    artifact_path = tmp_path / "digest-2026-not-the-citekey.md"
    entry_path = _write(artifact_path, log_dir)

    assert entry_path == log_dir / f"{DATE}-{CITEKEY}.yml"
    entry = yaml.safe_load(entry_path.read_text(encoding="utf-8"))[0]
    assert entry["citekey"] == CITEKEY


def test_a_second_extraction_the_same_day_never_overwrites_the_first(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "defend-log"
    first = _write(tmp_path / f"{CITEKEY}.md", log_dir)
    second = _write(
        tmp_path / f"{CITEKEY}.md",
        log_dir,
        [ex.Cell(CITEKEY, "scope", "global", locator="§4")],
    )

    assert second == log_dir / f"{DATE}-{CITEKEY}-2.yml"
    assert (
        yaml.safe_load(first.read_text(encoding="utf-8"))[0]["cells"][0]["value"]
        == "architectural"
    )


# --- behaviour 7: set_batch_check ----------------------------------------------


def test_set_batch_check_touches_only_that_key(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")
    before = target.read_text(encoding="utf-8")

    art.set_batch_check(target, "failed")

    after = target.read_text(encoding="utf-8")
    assert _status(target)["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "failed",
    }
    assert UNDERSTANDING_LINE in after.splitlines()
    assert _cells_span(after) == _cells_span(before)
    assert _last_updated(target) == DATE


def _cells_span(text: str) -> list[str]:
    lines = text.splitlines()
    return lines[lines.index(art.CELLS_BEGIN) : lines.index(art.CELLS_END) + 1]


def test_set_batch_check_can_stamp_the_verdict_date(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    art.set_batch_check(target, "verified", date="2026-09-02")

    assert _last_updated(target) == "2026-09-02"
    assert _status(target)["extraction"]["batch-check"] == "verified"


def test_set_batch_check_refuses_an_unknown_verdict(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    with pytest.raises(ex.ExtractionError, match="batch-check must be one of"):
        art.set_batch_check(target, "looks-fine")
    assert _status(target)["extraction"]["batch-check"] == "pending"


def test_set_batch_check_refuses_a_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        art.set_batch_check(tmp_path / "nope.md", "verified")


def test_set_batch_check_never_invents_an_extraction_block(tmp_path: Path) -> None:
    """A paper skipped for want of a PDF has no block, and must not gain one."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match=r"no 'status\.extraction' block"):
        art.set_batch_check(target, "failed")
    assert target.read_text(encoding="utf-8") == DEPTH_ARTIFACT


@pytest.mark.parametrize(
    "frontmatter",
    [
        "status:\n  understanding: {}",  # a status block, but no extraction
        "status: pending",  # status is a scalar, not a mapping
        "just a bare string",  # frontmatter is not a mapping at all
    ],
)
def test_set_batch_check_refuses_frontmatter_without_an_extraction_mapping(
    tmp_path: Path, frontmatter: str
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match=r"no 'status\.extraction' block"):
        art.set_batch_check(target, "failed")


def test_set_batch_check_reports_unparseable_frontmatter_as_such(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus: [\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="frontmatter is not valid YAML"):
        art.set_batch_check(target, "failed")


def test_set_batch_check_reports_a_missing_status_block(tmp_path: Path) -> None:
    """`status.extraction` is read before the setter, so this is the read's word."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nnotstatus: 1\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match=r"no 'status\.extraction' block"):
        art.set_batch_check(target, "failed")


# --- the writer refuses what validation would have rejected (spec §3.3) --------


def test_write_extraction_refuses_an_empty_cell_list(tmp_path: Path) -> None:
    """A skipped paper gets no `status.extraction` block at all (spec §6.4)."""
    with pytest.raises(ex.ExtractionError, match="takes one paper's cells"):
        _write(tmp_path / "a.md", tmp_path / "log", [])
    assert not (tmp_path / "a.md").exists()


def test_write_extraction_refuses_cells_from_two_papers(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="takes one paper's cells"):
        _write(tmp_path / "a.md", tmp_path / "log", [*_cells(), *_cells("other2020")])


def test_write_extraction_refuses_a_value_cell_with_no_locator(
    tmp_path: Path,
) -> None:
    cells = [ex.Cell(CITEKEY, "scope", "global", locator="   ")]
    with pytest.raises(ex.ExtractionError, match="has no locator; refusing"):
        _write(tmp_path / "a.md", tmp_path / "log", cells)


def test_write_extraction_refuses_an_unjustified_absence(tmp_path: Path) -> None:
    cells = [ex.Cell(CITEKEY, "scope", ex.NOT_ADDRESSED)]
    with pytest.raises(ex.ExtractionError, match="with no justification"):
        _write(tmp_path / "a.md", tmp_path / "log", cells)


def test_write_extraction_reports_a_malformed_host_artifact(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("# no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        _write(target, tmp_path / "log")


def test_write_extraction_reports_a_frontmatter_without_a_status_block(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\ntitle: x\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no 'status:' block"):
        _write(target, tmp_path / "log")


# --- a justified absence may cite the scope that excludes the axis -------------


def test_an_absence_locator_is_recorded_as_scope_evidence_not_a_value_source(
    tmp_path: Path,
) -> None:
    cells = [
        ex.Cell(
            CITEKEY,
            "scope",
            ex.NOT_ADDRESSED,
            locator="§1",
            justification="the paper scopes itself to fully-monotone inputs",
        )
    ]
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log", cells)

    text = target.read_text(encoding="utf-8")
    assert "scope-evidence: §1" in text
    assert "locator:" not in text
    assert art.read_cells(target) == cells


# --- read_cells ----------------------------------------------------------------


def test_read_cells_refuses_a_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        art.read_cells(tmp_path / "nope.md")


def test_read_cells_refuses_an_artifact_without_frontmatter(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        art.read_cells(target)


def test_read_cells_refuses_an_unextracted_paper_rather_than_returning_none(
    tmp_path: Path,
) -> None:
    """Empty would read as "extracted, zero cells" — a claim about the paper."""
    target = tmp_path / "a.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no extracted-cells block"):
        art.read_cells(target)


def _artifact_with_body(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "a.md"
    target.write_text(f"---\nstatus:\n---\n{body}", encoding="utf-8")
    return target


@pytest.mark.parametrize(
    "body",
    [
        f"{art.CELLS_END}\n",  # an end with no begin
        f"{art.CELLS_BEGIN}\n",  # a begin with no end
        f"{art.CELLS_BEGIN}\n{art.CELLS_BEGIN}\n{art.CELLS_END}\n",  # duplicated
        f"{art.CELLS_END}\n{art.CELLS_BEGIN}\n",  # out of order
    ],
)
def test_read_cells_refuses_malformed_markers(tmp_path: Path, body: str) -> None:
    with pytest.raises(ex.ExtractionError, match="markers are malformed"):
        art.read_cells(_artifact_with_body(tmp_path, body))


def test_write_extraction_refuses_to_guess_which_span_to_replace(
    tmp_path: Path,
) -> None:
    target = _artifact_with_body(tmp_path, f"{art.CELLS_BEGIN}\nstale\n")
    before = target.read_text(encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="markers are malformed"):
        _write(target, tmp_path / "log")
    assert target.read_text(encoding="utf-8") == before


def test_read_cells_refuses_a_block_with_no_yaml_fence(tmp_path: Path) -> None:
    body = f"{art.CELLS_BEGIN}\naxis: scope\n{art.CELLS_END}\n"
    with pytest.raises(ex.ExtractionError, match="no ```yaml fence"):
        art.read_cells(_artifact_with_body(tmp_path, body))


def _fenced(payload: str) -> str:
    return f"{art.CELLS_BEGIN}\n```yaml\n{payload}\n```\n{art.CELLS_END}\n"


def test_read_cells_refuses_a_block_that_is_not_valid_yaml(tmp_path: Path) -> None:
    target = _artifact_with_body(tmp_path, _fenced("citekey: ["))
    with pytest.raises(ex.ExtractionError, match="not valid YAML"):
        art.read_cells(target)


@pytest.mark.parametrize(
    "payload",
    ["- a bare list", "citekey: k\ncells: not-a-list"],
)
def test_read_cells_refuses_a_block_of_the_wrong_shape(
    tmp_path: Path, payload: str
) -> None:
    with pytest.raises(ex.ExtractionError, match="block is malformed"):
        art.read_cells(_artifact_with_body(tmp_path, _fenced(payload)))


def test_read_cells_refuses_a_non_mapping_cell_entry(tmp_path: Path) -> None:
    payload = "citekey: k\ncells:\n- just a string"
    with pytest.raises(ex.ExtractionError, match="non-mapping entry"):
        art.read_cells(_artifact_with_body(tmp_path, _fenced(payload)))


def test_read_cells_refuses_a_hand_edited_field_name(tmp_path: Path) -> None:
    """A dropped ``locater`` typo would read back as a cell with no locator."""
    payload = "citekey: k\ncells:\n- axis: scope\n  value: v\n  locater: §3"
    with pytest.raises(ex.ExtractionError, match="unknown field"):
        art.read_cells(_artifact_with_body(tmp_path, _fenced(payload)))


# --- the shared log appender ----------------------------------------------------


def test_append_log_entry_creates_the_directory_and_returns_its_path(
    tmp_path: Path,
) -> None:
    from defendable_science.defend.record import append_log_entry

    written = append_log_entry(tmp_path / "log", DATE, "stem", "body: 1\n")
    assert written == tmp_path / "log" / f"{DATE}-stem.yml"
    assert written.read_text(encoding="utf-8") == "body: 1\n"


def test_the_block_is_appended_after_trailing_blank_lines_not_among_them(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus:\n---\n\nProse.\n\n\n", encoding="utf-8")
    _write(target, tmp_path / "log")

    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[lines.index(art.CELLS_BEGIN) - 1] == ""
    assert lines[lines.index(art.CELLS_BEGIN) - 2] == "Prose."


def test_set_batch_check_reports_an_artifact_without_frontmatter(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("# just prose\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        art.set_batch_check(target, "verified")


# --- a hand-written block-style status.extraction (spec §5's own shape) --------

#: Spec §5's example, literally: a human following the documented shape writes
#: `extraction` as an indented block mapping, not as a flow mapping.
SPEC_BLOCK_ARTIFACT = """---
status:
  understanding: {status: pending, unresolved: []}    # depth mode; untouched
  extraction:
    cells: 8
    locators: ok
    in-sample: false
    batch-check: pending
  last-updated: 2026-08-28
---

Prose.
"""


def test_writing_over_a_block_style_extraction_leaves_parseable_frontmatter(
    tmp_path: Path,
) -> None:
    """The whole block mapping is the key's value, so the whole block goes.

    Replacing only the `extraction:` line orphaned its children and produced a
    frontmatter no parser would read — while reporting a completed write.
    """
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(SPEC_BLOCK_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")

    assert _status(target)["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "pending",
    }
    assert _status(target)["understanding"] == {"status": "pending", "unresolved": []}
    assert "Prose." in target.read_text(encoding="utf-8").splitlines()
    assert art.read_cells(target) == _cells()


def test_set_batch_check_over_a_block_style_extraction_keeps_its_other_keys(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(SPEC_BLOCK_ARTIFACT, encoding="utf-8")
    art.set_batch_check(target, "failed")

    assert _status(target)["extraction"] == {
        "cells": 8,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "failed",
    }
    assert str(_status(target)["last-updated"]) == "2026-08-28"


def test_a_block_style_value_does_not_swallow_the_keys_after_it(
    tmp_path: Path,
) -> None:
    """Only the nested lines are the value; `last-updated` is a sibling."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(SPEC_BLOCK_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")

    assert set(_status(target)) == {"understanding", "extraction", "last-updated"}


def test_a_blank_line_inside_the_block_does_not_orphan_its_tail(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  extraction:\n    cells: 8\n\n    locators: ok\n"
        "  last-updated: 2026-08-01\n---\n",
        encoding="utf-8",
    )
    _write(target, tmp_path / "log")

    assert _status(target)["extraction"]["cells"] == 2
    assert set(_status(target)) == {"extraction", "last-updated"}


def test_a_blank_line_after_the_block_survives(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  extraction:\n    cells: 8\n\ntitle: x\n---\n",
        encoding="utf-8",
    )
    _write(target, tmp_path / "log")

    fm, _ = split_frontmatter(target.read_text(encoding="utf-8"))
    assert "" in fm
    assert "title: x" in fm


def test_a_comment_inside_the_replaced_block_is_refused_not_destroyed(
    tmp_path: Path,
) -> None:
    """`patch_triage`'s posture: refuse what cannot be round-tripped."""
    target = tmp_path / f"{CITEKEY}.md"
    original = (
        "---\nstatus:\n  extraction:\n    cells: 8  # counted by hand\n"
        "    batch-check: pending\n---\n"
    )
    target.write_text(original, encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="reads as carrying a comment"):
        _write(target, tmp_path / "log")
    assert target.read_text(encoding="utf-8") == original


def test_a_comment_on_the_extraction_line_itself_is_preserved(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  extraction:  # hand-seeded\n    cells: 8\n---\n",
        encoding="utf-8",
    )
    _write(target, tmp_path / "log")

    fm, _ = split_frontmatter(target.read_text(encoding="utf-8"))
    assert any(ln.endswith("# hand-seeded") for ln in fm)
    assert _status(target)["extraction"]["cells"] == 2


def test_set_batch_check_reports_a_block_value_json_cannot_rewrite(
    tmp_path: Path,
) -> None:
    """An unquoted date under `extraction` decodes to `datetime.date`."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  extraction:\n    cells: 8\n    checked-on: 2026-08-28\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(ex.ExtractionError, match="cannot be rewritten"):
        art.set_batch_check(target, "failed")


# --- a comment is not a dedent, at any column ---------------------------------


def _block_with_comment(comment_line: str) -> str:
    return (
        "---\nstatus:\n  extraction:\n"
        f"{comment_line}\n"
        "    cells: 8\n    batch-check: pending\n  last-updated: 2026-08-01\n---\n"
    )


@pytest.mark.parametrize(
    "comment_line",
    [
        "# flush-left note",  # column 0
        "  # a note at the parent's indent",  # the key's own indent
        "    # a note at the children's indent",  # inside the block
    ],
)
def test_write_refuses_a_comment_anywhere_in_the_block_it_would_replace(
    tmp_path: Path, comment_line: str
) -> None:
    """A comment at any column ends the block scan if it is read as a dedent.

    That would leave the scan short of the block's tail, so the refusal never
    fires and only part of the value is replaced — the orphaned-children
    corruption again, one column to the left.
    """
    target = tmp_path / f"{CITEKEY}.md"
    original = _block_with_comment(comment_line)
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ex.ExtractionError, match="reads as carrying a comment"):
        _write(target, tmp_path / "log")
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "comment_line",
    ["# flush-left note", "  # a note at the parent's indent"],
)
def test_set_batch_check_refuses_the_same_rather_than_reporting_success(
    tmp_path: Path, comment_line: str
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    original = _block_with_comment(comment_line)
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ex.ExtractionError, match="reads as carrying a comment"):
        art.set_batch_check(target, "failed")
    assert target.read_text(encoding="utf-8") == original


def test_a_comment_before_the_key_does_not_hide_it_and_cause_a_duplicate(
    tmp_path: Path,
) -> None:
    """Ending the *key search* on a comment inserts a second `extraction:`.

    A duplicate key silently shadows the value just written, so the write would
    report success and change nothing a reader sees.
    """
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n# a note about the block below\n"
        '  extraction: {"cells": 8, "batch-check": "pending"}\n---\n',
        encoding="utf-8",
    )
    art.set_batch_check(target, "verified")

    text = target.read_text(encoding="utf-8")
    assert text.count("extraction:") == 1
    assert "# a note about the block below" in text
    assert _status(target)["extraction"]["batch-check"] == "verified"


def test_a_top_level_key_after_the_status_block_still_ends_the_search(
    tmp_path: Path,
) -> None:
    """The dedent rule must still hold for anything that is not a comment."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  last-updated: 2026-08-01\nelsewhere:\n"
        "  extraction: not-a-status-child\n---\n",
        encoding="utf-8",
    )
    _write(target, tmp_path / "log")

    fm, _ = split_frontmatter(target.read_text(encoding="utf-8"))
    assert "  extraction: not-a-status-child" in fm
    assert _status(target)["extraction"]["cells"] == 2


# --- has_extraction: the batch-membership test (spec §8, ruling AL) ------------


def test_has_extraction_is_true_for_an_extracted_artifact(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")

    assert art.has_extraction(target) is True


def test_has_extraction_is_false_for_a_depth_only_digest(tmp_path: Path) -> None:
    """A depth-mode reading record was never extracted, so it is not a member."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus:\n  understanding: {status: complete}\n---\n", encoding="utf-8"
    )

    assert art.has_extraction(target) is False


def test_has_extraction_refuses_a_missing_artifact(tmp_path: Path) -> None:
    """Absent is not 'never extracted' — the caller must hear about it."""
    with pytest.raises(ex.ExtractionError, match="not found"):
        art.has_extraction(tmp_path / "nowhere.md")


def test_has_extraction_refuses_an_artifact_without_frontmatter(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("just prose\n", encoding="utf-8")

    with pytest.raises(ex.ExtractionError):
        art.has_extraction(target)


def test_has_extraction_refuses_unparseable_frontmatter(tmp_path: Path) -> None:
    """Unreadable YAML is a failure, never a quiet 'not in the batch'."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus: [unclosed\n---\n", encoding="utf-8")

    with pytest.raises(ex.ExtractionError, match="not valid YAML"):
        art.has_extraction(target)


def test_append_check_log_refuses_an_unknown_verdict(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="batch-check must be one of"):
        art.append_check_log(
            tmp_path / f"{CITEKEY}.md",
            CITEKEY,
            _cells(),
            verdict="probably fine",
            batch=[CITEKEY],
            log_dir=tmp_path / "log",
            date=DATE,
        )


# --- set_in_sample: "a human checked these cells" ------------------------------


def test_set_in_sample_touches_only_that_key(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write(target, tmp_path / "log")
    before = target.read_text(encoding="utf-8")

    art.set_in_sample(target, in_sample=True)

    after = target.read_text(encoding="utf-8")
    assert _status(target)["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": True,
        # The verdict on the run is a separate question and must not move with it.
        "batch-check": "pending",
    }
    assert UNDERSTANDING_LINE in after.splitlines()
    assert _cells_span(after) == _cells_span(before)
    assert _last_updated(target) == DATE


def test_set_in_sample_can_stamp_the_check_date(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    art.set_in_sample(target, in_sample=True, date="2026-09-02")

    assert _last_updated(target) == "2026-09-02"
    assert _status(target)["extraction"]["in-sample"] is True


def test_set_in_sample_refuses_a_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        art.set_in_sample(tmp_path / "nope.md", in_sample=True)


def test_set_in_sample_never_invents_an_extraction_block(tmp_path: Path) -> None:
    """A paper that was never extracted cannot have been sampled."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus:\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="has not been extracted"):
        art.set_in_sample(target, in_sample=True)


# --- write_depth_cells: matrix cells from a depth-mode reading (defendable-science#142) --


def _write_depth(path: Path, log_dir: Path, cells: list[ex.Cell] | None = None) -> Path:
    return art.write_depth_cells(
        path, _cells() if cells is None else cells, log_dir=log_dir, date=DATE
    )


def test_write_depth_cells_refuses_a_missing_artifact(tmp_path: Path) -> None:
    """Unlike `write_extraction`, there is no seed: nothing was certified yet."""
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        _write_depth(tmp_path / "nope.md", tmp_path / "log")


def test_write_depth_cells_requires_an_understanding_block(tmp_path: Path) -> None:
    """Cells restate what depth mode certified; there is nothing to restate."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus:\n---\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match=r"no 'status\.understanding' block"):
        _write_depth(target, tmp_path / "log")
    assert target.read_text(encoding="utf-8") == "---\nstatus:\n---\n"


def test_write_depth_cells_refuses_an_already_extracted_artifact(
    tmp_path: Path,
) -> None:
    """Extraction's cells must not be overwritten by a different standard's."""
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    before = target.read_text(encoding="utf-8")

    with pytest.raises(
        ex.ExtractionError, match=r"already carries a 'status\.extraction'"
    ):
        _write_depth(target, tmp_path / "log")

    assert target.read_text(encoding="utf-8") == before


def test_write_depth_cells_leaves_understanding_and_prose_byte_identical(
    tmp_path: Path,
) -> None:
    """A direct byte-level diff, not just "it still parses" (defendable-science#142)."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")

    _write_depth(target, tmp_path / "log")

    after = target.read_text(encoding="utf-8")
    before_fm, before_body = split_frontmatter(DEPTH_ARTIFACT)
    after_fm, after_body = split_frontmatter(after)

    # Frontmatter: only `last-updated` changes. The `understanding` block and
    # its trailing `# defend` comment, and every other line, are untouched.
    assert [ln for ln in before_fm if "last-updated" not in ln] == [
        ln for ln in after_fm if "last-updated" not in ln
    ]
    assert UNDERSTANDING_LINE in after_fm
    assert f"  last-updated: {DATE}" in after_fm

    # Body: every original line survives, in order; only the cells block is new.
    begin = after_body.index(art.CELLS_BEGIN)
    end = after_body.index(art.CELLS_END)
    assert [ln for ln in after_body[:begin] if ln.strip()] == [
        ln for ln in before_body if ln.strip()
    ]
    assert after_body[end + 1 :] == []


def test_write_depth_cells_reports_a_status_block_it_cannot_patch(
    tmp_path: Path,
) -> None:
    """A ``status`` that parses but cannot be patched.

    `status` parses as a mapping (so `_has_understanding` is true), but it is
    written as an inline flow mapping with no bare ``status:`` line — the shape
    `set_field` requires to patch ``last-updated``.
    """
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(
        "---\nstatus: {understanding: {status: ok, unresolved: []}}\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(ex.ExtractionError, match="no 'status:' block"):
        _write_depth(target, tmp_path / "log")


def test_write_depth_cells_never_writes_status_extraction(tmp_path: Path) -> None:
    """The provenance signal is the *absence* of `status.extraction` (ADR-0042)."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")

    _write_depth(target, tmp_path / "log")

    assert "extraction" not in _status(target)
    assert set(_status(target)) == {"understanding", "last-updated"}


def test_write_depth_cells_round_trips_through_read_cells(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")

    _write_depth(target, tmp_path / "log")

    assert art.read_cells(target) == _cells()


def test_write_depth_cells_never_claims_extractions_sampling_regime(
    tmp_path: Path,
) -> None:
    """The block's own prose must not say "checked by sample" — nothing was."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")

    _write_depth(target, tmp_path / "log")

    text = target.read_text(encoding="utf-8")
    assert "## Depth-sourced cells" in text
    assert "## Extracted cells" not in text
    assert "checked by sample" not in text
    assert "Extraction mode" not in text


def test_write_depth_cells_refuses_an_empty_cell_list(tmp_path: Path) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="takes one paper's cells"):
        _write_depth(target, tmp_path / "log", [])


def test_write_depth_cells_refuses_a_value_cell_with_no_locator(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    cells = [ex.Cell(CITEKEY, "scope", "global", locator="   ")]
    with pytest.raises(ex.ExtractionError, match="has no locator; refusing"):
        _write_depth(target, tmp_path / "log", cells)


def test_write_depth_cells_replaces_cells_rather_than_appending(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write_depth(target, tmp_path / "log")
    second = [ex.Cell(CITEKEY, "guarantee type", "learned", locator="§4")]
    _write_depth(target, tmp_path / "log", second)

    text = target.read_text(encoding="utf-8")
    assert text.count(art.CELLS_BEGIN) == 1
    assert text.count(art.CELLS_END) == 1
    assert art.read_cells(target) == second


def test_write_depth_cells_appends_a_depth_cells_log_entry(tmp_path: Path) -> None:
    """The log entry carries its own `kind`, distinct from extraction's."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    log_dir = tmp_path / "defend-log"

    entry_path = _write_depth(target, log_dir)

    assert entry_path == log_dir / f"{DATE}-{CITEKEY}.yml"
    entry = yaml.safe_load(entry_path.read_text(encoding="utf-8"))[0]
    assert entry["kind"] == "depth-cells"
    assert entry["citekey"] == CITEKEY
    assert entry["cells"] == [
        {
            "axis": "guarantee type",
            "value": "architectural",
            "locator": "§2, Eq. (3)",
        },
        {
            "axis": "scope",
            "value": ex.NOT_ADDRESSED,
            "justification": ("scoped to fully-monotone inputs in §1; never revisited"),
        },
    ]


def test_write_extraction_still_logs_kind_extraction(tmp_path: Path) -> None:
    """Pins the shared `_log_body` helper's default for the older writer."""
    entry_path = _write(tmp_path / f"{CITEKEY}.md", tmp_path / "log")
    entry = yaml.safe_load(entry_path.read_text(encoding="utf-8"))[0]
    assert entry["kind"] == "extraction"


# --- has_extraction_or_cells: `extract render`'s default-batch membership -----


def test_has_extraction_or_cells_is_true_for_an_extracted_artifact(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    assert art.has_extraction_or_cells(target) is True


def test_has_extraction_or_cells_is_true_for_a_depth_sourced_artifact(
    tmp_path: Path,
) -> None:
    """The exact case #142 exists for: no `status.extraction`, but cells present."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write_depth(target, tmp_path / "log")
    assert art.has_extraction(target) is False
    assert art.has_extraction_or_cells(target) is True


def test_has_extraction_or_cells_is_false_for_a_plain_depth_digest(
    tmp_path: Path,
) -> None:
    """Neither block present: nothing to render, and this is not a finding."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    assert art.has_extraction_or_cells(target) is False


def test_has_extraction_or_cells_is_true_for_extraction_status_with_no_cells_block(
    tmp_path: Path,
) -> None:
    """Mirrors `has_extraction`: the inconsistency surfaces when cells are read."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus:\n  extraction: {}\n---\n\nno block\n", "utf-8")
    assert art.has_extraction_or_cells(target) is True


def test_has_extraction_or_cells_refuses_a_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        art.has_extraction_or_cells(tmp_path / "nope.md")


def test_has_extraction_or_cells_refuses_unparseable_frontmatter(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("not a digest at all\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        art.has_extraction_or_cells(target)


def test_has_extraction_or_cells_refuses_malformed_cells_markers(
    tmp_path: Path,
) -> None:
    """No `status.extraction` to short-circuit on, and the cells markers are broken."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(f"---\nstatus:\n---\n\n{art.CELLS_BEGIN}\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="malformed"):
        art.has_extraction_or_cells(target)


def test_has_understanding_without_cells_is_true_for_a_plain_depth_digest(
    tmp_path: Path,
) -> None:
    """The exact "not yet recorded" case #142's render-batch fix must surface."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    assert art.has_understanding_without_cells(target) is True


def test_has_understanding_without_cells_is_false_once_cells_are_recorded(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write_depth(target, tmp_path / "log")
    assert art.has_understanding_without_cells(target) is False


def test_has_understanding_without_cells_is_false_for_an_extracted_artifact(
    tmp_path: Path,
) -> None:
    """`status.extraction` present: extraction's population, not depth's."""
    target = tmp_path / f"{CITEKEY}.md"
    _write(target, tmp_path / "log")
    assert art.has_understanding_without_cells(target) is False


def test_has_understanding_without_cells_is_false_with_no_understanding_either(
    tmp_path: Path,
) -> None:
    """Neither block present at all: not a depth digest, nothing pending."""
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("---\nstatus:\n---\n", encoding="utf-8")
    assert art.has_understanding_without_cells(target) is False


def test_has_understanding_without_cells_refuses_a_missing_artifact(
    tmp_path: Path,
) -> None:
    with pytest.raises(ex.ExtractionError, match="digest artifact not found"):
        art.has_understanding_without_cells(tmp_path / "nope.md")


def test_has_understanding_without_cells_refuses_unparseable_frontmatter(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text("not a digest at all\n", encoding="utf-8")
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        art.has_understanding_without_cells(target)


def test_cells_markers_present_is_false_with_no_markers_at_all(tmp_path: Path) -> None:
    path = tmp_path / f"{CITEKEY}.md"
    assert (
        art.cells_markers_present("---\nstatus:\n---\n\nno cells here\n", path) is False
    )


def test_cells_markers_present_is_true_for_a_well_formed_block(tmp_path: Path) -> None:
    path = tmp_path / f"{CITEKEY}.md"
    target = tmp_path / f"{CITEKEY}.md"
    target.write_text(DEPTH_ARTIFACT, encoding="utf-8")
    _write_depth(target, tmp_path / "log")
    assert art.cells_markers_present(target.read_text(encoding="utf-8"), path) is True


def test_cells_markers_present_raises_on_duplicated_markers(tmp_path: Path) -> None:
    path = tmp_path / f"{CITEKEY}.md"
    text = f"---\nstatus:\n---\n\n{art.CELLS_BEGIN}\n{art.CELLS_END}\n{art.CELLS_BEGIN}\n{art.CELLS_END}\n"
    with pytest.raises(ex.ExtractionError, match="malformed"):
        art.cells_markers_present(text, path)


def test_cells_markers_present_refuses_unparseable_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / f"{CITEKEY}.md"
    with pytest.raises(ex.ExtractionError, match="no YAML frontmatter"):
        art.cells_markers_present("not a digest at all\n", path)
