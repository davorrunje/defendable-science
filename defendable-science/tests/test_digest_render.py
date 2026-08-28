"""The concept-matrix merge — ``render_matrix`` and ``digest extract render``.

The weight is on the negatives (spec §9, §11). Render is the one operation in
extraction mode with no safe failure mode: it writes into a file the author
hand-wrote, so every test here that says "X survives" compares **bytes**, not a
parsed projection, and the deletion tests are the point of the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.digest import artifact as artifact_mod
from defendable_science.digest.extraction import Cell, ExtractionError
from defendable_science.digest.render import (
    MATRIX_NOT_ADDRESSED,
    render_matrix,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

runner = CliRunner()

POSITIONING = """# Positioning — p1

Author prose that must survive untouched.

A matrix looks like this:

```markdown
| Method | example axis |
|---|---|
| someone2020 | illustrative |
```

## Baselines

| Baseline | Why |
|---|---|
| ridge | simplest floor |

## Concept matrix

<!-- rows = prior work; the last row is our delta -->

| Method | guarantee type | partial monotonicity |
|---|---|---|
| sill1997 | architectural | no |
| **This paper** | architectural | yes |

## PRISMA log

- 2026-08-01 — screened 120 records.
"""


def _write(tmp_path: Path, text: str = POSITIONING) -> Path:
    target = tmp_path / "positioning.md"
    target.write_text(text, encoding="utf-8")
    return target


def _matrix_block(text: str) -> str:
    """Return the concept-matrix table region, for a targeted comparison."""
    start = text.index("| Method |", text.index("## Concept matrix"))
    return text[start : text.index("\n\n", start)]


# --- render_matrix: the merge --------------------------------------------------


def test_a_new_citekey_is_inserted_leaving_the_other_rows_alone(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path)
    before = target.read_bytes()
    out = render_matrix(
        target,
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert "| vanilla2020 | learned | no |" in out
    assert "| sill1997 | architectural | no |" in out
    # Purity on the *success* path too, not only on the refusals: the CLI is
    # what decides whether anything reaches disk, so the merge must not write.
    assert target.read_bytes() == before


def test_a_new_row_lands_before_the_author_s_own_delta(tmp_path: Path) -> None:
    """``**This paper**`` is the matrix's punchline and stays last."""
    out = render_matrix(
        _write(tmp_path),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert _matrix_block(out).splitlines()[-1].startswith("| **This paper** |")


def test_a_new_row_is_appended_when_the_delta_row_is_not_last(tmp_path: Path) -> None:
    """No self row at the end (here it leads): the new row simply goes last."""
    led = POSITIONING.replace(
        "| sill1997 | architectural | no |\n| **This paper** | architectural | yes |\n",
        "| **This paper** | architectural | yes |\n| sill1997 | architectural | no |\n",
    )
    out = render_matrix(
        _write(tmp_path, led),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert _matrix_block(out).splitlines()[-1] == "| vanilla2020 | learned | no |"


def test_an_existing_citekey_is_updated_in_place(tmp_path: Path) -> None:
    out = render_matrix(
        _write(tmp_path),
        {"sill1997": {"guarantee type": "architectural (min-max)"}},
    )
    rows = [ln for ln in _matrix_block(out).splitlines() if ln.startswith("| sill1997")]
    assert rows == ["| sill1997 | architectural (min-max) | no |"]  # column order kept


def test_the_self_row_is_never_written(tmp_path: Path) -> None:
    """The author's own delta is theirs; a caller asking to write it is refused."""
    target = _write(tmp_path)
    before = target.read_bytes()
    with pytest.raises(ExtractionError, match=r"\*\*This paper\*\*"):
        render_matrix(target, {"**This paper**": {"guarantee type": "rewritten"}})
    assert target.read_bytes() == before


def test_the_self_row_survives_a_render_of_other_papers(tmp_path: Path) -> None:
    out = render_matrix(
        _write(tmp_path),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert "| **This paper** | architectural | yes |" in out


def test_a_row_absent_from_the_rows_argument_survives(tmp_path: Path) -> None:
    """Render never deletes: sill1997 is not in the batch and stays untouched."""
    out = render_matrix(
        _write(tmp_path),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert "| sill1997 | architectural | no |" in out


def test_rendering_nothing_deletes_nothing(tmp_path: Path) -> None:
    out = render_matrix(_write(tmp_path), {})
    assert "| sill1997 | architectural | no |" in out
    assert "| **This paper** | architectural | yes |" in out


def test_the_host_document_survives_byte_identical(tmp_path: Path) -> None:
    """Preamble, the other table, the fenced example, the comment, the postamble."""
    out = render_matrix(
        _write(tmp_path),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert out == POSITIONING.replace(
        "| **This paper** | architectural | yes |\n",
        "| vanilla2020 | learned | no |\n| **This paper** | architectural | yes |\n",
    )


def test_rendering_twice_is_idempotent(tmp_path: Path) -> None:
    target = _write(tmp_path)
    rows = {
        "vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"},
    }
    first = render_matrix(target, rows)
    target.write_text(first, encoding="utf-8")
    assert render_matrix(target, rows) == first


def test_a_pipe_or_newline_in_a_value_is_escaped(tmp_path: Path) -> None:
    out = render_matrix(
        _write(tmp_path),
        {
            "odd2021": {
                "guarantee type": "a | b",
                "partial monotonicity": "line one\nline two",
            }
        },
    )
    assert r"| odd2021 | a \| b | line one line two |" in out
    # Still one well-formed table: the escaped pipe did not add a column.
    assert len(_matrix_block(out).splitlines()) == 5


def test_not_addressed_renders_as_a_marker_not_an_empty_cell(tmp_path: Path) -> None:
    """An empty cell reads as "not yet extracted", a different claim."""
    out = render_matrix(
        _write(tmp_path),
        {
            "scoped2019": {
                "guarantee type": "learned",
                "partial monotonicity": "not-addressed",
            }
        },
    )
    assert f"| scoped2019 | learned | {MATRIX_NOT_ADDRESSED} |" in out
    assert "| scoped2019 | learned |  |" not in out


def test_an_axis_the_matrix_does_not_have_is_refused(tmp_path: Path) -> None:
    target = _write(tmp_path)
    before = target.read_bytes()
    with pytest.raises(ExtractionError, match="not a matrix axis"):
        render_matrix(target, {"x2020": {"invented axis": "v"}})
    assert target.read_bytes() == before


def test_a_duplicated_row_label_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    """Two rows for one citekey: which one is the row? Refuse, do not pick."""
    doubled = POSITIONING.replace(
        "| sill1997 | architectural | no |\n",
        "| sill1997 | architectural | no |\n| sill1997 | learned | yes |\n",
    )
    target = _write(tmp_path, doubled)
    with pytest.raises(ExtractionError, match="appears in 2 rows"):
        render_matrix(target, {"sill1997": {"guarantee type": "v"}})


def test_a_duplicate_label_elsewhere_does_not_block_an_unrelated_row(
    tmp_path: Path,
) -> None:
    doubled = POSITIONING.replace(
        "| sill1997 | architectural | no |\n",
        "| sill1997 | architectural | no |\n| sill1997 | learned | yes |\n",
    )
    out = render_matrix(
        _write(tmp_path, doubled), {"other2020": {"guarantee type": "v"}}
    )
    assert out.count("| sill1997 |") == 2  # both survive, untouched


def test_a_column_beyond_the_axes_is_kept_on_an_updated_row(tmp_path: Path) -> None:
    """An author's extra column is never dropped, and never invented into."""
    extra = POSITIONING.replace(
        "| Method | guarantee type | partial monotonicity |\n|---|---|---|\n"
        "| sill1997 | architectural | no |\n"
        "| **This paper** | architectural | yes |\n",
        "| Method | guarantee type | partial monotonicity | notes |\n|---|---|---|---|\n"
        "| sill1997 | architectural | no | seminal |\n"
        "| **This paper** | architectural | yes | ours |\n",
    )
    out = render_matrix(
        _write(tmp_path, extra),
        {
            "sill1997": {"guarantee type": "architectural (min-max)"},
            "new2026": {"guarantee type": "learned"},
        },
    )
    assert "| sill1997 | architectural (min-max) | no | seminal |" in out
    assert "| new2026 | learned |  |  |" in out  # empty for the author to fill


def test_a_document_with_no_concept_matrix_is_refused_not_rendered_empty(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path, "# Positioning\n\nprose only\n")
    with pytest.raises(ExtractionError, match="no 'Concept matrix' section"):
        render_matrix(target, {"x": {"a": "b"}})


def test_a_matrix_inside_a_code_fence_is_never_written_into(tmp_path: Path) -> None:
    """The only pipe table is an illustration: refuse, do not overwrite it."""
    fenced = (
        "# Positioning\n\n## Concept matrix\n\n"
        "```markdown\n| Method | axis |\n|---|---|\n| ex | v |\n```\n"
    )
    target = _write(tmp_path, fenced)
    with pytest.raises(ExtractionError, match="holds no table"):
        render_matrix(target, {"x2020": {"axis": "v"}})
    assert target.read_text(encoding="utf-8") == fenced


# --- the CLI --------------------------------------------------------------------


def _repo(tmp_path: Path, positioning: str = POSITIONING) -> Path:
    """Build a minimal onboarded repo with one paper's positioning document."""
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text("", encoding="utf-8")
    docs = tmp_path / "docs" / "research" / "p1" / "paper"
    docs.mkdir(parents=True)
    (docs / "positioning.md").write_text(positioning, encoding="utf-8")
    return tmp_path


def _positioning(root: Path) -> Path:
    return root / "docs" / "research" / "p1" / "paper" / "positioning.md"


def _extract(root: Path, citekey: str, values: Mapping[str, str]) -> Path:
    """Record one paper's cells into its digest artifact."""
    artifact = root / "docs" / "research" / "literature" / "digests" / f"{citekey}.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    cells = [
        Cell(
            citekey=citekey,
            axis=axis,
            value=value,
            justification="out of scope" if value == "not-addressed" else None,
            locator=None if value == "not-addressed" else "§3",
        )
        for axis, value in values.items()
    ]
    artifact_mod.write_extraction(
        artifact,
        cells,
        in_sample=False,
        batch_check="pending",
        log_dir=root / "docs" / "research" / "defend-log",
        date="2026-08-28",
    )
    return artifact


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> Any:
    monkeypatch.chdir(root)
    return runner.invoke(app, ["digest", "extract", "render", "--paper", "p1", *extra])


def test_render_merges_every_extracted_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(
        root,
        "vanilla2020",
        {"guarantee type": "learned", "partial monotonicity": "not-addressed"},
    )
    result = _run(root, monkeypatch)
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["rendered"] == ["vanilla2020"]
    assert payload["changed"] is True
    text = _positioning(root).read_text(encoding="utf-8")
    assert f"| vanilla2020 | learned | {MATRIX_NOT_ADDRESSED} |" in text
    assert "| **This paper** | architectural | yes |" in text


def test_render_restricted_to_named_citekeys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(root, "a2020", {"guarantee type": "one", "partial monotonicity": "no"})
    _extract(root, "b2021", {"guarantee type": "two", "partial monotonicity": "no"})
    result = _run(root, monkeypatch, "--citekey", "a2020")
    assert result.exit_code == 0
    text = _positioning(root).read_text(encoding="utf-8")
    assert "| a2020 |" in text
    assert "b2021" not in text


def test_render_leaves_the_document_untouched_when_nothing_was_extracted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not "rendered zero rows": no paper was extracted, and saying so is the job."""
    root = _repo(tmp_path)
    (root / "docs" / "research" / "literature" / "digests").mkdir(parents=True)
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "no extracted papers" in result.stderr
    assert json.loads(result.stdout)["ok"] is False
    assert _positioning(root).read_bytes() == before


def test_render_reports_an_unreadable_artifact_and_still_lands_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(root, "good2020", {"guarantee type": "one", "partial monotonicity": "no"})
    broken = _extract(
        root, "bad2021", {"guarantee type": "two", "partial monotonicity": "no"}
    )
    broken.write_text("---\nstatus:\n  extraction: {}\n---\n\nno block\n", "utf-8")
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["rendered"] == ["good2020"]
    assert [e["citekey"] for e in payload["errors"]] == ["bad2021"]
    assert "Traceback" not in (result.stdout + result.stderr)
    text = _positioning(root).read_text(encoding="utf-8")
    assert "| good2020 |" in text
    assert "bad2021" not in text  # no row invented for a paper we could not read


def test_render_refuses_a_placeholder_matrix_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    placeholder = (
        "# Positioning\n\n## Concept matrix\n\n| Method | <attr 1> |\n|---|---|\n"
    )
    root = _repo(tmp_path, placeholder)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "template placeholders" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    assert _positioning(root).read_bytes() == before


def test_render_still_emits_a_report_when_the_merge_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused merge is a run outcome, so it gets the run's report too.

    And the report must not claim the papers it *would* have written: the
    document is byte-identical, so nothing was rendered.
    """
    placeholder = (
        "# Positioning\n\n## Concept matrix\n\n| Method | <attr 1> |\n|---|---|\n"
    )
    root = _repo(tmp_path, placeholder)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["batch"] == ["x2020"]
    assert payload["rendered"] == []
    assert payload["changed"] is False
    assert "template placeholders" in payload["error"]
    assert _positioning(root).read_bytes() == before


def test_render_reports_no_error_when_the_merge_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    result = _run(root, monkeypatch)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["error"] is None


def test_render_reports_a_write_failure_rather_than_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "write_text", _boom)
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "read-only file system" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_render_outside_a_paper_exits_2_naming_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "render"])
    assert result.exit_code == 2
    assert "--paper" in result.stderr


def test_render_is_idempotent_at_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    assert _run(root, monkeypatch).exit_code == 0
    once = _positioning(root).read_bytes()
    second = _run(root, monkeypatch)
    assert second.exit_code == 0
    assert json.loads(second.stdout)["changed"] is False
    assert _positioning(root).read_bytes() == once


def test_two_concept_matrix_sections_are_refused_not_guessed(tmp_path: Path) -> None:
    """Which section is the matrix cannot be guessed; the file is not written."""
    doubled = POSITIONING + "\n## Concept matrix\n\n| Method | other |\n|---|---|\n"
    target = _write(tmp_path, doubled)
    before = target.read_bytes()
    with pytest.raises(ExtractionError, match="2 headings"):
        render_matrix(target, {"x2020": {"guarantee type": "v"}})
    assert target.read_bytes() == before


def test_a_matrix_heading_inside_a_fence_is_not_a_second_matrix(
    tmp_path: Path,
) -> None:
    shown = POSITIONING.replace(
        "```markdown\n| Method | example axis |",
        "```markdown\n## Concept matrix\n\n| Method | example axis |",
    )
    out = render_matrix(
        _write(tmp_path, shown),
        {"vanilla2020": {"guarantee type": "learned", "partial monotonicity": "no"}},
    )
    assert "| vanilla2020 | learned | no |" in out


def test_the_cli_refuses_an_ambiguous_matrix_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubled = POSITIONING + "\n## Concept matrix\n\n| Method | other |\n|---|---|\n"
    root = _repo(tmp_path, doubled)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "2 headings" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    assert _positioning(root).read_bytes() == before


def test_a_legend_table_above_the_matrix_is_refused_not_overwritten(
    tmp_path: Path,
) -> None:
    """The worst pairing: the legend destroyed and the matrix never touched."""
    with_legend = POSITIONING.replace(
        "<!-- rows = prior work; the last row is our delta -->\n",
        "<!-- rows = prior work; the last row is our delta -->\n\n"
        "| symbol | meaning |\n|---|---|\n| yes | holds unconditionally |\n",
    )
    target = _write(tmp_path, with_legend)
    before = target.read_bytes()
    with pytest.raises(ExtractionError, match="holds 2 tables"):
        render_matrix(target, {"x2020": {"guarantee type": "v"}})
    assert target.read_bytes() == before


def test_the_cli_refuses_a_section_holding_two_tables_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_legend = POSITIONING.replace(
        "<!-- rows = prior work; the last row is our delta -->\n",
        "<!-- rows = prior work; the last row is our delta -->\n\n"
        "| symbol | meaning |\n|---|---|\n| yes | holds unconditionally |\n",
    )
    root = _repo(tmp_path, with_legend)
    _extract(root, "x2020", {"guarantee type": "v", "partial monotonicity": "no"})
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "holds 2 tables" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    assert _positioning(root).read_bytes() == before


def test_a_repeated_header_column_is_refused_before_it_eats_a_row_label(
    tmp_path: Path,
) -> None:
    """``| Method | Method |``: the label cell collapses and a bogus row appears."""
    doubled_column = (
        "# Positioning\n\n## Concept matrix\n\n| Method | Method |\n|---|---|\n"
        "| sill1997 | arch |\n"
    )
    target = _write(tmp_path, doubled_column)
    before = target.read_bytes()
    with pytest.raises(ExtractionError, match="duplicate column names"):
        render_matrix(target, {"x2020": {"Method": "v"}})
    assert target.read_bytes() == before


def test_an_all_unreadable_batch_does_not_report_an_empty_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure must not be announced as a legitimate empty result.

    Every artifact was unreadable, so whether anything was extracted is
    *unknown*. Saying "no extracted papers — run `digest extract record`" would
    state a falsehood and prescribe the wrong repair.
    """
    root = _repo(tmp_path)
    broken = _extract(root, "bad2021", {"guarantee type": "v"})
    broken.write_text("not a digest at all\n", encoding="utf-8")
    before = _positioning(root).read_bytes()
    result = _run(root, monkeypatch)
    assert result.exit_code == 1
    assert "no extracted papers" not in result.stderr
    assert "could not be read" in result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [e["citekey"] for e in payload["errors"]] == ["bad2021"]
    assert _positioning(root).read_bytes() == before
