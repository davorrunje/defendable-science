"""Tests for the shared exploration-backlog helper (defendable-science#5)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.exploration import backlog as b

if TYPE_CHECKING:
    from pathlib import Path

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
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    root = b.scaffold_paper(
        research, "depth-collapse", "a follow-up paper", backend="bench"
    )
    assert (root / "paper" / "pitch.md").is_file()
    assert (root / "backlog.md").is_file()
    registry = (research / "papers.md").read_text(encoding="utf-8")
    assert "depth-collapse" in registry
    assert "bench" in registry
    with pytest.raises(b.BacklogError, match="already"):
        b.scaffold_paper(research, "depth-collapse", "dup")


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


def test_registry_root_fallback(tmp_path: Path) -> None:
    research = tmp_path / "a" / "b"
    research.mkdir(parents=True)
    outside = tmp_path.parent / "elsewhere-xyz"
    assert b._registry_root(outside, research) == str(outside)


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
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    (research / "papers.md").write_text(_REGISTRY_DOC, encoding="utf-8")
    b.scaffold_paper(research, "second", "a follow-up paper", backend="sim")
    doc = b._parse_document((research / "papers.md").read_text(encoding="utf-8"))
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


def test_promote_scaffold_paper_registers_and_reports(tmp_path: Path) -> None:
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
        ("hypothesis", [], "--paper-root"),
        ("paper", ["--research-root", "x"], "--backend"),
        ("paper", ["--backend", "bench"], "--research-root"),
    ],
)
def test_promote_scaffold_missing_option_exits_2(
    tmp_path: Path, level: str, extra: list[str], wanted: str
) -> None:
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
