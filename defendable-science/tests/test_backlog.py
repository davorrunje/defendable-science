"""Tests for the shared exploration-backlog helper (defendable-science#5)."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.exploration import backlog as b
from defendable_science.scaffold import status as st
from defendable_science.scaffold.layout import Layout


def _split_frontmatter(text: str) -> str:
    """Return the YAML frontmatter source of a markdown document."""
    match = re.search(r"\A---\n(.*?)^---\n", text, re.S | re.M)
    assert match is not None, "no terminated YAML frontmatter"
    return match.group(1)


runner = CliRunner()


def test_round_trip_preserves_rows() -> None:
    board = b.Backlog(level="hypothesis")
    board.add("X does Y under Z", "scouted:W123")
    board.park("a hunch", "own")
    reloaded = b.Backlog.loads(board.dumps(), "hypothesis")
    assert [r["one-line"] for r in reloaded.rows] == ["X does Y under Z", "a hunch"]
    assert reloaded.rows[0]["status"] == "candidate"
    assert reloaded.rows[1]["status"] == "parked"


def test_pipe_in_provenance_survives_round_trip() -> None:
    board = b.Backlog(level="hypothesis")
    snippet = "unlike [anchor] | our method needs no lattice"
    board.add("a claim", snippet)
    reloaded = b.Backlog.loads(board.dumps(), "hypothesis")
    assert reloaded.rows[0]["provenance"] == snippet


def test_park_and_add_require_provenance() -> None:
    board = b.Backlog(level="hypothesis")
    with pytest.raises(b.BacklogError, match="provenance is required"):
        board.park("idea", "  ")
    with pytest.raises(b.BacklogError, match="provenance is required"):
        board.add("idea", "")


def test_rank_only_from_candidate_or_parked() -> None:
    board = b.Backlog(level="hypothesis")
    row = board.add("claim", "own")
    board.rank(row["id"], EIG="high", feas="med", interest="high")
    assert board.get(row["id"])["status"] == "ranked"
    assert board.get(row["id"])["EIG"] == "high"
    # Ranking an already-ranked row is illegal.
    with pytest.raises(b.BacklogError, match="cannot rank"):
        board.rank(row["id"])


def test_promote_only_from_ranked() -> None:
    board = b.Backlog(level="hypothesis")
    row = board.add("claim", "own")
    with pytest.raises(b.BacklogError, match="cannot promote"):
        board.promote(row["id"])
    board.rank(row["id"])
    board.promote(row["id"])
    assert board.get(row["id"])["status"] == "promoted"


def test_drop_requires_reason_and_keeps_row() -> None:
    board = b.Backlog(level="hypothesis")
    row = board.add("claim", "own")
    with pytest.raises(b.BacklogError, match="drop reason is required"):
        board.drop(row["id"], "")
    board.drop(row["id"], "superseded by newer idea")
    kept = board.get(row["id"])
    assert kept["status"] == "dropped"
    assert kept["note"] == "superseded by newer idea"


def test_unknown_id_raises() -> None:
    board = b.Backlog(level="hypothesis")
    with pytest.raises(b.BacklogError, match="no backlog row"):
        board.get("nope")


def test_fresh_ids_are_unique() -> None:
    board = b.Backlog(level="hypothesis")
    a = board.add("same title", "own")
    c = board.add("same title", "own")
    assert a["id"] != c["id"]


def test_paper_level_uses_lens_columns() -> None:
    board = b.Backlog(level="paper")
    assert "lens" in board.columns
    assert "EIG" not in board.columns


def test_scaffold_hypothesis_writes_frontmatter(tmp_path: Path) -> None:
    target = b.scaffold_hypothesis(
        tmp_path / "paperA",
        "2026-07-18-monotone-depth",
        "deep nets beat shallow",
        'scouted:W1 "snippet"',
        today="2026-07-18",
    )
    text = target.read_text(encoding="utf-8")
    assert target.name == "hypothesis.md"
    assert "level: hypothesis" in text
    assert "id: 2026-07-18-monotone-depth" in text
    assert "last-updated: 2026-07-18" in text
    assert 'scouted:W1 "snippet"' in text
    # Refuses to overwrite.
    with pytest.raises(b.BacklogError, match="already exists"):
        b.scaffold_hypothesis(
            tmp_path / "paperA", "2026-07-18-monotone-depth", "x", "own"
        )


def test_scaffold_paper_creates_root_and_registers(tmp_path: Path) -> None:
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    root = b.scaffold_paper(
        layout, "depth-collapse", "a follow-up paper", backend="bench"
    )
    assert (root / "paper" / "pitch.md").is_file()
    assert (root / "backlog.md").is_file()
    registry = layout.papers_registry.read_text(encoding="utf-8")
    assert "depth-collapse" in registry
    assert "bench" in registry
    with pytest.raises(b.BacklogError, match="already"):
        b.scaffold_paper(layout, "depth-collapse", "dup")


def test_append_papers_registry_rejects_duplicate(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")
    with pytest.raises(b.BacklogError, match="already"):
        b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")


# --- CLI ---------------------------------------------------------------------


def test_cli_park_then_list(tmp_path: Path) -> None:
    path = tmp_path / "backlog.md"
    result = runner.invoke(
        app,
        ["backlog", "park", "an idea", "--provenance", "own", "--backlog", str(path)],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "parked"

    listed = runner.invoke(app, ["backlog", "list", "--backlog", str(path)])
    assert listed.exit_code == 0
    assert len(json.loads(listed.stdout)) == 1


def test_cli_park_without_provenance_fails(tmp_path: Path) -> None:
    path = tmp_path / "backlog.md"
    result = runner.invoke(
        app, ["backlog", "park", "idea", "--provenance", "", "--backlog", str(path)]
    )
    assert result.exit_code == 1


def test_cli_bad_level_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["backlog", "list", "--backlog", str(tmp_path / "b.md"), "--level", "galaxy"],
    )
    assert result.exit_code == 2


def test_cli_full_lifecycle(tmp_path: Path) -> None:
    path = str(tmp_path / "backlog.md")
    added = runner.invoke(
        app,
        [
            "backlog",
            "add",
            "claim",
            "--provenance",
            "own",
            "--backlog",
            path,
            "--id",
            "h1",
        ],
    )
    assert added.exit_code == 0
    ranked = runner.invoke(
        app, ["backlog", "rank", "h1", "--backlog", path, "--feas", "high"]
    )
    assert json.loads(ranked.stdout)["status"] == "ranked"
    promoted = runner.invoke(app, ["backlog", "promote", "h1", "--backlog", path])
    assert json.loads(promoted.stdout)["status"] == "promoted"


def test_cli_add_without_provenance_fails(tmp_path: Path) -> None:
    path = str(tmp_path / "b.md")
    result = runner.invoke(
        app, ["backlog", "add", "x", "--provenance", "", "--backlog", path]
    )
    assert result.exit_code == 1


def test_cli_rank_unknown_id_fails(tmp_path: Path) -> None:
    path = str(tmp_path / "b.md")
    result = runner.invoke(app, ["backlog", "rank", "nope", "--backlog", path])
    assert result.exit_code == 1


def test_cli_promote_not_ranked_fails(tmp_path: Path) -> None:
    path = str(tmp_path / "b.md")
    runner.invoke(
        app,
        ["backlog", "add", "c", "--provenance", "own", "--backlog", path, "--id", "h1"],
    )
    result = runner.invoke(app, ["backlog", "promote", "h1", "--backlog", path])
    assert result.exit_code == 1


def test_cli_drop_and_list_status(tmp_path: Path) -> None:
    path = str(tmp_path / "b.md")
    runner.invoke(
        app,
        ["backlog", "add", "c", "--provenance", "own", "--backlog", path, "--id", "h1"],
    )
    dropped = runner.invoke(
        app, ["backlog", "drop", "h1", "--reason", "superseded", "--backlog", path]
    )
    assert dropped.exit_code == 0
    assert json.loads(dropped.stdout)["status"] == "dropped"
    listed = runner.invoke(
        app, ["backlog", "list", "--backlog", path, "--status", "dropped"]
    )
    assert len(json.loads(listed.stdout)) == 1


def test_cli_drop_without_reason_fails(tmp_path: Path) -> None:
    path = str(tmp_path / "b.md")
    runner.invoke(
        app,
        ["backlog", "add", "c", "--provenance", "own", "--backlog", path, "--id", "h1"],
    )
    result = runner.invoke(
        app, ["backlog", "drop", "h1", "--reason", "", "--backlog", path]
    )
    assert result.exit_code == 1


def test_add_duplicate_id_raises() -> None:
    board = b.Backlog(level="hypothesis")
    board.add("x", "own", row_id="h1")
    with pytest.raises(b.BacklogError, match="already exists"):
        board.add("y", "own", row_id="h1")


def test_today_is_iso() -> None:
    assert len(b.today_iso()) == 10


def test_registry_root_outside_the_repo_is_reported_in_full(tmp_path: Path) -> None:
    # A registry row must never hide where the paper really is.
    outside = tmp_path.parent / "elsewhere-xyz"
    assert b.registry_root(Layout.default(tmp_path), outside) == str(outside)


def test_split_cells_without_borders() -> None:
    assert b._split_cells("a | b | c") == ["a", "b", "c"]


def test_loads_ragged_row_raises() -> None:
    # A short row would silently pad required columns (id/status/provenance).
    text = "| id | one-line | status |\n|---|---|---|\n| h1 |\n"
    with pytest.raises(b.BacklogError, match="ragged backlog row"):
        b.Backlog.loads(text, "hypothesis")


def test_loads_over_wide_row_raises() -> None:
    text = "| id | status |\n|---|---|\n| h1 | parked | extra |\n"
    with pytest.raises(b.BacklogError, match="ragged backlog row"):
        b.Backlog.loads(text, "hypothesis")


def test_loads_malformed_table_without_separator_raises() -> None:
    # Table-like rows with no GFM separator must not read as a genuinely empty
    # backlog (which would be indistinguishable from a real one).
    text = "| id | one-line | status |\n| h1 | an idea | parked |\n"
    with pytest.raises(b.BacklogError, match="malformed backlog table"):
        b.Backlog.loads(text, "hypothesis")


def test_loads_blank_document_is_empty_not_malformed() -> None:
    assert b.Backlog.loads("", "hypothesis").rows == []
    assert b.Backlog.loads("just prose, no table\n", "hypothesis").rows == []


def test_get_second_row() -> None:
    board = b.Backlog(level="hypothesis")
    board.add("first", "own", row_id="a")
    board.add("second", "own", row_id="z")
    assert board.get("z")["one-line"] == "second"


def test_rank_rejects_foreign_score() -> None:
    board = b.Backlog(level="paper")  # paper level has no EIG column
    board.add("p", "own", row_id="p1")
    # A level-mismatched score must not vanish silently while the row is ranked.
    with pytest.raises(b.BacklogError, match="unknown score key"):
        board.rank("p1", EIG="high", feas="med")
    assert board.get("p1")["status"] == "candidate"  # transition did not happen


def test_append_registry_without_trailing_newline(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    papers.write_text("| paper-id | root | backend |\n|---|---|---|", encoding="utf-8")
    b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")
    assert "p1" in papers.read_text(encoding="utf-8")


def test_loads_skips_lines_without_pipe() -> None:
    text = "some prose\n| id | status |\n|---|---|\n| h1 | parked |\n"
    board = b.Backlog.loads(text, "hypothesis")
    assert len(board.rows) == 1


def test_fresh_id_double_collision() -> None:
    board = b.Backlog(level="hypothesis")
    ids = {board.add("same title", "own")["id"] for _ in range(3)}
    assert len(ids) == 3  # base, base-2, base-3


def test_loads_ignores_prose_pipes_before_table() -> None:
    board = b.Backlog(level="hypothesis")
    board.add("real claim", "own")
    table = board.dumps()
    # Prose above the table that itself contains stray pipes must NOT be mistaken
    # for the header row (which is fixed by the following GFM separator).
    doc = (
        "|---|---|\n\n"  # a stray separator with no pending header candidate
        "Notes: we compare cost | benefit | effort here.\n\n"
        "Another | stray | prose line with no separator\n\n" + table
    )
    reloaded = b.Backlog.loads(doc, "hypothesis")
    assert [r["one-line"] for r in reloaded.rows] == ["real claim"]
    assert reloaded.columns == board.columns  # header taken from the real table


# --- host-document preservation (#94) ----------------------------------------

#: A hand-written portfolio backlog: heading, prose, table, prose after it.
_HOST_DOC = """# Portfolio backlog

Paper-level ideas not yet promoted to a paper root.

| id | one-line | lens | provenance | feas | interest | status | note |
|---|---|---|---|---|---|---|---|
| earlier | some earlier idea | a lens | a resolved paper | med | high | parked | keep me |

## How to use this file

Rank before promoting; never delete a row.
"""


def _assert_host_doc_intact(text: str) -> None:
    """Assert the prose and the pre-existing row survived a write."""
    assert text.startswith("# Portfolio backlog\n")
    assert "Paper-level ideas not yet promoted to a paper root." in text
    assert text.endswith("Rank before promoting; never delete a row.\n")
    assert "## How to use this file" in text
    assert "| earlier | some earlier idea | a lens |" in text
    assert "keep me" in text


def test_load_mutate_save_preserves_prose(tmp_path: Path) -> None:
    # The load → mutate → save round trip must not own anything but the table.
    path = tmp_path / "portfolio-backlog.md"
    path.write_text(_HOST_DOC, encoding="utf-8")
    board = b.Backlog.load(path, "paper")
    board.park("a fresh idea", "own")
    board.save(path)
    text = path.read_text(encoding="utf-8")
    _assert_host_doc_intact(text)
    assert "| a-fresh-idea | a fresh idea |" in text


def test_untouched_load_save_is_byte_identical(tmp_path: Path) -> None:
    path = tmp_path / "portfolio-backlog.md"
    path.write_text(_HOST_DOC, encoding="utf-8")
    b.Backlog.load(path, "paper").save(path)
    assert path.read_text(encoding="utf-8") == _HOST_DOC


def test_foreign_header_refuses_mutation_rather_than_blanking() -> None:
    # The reproduction from defendable-science#94: a three-column hand-written
    # table. Rows must survive parsing AND serialization, and a mutation that
    # cannot be represented is refused loudly instead of writing blank cells.
    text = (
        "# Portfolio backlog\n\nSome prose.\n\n"
        "| idea | origin | note |\n|---|---|---|\n"
        "| some earlier idea | a resolved paper | keep me |\n"
    )
    board = b.Backlog.loads(text, "paper")
    assert board.rows == [
        {"idea": "some earlier idea", "origin": "a resolved paper", "note": "keep me"}
    ]
    assert board.dumps() == text  # nothing restructured, nothing blanked
    with pytest.raises(b.BacklogError, match="cannot carry required column"):
        board.park("a new idea", "own")


def test_superset_header_keeps_extra_columns(tmp_path: Path) -> None:
    # A consumer that added its own columns keeps them, and a new row leaves
    # them empty for the author rather than shifting the layout.
    path = tmp_path / "portfolio-backlog.md"
    cols = [*b.PAPER_COLUMNS, "readiness"]
    path.write_text(
        "| " + " | ".join(cols) + " |\n"
        "|" + "|".join("---" for _ in cols) + "|\n"
        "| earlier | old | lens | src | med | high | parked | note | ready |\n",
        encoding="utf-8",
    )
    board = b.Backlog.load(path, "paper")
    assert board.columns == cols
    board.park("a fresh idea", "own")
    board.save(path)
    text = path.read_text(encoding="utf-8")
    assert "| readiness |" in text
    assert "| earlier | old | lens | src | med | high | parked | note | ready |" in text
    rows = b.Backlog.load(path, "paper").rows
    assert rows[1]["readiness"] == ""  # extra column present but unset
    assert len(rows[1]) == len(cols)  # not ragged


def test_content_after_table_is_prose_not_rows() -> None:
    # A pipe line separated from the table by prose belongs to the host
    # document; absorbing it as a row would reformat text the tool does not own.
    text = (
        "| id | status |\n|---|---|\n| h1 | parked |\n"
        "\nAside: cost | benefit\n| h2 | parked |\n"
    )
    board = b.Backlog.loads(text, "hypothesis")
    assert board.rows == [{"id": "h1", "status": "parked"}]
    assert board.dumps() == text


def test_stray_separator_after_rows_ends_the_table() -> None:
    text = "| id | status |\n|---|---|\n| h1 | parked |\n|---|---|\ntrailing\n"
    board = b.Backlog.loads(text, "hypothesis")
    assert board.rows == [{"id": "h1", "status": "parked"}]
    assert board.postamble == "|---|---|\ntrailing\n"
    assert board.dumps() == text


def test_prose_only_document_gains_a_table_below_the_prose() -> None:
    # No trailing newline: the table must not be spliced mid-line.
    board = b.Backlog.loads("just prose, no table", "hypothesis")
    board.park("an idea", "own")
    out = board.dumps()
    assert out.startswith("just prose, no table\n| id |")


def test_drop_refuses_a_table_without_a_note_column() -> None:
    # The drop reason has nowhere to go, so the transition is refused rather
    # than recorded and then dropped on serialization (file-drawer discipline).
    cols = [c for c in b.HYPOTHESIS_COLUMNS if c != "note"]
    text = (
        "| " + " | ".join(cols) + " |\n"
        "|" + "|".join("---" for _ in cols) + "|\n"
        "| h1 | claim | move | src | high | med | high | frame | ranked |\n"
    )
    board = b.Backlog.loads(text, "hypothesis")
    with pytest.raises(b.BacklogError, match=r"required column\(s\) \['note'\]"):
        board.drop("h1", "superseded")
    assert board.dumps() == text


@pytest.mark.parametrize(
    ("one_line", "expected"),
    [
        (
            "A survey of monotonicity methods in machine learning",
            "a-survey-of-monotonicity-methods-in",
        ),
        ("short enough", "short-enough"),
        ("!!! ???", "row"),
        ("a" * 60, "a" * 40),  # a single word longer than the cap: hard cut
    ],
)
def test_slug_truncates_on_a_word_boundary(one_line: str, expected: str) -> None:
    assert b._slug(one_line) == expected


def test_minted_id_is_not_cut_mid_word() -> None:
    board = b.Backlog(level="paper")
    row = board.park("A survey of monotonicity methods in machine learning", "own")
    assert row["id"] == "a-survey-of-monotonicity-methods-in"


# --- CLI verbs preserve the host document (#94) ------------------------------


def test_cli_verbs_preserve_prose(tmp_path: Path) -> None:
    path = tmp_path / "portfolio-backlog.md"
    path.write_text(_HOST_DOC, encoding="utf-8")
    common = ["--backlog", str(path), "--level", "paper"]

    for args in (
        ["backlog", "park", "an idea", "--provenance", "own", "--id", "x1", *common],
        ["backlog", "add", "a claim", "--provenance", "own", "--id", "x2", *common],
        ["backlog", "rank", "x1", "--feas", "high", "--interest", "med", *common],
        ["backlog", "promote", "x1", *common],
        ["backlog", "drop", "x2", "--reason", "superseded", *common],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.stdout)
        _assert_host_doc_intact(path.read_text(encoding="utf-8"))

    rows = b.Backlog.load(path, "paper").rows
    assert [r["id"] for r in rows] == ["earlier", "x1", "x2"]
    assert rows[1]["status"] == "promoted"
    assert rows[2]["status"] == "dropped"
    assert rows[2]["note"] == "superseded"


# --- papers registry splicing (#95) ------------------------------------------

_REGISTRY_DOC = """# Papers

The portfolio registry.

| paper-id | root | backend |
|---|---|---|
| first | docs/research/first | bench |

## Scope notes

- **first** — the anchor paper.
"""


def test_registry_row_lands_inside_the_table(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    papers.write_text(_REGISTRY_DOC, encoding="utf-8")
    b.append_papers_registry(papers, "second", "docs/research/second", "sim")
    text = papers.read_text(encoding="utf-8")
    assert "| first | docs/research/first | bench |\n" in text
    assert "| second | docs/research/second | sim |\n\n## Scope notes" in text
    assert text.endswith("- **first** — the anchor paper.\n")
    # Still one table: the parser sees both rows.
    doc = b._parse_document(text)
    assert [r["paper-id"] for r in doc.rows] == ["first", "second"]


def test_registry_extra_columns_are_filled_empty(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    papers.write_text(
        "| paper-id | root | backend | readiness | covers (thesis aims) |\n"
        "|---|---|---|---|---|\n"
        "| first | docs/research/first | bench | drafting | A1 |\n",
        encoding="utf-8",
    )
    b.append_papers_registry(papers, "second", "docs/research/second", "sim")
    doc = b._parse_document(papers.read_text(encoding="utf-8"))
    assert doc.rows[1] == {
        "paper-id": "second",
        "root": "docs/research/second",
        "backend": "sim",
        "readiness": "",
        "covers (thesis aims)": "",
    }
    assert doc.rows[0]["readiness"] == "drafting"  # untouched


def test_registry_missing_required_column_raises(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    papers.write_text("| paper-id | root |\n|---|---|\n", encoding="utf-8")
    before = papers.read_text(encoding="utf-8")
    with pytest.raises(
        b.BacklogError, match=r"missing required column\(s\) \['backend'\]"
    ):
        b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")
    assert papers.read_text(encoding="utf-8") == before


def test_registry_malformed_table_raises(tmp_path: Path) -> None:
    papers = tmp_path / "papers.md"
    papers.write_text(
        "| paper-id | root | backend |\n| first | docs/research/first | bench |\n",
        encoding="utf-8",
    )
    with pytest.raises(b.BacklogError, match="malformed registry table"):
        b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")


def test_registry_absent_file_creates_three_column_table(tmp_path: Path) -> None:
    papers = tmp_path / "nested" / "papers.md"
    b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")
    assert papers.read_text(encoding="utf-8") == (
        "| paper-id | root | backend |\n|---|---|---|\n"
        "| p1 | docs/research/p1 | bench |\n"
    )


def test_registry_duplicate_id_in_prose_is_not_a_duplicate(tmp_path: Path) -> None:
    # The guard reads parsed rows, so a mention below the table is just prose.
    papers = tmp_path / "papers.md"
    papers.write_text(
        "| paper-id | root | backend |\n|---|---|---|\n\nNotes on | p1 | below.\n",
        encoding="utf-8",
    )
    b.append_papers_registry(papers, "p1", "docs/research/p1", "bench")
    assert "Notes on | p1 | below." in papers.read_text(encoding="utf-8")


def test_scaffold_paper_row_is_inside_the_table(tmp_path: Path) -> None:
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    layout.papers_registry.write_text(_REGISTRY_DOC, encoding="utf-8")
    b.scaffold_paper(layout, "second", "a follow-up paper", backend="sim")
    doc = b._parse_document(layout.papers_registry.read_text(encoding="utf-8"))
    assert [r["paper-id"] for r in doc.rows] == ["first", "second"]
    assert doc.rows[1]["root"] == "docs/research/second"
    assert doc.postamble.startswith("\n## Scope notes")


# --- promote --scaffold (#113) ------------------------------------------------


def _ranked_backlog(path: Path, level: str, row_id: str) -> None:
    """Write a backlog at `path` holding one ``ranked`` row `row_id`."""
    board = b.Backlog(level=level)  # type: ignore[arg-type]
    board.add("a claim worth testing", "scouted:W123", row_id=row_id)
    board.rank(row_id, feas="high", interest="high")
    board.save(path)


def test_promote_scaffold_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "backlog.md"
    _ranked_backlog(path, "hypothesis", "h1")
    paper_root = tmp_path / "docs" / "research" / "depth-collapse"
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "h1",
            "--backlog",
            str(path),
            "--paper-root",
            str(paper_root),
            "--scaffold",
            "--date",
            "2026-03-04",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["row"]["status"] == "promoted"
    target = paper_root / "hypotheses" / "2026-03-04-h1" / "hypothesis.md"
    assert payload["artifacts"] == {"hypothesis": str(target)}
    text = target.read_text(encoding="utf-8")
    assert "last-updated: 2026-03-04" in text
    assert "scouted:W123" in text  # provenance carried verbatim
    assert "a claim worth testing" in text
    assert b.Backlog.load(path, "hypothesis").get("h1")["status"] == "promoted"


def test_promote_scaffold_hypothesis_explicit_slug_and_default_date(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backlog.md"
    _ranked_backlog(path, "hypothesis", "h1")
    paper_root = tmp_path / "paper"
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "h1",
            "--backlog",
            str(path),
            "--paper-root",
            str(paper_root),
            "--scaffold",
            "--slug",
            "2026-01-01-hand-picked",
        ],
    )
    assert result.exit_code == 0, result.stdout
    target = paper_root / "hypotheses" / "2026-01-01-hand-picked" / "hypothesis.md"
    assert target.is_file()
    # No --date: last-updated falls back to today.
    assert f"last-updated: {b.today_iso()}" in target.read_text(encoding="utf-8")


def test_promote_scaffold_paper_registers_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # the repo root the registry row is relative to
    path = tmp_path / "portfolio-backlog.md"
    _ranked_backlog(path, "paper", "depth-collapse")
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "depth-collapse",
            "--backlog",
            str(path),
            "--level",
            "paper",
            "--scaffold",
            "--research-root",
            str(research),
            "--backend",
            "bench",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    root = research / "depth-collapse"
    assert payload["artifacts"] == {
        "paper_root": str(root),
        "pitch": str(root / "paper" / "pitch.md"),
        "backlog": str(root / "backlog.md"),
        "registry": str(research / "papers.md"),
    }
    assert (root / "paper" / "pitch.md").is_file()
    assert (root / "backlog.md").is_file()
    registry = b._parse_document((research / "papers.md").read_text(encoding="utf-8"))
    assert registry.rows == [
        {
            "paper-id": "depth-collapse",
            "root": "docs/research/depth-collapse",
            "backend": "bench",
        }
    ]


@pytest.mark.parametrize(
    ("level", "extra", "wanted"),
    [
        # No --paper-root, and a cwd outside every paper: the layout cannot say
        # which paper this hypothesis belongs to, so the option is named.
        ("hypothesis", [], "--paper-root"),
        ("paper", ["--research-root", "x"], "--backend"),
    ],
)
def test_promote_scaffold_missing_option_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    level: str,
    extra: list[str],
    wanted: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "backlog.md"
    _ranked_backlog(path, level, "r1")
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "r1",
            "--backlog",
            str(path),
            "--level",
            level,
            "--scaffold",
            *extra,
        ],
    )
    assert result.exit_code == 2
    assert wanted in result.stderr
    # Refused before any mutation: the row is still ranked.
    assert b.Backlog.load(path, level).get("r1")["status"] == "ranked"  # type: ignore[arg-type]


def test_promote_scaffold_refused_leaves_row_ranked(tmp_path: Path) -> None:
    # A promoted row with no artifact on disk is the inconsistency to avoid, so
    # the scaffold runs before the backlog is written and a refusal is retryable.
    path = tmp_path / "portfolio-backlog.md"
    _ranked_backlog(path, "paper", "depth-collapse")
    research = tmp_path / "docs" / "research"
    (research / "depth-collapse").mkdir(parents=True)  # already there
    args = [
        "backlog",
        "promote",
        "depth-collapse",
        "--backlog",
        str(path),
        "--level",
        "paper",
        "--scaffold",
        "--research-root",
        str(research),
        "--backend",
        "bench",
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert not (research / "papers.md").exists()  # no half-written registry
    assert b.Backlog.load(path, "paper").get("depth-collapse")["status"] == "ranked"

    # Retryable once the obstruction is gone.
    (research / "depth-collapse").rmdir()
    assert runner.invoke(app, args).exit_code == 0
    assert b.Backlog.load(path, "paper").get("depth-collapse")["status"] == "promoted"


def test_promote_without_scaffold_still_emits_the_bare_row(tmp_path: Path) -> None:
    path = tmp_path / "backlog.md"
    _ranked_backlog(path, "hypothesis", "h1")
    result = runner.invoke(app, ["backlog", "promote", "h1", "--backlog", str(path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "promoted"
    assert "artifacts" not in payload


# --- the scaffolded pitch carries status frontmatter (#96) --------------------
#
# The drift guard over the shipped templates lives in ``tests/test_status.py``,
# which covers all nine of them against the single renderer.


def test_scaffolded_pitch_has_status_frontmatter(tmp_path: Path) -> None:
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    root = b.scaffold_paper(
        layout,
        "depth-collapse",
        "Depth collapse explains the OOD gap",
        backend="bench",
        provenance="limitation-driven, from aug-policy-robustness §6",
        today="2026-03-04",
    )
    text = (root / "paper" / "pitch.md").read_text(encoding="utf-8")

    status = yaml.safe_load(_split_frontmatter(text))["status"]
    assert status["level"] == "paper"
    assert status["id"] == "depth-collapse"
    assert status["verdict"] is None
    assert status["readiness"] == "drafting"
    assert status["signed-off-by"] is None
    assert status["signed-off-date"] is None
    assert status["evidence"] == []
    assert status["blockers"] == []
    assert status["covers"] == []
    assert status["understanding"] == {"status": "pending", "unresolved": []}
    # YAML types an unquoted ISO date as a date, which is what `progress` sees.
    assert status["last-updated"] == date(2026, 3, 4)

    # Both fields carried from the backlog row are present, verbatim.
    assert "Depth collapse explains the OOD gap" in text
    assert "limitation-driven, from aug-policy-robustness §6" in text


def test_scaffolded_pitch_drafts_no_prose_for_the_author(tmp_path: Path) -> None:
    # A tracked stub, not a drafted pitch: seeding prose the author did not write
    # would cut against the agency principle (meta-spec 2.1).
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    root = b.scaffold_paper(layout, "p1", "a claim", backend="bench")
    text = (root / "paper" / "pitch.md").read_text(encoding="utf-8")
    for section in ("Contribution", "Target venue + bar", "Load-bearing hypotheses"):
        assert f"## {section}\n\n<!--" in text


def test_scaffolded_pitch_defaults_the_date_to_today(tmp_path: Path) -> None:
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    root = b.scaffold_paper(layout, "p1", "a claim")
    text = (root / "paper" / "pitch.md").read_text(encoding="utf-8")
    assert f"last-updated: {b.today_iso()}" in text


def test_promote_scaffold_pitch_is_tracked_end_to_end(tmp_path: Path) -> None:
    """The CLI path carries the row's provenance into the frontmatter'd pitch."""
    path = tmp_path / "portfolio-backlog.md"
    board = b.Backlog(level="paper")
    board.add("Depth collapse explains the OOD gap", "own reading", row_id="dc")
    board.rank("dc", feas="high", interest="high")
    board.save(path)
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "dc",
            "--backlog",
            str(path),
            "--level",
            "paper",
            "--scaffold",
            "--research-root",
            str(research),
            "--backend",
            "bench",
            "--date",
            "2026-03-04",
        ],
    )
    assert result.exit_code == 0, result.stdout
    pitch = Path(json.loads(result.stdout)["artifacts"]["pitch"])
    status = yaml.safe_load(_split_frontmatter(pitch.read_text(encoding="utf-8")))
    assert status["status"]["id"] == "dc"
    assert status["status"]["last-updated"] == date(2026, 3, 4)
    assert "own reading" in pitch.read_text(encoding="utf-8")


# --- every path comes from the resolver (#122) -------------------------------


def _flat_layout(repo_root: Path) -> Layout:
    """Build a layout whose papers sit under ``writing/``, not docs/research."""
    return Layout(
        repo_root=repo_root,
        research_root=repo_root / "writing",
        literature_dir=repo_root / "writing" / "literature",
        datasets_manifest=repo_root / "datasets.yml",
        thesis_dir=repo_root / "writing" / "thesis",
    )


def test_registry_root_is_correct_under_a_non_default_research_root(
    tmp_path: Path,
) -> None:
    """``research.parent.parent`` was wrong for any research_root but docs/research."""
    layout = Layout.default(tmp_path)
    flat = _flat_layout(tmp_path)

    assert b.registry_root(layout, layout.paper_dir("dc")) == "docs/research/dc"
    assert b.registry_root(flat, flat.paper_dir("dc")) == "writing/dc"


def test_scaffold_paper_registers_the_root_relative_to_the_layouts_repo_root(
    tmp_path: Path,
) -> None:
    flat = _flat_layout(tmp_path)
    flat.research_root.mkdir()

    b.scaffold_paper(flat, "dc", "Depth collapse", backend="bench")

    doc = b._parse_document(flat.papers_registry.read_text(encoding="utf-8"))
    assert doc.rows == [{"paper-id": "dc", "root": "writing/dc", "backend": "bench"}]


def test_scaffolded_hypothesis_and_pitch_status_blocks_come_from_the_renderer(
    tmp_path: Path,
) -> None:
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)
    root = b.scaffold_paper(
        layout,
        "dc",
        "Depth collapse",
        backend="bench",
        provenance="p",
        today="2026-03-04",
    )
    pitch = (root / "paper" / "pitch.md").read_text(encoding="utf-8")
    target = b.scaffold_hypothesis(
        root, "2026-03-04-monotone", "Monotone depth", "p", today="2026-03-04"
    )
    hypothesis = target.read_text(encoding="utf-8")

    assert st.render("paper", {"id": "dc", "last-updated": "2026-03-04"}) in pitch
    assert (
        st.render(
            "hypothesis",
            {"id": "2026-03-04-monotone", "last-updated": "2026-03-04"},
        )
        in hypothesis
    )


def _onboard(tmp_path: Path, config: str = "") -> None:
    """Write a ``.defendable-science/config.yml`` so `tmp_path` is the repo root."""
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text(config, encoding="utf-8")


def test_park_resolves_the_backlog_from_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path, "layout:\n  research_root: writing/\n")
    paper = tmp_path / "writing" / "dc"
    (paper / "hypotheses").mkdir(parents=True)
    (paper / "backlog.md").write_text(
        b.Backlog(level="hypothesis").dumps(), encoding="utf-8"
    )
    monkeypatch.chdir(paper / "hypotheses")  # inside the paper, not at its root

    result = runner.invoke(app, ["backlog", "park", "An idea", "--provenance", "smoke"])

    assert result.exit_code == 0, result.stdout
    assert "An idea" in (paper / "backlog.md").read_text(encoding="utf-8")
    assert not (paper / "hypotheses" / "backlog.md").exists()


def test_an_explicit_backlog_still_wins_over_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path, "layout:\n  research_root: writing/\n")
    paper = tmp_path / "writing" / "dc"
    paper.mkdir(parents=True)
    (paper / "backlog.md").write_text(
        b.Backlog(level="hypothesis").dumps(), encoding="utf-8"
    )
    elsewhere = tmp_path / "elsewhere.md"
    monkeypatch.chdir(paper)

    result = runner.invoke(
        app,
        [
            "backlog",
            "park",
            "An idea",
            "--provenance",
            "smoke",
            "--backlog",
            str(elsewhere),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "An idea" in elsewhere.read_text(encoding="utf-8")
    assert "An idea" not in (paper / "backlog.md").read_text(encoding="utf-8")


def test_hypothesis_backlog_outside_any_paper_names_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Failure honesty: not a traceback, and not a silently-wrong ./backlog.md.
    _onboard(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["backlog", "park", "An idea", "--provenance", "smoke"])

    assert result.exit_code == 2
    assert "--backlog" in result.stderr
    assert "not inside a paper" in result.stderr
    assert not (tmp_path / "backlog.md").exists()


def test_a_portfolio_backlog_with_no_research_dir_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["backlog", "list", "--level", "paper"])

    assert result.exit_code == 2
    assert "--backlog" in result.stderr
    assert "docs/research" in result.stderr


def test_an_invalid_layout_block_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path, "layout:\n  nope: writing/\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["backlog", "list", "--level", "paper"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.stderr


def test_promote_scaffold_needs_no_path_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path)
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    (research / "portfolio-backlog.md").write_text(
        b.Backlog(level="paper").dumps(), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    runner.invoke(
        app,
        ["backlog", "park", "Depth collapse", "--provenance", "p", "--level", "paper"],
    )
    runner.invoke(
        app, ["backlog", "rank", "depth-collapse", "--level", "paper", "--feas", "3"]
    )
    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "depth-collapse",
            "--level",
            "paper",
            "--scaffold",
            "--backend",
            "bench",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (research / "depth-collapse" / "paper" / "pitch.md").is_file()
    registry = b._parse_document((research / "papers.md").read_text(encoding="utf-8"))
    assert registry.rows[0]["root"] == "docs/research/depth-collapse"


def test_promote_scaffold_resolves_the_paper_root_from_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _onboard(tmp_path)
    paper = tmp_path / "docs" / "research" / "dc"
    (paper / "hypotheses").mkdir(parents=True)
    _ranked_backlog(paper / "backlog.md", "hypothesis", "h1")
    monkeypatch.chdir(paper / "hypotheses")  # deep inside the paper, not at its root

    result = runner.invoke(
        app, ["backlog", "promote", "h1", "--scaffold", "--date", "2026-03-04"]
    )

    assert result.exit_code == 0, result.stdout
    target = paper / "hypotheses" / "2026-03-04-h1" / "hypothesis.md"
    assert json.loads(result.stdout)["artifacts"] == {"hypothesis": str(target)}
    assert b.Backlog.load(paper / "backlog.md", "hypothesis").get("h1")["status"] == (
        "promoted"
    )


def test_promote_scaffold_registers_under_a_non_default_research_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end cover for the bug: the registry row must read ``writing/dc``."""
    _onboard(tmp_path, "layout:\n  research_root: writing/\n")
    writing = tmp_path / "writing"
    writing.mkdir()
    _ranked_backlog(writing / "portfolio-backlog.md", "paper", "dc")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "dc",
            "--level",
            "paper",
            "--scaffold",
            "--backend",
            "bench",
        ],
    )

    assert result.exit_code == 0, result.stdout
    registry = b._parse_document((writing / "papers.md").read_text(encoding="utf-8"))
    assert registry.rows == [
        {"paper-id": "dc", "root": "writing/dc", "backend": "bench"}
    ]
    assert json.loads(result.stdout)["artifacts"] == {
        "paper_root": str(writing / "dc"),
        "pitch": str(writing / "dc" / "paper" / "pitch.md"),
        "backlog": str(writing / "dc" / "backlog.md"),
        "registry": str(writing / "papers.md"),
    }


def test_an_explicit_research_root_is_still_rendered_against_the_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --research-root overrides *where the tree goes*, never *what the repo root
    # is*: guessing the latter from the former's grandparent wrote `repo/writing/dc`.
    _onboard(tmp_path)
    writing = tmp_path / "writing"
    writing.mkdir()
    path = tmp_path / "portfolio-backlog.md"
    _ranked_backlog(path, "paper", "dc")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "backlog",
            "promote",
            "dc",
            "--backlog",
            str(path),
            "--level",
            "paper",
            "--scaffold",
            "--research-root",
            str(writing),
            "--backend",
            "bench",
        ],
    )

    assert result.exit_code == 0, result.stdout
    registry = b._parse_document((writing / "papers.md").read_text(encoding="utf-8"))
    assert registry.rows[0]["root"] == "writing/dc"


def test_registry_dumps_produces_a_registry_append_papers_registry_accepts(
    tmp_path: Path,
) -> None:
    """The 4th `state` column an agent invented is why promote could not register."""
    papers = tmp_path / "papers.md"
    papers.write_text(b.registry_dumps(), encoding="utf-8")

    b.append_papers_registry(papers, "depth-collapse", "docs/research/dc", "bench")

    text = papers.read_text(encoding="utf-8")
    header = [c.strip() for c in text.splitlines()[7].strip("|").split("|")]
    assert header == b.REGISTRY_COLUMNS
    assert "depth-collapse" in text


def test_registry_dumps_carries_a_heading_and_no_data_rows() -> None:
    text = b.registry_dumps()

    assert text.startswith("# Papers registry\n")
    assert "| paper-id | root | backend |" in text
    assert "|---" in text
    assert text.count("\n|") == 2  # header + separator only
