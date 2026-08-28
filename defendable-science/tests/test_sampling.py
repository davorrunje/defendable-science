"""The deterministic sampled check — the kernel and its CLI surface (spec §8).

Determinism is the anti-gaming property the whole of extraction mode rests on,
so the pins here are deliberately *literal*: `test_select_sample_pins_the_draw`
names the three papers a specific batch must always draw, and
`test_select_sample_is_stable_across_processes` re-draws them in fresh
interpreters under different ``PYTHONHASHSEED`` values. A test that merely drew
twice in one process would pass over a `hash()`-seeded implementation, which
re-rolls the sample on every run — exactly the hole this feature must not have.

The negatives carry the rest (spec §11): a ``failed`` verdict leaves every cell
byte-identical, lands on **unsampled** members too, and never writes
``status.understanding``; an artifact with no ``status.extraction`` block is not
part of an extraction batch; and ``--all`` over an empty digests directory is a
loud failure, not a passed sample of size zero.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.core.frontmatter import split_frontmatter
from defendable_science.digest import artifact as artifact_mod
from defendable_science.digest.extraction import Cell, ExtractionError
from defendable_science.digest.sampling import default_size, select_sample

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

#: A fixed batch, used for every literal pin below.
BATCH = [
    "sill1997monotonic",
    "daniels2010monotone",
    "you2017deep",
    "gupta2016monotonic",
    "liu2020certified",
    "wehenkel2019unconstrained",
    "runje2023constrained",
    "nolte2023expressive",
]

#: What `BATCH` must draw, always, in every process. Changing the seeding
#: algorithm changes this list — which is the point: it is a contract with
#: every survey already checked against it, not an implementation detail.
EXPECTED_SAMPLE = [
    "nolte2023expressive",
    "runje2023constrained",
    "sill1997monotonic",
]


# --- the kernel -----------------------------------------------------------------


def test_select_sample_pins_the_draw_for_a_fixed_batch() -> None:
    assert select_sample(BATCH, 3) == EXPECTED_SAMPLE


def test_select_sample_ignores_the_input_order() -> None:
    """The batch is a set; the order it arrives in must not steer the draw."""
    assert select_sample(list(reversed(BATCH)), 3) == EXPECTED_SAMPLE


def test_select_sample_collapses_duplicates() -> None:
    assert select_sample(["a", "a", "b"], 3) == ["a", "b"]


def test_select_sample_is_stable_across_processes() -> None:
    """Two fresh interpreters, two different hash seeds, one sample.

    `hash()` on a `str` is salted per process, so seeding from it would pass
    every same-process test and still re-roll the sample on each run.
    """
    script = (
        "import json;"
        "from defendable_science.digest.sampling import select_sample;"
        f"print(json.dumps(select_sample({BATCH!r}, 3)))"
    )
    drawn = [
        json.loads(
            subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
            ).stdout
        )
        for seed in ("0", "1")
    ]
    assert drawn == [EXPECTED_SAMPLE, EXPECTED_SAMPLE]


def test_a_different_batch_draws_a_different_sample() -> None:
    """Adding one paper re-draws the batch — the sample is of *this* set."""
    assert select_sample([*BATCH, "zzz2024extra"], 3) != EXPECTED_SAMPLE


def test_a_batch_smaller_than_the_size_is_sampled_whole() -> None:
    assert select_sample(["a", "b"], 3) == ["a", "b"]


def test_select_sample_refuses_an_empty_batch() -> None:
    with pytest.raises(ExtractionError, match="empty batch"):
        select_sample([], 3)


def test_select_sample_refuses_a_size_below_one() -> None:
    with pytest.raises(ExtractionError, match="at least 1"):
        select_sample(BATCH, 0)


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, 0), (1, 1), (2, 2), (3, 3), (12, 3), (30, 3), (40, 4), (41, 5), (100, 10)],
)
def test_default_size(n: int, expected: int) -> None:
    assert default_size(n) == expected
    assert default_size(n) <= n


# --- the CLI surface -------------------------------------------------------------


def _cells(citekey: str) -> list[Cell]:
    """Build two recorded cells for `citekey`, one of them an absence."""
    return [
        Cell(
            citekey=citekey,
            axis="guarantee type",
            value="architectural",
            locator="§2, Eq. (3)",
        ),
        Cell(
            citekey=citekey,
            axis="partial monotonicity",
            value="not-addressed",
            justification="scoped to fully-monotone inputs in §1",
        ),
    ]


def _repo(tmp_path: Path, citekeys: list[str] = BATCH) -> Path:
    """Build an onboarded repo with one extracted artifact per citekey."""
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text("", encoding="utf-8")
    digests = tmp_path / "docs" / "research" / "literature" / "digests"
    digests.mkdir(parents=True)
    for citekey in citekeys:
        artifact_mod.write_extraction(
            digests / f"{citekey}.md",
            _cells(citekey),
            in_sample=False,
            batch_check="pending",
            log_dir=tmp_path / "seed-log",
            date="2026-08-28",
        )
    return tmp_path


def _run(root: Path, *args: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.chdir(root)
    return runner.invoke(app, ["digest", "extract", "sample", *args])


def _citekey_args(citekeys: list[str] = BATCH) -> list[str]:
    return [arg for key in citekeys for arg in ("--citekey", key)]


def _digest(root: Path, citekey: str) -> Path:
    return root / "docs" / "research" / "literature" / "digests" / f"{citekey}.md"


def _block(root: Path, citekey: str) -> dict[str, Any]:
    """Return the artifact's whole ``status:`` mapping."""
    fm_lines, _body = split_frontmatter(
        _digest(root, citekey).read_text(encoding="utf-8")
    )
    status: dict[str, Any] = yaml.safe_load("\n".join(fm_lines))["status"]
    return status


def _cells_bytes(root: Path, citekey: str) -> str:
    """Return the artifact's generated cells block, verbatim."""
    text = _digest(root, citekey).read_text(encoding="utf-8")
    begin = text.index(artifact_mod.CELLS_BEGIN)
    end = text.index(artifact_mod.CELLS_END) + len(artifact_mod.CELLS_END)
    return text[begin:end]


def test_sample_reports_the_draw_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    before = {k: _digest(root, k).read_bytes() for k in BATCH}
    result = _run(root, *_citekey_args(), monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["sample"] == EXPECTED_SAMPLE
    assert payload["batch"] == sorted(BATCH)
    assert payload["size"] == 3
    assert payload["verdict"] is None
    # Drawing is not recording: nothing on disk moved.
    assert {k: _digest(root, k).read_bytes() for k in BATCH} == before


def test_sample_reports_each_drawn_paper_s_cells_for_the_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The human is shown axis, value and locator — that is the check (§8)."""
    root = _repo(tmp_path)
    result = _run(root, *_citekey_args(), monkeypatch=monkeypatch)
    payload = json.loads(result.stdout)
    assert [p["citekey"] for p in payload["sampled"]] == EXPECTED_SAMPLE
    first = payload["sampled"][0]["cells"][0]
    assert first["axis"] == "guarantee type"
    assert first["value"] == "architectural"
    assert first["locator"] == "§2, Eq. (3)"


def test_sample_honours_an_explicit_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _run(root, *_citekey_args(), "--size", "5", monkeypatch=monkeypatch)
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)["sample"]) == 5


def test_sample_refuses_a_size_below_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _run(root, *_citekey_args(), "--size", "0", monkeypatch=monkeypatch)
    assert result.exit_code == 2


def test_all_collects_only_artifacts_carrying_an_extraction_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A depth-mode digest was never extracted, so it is not in the batch."""
    root = _repo(tmp_path, ["a1", "b2"])
    digests = root / "docs" / "research" / "literature" / "digests"
    (digests / "depthonly.md").write_text(
        "---\nstatus:\n  understanding: {status: complete}\n---\n\nprose\n",
        encoding="utf-8",
    )
    (digests / "notes.txt").write_text("not a digest\n", encoding="utf-8")
    result = _run(root, "--all", monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["batch"] == ["a1", "b2"]


def test_all_over_an_empty_digests_directory_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero extraction artifacts is a failed run, never a passed empty sample."""
    root = _repo(tmp_path, [])
    result = _run(root, "--all", monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["sample"] == []
    assert "no extracted papers" in result.stderr


def test_all_without_a_digests_directory_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, [])
    (root / "docs" / "research" / "literature" / "digests").rmdir()
    result = _run(root, "--all", monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_all_reports_an_unreadable_artifact_rather_than_skipping_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed artifact is not evidence that it was never extracted."""
    root = _repo(tmp_path, ["a1"])
    digests = root / "docs" / "research" / "literature" / "digests"
    (digests / "broken.md").write_text("no frontmatter here\n", encoding="utf-8")
    result = _run(root, "--all", monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [e["citekey"] for e in payload["errors"]] == ["broken"]


@pytest.mark.parametrize("args", [[], ["--all", "--citekey", "a1"]])
def test_exactly_one_of_citekey_and_all_is_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    root = _repo(tmp_path, ["a1"])
    result = _run(root, *args, monkeypatch=monkeypatch)
    assert result.exit_code == 2


def test_a_failed_verdict_marks_every_member_and_touches_no_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed sample is evidence about the batch, not about one paper (§8)."""
    root = _repo(tmp_path)
    cells_before = {k: _cells_bytes(root, k) for k in BATCH}
    result = _run(
        root, *_citekey_args(), "--verdict", "failed", monkeypatch=monkeypatch
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "failed"
    assert payload["updated"] == sorted(BATCH)
    unsampled = [k for k in sorted(BATCH) if k not in EXPECTED_SAMPLE]
    assert unsampled  # the assertion below is only meaningful if some exist
    for citekey in sorted(BATCH):
        status = _block(root, citekey)
        assert status["extraction"]["batch-check"] == "failed"
        # The two keys do not move together: `batch-check` is the verdict on the
        # run, `in-sample` is whether a human looked at *this* paper's cells.
        assert status["extraction"]["in-sample"] is (citekey in EXPECTED_SAMPLE)
        # The guarantee-inflation guard: extraction never claims comprehension.
        assert "understanding" not in status
        # Byte-identical cells: repairing the caught cell would convert a
        # population signal into a tidy-looking local fix.
        assert _cells_bytes(root, citekey) == cells_before[citekey]


def test_a_verified_verdict_marks_every_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _run(
        root, *_citekey_args(), "--verdict", "verified", monkeypatch=monkeypatch
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    for citekey in BATCH:
        assert _block(root, citekey)["extraction"]["batch-check"] == "verified"


def test_in_sample_marks_exactly_the_papers_the_draw_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two invocations must agree about who was checked.

    The verdict call re-draws with the same deterministic selector over the same
    membership set, so the papers marked ``in-sample: true`` are the ones the
    human was actually shown — not a second, differently-drawn set.
    """
    root = _repo(tmp_path)
    drawn = json.loads(_run(root, *_citekey_args(), monkeypatch=monkeypatch).stdout)
    shown = [p["citekey"] for p in drawn["sampled"]]
    # Drawing alone establishes nothing, so it must claim nothing.
    assert all(_block(root, k)["extraction"]["in-sample"] is False for k in BATCH)

    _run(root, *_citekey_args(), "--verdict", "verified", monkeypatch=monkeypatch)

    marked = [k for k in sorted(BATCH) if _block(root, k)["extraction"]["in-sample"]]
    assert marked == shown


def test_in_sample_follows_an_explicit_size_on_both_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    drawn = json.loads(
        _run(root, *_citekey_args(), "--size", "5", monkeypatch=monkeypatch).stdout
    )
    _run(
        root,
        *_citekey_args(),
        "--size",
        "5",
        "--verdict",
        "verified",
        monkeypatch=monkeypatch,
    )
    marked = [k for k in sorted(BATCH) if _block(root, k)["extraction"]["in-sample"]]
    assert marked == drawn["sample"]
    assert len(marked) == 5


def test_a_sampled_paper_whose_cells_could_not_be_read_is_not_marked_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The human cannot have checked cells the command could not show them."""
    root = _repo(tmp_path, ["a1", "b2"])
    target = _digest(root, "a1")
    fm_lines, _body = split_frontmatter(target.read_text(encoding="utf-8"))
    target.write_text(
        "---\n" + "\n".join(fm_lines) + "\n---\n\nprose only\n", encoding="utf-8"
    )
    result = _run(
        root,
        "--citekey",
        "a1",
        "--citekey",
        "b2",
        "--verdict",
        "failed",
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 1
    assert _block(root, "a1")["extraction"]["in-sample"] is False
    # The verdict on the run still lands — that is what a failed batch means.
    assert _block(root, "a1")["extraction"]["batch-check"] == "failed"
    assert _block(root, "b2")["extraction"]["in-sample"] is True


def test_an_unknown_verdict_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _run(
        root, *_citekey_args(), "--verdict", "pending", monkeypatch=monkeypatch
    )
    assert result.exit_code == 2


def test_the_verdict_logs_a_check_record_for_each_sampled_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-cell records land in the shared accountability log (§8)."""
    root = _repo(tmp_path)
    nested = root / "docs" / "research" / "literature"
    result = _run(
        root, *_citekey_args(), "--verdict", "verified", monkeypatch=monkeypatch
    )
    assert result.exit_code == 0
    log_dir = root / "docs" / "research" / "defend-log"
    written = sorted(p.name for p in log_dir.glob("*.yml"))
    assert len(written) == len(EXPECTED_SAMPLE)
    entry = yaml.safe_load(
        next(log_dir.glob(f"*{EXPECTED_SAMPLE[0]}.yml")).read_text(encoding="utf-8")
    )[0]
    assert entry["kind"] == "extraction-check"
    assert entry["verdict"] == "verified"
    assert entry["citekey"] == EXPECTED_SAMPLE[0]
    assert entry["batch"] == sorted(BATCH)
    assert [c["axis"] for c in entry["cells"]] == [
        "guarantee type",
        "partial monotonicity",
    ]
    assert json.loads(result.stdout)["log_entries"]
    assert nested.is_dir()


def test_the_log_default_is_anchored_to_the_layout_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from inside a subdirectory; the evidence still lands in the log."""
    root = _repo(tmp_path)
    inner = root / "docs" / "research" / "literature" / "digests"
    monkeypatch.chdir(inner)
    result = runner.invoke(
        app,
        ["digest", "extract", "sample", *_citekey_args(), "--verdict", "verified"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert not (inner / "defend-log").exists()
    assert list((root / "docs" / "research" / "defend-log").glob("*.yml"))


def test_an_explicit_log_dir_is_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    target = tmp_path / "elsewhere"
    result = _run(
        root,
        *_citekey_args(),
        "--verdict",
        "verified",
        "--log-dir",
        str(target),
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 0
    assert len(list(target.glob("*.yml"))) == len(EXPECTED_SAMPLE)


def test_a_member_without_an_artifact_is_reported_and_the_rest_still_land(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, ["a1", "b2"])
    result = _run(
        root,
        "--citekey",
        "a1",
        "--citekey",
        "b2",
        "--citekey",
        "ghost",
        "--verdict",
        "failed",
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [e["citekey"] for e in payload["errors"]] == ["ghost"]
    assert payload["updated"] == ["a1", "b2"]
    assert _block(root, "a1")["extraction"]["batch-check"] == "failed"


def test_a_sampled_paper_with_no_cells_block_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An artifact whose cells cannot be read is an error, not an empty check."""
    root = _repo(tmp_path, ["a1"])
    target = _digest(root, "a1")
    fm_lines, _body = split_frontmatter(target.read_text(encoding="utf-8"))
    target.write_text(
        "---\n" + "\n".join(fm_lines) + "\n---\n\nprose only\n", encoding="utf-8"
    )
    result = _run(root, "--citekey", "a1", monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["citekey"] == "a1"
