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
    assert len(b._today()) == 10


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
