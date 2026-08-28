"""The ``digest extract`` CLI surface — axes, and the validating writer.

The weight is on the negative assertions (spec §11): a rejected cell must leave
**nothing** on disk, and there must be no path at this surface that records a
cell without validating it first (spec §3.3). `test_write_extraction_is_reached_
only_through_validate` pins that structurally, so a later bypass fails a test
rather than shipping.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from typer.testing import CliRunner

from defendable_science import cli as cli_mod
from defendable_science.cli import app
from defendable_science.core.frontmatter import split_frontmatter
from defendable_science.digest import artifact as artifact_mod
from defendable_science.digest.artifact import read_cells
from defendable_science.literature import registry as registry_mod
from defendable_science.scaffold.layout import Layout

if TYPE_CHECKING:
    from defendable_science.digest.extraction import Cell

runner = CliRunner()

POSITIONING = """# Positioning — p1

Author prose that must survive untouched.

## Concept matrix

| Method | guarantee type | partial monotonicity |
|---|---|---|
| **This paper** | architectural | yes |

More prose.
"""

PLACEHOLDER_POSITIONING = """# Positioning — p1

## Concept matrix

| Method | <attr 1> | <attr 2> |
|---|---|---|
| **This paper** | a | b |
"""

GOOD_CELLS: list[dict[str, Any]] = [
    {
        "citekey": "sill1997monotonic",
        "axis": "guarantee type",
        "value": "architectural — monotone by construction",
        "locator": "§2, Eq. (3)",
    },
    {
        "citekey": "sill1997monotonic",
        "axis": "partial monotonicity",
        "value": "not-addressed",
        "justification": "scoped to fully-monotone inputs in §1; never revisited",
    },
]


def _repo(
    tmp_path: Path,
    *,
    config: str = "",
    positioning: str = POSITIONING,
) -> Path:
    """Build a minimal onboarded repo with one paper's positioning document."""
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        config, encoding="utf-8"
    )
    docs = tmp_path / "docs" / "research" / "p1" / "paper"
    docs.mkdir(parents=True)
    (docs / "positioning.md").write_text(positioning, encoding="utf-8")
    return tmp_path


def _cells_file(tmp_path: Path, payload: object) -> str:
    """Write a ``--cells`` JSON file and return its path."""
    target = tmp_path / "cells.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return str(target)


def _record(
    root: Path, cells: object, *extra: str, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Run ``digest extract record --paper p1`` over `cells` from `root`."""
    monkeypatch.chdir(root)
    return runner.invoke(
        app,
        [
            "digest",
            "extract",
            "record",
            "--paper",
            "p1",
            "--cells",
            _cells_file(root, cells),
            *extra,
        ],
    )


# --- axes ----------------------------------------------------------------------


def test_axes_prints_the_matrix_axes_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["axes"] == ["guarantee type", "partial monotonicity"]
    assert payload["positioning"].endswith("docs/research/p1/paper/positioning.md")


def test_axes_resolves_the_positioning_document_from_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--paper`` names the paper; the layout supplies the path (never the cwd)."""
    root = _repo(tmp_path, config="layout:\n  research_root: writing\n")
    moved = root / "writing" / "p1" / "paper"
    moved.mkdir(parents=True)
    (moved / "positioning.md").write_text(POSITIONING, encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["positioning"] == str(moved / "positioning.md")


def test_axes_infers_the_paper_from_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root / "docs" / "research" / "p1" / "paper")
    result = runner.invoke(app, ["digest", "extract", "axes"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["axes"] == [
        "guarantee type",
        "partial monotonicity",
    ]


def test_axes_outside_a_paper_exits_2_naming_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes"])
    assert result.exit_code == 2
    assert "--paper" in result.stderr


def test_axes_positioning_option_overrides_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    other = root / "elsewhere.md"
    other.write_text(
        "## Concept matrix\n\n| Method | only axis |\n|---|---|\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "axes", "--positioning", "elsewhere.md"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["axes"] == ["only axis"]
    # The reported path is absolute whichever branch resolved it, even though a
    # relative --positioning is honoured as typed.
    assert payload["positioning"] == str(other.resolve())


def test_axes_refuses_a_placeholder_matrix_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 1
    assert "template placeholders" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_axes_reports_a_missing_positioning_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p2"])
    assert result.exit_code == 1
    assert "positioning document not found" in result.stderr


def test_axes_reports_an_invalid_layout_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, config="layout:\n  nope: x\n")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 1
    assert "unknown layout key" in result.stderr


# --- cells: the read-only accessor (defendable-science#141) -----------------------


def test_cells_prints_the_recorded_cells_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    result = runner.invoke(
        app, ["digest", "extract", "cells", "--citekey", "sill1997monotonic"]
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["citekey"] == "sill1997monotonic"
    assert payload["error"] is None
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    assert payload["artifact"] == str(artifact)
    assert payload["cells"] == [
        {
            "citekey": "sill1997monotonic",
            "axis": "guarantee type",
            "value": "architectural — monotone by construction",
            "locator": "§2, Eq. (3)",
            "justification": None,
        },
        {
            "citekey": "sill1997monotonic",
            "axis": "partial monotonicity",
            "value": "not-addressed",
            "locator": None,
            "justification": ("scoped to fully-monotone inputs in §1; never revisited"),
        },
    ]


def test_cells_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No write, no log entry — a pure reader over an already-recorded paper."""
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    before = artifact.read_text(encoding="utf-8")
    log_dir = root / "docs" / "research" / "defend-log"
    before_log = sorted(log_dir.iterdir()) if log_dir.is_dir() else []
    result = runner.invoke(
        app, ["digest", "extract", "cells", "--citekey", "sill1997monotonic"]
    )
    assert result.exit_code == 0, result.stderr
    assert artifact.read_text(encoding="utf-8") == before
    after_log = sorted(log_dir.iterdir()) if log_dir.is_dir() else []
    assert after_log == before_log


def test_cells_refuses_a_paper_with_no_digest_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "cells", "--citekey", "never-extracted"]
    )
    assert result.exit_code == 1
    assert "digest extract cells failed" in result.stderr
    assert "digest artifact not found" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["cells"] is None
    assert payload["error"]


def test_cells_refuses_an_artifact_with_no_cells_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A digest that exists (e.g. depth mode only) but was never extracted."""
    root = _repo(tmp_path)
    layout = Layout.default(root.resolve())
    layout.digests_dir.mkdir(parents=True)
    artifact = layout.digest("neverextracted2020")
    artifact.write_text(
        "---\nstatus:\n  understanding: {status: ok, unresolved: []}\n---\n\nBody.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "cells", "--citekey", "neverextracted2020"]
    )
    assert result.exit_code == 1
    assert "has not been extracted" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["cells"] is None


def test_cells_refuses_a_malformed_cells_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    layout = Layout.default(root.resolve())
    layout.digests_dir.mkdir(parents=True)
    artifact = layout.digest("corrupt2021")
    artifact.write_text(
        "---\nstatus:\n  extraction: {cells: 1, locators: ok, in-sample: false, "
        "batch-check: pending}\n---\n\n"
        f"{artifact_mod.CELLS_END}\n{artifact_mod.CELLS_BEGIN}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "cells", "--citekey", "corrupt2021"]
    )
    assert result.exit_code == 1
    assert "markers are malformed" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_cells_missing_citekey_option_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo(tmp_path))
    result = runner.invoke(app, ["digest", "extract", "cells"])
    assert result.exit_code == 2


# --- record: the happy path ------------------------------------------------------


def test_record_writes_the_artifact_the_layout_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer's path and ``Layout.digest`` must be the same file."""
    root = _repo(tmp_path)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    layout = Layout.default(root.resolve())
    artifact = layout.digest("sill1997monotonic")
    assert artifact.parent == layout.digests_dir
    assert artifact.is_file()
    payload = json.loads(result.stdout)
    assert payload["recorded"] == [
        {
            "citekey": "sill1997monotonic",
            "artifact": str(artifact),
            "cells": 2,
            "not_addressed": 1,
            "log_entry": payload["recorded"][0]["log_entry"],
        }
    ]
    assert payload["rejected"] == []
    assert payload["errors"] == []
    assert payload["not_addressed"] == 1
    assert payload["ok"] is True


def test_record_round_trips_through_read_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    cells: list[Cell] = read_cells(
        Layout.default(root.resolve()).digest("sill1997monotonic")
    )
    assert [c.axis for c in cells] == ["guarantee type", "partial monotonicity"]
    assert cells[0].locator == "§2, Eq. (3)"
    assert cells[1].value == "not-addressed"


def test_record_writes_extraction_and_never_understanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    text = Layout.default(root.resolve()).digest("sill1997monotonic").read_text()
    fm_lines, _body = split_frontmatter(text)
    status = yaml.safe_load("\n".join(fm_lines))["status"]
    # The guarantee-inflation guard: extraction owns `extraction` and only it.
    assert set(status) == {"extraction", "last-updated"}
    assert status["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "pending",
    }


def test_record_appends_the_accountability_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _record(
        root, GOOD_CELLS, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 0
    entries = sorted((root / "log").iterdir())
    assert len(entries) == 1
    assert "kind: extraction" in entries[0].read_text(encoding="utf-8")
    assert json.loads(result.stdout)["recorded"][0]["log_entry"] == str(entries[0])


def test_record_logs_under_the_layout_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from inside a paper, the log must not land in that paper's tree."""
    root = _repo(tmp_path)
    cells = _cells_file(root, GOOD_CELLS)
    paper_dir = root / "docs" / "research" / "p1"
    monkeypatch.chdir(paper_dir)
    result = runner.invoke(app, ["digest", "extract", "record", "--cells", cells])
    assert result.exit_code == 0, result.stderr
    assert not (paper_dir / "docs").exists()
    entries = sorted((root / "docs" / "research" / "defend-log").iterdir())
    assert len(entries) == 1
    assert json.loads(result.stdout)["recorded"][0]["log_entry"] == str(entries[0])


def test_record_reads_the_cells_from_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "extract", "record", "--paper", "p1", "--cells", "-"],
        input=json.dumps(GOOD_CELLS),
    )
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("sill1997monotonic").is_file()


def test_record_creates_the_digests_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``init`` does not scaffold ``literature/digests/``; ``record`` must."""
    root = _repo(tmp_path)
    assert not Layout.default(root.resolve()).digests_dir.exists()
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    assert Layout.default(root.resolve()).digests_dir.is_dir()


def test_record_honours_the_positioning_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    (root / "other.md").write_text(
        "## Concept matrix\n\n| Method | only axis |\n|---|---|\n", encoding="utf-8"
    )
    result = _record(
        root,
        [
            {
                "citekey": "a2020",
                "axis": "only axis",
                "value": "v",
                "locator": "p. 7",
            }
        ],
        "--positioning",
        "other.md",
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("a2020").is_file()
    assert json.loads(result.stdout)["positioning"] == str(
        (root / "other.md").resolve()
    )


# --- record: refusal (nothing may land) -------------------------------------------

_BAD_BATCHES: list[tuple[str, list[dict[str, Any]], str]] = [
    (
        "no locator",
        [
            {"citekey": "a2020", "axis": "guarantee type", "value": "v"},
            {"citekey": "a2020", "axis": "partial monotonicity", "value": "w"},
        ],
        "has no locator",
    ),
    (
        "vague locator",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "see paper",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§1",
            },
        ],
        "matches no known form",
    ),
    (
        "omitted axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            }
        ],
        "is missing",
    ),
    (
        "invented axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§2",
            },
            {"citekey": "a2020", "axis": "invented", "value": "x", "locator": "§3"},
        ],
        "is not a matrix axis",
    ),
    (
        "duplicate axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            },
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v2",
                "locator": "§2",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§3",
            },
        ],
        "recorded 2 times",
    ),
    (
        "unjustified not-addressed",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "not-addressed",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§2",
            },
        ],
        "no justification",
    ),
]


@pytest.mark.parametrize(
    ("cells", "wanted"),
    [pytest.param(c, w, id=name) for name, c, w in _BAD_BATCHES],
)
def test_record_refuses_and_writes_nothing(
    cells: list[dict[str, Any]],
    wanted: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No rule may be satisfied by a write: a rejected paper leaves no trace."""
    root = _repo(tmp_path)
    result = _record(
        root, cells, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert "a2020" in result.stderr
    assert not Layout.default(root.resolve()).digest("a2020").exists()
    assert not (root / "log").exists()
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["recorded"] == []
    assert [r["citekey"] for r in payload["rejected"]] == ["a2020"] * len(
        payload["rejected"]
    )
    assert all(r["axis"] for r in payload["rejected"])
    assert any(wanted in r["reason"] for r in payload["rejected"])


def test_record_rejects_per_paper_and_records_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad paper must not abort the sweep, and must not half-land."""
    root = _repo(tmp_path)
    cells = [
        *GOOD_CELLS,
        {"citekey": "bad2021", "axis": "guarantee type", "value": "v"},
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    layout = Layout.default(root.resolve())
    assert layout.digest("sill1997monotonic").is_file()
    assert not layout.digest("bad2021").exists()
    payload = json.loads(result.stdout)
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    assert {r["citekey"] for r in payload["rejected"]} == {"bad2021"}


def test_record_reports_a_write_failure_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    artifact.parent.mkdir(parents=True)
    artifact.write_text("no frontmatter here\n", encoding="utf-8")
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "digest extract record failed for sill1997monotonic" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["recorded"] == []
    assert [e["citekey"] for e in payload["errors"]] == ["sill1997monotonic"]
    assert payload["errors"][0]["artifact"] == str(artifact)
    assert payload["errors"][0]["reason"]


def test_record_reports_what_landed_when_one_paper_fails_to_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partly-landed batch must say what landed, not only that it failed.

    Aborting on the first write failure leaves the author knowing something went
    wrong but not which papers are already recorded — and re-running the whole
    batch to find out appends a second log entry for each of them.
    """
    root = _repo(tmp_path)
    layout = Layout.default(root.resolve())
    corrupt = layout.digest("zz2021")
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("no frontmatter here\n", encoding="utf-8")
    cells = [
        *GOOD_CELLS,
        {"citekey": "zz2021", "axis": "guarantee type", "value": "v", "locator": "§1"},
        {
            "citekey": "zz2021",
            "axis": "partial monotonicity",
            "value": "w",
            "locator": "§2",
        },
    ]
    result = _record(
        root, cells, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    assert [e["citekey"] for e in payload["errors"]] == ["zz2021"]
    assert payload["rejected"] == []
    # The good paper really did land, exactly as the report says.
    assert layout.digest("sill1997monotonic").is_file()
    assert len(list((root / "log").iterdir())) == 1


# --- record: the triage writeback --------------------------------------------------


def _triage(root: Path) -> dict[str, Any]:
    """Load the triage sidecar the default layout names."""
    text = Layout.default(root.resolve()).triage.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


def _write_triage(root: Path, text: str) -> Path:
    """Seed the triage sidecar with `text`, creating its directory."""
    target = Layout.default(root.resolve()).triage
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_record_writes_the_extraction_facts_to_triage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recorded paper leaves two factual scalars on its triage row."""
    root = _repo(tmp_path)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    row = _triage(root)["sill1997monotonic"]
    assert row["extraction-cells"] == 2
    # The same date the artifact carries — one value per run, not a second clock.
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    fm_lines, _body = split_frontmatter(artifact.read_text(encoding="utf-8"))
    last_updated = yaml.safe_load("\n".join(fm_lines))["status"]["last-updated"]
    assert row["extracted"] == str(last_updated)
    assert isinstance(row["extracted"], str)
    assert json.loads(result.stdout)["triage_not_updated"] == []


def test_record_creates_a_triage_row_for_a_paper_that_had_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar need not exist yet, and existing rows must survive."""
    root = _repo(tmp_path)
    _write_triage(root, "other1997:\n  disposition: interesting\n")
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    loaded = _triage(root)
    assert loaded["other1997"] == {"disposition": "interesting"}
    assert set(loaded["sill1997monotonic"]) == {"extracted", "extraction-cells"}


def test_record_never_touches_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`disposition` is the human's decision state machine — extraction is not.

    A machine advancing ``screened -> interesting`` would be exactly the agency
    violation this plugin exists to prevent, so the negative is pinned twice:
    an existing value is left alone, and no key is invented where none was.
    """
    root = _repo(tmp_path)
    _write_triage(
        root,
        "sill1997monotonic:\n"
        "  disposition: screened\n"
        "  rationale: matches the inclusion criteria\n"
        "zz2021:\n"
        "  rationale: queued\n",
    )
    cells = [
        *GOOD_CELLS,
        {"citekey": "zz2021", "axis": "guarantee type", "value": "v", "locator": "§1"},
        {
            "citekey": "zz2021",
            "axis": "partial monotonicity",
            "value": "w",
            "locator": "§2",
        },
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    loaded = _triage(root)
    assert loaded["sill1997monotonic"]["disposition"] == "screened"
    assert loaded["sill1997monotonic"]["rationale"] == "matches the inclusion criteria"
    assert "disposition" not in loaded["zz2021"]
    assert loaded["zz2021"]["extraction-cells"] == 2


def test_record_writes_the_cells_before_it_touches_triage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordering is load-bearing: a triage refusal must not discard cells."""
    root = _repo(tmp_path)
    calls: list[str] = []
    real_write = artifact_mod.write_extraction
    real_patch = registry_mod.patch_triage

    def spy_write(*args: Any, **kwargs: Any) -> Any:
        calls.append("write_extraction")
        return real_write(*args, **kwargs)

    def spy_patch(*args: Any, **kwargs: Any) -> None:
        calls.append("patch_triage")
        real_patch(*args, **kwargs)

    monkeypatch.setattr(artifact_mod, "write_extraction", spy_write)
    monkeypatch.setattr(registry_mod, "patch_triage", spy_patch)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    assert calls == ["write_extraction", "patch_triage"]


@pytest.mark.parametrize(
    ("sidecar", "wanted"),
    [
        pytest.param(
            "# screened 2026-08-01 against the protocol\n"
            "sill1997monotonic:\n"
            "  disposition: screened\n"
            "  rationale: the PRISMA audit trail lives in this comment\n",
            "carries comments",
            id="comments",
        ),
        pytest.param(
            "other1997: include\nsill1997monotonic:\n  disposition: screened\n",
            "not mappings",
            id="non-mapping-row",
        ),
        pytest.param(
            "a2020: &shared\n"
            "  disposition: screened\n"
            "b2021: *shared\n"
            "sill1997monotonic:\n"
            "  disposition: screened\n",
            "same mapping",
            id="aliased-rows",
        ),
    ],
)
def test_record_reports_a_refused_triage_and_leaves_it_byte_identical(
    sidecar: str, wanted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is visible and non-zero-exit — and the cells still landed.

    `patch_triage` refuses rather than destroy a hand-authored sidecar. That
    refusal is not a write *failure*, so it gets its own report key: a reader
    must not conclude the artifact failed when it did not.
    """
    root = _repo(tmp_path)
    triage = _write_triage(root, sidecar)
    before = triage.read_bytes()
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    assert "triage not updated for sill1997monotonic" in result.stderr
    # Nothing was rewritten, and nothing stripped the comments to get around it.
    assert triage.read_bytes() == before
    assert not list(triage.parent.glob("*.tmp"))
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"] == []
    assert [t["citekey"] for t in payload["triage_not_updated"]] == [
        "sill1997monotonic"
    ]
    assert wanted in payload["triage_not_updated"][0]["reason"]
    assert str(triage) in payload["triage_not_updated"][0]["reason"]
    # A principled refusal, not a write that failed — a reader must be able to
    # tell "edit this file by hand" from "the disk said no" without a regex.
    assert payload["triage_not_updated"][0]["kind"] == "refused"
    # The extraction itself is intact: refusing the sidecar discards nothing.
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    assert len(read_cells(artifact)) == 2


def test_record_never_fabricates_an_extraction_record_for_an_aliased_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worst thing this branch could ship, pinned as a negative.

    Rows joined by a YAML anchor are one dict after `yaml.safe_load`, so an
    unguarded patch of ``sill1997monotonic`` would write ``extracted`` and
    ``extraction-cells`` onto ``b2021`` and ``c2022`` as well — an extraction
    record, in the PRISMA audit trail, for two papers this run never touched,
    at exit 0 and with no diagnostic. The refusal is what prevents that; this
    fails loudly if it is ever reverted.
    """
    root = _repo(tmp_path)
    triage = _write_triage(
        root,
        "sill1997monotonic: &shared\n"
        "  disposition: screened\n"
        "b2021: *shared\n"
        "c2022: *shared\n",
    )
    before = triage.read_bytes()
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert triage.read_bytes() == before
    loaded = _triage(root)
    for citekey in ("sill1997monotonic", "b2021", "c2022"):
        assert "extracted" not in loaded[citekey]
        assert "extraction-cells" not in loaded[citekey]
    payload = json.loads(result.stdout)
    assert payload["triage_not_updated"][0]["kind"] == "refused"
    assert "b2021" in payload["triage_not_updated"][0]["reason"]
    # And the ordering property still holds: the cells landed regardless.
    assert len(read_cells(Layout.default(root.resolve()).digest("sill1997monotonic")))


def test_record_reports_an_unwritable_triage_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OS-level failure on the sidecar is reported, not raised."""
    root = _repo(tmp_path)
    triage = Layout.default(root.resolve()).triage
    triage.mkdir(parents=True)  # a directory where the sidecar should be
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    payload = json.loads(result.stdout)
    assert [t["citekey"] for t in payload["triage_not_updated"]] == [
        "sill1997monotonic"
    ]
    # `failed`, not `refused`: nothing here is a principled decision, and the
    # remedy is not "edit the sidecar by hand".
    assert payload["triage_not_updated"][0]["kind"] == "failed"
    assert payload["errors"] == []
    assert Layout.default(root.resolve()).digest("sill1997monotonic").is_file()


def test_record_honours_a_configured_triage_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, config="literature:\n  triage: notes/decisions.yml\n")
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    loaded = yaml.safe_load((root / "notes" / "decisions.yml").read_text("utf-8"))
    assert loaded["sill1997monotonic"]["extraction-cells"] == 2
    assert not Layout.default(root.resolve()).triage.exists()


def test_record_does_not_touch_triage_for_a_paper_that_failed_to_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cells, no claim: a failed artifact must leave no extraction facts."""
    root = _repo(tmp_path)
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    artifact.parent.mkdir(parents=True)
    artifact.write_text("no frontmatter here\n", encoding="utf-8")
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 1
    assert not Layout.default(root.resolve()).triage.exists()


# --- record: malformed input -------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "wanted"),
    [
        pytest.param("{oops", "not valid JSON", id="not-json"),
        pytest.param('{"citekey": "a"}', "must be a JSON array", id="not-an-array"),
        pytest.param("[3]", "must be a JSON object", id="non-object-element"),
        pytest.param(
            '[{"citekey": "a", "axis": "b", "value": "c", "locater": "§1"}]',
            "unknown field",
            id="unknown-field",
        ),
        pytest.param(
            '[{"citekey": "a", "axis": "b", "value": 3}]',
            "must be a string",
            id="wrong-type",
        ),
        pytest.param('[{"axis": "b"}]', "malformed", id="missing-field"),
        pytest.param("[]", "empty", id="empty-array"),
        pytest.param("   ", "empty", id="blank"),
    ],
)
def test_record_refuses_a_malformed_cells_file(
    payload: str, wanted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    target = root / "cells.json"
    target.write_text(payload, encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "extract", "record", "--paper", "p1", "--cells", str(target)],
    )
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert "--cells" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_record_reports_an_unreadable_cells_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "record", "--paper", "p1", "--cells", "nope.json"]
    )
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    assert "nope.json" in result.stderr


def test_record_refuses_a_placeholder_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "template placeholders" in result.stderr


# --- record: configured locator patterns --------------------------------------------


def test_record_accepts_a_configured_locator_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(
        tmp_path,
        config=(
            "literature:\n"
            "  extraction:\n"
            "    locator_patterns:\n"
            '      - "para\\\\. \\\\d+"\n'
        ),
    )
    cells = [
        {
            "citekey": "a2020",
            "axis": "guarantee type",
            "value": "v",
            "locator": "para. 4",
        },
        {
            "citekey": "a2020",
            "axis": "partial monotonicity",
            "value": "w",
            "locator": "§2",
        },
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("a2020").is_file()


@pytest.mark.parametrize(
    ("config", "wanted"),
    [
        pytest.param(
            "literature:\n  extraction: nope\n",
            "'literature.extraction' must be a mapping",
            id="extraction-not-a-mapping",
        ),
        pytest.param(
            "literature:\n  extraction:\n    locator_patterns: nope\n",
            "'literature.extraction.locator_patterns' must be a list",
            id="patterns-not-a-list",
        ),
        pytest.param(
            "literature:\n  extraction:\n    locator_patterns: [3]\n",
            "'literature.extraction.locator_patterns' must be a list",
            id="pattern-not-a-string",
        ),
        pytest.param(
            'literature:\n  extraction:\n    locator_patterns: ["([a-"]\n',
            "invalid locator pattern '([a-'",
            id="invalid-regex",
        ),
        pytest.param(
            'literature:\n  extraction:\n    locator_patterns: ["(?P<x>a)", "(?P<x>b)"]\n',
            "cannot be combined",
            id="colliding-group-names",
        ),
        pytest.param(
            "literature: nope\n",
            "'literature' must be a mapping",
            id="literature-not-a-mapping",
        ),
    ],
)
def test_record_refuses_bad_locator_pattern_config(
    config: str, wanted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, config=config)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert not Layout.default(root.resolve()).digest("sill1997monotonic").exists()


# --- the shared report shape (fix: one contract across the four verbs) -------------


def test_axes_reports_ok_and_no_error_on_the_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``ok`` agrees with the exit code here exactly as it does for the others."""
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["error"] is None


def test_axes_still_emits_a_report_when_the_matrix_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is a report, and ``axes: null`` is not "a matrix with no axes"."""
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    # The negative: a caller must not be able to read the refusal as an empty
    # question set and go on to extract nothing against it.
    assert payload["axes"] is None
    assert payload["axes"] != []
    assert "template placeholders" in payload["error"]
    assert payload["positioning"].endswith("positioning.md")


def test_record_still_emits_a_report_when_the_input_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parse failure is a run outcome, so it gets the run's report."""
    root = _repo(tmp_path)
    target = root / "cells.json"
    target.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "extract", "record", "--paper", "p1", "--cells", str(target)],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["axes"] is None
    assert payload["recorded"] == []
    assert payload["not_addressed"] == 0
    assert "empty array" in payload["error"]


def test_record_reports_no_error_when_everything_landed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["error"] is None


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["digest", "extract", "axes", "--paper", "p1"], id="axes"),
        pytest.param(["digest", "extract", "render", "--paper", "p1"], id="render"),
        pytest.param(["digest", "extract", "sample", "--all"], id="sample"),
        pytest.param(
            ["digest", "extract", "record", "--paper", "p1", "--cells", "cells.json"],
            id="record",
        ),
    ],
)
def test_every_verb_reports_ok_agreeing_with_its_exit_code(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One contract for a caller scripting all four: JSON, and ``ok == exit 0``.

    Run against a repo where each verb fails, because the failing paths are the
    ones that used to disagree — two of them emitted no JSON at all.
    """
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    (root / "docs" / "research" / "literature" / "digests").mkdir(parents=True)
    (root / "cells.json").write_text(json.dumps(GOOD_CELLS), encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(app, argv)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]


# --- record: the self-reference row is never an extracted paper ---------------------


SELF_CELLS: list[dict[str, Any]] = [
    {
        "citekey": "**This paper**",
        "axis": "guarantee type",
        "value": "architectural",
        "locator": "§1",
    },
    {
        "citekey": "**This paper**",
        "axis": "partial monotonicity",
        "value": "yes",
        "locator": "§2",
    },
]


def test_record_refuses_the_self_row_as_a_citekey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the artifact lands and poisons every later ``render --all``.

    Every cell here is individually valid, so nothing but this rule stops it.
    """
    root = _repo(tmp_path)
    result = _record(
        root, SELF_CELLS, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["recorded"] == []
    assert [r["citekey"] for r in payload["rejected"]] == ["**This paper**"]
    # A whole-paper problem, so no axis is named — and it is the *only* reason
    # reported, not buried under per-axis noise.
    assert payload["rejected"][0]["axis"] is None
    assert "author's own delta" in payload["rejected"][0]["reason"]
    assert "**This paper**" in result.stderr
    # Nothing on disk: no artifact to poison a later merge, no log entry.
    digests = root / "docs" / "research" / "literature" / "digests"
    assert not list(digests.glob("*.md"))
    assert not (root / "log").exists()


def test_the_self_row_is_rejected_per_paper_and_the_rest_still_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rejection is per paper, not per batch — and the merge still runs.

    The defect this pins: caught only at ``render``, one poisoned artifact
    refuses the *whole* batch's merge, forever, with a message about the
    author's own delta rather than about the artifact.
    """
    root = _repo(tmp_path)
    result = _record(root, [*SELF_CELLS, *GOOD_CELLS], monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    assert [r["citekey"] for r in payload["rejected"]] == ["**This paper**"]
    layout = Layout.default(root.resolve())
    assert layout.digest("sill1997monotonic").is_file()
    assert not layout.digest("**This paper**").exists()
    # And the merge the poisoned artifact would have blocked still succeeds.
    merge = runner.invoke(app, ["digest", "extract", "render", "--paper", "p1"])
    assert merge.exit_code == 0, merge.stdout + merge.stderr
    assert json.loads(merge.stdout)["rendered"] == ["sill1997monotonic"]


# --- exit codes --------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["digest", "extract", "record"], id="missing-required-option"),
        pytest.param(["digest", "extract", "axes", "--nope"], id="unknown-option"),
        pytest.param(["digest", "extract", "nope"], id="unknown-subcommand"),
    ],
)
def test_a_usage_error_still_exits_2(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2 belongs to Click. A domain outcome may never take it (#106/#119)."""
    monkeypatch.chdir(_repo(tmp_path))
    assert runner.invoke(app, argv).exit_code == 2


# --- the structural guarantee (spec §3.3) --------------------------------------------


def _callee(func: ast.expr) -> str | None:
    """Return the called name, whether it is bare or attribute-qualified."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    """Return every call to `name` inside `node`."""
    return [
        n for n in ast.walk(node) if isinstance(n, ast.Call) and _callee(n.func) == name
    ]


def test_write_extraction_is_reached_only_through_validate() -> None:
    """Validation and writing are one action — no bypass may be added.

    Pinned structurally, not by example: a flag, an env var or an early branch
    that wrote without validating would satisfy every behavioural test that
    exercises the validated path, and fail this one.

    **What this costs, so the next person does not loosen it by mistake.** The
    test also fails for a refactor that is *not* a bypass: extracting the write
    into a helper — even one called from exactly this loop — moves the call out
    of `extract_record` and out of the loop over the accepted cells, and this
    test cannot tell that apart from a second writer added elsewhere, because
    the two have the same shape. That is deliberate. If you hit it during an
    honest refactor, keep the write inline here; do not weaken the assertions to
    let a call site float free of the validation that produced its arguments.
    """
    tree = ast.parse(Path(cli_mod.__file__).read_text(encoding="utf-8"))
    writes = _calls(tree, "write_extraction")
    assert len(writes) == 1, "write_extraction must have exactly one call site"

    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    record_fn = functions["extract_record"]
    assert _calls(record_fn, "write_extraction") == writes

    # The accepted-cells name is whatever `validate`'s result is unpacked into.
    validations = [
        node
        for node in ast.walk(record_fn)
        if isinstance(node, ast.Assign) and _calls(node.value, "validate")
    ]
    assert len(validations) == 1
    target = validations[0].targets[0]
    assert isinstance(target, ast.Tuple)
    accepted = target.elts[0]
    assert isinstance(accepted, ast.Name)

    # …and the single write sits inside a loop over exactly that name.
    loops = [
        node
        for node in ast.walk(record_fn)
        if isinstance(node, ast.For)
        and accepted.id in ast.dump(node.iter)
        and _calls(node, "write_extraction")
    ]
    assert len(loops) == 1
